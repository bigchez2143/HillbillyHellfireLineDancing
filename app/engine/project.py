"""Versioned, atomic project saves with independent working drafts and history."""
import copy
import hashlib
import json
import os
import re
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from .paths import runtime_path
PROJECTS_DIR = os.environ.get('LINE_DANCE_PROJECTS_DIR') or runtime_path('projects', os.path.join(APP_DIR, 'projects'))
PROJECT_ID_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
VERSION_ID_RE = re.compile(r'^v-[a-f0-9]{32}$')
SCHEMA_VERSION = 1
AUTHOR_FIELDS = ('song', 'sections', 'lyrics_raw', 'lyric_sections', 'sheet_meta',
                 'tutorial', 'attachments', 'music_map')
_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


class RevisionConflict(ValueError):
    def __init__(self, expected_revision, current_revision):
        self.expected_revision = expected_revision
        self.current_revision = current_revision
        super().__init__('The project changed since it was loaded. Reload before saving; your edits have not overwritten the newer document.')


class UnsupportedSchema(ValueError):
    pass


class ProjectCorrupt(ValueError):
    pass


class MissingMoveDefinition(ValueError):
    pass


class ProjectDocument(dict):
    """A legacy-compatible dict; runtime bookkeeping is not serialized."""
    def __init__(self, value, recovery=None, source_hash=None):
        super().__init__(value)
        self.recovery = recovery
        self.source_hash = source_hash


def _slug(name):
    return re.sub(r'[^a-zA-Z0-9]+', '-', (name or 'untitled').strip()).strip('-').lower() or 'untitled'


def ensure_dirs():
    os.makedirs(PROJECTS_DIR, exist_ok=True)


def project_dir(pid):
    if not isinstance(pid, str) or not PROJECT_ID_RE.fullmatch(pid):
        raise ValueError('Invalid project id')
    root = os.path.realpath(PROJECTS_DIR)
    target = os.path.realpath(os.path.join(root, pid))
    if os.path.commonpath((root, target)) != root or target == root:
        raise ValueError('Project path leaves the project directory')
    return target


def _path(pid):
    return os.path.join(project_dir(pid), 'project.json')


def _backup_path(pid):
    return os.path.join(project_dir(pid), 'project.last-good.json')


@contextmanager
def _project_lock(pid):
    """Serialize writers across threads and local server processes."""
    directory = project_dir(pid)
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(directory, threading.RLock())
    with lock:
        lock_dir = os.path.join(os.path.realpath(PROJECTS_DIR), '.locks')
        os.makedirs(lock_dir, exist_ok=True)
        with open(os.path.join(lock_dir, pid + '.lock'), 'a+b') as handle:
            if os.name == 'nt':
                import msvcrt
                handle.seek(0, os.SEEK_END)
                if not handle.tell():
                    handle.write(b'0')
                    handle.flush()
                deadline = time.monotonic() + 15
                while True:
                    handle.seek(0)
                    try:
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise OSError('Project is busy; try saving again shortly.')
                        time.sleep(0.02)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == 'nt':
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)


def _encoded(value):
    return (json.dumps(value, indent=1, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False, separators=(',', ':')).encode('utf-8')).hexdigest()


def _atomic_write(path, payload):
    """Replace only after a complete flushed temporary file exists."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.saving-', suffix='.tmp', dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _decode_project(raw, pid):
    def invalid_constant(value):
        raise ValueError('Invalid JSON numeric value: ' + value)
    data = json.loads(raw.decode('utf-8'), parse_constant=invalid_constant)
    if not isinstance(data, dict):
        raise ValueError('Project document must be an object')
    schema = data.get('schema_version', 0)
    if type(schema) is not int or schema < 0 or schema > SCHEMA_VERSION:
        raise UnsupportedSchema(f'Project schema {schema!r} is unsupported. Use a compatible application version.')
    revision = data.get('document_revision', 0)
    if type(revision) is not int or revision < 0:
        raise ValueError('Invalid document revision')
    if data.get('id', pid) != pid:
        raise ValueError('Project identity does not match its folder')
    if 'draft' in data and not isinstance(data['draft'], dict):
        raise ValueError('Project draft must be an object')
    return data


def _editor_from_dance(dance):
    dance = dance if isinstance(dance, dict) else {}
    moves = dance.get('custom') if dance.get('source') == 'custom' else None
    if moves is None and dance.get('candidates'):
        index = max(0, min(int(dance.get('chosen') or 0), len(dance['candidates']) - 1))
        moves = [({'move_id': m['move_id'], 'lead': m.get('lead', 'R')}
                  if isinstance(m, dict) and 'move_id' in m else copy.deepcopy(m))
                 for m in dance['candidates'][index].get('moves', [])]
    return {'moves': copy.deepcopy(moves or []), 'counts': dance.get('counts', 32),
            'wall': dance.get('wall', '2'), 'turn_dir': dance.get('turn_dir', 'L')}


def _initial_draft(data):
    draft = {field: copy.deepcopy(data[field]) for field in AUTHOR_FIELDS if field in data}
    draft['editor'] = _editor_from_dance(data.get('dance'))
    return draft


def _migrate(data, pid):
    """Additive in-memory migration; original bytes are retained on first save."""
    result = copy.deepcopy(dict(data))
    result.setdefault('id', pid)
    result['schema_version'] = SCHEMA_VERSION
    result.setdefault('document_revision', 0)
    if 'draft' not in result:
        result['draft'] = _initial_draft(result)
    result.setdefault('draft_saved_at', None)
    result.setdefault('movement_snapshots', {})
    result.setdefault('draft_move_snapshots', {})
    result.setdefault('workspace_versions', [])
    return result


def _read_unlocked(pid):
    primary_error = None
    for path in (_path(pid), _backup_path(pid)):
        try:
            with open(path, 'rb') as handle:
                raw = handle.read()
            value = _decode_project(raw, pid)
        except UnsupportedSchema:
            # A newer document must not be silently downgraded from a backup.
            raise
        except (FileNotFoundError, UnicodeError, ValueError) as exc:
            if primary_error is None:
                primary_error = exc
            continue
        recovery = None if path == _path(pid) else {
            'used_last_good': True, 'recovered_revision': value.get('document_revision', 0),
            'message': 'The main project could not be read. The previous successful save was recovered; review it and save again.'}
        return ProjectDocument(_migrate(value, pid), recovery, hashlib.sha256(raw).hexdigest()), raw
    if isinstance(primary_error, FileNotFoundError) and not os.path.exists(_backup_path(pid)):
        raise FileNotFoundError(_path(pid))
    raise ProjectCorrupt('The project and its recovery copy cannot be read. Keep the files and restore a backup.') from primary_error


def load_project(pid):
    with _project_lock(pid):
        document, _ = _read_unlocked(pid)
        return document


def _move_definition(move_id):
    from .steps import get_move
    return get_move(move_id)


def _references(value):
    if isinstance(value, dict):
        if isinstance(value.get('move_id'), str):
            yield value
        for child in value.values():
            yield from _references(child)
    elif isinstance(value, list):
        for child in value:
            yield from _references(child)


def _capture_group(existing, content):
    snapshots = copy.deepcopy(existing if isinstance(existing, dict) else {})
    issues = []
    for item in _references(content):
        move_id = item['move_id']
        if isinstance(item.get('events'), list) and item['events']:
            # Exact-event definitions already travel inside the saved document,
            # including their source/review metadata and content hashes. Do not
            # replace them with a live legacy summary or report a missing legacy
            # lookup. The compiler still checks unknown/invalid event mechanics;
            # having an embedded definition is not a verification claim.
            continue
        if move_id in snapshots:
            continue
        definition = _move_definition(move_id)
        variants = {lead: definition.variant(lead) for lead in ('R', 'L')} if definition else {}
        if all(field in item for field in ('lines', 'counts', 'start', 'end', 'rot')):
            variants[item.get('lead', 'R')] = copy.deepcopy(item)
        if variants:
            snapshots[move_id] = {'variants': variants, 'captured_at': time.time(),
                                  'review_status': 'stored_model_not_instructor_certified'}
        else:
            issues.append({'move_id': move_id, 'code': 'MISSING_MOVE_DEFINITION',
                           'message': 'Move definition unavailable. The ID is retained; supply the original definition before mechanical checks or export.'})
    return snapshots, issues


def _capture_snapshots(data):
    # A newly applied ID may already have a frozen definition in the draft.
    # Existing accepted definitions take precedence so draft restoration cannot
    # change the meaning of an accepted dance that happens to use the same ID.
    accepted_existing = copy.deepcopy(data.get('draft_move_snapshots') or {})
    accepted_existing.update(data.get('movement_snapshots') or {})
    data['movement_snapshots'], accepted_issues = _capture_group(accepted_existing, data.get('dance', {}))
    draft_existing = copy.deepcopy(data.get('movement_snapshots') or {})
    draft_existing.update(data.get('draft_move_snapshots') or {})
    data['draft_move_snapshots'], draft_issues = _capture_group(draft_existing, data.get('draft', {}))
    data['snapshot_issues'] = {'accepted': accepted_issues, 'draft': draft_issues}


def resolve_move_variants(project, items, start_foot='R', draft=False):
    """Use frozen definitions; a missing saved variant is never substituted."""
    snapshots = project.get('draft_move_snapshots' if draft else 'movement_snapshots') or {}
    out, foot = [], start_foot
    for item in items:
        move_id, lead = item.get('move_id'), item.get('lead', 'R')
        if lead not in ('R', 'L'):
            raise ValueError('Bad lead: ' + str(lead))
        record = snapshots.get(move_id)
        if all(field in item for field in ('lines', 'counts', 'start', 'end', 'rot')):
            value = copy.deepcopy(item)
        elif record is not None:
            variants = record.get('variants') or {}
            selected = variants.get(lead)
            if selected and selected.get('start') == 'F':
                selected = variants.get(foot)
            if not selected:
                raise MissingMoveDefinition(f'The saved {move_id} definition has no {lead} variant.')
            value = copy.deepcopy(selected)
        else:
            definition = _move_definition(move_id)
            if not definition:
                raise MissingMoveDefinition(f'Unknown move id: {move_id}. Restore its original definition.')
            value = definition.variant(foot if definition.start == 'F' else lead)
        out.append(value)
        if value['end'] != 'SAME':
            foot = value['end']
    return out


def _check_revision(expected, current):
    revision = current.get('document_revision', 0) if current is not None else 0
    if type(expected) is not int or expected != revision:
        raise RevisionConflict(expected, revision)


def _save_unlocked(pid, data, current, raw, expected_revision):
    _check_revision(expected_revision, current)
    # Check incoming schema before additive migration to avoid a downgrade.
    _decode_project(_encoded(dict(data)), pid)
    merged = copy.deepcopy(dict(current)) if current is not None else {}
    merged.update(copy.deepcopy(dict(data)))
    value = _migrate(merged, pid)
    if current is not None:
        for key in ('draft', 'draft_saved_at', 'movement_snapshots', 'draft_move_snapshots', 'workspace_versions'):
            if key not in data:
                value[key] = copy.deepcopy(current[key])
        for field in AUTHOR_FIELDS:
            if field in value and value.get(field) != current.get(field):
                value['draft'][field] = copy.deepcopy(value[field])
        if not value.get('draft_saved_at') and value.get('dance') != current.get('dance'):
            value['draft']['editor'] = _editor_from_dance(value.get('dance'))
    _capture_snapshots(value)
    value['document_revision'] = (current.get('document_revision', 0) if current else 0) + 1
    value['updated'] = time.time()
    payload = _encoded(value)
    if raw is not None:
        original = _decode_project(raw, pid)
        if original.get('schema_version', 0) < SCHEMA_VERSION:
            backup = os.path.join(project_dir(pid), 'project.pre-schema-1.json')
            if not os.path.exists(backup):
                _atomic_write(backup, raw)
        _atomic_write(_backup_path(pid), raw)
        if getattr(current, 'recovery', None) and os.path.exists(_path(pid)):
            with open(_path(pid), 'rb') as handle:
                corrupt = handle.read()
            _atomic_write(os.path.join(project_dir(pid), 'project.corrupt-' + uuid.uuid4().hex + '.json'), corrupt)
    _atomic_write(_path(pid), payload)
    return ProjectDocument(value, source_hash=hashlib.sha256(payload).hexdigest())


def save_project(pid, data, expected_revision=None):
    """Existing load/edit/save calls retain their signature and gain CAS checks.

    A successful save updates the caller's dictionary revision. Existing projects
    require a revision token; the current load_project always supplies it.
    """
    with _project_lock(pid):
        try:
            current, raw = _read_unlocked(pid)
        except FileNotFoundError:
            current, raw = None, None
        expected = expected_revision if expected_revision is not None else data.get('document_revision', 0 if current is None else None)
        if current is not None and getattr(data, 'source_hash', None) and data.source_hash != current.source_hash:
            raise RevisionConflict(expected, current['document_revision'])
        result = _save_unlocked(pid, data, current, raw, expected)
        data.clear()
        data.update(copy.deepcopy(result))
        if isinstance(data, ProjectDocument):
            data.source_hash, data.recovery = result.source_hash, None
        return data


def create_project(name, title=None, artist=None):
    ensure_dirs()
    base, pid = _slug(name), _slug(name)
    while True:
        try:
            os.mkdir(project_dir(pid))
            break
        except FileExistsError:
            pid = f'{base}-{uuid.uuid4().hex[:8]}'
    data = {'id': pid, 'name': name, 'created': time.time(),
            'song': {'title': title or name, 'artist': artist or '', 'path': None, 'filename': None},
            'analysis': None, 'lyrics_raw': '', 'lyric_sections': [], 'alignment': None,
            'sections': [], 'phrase': None, 'lyric_move_draft': None, 'dance': {}, 'tutorial': None, 'sheet_meta': {}}
    save_project(pid, data)
    return data


def list_projects():
    ensure_dirs()
    out = []
    for pid in sorted(os.listdir(PROJECTS_DIR)):
        if not PROJECT_ID_RE.fullmatch(pid) or not os.path.isdir(os.path.join(PROJECTS_DIR, pid)):
            continue
        try:
            data = load_project(pid)
            song, dance = data.get('song') or {}, data.get('dance') or {}
            out.append({'id': pid, 'name': data.get('name', pid), 'title': song.get('title'),
                        'created': data.get('created'), 'has_audio': bool(song.get('path')),
                        'has_analysis': bool(data.get('analysis')),
                        'has_dance': bool(dance.get('candidates') or dance.get('custom')),
                        'has_draft': bool((data.get('draft', {}).get('editor') or {}).get('moves')),
                        'document_revision': data['document_revision'], 'recovery': data.recovery})
        except (OSError, ValueError):
            continue
    return sorted(out, key=lambda item: item.get('created') or 0, reverse=True)


def _workspace_result(data):
    draft = copy.deepcopy(data['draft'])
    draft['analysis'] = copy.deepcopy(data.get('analysis'))
    return {'project_id': data['id'], 'schema_version': data['schema_version'],
            'document_revision': data['document_revision'], 'draft': draft,
            'analysis': copy.deepcopy(data.get('analysis')),
            'accepted_dance': copy.deepcopy(data.get('dance') or {}), 'saved_at': data.get('draft_saved_at'),
            'recovery': getattr(data, 'recovery', None), 'snapshot_issues': copy.deepcopy(data.get('snapshot_issues') or {})}


def get_workspace(pid):
    data = load_project(pid)
    _capture_snapshots(data)
    return _workspace_result(data)


def save_workspace(pid, draft, expected_revision):
    if not isinstance(draft, dict):
        raise ValueError('Draft must be an object')
    draft = copy.deepcopy(draft)
    if 'music_map' in draft and draft['music_map']:
        from .music_map import validate_map
        validate_map(draft['music_map'])
    with _project_lock(pid):
        current, raw = _read_unlocked(pid)
        _check_revision(expected_revision, current)
        data = copy.deepcopy(current)
        tutorial_edits = draft.pop('tutorial_edits', None)
        if tutorial_edits is not None:
            from . import tutorial as tutorial_engine
            if not isinstance(tutorial_edits, dict) or set(tutorial_edits) - {'provenance_hash', 'segments', 'count_in', 'voice_notes', 'producer_notes', 'tempo_grid_confirmed'}:
                raise ValueError('Tutorial edits must contain only review fields.')
            plan = current.get('tutorial')
            if not isinstance(plan, dict) or not plan.get('provenance_hash') or tutorial_edits.get('provenance_hash') != plan['provenance_hash']:
                raise ValueError('The tutorial changed. Reload its current blueprint before applying review edits.')
            try:
                updated = tutorial_engine.update_tutorial_plan(plan, tutorial_edits.get('segments', []),
                    **{key: tutorial_edits[key] for key in ('count_in', 'voice_notes', 'producer_notes', 'tempo_grid_confirmed') if key in tutorial_edits})
            except KeyError as exc:
                raise ValueError(str(exc)) from exc
            if plan.get('status') == 'STALE':
                updated['status'] = 'STALE'
            draft['tutorial'] = updated
        if 'lyrics_raw' in draft and draft['lyrics_raw'] != current.get('lyrics_raw'):
            from . import phrasing
            if not isinstance(draft['lyrics_raw'], str):
                raise ValueError('Lyrics must be plain text.')
            draft['lyric_sections'] = phrasing.parse_tagged_lyrics(draft['lyrics_raw'])
            data['alignment'] = None
            if data.get('lyric_move_draft'):
                data['lyric_move_draft']['status'] = 'STALE'
                data['lyric_move_draft']['stale_reason'] = 'The lyrics changed.'
            if data.get('tutorial'):
                data['tutorial']['status'] = 'STALE'
                if 'tutorial' in draft and isinstance(draft['tutorial'], dict):
                    draft['tutorial']['status'] = 'STALE'
        if 'sections' in draft and draft['sections'] != current.get('sections', []):
            data['phrase'] = None
            if data.get('lyric_move_draft'):
                data['lyric_move_draft']['status'] = 'STALE'
                data['lyric_move_draft']['stale_reason'] = 'The music sections changed.'
            if data.get('tutorial'):
                data['tutorial']['status'] = 'STALE'
                if isinstance(draft.get('tutorial'), dict):
                    draft['tutorial']['status'] = 'STALE'
        # Omitted fields survive older clients; provided fields replace a field.
        data['draft'].update(copy.deepcopy(draft))
        for field in AUTHOR_FIELDS:
            if field in draft:
                if field == 'song':
                    if not isinstance(draft[field], dict):
                        raise ValueError('Song metadata must be an object')
                    # Media identity belongs to upload/relink endpoints. Older
                    # forms may send only title/artist or a stale path value.
                    song = copy.deepcopy(data.get('song') or {})
                    song.update({key: copy.deepcopy(value) for key, value in draft[field].items()
                                 if key not in ('path', 'filename', 'sha256', 'fingerprint', 'recording_id', 'content_signature')})
                    data['song'] = song
                    data['draft']['song'] = copy.deepcopy(song)
                else:
                    data[field] = copy.deepcopy(draft[field])
        data['draft_saved_at'] = time.time()
        return _workspace_result(_save_unlocked(pid, data, current, raw, expected_revision))


def _version_path(pid, version_id):
    if not isinstance(version_id, str) or not VERSION_ID_RE.fullmatch(version_id):
        raise ValueError('Invalid version id')
    path = os.path.realpath(os.path.join(project_dir(pid), 'versions', version_id + '.json'))
    if os.path.commonpath((project_dir(pid), path)) != project_dir(pid):
        raise ValueError('Version path leaves the project directory')
    return path


def _version_payload(data, label, kind='named'):
    version = {'version_id': 'v-' + uuid.uuid4().hex, 'label': label, 'created_at': time.time(),
               'kind': kind, 'source_revision': data['document_revision'], 'draft': copy.deepcopy(data['draft']),
               'draft_move_snapshots': copy.deepcopy(data.get('draft_move_snapshots') or {}),
               'accepted_dance': copy.deepcopy(data.get('dance') or {}), 'schema_version': SCHEMA_VERSION}
    version['content_hash'] = _digest(version)
    return version


def _version_summary(version):
    return {field: version[field] for field in ('version_id', 'label', 'created_at', 'kind', 'source_revision')}


def list_versions(pid):
    data = load_project(pid)
    return {'document_revision': data['document_revision'], 'versions': copy.deepcopy(data['workspace_versions'])}


def get_version(pid, version_id):
    load_project(pid)
    with open(_version_path(pid, version_id), 'rb') as handle:
        version = json.load(handle)
    if not isinstance(version, dict) or version.get('schema_version') != SCHEMA_VERSION:
        raise UnsupportedSchema('This saved version uses an unsupported schema.')
    if not isinstance(version.get('draft'), dict) or version.get('version_id') != version_id:
        raise ProjectCorrupt('Saved version is invalid.')
    if version.get('content_hash') != _digest({key: value for key, value in version.items() if key != 'content_hash'}):
        raise ProjectCorrupt('Saved version failed its integrity check; the current draft was not changed.')
    return version


def create_version(pid, label, expected_revision):
    label = str(label or '').strip()
    if not label or len(label) > 120:
        raise ValueError('Give the version a name of 1 to 120 characters')
    with _project_lock(pid):
        current, raw = _read_unlocked(pid)
        _check_revision(expected_revision, current)
        data = copy.deepcopy(current)
        _capture_snapshots(data)
        version = _version_payload(data, label)
        path = _version_path(pid, version['version_id'])
        _atomic_write(path, _encoded(version))
        data['workspace_versions'].append(_version_summary(version))
        try:
            saved = _save_unlocked(pid, data, current, raw, expected_revision)
        except Exception:
            os.unlink(path)
            raise
        return {'document_revision': saved['document_revision'], 'version': _version_summary(version)}


def restore_version(pid, version_id, expected_revision):
    # Immutable version read outside the document lock; CAS is repeated inside.
    version = get_version(pid, version_id)
    with _project_lock(pid):
        current, raw = _read_unlocked(pid)
        _check_revision(expected_revision, current)
        data = copy.deepcopy(current)
        _capture_snapshots(data)
        before = _version_payload(data, 'Before restoring ' + version['label'], 'before_restore')
        path = _version_path(pid, before['version_id'])
        _atomic_write(path, _encoded(before))
        data['workspace_versions'].append(_version_summary(before))
        data['draft'] = copy.deepcopy(version['draft'])
        data['draft_move_snapshots'] = copy.deepcopy(version['draft_move_snapshots'])
        for field in AUTHOR_FIELDS:
            if field in data['draft']:
                data[field] = copy.deepcopy(data['draft'][field])
        data['draft_saved_at'] = time.time()
        try:
            saved = _save_unlocked(pid, data, current, raw, expected_revision)
        except Exception:
            os.unlink(path)
            raise
        result = _workspace_result(saved)
        result['restored_version_id'] = version_id
        result['recovery_version'] = _version_summary(before)
        return result


def delete_project(pid):
    import shutil
    with _project_lock(pid):
        directory = project_dir(pid)
        if os.path.isdir(directory):
            shutil.rmtree(directory)
