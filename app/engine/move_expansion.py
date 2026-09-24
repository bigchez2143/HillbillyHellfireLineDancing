"""Validated, frozen manual move definitions; never a legacy generator pool.

This module has no compiler, settings, database, or network dependency. Review
status describes instructor review separately from mechanically complete data.
"""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

PACK_PATH = Path(__file__).resolve().parents[2] / 'data' / 'expanded-moves.json'
MAX_BYTES = 4 * 1024 * 1024
REVIEW_STATUS = 'mechanics_draft_instructor_review_pending'
_ID = re.compile(r'^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$')
_MOVE_KEYS = {'id', 'name', 'aliases', 'level', 'family', 'duration_counts',
              'start_free_foot', 'net_rotation_deg', 'travel', 'events',
              'explanation', 'source_ids', 'review_status', 'generator_eligible',
              'group', 'entry_facing_deg', 'review_note', 'provenance_note'}
_REQUIRED_MOVE_KEYS = _MOVE_KEYS - {'entry_facing_deg', 'review_note', 'provenance_note'}
_EVENT_KEYS = {'id', 'offset_counts', 'duration_counts', 'text', 'support_before',
               'support_after', 'rotation_deg', 'moving_foot', 'travel',
               'facing_before_deg', 'facing_after_deg', 'notes'}
_REQUIRED_EVENT_KEYS = {'offset_counts', 'duration_counts', 'text', 'support_before',
                        'support_after', 'rotation_deg'}


class ExpansionError(ValueError):
    """A packaged move is malformed; do not silently reinterpret its mechanics."""


def _fail(message):
    raise ExpansionError(message)


def _object(value, allowed, required, label):
    if not isinstance(value, dict) or set(value) - allowed or required - set(value):
        _fail(label + ' has missing or unsupported fields.')


def _text(value, label, maximum=1000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        _fail(label + ' must be nonempty text within the size limit.')
    return value


def _count(value, label, positive=False):
    if not isinstance(value, str) or len(value) > 40 or not re.fullmatch(r'-?\d+(?:/\d+|\.\d+)?', value):
        _fail(label + ' must be an exact integer, decimal, or fraction string.')
    try:
        result = Fraction(value)
    except (ValueError, ZeroDivisionError):
        _fail(label + ' contains an invalid fraction.')
    if result < 0 or (positive and result == 0) or result > 4096 or result.denominator > 1000000:
        _fail(label + ' is outside the supported count range.')
    return result


def _angle(value, label):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        _fail(label + ' must be a finite angle or null.')
    try:
        result = Fraction(str(value))
    except (ValueError, ZeroDivisionError):
        _fail(label + ' must be a finite angle or null.')
    if abs(result) > 36000 or result.denominator > 1000000:
        _fail(label + ' is outside the supported angle range.')
    return result


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def _hash(value):
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail('Duplicate JSON object key: ' + key)
        result[key] = value
    return result


def _invalid_constant(value):
    _fail('Non-finite JSON value: ' + value)


def validate_pack(raw):
    """Validate without inferring footwork, and return an independent copy."""
    _object(raw, {'schema_version', 'sources', 'moves'}, {'schema_version', 'sources', 'moves'}, 'Expansion pack')
    if type(raw['schema_version']) is not int or raw['schema_version'] != 1:
        _fail('Unsupported expansion schema version.')
    sources = raw['sources']
    if not isinstance(sources, dict) or not 1 <= len(sources) <= 100:
        _fail('Sources must be a nonempty bounded object.')
    for sid, source in sources.items():
        if not isinstance(sid, str) or not _ID.fullmatch(sid):
            _fail('Invalid source ID.')
        _object(source, {'title', 'url'}, {'title', 'url'}, 'Source ' + sid)
        _text(source['title'], 'Source title')
        url = urlsplit(_text(source['url'], 'Source URL', 2048))
        if url.scheme not in {'https', 'http'} or not url.hostname or url.username or url.password:
            _fail('Source URLs must be public HTTP(S) references without credentials.')
    moves = raw['moves']
    if not isinstance(moves, list) or not 1 <= len(moves) <= 512:
        _fail('Moves must be a nonempty bounded array.')
    used = set()
    for row in moves:
        _object(row, _MOVE_KEYS, _REQUIRED_MOVE_KEYS, 'Expanded move')
        mid = _text(row['id'], 'Move ID', 120)
        if not mid.startswith('expansion-') or not _ID.fullmatch(mid) or mid in used:
            _fail('Expanded move IDs must be unique expansion-prefixed identifiers.')
        used.add(mid)
        for field in ('name', 'family', 'group', 'explanation'):
            _text(row[field], mid + ' ' + field, 16000 if field == 'explanation' else 500)
        for field in ('review_note', 'provenance_note'):
            if field in row:
                _text(row[field], mid + ' ' + field, 16000)
        if row['level'] not in {'I', 'INT', 'A'}:
            _fail(mid + ': level must be I, INT, or A; it is a local label.')
        if row['review_status'] != REVIEW_STATUS or row['generator_eligible'] is not False:
            _fail(mid + ': this pack contains instructor-review-pending manual moves only.')
        if not isinstance(row['aliases'], list) or len(row['aliases']) > 50:
            _fail(mid + ': aliases must be a bounded array.')
        for alias in row['aliases']:
            _text(alias, mid + ' alias', 500)
        refs = row['source_ids']
        if not isinstance(refs, list) or not refs or any(not isinstance(sid, str) or sid not in sources for sid in refs):
            _fail(mid + ': every source reference must resolve in the pack.')
        if row['start_free_foot'] not in {'R', 'L', None, 'unknown'}:
            _fail(mid + ': unsupported entry free foot.')
        if row['travel'] not in {'N', 'S', 'E', 'W', '', None}:
            _fail(mid + ': unsupported travel direction.')
        duration = _count(row['duration_counts'], mid + ' duration', positive=True)
        total_rotation = _angle(row['net_rotation_deg'], mid + ' net rotation')
        entry_angle = _angle(row.get('entry_facing_deg'), mid + ' entry facing')
        events = row['events']
        if not isinstance(events, list) or not 1 <= len(events) <= 256:
            _fail(mid + ': events must be a nonempty bounded array.')
        cursor, rotation, rotation_known = Fraction(0), Fraction(0), True
        support = {'R': 'L', 'L': 'R'}.get(row['start_free_foot'], 'unknown')
        event_ids = set()
        for index, event in enumerate(events):
            _object(event, _EVENT_KEYS, _REQUIRED_EVENT_KEYS, mid + ' event')
            if 'id' in event:
                eid = _text(event['id'], mid + ' event ID', 120)
                if eid in event_ids:
                    _fail(mid + ': event IDs must be unique.')
                event_ids.add(eid)
            _text(event['text'], mid + ' event text', 4000)
            offset = _count(event['offset_counts'], mid + ' event offset')
            span = _count(event['duration_counts'], mid + ' event duration')
            if offset != cursor:
                _fail(mid + ': event times must be contiguous and ordered without gaps or overlaps.')
            cursor = offset + span
            before, after = event['support_before'], event['support_after']
            if before not in {'L', 'R', 'both', 'neither', 'unknown', 'any'} or after not in {'L', 'R', 'both', 'neither', 'unknown', 'same'}:
                _fail(mid + ': unsupported event support.')
            if support != 'unknown' and before not in {'unknown', 'any', support}:
                _fail(mid + ': contradictory known support transition.')
            if after != 'same':
                support = after
            angle = _angle(event['rotation_deg'], mid + ' event rotation')
            rotation_known = rotation_known and angle is not None
            if angle is not None:
                rotation += angle
            for key in ('facing_before_deg', 'facing_after_deg'):
                if key in event:
                    _angle(event[key], mid + ' ' + key)
            if index == 0 and entry_angle is not None and event.get('facing_before_deg') is not None:
                if _angle(event['facing_before_deg'], mid + ' event facing') % 360 != entry_angle % 360:
                    _fail(mid + ': entry facing contradicts the first event.')
            if 'moving_foot' in event and event['moving_foot'] not in {'L', 'R', 'both', 'neither', 'unknown'}:
                _fail(mid + ': unsupported moving foot.')
            if 'travel' in event and event['travel'] not in {'N', 'S', 'E', 'W', '', None}:
                _fail(mid + ': unsupported event travel.')
            if 'notes' in event:
                _text(event['notes'], mid + ' event notes', 4000)
        if cursor != duration:
            _fail(mid + ': event duration does not match the declared move duration.')
        if rotation_known and total_rotation is not None and rotation != total_rotation:
            _fail(mid + ': event rotations do not match the declared net rotation.')
    return deepcopy(raw)


def load_pack(path=None):
    """Read each requested pack afresh: updated content cannot reuse stale cache."""
    path = Path(path) if path is not None else PACK_PATH
    with path.open('rb') as handle:
        payload = handle.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        _fail('The expansion pack exceeds its size limit.')
    try:
        raw = json.loads(payload.decode('utf-8-sig'), object_pairs_hook=_unique_object,
                         parse_constant=_invalid_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ExpansionError('The expansion pack is not valid UTF-8 JSON.') from exc
    return validate_pack(raw)


_MIRROR_WORDS = {'R': 'L', 'L': 'R', 'right': 'left', 'left': 'right',
                 'rightward': 'leftward', 'leftward': 'rightward',
                 'rightwards': 'leftwards', 'leftwards': 'rightwards',
                 'clockwise': 'counterclockwise', 'counterclockwise': 'clockwise',
                 'anticlockwise': 'clockwise', 'RF': 'LF', 'LF': 'RF',
                 'CW': 'CCW', 'CCW': 'CW'}


def _mirror_text(value, entry_facing=None):
    def replace(match):
        word = match.group()
        if re.fullmatch(r'[RL]{2,}', word):
            return word.translate(str.maketrans('RL', 'LR'))
        normalized = re.sub(r'[- ]', '', word.lower())
        swapped = _MIRROR_WORDS.get(word, _MIRROR_WORDS.get(normalized, word))
        if len(word) > 1 and word.isupper():
            return swapped.upper()
        if word.istitle():
            return swapped.capitalize()
        return swapped
    value = re.sub(r'\b(?:(?-i:[RL]{2,})|counter[- ]?clockwise|anti[- ]?clockwise|clockwise|rightwards?|leftwards?|right|left|CCW|CW|RF|LF|R|L)\b', replace, value, flags=re.IGNORECASE)
    if entry_facing is not None:
        declared = _angle(entry_facing, 'entry facing') % 360
        def facing(match):
            number = _angle(match.group(), 'entry facing text')
            return str((-declared) % 360) if number % 360 == declared else match.group()
        # Only degree-labeled references to the declared entry angle change.
        # Counts, years, distances and unrelated angle values remain untouched.
        value = re.sub(r'(?<![\w./])\d+(?:/\d+|\.\d+)?(?=\s*(?:-\s*)?(?:degrees?\b|°))',
                       facing, value, flags=re.IGNORECASE)
    return value


def _flip(value):
    return {'L': 'R', 'R': 'L', 'E': 'W', 'W': 'E'}.get(value, value)


def _make_variant(pack, row, lead, source_hash):
    if lead not in {'R', 'L'}:
        _fail('Lead must be R or L.')
    # A pack row's orientation is its declared free foot, normally R. Unknown
    # support uses the canonical R-oriented prose, without assuming a free foot.
    canonical_lead = row['start_free_foot'] if row['start_free_foot'] in {'R', 'L'} else 'R'
    mirror = lead != canonical_lead
    mirrored_text = lambda value: _mirror_text(value, row.get('entry_facing_deg')) if mirror else value
    events = deepcopy(row['events'])
    for index, event in enumerate(events):
        event.setdefault('id', 'event-' + str(index + 1))
        event['offset_counts'] = str(Fraction(event['offset_counts']))
        event['duration_counts'] = str(Fraction(event['duration_counts']))
        if index == 0 and row.get('entry_facing_deg') is not None:
            event['facing_before_deg'] = row['entry_facing_deg']
        for key in ('rotation_deg', 'facing_before_deg', 'facing_after_deg'):
            if key in event and event[key] is not None:
                value = _angle(event[key], key) * (-1 if mirror else 1)
                event[key] = str(value % 360 if key != 'rotation_deg' else value)
        if mirror:
            for key in ('support_before', 'support_after', 'moving_foot', 'travel'):
                if key in event:
                    event[key] = _flip(event[key])
            for key in ('text', 'notes'):
                if key in event:
                    event[key] = mirrored_text(event[key])
    duration = Fraction(row['duration_counts'])
    source_rows = [{**deepcopy(pack['sources'][sid]), 'id': sid} for sid in row['source_ids']]
    display = {'name': mirrored_text(row['name']), 'explanation': mirrored_text(row['explanation']),
               'aliases': [mirrored_text(alias) for alias in row['aliases']]}
    if 'review_note' in row:
        display['review_note'] = mirrored_text(row['review_note'])
    definition_hash = _hash({'move': row, 'sources': source_rows, 'lead': lead,
                             'events': events, 'display': display})
    complete = (row['start_free_foot'] in {'R', 'L'} and row['net_rotation_deg'] is not None
                and all(event['support_before'] != 'unknown' and event['support_after'] != 'unknown'
                        and event['rotation_deg'] is not None for event in events))
    required = row.get('entry_facing_deg')
    required = None if required is None else str((_angle(required, 'entry facing') * (-1 if mirror else 1)) % 360)
    value = {'id': row['id'] + '-' + lead.lower(), 'move_id': row['id'],
             'definition_id': row['id'], 'snapshot_id': row['id'] + '@' + definition_hash[:20],
             'definition_hash': definition_hash, 'source_hash': source_hash,
             'lead': lead, 'name': display['name'],
             'aliases': display['aliases'], 'level': row['level'], 'family': row['family'],
             'group': row['group'], 'duration_counts': str(duration),
             'counts': int(duration) if duration.denominator == 1 else str(duration),
             'events': events, 'explanation': display['explanation'],
             'source_ids': list(row['source_ids']), 'sources': source_rows,
             'links': [{'label': source['title'], 'url': source['url']} for source in source_rows],
             'review_status': row['review_status'], 'review': {'status': 'INSTRUCTOR_REVIEW_PENDING'},
             'mechanically_complete': complete, 'required_start_facing': required,
             'start_free_foot': _flip(row['start_free_foot']) if mirror else row['start_free_foot'],
             'net_rotation_deg': None if row['net_rotation_deg'] is None else str(_angle(row['net_rotation_deg'], 'rotation') * (-1 if mirror else 1)),
             'travel': _flip(row['travel']) if mirror else row['travel'],
             'ab_safe': False, 'in_generator': False, 'generator_eligible': False,
             'source_pack': 'expanded-moves', 'manual_only': True}
    for key in ('review_note', 'provenance_note'):
        if key in row:
            value[key] = display[key] if key == 'review_note' else row[key]
    return value


def variants(path=None):
    pack = load_pack(path)
    source_hash = _hash(pack)
    return [_make_variant(pack, row, lead, source_hash) for row in pack['moves'] for lead in ('R', 'L')]


def variant(move_id, lead='R', path=None):
    pack = load_pack(path)
    row = next((row for row in pack['moves'] if row['id'] == move_id), None)
    if row is None:
        raise KeyError('Unknown expanded move: ' + str(move_id))
    return _make_variant(pack, row, lead, _hash(pack))


def coverage(path=None):
    pack = load_pack(path)
    rows = [_make_variant(pack, row, 'R', _hash(pack)) for row in pack['moves']]
    return {'count_new': len(rows), 'count_variants': len(rows) * 2,
            'groups': sorted({row['group'] for row in rows}),
            'count_groups': len({row['group'] for row in rows}),
            'mechanically_complete': sum(row['mechanically_complete'] for row in rows),
            'instructor_review_pending': len(rows), 'generator_eligible': 0,
            'status': REVIEW_STATUS, 'source_hash': _hash(pack)}
