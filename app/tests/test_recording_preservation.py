"""Song replacement must preserve dance work and prevent mismatched exports."""
from copy import deepcopy
import io
from pathlib import Path
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import project as store, project_media, steps
import media_api
import server


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'PROJECTS_DIR', str(tmp_path / 'projects'))
    with server._jobs_lock:
        server._jobs.clear()
        server._alignment_jobs.clear()
        server._repair_jobs.clear()
    # Root mounts the router for the actual application. This fixture also works
    # during its narrow parallel integration window without mutating that app.
    if any(getattr(route, 'path', '') == '/api/creator/projects/{pid}/recording/review' for route in server.app.routes):
        app = server.app
    else:
        app = FastAPI()
        app.router.routes.extend(server.app.router.routes)
        app.include_router(media_api.router)
        app.add_exception_handler(store.RevisionConflict, server.revision_conflict_handler)
    with TestClient(app) as value:
        yield value


def _ready_project(client, tmp_path):
    pid = client.post('/api/projects', json={'name': 'Recording preservation'}).json()['id']
    old = tmp_path / 'old.wav'
    old.write_bytes(b'RIFF-old-recording')
    project = store.load_project(pid)
    project['song'].update(path=str(old), filename=old.name, title='Old song')
    project['analysis'] = {'bpm': 113, 'beat_times': [0, 0.53, 1.06]}
    project['sections'] = [{'label': 'Old chorus', 'start': 0, 'end': 12}]
    project['alignment'] = {'source_path': str(old), 'words': [{'word': 'old', 'start': 0}]}
    project['phrase'] = {'source': 'old timing'}
    project['tutorial'] = {'source': 'old audio'}
    project['repair'] = {'last_output': 'old-mix.wav'}
    store.save_project(pid, project)
    move = {**steps.get_move('rocking_chair').variant('R'), 'id': 'keep-move'}
    document = {'schema_version': 1, 'start': {'free_foot': 'R'},
                'parts': [{'id': 'A', 'moves': [move]}], 'routine': [{'part_id': 'A'}]}
    workspace = store.save_workspace(pid, {'choreography': document,
        'music_map': {'bpm': 113, 'first_count': 3, 'meter': 4,
                      'anchors': [{'count': 0, 'time': 3}, {'count': 4, 'time': 5.124}]},
        'custom_editor_metadata': {'keep': [1, 2, 3]}}, project['document_revision'])
    response = client.post(f'/api/creator/projects/{pid}/accept', json={'expected_revision': workspace['document_revision']})
    assert response.status_code == 200, response.text
    return pid, old, deepcopy(store.load_project(pid))


def _switch(client, pid, tmp_path, payload=b'RIFF-new-recording'):
    replacement = tmp_path / 'new.wav'
    replacement.write_bytes(payload)
    response = client.post(f'/api/projects/{pid}/song-path', json={'path': str(replacement)})
    assert response.status_code == 200, response.text
    return replacement, store.load_project(pid)


def _review(client, pid):
    project = store.load_project(pid)
    result = client.post(f'/api/creator/projects/{pid}/recording/review',
                         json={'expected_revision': project['document_revision'], 'confirmed': True})
    assert result.status_code == 200, result.text
    return store.load_project(pid)


def test_new_song_preserves_accepted_and_working_choreography_with_original_mapping_history(client, tmp_path):
    pid, old, before = _ready_project(client, tmp_path)
    replacement, after = _switch(client, pid, tmp_path)
    for key in ('dance', 'accepted_choreography', 'accepted_choreography_source', 'accepted_choreography_hash', 'movement_snapshots'):
        assert after[key] == before[key]
    assert after['draft']['choreography'] == before['draft']['choreography']
    assert after['draft']['custom_editor_metadata'] == {'keep': [1, 2, 3]}
    assert after['song']['path'] == str(replacement)
    assert old.read_bytes() == b'RIFF-old-recording'
    archive = after['recording_history'][-1]
    for key in ('song', 'analysis', 'sections', 'alignment', 'phrase', 'tutorial', 'repair', 'dance', 'accepted_choreography_source'):
        assert archive[key] == before[key]
    assert archive['music_map'] == before['draft']['music_map']
    assert after['analysis'] is None and after['alignment'] is None
    assert after['sections'] == [] and after['tutorial'] is None
    assert after['draft']['music_map']['anchors'] == []
    assert after['draft']['music_map']['bpm_source'] == 'PROVISIONAL_DEFAULT'
    assert after['draft']['recording_review']['status'] == 'REVIEW_REQUIRED'


@pytest.mark.parametrize('endpoint', ['sheet.json', 'sheet.txt', 'sheet.html', 'sheet.pdf', 'publish-kit'])
def test_legacy_exports_block_until_recording_and_map_review(client, tmp_path, endpoint):
    pid, _, before = _ready_project(client, tmp_path)
    _switch(client, pid, tmp_path)
    result = client.get(f'/api/projects/{pid}/{endpoint}')
    assert result.status_code == 409
    assert store.load_project(pid)['dance'] == before['dance']


def test_review_exact_current_map_allows_legacy_export_without_replacing_accepted_dance(client, tmp_path):
    pid, _, before = _ready_project(client, tmp_path)
    _switch(client, pid, tmp_path)
    project = store.load_project(pid)
    store.save_workspace(pid, {'music_map': {'bpm': 120, 'first_count': 5, 'meter': 4, 'anchors': []}}, project['document_revision'])
    reviewed = _review(client, pid)
    assert not project_media.recording_review_needed(reviewed)
    assert reviewed['dance'] == before['dance']
    assert reviewed['draft']['music_map']['timing_confirmed'] is True
    current = server._current_dance(reviewed)
    assert current['tempo']['bpm'] == 120
    assert before['dance']['tempo']['bpm'] == 113
    assert client.get(f'/api/projects/{pid}/sheet.txt').status_code == 200


@pytest.mark.parametrize('change', ['map', 'recording_bytes', 'missing_recording'])
def test_review_binding_expires_when_timing_or_recording_changes(client, tmp_path, change):
    pid, _, _ = _ready_project(client, tmp_path)
    path, _ = _switch(client, pid, tmp_path)
    reviewed = _review(client, pid)
    if change == 'map':
        timing = deepcopy(reviewed['draft']['music_map'])
        timing['first_count'] = 9
        store.save_workspace(pid, {'music_map': timing}, reviewed['document_revision'])
    elif change == 'recording_bytes':
        path.write_bytes(b'RIFF-a-different-performance')
    else:
        path.unlink()
    assert project_media.recording_review_needed(store.load_project(pid))
    assert client.get(f'/api/projects/{pid}/sheet.txt').status_code == 409


def test_review_requires_confirmation_and_current_revision(client, tmp_path):
    pid, _, _ = _ready_project(client, tmp_path)
    _switch(client, pid, tmp_path)
    original = deepcopy(store.load_project(pid))
    url = f'/api/creator/projects/{pid}/recording/review'
    assert client.post(url, json={'expected_revision': original['document_revision'], 'confirmed': False}).status_code == 422
    assert client.post(url, json={'expected_revision': original['document_revision'] - 1, 'confirmed': True}).status_code == 409
    assert store.load_project(pid) == original


def test_same_recording_content_relink_preserves_review_and_analysis(client, tmp_path):
    pid, _, _ = _ready_project(client, tmp_path)
    path, _ = _switch(client, pid, tmp_path)
    reviewed = _review(client, pid)
    reviewed['analysis'] = {'bpm': 120, 'source': 'new'}
    store.save_project(pid, reviewed)
    before = deepcopy(store.load_project(pid))
    relink = tmp_path / 'moved.wav'
    relink.write_bytes(path.read_bytes())
    assert client.post(f'/api/projects/{pid}/song-path', json={'path': str(relink)}).status_code == 200
    after = store.load_project(pid)
    assert after['analysis'] == before['analysis']
    assert after['recording_history'] == before['recording_history']
    assert after['draft']['music_map'] == before['draft']['music_map']
    assert not project_media.recording_review_needed(after)


def test_repeated_uploaded_filename_never_overwrites_original_recording(client, tmp_path):
    pid, _, original = _ready_project(client, tmp_path)
    url = f'/api/projects/{pid}/song-upload'
    first = client.post(url, files={'file': ('same.wav', b'RIFF-upload-first', 'audio/wav')})
    assert first.status_code == 200, first.text
    old_path = Path(first.json()['path'])
    second = client.post(url, files={'file': ('same.wav', b'RIFF-upload-second', 'audio/wav')})
    assert second.status_code == 200, second.text
    new_path = Path(second.json()['path'])
    assert new_path != old_path
    assert old_path.read_bytes() == b'RIFF-upload-first'
    assert new_path.read_bytes() == b'RIFF-upload-second'
    after = store.load_project(pid)
    assert after['dance'] == original['dance']
    assert after['recording_history'][-1]['song']['path'] == str(old_path)


def test_upload_failure_keeps_previous_file_and_project_and_removes_uncommitted_audio(client, tmp_path, monkeypatch):
    pid, _, _ = _ready_project(client, tmp_path)
    before = deepcopy(store.load_project(pid))
    def failed(*args, **kwargs):
        raise OSError('Simulated storage failure')
    monkeypatch.setattr(store, 'save_project', failed)
    response = client.post(f'/api/projects/{pid}/song-upload', files={'file': ('new.wav', b'RIFF-new', 'audio/wav')})
    assert response.status_code == 503
    assert store.load_project(pid) == before
    assert not list((Path(store.project_dir(pid)) / 'recordings').glob('*'))


@pytest.mark.parametrize('filename,payload', [('bad.exe', b'data'), ('empty.wav', b'')])
def test_bad_upload_keeps_saved_choreography(client, tmp_path, filename, payload):
    pid, _, _ = _ready_project(client, tmp_path)
    before = deepcopy(store.load_project(pid))
    response = client.post(f'/api/projects/{pid}/song-upload', files={'file': (filename, payload)})
    assert response.status_code == 400
    assert store.load_project(pid) == before


def test_upload_traversal_filename_is_confined_to_immutable_project_recording(client, tmp_path):
    pid, _, _ = _ready_project(client, tmp_path)
    result = client.post(f'/api/projects/{pid}/song-upload', files={'file': ('../../escape.wav', b'RIFF-safe')})
    assert result.status_code == 200
    path = Path(result.json()['path']).resolve()
    assert path.parent == (Path(store.project_dir(pid)) / 'recordings').resolve()
    assert result.json()['filename'] == 'escape.wav'


def test_accepting_or_generating_does_not_grant_recording_review(client, tmp_path):
    pid, _, _ = _ready_project(client, tmp_path)
    _switch(client, pid, tmp_path)
    project = store.load_project(pid)
    assert client.post('/api/creator/generate', json={'counts': 32, 'wall': '1'}).status_code == 200
    assert client.post(f'/api/creator/projects/{pid}/accept', json={'expected_revision': project['document_revision']}).status_code == 200
    assert project_media.recording_review_needed(store.load_project(pid))
    assert client.get(f'/api/projects/{pid}/sheet.txt').status_code == 409


def test_recording_status_reflects_unsaved_identity_drift_and_missing_audio(client, tmp_path):
    pid, _, _ = _ready_project(client, tmp_path)
    path, _ = _switch(client, pid, tmp_path)
    url = f'/api/creator/projects/{pid}/recording/status'
    assert client.get(url).json() == {'review_needed': True, 'status': 'REVIEW_REQUIRED', 'has_audio': True}
    reviewed = _review(client, pid)
    assert client.get(url).json() == {'review_needed': False, 'status': 'REVIEWED', 'has_audio': True}
    edited = deepcopy(reviewed['draft']['music_map'])
    edited['bpm'] = 110
    store.save_workspace(pid, {'music_map': edited}, reviewed['document_revision'])
    assert client.get(url).json()['review_needed'] is True
    _review(client, pid)
    path.unlink()
    assert client.get(url).json() == {'review_needed': True, 'status': 'REVIEW_REQUIRED', 'has_audio': False}
    assert client.get('/api/creator/projects/missing-project/recording/status').status_code == 404


def test_recording_status_allows_music_free_legacy_workflow(client):
    project = client.post('/api/projects', json={'name': 'No recording'}).json()
    result = client.get(f"/api/creator/projects/{project['id']}/recording/status")
    assert result.json() == {'review_needed': False, 'status': 'NO_RECORDING', 'has_audio': False}


def test_stale_song_metadata_cannot_replace_current_recording_identity(client, tmp_path):
    pid, _, _ = _ready_project(client, tmp_path)
    _, current = _switch(client, pid, tmp_path)
    identity = {key: current['song'][key] for key in ('path', 'filename', 'recording_id', 'content_signature')}
    response = client.put(f'/api/projects/{pid}/workspace', json={
        'expected_revision': current['document_revision'],
        'draft': {'song': {'title': 'Authored title', 'path': 'old.wav', 'filename': 'old.wav',
                           'recording_id': 'old-recording-id', 'content_signature': {'sha256': 'old', 'bytes': 1}}}})
    assert response.status_code == 200
    song = store.load_project(pid)['song']
    assert song['title'] == 'Authored title'
    assert {key: song[key] for key in identity} == identity


def test_upload_revision_conflict_keeps_concurrent_edit_and_removes_uncommitted_file(client, tmp_path, monkeypatch):
    pid, _, before = _ready_project(client, tmp_path)
    real_save = store.save_project
    raced = False
    def concurrent_edit(record_id, data, **kwargs):
        nonlocal raced
        if not raced:
            raced = True
            other = store.load_project(record_id)
            other['name'] = 'Concurrent edit kept'
            real_save(record_id, other)
        return real_save(record_id, data, **kwargs)
    monkeypatch.setattr(store, 'save_project', concurrent_edit)
    response = client.post(f'/api/projects/{pid}/song-upload', files={'file': ('new.wav', b'RIFF-cas')})
    assert response.status_code == 409
    after = store.load_project(pid)
    assert after['name'] == 'Concurrent edit kept'
    assert after['song'] == before['song'] and after['dance'] == before['dance']
    assert not list((Path(store.project_dir(pid)) / 'recordings').glob('*'))
