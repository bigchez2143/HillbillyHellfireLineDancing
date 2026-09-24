"""Private, allowlisted snapshots and non-destructive restore into new profiles.

Archive members are data, never SQL or executable code. SQLite backup() gives
each local database a consistent read; project/history copies use their writer
locks. There is no global transaction spanning independent application stores.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
import sys
import threading
import time
from urllib.parse import urlsplit, urlunsplit
import uuid
import zipfile

from . import project, library_store, instructor_tools, settings, steps, community_shelf

MAX_ARCHIVE_BYTES = 2 * 1024**3
MAX_EXPANDED_BYTES = 4 * 1024**3
MAX_MEDIA_BYTES = 512 * 1024**2
MAX_JSON_BYTES = 32 * 1024**2
MAX_FILES = 30000
MAX_ROWS = 100000
JOB_SECONDS = 3600
JOB_ROOT = None
PROFILE_ROOT = None
_LOCK = threading.RLock()
TOKEN = re.compile(r'^[a-f0-9]{32}$')
PROFILE = re.compile(r'^restored-[a-f0-9]{32}$')
SHA = re.compile(r'^[a-f0-9]{64}$')
MEDIA_EXT = {'.mp3': 'music', '.wav': 'music', '.m4a': 'music', '.flac': 'music',
             '.ogg': 'music', '.aac': 'music', '.png': 'photos', '.jpg': 'photos',
             '.jpeg': 'photos', '.gif': 'photos', '.webp': 'photos',
             '.mp4': 'videos', '.mov': 'videos', '.webm': 'videos'}
SECRET_KEYS = {'api_key', 'apikey', 'api_key_protected', 'access_token', 'refresh_token',
               'password', 'authorization', 'client_secret', 'secret', 'credentials'}
LIBRARY_TABLES = {
    'records': ('id', 'version', 'payload'),
    'versions': ('record_id', 'version', 'payload'),
    'media': ('id', 'record_id', 'filename', 'payload'),
    'batches': ('id', 'changes', 'state'),
}
LIBRARY_DDL = '''
CREATE TABLE records(id TEXT PRIMARY KEY,version INTEGER NOT NULL,payload TEXT NOT NULL);
CREATE TABLE versions(record_id TEXT,version INTEGER,payload TEXT NOT NULL,PRIMARY KEY(record_id,version));
CREATE TABLE media(id TEXT PRIMARY KEY,record_id TEXT,filename TEXT,payload TEXT);
CREATE TABLE batches(id TEXT PRIMARY KEY,changes TEXT,state TEXT);
CREATE TABLE previews(id TEXT PRIMARY KEY,digest TEXT,payload TEXT,created TEXT,result TEXT);
'''


class Conflict(ValueError):
    pass


def _json(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def _decode(payload):
    if len(payload) > MAX_JSON_BYTES:
        raise ValueError('A backup metadata file exceeds the 32 MiB limit.')
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise ValueError('Duplicate JSON field in backup.')
            result[key] = value
        return result
    def invalid(_):
        raise ValueError('Non-finite JSON value in backup.')
    try:
        value = json.loads(payload.decode('utf-8'), object_pairs_hook=pairs, parse_constant=invalid)
        stack, count = [(value, 0)], 0
        while stack:
            node, depth = stack.pop(); count += 1
            if depth > 80 or count > 1000000:
                raise ValueError('Backup metadata is too deeply nested or complex.')
            if isinstance(node, dict):
                stack.extend((child, depth + 1) for child in node.values())
            elif isinstance(node, list):
                stack.extend((child, depth + 1) for child in node)
        return value
    except (UnicodeError, RecursionError, json.JSONDecodeError) as exc:
        raise ValueError('Backup metadata is not readable JSON.') from exc


def _clean_secrets(value):
    if isinstance(value, dict):
        return {key: _clean_secrets(child) for key, child in value.items()
                if str(key).casefold().replace('-', '_') not in SECRET_KEYS}
    if isinstance(value, list):
        return [_clean_secrets(child) for child in value]
    return value


def _app_root():
    return Path(__file__).resolve().parents[1]


def _base():
    explicit = os.environ.get('LINE_DANCE_DATA_DIR')
    return Path(explicit).absolute() if explicit else _app_root() / 'private-backups'


def job_root():
    return Path(JOB_ROOT).absolute() if JOB_ROOT else _base() / 'backup-work'


def profile_root():
    return Path(PROFILE_ROOT).absolute() if PROFILE_ROOT else _base() / 'restored-profiles'


def _no_links(path):
    """Reject symlinks and Windows reparse points before reading owned paths."""
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError('Backup storage must not contain links or Windows junctions.')
    return path


def _owned(path, root):
    # pathlib.absolute() preserves '..' on Windows. Reject such input before
    # containment, then normalize both sides without following filesystem links.
    if '..' in Path(path).parts:
        raise ValueError('Parent traversal is not permitted in backup storage paths.')
    path, root = Path(os.path.abspath(path)), Path(os.path.abspath(root))
    if path == root or not path.is_relative_to(root):
        raise ValueError('A backup path leaves its owned storage directory.')
    _no_links(path)
    return path


def _remove_owned(path, root):
    path = _owned(path, root)
    if path.is_dir():
        shutil.rmtree(path)


def _read(path, root, limit=MAX_JSON_BYTES):
    path = _owned(path, root)
    if path.stat().st_size > limit:
        raise ValueError('A selected backup file exceeds its size limit.')
    with path.open('rb') as stream:
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise ValueError('A selected backup file grew beyond its size limit.')
    return value


def _new_job(kind):
    root = _no_links(job_root()); root.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        for folder in root.iterdir():
            if TOKEN.fullmatch(folder.name) and folder.is_dir() and folder.stat().st_mtime < time.time() - JOB_SECONDS:
                _remove_owned(folder, root)
        if sum(1 for p in root.iterdir() if TOKEN.fullmatch(p.name)) >= 8:
            raise ValueError('Close an existing backup preview or wait for it to expire before creating another.')
        token = uuid.uuid4().hex
        folder = root / token; folder.mkdir()
        (folder / 'job.json').write_bytes(_json({'kind': kind, 'created': time.time()}))
        return token, folder


def new_import():
    return _new_job('import')


def discard(token):
    if not TOKEN.fullmatch(str(token)):
        raise ValueError('Invalid backup preview identifier.')
    with _LOCK:
        _remove_owned(job_root() / token, job_root())


def _job(token, kind, digest=None):
    if not TOKEN.fullmatch(str(token)):
        raise ValueError('Invalid backup preview identifier.')
    folder = _owned(job_root() / token, job_root())
    meta = _decode(_read(folder / 'job.json', folder))
    if meta.get('kind') != kind or time.time() - meta.get('created', 0) > JOB_SECONDS:
        raise Conflict('This backup preview expired. Preview the file again.')
    if digest is not None and (not SHA.fullmatch(str(digest)) or digest != meta.get('manifest_digest')):
        raise Conflict('The selected backup differs from its preview. Preview it again.')
    return folder, meta


@contextmanager
def _sqlite_snapshot(path, root):
    path = _owned(path, root)
    if path.stat().st_size > 256 * 1024**2:
        raise ValueError('A local database exceeds the 256 MiB snapshot limit.')
    source = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=15)
    target = sqlite3.connect(':memory:')
    deadline = time.monotonic() + 30
    try:
        source.execute('PRAGMA trusted_schema=OFF')
        def progress(*_):
            if time.monotonic() > deadline:
                raise Conflict('A database is busy. Finish saving and retry the backup.')
        source.backup(target, pages=128, progress=progress, sleep=.02)
        target.execute('PRAGMA trusted_schema=OFF')
        if target.execute('PRAGMA quick_check').fetchone() != ('ok',):
            raise ValueError('A local database failed its integrity check.')
        if target.execute("SELECT count(*) FROM sqlite_master WHERE type IN ('view','trigger')").fetchone()[0]:
            raise ValueError('Unsupported executable database objects in backup source.')
        yield target
    finally:
        source.close(); target.close()


def _table_dump(conn, schema):
    output = {}
    for table, columns in schema.items():
        actual = tuple(row[1] for row in conn.execute('PRAGMA table_info("' + table + '")'))
        if actual != columns:
            raise ValueError('Unsupported ' + table + ' database schema. Use a compatible app version.')
        values = conn.execute('SELECT ' + ','.join('"' + c + '"' for c in columns) + ' FROM "' + table + '"').fetchmany(MAX_ROWS + 1)
        if len(values) > MAX_ROWS:
            raise ValueError('A database table exceeds the backup row limit.')
        output[table] = [dict(zip(columns, row)) for row in values]
    return {'schema_version': 1, 'tables': output}


def _safe_browser(value):
    if not isinstance(value, dict) or set(value) - {'mode', 'resources', 'lastProject'}:
        raise ValueError('Unsupported browser preferences.')
    mode = value.get('mode', 'basic')
    if mode not in {'basic', 'advanced'}:
        raise ValueError('Choose Basic or Advanced.')
    resources = value.get('resources', [])
    if not isinstance(resources, list) or len(resources) > 100:
        raise ValueError('Use at most 100 saved resource links.')
    clean = []
    for row in resources:
        if not isinstance(row, dict) or set(row) != {'name', 'url'} or not isinstance(row['name'], str) or len(row['name']) > 300:
            raise ValueError('Invalid saved resource link.')
        instructor_tools.safe_http_url(row['url'])
        # Provider credentials in query strings are not part of preferences.
        parsed = urlsplit(row['url'])
        clean.append({'name': row['name'], 'url': urlunsplit((parsed.scheme, parsed.netloc, parsed.path, '', ''))})
    last = value.get('lastProject', '')
    if last and (not isinstance(last, str) or not project.PROJECT_ID_RE.fullmatch(last)):
        raise ValueError('Invalid last-project preference.')
    return {'mode': mode, 'resources': clean, 'lastProject': last}


def _safe_settings(raw):
    ai = raw.get('ai') or {}
    # Never copy a key, protected credential, arbitrary header or credential URL.
    safe = {'ai': {'enabled': False,
                   'provider': ai.get('provider') if ai.get('provider') in {'openai_compatible', 'anthropic_messages', 'custom'} else 'openai_compatible',
                   'model': str(ai.get('model') or '')[:160],
                   'timeout_seconds': ai.get('timeout_seconds') if type(ai.get('timeout_seconds')) is int and 5 <= ai['timeout_seconds'] <= 180 else 60,
                   'base_url': ''}}
    if isinstance(raw, dict) and 'community' in raw:
        safe['community'] = {'links': community_shelf.links_for_backup(raw)}
    return safe


def _project_json(raw, pid, filename):
    value = _decode(raw)
    if filename.startswith('v-'):
        if not isinstance(value, dict) or value.get('schema_version') != 1 or value.get('version_id') + '.json' != filename or not isinstance(value.get('draft'), dict):
            raise ValueError('Invalid saved project version.')
        if value.get('content_hash') != project._digest({k: v for k, v in value.items() if k != 'content_hash'}):
            raise ValueError('A saved project version failed its integrity check.')
    else:
        project._decode_project(raw, pid)
    clean = _clean_secrets(value)
    if filename.startswith('v-'):
        clean['content_hash'] = project._digest({k: v for k, v in clean.items() if k != 'content_hash'})
    return clean


def _path_fields(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(child, str) and child and (key == 'path' or key.endswith('_path')) and not child.startswith(('https://', 'http://')):
                yield value, key, child
            elif isinstance(child, (dict, list)):
                yield from _path_fields(child)
    elif isinstance(value, list):
        for child in value:
            yield from _path_fields(child)


def _media_header(suffix, header):
    if suffix in {'.wav', '.webp'}:
        return header[:4] == b'RIFF' and header[8:12] == (b'WAVE' if suffix == '.wav' else b'WEBP')
    if suffix == '.flac': return header.startswith(b'fLaC')
    if suffix in {'.mp3', '.aac'}: return header.startswith(b'ID3') or len(header) > 1 and header[0] == 255 and header[1] & 224 == 224
    if suffix == '.ogg': return header.startswith(b'OggS')
    if suffix in {'.m4a', '.mp4', '.mov'}: return header[4:8] == b'ftyp'
    if suffix == '.webm': return header.startswith(b'\x1aE\xdf\xa3')
    if suffix == '.png': return header.startswith(b'\x89PNG\r\n\x1a\n')
    if suffix in {'.jpg', '.jpeg'}: return header.startswith(b'\xff\xd8\xff')
    if suffix == '.gif': return header.startswith((b'GIF87a', b'GIF89a'))
    return False


class Snapshot:
    def __init__(self, folder, options):
        self.folder, self.options = folder, options
        self.entries, self.media, self.omissions = [], [], []
        self.names, self.total = set(), 0
        self.zip = zipfile.ZipFile(folder / 'backup.zip', 'x', compression=zipfile.ZIP_STORED)

    def add(self, name, payload=None, source=None, owner=None):
        _member_kind(name)
        if name in self.names: return
        if len(self.names) >= MAX_FILES: raise ValueError('The backup has too many files.')
        digest, count = hashlib.sha256(), 0
        with self.zip.open(name, 'w', force_zip64=True) as target:
            if source is not None:
                path = _owned(source, owner)
                before = path.stat()
                if before.st_size > MAX_MEDIA_BYTES: raise ValueError('A media file exceeds 512 MiB.')
                with path.open('rb') as stream:
                    head = stream.read(32)
                    if not _media_header(path.suffix.lower(), head):
                        raise ValueError('A selected media file has an unsupported file signature.')
                    stream.seek(0)
                    for chunk in iter(lambda: stream.read(1024**2), b''):
                        count += len(chunk)
                        if count > MAX_MEDIA_BYTES: raise ValueError('A media file grew beyond 512 MiB.')
                        digest.update(chunk); target.write(chunk)
                after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise Conflict('A media file changed during backup. Finish editing it and retry.')
            else:
                if len(payload) > MAX_JSON_BYTES: raise ValueError('A metadata file exceeds 32 MiB.')
                target.write(payload); digest.update(payload); count = len(payload)
        self.total += count
        if self.total > MAX_ARCHIVE_BYTES - MAX_JSON_BYTES: raise ValueError('The selected backup exceeds 2 GiB. Exclude media and preview again.')
        self.names.add(name)
        self.entries.append({'path': name, 'bytes': count, 'sha256': digest.hexdigest()})

    def local_media(self, original, owners, preferred=None):
        key = original
        prior = next((m for m in self.media if m['original_path'] == key), None)
        if prior: return
        row = {'original_path': key, 'archive_path': None, 'kind': MEDIA_EXT.get(Path(original).suffix.lower(), 'other'), 'bytes': None, 'reason': 'external_path_relink_required'}
        candidate = Path(original)
        if not candidate.is_absolute():
            row['reason'] = 'relative_path_relink_required'; self.media.append(row); return
        if '..' in candidate.parts:
            self.media.append(row); return
        candidate = Path(os.path.abspath(candidate))
        for root, prefix in owners:
            root = Path(os.path.abspath(root))
            if not candidate.is_relative_to(root): continue
            if row['kind'] == 'other': row['reason'] = 'unsupported_or_generated_file'; break
            relative = candidate.relative_to(root)
            if prefix.startswith('projects/') and len(relative.parts) > 1 and relative.parts[0] not in {'recordings', 'media', 'attachments'}:
                row['reason'] = 'generated_or_unowned_subdirectory'; break
            try:
                path = _owned(candidate, root)
                if not path.is_file(): row['reason'] = 'missing_file'; break
                row['bytes'] = path.stat().st_size
                if not self.options['include_' + row['kind']]: row['reason'] = 'not_selected'; break
                if row['bytes'] > MAX_MEDIA_BYTES: raise ValueError('A selected media file exceeds 512 MiB; exclude media to back up its metadata.')
                # Filename is generated from the source identity, never from a path supplied by an archive.
                name = preferred or prefix + '/backup-' + _sha(str(path).encode()) + path.suffix.lower()
                self.add(name, source=path, owner=root)
                row.update(archive_path=name, reason='included')
                break
            except FileNotFoundError:
                row['reason'] = 'missing_file'; break
        self.media.append(row)

    def finish(self):
        manifest = {'format': 'line-dance-private-backup', 'schema_version': 1,
                    'snapshot_id': uuid.uuid4().hex, 'created_at': datetime.now(timezone.utc).isoformat(),
                    'entries': self.entries, 'media': self.media, 'omissions': self.omissions,
                    'consistency': 'Project/history writer locks and independent SQLite backup snapshots; not a cross-store transaction.'}
        raw = _json(manifest)
        if len(raw) > MAX_JSON_BYTES: raise ValueError('Backup manifest exceeds its size limit.')
        self.zip.writestr('manifest.json', raw); self.zip.close()
        return manifest, _sha(raw)


def create_export(options=None, browser_preferences=None):
    options = options or {}
    if set(options) - {'include_music', 'include_photos', 'include_videos'} or any(type(v) is not bool for v in options.values()):
        raise ValueError('Media options must be true or false.')
    selected = {key: options.get(key, False) for key in ('include_music', 'include_photos', 'include_videos')}
    token, folder = _new_job('export')
    snap = Snapshot(folder, selected)
    try:
        roots, documents = [], []
        project_root = _no_links(Path(project.PROJECTS_DIR).absolute())
        if project_root.exists():
            for directory in sorted(project_root.iterdir()):
                if not project.PROJECT_ID_RE.fullmatch(directory.name) or not directory.is_dir(): continue
                _owned(directory, project_root)
                pid = directory.name
                roots.append((directory, 'projects/' + pid + '/media'))
                with project._project_lock(pid):
                    candidates = [directory / name for name in ('project.json', 'project.last-good.json', 'project.pre-schema-1.json')]
                    if (directory / 'versions').exists():
                        _owned(directory / 'versions', project_root)
                        candidates += sorted((directory / 'versions').glob('v-*.json'))
                    valid_current = False
                    for source in candidates:
                        if not source.exists(): continue
                        if source.parent.name == 'versions' and not project.VERSION_ID_RE.fullmatch(source.stem):
                            raise ValueError('Invalid project version filename.')
                        value = _project_json(_read(source, project_root), pid, source.name)
                        documents.append(('projects/' + pid + '/' + source.relative_to(directory).as_posix(), value))
                        valid_current |= source.name == 'project.json'
                    if not valid_current:
                        raise ValueError('Project ' + pid + ' has no readable current document. Recover it before a complete backup.')
        library_root = _no_links(library_store.directory().absolute())
        database = library_root / 'library.sqlite3'
        if database.exists():
            with _sqlite_snapshot(database, library_root) as conn:
                library = _table_dump(conn, LIBRARY_TABLES)
            library = _sanitize_document(library)
            _validate_library(library)
            documents.append(('stores/library.json', library))
            for row in library['tables']['media']:
                path = library_root / 'media' / row['filename']
                snap.local_media(str(path), [(library_root / 'media', 'library/media')], 'library/media/' + row['filename'])
        roots.append((library_root / 'media', 'library/media'))
        with instructor_tools._locked() as tools_root:
            for name in ('state.json', 'state.backup.json'):
                path = tools_root / name
                if path.exists():
                    value = _decode(_read(path, tools_root))
                    instructor_tools.State.model_validate(value)
                    documents.append(('tools/' + name, value))
        custom_path = Path(steps.CUSTOM_MOVES_PATH).absolute()
        if custom_path.exists():
            value = _clean_secrets(_decode(_read(custom_path, custom_path.parent))); _validate_custom(value)
            documents.append(('custom-moves.json', value))
        settings_path = Path(settings.SETTINGS_FILE).absolute()
        raw_settings = _decode(_read(settings_path, settings_path.parent)) if settings_path.exists() else {}
        documents.append(('settings.json', _safe_settings(raw_settings)))
        documents.append(('browser-preferences.json', _safe_browser(browser_preferences or {})))
        _snapshot_optional_stores(documents)
        for name, value in documents:
            for node in _document_nodes(value):
                for _, _, original in _path_fields(node): snap.local_media(original, roots)
            snap.add(name, payload=_json(_sanitize_document(value)))
        snap.omissions.extend(['Provider credentials, protected keys and provider endpoint URLs are excluded; AI is disabled after restore.',
                               'Runtime, optional models, generated repair/stem caches, arbitrary files, import previews and browser-only unsaved recovery drafts are excluded.',
                               'External and missing media paths remain recorded for relinking; their file contents are not read.',
                               'Resource-link query strings and fragments are excluded from browser preferences.'])
        manifest, digest = snap.finish()
        result = validate_archive(folder / 'backup.zip')
        result.update(token=token, manifest_digest=digest, expires_in_seconds=JOB_SECONDS)
        (folder / 'job.json').write_bytes(_json({'kind': 'export', 'created': time.time(), 'manifest_digest': digest}))
        return result
    except BaseException:
        snap.zip.close(); _remove_owned(folder, job_root()); raise


def _snapshot_optional_stores(documents):
    from . import browser_preferences
    path = browser_preferences.directory().absolute() / 'browser.sqlite3'
    if path.exists():
        with _sqlite_snapshot(path, path.parent) as conn:
            rows = _table_dump(conn, {'favorites': ('key',)})
        value = {'schema_version': 1, 'favorites': [r['key'] for r in rows['tables']['favorites']]}
        _validate_preferences(value)
        documents.append(('stores/preferences.json', value))
    try:
        from . import phrase_store
    except ImportError:
        return
    path = phrase_store.directory().absolute() / 'phrases.sqlite3'
    if path.exists():
        with _sqlite_snapshot(path, path.parent) as conn:
            value = _table_dump(conn, {k: LIBRARY_TABLES[k] for k in ('records', 'versions')})
        value = _sanitize_document(value)
        _validate_phrases(value)
        documents.append(('stores/phrases.json', value))


def _tables(value, schema):
    if not isinstance(value, dict) or set(value) != {'schema_version', 'tables'} or value['schema_version'] != 1 or not isinstance(value['tables'], dict) or set(value['tables']) != set(schema):
        raise ValueError('Unsupported backup database interchange schema.')
    for table, columns in schema.items():
        rows = value['tables'][table]
        if not isinstance(rows, list) or len(rows) > MAX_ROWS:
            raise ValueError('Invalid backup database row count.')
        for row in rows:
            if not isinstance(row, dict) or set(row) != set(columns):
                raise ValueError('Invalid backup database columns.')
            if any(not isinstance(v, (str, int)) or isinstance(v, bool) for v in row.values()):
                raise ValueError('Invalid backup database value.')
    return value['tables']


def _version_tables(tables, validator):
    records, versions = {}, {}
    for table in ('records', 'versions'):
        for row in tables[table]:
            record = _decode(row['payload'].encode())
            validator(record)
            identity = row.get('id', row.get('record_id'))
            if record['id'] != identity or type(row['version']) is not int or record['version'] != row['version']:
                raise ValueError('A database row disagrees with its saved definition.')
            key = identity if table == 'records' else (identity, row['version'])
            target = records if table == 'records' else versions
            if key in target: raise ValueError('Duplicate record or version in backup.')
            target[key] = record
    for identity, record in records.items():
        if versions.get((identity, record['version'])) != record:
            raise ValueError('A current library record has no matching immutable version.')
    if any(identity not in records for identity, _ in versions):
        raise ValueError('A library version has no corresponding record.')
    return records, versions


def _validate_library(value):
    tables = _tables(value, LIBRARY_TABLES)
    def validate(record):
        if not isinstance(record, dict): raise ValueError('Invalid move record.')
        library_store._check_id(record.get('id'), 'move')
        if type(record.get('version')) is not int or record['version'] < 1 or type(record.get('deleted')) is not bool or record.get('generator_eligible') is not False:
            raise ValueError('Invalid move version/status.')
        library_store._fields({k: record.get(k) for k in library_store.FIELDS})
        library_store._no_secrets(record)
        if not isinstance(record.get('attachments'), list) or len(record['attachments']) > MAX_ROWS or not isinstance(record.get('review'), dict):
            raise ValueError('Invalid move attachment or review metadata.')
    records, versions = _version_tables(tables, validate)
    media = {}
    for row in tables['media']:
        library_store._check_id(row['id'], 'media')
        payload = _decode(row['payload'].encode())
        if row['id'] in media or row['record_id'] not in records or not isinstance(payload, dict) or payload.get('id') != row['id']:
            raise ValueError('Invalid or duplicate media metadata.')
        name = row['filename']
        if name != row['id'] + Path(name).suffix.lower() or Path(name).suffix.lower() not in {k for k, v in MEDIA_EXT.items() if v in {'photos', 'videos'}}:
            raise ValueError('Invalid library media filename.')
        if not SHA.fullmatch(str(payload.get('sha256'))) or type(payload.get('bytes')) is not int or not 0 <= payload['bytes'] <= MAX_MEDIA_BYTES:
            raise ValueError('Invalid media integrity metadata.')
        media[row['id']] = payload
    for record in [*records.values(), *versions.values()]:
        for attachment in record['attachments']:
            if not isinstance(attachment, dict) or attachment.get('id') not in media or media[attachment['id']] != attachment:
                raise ValueError('A saved move refers to missing or inconsistent media metadata.')
    batches = set()
    for row in tables['batches']:
        library_store._check_id(row['id'], 'batch')
        if row['id'] in batches or row['state'] not in {'applied', 'rolled_back'}:
            raise ValueError('Invalid library batch history.')
        batches.add(row['id'])
        changes = _decode(row['changes'].encode())
        if not isinstance(changes, list) or len(changes) > MAX_ROWS: raise ValueError('Invalid batch changes.')
        for change in changes:
            if not isinstance(change, dict) or set(change) != {'id', 'applied_version', 'prior'} or change['id'] not in records or type(change['applied_version']) is not int or change['applied_version'] < 1:
                raise ValueError('Invalid batch change.')
            if change['prior'] is not None:
                validate(change['prior'])
                if change['prior']['id'] != change['id']: raise ValueError('Batch prior identity mismatch.')
    return tables


def _validate_phrases(value):
    from . import phrase_store
    tables = _tables(value, {k: LIBRARY_TABLES[k] for k in ('records', 'versions')})
    _version_tables(tables, phrase_store.validate_record)
    return tables


def _validate_preferences(value):
    from . import browser_preferences
    if not isinstance(value, dict) or set(value) != {'schema_version', 'favorites'} or value['schema_version'] != 1 or not isinstance(value['favorites'], list) or len(value['favorites']) > 5000:
        raise ValueError('Invalid move favorites backup.')
    if any(not isinstance(key, str) or not browser_preferences.KEY.fullmatch(key) for key in value['favorites']) or len(set(value['favorites'])) != len(value['favorites']):
        raise ValueError('Invalid or duplicate favorite.')


def _validate_custom(value):
    if not isinstance(value, dict) or set(value) != {'schema_version', 'moves'} or value['schema_version'] != 1 or not isinstance(value['moves'], list) or len(value['moves']) > 5000:
        raise ValueError('Invalid legacy custom-move backup.')
    ids = set()
    for row in value['moves']:
        move = steps._custom_move_from_record(row)
        if move.id in ids: raise ValueError('Duplicate custom move.')
        ids.add(move.id)
        library_store._no_secrets(row)


def _member_kind(name):
    if not isinstance(name, str) or len(name) > 300 or '\\' in name or ':' in name or any(ord(c) < 32 for c in name) or name.startswith('/') or name.endswith('/'):
        raise ValueError('Unsafe archive member path.')
    p = PurePosixPath(name)
    if str(p) != name or any(c in {'.', '..'} for c in p.parts): raise ValueError('Unsafe archive member path.')
    if any(re.fullmatch(r'(?i)(con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\..*)?', part) for part in p.parts):
        raise ValueError('Reserved Windows path in archive.')
    if name in {'settings.json', 'custom-moves.json', 'browser-preferences.json', 'stores/library.json', 'stores/phrases.json', 'stores/preferences.json', 'tools/state.json', 'tools/state.backup.json'}:
        return 'json'
    if len(p.parts) >= 3 and p.parts[0] == 'projects' and project.PROJECT_ID_RE.fullmatch(p.parts[1]):
        if len(p.parts) == 3 and p.parts[2] in {'project.json', 'project.last-good.json', 'project.pre-schema-1.json'}: return 'json'
        if len(p.parts) == 4 and p.parts[2] == 'versions' and p.suffix == '.json' and project.VERSION_ID_RE.fullmatch(p.stem): return 'json'
        if len(p.parts) == 4 and p.parts[2] == 'media' and re.fullmatch(r'backup-[a-f0-9]{64}', p.stem) and p.suffix in MEDIA_EXT: return 'media'
    if len(p.parts) == 3 and p.parts[:2] == ('library', 'media') and re.fullmatch(r'(?:media-[a-f0-9]{32}|backup-[a-f0-9]{64})', p.stem) and p.suffix in MEDIA_EXT:
        return 'media'
    raise ValueError('This archive contains a file outside the private-backup allowlist.')


def _validate_document(name, payload):
    value = _decode(payload)
    if any(_clean_secrets(node) != node for node in _document_nodes(value)):
        raise ValueError('Provider credential fields are not permitted in a backup, including serialized history.')
    if name.startswith('projects/'):
        value = _project_json(payload, PurePosixPath(name).parts[1], PurePosixPath(name).name)
    elif name.startswith('tools/'):
        instructor_tools.State.model_validate(value)
    elif name == 'stores/library.json': _validate_library(value)
    elif name == 'stores/phrases.json': _validate_phrases(value)
    elif name == 'stores/preferences.json': _validate_preferences(value)
    elif name == 'custom-moves.json': _validate_custom(value)
    elif name == 'settings.json':
        if not isinstance(value, dict) or _safe_settings(value) != value: raise ValueError('Unsafe backup settings.')
    elif name == 'browser-preferences.json':
        if _safe_browser(value) != value: raise ValueError('Unsafe browser preferences.')
    return value


def _inspect_archive(path):
    if Path(path).stat().st_size > MAX_ARCHIVE_BYTES: raise ValueError('Backup archives must be at most 2 GiB.')
    try:
        archive = zipfile.ZipFile(path)
        infos = archive.infolist()
        if not infos or len(infos) > MAX_FILES + 1: raise ValueError('Archive file count exceeds the backup limit.')
        names = [i.filename for i in infos]
        if len(set(n.casefold() for n in names)) != len(names): raise ValueError('Duplicate archive members are not permitted.')
        if 'manifest.json' not in names: raise ValueError('This is not a complete private application backup.')
        if sum(i.file_size for i in infos) > MAX_EXPANDED_BYTES: raise ValueError('Expanded archive exceeds 4 GiB.')
        for info in infos:
            if info.filename != 'manifest.json': _member_kind(info.filename)
            mode = info.external_attr >> 16
            if info.is_dir() or stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in {0, stat.S_IFREG} or info.flag_bits & 1 or info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                raise ValueError('Links, special files and encrypted members are not permitted.')
            limit = MAX_JSON_BYTES if info.filename == 'manifest.json' or _member_kind(info.filename) == 'json' else MAX_MEDIA_BYTES
            if info.file_size > limit or info.file_size > max(1024**2, info.compress_size * 200):
                raise ValueError('An archive member exceeds size or compression limits.')
        raw = archive.read('manifest.json')
        manifest = _decode(raw)
        if not isinstance(manifest, dict) or set(manifest) != {'format', 'schema_version', 'snapshot_id', 'created_at', 'entries', 'media', 'omissions', 'consistency'} or manifest.get('format') != 'line-dance-private-backup' or manifest.get('schema_version') != 1:
            raise ValueError('Unsupported private backup format.')
        if not TOKEN.fullmatch(str(manifest.get('snapshot_id'))) or not isinstance(manifest['created_at'], str) or len(manifest['created_at']) > 80 or not isinstance(manifest['consistency'], str) or len(manifest['consistency']) > 1000:
            raise ValueError('Invalid backup manifest metadata.')
        entries = manifest['entries']
        if not isinstance(entries, list) or len(entries) > MAX_FILES: raise ValueError('Invalid manifest entries.')
        if any(not isinstance(e, dict) or set(e) != {'path', 'bytes', 'sha256'} for e in entries): raise ValueError('Invalid manifest file fields.')
        if len({e['path'] for e in entries}) != len(entries) or {e['path'] for e in entries} != set(names) - {'manifest.json'}:
            raise ValueError('Archive contents disagree with the selected manifest.')
        documents = {}
        for entry in entries:
            info = archive.getinfo(entry['path'])
            if type(entry['bytes']) is not int or entry['bytes'] != info.file_size or not SHA.fullmatch(str(entry['sha256'])):
                raise ValueError('Invalid manifest file size or hash.')
            digest, count, chunks, header = hashlib.sha256(), 0, [], b''
            kind = _member_kind(entry['path'])
            with archive.open(info) as stream:
                for chunk in iter(lambda: stream.read(1024**2), b''):
                    count += len(chunk)
                    if count > info.file_size: raise ValueError('Archive member exceeded its declared size.')
                    if not header: header = chunk[:32]
                    digest.update(chunk)
                    if kind == 'json': chunks.append(chunk)
            if count != entry['bytes'] or digest.hexdigest() != entry['sha256']: raise ValueError('Backup file failed its integrity check.')
            if kind == 'json': documents[entry['path']] = _validate_document(entry['path'], b''.join(chunks))
            elif not _media_header(PurePosixPath(entry['path']).suffix, header): raise ValueError('Unsupported media signature in backup.')
        if not {'settings.json', 'browser-preferences.json'} <= documents.keys(): raise ValueError('Backup preferences are missing.')
        media = manifest['media']
        if not isinstance(media, list) or len(media) > MAX_FILES: raise ValueError('Invalid media manifest.')
        originals, included = set(), set()
        for row in media:
            if not isinstance(row, dict) or set(row) != {'original_path', 'archive_path', 'kind', 'bytes', 'reason'} or not isinstance(row['original_path'], str) or not 0 < len(row['original_path']) <= 4096 or row['original_path'] in originals:
                raise ValueError('Invalid or duplicate media reference.')
            originals.add(row['original_path'])
            if row['kind'] not in {'music', 'photos', 'videos', 'other'} or row['bytes'] is not None and (type(row['bytes']) is not int or row['bytes'] < 0): raise ValueError('Invalid media information.')
            if row['reason'] not in {'included', 'external_path_relink_required', 'relative_path_relink_required', 'unsupported_or_generated_file', 'generated_or_unowned_subdirectory', 'missing_file', 'not_selected'}: raise ValueError('Invalid media omission reason.')
            if row['archive_path'] is not None:
                name = row['archive_path']
                if not isinstance(name, str) or name not in names or _member_kind(name) != 'media' or row['reason'] != 'included' or row['bytes'] != archive.getinfo(name).file_size or MEDIA_EXT[PurePosixPath(name).suffix] != row['kind']:
                    raise ValueError('Media reference disagrees with its archived file.')
                included.add(name)
            elif row['reason'] == 'included': raise ValueError('Included media has no archived file.')
        if included != {n for n in names if n != 'manifest.json' and _member_kind(n) == 'media'}: raise ValueError('Unreferenced media file in archive.')
        if not isinstance(manifest['omissions'], list) or len(manifest['omissions']) > 100 or any(not isinstance(x, str) or len(x) > 2000 for x in manifest['omissions']): raise ValueError('Invalid omission list.')
        _cross_check(documents, entries)
        return archive, manifest, _sha(raw), documents
    except (zipfile.BadZipFile, KeyError, TypeError, OverflowError, RecursionError) as exc:
        if 'archive' in locals(): archive.close()
        raise ValueError('The backup archive is malformed or incomplete.') from exc
    except BaseException:
        if 'archive' in locals(): archive.close()
        raise


def _cross_check(documents, entries):
    projects = {PurePosixPath(name).parts[1] for name in documents if name.startswith('projects/')}
    for pid in projects:
        if 'projects/' + pid + '/project.json' not in documents: raise ValueError('A project is missing its current document.')
    for name, value in documents.items():
        if name.startswith('projects/') and not '/versions/' in name:
            for version in value.get('workspace_versions', []):
                if not isinstance(version, dict) or 'projects/' + PurePosixPath(name).parts[1] + '/versions/' + str(version.get('version_id')) + '.json' not in documents:
                    raise ValueError('A project refers to a missing named version.')
    files = {e['path']: e for e in entries}
    library = documents.get('stores/library.json')
    if library:
        for row in library['tables']['media']:
            name = 'library/media/' + row['filename']
            if name in files:
                metadata = _decode(row['payload'].encode())
                if metadata['sha256'] != files[name]['sha256'] or metadata['bytes'] != files[name]['bytes']:
                    raise ValueError('Library attachment bytes disagree with saved metadata.')


def _summary(manifest, documents):
    library = documents.get('stores/library.json', {}).get('tables', {})
    phrases = documents.get('stores/phrases.json', {}).get('tables', {})
    teaching = documents.get('tools/state.json', {})
    return {'projects': sum(name.endswith('/project.json') for name in documents),
            'named_versions': sum('/versions/' in name for name in documents),
            'last_good_copies': sum(name.endswith('/project.last-good.json') for name in documents),
            'library_records': len(library.get('records', [])), 'library_versions': len(library.get('versions', [])),
            'library_media_records': len(library.get('media', [])), 'phrases': len(phrases.get('records', [])),
            'phrase_versions': len(phrases.get('versions', [])), 'teaching_dances': len(teaching.get('dances', [])),
            'setlists': len(teaching.get('setlists', [])), 'events': len(teaching.get('events', [])),
            'media_included': sum(row['archive_path'] is not None for row in manifest['media']),
            'media_to_relink': sum(row['archive_path'] is None for row in manifest['media']),
            'expanded_bytes': sum(e['bytes'] for e in manifest['entries'])}


def validate_archive(path):
    archive, manifest, digest, documents = _inspect_archive(path)
    archive.close()
    return {'manifest_digest': digest, 'archive_bytes': Path(path).stat().st_size,
            'summary': _summary(manifest, documents), 'media': manifest['media'],
            'omissions': manifest['omissions'], 'consistency': manifest['consistency'],
            'private_backup': True, 'credentials_included': False,
            'restore_behavior': 'Restore into a new separate profile. Current data is unchanged.'}


def finish_import(token):
    folder, meta = _job(token, 'import')
    try:
        result = validate_archive(folder / 'backup.zip')
        meta['manifest_digest'] = result['manifest_digest']
        (folder / 'job.json').write_bytes(_json(meta))
        return {**result, 'token': token, 'expires_in_seconds': JOB_SECONDS}
    except BaseException:
        _remove_owned(folder, job_root()); raise


def preview_import_bytes(payload):
    """Convenience for bounded tests/callers; HTTP uploads stream to disk."""
    if len(payload) > MAX_ARCHIVE_BYTES: raise ValueError('Backup archives must be at most 2 GiB.')
    token, folder = new_import()
    (folder / 'backup.zip').write_bytes(payload)
    return finish_import(token)


def download_export(token, digest, confirmed):
    if confirmed is not True: raise ValueError('Confirm the private backup download after reviewing its contents.')
    folder, _ = _job(token, 'export', digest)
    result = validate_archive(folder / 'backup.zip')
    if result['manifest_digest'] != digest: raise Conflict('The backup changed; preview it again.')
    return folder / 'backup.zip'


def _document_nodes(value):
    yield value
    if isinstance(value, dict) and isinstance(value.get('tables'), dict):
        for rows in value['tables'].values():
            for row in rows:
                for key in ('payload', 'changes'):
                    if isinstance(row.get(key), str): yield _decode(row[key].encode())


def _sanitize_document(value):
    value = _clean_secrets(value)
    if isinstance(value, dict) and isinstance(value.get('tables'), dict):
        for rows in value['tables'].values():
            for row in rows:
                for key in ('payload', 'changes'):
                    if isinstance(row.get(key), str):
                        row[key] = _json(_clean_secrets(_decode(row[key].encode()))).decode().strip()
    return value


def _relocate(value, media, destination):
    value = deepcopy(value)
    for obj, key, original in _path_fields(value):
        target = media.get(original)
        obj[key] = str(destination / target) if target else '' if key == 'local_path' else None
    if isinstance(value, dict) and isinstance(value.get('tables'), dict):
        for rows in value['tables'].values():
            for row in rows:
                for key in ('payload', 'changes'):
                    if isinstance(row.get(key), str): row[key] = _json(_relocate(_decode(row[key].encode()), media, destination)).decode().strip()
    if isinstance(value, dict) and 'version_id' in value and 'content_hash' in value:
        value['content_hash'] = project._digest({k: v for k, v in value.items() if k != 'content_hash'})
    return value


def _write_database(path, tables, ddl, schema):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(ddl)
        for table, columns in schema.items():
            conn.executemany('INSERT INTO "' + table + '" (' + ','.join('"' + c + '"' for c in columns) + ') VALUES (' + ','.join('?' for _ in columns) + ')',
                             [[row[c] for c in columns] for row in tables[table]])
        conn.commit()
        if conn.execute('PRAGMA integrity_check').fetchone() != ('ok',): raise ValueError('Restored database failed its integrity check.')
        if _table_dump(conn, schema)['tables'] != tables: raise ValueError('Restored database did not preserve its records.')
    finally:
        conn.close()


def _launcher(destination):
    """Generate trusted code locally. No executable archive member is accepted."""
    app = _app_root()
    script = '''from pathlib import Path
import json, os, socket, sys, threading, webbrowser
root = Path(__file__).resolve().parent
os.environ['LINE_DANCE_DATA_DIR'] = str(root)
for key, child in {'LINE_DANCE_PROJECTS_DIR':'projects', 'LINE_DANCE_LIBRARY_DIR':'library', 'LINE_DANCE_TOOLS_DIR':'tools', 'LINE_DANCE_PHRASE_DIR':'phrases'}.items():
    os.environ[key] = str(root / child)
app = Path(APP_PATH)
os.chdir(app)
sys.path.insert(0, str(app))
import server, uvicorn
from engine import database, project
project.ensure_dirs()
database.initialize_database()
# Keep a stable origin so browser recovery and preferences survive restarts.
# A short exclusive creation lock prevents two first launches choosing ports.
lockpath = root / '.profile-launch.lock'
try:
    lock = lockpath.open('x')
except FileExistsError:
    raise SystemExit('Another launch is preparing this profile. Try again shortly. If it stopped unexpectedly, remove .profile-launch.lock from this restored profile only.')
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    portfile = root / 'profile-port.json'
    port = 0
    if portfile.exists():
        port = json.loads(portfile.read_text(encoding='utf-8'))['port']
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError('The saved restored-profile port is invalid.')
    try:
        sock.bind(('127.0.0.1', port))
    except OSError:
        raise SystemExit('This restored profile uses port ' + str(port) + ', which is already in use. Close its earlier app window/server or the program using that port, then open this launcher again. No other profile was opened.')
    sock.listen(128)
    port = sock.getsockname()[1]
    if not portfile.exists():
        with portfile.open('x', encoding='utf-8') as output:
            json.dump({'port': port}, output)
            output.flush(); os.fsync(output.fileno())
finally:
    lock.close(); lockpath.unlink(missing_ok=True)
threading.Timer(1.2, lambda: webbrowser.open('http://127.0.0.1:' + str(port) + '/dance')).start()
uvicorn.Server(uvicorn.Config(server.app, host='127.0.0.1', port=port)).run(sockets=[sock])
'''.replace('APP_PATH', repr(str(app)))
    (destination / 'open-restored-profile.py').write_text(script, encoding='utf-8')
    def quote(path):
        text = str(path)
        if any(c in text for c in ('"', '\r', '\n')): raise ValueError('The local application path cannot be used in a launcher.')
        return '"' + text.replace('%', '%%') + '"'
    batch = '@echo off\r\nsetlocal DisableDelayedExpansion\r\nchcp 65001 >nul\r\n' + quote(sys.executable) + ' -I -B ' + quote(destination / 'open-restored-profile.py') + '\r\nif errorlevel 1 pause\r\n'
    return batch.encode('utf-8')


def restore(token, digest, confirmed):
    if confirmed is not True: raise ValueError('Confirm restore into a new separate data profile.')
    with _LOCK:
        folder, meta = _job(token, 'import', digest)
        if meta.get('result'):
            previous = meta['result']
            if PROFILE.fullmatch(str(previous.get('profile_id'))):
                report_path = _owned(profile_root() / previous['profile_id'] / 'restore-report.json', profile_root())
                if report_path.exists() and _decode(_read(report_path, report_path.parent)).get('source_manifest_digest') == digest:
                    return previous
            # A receipt can precede a failed final rename. It is not success
            # until the verified destination and matching report exist.
            meta.pop('result')
        try:
            lock = (folder / '.restore.lock').open('x')
        except FileExistsError as exc:
            raise Conflict('This restore is already running. Preview the archive again if an earlier app session stopped.') from exc
        destination = staging = None
        archive = None
        try:
            archive, manifest, actual, documents = _inspect_archive(folder / 'backup.zip')
            if actual != digest: raise Conflict('The selected backup changed after preview.')
            root = _no_links(profile_root()); root.mkdir(parents=True, exist_ok=True)
            profile_id = 'restored-' + uuid.uuid4().hex
            destination = root / profile_id
            staging = root / ('.restoring-' + uuid.uuid4().hex)
            staging.mkdir()
            media = {row['original_path']: row['archive_path'] for row in manifest['media']}
            relocated = {name: _relocate(value, media, destination) for name, value in documents.items()}
            for name, value in relocated.items():
                raw = _json(value); _validate_document(name, raw)
                if name.startswith('stores/'): continue
                path = _owned(staging / name, staging); path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
                if path.read_bytes() != raw: raise OSError('Restored metadata could not be verified.')
            for entry in manifest['entries']:
                if _member_kind(entry['path']) != 'media': continue
                path = _owned(staging / entry['path'], staging); path.parent.mkdir(parents=True, exist_ok=True)
                h = hashlib.sha256()
                with archive.open(entry['path']) as source, path.open('xb') as output:
                    for block in iter(lambda: source.read(1024**2), b''):
                        h.update(block); output.write(block)
                    output.flush(); os.fsync(output.fileno())
                if path.stat().st_size != entry['bytes'] or h.hexdigest() != entry['sha256']: raise ValueError('Restored media failed verification.')
            if 'stores/library.json' in relocated:
                _write_database(staging / 'library/library.sqlite3', relocated['stores/library.json']['tables'], LIBRARY_DDL, LIBRARY_TABLES)
            if 'stores/phrases.json' in relocated:
                schema = {k: LIBRARY_TABLES[k] for k in ('records', 'versions')}
                _write_database(staging / 'phrases/phrases.sqlite3', relocated['stores/phrases.json']['tables'],
                                'CREATE TABLE records(id TEXT PRIMARY KEY,version INTEGER NOT NULL,payload TEXT NOT NULL); CREATE TABLE versions(record_id TEXT,version INTEGER,payload TEXT NOT NULL,PRIMARY KEY(record_id,version));', schema)
            if 'stores/preferences.json' in relocated:
                _write_database(staging / 'preferences/browser.sqlite3', {'favorites': [{'key': key} for key in relocated['stores/preferences.json']['favorites']]}, 'CREATE TABLE favorites(key TEXT PRIMARY KEY);', {'favorites': ('key',)})
            _cross_check(relocated, manifest['entries'])
            report = {'schema_version': 1, 'source_manifest_digest': digest,
                      'restored_at': datetime.now(timezone.utc).isoformat(),
                      'summary': _summary(manifest, documents), 'media': manifest['media'],
                      'omissions': manifest['omissions'], 'credentials_restored': False,
                      'path_relocation': 'Owned included media now points into this new profile; omitted paths were cleared and are listed for relinking. Named version content hashes were recalculated after path relocation.'}
            (staging / 'restore-report.json').write_bytes(_json(report))
            # Launcher embeds the final path, not the transient staging folder.
            launcher = _launcher(staging)
            script_path = staging / 'open-restored-profile.py'
            launcher = launcher.replace(str(script_path).replace('%', '%%').encode(), str(destination / script_path.name).replace('%', '%%').encode())
            (staging / 'Open restored Line Dance Creator.cmd').write_bytes(launcher)
            if destination.exists(): raise Conflict('The new profile folder already exists; retry restore.')
            result = {'profile_id': profile_id, 'restored_folder': str(destination), 'summary': report['summary'],
                      'current_data_unchanged': True, 'launcher_url': '/api/creator/backup/restored/' + profile_id + '/launcher',
                      'report_url': '/api/creator/backup/restored/' + profile_id + '/report',
                      'message': 'Restored separately. Your current data is unchanged. Download and open the restored-profile launcher to use this copy. Relink omitted media in Music or your library.'}
            meta['result'] = result
            (folder / 'job.json').write_bytes(_json(meta))
            # Publish only after the entire profile and retry receipt exist.
            # No fallible disk writes remain after the final directory rename.
            os.rename(staging, destination)
            staging = None
            return result
        finally:
            if archive: archive.close()
            lock.close()
            (folder / '.restore.lock').unlink(missing_ok=True)
            if staging is not None and staging.exists(): _remove_owned(staging, profile_root())


def restored_file(profile_id, name):
    if not PROFILE.fullmatch(str(profile_id)) or name not in {'Open restored Line Dance Creator.cmd', 'restore-report.json'}:
        raise ValueError('Invalid restored profile request.')
    path = _owned(profile_root() / profile_id / name, profile_root())
    if not path.is_file(): raise FileNotFoundError('Restored profile file not found.')
    return path


def profile_context():
    from . import browser_preferences
    roots = [Path(project.PROJECTS_DIR), library_store.directory(), instructor_tools.directory(), browser_preferences.directory()]
    try:
        from . import phrase_store
        roots.append(phrase_store.directory())
    except ImportError:
        pass
    identity = _sha(_json([os.path.normcase(os.path.abspath(path)) for path in roots]))[:24]
    data = os.environ.get('LINE_DANCE_DATA_DIR')
    preferences = {}
    if data:
        path = Path(data).absolute() / 'browser-preferences.json'
        if path.exists(): preferences = _safe_browser(_decode(_read(path, path.parent)))
    return {'profile_id': identity, 'browser_preferences': preferences,
            'can_migrate_legacy_browser_state': not any(os.environ.get(key) for key in ('LINE_DANCE_DATA_DIR', 'LINE_DANCE_PROJECTS_DIR', 'LINE_DANCE_LIBRARY_DIR', 'LINE_DANCE_TOOLS_DIR', 'LINE_DANCE_PHRASE_DIR')),
            'data_label': str(Path(data).absolute()) if data else 'Original local workspace',
            'limits': {'archive_bytes': MAX_ARCHIVE_BYTES, 'expanded_bytes': MAX_EXPANDED_BYTES, 'media_file_bytes': MAX_MEDIA_BYTES}}
