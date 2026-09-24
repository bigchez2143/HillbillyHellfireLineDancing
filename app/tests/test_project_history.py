"""S01 persistence evidence. All data and subprocess storage use pytest tmp_path."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import threading

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import project as store
from engine import steps
from workspace_api import router


@pytest.fixture
def projects(tmp_path, monkeypatch):
    root = tmp_path / 'projects'
    monkeypatch.setattr(store, 'PROJECTS_DIR', str(root))
    return root


@pytest.fixture
def project(projects):
    return store.create_project('Practice draft')


@pytest.fixture
def client(projects):
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as value:
        yield value


def test_legacy_migration_is_additive_and_keeps_exact_original_bytes(projects):
    directory = projects / 'old-dance'
    directory.mkdir(parents=True)
    legacy = {'id': 'old-dance', 'name': 'Old', 'song': {'title': 'Original'},
              'dance': {'source': 'custom', 'custom': [{'move_id': 'hold', 'lead': 'R'}]},
              'plugin_future_field': {'odd': [1, 'two', None]}, 'lyrics_raw': 'Text'}
    raw = json.dumps(legacy, indent=4).encode()
    (directory / 'project.json').write_bytes(raw)
    document = store.load_project('old-dance')
    assert document['schema_version'] == 1
    assert document['document_revision'] == 0
    assert document['draft']['editor']['moves'] == legacy['dance']['custom']
    assert (directory / 'project.json').read_bytes() == raw
    document['lyrics_raw'] = 'Edited'
    store.save_project('old-dance', document)
    assert (directory / 'project.pre-schema-1.json').read_bytes() == raw
    assert document['plugin_future_field'] == legacy['plugin_future_field']
    document['lyrics_raw'] = 'Edited again'
    store.save_project('old-dance', document)
    assert (directory / 'project.pre-schema-1.json').read_bytes() == raw
    assert store.load_project('old-dance')['draft']['lyrics_raw'] == 'Edited again'


@pytest.mark.parametrize('schema', [2, '1', True, -1])
def test_unsupported_schema_never_silently_uses_older_backup(project, schema):
    pid = project['id']
    store.save_project(pid, project)
    path = Path(store._path(pid))
    value = json.loads(path.read_text())
    value['schema_version'] = schema
    raw = json.dumps(value).encode()
    path.write_bytes(raw)
    with pytest.raises(store.UnsupportedSchema):
        store.load_project(pid)
    with pytest.raises(store.UnsupportedSchema):
        store.save_project(pid, project)
    assert path.read_bytes() == raw


def test_complete_draft_round_trip_keeps_accepted_dance(project):
    pid = project['id']
    project['dance'] = {'source': 'custom', 'custom': [{'move_id': 'hold', 'lead': 'R'}], 'counts': 1}
    store.save_project(pid, project)
    accepted = copy.deepcopy(project['dance'])
    draft = {'editor': {'moves': [], 'counts': 40, 'wall': '4', 'turn_dir': 'R'},
             'choreography': {'parts': [{'moves': [{'move_id': 'new-description', 'text': 'Incomplete'}]}]},
             'sections': [{'label': 'Verse', 'start': 3.1, 'end': 12.4}],
             'lyrics_raw': 'Multiline\nlyrics', 'sheet_meta': {'dance_title': 'Print me'},
             'tutorial': {'segments': [{'id': 's1', 'confirmed': True}]},
             'attachments': [{'id': 'local-photo', 'path': 'media/photo.png'}],
             'music_map': {'first_count': 3.1}, 'future_plugin': {'preserve': True}}
    result = store.save_workspace(pid, draft, project['document_revision'])
    reopened = store.get_workspace(pid)
    for key, value in draft.items():
        assert reopened['draft'][key] == value
    assert reopened['accepted_dance'] == accepted
    assert result['saved_at'] and result['document_revision'] > project['document_revision']
    assert reopened['snapshot_issues']['draft'][0]['move_id'] == 'new-description'
    # Older clients cannot erase fields they do not understand by omission.
    again = store.save_workspace(pid, {'lyrics_raw': ''}, reopened['document_revision'])
    assert again['draft']['future_plugin'] == {'preserve': True}
    assert again['draft']['lyrics_raw'] == ''


def test_old_endpoint_updates_keep_draft_choreography_and_new_audio_identity(project):
    pid = project['id']
    store.save_workspace(pid, {'choreography': {'parts': ['keep']}, 'editor': {'moves': []}}, project['document_revision'])
    old_endpoint = store.load_project(pid)
    old_endpoint['song'].update(path='new-recording.wav', filename='new-recording.wav')
    old_endpoint['analysis'] = {'bpm': 121.5}
    old_endpoint['sections'] = [{'label': 'User section'}]
    store.save_project(pid, old_endpoint)
    current = store.get_workspace(pid)
    assert current['draft']['choreography'] == {'parts': ['keep']}
    assert current['draft']['analysis'] == {'bpm': 121.5}
    assert current['draft']['sections'] == [{'label': 'User section'}]
    result = store.save_workspace(pid, {'song': {'title': 'Renamed', 'path': 'stale.wav', 'filename': None}}, current['document_revision'])
    assert result['draft']['song']['path'] == 'new-recording.wav'
    assert result['draft']['song']['filename'] == 'new-recording.wav'
    assert result['draft']['song']['title'] == 'Renamed'


def test_legacy_load_save_revisions_conflict_and_update_callers(project):
    pid = project['id']
    first, stale = store.load_project(pid), store.load_project(pid)
    first['name'] = 'Winner'
    store.save_project(pid, first)
    first['name'] = 'Same caller again'
    store.save_project(pid, first)
    stale['name'] = 'Lost update'
    with pytest.raises(store.RevisionConflict) as conflict:
        store.save_project(pid, stale)
    assert conflict.value.current_revision == first['document_revision']
    assert store.load_project(pid)['name'] == 'Same caller again'
    omitted_token = dict(first)
    del omitted_token['document_revision']
    with pytest.raises(store.RevisionConflict):
        store.save_project(pid, omitted_token)


def test_out_of_band_same_revision_change_is_detected(project):
    pid = project['id']
    loaded = store.load_project(pid)
    path = Path(store._path(pid))
    value = json.loads(path.read_text())
    value['name'] = 'External edit without revision increment'
    path.write_text(json.dumps(value))
    loaded['name'] = 'Clobber'
    with pytest.raises(store.RevisionConflict):
        store.save_project(pid, loaded)


def test_competing_threads_have_one_winner(project):
    pid, revision = project['id'], project['document_revision']
    barrier = threading.Barrier(2)
    def writer(label):
        barrier.wait(timeout=5)
        try:
            store.save_workspace(pid, {'lyrics_raw': label}, revision)
            return label
        except store.RevisionConflict:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(writer, ['first', 'second']))
    assert results.count('conflict') == 1
    assert store.load_project(pid)['lyrics_raw'] in results
    assert store.load_project(pid)['document_revision'] == revision + 1


@pytest.mark.parametrize('failure', ['replace', 'fsync'])
def test_failed_save_keeps_current_file_revision_and_no_temporary_file(project, monkeypatch, failure):
    pid = project['id']
    path = Path(store._path(pid))
    original = path.read_bytes()
    revision = project['document_revision']
    if failure == 'replace':
        real_replace = os.replace
        def replace_file(source, destination):
            if os.fspath(destination) == store._path(pid):
                raise OSError('simulated disk failure')
            return real_replace(source, destination)
        monkeypatch.setattr(store.os, 'replace', replace_file)
    else:
        monkeypatch.setattr(store.os, 'fsync', lambda fd: (_ for _ in ()).throw(OSError('simulated flush failure')))
    project['lyrics_raw'] = 'Unsaved work'
    with pytest.raises(OSError):
        store.save_project(pid, project)
    assert path.read_bytes() == original
    assert project['document_revision'] == revision
    assert project['lyrics_raw'] == 'Unsaved work'
    assert not list(path.parent.glob('.saving-*.tmp'))


def test_nonserializable_draft_fails_before_mutating_files(project):
    path = Path(store._path(project['id']))
    original = path.read_bytes()
    with pytest.raises(ValueError):
        store.save_workspace(project['id'], {'bad': float('nan')}, project['document_revision'])
    assert path.read_bytes() == original


@pytest.mark.parametrize('missing', [False, True])
def test_last_good_recovery_is_visible_and_can_be_saved(project, missing):
    pid = project['id']
    store.save_workspace(pid, {'lyrics_raw': 'Recover this'}, project['document_revision'])
    current = store.load_project(pid)
    store.save_workspace(pid, {'lyrics_raw': 'Newest save'}, current['document_revision'])
    path = Path(store._path(pid))
    if missing:
        path.unlink()
    else:
        path.write_bytes(b'{broken')
    recovered = store.get_workspace(pid)
    assert recovered['recovery']['used_last_good']
    assert recovered['draft']['lyrics_raw'] == 'Recover this'
    saved = store.save_workspace(pid, recovered['draft'], recovered['document_revision'])
    assert saved['recovery'] is None
    assert store.get_workspace(pid)['draft']['lyrics_raw'] == 'Recover this'
    if not missing:
        assert list(path.parent.glob('project.corrupt-*.json'))[0].read_bytes() == b'{broken'


def test_corrupt_primary_and_backup_never_create_a_blank_project(project):
    Path(store._path(project['id'])).write_bytes(b'{broken')
    Path(store._backup_path(project['id'])).write_bytes(b'[]')
    with pytest.raises(store.ProjectCorrupt):
        store.load_project(project['id'])
    with pytest.raises(store.ProjectCorrupt):
        store.save_project(project['id'], project)


def test_custom_snapshots_survive_library_edit_delete_and_caller_mutation(project, monkeypatch):
    pid = project['id']
    custom = replace(steps.MOVE_BY_ID['rock_fwd'], id='custom-tested', name='Old move')
    original_lookup = store._move_definition
    monkeypatch.setattr(store, '_move_definition', lambda mid: custom if mid == custom.id else original_lookup(mid))
    project['dance'] = {'source': 'custom', 'custom': [{'move_id': custom.id, 'lead': 'R'}]}
    store.save_project(pid, project)
    snapshot = copy.deepcopy(project['movement_snapshots'])
    monkeypatch.setattr(store, '_move_definition', lambda mid: None)
    loaded = store.load_project(pid)
    resolved = store.resolve_move_variants(loaded, project['dance']['custom'])
    assert resolved[0]['name'] == 'Old move'
    resolved[0]['lines'][0]['text'] = 'A caller must not change snapshots'
    assert loaded['movement_snapshots'] == snapshot
    store.save_project(pid, loaded)
    assert store.resolve_move_variants(store.load_project(pid), project['dance']['custom'])[0]['name'] == 'Old move'


def test_free_foot_fillers_use_frozen_correct_variant(project):
    moves = [{'move_id': 'stomp_weighted', 'lead': 'R'}, {'move_id': 'hitch', 'lead': 'R'}]
    project['dance'] = {'source': 'custom', 'custom': moves}
    store.save_project(project['id'], project)
    result = store.resolve_move_variants(project, moves)
    assert result[1]['lead'] == 'L'
    assert 'L' in result[1]['lines'][0]['text']


def test_legacy_unrecognized_move_payload_is_preserved(project):
    project['dance'] = {'source': 'generated', 'candidates': [{'moves': [{'legacy_text': 'keep this'}]}]}
    store.save_project(project['id'], project)
    assert store.get_workspace(project['id'])['draft']['editor']['moves'] == [{'legacy_text': 'keep this'}]


def test_apply_uses_draft_snapshot_after_custom_library_disappears(project, monkeypatch):
    custom = replace(steps.MOVE_BY_ID['rock_fwd'], id='custom-saved-draft', name='Frozen draft')
    monkeypatch.setattr(store, '_move_definition', lambda mid: custom if mid == custom.id else None)
    moves = [{'move_id': custom.id, 'lead': 'R'}]
    store.save_workspace(project['id'], {'editor': {'moves': moves}}, project['document_revision'])
    monkeypatch.setattr(store, '_move_definition', lambda mid: None)
    accepted = store.load_project(project['id'])
    accepted['dance'] = {'source': 'custom', 'custom': moves}
    store.save_project(project['id'], accepted)
    assert store.resolve_move_variants(accepted, moves)[0]['name'] == 'Frozen draft'


def test_named_version_restore_preserves_later_work_and_accepted_dance(project):
    pid = project['id']
    first = store.save_workspace(pid, {'lyrics_raw': 'First', 'editor': {'moves': []}}, project['document_revision'])
    named = store.create_version(pid, 'First draft', first['document_revision'])
    vid = named['version']['version_id']
    before_bytes = Path(store._version_path(pid, vid)).read_bytes()
    second = store.save_workspace(pid, {'lyrics_raw': 'Later', 'editor': {'moves': ['unfinished']}}, named['document_revision'])
    accepted = store.load_project(pid)
    accepted['dance'] = {'source': 'custom', 'custom': [{'move_id': 'hold', 'lead': 'L'}]}
    store.save_project(pid, accepted)
    restored = store.restore_version(pid, vid, accepted['document_revision'])
    assert restored['draft']['lyrics_raw'] == 'First'
    assert restored['accepted_dance'] == accepted['dance']
    recovery = store.get_version(pid, restored['recovery_version']['version_id'])
    assert recovery['draft']['lyrics_raw'] == second['draft']['lyrics_raw']
    assert recovery['draft']['editor'] == second['draft']['editor']
    assert Path(store._version_path(pid, vid)).read_bytes() == before_bytes
    assert restored['document_revision'] > accepted['document_revision']


def test_tampered_version_and_stale_restore_do_not_change_current_document(project):
    pid = project['id']
    version = store.create_version(pid, 'Saved', project['document_revision'])
    vid = version['version']['version_id']
    current = Path(store._path(pid)).read_bytes()
    with pytest.raises(store.RevisionConflict):
        store.restore_version(pid, vid, project['document_revision'])
    path = Path(store._version_path(pid, vid))
    payload = json.loads(path.read_text())
    payload['draft']['lyrics_raw'] = 'tampered'
    path.write_text(json.dumps(payload))
    with pytest.raises(store.ProjectCorrupt):
        store.restore_version(pid, vid, version['document_revision'])
    assert Path(store._path(pid)).read_bytes() == current


def test_failed_version_commit_removes_only_new_version(project, monkeypatch):
    pid = project['id']
    real_write = store._atomic_write
    def fail_primary(path, payload):
        if path == store._path(pid):
            raise OSError('Failed history commit')
        return real_write(path, payload)
    monkeypatch.setattr(store, '_atomic_write', fail_primary)
    with pytest.raises(OSError):
        store.create_version(pid, 'Not committed', project['document_revision'])
    assert store.list_versions(pid)['versions'] == []
    assert not list((Path(store.project_dir(pid)) / 'versions').glob('*.json'))


@pytest.mark.parametrize('pid', ['../outside', 'UPPER', '', 'a/b', 'a\\b', '.locks'])
def test_project_id_traversal_is_rejected(projects, pid):
    with pytest.raises(ValueError):
        store.load_project(pid)


def test_router_contract_errors_and_version_preview(client, project, monkeypatch):
    pid = project['id']
    endpoint = f'/api/projects/{pid}/workspace'
    current = client.get(endpoint).json()
    assert client.put(endpoint, json={'draft': {}, 'expected_revision': True}).status_code == 422
    saved = client.put(endpoint, json={'draft': {'editor': {'moves': []}, 'choreography': {'parts': []}},
                                      'expected_revision': current['document_revision']})
    assert saved.status_code == 200
    stale = client.put(endpoint, json={'draft': {'lyrics_raw': 'stale'}, 'expected_revision': current['document_revision']})
    assert stale.status_code == 409
    assert stale.json()['detail']['current_revision'] == saved.json()['document_revision']
    version = client.post(f'/api/projects/{pid}/versions', json={'expected_revision': saved.json()['document_revision'], 'label': 'Preview'})
    assert version.status_code == 200
    vid = version.json()['version']['version_id']
    preview = client.get(f'/api/projects/{pid}/versions/{vid}')
    assert preview.status_code == 200 and preview.json()['draft']['choreography'] == {'parts': []}
    assert client.get('/api/projects/missing/workspace').status_code == 404
    monkeypatch.setattr(store, '_atomic_write', lambda *args: (_ for _ in ()).throw(OSError('disk')))
    failed = client.put(endpoint, json={'expected_revision': version.json()['document_revision'], 'draft': {'lyrics_raw': 'failed'}})
    assert failed.status_code == 503


def _child(code, root, pid, *args):
    env = dict(os.environ, LINE_DANCE_PROJECTS_DIR=str(root), PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    return subprocess.Popen([sys.executable, '-B', '-u', '-c', code, pid, *args], env=env,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, creationflags=0x08000000 if os.name == 'nt' else 0)


def test_competing_processes_cannot_both_commit_one_revision(projects, project):
    code = """
import sys
from engine import project as s
p = s.load_project(sys.argv[1])
print('ready', flush=True)
sys.stdin.readline()
try:
    s.save_workspace(p['id'], {'lyrics_raw': sys.argv[2]}, p['document_revision'])
    print('saved', flush=True)
except s.RevisionConflict:
    print('conflict', flush=True)
"""
    children = [_child(code, projects, project['id'], label) for label in ('first', 'second')]
    try:
        for child in children:
            assert child.stdout.readline().strip() == 'ready'
        for child in children:
            child.stdin.write('go\n')
            child.stdin.flush()
        outputs = [child.communicate(timeout=15) for child in children]
        assert sorted(stdout.strip() for stdout, _ in outputs) == ['conflict', 'saved']
        assert all(child.returncode == 0 for child in children), outputs
        assert store.load_project(project['id'])['document_revision'] == project['document_revision'] + 1
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.communicate()


@pytest.mark.parametrize('moment', ['before', 'after'])
def test_process_interruption_at_primary_replace_keeps_a_complete_save(projects, project, moment):
    code = """
import os, sys
from engine import project as s
p = s.load_project(sys.argv[1])
original = os.replace
def interrupt(source, destination):
    if destination == s._path(p['id']):
        if sys.argv[2] == 'before':
            os._exit(42)
        original(source, destination)
        os._exit(42)
    return original(source, destination)
os.replace = interrupt
s.save_workspace(p['id'], {'lyrics_raw': 'Completed new draft'}, p['document_revision'])
"""
    child = _child(code, projects, project['id'], moment)
    stdout, stderr = child.communicate(timeout=15)
    assert child.returncode == 42, (stdout, stderr)
    recovered = store.get_workspace(project['id'])
    assert recovered['draft']['lyrics_raw'] == ('' if moment == 'before' else 'Completed new draft')
    assert recovered['recovery'] is None
    assert json.loads(Path(store._backup_path(project['id'])).read_text())['document_revision'] == project['document_revision']
