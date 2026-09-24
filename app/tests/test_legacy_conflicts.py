"""Legacy revision guards and atomic full-draft tutorial/lyric application."""
import copy
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
from engine import project as store, tutorial
from test_tutorial_api import _project_with_ready_sources


@pytest.mark.parametrize('endpoint,body', [('lyrics',{'text':'Changed'}),('sections',{'sections':[]}),('meta',{'description':'Changed'}),('tutorial',{'segments':[]})])
def test_legacy_stale_revision_rejected_before_any_write(tmp_path,monkeypatch,endpoint,body):
    monkeypatch.setattr(store,'PROJECTS_DIR',str(tmp_path/'projects'))
    project=store.create_project('Revision fixture')
    before=store.load_project(project['id'])
    with TestClient(server.app) as client:
        response=client.put(f"/api/projects/{project['id']}/{endpoint}",json={**body,'expected_revision':0})
        assert response.status_code == 409
        assert store.load_project(project['id']) == before
        assert client.put(f"/api/projects/{project['id']}/{endpoint}",json={**body,'expected_revision':True}).status_code == 422


def built(tmp_path,monkeypatch):
    project=_project_with_ready_sources(tmp_path,monkeypatch)
    server.build_tutorial(project['id'],server.TutorialBuildBody())
    return store.load_project(project['id'])


def edits(plan):
    return {'provenance_hash':plan['provenance_hash'],
            'segments':[{'id':segment['id'],'callout':segment['callout']['text'],'camera':segment['camera']['primary'],'confirmed':True,'review_note':'Reviewed synthetic cue'} for segment in plan['segments']],
            'count_in':'Ready, five, six, seven, eight','voice_notes':'Speak plainly','producer_notes':'Use the rear view','tempo_grid_confirmed':True}


def test_whole_draft_save_applies_tutorial_edits_through_engine_with_valid_hashes(tmp_path,monkeypatch):
    project=built(tmp_path,monkeypatch);changes=edits(project['tutorial'])
    changes['segments'][0].update(callout='Step right',camera='overhead_feet')
    with TestClient(server.app) as client:
        response=client.put(f"/api/projects/{project['id']}/workspace",json={'expected_revision':project['document_revision'],
            'draft':{'sheet_meta':{'description':'Entire form saved'},'tutorial_edits':changes}})
        assert response.status_code == 200
    saved=store.load_project(project['id']);plan=saved['tutorial']
    assert saved['dance'] == project['dance']
    assert plan['segments'][0]['callout']['text'] == 'Step right'
    assert plan['segments'][0]['camera']['primary'] == 'overhead_feet'
    assert plan['segments'][0]['confirmed'] and plan['segments'][0]['confirmation_fingerprint']
    assert plan['settings']['voice_notes'] == 'Speak plainly' and plan['settings']['tempo_grid_confirmed'] is True
    assert 'voice_notes' not in plan and 'tutorial_edits' not in saved['draft']
    assert tutorial.update_tutorial_plan(plan,[])['provenance_hash']
    assert saved['draft']['tutorial'] == plan


@pytest.mark.parametrize('failure',['camera','provenance','segment'])
def test_bad_tutorial_edit_aborts_entire_draft_save(tmp_path,monkeypatch,failure):
    project=built(tmp_path,monkeypatch);changes=edits(project['tutorial'])
    if failure=='camera':changes['segments'][0]['camera']='made_up_camera'
    elif failure=='provenance':changes['provenance_hash']='stale'
    else:changes['segments'][0]['id']='unknown-segment'
    with TestClient(server.app) as client:
        response=client.put(f"/api/projects/{project['id']}/workspace",json={'expected_revision':project['document_revision'],
            'draft':{'lyrics_raw':'[Verse]\nMust not be saved','sheet_meta':{'description':'Must not be saved'},'tutorial_edits':changes}})
        assert response.status_code == 422
    assert store.load_project(project['id']) == project


def test_whole_draft_lyric_and_section_changes_rebuild_tags_and_stale_derivatives(tmp_path,monkeypatch):
    project=built(tmp_path,monkeypatch)
    project['alignment']={'status':'done'};project['lyric_move_draft']={'status':'READY'};store.save_project(project['id'],project)
    before=copy.deepcopy(project['dance'])
    result=store.save_workspace(project['id'],{'lyrics_raw':'[Verse 1]\nSynthetic first verse\n[Chorus]\nSynthetic chorus',
        'sections':[{'label':'Verse 1','start':0,'end':8}], 'tutorial_edits':edits(project['tutorial'])},project['document_revision'])
    saved=store.load_project(project['id'])
    assert [section['label'] for section in saved['lyric_sections']] == ['Verse 1','Chorus']
    assert result['draft']['lyric_sections'] == saved['lyric_sections']
    assert saved['alignment'] is None and saved['phrase'] is None
    assert saved['tutorial']['status'] == 'STALE' and saved['draft']['tutorial']['status'] == 'STALE'
    assert saved['lyric_move_draft']['status'] == 'STALE' and saved['dance'] == before
