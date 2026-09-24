import copy
import os
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.music_map import count_to_seconds, seconds_to_count, validate_map, estimate_key
from engine import project as store
from engine.steps import library_json
from fastapi.testclient import TestClient
import server


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store,'PROJECTS_DIR', str(tmp_path/'projects'))
    return TestClient(server.app)


def document():
    moves=[copy.deepcopy(m) for m in library_json() if m['move_id']=='rocking_chair' and m['lead']=='R']
    if not moves:
        moves=[{'name':'Rocking chair','counts':4,'start':'R','end':'R','rot':0,'lines':[]}]
    moves[0]['id']='m1'
    return {'schema_version':1,'start':{'free_foot':'R','support':'L','facing_deg':'0'},
            'parts':[{'id':'A','name':'Main','moves':moves}], 'routine':[{'id':'r1','part_id':'A','repeat':2}]}


def test_manual_without_music_ai_save_accept_restore(client):
    pid=client.post('/api/projects',json={'name':'Offline test'}).json()['id']
    w=client.get(f'/api/projects/{pid}/workspace').json()
    draft={'choreography':document(),'music_map':{'bpm':120,'first_count':3,'meter':4},'sheet_meta':{'dance_title':'A revised title'}}
    result=client.put(f'/api/projects/{pid}/workspace',json={'expected_revision':w['document_revision'],'draft':draft})
    assert result.status_code==200
    revision=result.json()['document_revision']
    p=store.load_project(pid)
    assert p['dance']=={}
    assert p['draft']['choreography']==document()
    compiled=client.post('/api/creator/compile',json={'document':document()}).json()
    assert compiled['status']=='VALID' and compiled['total_counts']=='8'
    accepted=client.post(f'/api/creator/projects/{pid}/accept',json={'expected_revision':revision})
    assert accepted.status_code==200
    old=store.load_project(pid)['accepted_choreography_hash']
    assert client.post(f'/api/creator/projects/{pid}/accept',json={'expected_revision':revision}).status_code==409
    w=client.get(f'/api/projects/{pid}/workspace').json()
    draft['choreography']['routine'][0]['repeat']=3
    assert client.put(f'/api/projects/{pid}/workspace',json={'expected_revision':w['document_revision'],'draft':draft}).status_code==200
    assert store.load_project(pid)['accepted_choreography_hash']==old


@pytest.mark.parametrize('raw', [{'bpm':0},{'bpm':500},{'bpm':float('inf')},{'first_count':-1},{'anchors':[{'count':0,'time':3},{'count':4,'time':2}]},{'anchors':[{'count':0,'time':1},{'count':0,'time':2}]},{'meter':5}])
def test_invalid_music_maps_rejected(raw):
    with pytest.raises(ValueError):validate_map(raw)


@pytest.mark.parametrize('count', [-4,0,0.25,1,8,16,24,32,40])
def test_variable_timing_roundtrip(count):
    timing={'bpm':120,'first_count':3,'anchors':[{'count':0,'time':3},{'count':16,'time':11},{'count':32,'time':21}]}
    assert seconds_to_count(count_to_seconds(count,timing),timing)==pytest.approx(count)
    assert count_to_seconds(24,timing)==16


def test_draft_bad_timing_does_not_replace_good_data(client):
    pid=client.post('/api/projects',json={'name':'Timing test'}).json()['id']
    before=store.load_project(pid)
    result=client.put(f'/api/projects/{pid}/workspace',json={'expected_revision':before['document_revision'],'draft':{'music_map':{'bpm':-20}}})
    assert result.status_code==422
    assert store.load_project(pid)==before


def test_lyrics_edit_invalidates_derived_work_but_keeps_accepted(client):
    pid=client.post('/api/projects',json={'name':'Lyrics test'}).json()['id']
    p=store.load_project(pid);p['alignment']={'status':'done'};p['lyric_move_draft']={'status':'READY'};p['dance']={'legacy':'accepted'};store.save_project(pid,p)
    store.save_workspace(pid,{'lyrics_raw':'Changed lyric'},p['document_revision'])
    p=store.load_project(pid)
    assert p['alignment'] is None and p['lyric_move_draft']['status']=='STALE'
    assert p['dance']=={'legacy':'accepted'}


def test_static_navigation_and_catalog_preserved(client):
    assert 'creator.js' in client.get('/dance').text
    assert 'app.js' in client.get('/legacy').text
    assert client.get('/repair').status_code==200
    catalog=client.get('/api/creator/catalog').json()
    assert len(catalog['steps'])==216
    assert len(client.get('/api/steps').json())>=78
    html=client.get('/dance').text
    assert 'https://www.youtube.com/@HillbillyHellfire' in html
    assert '<iframe' not in html


def test_key_silence_is_uncertain(tmp_path):
    import numpy as np
    import soundfile as sf
    path=tmp_path/'silence.wav';sf.write(path,np.zeros(44100),22050)
    result=estimate_key(path)
    assert result['confidence']=='insufficient' and result['key']==''
