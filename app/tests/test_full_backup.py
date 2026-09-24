"""Private multi-store recovery against synthetic, isolated application data."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import wave
import zipfile
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import full_backup as backup
from engine import project, library_store, instructor_tools, phrase_store, browser_preferences, settings, steps
from backup_api import router


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    live = tmp_path / 'live'; live.mkdir()
    monkeypatch.setenv('LINE_DANCE_DATA_DIR', str(live))
    monkeypatch.setenv('LINE_DANCE_TOOLS_DIR', str(live / 'tools'))
    monkeypatch.setattr(project, 'PROJECTS_DIR', str(live / 'projects'))
    monkeypatch.setattr(library_store, 'LIBRARY_DIR', live / 'library')
    monkeypatch.setattr(phrase_store, 'PHRASE_DIR', live / 'phrases')
    monkeypatch.setattr(browser_preferences, 'PREFERENCES_DIR', live / 'preferences')
    monkeypatch.setattr(settings, 'SETTINGS_FILE', str(live / 'settings.json'))
    monkeypatch.setattr(steps, 'CUSTOM_MOVES_PATH', str(live / 'custom-moves.json'))
    monkeypatch.setattr(backup, 'JOB_ROOT', tmp_path / 'jobs')
    monkeypatch.setattr(backup, 'PROFILE_ROOT', tmp_path / 'restored')
    return live


def audio(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as stream:
        stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(8000)
        stream.writeframes(b'\0\0' * 80)
    return path


def png():
    stream = io.BytesIO(); Image.new('RGB', (5, 5), 'blue').save(stream, format='PNG')
    return stream.getvalue()


@pytest.fixture
def populated(isolated):
    one = project.create_project('First dance')
    two = project.create_project('Second dance')
    pid = one['id']
    music = audio(isolated / 'projects' / pid / 'recordings' / 'owned.wav')
    external = audio(isolated.parent / 'external.wav')
    one['song']['path'] = str(music)
    one['song']['filename'] = music.name
    one['draft']['song'] = copy.deepcopy(one['song'])
    one['lyrics_raw'] = 'PRIVATE LYRICS'
    one['draft']['lyrics_raw'] = 'PRIVATE LYRICS'
    one['accepted_choreography'] = {'private_accepted_marker': 'KEEP ACCEPTED'}
    one['recording_history'] = [{'song': {'path': str(external), 'title': 'Earlier'}, 'music_map': {'bpm': 96}}]
    project.save_project(pid, one)
    milestone = project.create_version(pid, 'Class-ready version', one['document_revision'])
    current = project.load_project(pid)
    current['draft']['lyrics_raw'] = 'LATER DRAFT'
    project.save_project(pid, current)
    fields = {'name': 'My move', 'explanation': 'My private teaching explanation.', 'duration_counts': '8'}
    record = library_store.create_record(fields)
    attached = library_store.attach_media(record['id'], 1, 'photo.png', png())
    changed = library_store.update_record(record['id'], 2, {'name': 'Renamed move'})
    phrase = phrase_store.create('My phrase', [{'id': 'm1', 'name': 'Written eight', 'duration_counts': '8', 'events': [{'duration_counts': '8', 'text': 'My sequence', 'support_before': 'unknown', 'support_after': 'unknown'}]}], 'PRIVATE PHRASE')
    phrase_store.update(phrase['id'], 1, {'favorite': True, 'name': 'Renamed phrase'})
    browser_preferences.set_favorite('user:' + record['id'], True)
    teaching = {'schema_version': 1, 'dances': [{'id': 'd1', 'title': 'First', 'project_id': pid,
        'private_notes': 'PRIVATE NOTES', 'learning_status': 'learning', 'favorite': True,
        'checklist': [{'id': 'c1', 'label': 'Practice the tag', 'done': True}],
        'practice_history': [{'id': 'p1', 'at': '2026-09-04T09:00:00-04:00', 'duration_minutes': 15}],
        'recordings': [{'id': 'r1', 'title': 'First recording', 'local_path': str(music), 'music_map': {'bpm': 112}}]}],
        'setlists': [{'id': 's1', 'title': 'Thursday class', 'private_notes': 'PRIVATE PLAN', 'items': [{'dance_id': 'd1', 'recording_id': 'r1', 'duration_minutes': 10}]}],
        'events': [{'id': 'e1', 'title': 'Class', 'start': '2026-11-01T18:00:00', 'end': '2026-11-01T19:00:00', 'timezone': 'America/New_York', 'rrule': 'FREQ=WEEKLY;COUNT=3'}]}
    instructor_tools.save_state(teaching, 0)
    instructor_tools.save_state(instructor_tools.get_state(), 1)
    steps.save_custom_move({'name': 'My legacy step', 'counts': 2, 'rotation': 0, 'start': 'R', 'end': 'R', 'instructions': 'Step and step.', 'level': 'B'})
    (isolated / 'settings.json').write_text(json.dumps({'ai': {'enabled': True, 'provider': 'openai_compatible', 'model': 'user-model', 'base_url': 'https://example.com?api_key=URL-SECRET', 'api_key_protected': 'PROTECTED-SECRET', 'api_key': 'PLAIN-SECRET'}, 'unexpected': {'password': 'NESTED-SECRET'}}))
    # Arbitrary files and generated audio are intentionally not bulk copied.
    (isolated / 'do-not-copy.txt').write_text('PRIVATE ARBITRARY FILE')
    repair = audio(isolated / 'projects' / pid / 'repair' / 'cache.wav')
    current = project.load_project(pid); current['repair'] = {'output_path': str(repair)}
    project.save_project(pid, current)
    return {'root': isolated, 'pid': pid, 'other': two['id'], 'music': music, 'external': external,
            'move': record['id'], 'media': attached['attachment'], 'phrase': phrase['id'], 'version': milestone['version']['version_id']}


def prepare(**options):
    result = backup.create_export(options, {'mode': 'advanced', 'resources': [{'name': 'School', 'url': 'https://example.com/steps?token=OMIT'}], 'lastProject': 'first-dance'})
    path = backup.download_export(result['token'], result['manifest_digest'], True)
    return result, path


def roundtrip(path):
    preview = backup.preview_import_bytes(path.read_bytes())
    return preview, backup.restore(preview['token'], preview['manifest_digest'], True)


def files(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and p.suffix != '.lock'}


def rows(path, table):
    with sqlite3.connect(path) as conn:
        return conn.execute('SELECT * FROM ' + table).fetchall()


def test_complete_multistore_restore_preserves_history_and_media(populated):
    before = files(populated['root'])
    preview, path = prepare(include_music=True, include_photos=True)
    assert preview['summary']['projects'] == 2
    assert preview['summary']['library_versions'] == 3
    assert preview['summary']['phrase_versions'] == 2
    assert preview['summary']['media_included'] == 2
    selected, result = roundtrip(path)
    restored = Path(result['restored_folder'])
    assert result['current_data_unchanged'] and files(populated['root']) == before
    assert rows(restored / 'library/library.sqlite3', 'records') == rows(populated['root'] / 'library/library.sqlite3', 'records')
    assert rows(restored / 'phrases/phrases.sqlite3', 'versions') == rows(populated['root'] / 'phrases/phrases.sqlite3', 'versions')
    assert rows(restored / 'preferences/browser.sqlite3', 'favorites') == [('user:' + populated['move'],)]
    project_root = restored / 'projects' / populated['pid']
    current = json.loads((project_root / 'project.json').read_text())
    assert current['accepted_choreography']['private_accepted_marker'] == 'KEEP ACCEPTED'
    assert current['draft']['lyrics_raw'] == 'LATER DRAFT'
    assert Path(current['song']['path']).is_relative_to(restored)
    assert Path(current['song']['path']).read_bytes() == populated['music'].read_bytes()
    assert current['recording_history'][0]['song']['path'] is None
    assert current['repair']['output_path'] is None
    saved = json.loads((project_root / 'versions' / (populated['version'] + '.json')).read_text())
    assert saved['draft']['lyrics_raw'] == 'PRIVATE LYRICS'
    assert saved['content_hash'] == project._digest({k: v for k, v in saved.items() if k != 'content_hash'})
    assert Path(saved['draft']['song']['path']).is_relative_to(restored)
    tools = json.loads((restored / 'tools/state.json').read_text())
    assert tools['dances'][0]['private_notes'] == 'PRIVATE NOTES'
    assert tools['dances'][0]['practice_history'][0]['duration_minutes'] == 15
    assert tools['events'][0]['timezone'] == 'America/New_York'
    assert Path(tools['dances'][0]['recordings'][0]['local_path']).is_relative_to(restored)
    assert (restored / 'tools/state.backup.json').exists()
    assert (restored / 'custom-moves.json').exists()
    assert backup.restore(selected['token'], selected['manifest_digest'], True) == result
    compile((restored / 'open-restored-profile.py').read_text(), 'launcher', 'exec')
    assert '.restoring-' not in (restored / 'Open restored Line Dance Creator.cmd').read_text()
    assert 'profile-port.json' in (restored / 'open-restored-profile.py').read_text()


def test_metadata_only_never_reads_external_or_omitted_media(populated, monkeypatch):
    original = Path.open
    def guarded(path, *args, **kwargs):
        if path == populated['external'] or path == populated['music']:
            raise AssertionError('Media contents were read when omitted')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', guarded)
    preview, path = prepare()
    assert preview['summary']['media_included'] == 0
    assert any(m['reason'] == 'external_path_relink_required' for m in preview['media'])
    _, result = roundtrip(path)
    restored = Path(result['restored_folder'])
    current = json.loads((restored / 'projects' / populated['pid'] / 'project.json').read_text())
    assert current['song']['path'] is None
    assert not list((restored / 'library').glob('media/*'))
    assert len(rows(restored / 'library/library.sqlite3', 'media')) == 1


def test_secrets_and_arbitrary_files_are_excluded(populated):
    _, path = prepare(include_music=True, include_photos=True, include_videos=True)
    with zipfile.ZipFile(path) as archive:
        all_json = b'\n'.join(archive.read(n) for n in archive.namelist() if n.endswith('.json'))
        for secret in (b'PROTECTED-SECRET', b'PLAIN-SECRET', b'URL-SECRET', b'NESTED-SECRET', b'?token=OMIT'):
            assert secret not in all_json
        assert b'PRIVATE LYRICS' in all_json and b'PRIVATE NOTES' in all_json
        assert not any(n.endswith(('.cmd', '.py', '.exe', '.sqlite3')) for n in archive.namelist())
        settings_copy = json.loads(archive.read('settings.json'))
        assert settings_copy['ai']['enabled'] is False and settings_copy['ai']['base_url'] == ''


def test_serialized_history_credentials_are_removed_and_import_rejects_them(populated):
    source = populated['root'] / 'phrases/phrases.sqlite3'
    with sqlite3.connect(source) as conn:
        for table in ('records', 'versions'):
            for rowid, payload in conn.execute('SELECT rowid,payload FROM ' + table).fetchall():
                value = json.loads(payload)
                value['moves'][0]['api_key_protected'] = 'HIDDEN-SERIALIZED-SECRET'
                conn.execute('UPDATE ' + table + ' SET payload=? WHERE rowid=?', (json.dumps(value), rowid))
    _, path = prepare()
    with zipfile.ZipFile(path) as archive:
        assert b'HIDDEN-SERIALIZED-SECRET' not in archive.read('stores/phrases.json')
    # An attacker can recompute hashes, so schema validation must still reject
    # credentials hidden in the inner serialized record/history payloads.
    def add_credentials(members, manifest):
        value = json.loads(members['stores/phrases.json'])
        for table in ('records', 'versions'):
            for row in value['tables'][table]:
                record = json.loads(row['payload'])
                record['moves'][0]['credentials'] = {'private': 'smuggled'}
                row['payload'] = json.dumps(record)
        payload = backup._json(value)
        members['stores/phrases.json'] = payload
        entry = next(e for e in manifest['entries'] if e['path'] == 'stores/phrases.json')
        entry.update(bytes=len(payload), sha256=backup._sha(payload))
    with pytest.raises(ValueError, match='credential'):
        backup.preview_import_bytes(rewrite(path, add_credentials))


def rewrite(path, mutate):
    with zipfile.ZipFile(path) as archive:
        members = {n: archive.read(n) for n in archive.namelist()}
    manifest = json.loads(members['manifest.json'])
    mutate(members, manifest)
    members['manifest.json'] = backup._json(manifest)
    target = io.BytesIO()
    with zipfile.ZipFile(target, 'w') as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    return target.getvalue()


def test_tamper_and_preview_digest_fail_without_restore(populated):
    _, path = prepare()
    corrupt = rewrite(path, lambda members, manifest: members.__setitem__('settings.json', b'{}'))
    with pytest.raises(ValueError, match='integrity|size'): backup.preview_import_bytes(corrupt)
    selected = backup.preview_import_bytes(path.read_bytes())
    with pytest.raises(backup.Conflict): backup.restore(selected['token'], 'f' * 64, True)
    with pytest.raises(ValueError, match='Confirm'): backup.restore(selected['token'], selected['manifest_digest'], False)
    assert not backup.profile_root().exists()


@pytest.mark.parametrize('name', ['../escape.json', '/absolute.json', 'projects/p/../../evil.py', 'projects/p/evil.exe', 'projects/p/project.json:evil', 'settings.json/../bad', 'projects\\p\\project.json', 'launch.py', 'projects/con/project.json'])
def test_unsafe_and_executable_archive_paths_rejected(isolated, name):
    _, path = prepare()
    payload = rewrite(path, lambda members, manifest: members.__setitem__(name, b'bad'))
    with pytest.raises(ValueError): backup.preview_import_bytes(payload)
    assert not backup.profile_root().exists()


def test_duplicate_symlink_and_bomb_members_rejected(isolated):
    _, path = prepare()
    for kind in ('duplicate', 'symlink', 'bomb'):
        out = io.BytesIO()
        with zipfile.ZipFile(path) as source, zipfile.ZipFile(out, 'w') as target:
            for name in source.namelist(): target.writestr(name, source.read(name))
            if kind == 'duplicate': target.writestr('SETTINGS.JSON', b'{}')
            elif kind == 'symlink':
                info = zipfile.ZipInfo('projects/x/project.json'); info.create_system = 3; info.external_attr = (stat.S_IFLNK | 0o777) << 16
                target.writestr(info, b'/elsewhere')
            else: target.writestr('projects/x/project.json', b'0' * (2 * 1024**2), compress_type=zipfile.ZIP_DEFLATED)
        with pytest.raises(ValueError): backup.preview_import_bytes(out.getvalue())


def test_missing_named_version_is_detected(populated):
    file = populated['root'] / 'projects' / populated['pid'] / 'versions' / (populated['version'] + '.json')
    file.unlink()
    with pytest.raises(ValueError, match='missing named version'): prepare()


def test_failure_cleans_staging_and_keeps_live_data(populated, monkeypatch):
    _, path = prepare(include_music=True, include_photos=True)
    selected = backup.preview_import_bytes(path.read_bytes())
    before = files(populated['root'])
    def fail(*args, **kwargs): raise OSError('simulated disk failure')
    monkeypatch.setattr(backup, '_write_database', fail)
    with pytest.raises(OSError): backup.restore(selected['token'], selected['manifest_digest'], True)
    assert list(backup.profile_root().iterdir()) == []
    assert files(populated['root']) == before


def test_final_rename_failure_is_not_a_success_receipt(isolated, monkeypatch):
    _, path = prepare()
    selected = backup.preview_import_bytes(path.read_bytes())
    original = backup.os.rename
    def fail(*args): raise OSError('simulated final rename failure')
    monkeypatch.setattr(backup.os, 'rename', fail)
    with pytest.raises(OSError): backup.restore(selected['token'], selected['manifest_digest'], True)
    assert list(backup.profile_root().iterdir()) == []
    monkeypatch.setattr(backup.os, 'rename', original)
    result = backup.restore(selected['token'], selected['manifest_digest'], True)
    assert (Path(result['restored_folder']) / 'restore-report.json').exists()


def test_source_junction_is_rejected_before_media_read(populated, monkeypatch):
    original = Path.lstat
    class JunctionInfo:
        st_mode = stat.S_IFDIR
        st_file_attributes = 0x400
    def linked(path, *args, **kwargs):
        return JunctionInfo() if path == populated['music'].parent else original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'lstat', linked)
    with pytest.raises(ValueError, match='junction'): prepare(include_music=True)
    assert not backup.profile_root().exists()


def test_traversal_valued_media_path_is_never_opened(populated, monkeypatch):
    root = populated['root'] / 'projects' / populated['pid']
    outside = audio(populated['root'] / 'projects' / 'outside.wav')
    deceptive = str(root / 'recordings' / '..' / '..' / 'outside.wav')
    assert Path(os.path.abspath(deceptive)) == outside
    current = project.load_project(populated['pid'])
    current['song']['path'] = deceptive; current['draft']['song']['path'] = deceptive
    project.save_project(populated['pid'], current)
    original = Path.open
    def guarded(path, *args, **kwargs):
        if os.path.abspath(path) == str(outside): raise AssertionError('Traversal media was opened')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', guarded)
    preview, _ = prepare(include_music=True)
    row = next(row for row in preview['media'] if row['original_path'] == deceptive)
    assert row['archive_path'] is None and row['reason'] == 'external_path_relink_required'
    with pytest.raises(ValueError, match='traversal'):
        backup._owned(root / '..' / 'outside.wav', root)


def test_same_project_ids_restore_twice_into_distinct_profiles(populated):
    _, path = prepare(include_music=True)
    _, one = roundtrip(path); _, two = roundtrip(path)
    assert one['restored_folder'] != two['restored_folder']
    for result in (one, two):
        root = Path(result['restored_folder'])
        document = json.loads((root / 'projects' / populated['pid'] / 'project.json').read_text())
        assert Path(document['song']['path']).is_relative_to(root)


def test_sqlite_snapshot_contains_committed_wal_only(isolated):
    record = library_store.create_record({'name': 'Committed', 'duration_counts': '8'})
    path = isolated / 'library/library.sqlite3'
    conn = sqlite3.connect(path)
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        value = json.loads(conn.execute('SELECT payload FROM records').fetchone()[0])
        value['name'] = 'Committed WAL'; value['version'] = 2
        payload = json.dumps(value)
        conn.execute('INSERT INTO versions VALUES(?,?,?)', (record['id'], 2, payload))
        conn.execute('UPDATE records SET version=2,payload=?', (payload,)); conn.commit()
        conn.execute('UPDATE records SET payload=?', ('uncommitted invalid JSON',))
        preview, archive = prepare()
        assert preview['summary']['library_versions'] == 2
        _, result = roundtrip(archive)
        restored = rows(Path(result['restored_folder']) / 'library/library.sqlite3', 'records')
        assert json.loads(restored[0][2])['name'] == 'Committed WAL'
    finally:
        conn.rollback(); conn.close()


def test_profile_defaults_and_identity_are_derived_from_active_paths(isolated, monkeypatch):
    first = backup.profile_context()
    assert first['can_migrate_legacy_browser_state'] is False
    (isolated / 'browser-preferences.json').write_bytes(backup._json({'mode': 'advanced', 'resources': [], 'lastProject': 'dance'}))
    assert backup.profile_context()['browser_preferences']['mode'] == 'advanced'
    monkeypatch.setattr(project, 'PROJECTS_DIR', str(isolated / 'other-projects'))
    assert backup.profile_context()['profile_id'] != first['profile_id']


def test_api_preview_confirm_and_bounded_upload(isolated):
    app = FastAPI(); app.include_router(router)
    with TestClient(app) as client:
        response = client.post('/api/creator/backup/exports/preview', json={})
        assert response.status_code == 200, response.text
        preview = response.json()
        assert client.get(f"/api/creator/backup/exports/{preview['token']}/download", params={'manifest_digest': preview['manifest_digest']}).status_code == 422
        response = client.get(f"/api/creator/backup/exports/{preview['token']}/download", params={'manifest_digest': preview['manifest_digest'], 'confirmed': 'true'})
        assert response.status_code == 200
        imported = client.post('/api/creator/backup/imports/preview', files={'file': ('backup.zip', response.content, 'application/zip')})
        assert imported.status_code == 200, imported.text
        selected = imported.json()
        restored = client.post(f"/api/creator/backup/imports/{selected['token']}/restore", json={'manifest_digest': selected['manifest_digest'], 'confirmed': True})
        assert restored.status_code == 200, restored.text
        assert client.get(restored.json()['launcher_url']).status_code == 200
        assert client.get('/api/creator/backup/profile').json()['profile_id']
        response = client.post('/api/creator/backup/imports/preview', content=b'x', headers={'content-length': str(backup.MAX_ARCHIVE_BYTES + 65537)})
        assert response.status_code == 413


def test_chunked_request_without_length_is_bounded(isolated, monkeypatch):
    monkeypatch.setattr(backup, 'MAX_ARCHIVE_BYTES', 1024)
    app = FastAPI(); app.include_router(router)
    with TestClient(app) as client:
        def chunks():
            yield b'--test\r\nContent-Disposition: form-data; name="file"; filename="x.zip"\r\nContent-Type: application/zip\r\n\r\n'
            for _ in range(10): yield b'x' * 10000
            yield b'\r\n--test--\r\n'
        result = client.post('/api/creator/backup/imports/preview', content=chunks(), headers={'Content-Type': 'multipart/form-data; boundary=test'})
        assert result.status_code == 413


def test_trusted_launcher_preserves_port_and_refuses_occupied_origin(isolated, monkeypatch):
    import socket
    import threading
    from engine import database
    destination = isolated.parent / 'launcher-profile'; destination.mkdir()
    backup._launcher(destination)
    script = (destination / 'open-restored-profile.py').read_text()
    ports, timers = [], []
    class Socket:
        busy = False
        def __init__(self, *_): pass
        def bind(self, target):
            if self.busy: raise OSError('occupied')
            self.port = target[1] or 25432
        def listen(self, *_): pass
        def getsockname(self): return ('127.0.0.1', self.port)
    class Server:
        def __init__(self, config): self.config = config
        def run(self, sockets): ports.append(sockets[0].port)
    class Timer:
        def __init__(self, *args): pass
        def start(self): timers.append(True)
    monkeypatch.setattr(socket, 'socket', Socket)
    monkeypatch.setattr(threading, 'Timer', Timer)
    monkeypatch.setitem(sys.modules, 'server', SimpleNamespace(app=object()))
    monkeypatch.setitem(sys.modules, 'uvicorn', SimpleNamespace(Config=lambda *a, **kw: kw, Server=Server))
    monkeypatch.setattr(database, 'initialize_database', lambda: None)
    monkeypatch.setattr(project, 'ensure_dirs', lambda: None)
    monkeypatch.setattr(os, 'chdir', lambda *_: None)
    monkeypatch.setattr(sys, 'path', list(sys.path))
    for key in ('LINE_DANCE_DATA_DIR', 'LINE_DANCE_PROJECTS_DIR', 'LINE_DANCE_LIBRARY_DIR', 'LINE_DANCE_TOOLS_DIR', 'LINE_DANCE_PHRASE_DIR'):
        monkeypatch.setenv(key, str(isolated))
    for _ in range(2): exec(compile(script, 'launcher', 'exec'), {'__file__': str(destination / 'open-restored-profile.py')})
    assert ports == [25432, 25432] and len(timers) == 2
    assert json.loads((destination / 'profile-port.json').read_text()) == {'port': 25432}
    Socket.busy = True
    with pytest.raises(SystemExit, match='already in use'):
        exec(compile(script, 'launcher', 'exec'), {'__file__': str(destination / 'open-restored-profile.py')})
    assert len(timers) == 2 and ports == [25432, 25432]
    assert not (destination / '.profile-launch.lock').exists()
