"""Local instructor state and an explicitly bounded iCalendar interchange.

No network access. Daily/weekly bounded recurrence is supported; unsupported
calendar semantics are rejected before import instead of being discarded.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Literal
from uuid import uuid4
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil.rrule import rrulestr
from icalendar import Calendar, Event as CalendarEvent, Timezone, vRecur
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

UTC = timezone.utc
_LOCK = threading.RLock()
MAX_BYTES = 5_000_000


class Conflict(ValueError):
    def __init__(self, revision):
        self.revision = revision
        super().__init__('Instructor tools changed in another window; reload before saving.')


class Corrupt(ValueError):
    pass


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Identified(Model):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')


class Checklist(Identified):
    label: str = Field(min_length=1, max_length=500)
    done: bool = False


class Practice(Identified):
    at: datetime
    duration_minutes: float = Field(default=0, ge=0, le=1440)
    notes: str = Field(default='', max_length=10000)

    @model_validator(mode='after')
    def timezone_required(self):
        if self.at.tzinfo is None:
            raise ValueError('Practice history needs a timestamp with a timezone offset.')
        return self


def safe_http_url(value):
    if not value:
        return
    parsed = urlsplit(value)
    if (parsed.scheme not in {'http','https'} or not parsed.netloc or parsed.username or parsed.password
            or any(ord(char) < 32 for char in value)):
        raise ValueError('Links must use http or https, have a host, and contain no credentials/control characters.')


class Recording(Identified):
    title: str = Field(min_length=1, max_length=300)
    artist: str = Field(default='', max_length=300)
    url: str = Field(default='', max_length=2048)
    local_path: str = Field(default='', max_length=4096)
    music_map: dict = Field(default_factory=dict)
    choreography_review: Literal['not_reviewed', 'compatible', 'needs_changes'] = 'not_reviewed'
    review_notes: str = Field(default='', max_length=10000)

    @model_validator(mode='after')
    def safe_url(self):
        safe_http_url(self.url)
        try:
            json.dumps(self.music_map, allow_nan=False)
        except (ValueError, TypeError) as error:
            raise ValueError('A recording music map must contain finite JSON values.') from error
        return self


class Dance(Identified):
    title: str = Field(min_length=1, max_length=300)
    project_id: str | None = None
    sheet_url: str = Field(default='', max_length=2048)
    video_url: str = Field(default='', max_length=2048)
    tags: list[str] = Field(default_factory=list, max_length=100)
    favorite: bool = False
    learning_status: Literal['new', 'learning', 'ready', 'review'] = 'new'
    public_notes: str = Field(default='', max_length=10000)
    private_notes: str = Field(default='', max_length=10000)
    checklist: list[Checklist] = Field(default_factory=list, max_length=200)
    practice_history: list[Practice] = Field(default_factory=list, max_length=2000)
    recordings: list[Recording] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def unique_children(self):
        safe_http_url(self.sheet_url)
        safe_http_url(self.video_url)
        for values in (self.checklist, self.practice_history, self.recordings):
            _unique(values)
        if any(len(tag) > 100 for tag in self.tags):
            raise ValueError('Tags must be at most 100 characters.')
        return self


class SetlistItem(Model):
    dance_id: str
    recording_id: str | None = None
    duration_minutes: float = Field(default=0, ge=0, le=1440)
    public_notes: str = Field(default='', max_length=10000)
    private_notes: str = Field(default='', max_length=10000)


class Setlist(Identified):
    title: str = Field(min_length=1, max_length=300)
    items: list[SetlistItem] = Field(default_factory=list, max_length=1000)
    public_notes: str = Field(default='', max_length=10000)
    private_notes: str = Field(default='', max_length=10000)


def local_time(text: str, zone_name: str) -> datetime:
    try:
        zone = ZoneInfo(zone_name)
        value = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise ValueError('Use an ISO date/time and a known IANA timezone, such as America/New_York.') from error
    if value.tzinfo is not None:
        projected = value.astimezone(zone)
        if projected.replace(tzinfo=None) != value.replace(tzinfo=None) or projected.utcoffset() != value.utcoffset():
            raise ValueError('The supplied offset does not match the selected timezone at this local time.')
        return projected
    choices = [value.replace(tzinfo=zone, fold=fold) for fold in (0, 1)]
    valid = [item for item in choices if item.astimezone(UTC).astimezone(zone).replace(tzinfo=None) == value]
    offsets = {item.utcoffset() for item in valid}
    if not offsets:
        raise ValueError('This local time does not exist because the clocks change; choose another time.')
    if len(offsets) > 1:
        raise ValueError('This local time occurs twice; include an explicit offset to choose which occurrence.')
    return valid[0]


def recurrence_times(start: datetime, rule: str) -> list[datetime]:
    if not rule:
        return [start]
    pieces = rule.upper().split(';')
    parts = {}
    for piece in pieces:
        key, sep, value = piece.partition('=')
        if not sep or key in parts:
            raise ValueError('Recurrence must contain unique KEY=VALUE fields.')
        parts[key] = value
    if set(parts) - {'FREQ', 'INTERVAL', 'COUNT', 'UNTIL', 'BYDAY'}:
        raise ValueError('Supported recurrence fields are FREQ, INTERVAL, COUNT or UNTIL, and weekly BYDAY.')
    if parts.get('FREQ') not in {'DAILY', 'WEEKLY'}:
        raise ValueError('Only daily or weekly recurrence is supported.')
    if ('COUNT' in parts) == ('UNTIL' in parts):
        raise ValueError('Recurrence must have exactly one end: COUNT or UTC UNTIL.')
    try:
        if not 1 <= int(parts.get('INTERVAL', '1')) <= 52:
            raise ValueError()
        if 'COUNT' in parts and not 1 <= int(parts['COUNT']) <= 366:
            raise ValueError()
        if 'UNTIL' in parts:
            until = datetime.strptime(parts['UNTIL'], '%Y%m%dT%H%M%SZ').replace(tzinfo=UTC)
            if until < start.astimezone(UTC) or until - start.astimezone(UTC) > timedelta(days=1827):
                raise ValueError()
    except ValueError as error:
        raise ValueError('Use interval 1–52, count 1–366, or a UTC end within five years.') from error
    if 'BYDAY' in parts and (parts['FREQ'] != 'WEEKLY' or
                            any(day not in {'MO','TU','WE','TH','FR','SA','SU'} for day in parts['BYDAY'].split(','))):
        raise ValueError('BYDAY supports weekday names in weekly recurrence only.')
    values = []
    for value in rrulestr(rule.upper(), dtstart=start):
        if len(values) >= 366 or value - start > timedelta(days=1827):
            raise ValueError('This recurrence exceeds the supported 366 occurrences/five-year limit.')
        # A recurring local wall time that lands in a DST gap/fold needs review.
        checked = local_time(value.replace(tzinfo=None).isoformat(), str(start.tzinfo))
        values.append(checked)
    if not values or values[0] != start:
        raise ValueError('The first occurrence must agree with the event start and selected weekdays.')
    return values


class LocalEvent(Identified):
    title: str = Field(min_length=1, max_length=300)
    start: str
    end: str
    timezone: str = 'UTC'
    location: str = Field(default='', max_length=1000)
    public_notes: str = Field(default='', max_length=10000)
    private_notes: str = Field(default='', max_length=10000)
    rrule: str = Field(default='', max_length=300)
    status: Literal['CONFIRMED','TENTATIVE','CANCELLED'] = 'CONFIRMED'
    uid: str = Field(default='', max_length=500)
    sequence: StrictInt = Field(default=0, ge=0)

    @model_validator(mode='after')
    def check_times(self):
        start, end = local_time(self.start, self.timezone), local_time(self.end, self.timezone)
        if start.microsecond or end.microsecond:
            raise ValueError('Calendar times support whole seconds; remove fractional seconds.')
        if end.astimezone(UTC) <= start.astimezone(UTC) or end.astimezone(UTC)-start.astimezone(UTC) > timedelta(days=7):
            raise ValueError('An event must end after it starts and last no more than seven days.')
        self.start, self.end = start.isoformat(), end.isoformat()
        self.rrule = self.rrule.upper()
        occurrences = recurrence_times(start, self.rrule)
        try:
            start.date() - timedelta(days=366)
            occurrences[-1].date() + timedelta(days=373)
        except OverflowError as error:
            raise ValueError('Event dates exceed the supported calendar timezone range.') from error
        if self.rrule:
            wall_duration = end.replace(tzinfo=None) - start.replace(tzinfo=None)
            for occurrence in occurrences:
                ending = local_time((occurrence.replace(tzinfo=None) + wall_duration).isoformat(), self.timezone)
                if ending.astimezone(UTC) <= occurrence.astimezone(UTC):
                    raise ValueError('A recurrence would end before it starts; review the timezone transition.')
        self.uid = self.uid or self.id + '@line-dance.local'
        if any(c in self.uid for c in '\r\n\x00'):
            raise ValueError('Calendar UID contains an invalid control character.')
        return self


def _unique(values):
    if len({item.id for item in values}) != len(values):
        raise ValueError('IDs must be unique within each collection.')


class State(Model):
    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    revision: StrictInt = Field(default=0, ge=0)
    dances: list[Dance] = Field(max_length=5000)
    setlists: list[Setlist] = Field(max_length=1000)
    events: list[LocalEvent] = Field(max_length=2000)

    @model_validator(mode='after')
    def references(self):
        for values in (self.dances, self.setlists, self.events):
            _unique(values)
        if len({e.uid for e in self.events}) != len(self.events):
            raise ValueError('Calendar UIDs must be unique.')
        dances = {dance.id: dance for dance in self.dances}
        for plan in self.setlists:
            for item in plan.items:
                dance = dances.get(item.dance_id)
                if dance is None:
                    raise ValueError('A setlist refers to a missing dance; remove or replace that item first.')
                if item.recording_id and item.recording_id not in {recording.id for recording in dance.recordings}:
                    raise ValueError('A setlist refers to a missing recording.')
        return self


def directory() -> Path:
    explicit = os.environ.get('LINE_DANCE_TOOLS_DIR')
    if explicit:
        return Path(explicit).expanduser().resolve()
    data = os.environ.get('LINE_DANCE_DATA_DIR')
    return (Path(data) / 'tools' if data else Path(__file__).resolve().parents[1] / 'instructor-data').resolve()


@contextmanager
def _locked():
    with _LOCK:
        root = directory()
        root.mkdir(parents=True, exist_ok=True)
        with (root / '.state.lock').open('a+b') as lock:
            if not lock.tell():
                lock.write(b'0'); lock.flush()
            limit = time.monotonic() + 5
            while True:
                try:
                    lock.seek(0)
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= limit:
                        raise OSError('Instructor tools are busy; retry after the other save finishes.')
                    time.sleep(.025)
            try:
                yield root
            finally:
                lock.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _read(root):
    path = root / 'state.json'
    if not path.exists():
        return State(dances=[], setlists=[], events=[])
    try:
        if path.stat().st_size > MAX_BYTES:
            raise ValueError('State exceeds its size limit.')
        return State.model_validate_json(path.read_bytes())
    except ValueError as error:
        raise Corrupt('Instructor data is unreadable or uses an unsupported schema. Preserve state.json and state.backup.json for recovery.') from error


def get_state():
    with _locked() as root:
        return _read(root).model_dump(mode='json')


def _atomic(path, data):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.state-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def save_state(value, expected_revision):
    candidate = State.model_validate(value)
    with _locked() as root:
        current = _read(root)
        if type(expected_revision) is not int or current.revision != expected_revision:
            raise Conflict(current.revision)
        old_events = {event.uid: event for event in current.events}
        for event in candidate.events:
            old = old_events.get(event.uid)
            if old:
                changed = event.model_dump(exclude={'sequence'}) != old.model_dump(exclude={'sequence'})
                event.sequence = max(event.sequence, old.sequence + int(changed))
        candidate.revision = current.revision + 1
        encoded = candidate.model_dump_json(indent=2).encode('utf-8')
        if len(encoded) > MAX_BYTES:
            raise ValueError('Instructor data exceeds the 5 MB local-store limit.')
        path = root / 'state.json'
        if path.exists():
            _atomic(root / 'state.backup.json', path.read_bytes())
        _atomic(path, encoded)
        return candidate.model_dump(mode='json')


def class_guide(setlist_id, include_private=False, as_html=True):
    state = State.model_validate(get_state())
    plan = next((p for p in state.setlists if p.id == setlist_id), None)
    if plan is None:
        raise FileNotFoundError('Setlist was not found.')
    dances = {d.id: d for d in state.dances}
    lines = [plan.title, f'Total planned time: {sum(i.duration_minutes for i in plan.items):g} minutes']
    links = {}
    if include_private:
        lines.append('PRIVATE INSTRUCTOR COPY — includes private notes')
    if plan.public_notes:
        lines.append(plan.public_notes)
    if include_private and plan.private_notes:
        lines.append('Instructor note: ' + plan.private_notes)
    for number, item in enumerate(plan.items, 1):
        dance = dances[item.dance_id]
        lines.append(f'{number}. {dance.title} ({item.duration_minutes:g} minutes)')
        for label, url in [('Step sheet', dance.sheet_url), ('Demo video', dance.video_url)]:
            if url:
                lines.append(label + ': ' + url)
                links[len(lines)-1] = (label, url)
        for note in (dance.public_notes, item.public_notes):
            if note:
                lines.append(note)
        if item.recording_id:
            recording = next(r for r in dance.recordings if r.id == item.recording_id)
            lines.append('Recording: ' + recording.title + (' — ' + recording.artist if recording.artist else ''))
            if recording.url:
                lines.append('Song link: ' + recording.url)
                links[len(lines)-1] = ('Song link', recording.url)
        if include_private:
            for note in (dance.private_notes, item.private_notes):
                if note:
                    lines.append('Instructor note: ' + note)
    if not as_html:
        return '\n\n'.join(lines) + '\n'
    paragraphs = []
    for index, line in enumerate(lines[1:], 1):
        if index in links:
            label, url = links[index]
            paragraphs.append('<p><a target="_blank" rel="noopener noreferrer" href="' + html.escape(url, quote=True) + '">' + html.escape(label) + '</a> — ' + html.escape(url) + '</p>')
        else:
            paragraphs.append('<p>' + html.escape(line) + '</p>')
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>' + html.escape(plan.title) + '</title><style>body{font:18px/1.5 system-ui;max-width:850px;margin:2rem auto;padding:0 1rem}p{white-space:pre-wrap}</style><body><h1>' + html.escape(lines[0]) + '</h1>' + ''.join(paragraphs) + '</body></html>'


def export_ics(include_private=False):
    state = State.model_validate(get_state())
    calendar = Calendar()
    calendar.add('prodid', '-//Hillbilly Hellfire//Line Dance Creator//EN')
    calendar.add('version', '2.0')
    calendar.add('calscale', 'GREGORIAN')
    ranges = {}
    for event in state.events:
        start, end = local_time(event.start, event.timezone), local_time(event.end, event.timezone)
        occurrences = recurrence_times(start, event.rrule)
        first, last = start.date() - timedelta(days=366), occurrences[-1].date() + timedelta(days=373)
        if event.timezone != 'UTC':
            prior = ranges.get(event.timezone, (first, last))
            ranges[event.timezone] = (min(first, prior[0]), max(last, prior[1]))
        component = CalendarEvent()
        component.add('uid', event.uid)
        component.add('sequence', event.sequence)
        component.add('dtstamp', datetime.now(UTC))
        # UTC preserves an explicitly selected repeated-hour occurrence.
        ambiguous = start.replace(fold=0).utcoffset() != start.replace(fold=1).utcoffset() or end.replace(fold=0).utcoffset() != end.replace(fold=1).utcoffset()
        component.add('dtstart', start.astimezone(UTC) if ambiguous else start)
        component.add('dtend', end.astimezone(UTC) if ambiguous else end)
        component.add('x-ldc-timezone', event.timezone)
        component.add('summary', event.title)
        component.add('location', event.location)
        component.add('status', event.status)
        component.add('description', event.public_notes)
        if include_private and event.private_notes:
            # Keep privacy classification on reimport; ordinary calendars may
            # ignore this custom field, but must not treat it as public prose.
            component.add('x-ldc-private-notes', event.private_notes)
        if event.rrule:
            component.add('rrule', vRecur.from_ical(event.rrule))
        calendar.add_component(component)
    for zone, (first, last) in ranges.items():
        calendar.add_component(Timezone.from_tzinfo(ZoneInfo(zone), first_date=first, last_date=last))
    return calendar.to_ical()


def parse_ics(text):
    if len(text.encode('utf-8')) > MAX_BYTES:
        raise ValueError('Calendar exceeds the 5 MB import limit.')
    try:
        calendar = Calendar.from_ical(text)
    except Exception as error:
        raise ValueError('This file is not a readable iCalendar file.') from error
    if calendar.name != 'VCALENDAR' or str(calendar.get('VERSION', '')) != '2.0':
        raise ValueError('An iCalendar 2.0 VCALENDAR is required.')
    if set(calendar.keys()) - {'VERSION','PRODID','CALSCALE','METHOD','X-WR-CALNAME','X-WR-TIMEZONE'}:
        raise ValueError('This calendar contains unsupported properties; simplify it before importing.')
    if str(calendar.get('METHOD', '')).upper() not in {'','PUBLISH'}:
        raise ValueError('Invitations, organizer actions and METHOD cancellations are not supported; use event STATUS:CANCELLED.')
    if str(calendar.get('CALSCALE', 'GREGORIAN')).upper() != 'GREGORIAN':
        raise ValueError('Only Gregorian calendar dates are supported.')
    if any(c.name not in {'VEVENT','VTIMEZONE'} for c in calendar.subcomponents):
        raise ValueError('Only events and known timezone definitions are supported.')
    zones = {}
    for component in calendar.walk('VTIMEZONE'):
        name = str(component.get('TZID', ''))
        try:
            ZoneInfo(name)
            if name in zones:
                raise ValueError('Duplicate timezone definition.')
            zones[name] = component.to_tz(lookup_tzid=False)
        except Exception as error:
            raise ValueError('Custom/unknown timezone definitions are unsupported; export with known IANA zones or UTC.') from error
    events = []
    if len(calendar.walk('VEVENT')) > 2000:
        raise ValueError('A calendar import supports at most 2,000 events.')
    allowed = {'UID','DTSTART','DTEND','DTSTAMP','SUMMARY','DESCRIPTION','LOCATION','STATUS','SEQUENCE','RRULE','CREATED','LAST-MODIFIED','X-LDC-TIMEZONE','X-LDC-PRIVATE-NOTES','CLASS'}
    for component in calendar.walk('VEVENT'):
        if component.errors or component.subcomponents or set(component.keys()) - allowed:
            raise ValueError('Unsupported event properties or alarms: all-day events, exceptions, attendees and attachments require manual entry.')
        if any(isinstance(component.get(key), list) for key in allowed):
            raise ValueError('Duplicate calendar properties are unsupported.')
        for key, value in component.items():
            allowed_parameters = {'TZID','VALUE'} if key in {'DTSTART','DTEND'} else set()
            if set(getattr(value, 'params', {})) - allowed_parameters:
                raise ValueError('Unsupported calendar property parameters require manual review.')
        if not all(key in component for key in ('UID','DTSTART','DTEND','SUMMARY')):
            raise ValueError('Every imported event needs UID, DTSTART, DTEND and SUMMARY.')
        if str(component.get('CLASS','PUBLIC')).upper() != 'PUBLIC':
            raise ValueError('Private/confidential calendar events require manual review before entering a public event list.')
        start, end = component.decoded('DTSTART'), component.decoded('DTEND')
        if not isinstance(start, datetime) or not isinstance(end, datetime) or start.tzinfo is None or end.tzinfo is None:
            raise ValueError('All-day and floating-time events require manual entry with a timezone.')
        start_zone = str(component['DTSTART'].params.get('TZID', 'UTC'))
        end_zone = str(component['DTEND'].params.get('TZID', 'UTC'))
        if start_zone != end_zone:
            raise ValueError('Start/end timezone changes require manual entry.')
        zone = str(component.get('X-LDC-TIMEZONE', start_zone))
        try:
            selected = ZoneInfo(zone)
        except ZoneInfoNotFoundError as error:
            raise ValueError('Unknown event timezone.') from error
        # UTC exports may carry their original display zone for an exact fold.
        if start_zone == 'UTC':
            start, end = start.astimezone(selected), end.astimezone(selected)
        elif zone != start_zone:
            raise ValueError('Conflicting event timezone identifiers.')
        event = LocalEvent(id=uuid4().hex, uid=str(component['UID']), title=str(component['SUMMARY']),
                           start=start.isoformat(), end=end.isoformat(), timezone=zone,
                           location=str(component.get('LOCATION','')), public_notes=str(component.get('DESCRIPTION','')),
                           private_notes=str(component.get('X-LDC-PRIVATE-NOTES','')),
                           status=str(component.get('STATUS','CONFIRMED')).upper(), sequence=int(component.get('SEQUENCE',0)),
                           rrule=component['RRULE'].to_ical().decode() if 'RRULE' in component else '')
        if start_zone in zones:
            for when in [*recurrence_times(local_time(event.start, zone), event.rrule), local_time(event.end, zone)]:
                instant = when.astimezone(UTC)
                if instant.astimezone(zones[start_zone]).utcoffset() != instant.astimezone(selected).utcoffset():
                    raise ValueError('Embedded timezone offsets disagree with installed IANA data; review this calendar manually.')
        events.append(event)
    if not events:
        raise ValueError('No supported events were found.')
    if len({event.uid for event in events}) != len(events):
        raise ValueError('Repeated UIDs/recurrence overrides are unsupported; import distinct events.')
    return events


def import_ics(text, expected_revision, apply=False, preview_token=''):
    current = get_state()
    if current['revision'] != expected_revision:
        raise Conflict(current['revision'])
    events = parse_ics(text)
    token = hashlib.sha256((str(expected_revision) + '\0' + text).encode('utf-8')).hexdigest()
    updated = copy.deepcopy(current)
    positions = {event['uid']: index for index, event in enumerate(updated['events'])}
    changes = []
    for event in events:
        item = event.model_dump(mode='json')
        if event.uid in positions:
            index = positions[event.uid]
            old = updated['events'][index]
            if event.sequence < old['sequence']:
                raise ValueError('An imported event has an older sequence than the local event; review it manually.')
            item['id'], item['private_notes'] = old['id'], old['private_notes']
            updated['events'][index] = item
            action = 'update'
        else:
            updated['events'].append(item)
            action = 'add'
        changes.append({'action': action, 'uid': item['uid'], 'title': item['title'], 'status': item['status']})
    if not apply:
        return {'revision': expected_revision, 'preview_token': token, 'changes': changes,
                'events': [event.model_dump(mode='json') for event in events], 'applied': False}
    if preview_token != token:
        raise ValueError('Preview this exact calendar at the current revision before applying it.')
    return {'state': save_state(updated, expected_revision), 'changes': changes, 'applied': True}
