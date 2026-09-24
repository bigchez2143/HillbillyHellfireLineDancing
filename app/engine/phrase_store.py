"""Private, versioned eight-count phrases containing complete frozen moves.

No catalog lookup, external access or review certification occurs here. Versions
are immutable, edits use compare-and-swap, and deletion is reversible archiving.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid

from .choreography import exact_count

PHRASE_DIR = None
MAX_BYTES = 2 * 1024 * 1024
SCHEMA_VERSION = 1


class Conflict(ValueError):
    pass


def directory():
    if PHRASE_DIR is not None:
        return Path(PHRASE_DIR)
    if os.environ.get('LINE_DANCE_PHRASE_DIR'):
        return Path(os.environ['LINE_DANCE_PHRASE_DIR']).expanduser()
    if os.environ.get('LINE_DANCE_DATA_DIR'):
        return Path(os.environ['LINE_DANCE_DATA_DIR']).expanduser() / 'phrases'
    base = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local' / 'share')))
    return base / 'LineDanceCreator' / 'phrases'


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _id():
    return 'phrase-' + uuid.uuid4().hex


def _check_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'phrase-[0-9a-f]{32}', value):
        raise ValueError('Invalid phrase identifier.')


@contextmanager
def _db(write=False):
    root = directory()
    root.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(root / 'phrases.sqlite3', timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript('''
          CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY,version INTEGER NOT NULL,payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS versions(record_id TEXT,version INTEGER,payload TEXT NOT NULL,PRIMARY KEY(record_id,version));
        ''')
        if write:
            conn.execute('BEGIN IMMEDIATE')
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _text(value, label, limit=200):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or '\0' in value:
        raise ValueError(label + ' must be nonempty text within ' + str(limit) + ' characters.')
    return value.strip()


def _safe(value, depth=0):
    if depth > 30:
        raise ValueError('Phrase data is nested too deeply.')
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError('Phrase field names must be text.')
            if key.casefold().replace('-', '_') in {'api_key', 'apikey', 'api_key_protected', 'access_token', 'refresh_token', 'password', 'authorization', 'client_secret', 'secret', 'credentials'}:
                raise ValueError('Remove credentials before saving a phrase.')
            _safe(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _safe(child, depth + 1)


def _number(value, label, minimum=None):
    try:
        number = exact_count(value)
    except (TypeError, ValueError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError(label + ' must be a finite number or fraction.') from exc
    if abs(number) > 100000 or number.denominator > 1000000 or (minimum is not None and number < minimum):
        raise ValueError(label + ' is outside the supported range.')
    return number


def _definition(move):
    if isinstance(move.get('definition'), dict) and not move.get('snapshot_id'):
        return {**move['definition'], **{k: v for k, v in move.items() if k != 'definition'}}
    return move


def _duration(move):
    definition = _definition(move)
    value = definition.get('duration_counts', definition.get('counts'))
    events = definition.get('events')
    cursor = _number(0, 'Start')
    if events is not None:
        if not isinstance(events, list) or not events or len(events) > 512:
            raise ValueError('Each timed move needs 1 to 512 event rows.')
        ids = set()
        for event in events:
            if not isinstance(event, dict):
                raise ValueError('Move event rows must be objects.')
            if 'id' in event:
                eid = _text(event['id'], 'Event ID')
                if eid in ids:
                    raise ValueError('Event IDs must be distinct within each move.')
                ids.add(eid)
            offset = _number(event.get('offset_counts', str(cursor)), 'Event start', 0)
            duration = _number(event.get('duration_counts', 0 if event.get('instant') is True else None), 'Event duration', 0)
            if offset != cursor:
                raise ValueError('Fix gaps or overlapping event timing before saving this phrase.')
            cursor = offset + duration
        if value is None:
            value = str(cursor)
    elif move.get('snapshot_id'):
        raise ValueError('This move is missing its frozen events. Restore its definition before saving a phrase.')
    elif not any(key in definition for key in ('lines', 'text', 'start', 'support_before', 'support_after')):
        raise ValueError('Save full move definitions, rather than move IDs alone.')
    duration = _number(value, 'Move duration', 0)
    if events is not None and cursor != duration:
        raise ValueError('Move duration does not match its event timing.')
    return duration


def validate_moves(moves):
    """Return an independent eight-count copy, preserving exact input payloads."""
    if not isinstance(moves, list) or not 1 <= len(moves) <= 256:
        raise ValueError('Choose 1 to 256 consecutive whole moves.')
    _safe(moves)
    try:
        if len(_json(moves).encode('utf-8')) > MAX_BYTES:
            raise ValueError('This phrase is too large; use fewer attached notes.')
    except (TypeError, OverflowError, RecursionError) as exc:
        raise ValueError('Phrase data must be valid JSON.') from exc
    total = _number(0, 'Start')
    ids = set()
    for move in moves:
        if not isinstance(move, dict):
            raise ValueError('Each move must be an object.')
        if 'id' in move:
            mid = _text(move['id'], 'Move occurrence ID')
            if mid in ids:
                raise ValueError('Move occurrence IDs must be distinct.')
            ids.add(mid)
        total += _duration(move)
    if total != 8:
        raise ValueError(f'This selection is {total} counts. Choose consecutive whole moves totaling exactly 8 counts; a move cannot be cut in half here.')
    return deepcopy(moves)


def _get(conn, phrase_id, version=None):
    _check_id(phrase_id)
    if version is None:
        row = conn.execute('SELECT payload FROM records WHERE id=?', (phrase_id,)).fetchone()
    else:
        if type(version) is not int or version < 1:
            raise ValueError('Version must be a positive integer.')
        row = conn.execute('SELECT payload FROM versions WHERE record_id=? AND version=?', (phrase_id, version)).fetchone()
    if row is None:
        raise FileNotFoundError('Phrase not found.')
    return json.loads(row['payload'])


def _put(conn, record):
    payload = _json(record)
    conn.execute('INSERT INTO versions VALUES(?,?,?)', (record['id'], record['version'], payload))
    conn.execute('INSERT INTO records VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,payload=excluded.payload', (record['id'], record['version'], payload))
    return deepcopy(record)


def create(name, moves, notes=''):
    if not isinstance(notes, str) or len(notes) > 3000:
        raise ValueError('Phrase notes must be at most 3000 characters.')
    record = {'schema_version': SCHEMA_VERSION, 'id': _id(), 'version': 1,
              'name': _text(name, 'Phrase name'), 'notes': notes,
              'duration_counts': '8', 'moves': validate_moves(moves),
              'favorite': False, 'archived': False, 'created_at': _now(), 'updated_at': _now()}
    with _db(True) as conn:
        return _put(conn, record)


def get(phrase_id, version=None):
    with _db() as conn:
        return _get(conn, phrase_id, version)


def list_phrases(include_archived=False):
    with _db() as conn:
        records = [json.loads(row['payload']) for row in conn.execute('SELECT payload FROM records')]
    return {'schema_version': SCHEMA_VERSION, 'phrases': sorted(
        (row for row in records if include_archived or not row['archived']),
        key=lambda row: (not row['favorite'], row['name'].casefold(), row['id']))}


def update(phrase_id, expected_version, fields):
    if not isinstance(fields, dict) or not fields or set(fields) - {'name', 'notes', 'favorite', 'archived'}:
        raise ValueError('Edit a phrase name, notes, favorite or archived status.')
    fields = deepcopy(fields)
    if 'name' in fields:
        fields['name'] = _text(fields['name'], 'Phrase name')
    if 'notes' in fields and (not isinstance(fields['notes'], str) or len(fields['notes']) > 3000):
        raise ValueError('Phrase notes must be at most 3000 characters.')
    for key in ('favorite', 'archived'):
        if key in fields and type(fields[key]) is not bool:
            raise ValueError(key + ' must be true or false.')
    with _db(True) as conn:
        record = _get(conn, phrase_id)
        if type(expected_version) is not int or record['version'] != expected_version:
            raise Conflict('This phrase changed. Reload the phrase list before saving.')
        record.update(fields)
        record['version'] += 1
        record['updated_at'] = _now()
        return _put(conn, record)


_FEET = {'R': 'L', 'L': 'R', 'r': 'l', 'l': 'r', 'right': 'left', 'left': 'right'}
_DIRECTIONS = {'E': 'W', 'W': 'E', 'NE': 'NW', 'NW': 'NE', 'SE': 'SW', 'SW': 'SE'}
_WORDS = {'right': 'left', 'left': 'right', 'rightward': 'leftward', 'leftward': 'rightward',
          'rightwards': 'leftwards', 'leftwards': 'rightwards', 'clockwise': 'counterclockwise',
          'counterclockwise': 'clockwise', 'anticlockwise': 'clockwise', 'rf': 'lf', 'lf': 'rf',
          'r': 'l', 'l': 'r', 'cw': 'ccw', 'ccw': 'cw', 'east': 'west', 'west': 'east'}
_FOOT_FIELDS = {'start', 'end', 'lead', 'start_free_foot', 'free_foot', 'support_before', 'support_after', 'moving_foot'}
_ANGLE_FIELDS = {'rot', 'rotation_deg', 'net_rotation_deg'}
_FACING_FIELDS = {'facing_before_deg', 'facing_after_deg', 'required_start_facing', 'entry_facing_deg'}
_TEXT_FIELDS = {'name', 'header', 'text', 'action_text', 'explanation', 'notes', 'callout', 'review_note'}
_TIMING_FIELDS = {'counts', 'duration_counts', 'offset_counts', 'beats', 'instant'}
_META_FIELDS = {'id', 'move_id', 'definition_id', 'snapshot_id', 'definition_hash', 'source_hash', 'reference_fingerprint',
                'source_ids', 'sources', 'links', 'origins', 'attachments', 'review', 'review_status', 'provenance_note',
                'source_pack', 'library_version', 'reference_record', 'reported_mechanics', 'count_origin', 'requires_counts',
                'usage_note', 'level', 'difficulty', 'family', 'group', 'sync', 'turning', 'ab_safe', 'in_generator',
                'generator_eligible', 'manual_only', 'mechanically_complete', 'locked', 'minimum_bpm', 'preferred_bpm_min',
                'preferred_bpm_max', 'maximum_bpm', 'high_tempo_penalty', 'phrase_origin'}


def _mirror_text(value):
    if not isinstance(value, str):
        raise ValueError('Instruction fields must be text before mirroring.')
    def replace(match):
        word = match.group()
        if re.fullmatch(r'[RL]{2,}', word):
            return word.translate(str.maketrans('RL', 'LR'))
        swapped = _WORDS[re.sub(r'[- ]', '', word.lower())]
        return swapped.upper() if word.isupper() else swapped.capitalize() if word.istitle() else swapped
    value = re.sub(r'\b(?:(?-i:[RL]{2,})|counter[- ]?clockwise|anti[- ]?clockwise|clockwise|rightwards?|leftwards?|right|left|CCW|CW|RF|LF|R|L|east|west)\b', replace, value, flags=re.IGNORECASE)
    # Clock-face bearings are absolute direction labels, unlike ordinary counts.
    value = re.sub(r'\b(1[0-2]|[1-9]):(00|30)\b', lambda m: _clock_reflect(int(m[1]) * 60 + int(m[2])), value)
    return value


def _clock_reflect(minutes):
    reflected = (-minutes) % 720
    return f'{reflected // 60 or 12}:{reflected % 60:02}'


def _reflect_angle(value, absolute=False):
    if value is None or value == 'unknown':
        return value
    result = -_number(value, 'Turn or facing')
    if absolute:
        result %= 360
    return int(result) if isinstance(value, int) else float(result) if isinstance(value, float) else str(result)


def mirror_move(move):
    """Reflect known mechanics; unfamiliar fields are never silently ignored."""
    result = deepcopy(move)
    allowed = _FOOT_FIELDS | _ANGLE_FIELDS | _FACING_FIELDS | _TEXT_FIELDS | _TIMING_FIELDS | _META_FIELDS | {'events', 'lines', 'definition', 'travel', 'aliases'}
    unsupported = set(result) - allowed
    if unsupported:
        raise ValueError('Cannot safely mirror unsupported move fields: ' + ', '.join(sorted(unsupported)) + '. Insert the original phrase and edit those moves manually.')
    for key, value in list(result.items()):
        if key in _FOOT_FIELDS:
            if isinstance(value, (dict, list)):
                raise ValueError('Cannot mirror a structured foot state. Insert the original phrase.')
            if value not in {'L', 'R', 'l', 'r', 'left', 'right', 'F', 'SAME', 'same', 'any', 'both', 'neither', 'unknown', None}:
                raise ValueError('Cannot safely mirror foot state ' + str(value) + '.')
            result[key] = _FEET.get(value, value)
        elif key in _ANGLE_FIELDS | _FACING_FIELDS:
            result[key] = _reflect_angle(value, key in _FACING_FIELDS)
        elif key in _TEXT_FIELDS:
            result[key] = _mirror_text(value)
        elif key == 'aliases':
            if not isinstance(value, list):
                raise ValueError('Aliases must be a list before mirroring.')
            result[key] = [_mirror_text(alias) for alias in value]
        elif key == 'travel':
            if value not in {'', 'N', 'S', 'E', 'W', 'NE', 'NW', 'SE', 'SW', None, 'unknown'}:
                raise ValueError('Cannot safely mirror this travel direction. Insert the original phrase.')
            result[key] = _DIRECTIONS.get(value, value)
        elif key in {'events', 'lines'}:
            if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
                raise ValueError('Timed rows must be objects before mirroring.')
            result[key] = [mirror_move(row) for row in value]
        elif key == 'definition':
            if not isinstance(value, dict):
                raise ValueError('Frozen definition must be an object.')
            result[key] = mirror_move(value)
    # Absolute degree directions in prose can be ambiguous with turn amounts.
    # Refuse these instead of leaving a mirrored instruction with a stale bearing.
    for key in _TEXT_FIELDS:
        text = result.get(key, '')
        if isinstance(text, str) and re.search(r'\b(?:facing|face|bearing|heading)\b[^.;\n]{0,50}?\d\s*(?:°|degrees?\b)', text, re.I):
            raise ValueError('This move describes an absolute facing in degrees. Use a clock-face label (for example 3:00) before mirroring, or insert the original phrase.')
    return result


def insertion(phrase_id, expected_version, mirrored=False):
    if type(mirrored) is not bool:
        raise ValueError('Mirrored must be true or false.')
    with _db() as conn:
        record = _get(conn, phrase_id)
    if type(expected_version) is not int or record['version'] != expected_version:
        raise Conflict('This phrase changed. Reload and preview the current version before inserting.')
    if record['archived']:
        raise Conflict('Restore this archived phrase before inserting it.')
    rows = validate_moves(record['moves'])
    if mirrored:
        rows = [mirror_move(move) for move in rows]
    result = []
    for index, move in enumerate(rows):
        original = record['moves'][index]
        origin = {'phrase_id': record['id'], 'version': record['version'], 'name': record['name'],
                  'source_occurrence_id': original.get('id'), 'mirrored': mirrored,
                  'source_definition_hash': original.get('definition_hash'), 'source_snapshot_id': original.get('snapshot_id'),
                  'prior_phrase_origin': deepcopy(original.get('phrase_origin'))}
        if mirrored:
            origin.update({'status': 'MIRRORED_REVIEW_PENDING', 'original_review_status': original.get('review_status'),
                           'transform': 'left-right-reflection-v1', 'transformed_hash': hashlib.sha256(_json(move).encode()).hexdigest()})
            move['review_status'] = 'MIRRORED_REVIEW_PENDING'
            move['generator_eligible'] = False
            move['in_generator'] = False
            move['manual_only'] = True
        move['id'] = 'phrase-move-' + uuid.uuid4().hex
        move['phrase_origin'] = origin
        result.append(move)
    return {'phrase_id': phrase_id, 'version': record['version'], 'name': record['name'], 'duration_counts': '8',
            'mirrored': mirrored, 'moves': result,
            'notice': 'Review mirrored footwork and the transition into this phrase. Linked pictures and videos still show their original orientation.' if mirrored else 'Phrase inserted as an independent copy. Check its entry foot and facing in this dance.'}


def validate_record(record):
    """Read-only validation hook for private backup preview and restore."""
    if not isinstance(record, dict) or record.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('Unsupported phrase record.')
    _safe(record)
    if set(record) - {'schema_version', 'id', 'version', 'name', 'notes', 'duration_counts', 'moves', 'favorite', 'archived', 'created_at', 'updated_at'}:
        raise ValueError('Unsupported phrase record fields.')
    _check_id(record.get('id'))
    _text(record.get('name'), 'Phrase name')
    if type(record.get('version')) is not int or record['version'] < 1:
        raise ValueError('Invalid phrase version.')
    if record.get('duration_counts') != '8' or any(type(record.get(k)) is not bool for k in ('favorite', 'archived')):
        raise ValueError('Invalid phrase status or duration.')
    if not isinstance(record.get('notes'), str) or len(record['notes']) > 3000:
        raise ValueError('Invalid phrase notes.')
    for key in ('created_at', 'updated_at'):
        _text(record.get(key), 'Phrase timestamp', 100)
    validate_moves(record.get('moves'))
    return deepcopy(record)
