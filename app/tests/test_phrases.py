"""Phrase persistence, exact timing and reflection across real move snapshots."""
from copy import deepcopy
from pathlib import Path
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import phrase_store as store
from engine.steps import library_json
from engine.move_expansion import variants
from engine.choreography import compile_choreography
from phrase_api import router


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'PHRASE_DIR', tmp_path / 'phrases')


def written(duration='8'):
    return {'id': 'my-occurrence', 'name': 'Right diagonal practice', 'duration_counts': duration,
            'events': [{'id': 'step', 'offset_counts': '0', 'duration_counts': duration,
                        'text': 'Step R to the right facing 3:00', 'support_before': 'L',
                        'support_after': 'R', 'moving_foot': 'R', 'rotation_deg': '90',
                        'facing_before_deg': '0', 'facing_after_deg': '90'}],
            'snapshot_id': 'written@1', 'definition_hash': 'a' * 64, 'source_hash': 'b' * 64,
            'required_start_facing': '0', 'start_free_foot': 'R', 'net_rotation_deg': '90', 'travel': 'E',
            'review': {'status': 'AUTHOR_REVIEWED', 'reviewer': 'A dancer'},
            'review_status': 'AUTHOR_REVIEWED',
            'links': [{'label': 'Right foot teacher', 'url': 'https://example.org/right'}],
            'attachments': [{'id': 'pic-1', 'caption': 'Original right foot'}]}


def test_save_retains_frozen_data_and_insertions_are_independent():
    original = written()
    saved = store.create('A favorite eight', [original])
    original['events'][0]['text'] = 'Changed outside the store'
    saved['moves'][0]['review']['status'] = 'Tampered result'
    first = store.insertion(saved['id'], 1)
    second = store.insertion(saved['id'], 1)
    assert first['moves'][0]['id'] != second['moves'][0]['id'] != 'my-occurrence'
    assert first['moves'][0]['snapshot_id'] == 'written@1'
    assert first['moves'][0]['definition_hash'] == 'a' * 64
    assert first['moves'][0]['review']['status'] == 'AUTHOR_REVIEWED'
    assert first['moves'][0]['phrase_origin']['source_occurrence_id'] == 'my-occurrence'
    first['moves'][0]['events'][0]['text'] = 'An edited dance copy'
    assert store.get(saved['id'])['moves'][0]['events'][0]['text'].startswith('Step R')
    renamed = store.update(saved['id'], 1, {'name': 'New title', 'favorite': True})
    assert renamed['version'] == 2
    assert second['name'] == 'A favorite eight'
    assert store.get(saved['id'], 1)['name'] == 'A favorite eight'


def test_exact_thirds_and_half_counts_retain_offsets():
    move = written()
    move['events'] = [
        {'offset_counts': '0', 'duration_counts': '1/3', 'text': 'First'},
        {'offset_counts': '1/3', 'duration_counts': '1/6', 'text': 'Second'},
        {'offset_counts': '1/2', 'duration_counts': '15/2', 'text': 'Last'}]
    result = store.create('Exact rhythm', [move])
    assert result['moves'][0]['events'] == move['events']
    compiled = compile_choreography(result['moves'])
    assert compiled['total_counts'] == '8'
    assert compiled['status'] == 'UNVERIFIED'


@pytest.mark.parametrize('duration', ['7', '17/2', '-8', '0', '1/0', float('nan'), True, None])
def test_reject_inexact_or_invalid_selection(duration):
    with pytest.raises(ValueError):
        store.create('Bad counts', [written(duration)])


def test_event_boundaries_and_missing_snapshots_rejected():
    move = written()
    move['events'][0]['offset_counts'] = '1/2'
    with pytest.raises(ValueError, match='overlapping'):
        store.create('Gap', [move])
    move = written()
    move['events'][0]['duration_counts'] = '7'
    with pytest.raises(ValueError, match='does not match'):
        store.create('Mismatch', [move])
    with pytest.raises(ValueError, match='missing its frozen'):
        store.create('Missing', [{'snapshot_id': 'x', 'counts': 8}])
    with pytest.raises(ValueError, match='full move definitions'):
        store.create('Live lookup', [{'move_id': 'vine', 'counts': 8}])


def test_stale_edits_archiving_and_restoring_are_versioned():
    saved = store.create('Keep this', [written()])
    updated = store.update(saved['id'], 1, {'archived': True})
    assert not store.list_phrases()['phrases']
    assert store.list_phrases(True)['phrases'][0]['archived']
    with pytest.raises(store.Conflict):
        store.update(saved['id'], 1, {'name': 'Stale change'})
    with pytest.raises(store.Conflict):
        store.insertion(saved['id'], 1)
    with pytest.raises(store.Conflict, match='Restore'):
        store.insertion(saved['id'], updated['version'])
    restored = store.update(saved['id'], 2, {'archived': False})
    assert restored['version'] == 3
    assert store.insertion(saved['id'], 3)['duration_counts'] == '8'


def test_concurrent_compare_and_swap_allows_one_writer():
    saved = store.create('Original', [written()])
    def change_name(name):
        try:
            return store.update(saved['id'], 1, {'name': name})['name']
        except store.Conflict:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(change_name, ['First writer', 'Second writer']))
    assert outcomes.count('conflict') == 1
    assert store.get(saved['id'])['version'] == 2


def test_mirror_changes_mechanics_but_retains_sources_and_original_review():
    move = written()
    record = store.create('Quarter turn', [move])
    reflected = store.insertion(record['id'], 1, True)['moves'][0]
    event = reflected['events'][0]
    assert event['text'] == 'Step L to the left facing 9:00'
    assert event['support_before'] == 'R' and event['support_after'] == 'L'
    assert event['moving_foot'] == 'L'
    assert event['rotation_deg'] == '-90' and event['facing_after_deg'] == '270'
    assert reflected['travel'] == 'W' and reflected['start_free_foot'] == 'L'
    assert reflected['net_rotation_deg'] == '-90'
    assert reflected['links'] == move['links'] and reflected['attachments'] == move['attachments']
    assert reflected['review'] == move['review']
    assert reflected['review_status'] == 'MIRRORED_REVIEW_PENDING'
    assert reflected['phrase_origin']['original_review_status'] == 'AUTHOR_REVIEWED'
    assert reflected['phrase_origin']['source_snapshot_id'] == move['snapshot_id']
    assert reflected['generator_eligible'] is False
    assert store.get(record['id'])['moves'] == [move]


def test_unknown_support_rotation_and_extra_provenance_not_invented():
    move = written()
    event = move['events'][0]
    event.update({'support_before': 'unknown', 'support_after': 'unknown', 'rotation_deg': None})
    move['net_rotation_deg'] = None
    move['start_free_foot'] = None
    result = store.mirror_move(move)
    assert result['events'][0]['support_before'] == 'unknown'
    assert result['events'][0]['support_after'] == 'unknown'
    assert result['events'][0]['rotation_deg'] is None
    assert result['net_rotation_deg'] is None and result['start_free_foot'] is None


def test_mirror_refuses_unrecognized_payload_without_losing_it():
    move = written()
    move['body_path'] = [{'x': 1, 'y': 2}]
    record = store.create('Future format', [move])
    with pytest.raises(ValueError, match='body_path'):
        store.insertion(record['id'], 1, True)
    assert store.insertion(record['id'], 1)['moves'][0]['body_path'] == move['body_path']
    move = written()
    move['events'][0]['text'] = 'Start facing the diagonal at 45 degrees'
    with pytest.raises(ValueError, match='absolute facing'):
        store.mirror_move(move)


def test_nested_definitions_and_fraction_objects_are_not_flattened():
    definition = written()
    definition.pop('snapshot_id')
    definition['events'][0]['duration_counts'] = {'numerator': 16, 'denominator': 2}
    row = {'id': 'wrapper', 'definition': definition}
    record = store.create('Nested', [row])
    inserted = store.insertion(record['id'], 1, True)['moves'][0]
    assert inserted['definition']['events'][0]['duration_counts'] == {'numerator': 16, 'denominator': 2}
    assert inserted['definition']['start_free_foot'] == 'L'
    assert compile_choreography([inserted])['total_counts'] == '8'


def test_legacy_mirrors_match_existing_library_footwork():
    library = library_json()
    for original in (row for row in library if row['lead'] == 'R'):
        expected = next(row for row in library if row['lead'] == 'L' and row['move_id'] == original['move_id'])
        result = store.mirror_move(original)
        for key in ('start', 'end', 'rot', 'travel', 'lead', 'counts'):
            assert result[key] == expected[key], (original['move_id'], key)
        assert [line['beats'] for line in result['lines']] == [line['beats'] for line in expected['lines']]


def test_real_expanded_eight_count_pattern_mirrors_exactly():
    row = next(item for item in variants() if item['lead'] == 'R' and item['group'] == 'Figure-eight turn')
    saved = store.create('Figure eight', [row])
    mirrored = store.insertion(saved['id'], 1, True)['moves'][0]
    assert len(mirrored['events']) == len(row['events'])
    assert [event['duration_counts'] for event in mirrored['events']] == [event['duration_counts'] for event in row['events']]
    assert sum(int(event['rotation_deg']) for event in mirrored['events']) == -360
    report = compile_choreography({'start': {'free_foot': 'L', 'facing_deg': '0'}, 'parts': [{'id': 'A', 'moves': [mirrored]}], 'routine': [{'part_id': 'A'}]})
    assert report['total_counts'] == '8'
    assert report['status'] == 'VALID'


def test_sqlite_backup_captures_current_and_history(tmp_path):
    saved = store.create('Original', [written()])
    store.update(saved['id'], 1, {'name': 'Renamed'})
    target = tmp_path / 'copy.sqlite3'
    with sqlite3.connect(store.directory() / 'phrases.sqlite3') as source, sqlite3.connect(target) as dest:
        source.backup(dest)
    with sqlite3.connect(target) as copied:
        assert copied.execute('SELECT count(*) FROM records').fetchone()[0] == 1
        assert copied.execute('SELECT count(*) FROM versions').fetchone()[0] == 2
    assert store.validate_record(store.get(saved['id']))['name'] == 'Renamed'


@pytest.mark.parametrize('bad', [{'api_key': 'example'}, {'nested': [{'password': 'example'}]}, {'api_key_protected': 'example'}, {'credentials': {'key': 'example'}}])
def test_credentials_rejected(bad):
    move = written(); move.update(bad)
    with pytest.raises(ValueError, match='credentials'):
        store.create('Private', [move])


def test_api_stale_versions_strict_fields_and_independent_insertion():
    app = FastAPI(); app.include_router(router)
    with TestClient(app) as client:
        created = client.post('/api/creator/phrases', json={'name': 'API eight', 'moves': [written()]})
        assert created.status_code == 201
        row = created.json(); url = '/api/creator/phrases/' + row['id']
        assert client.patch(url, json={'expected_version': True, 'fields': {'favorite': True}}).status_code == 422
        assert client.patch(url, json={'expected_version': 1, 'fields': {'moves': []}}).status_code == 422
        assert client.patch(url, json={'expected_version': 1, 'fields': {'favorite': True}}).status_code == 200
        assert client.post(url + '/insertion', json={'expected_version': 1}).status_code == 409
        inserted = client.post(url + '/insertion', json={'expected_version': 2, 'mirrored': True})
        assert inserted.status_code == 200
        assert inserted.json()['moves'][0]['id'] != row['moves'][0]['id']
        assert client.get('/api/creator/phrases').json()['phrases'][0]['favorite'] is True
        assert client.get('/api/creator/phrases/../../file').status_code == 404


@pytest.mark.parametrize('format_name', ['json', 'zip'])
def test_portable_roundtrip_keeps_phrase_ancestry_and_source_metadata(format_name):
    from engine.creator_exports import export_project, read_project_package
    saved = store.create('Turn eight', [written()])
    inserted = store.insertion(saved['id'], 1, True)['moves']
    another = store.create('Reuse eight', inserted)
    second = store.insertion(another['id'], 1)['moves']
    project = {'name': 'Phrase portability', 'draft': {'choreography': {
        'start': {'free_foot': 'L', 'facing_deg': '0'},
        'parts': [{'id': 'A', 'moves': second}], 'routine': [{'part_id': 'A'}]}}}
    payload, _, filename = export_project(project, format_name)
    package = read_project_package(payload, filename)
    restored = package['draft']['choreography']['parts'][0]['moves'][0]
    assert restored['phrase_origin'] == second[0]['phrase_origin']
    assert restored['review_status'] == 'MIRRORED_REVIEW_PENDING'
    assert restored['snapshot_id'] == 'written@1'
    assert restored['definition_hash'] == 'a' * 64
    assert restored['source_hash'] == 'b' * 64
    assert restored['events'][0]['rotation_deg'] == '-90'
    assert restored['events'][0]['support_after'] == 'L'
    assert restored['links'] == second[0]['links']


def test_portable_phrase_metadata_rejects_depth_and_redacts_extra_private_fields():
    from engine.creator_exports import _phrase_origin, ExportError
    origin = {'phrase_id': 'phrase-example', 'version': 1, 'name': r'C:\Private\My phrase',
              'api_key': 'private-example', 'path': r'C:\Private\data'}
    assert _phrase_origin(origin) == {'phrase_id': 'phrase-example', 'version': 1, 'name': 'My phrase'}
    for _ in range(18):
        origin = {'prior_phrase_origin': origin}
    with pytest.raises(ExportError, match='ancestry'):
        _phrase_origin(origin)
