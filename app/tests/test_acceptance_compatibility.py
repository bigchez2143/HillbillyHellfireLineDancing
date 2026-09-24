"""Accepted legacy views and explicit lyric portability; synthetic local data only."""
import copy
import json
from pathlib import Path
import sys

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import project as store, steps
from engine.assembler import assemble
from engine.choreography import compile_choreography
from engine.creator_exports import export_project, read_project_package, preview_project_package, restore_project_package
import creator_api
import server


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'PROJECTS_DIR', str(tmp_path / 'projects'))
    monkeypatch.setattr(steps, 'CUSTOM_MOVES_PATH', str(tmp_path / 'custom-moves.json'))
    with TestClient(server.app) as value:
        yield value


def document(moves=None, start='R'):
    moves=[copy.deepcopy(move) for move in (moves or [steps.get_move('rocking_chair').variant(start)])]
    for index, move in enumerate(moves):
        move['id']=f'move-{index+1}'
    return {'schema_version':1, 'start':{'free_foot':start, 'facing_deg':'0'},
            'parts':[{'id':'A', 'name':'Main part', 'moves':moves}],
            'routine':[{'id':'run-A', 'part_id':'A', 'repeat':1}]}


def saved(doc, **extra):
    project=store.create_project('Acceptance fixture', 'Synthetic instrumental', 'Test author')
    workspace=store.save_workspace(project['id'], {'choreography':doc, 'music_map':{'bpm':113}, **extra}, project['document_revision'])
    return project['id'], workspace['document_revision']


@pytest.mark.parametrize('start', ['R', 'L'])
def test_simple_accepted_builtin_reaches_legacy_tools_with_same_counts_feet_and_walls(client, start):
    doc=document(start=start)
    pid, revision=saved(doc)
    response=client.post(f'/api/creator/projects/{pid}/accept', json={'expected_revision':revision})
    assert response.status_code == 200 and response.json()['legacy_compatible'] is True
    project=store.load_project(pid)
    current=server._current_dance(project)
    assert current['total_counts'] == 4 and current['walls'] == 1 and current['net_rot'] == 0
    assert current['validation']['valid'] and current['validation']['end_foot'] == start
    assert current['moves'] == doc['parts'][0]['moves']
    assert current['tempo']['bpm'] == 113
    expected=compile_choreography(doc)
    assert project['accepted_choreography'] == expected['normalized_document']
    assert project['accepted_choreography_hash'] == expected['source_hash']
    assert project['accepted_choreography_source'] == doc


def test_generated_candidate_is_frozen_without_losing_line_templates(client):
    candidate=assemble(total_counts=16, wall='2', turn_dir='L', level='AB', seed=23, k=1)['candidates'][0]
    doc=document(candidate['moves'])
    pid, revision=saved(doc)
    response=client.post(f'/api/creator/projects/{pid}/accept', json={'expected_revision':revision})
    assert response.status_code == 200 and response.json()['legacy_compatible']
    current=server._current_dance(store.load_project(pid))
    assert current['total_counts'] == 16 and current['walls'] == 2 and current['net_rot'] == 180
    assert current['validation']['valid'] and current['validation']['end_foot'] == 'R'
    assert [move['lines'] for move in current['moves']] == [move['lines'] for move in candidate['moves']]


def test_acceptance_is_immutable_after_draft_edits_and_rejects_stale_revision(client):
    pid, revision=saved(document())
    assert client.post(f'/api/creator/projects/{pid}/accept', json={'expected_revision':revision}).status_code == 200
    accepted=store.load_project(pid)
    assert client.post(f'/api/creator/projects/{pid}/accept', json={'expected_revision':revision}).status_code == 409
    edited=document(); edited['parts'][0]['moves'][0]['lines'][0]['text']='A later draft instruction'
    store.save_workspace(pid, {'choreography':edited}, accepted['document_revision'])
    after=store.load_project(pid)
    for key in ('accepted_choreography','accepted_choreography_hash','accepted_choreography_source','dance'):
        assert after[key] == accepted[key]
    assert server._current_dance(after) == server._current_dance(accepted)


def test_concurrent_save_during_compile_cannot_accept_mixed_revision(client, monkeypatch):
    pid, revision=saved(document())
    original=creator_api.compile_choreography
    def concurrent_compile(doc, snapshots=None):
        newer=store.load_project(pid)
        store.save_workspace(pid, {'sheet_meta':{'dance_title':'Saved by another window'}}, newer['document_revision'])
        return original(doc, snapshots)
    monkeypatch.setattr(creator_api,'compile_choreography',concurrent_compile)
    response=client.post(f'/api/creator/projects/{pid}/accept', json={'expected_revision':revision})
    assert response.status_code == 409
    after=store.load_project(pid)
    assert 'accepted_choreography' not in after and after['dance'] == {}
    assert after['draft']['sheet_meta']['dance_title'] == 'Saved by another window'


def test_deleted_custom_move_cannot_change_accepted_frozen_mechanics(client):
    steps.save_custom_move({'name':'Synthetic half turn', 'id':'custom-synthetic-half-turn', 'counts':4,
                            'rotation':180, 'start':'R', 'end':'R', 'level':'I',
                            'instructions':'Four authored counts with a half turn.', 'travel':''})
    concrete=steps.get_move('custom-synthetic-half-turn').variant('L')
    doc=document([concrete], start='L')
    pid, revision=saved(doc)
    assert client.post(f'/api/creator/projects/{pid}/accept', json={'expected_revision':revision}).json()['legacy_compatible']
    before=store.load_project(pid)
    expected=server._current_dance(before)
    steps.delete_custom_move('custom-synthetic-half-turn')
    assert steps.get_move('custom-synthetic-half-turn') is None
    after=store.load_project(pid)
    assert server._current_dance(after) == expected
    assert after['movement_snapshots'] == before['movement_snapshots']
    assert expected['total_counts'] == 4 and expected['walls'] == 2 and expected['net_rot'] == 180
    assert expected['validation']['valid'] and expected['validation']['end_foot'] == 'L'
    assert expected['moves'][0]['lines'] == concrete['lines']


@pytest.mark.parametrize('shape', ['multipart','repeated','restart','override','unverified','no_lines','irregular_meter'])
def test_nonrepresentable_graph_is_preserved_and_legacy_tools_explain_limit(client, shape):
    doc=document()
    if shape == 'multipart':
        tag=copy.deepcopy(doc['parts'][0]); tag.update(id='T',name='Tag',kind='tag')
        doc['parts'].append(tag); doc['routine'].append({'id':'tag','part_id':'T'})
    elif shape == 'repeated':
        doc['routine'][0]['repeat']=2
    elif shape == 'restart':
        doc['routine'][0].update(end_after_counts='4',reason='restart')
    elif shape == 'override':
        doc['routine'][0]['overrides']={'move-1':copy.deepcopy(doc['parts'][0]['moves'][0])}
    elif shape == 'unverified':
        doc['parts'][0]['moves']=[{'id':'personal','duration_counts':'1/2','text':'Unreviewed movement'}]
    elif shape == 'no_lines':
        doc['parts'][0]['moves'][0]['lines']=[]
    else:
        doc['meter']={'beats':6,'unit':8,'group_counts':6}
    expected=compile_choreography(doc)
    assert expected['valid']
    pid, revision=saved(doc)
    response=client.post(f'/api/creator/projects/{pid}/accept', json={'expected_revision':revision})
    assert response.status_code == 200 and response.json()['legacy_compatible'] is False
    accepted=store.load_project(pid)
    assert accepted['dance']['source'] == 'structured' and 'candidates' not in accepted['dance']
    assert accepted['accepted_choreography'] == expected['normalized_document']
    assert accepted['accepted_choreography_source'] == doc
    with pytest.raises(HTTPException, match='complete choreography format') as failure:
        server._current_dance(accepted)
    assert failure.value.status_code == 422


def test_invalid_draft_does_not_replace_previous_acceptance(client):
    pid, revision=saved(document())
    client.post(f'/api/creator/projects/{pid}/accept',json={'expected_revision':revision})
    before=store.load_project(pid)
    invalid=document(start='R'); invalid['parts'][0]['moves'][0]['start']='L'
    workspace=store.save_workspace(pid,{'choreography':invalid},before['document_revision'])
    response=client.post(f'/api/creator/projects/{pid}/accept',json={'expected_revision':workspace['document_revision']})
    assert response.status_code == 422
    assert store.load_project(pid)['dance'] == before['dance']


@pytest.mark.parametrize('format', ['json','zip'])
def test_native_lyrics_opt_in_retains_full_text_and_discloses_preview(client, format):
    lyrics=('Synthetic verse café, count one.\r\n\n' * 1500) + 'Exact final line\n'
    pid, revision=saved(document(), lyrics_raw=lyrics,
                         connection={'api_key':'PRIVATE-PROVIDER-KEY'},
                         sheet_meta={'dance_title':'Lyric fixture','api_key':'PRIVATE-PROVIDER-KEY'})
    project=store.load_project(pid)
    default=read_project_package(export_project(project,format)[0])
    assert 'lyrics_raw' not in default['draft'] and default['includes_lyrics'] is False
    assert 'Lyrics' in default['omitted'] and 'Project revision history' in default['omitted']
    response=client.get(f'/api/creator/projects/{pid}/export/{format}?include_lyrics=1')
    assert response.status_code == 200
    portable=read_project_package(response.content)
    assert portable['draft']['lyrics_raw'] == lyrics and portable['includes_lyrics'] is True
    assert 'Lyrics' not in portable['omitted']
    assert 'PRIVATE-PROVIDER-KEY' not in json.dumps(portable)
    preview=preview_project_package(response.content)
    assert preview['includes_lyrics'] is True and preview['lyrics_characters'] == len(lyrics)
    restored=restore_project_package(response.content)
    assert restored['id'] != pid
    loaded=store.load_project(restored['id'])
    assert loaded['lyrics_raw'] == lyrics and loaded['draft']['lyrics_raw'] == lyrics
    # An opt-in download is not a persistent preference for future downloads.
    next_download=read_project_package(client.get(f'/api/creator/projects/{pid}/export/{format}').content)
    assert 'lyrics_raw' not in next_download['draft']


def test_package_rejects_structured_lyrics_instead_of_importing_private_fields(client):
    pid, _=saved(document())
    package=read_project_package(export_project(store.load_project(pid),'json')[0])
    package['draft']['lyrics_raw']={'text':'Synthetic lyric','api_key':'PRIVATE-PROVIDER-KEY'}
    response=client.post('/api/creator/import/preview',files={'file':('bad.json',json.dumps(package).encode())})
    assert response.status_code == 400 and 'plain text' in response.json()['detail']
