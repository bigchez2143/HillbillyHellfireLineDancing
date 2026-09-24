"""S05/S06 integration evidence with deterministic synthetic audio and no AI calls.

These are behavior requirements, not snapshots of implementation output. Audio
estimation has an explicit tolerance; synthetic fixtures are not real-song QA.
"""
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.error import HTTPError, URLError

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import audio as audio_engine, project as store, settings, ai_assistant
from engine.assembler import validate_sequence
from engine.choreography import compile_choreography
from engine.music_map import count_to_seconds, seconds_to_count, validate_map, estimate_key
from engine.steps import get_move
import server

SR = 22050


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'PROJECTS_DIR', str(tmp_path / 'projects'))
    monkeypatch.setattr(settings, 'SETTINGS_FILE', str(tmp_path / 'settings.json'))
    with TestClient(server.app) as value:
        yield value


def create(client):
    return client.post('/api/projects', json={'name': 'Synthetic integration'}).json()['id']


def concrete(lead='R'):
    return {**get_move('rocking_chair').variant(lead), 'id': 'locked-occurrence',
            'locked': True, 'notes': 'Keep these authored words.', 'teaching': {'cue': 'Rock and return'}}


def part_with_middle_lock(lead='R'):
    before = get_move('rocking_chair').variant(lead)
    return {'id': 'A', 'name': 'Main', 'moves': [{**before, 'id': 'before'}, concrete(lead),
                                                {**copy.deepcopy(before), 'id': 'after'}]}


@pytest.mark.parametrize('count', [-8, 0, 0.125, 10.5, 32, 63.75, 64, 200, 10000])
def test_variable_tempo_roundtrip_and_no_accumulated_drift(count):
    # First 32 counts at 100 BPM, next 32 at 120 BPM, with a 2-second intro.
    timing = {'bpm': 100, 'first_count': 2, 'meter': 4,
              'anchors': [{'count': 0, 'time': 2}, {'count': 32, 'time': 21.2}, {'count': 64, 'time': 37.2}]}
    expected = 2 + count * 0.6 if count <= 32 else 21.2 + (count - 32) * 0.5
    seconds = count_to_seconds(count, timing)
    assert seconds == pytest.approx(expected, abs=1e-9)
    assert seconds_to_count(seconds, timing) == pytest.approx(count, abs=1e-9)


def test_variable_map_survives_project_save_roundtrip(client):
    pid = create(client)
    project = store.load_project(pid)
    timing = {'bpm': 100, 'first_count': 2, 'meter': 3, 'reviewed': True,
              'key': {'key': 'C major', 'status': 'USER_REVIEWED'},
              'anchors': [{'count': 0, 'time': 2}, {'count': 32, 'time': 21.2}, {'count': 64, 'time': 37.2}]}
    response = client.put(f'/api/projects/{pid}/workspace', json={'expected_revision': project['document_revision'],
                                                                 'draft': {'music_map': timing}})
    assert response.status_code == 200, response.text
    restored = client.get(f'/api/projects/{pid}/workspace').json()['draft']['music_map']
    assert restored == timing
    assert count_to_seconds(48, restored) == pytest.approx(29.2)
    assert store.load_project(pid)['dance'] == {}


def test_fractional_meter_is_rejected_instead_of_truncated(client):
    response = client.post('/api/creator/music-map/validate', json={'meter': 3.5})
    assert response.status_code == 422, 'A 3.5 meter must not silently become 3.'


@pytest.fixture(scope='module')
def key_samples(tmp_path_factory):
    root = tmp_path_factory.mktemp('key-audio')
    t = np.arange(SR * 6) / SR
    chord = sum(np.sin(2 * np.pi * f * t) for f in (261.625565, 329.627557, 391.995436)) / 5
    envelope = np.minimum(1, np.minimum(t * 20, (6 - t) * 20))
    signals = {'silence': np.zeros(SR * 2), 'short': chord[:SR // 2],
               'noise': np.random.default_rng(2409).normal(0, 0.15, SR * 6), 'c_major_chord': chord * envelope}
    result = {}
    for name, y in signals.items():
        path = root / (name + '.wav')
        sf.write(path, y, SR, subtype='PCM_16')
        result[name] = estimate_key(str(path))
    return result


@pytest.mark.parametrize('name', ['silence', 'short'])
def test_no_key_claim_with_insufficient_audio(key_samples, name):
    assert key_samples[name]['key'] == ''
    assert key_samples[name]['confidence'] == 'insufficient'


def test_noise_key_estimate_does_not_claim_confident_tonality(key_samples):
    value = key_samples['noise']
    print('noise_key', json.dumps(value, ensure_ascii=True))
    assert value['confidence'] in {'low', 'insufficient'}
    if value['key']:
        assert 'Estimate only' in value['note']
        assert len(value['alternatives']) >= 2


def test_major_chord_candidate_and_uncertainty_are_exposed(key_samples):
    value = key_samples['c_major_chord']
    print('chord_key', json.dumps(value, ensure_ascii=True))
    assert 'C major' in {row['key'] for row in value['alternatives']}
    # A chord alone does not prove the key of a song.
    assert value['confidence'] in {'low', 'moderate'}
    assert 'Estimate only' in value['note']
    assert len(value['alternatives']) == 3


def _click_track(path, segments):
    duration = sum(seconds for _, seconds in segments) + 2
    y = np.zeros(int(duration * SR), dtype=np.float32)
    click_t = np.arange(int(0.035 * SR)) / SR
    pulse = np.sin(2 * np.pi * 1600 * click_t) * np.exp(-click_t * 110)
    start, beat_index = 1.0, 0
    for bpm, seconds in segments:
        for onset in np.arange(start, start + seconds - 1e-6, 60 / bpm):
            index = round(onset * SR)
            amplitude = 0.85 if beat_index % 4 == 0 else 0.55
            y[index:index + len(pulse)] += (pulse * amplitude).astype(np.float32)
            beat_index += 1
        start += seconds
    sf.write(path, y, SR, subtype='PCM_16')


@pytest.fixture(scope='module')
def analyzed_clicks(tmp_path_factory):
    root = tmp_path_factory.mktemp('click-audio')
    results = {}
    for label, segments in [('100', [(100, 64)]), ('120', [(120, 64)]),
                            ('changing', [(100, 40), (120, 40)])]:
        path = root / (label + '.wav')
        _click_track(path, segments)
        results[label] = audio_engine.analyze(str(path))
    return results


@pytest.mark.parametrize('expected', [100, 120])
def test_real_audio_analysis_of_known_click_tempo(analyzed_clicks, expected):
    result = analyzed_clicks[str(expected)]
    print('click_' + str(expected), json.dumps({k: result[k] for k in ('bpm', 'bpm_confidence', 'bpm_confidence_notes', 'methods', 'drift')}))
    # HOP=512 introduces estimator quantization; tolerate at most 3 percent.
    assert abs(result['bpm'] - expected) / expected <= 0.03
    beats = result['beat_times']
    assert len(beats) > 80
    assert all(b > a for a, b in zip(beats, beats[1:]))
    assert np.median(np.diff(beats)) == pytest.approx(60 / expected, rel=0.04)
    json.dumps(result, allow_nan=False)


def test_real_audio_tempo_change_is_flagged_for_human_review(analyzed_clicks):
    result = analyzed_clicks['changing']
    print('changing_click', json.dumps({k: result[k] for k in ('bpm', 'bpm_confidence', 'bpm_confidence_notes', 'methods', 'drift')}))
    assert result['bpm_confidence'] != 'high'
    assert result['drift'] is not None, 'A clear 100 to 120 BPM change must not be presented as one steady tempo.'
    assert result['drift']['drift_pct'] > 10
    assert not result['tempo_steady']


@pytest.mark.parametrize('lead', ['R', 'L'])
def test_generation_preserves_locked_occurrence_payload_and_count_position(client, lead):
    part = part_with_middle_lock(lead)
    locked = copy.deepcopy(part['moves'][1])
    response = client.post('/api/creator/generate', json={'counts': 32, 'wall': '1', 'level': 'AB',
                                                         'start_foot': lead, 'seed': 42, 'part': part})
    assert response.status_code == 200, response.text
    candidates = response.json()['candidates']
    assert candidates
    for candidate in candidates:
        found, count = [], 0
        for move in candidate['moves']:
            if move.get('id') == locked['id']:
                found.append((count, move))
            count += move['counts']
        assert found == [(4, locked)]
        assert count == 32
        assert validate_sequence(candidate['moves'], 32, '1', 'L', start_foot=lead)['valid']
        assert candidate['moves'][0]['start'] in (lead, 'F')


@pytest.mark.parametrize('fault', ['off_grid', 'changed_lines', 'non_core', 'contradictory_duration', 'explicit_events', 'too_long'])
def test_impossible_or_modified_lock_fails_without_project_mutation(client, fault):
    pid = create(client)
    p = store.load_project(pid)
    part = part_with_middle_lock()
    if fault == 'off_grid':
        part['moves'][0]['duration_counts'] = '1/2'
    elif fault == 'changed_lines':
        part['moves'][1]['lines'][0]['text'] = 'A different movement'
    elif fault == 'non_core':
        part['moves'][1]['move_id'] = 'undefined-user-move'
    elif fault == 'contradictory_duration':
        part['moves'][1]['duration_counts'] = '8'
    elif fault == 'explicit_events':
        # An explicit event graph takes priority in the shared compiler. A
        # matching legacy summary cannot authorize ignoring that graph.
        part['moves'][1]['events'] = [{'duration_counts': '4', 'support_before': 'L',
                                      'support_after': 'L', 'rotation_deg': '180', 'text': 'Different turn'}]
    elif fault == 'too_long':
        part['moves'][0]['duration_counts'] = '32'
    store.save_workspace(pid, {'choreography': {'parts': [part], 'routine': [{'part_id': 'A'}]}}, p['document_revision'])
    before = copy.deepcopy(store.load_project(pid))
    response = client.post('/api/creator/generate', json={'counts': 32, 'wall': '1', 'level': 'AB', 'part': part})
    assert response.status_code == 422, 'An impossible or modified locked definition was accepted: ' + fault
    assert store.load_project(pid) == before


def test_cross_origin_write_blocked_same_origin_allowed(client):
    blocked = client.post('/api/projects', json={'name': 'Cross origin'}, headers={'Origin': 'https://unrelated.example'})
    assert blocked.status_code == 403
    assert store.list_projects() == []
    allowed = client.post('/api/projects', json={'name': 'Same origin'}, headers={'Origin': 'http://testserver'})
    assert allowed.status_code == 200
    pid = allowed.json()['id']
    original = copy.deepcopy(store.load_project(pid))
    for method, path, data in [('PUT', f'/api/projects/{pid}/workspace', {'expected_revision': original['document_revision'], 'draft': {'name': 'Changed'}}),
                              ('POST', '/api/creator/generate', {'counts': 32})]:
        assert client.request(method, path, json=data, headers={'Origin': 'null'}).status_code == 403
    assert store.load_project(pid) == original
    assert client.get('/dance').headers['referrer-policy'] == 'no-referrer'


@pytest.mark.parametrize('failure', ['unauthorized', 'timeout', 'bad_json'])
def test_provider_failure_has_no_fallback_or_project_mutation(client, monkeypatch, failure):
    pid = create(client)
    before = copy.deepcopy(store.load_project(pid))
    connection = {'provider': 'openai_compatible', 'model': 'user-model',
                  'base_url': 'https://user-provider.example/v1', 'api_key': 'fake-user-key', 'timeout_seconds': 2}
    monkeypatch.setattr(settings, 'load_ai_connection', lambda: connection)
    requests = []
    def fail(request, timeout):
        requests.append(request)
        if failure == 'unauthorized':
            raise HTTPError(request.full_url, 401, 'Unauthorized', {}, io.BytesIO(b'{"error":{"message":"User credentials rejected"}}'))
        if failure == 'timeout':
            raise URLError('Timed out')
        class Reply:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, size): return b'not-json'
        return Reply()
    monkeypatch.setattr(ai_assistant, 'urlopen', fail)
    response = client.post('/api/ai/chat', json={'prompt': 'Suggest an idea', 'project_id': pid, 'include_project': True})
    assert response.status_code == 502
    assert len(requests) == 1
    assert requests[0].full_url == connection['base_url'] + '/chat/completions'
    assert requests[0].get_header('Authorization') == 'Bearer fake-user-key'
    assert 'fake-user-key' not in response.text
    assert store.load_project(pid) == before
    assert client.post('/api/creator/generate', json={'counts': 32, 'wall': '1'}).status_code == 200
    assert len(requests) == 1


def test_fresh_start_and_core_workflows_need_no_ai_provider(tmp_path):
    # Fresh interpreter: fail every attempted network connection before import.
    script = '''
import socket, urllib.request
def forbidden(*args, **kwargs):
    raise AssertionError("Core startup attempted an external connection")
socket.create_connection = forbidden
urllib.request.urlopen = forbidden
import server
from fastapi.testclient import TestClient
with TestClient(server.app) as client:
    assert client.get('/dance').status_code == 200
    settings = client.get('/api/settings/ai').json()
    assert not settings['ready'] and not settings['api_key_configured']
    project = client.post('/api/projects', json={'name':'No AI'}).json()
    assert client.get('/api/projects/' + project['id'] + '/workspace').status_code == 200
    assert client.post('/api/creator/generate', json={'counts':32,'wall':'1'}).status_code == 200
    assert client.post('/api/ai/chat', json={'prompt':'Hello'}).status_code == 400
'''
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1]),
           'LINE_DANCE_DATA_DIR': str(tmp_path / 'data'), 'LINE_DANCE_PROJECTS_DIR': str(tmp_path / 'projects')}
    result = subprocess.run([sys.executable, '-B', '-c', script], env=env, cwd=tmp_path,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
