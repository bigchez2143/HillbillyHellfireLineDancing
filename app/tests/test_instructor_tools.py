"""S08 local state, calendar meaning and default-public export boundaries."""
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from icalendar import Calendar

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import instructor_tools as tools
from instructor_api import router


@pytest.fixture
def location(tmp_path, monkeypatch):
    path = tmp_path / 'private tools'
    monkeypatch.setenv('LINE_DANCE_TOOLS_DIR', str(path))
    return path


@pytest.fixture
def state():
    return {'schema_version':1, 'dances':[{
        'id':'d1','title':'<script>bad()</script> & Dance','favorite':True,'tags':['practice'],
        'learning_status':'learning','public_notes':'Share this','private_notes':'PRIVATE-DANCE',
        'checklist':[{'id':'c1','label':'Try the tag','done':False}],
        'practice_history':[{'id':'h1','at':'2026-09-04T09:00:00-04:00','duration_minutes':20,'notes':'PRIVATE-HISTORY'}],
        'recordings':[{'id':'r1','title':'Original','local_path':'C:/secret/song.wav','music_map':{'bpm':120,'first_count':4},'choreography_review':'compatible'},
                      {'id':'r2','title':'Alternative','music_map':{'bpm':120,'first_count':19}}]}],
        'setlists':[{'id':'class1','title':'<Class>','public_notes':'Welcome','private_notes':'PRIVATE-CLASS',
                     'items':[{'dance_id':'d1','recording_id':'r1','duration_minutes':15,'public_notes':'Start slowly','private_notes':'PRIVATE-ITEM'},
                              {'dance_id':'d1','recording_id':'r2','duration_minutes':5}]}],
        'events':[{'id':'e1','title':'Weekly class','start':'2026-03-01T19:00:00','end':'2026-03-01T20:00:00',
                   'timezone':'America/New_York','rrule':'FREQ=WEEKLY;COUNT=3','location':'Hall, Room; 2',
                   'public_notes':'Public\nBring shoes','private_notes':'PRIVATE-EVENT'}]}


@pytest.fixture
def client(location):
    app = FastAPI(); app.include_router(router)
    with TestClient(app) as client:
        yield client


def test_round_trip_independent_recordings_and_checklists(location, state):
    saved = tools.save_state(state, 0)
    reopened = tools.get_state()
    assert reopened == saved and reopened['revision'] == 1
    dance = reopened['dances'][0]
    assert dance['favorite'] and dance['practice_history'][0]['notes'] == 'PRIVATE-HISTORY'
    assert dance['recordings'][1]['choreography_review'] == 'not_reviewed'
    dance['recordings'][1]['music_map']['bpm'] = 70
    updated = tools.save_state(reopened, 1)
    assert updated['dances'][0]['recordings'][0]['music_map'] == {'bpm':120,'first_count':4}
    assert json.loads((location/'state.backup.json').read_text())['revision'] == 1


def test_thread_cas_accepts_one_winner(location, state):
    tools.save_state(state, 0)
    def save(_):
        try:
            return tools.save_state(state, 1)['revision']
        except tools.Conflict:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(workers.map(save, range(4)))
    assert results.count(2) == 1 and results.count('conflict') == 3


def test_process_cas_accepts_one_winner(location, state):
    tools.save_state(state, 0)
    code = "import json,sys;sys.path.insert(0,sys.argv[1]);from engine import instructor_tools as s\ntry:\n print(s.save_state(s.get_state(),1)['revision'])\nexcept s.Conflict:\n print('conflict')"
    processes = [subprocess.Popen([sys.executable,'-c',code,str(Path(__file__).resolve().parents[1])],
                                 stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=os.environ.copy()) for _ in range(3)]
    results=[]
    for process in processes:
        stdout,stderr=process.communicate(timeout=30)
        assert process.returncode==0,stderr
        results.append(stdout.strip())
    assert results.count('2')==1 and results.count('conflict')==2


def test_failed_replace_and_corrupt_state_preserve_last_save(location, state, monkeypatch):
    tools.save_state(state, 0)
    before=(location/'state.json').read_bytes()
    original=tools.os.replace
    def fail(source, target):
        if Path(target).name=='state.json':
            raise OSError('Simulated storage failure')
        original(source,target)
    monkeypatch.setattr(tools.os,'replace',fail)
    with pytest.raises(OSError):
        tools.save_state(state,1)
    assert (location/'state.json').read_bytes()==before
    assert not list(location.glob('.state-*.tmp'))
    (location/'state.json').write_text('{corrupt')
    with pytest.raises(tools.Corrupt):
        tools.save_state(state,1)
    assert (location/'state.json').read_text()=='{corrupt'


def test_guide_escapes_html_and_defaults_to_public(location,state):
    tools.save_state(state,0)
    public=tools.class_guide('class1')
    assert '&lt;script&gt;' in public and '<script>' not in public
    assert '20 minutes' in public and public.index('Original') < public.index('Alternative')
    assert 'PRIVATE' not in public and 'C:/secret' not in public
    private=tools.class_guide('class1',True,False)
    assert 'PRIVATE INSTRUCTOR COPY' in private and 'PRIVATE-DANCE' in private and 'PRIVATE-ITEM' in private
    assert 'C:/secret' not in private


def test_ics_dst_recurrence_and_escaping_round_trip(location,state):
    state['events'][0]['title']='Dance, class; \\ party é'*12
    tools.save_state(state,0)
    data=tools.export_ics()
    assert b'PRIVATE-EVENT' not in data
    assert b'VTIMEZONE' in data and b'RRULE:FREQ=WEEKLY;COUNT=3' in data
    assert all(len(line)<=75 for line in data.split(b'\r\n'))
    parsed=tools.parse_ics(data.decode())
    assert parsed[0].title==state['events'][0]['title']
    assert parsed[0].public_notes=='Public\nBring shoes'
    times=tools.recurrence_times(tools.local_time(parsed[0].start,parsed[0].timezone),parsed[0].rrule)
    assert [x.hour for x in times]==[19,19,19]
    assert [x.astimezone(timezone.utc).hour for x in times]==[0,23,23]
    assert b'PRIVATE-EVENT' in tools.export_ics(True)


@pytest.mark.parametrize('start,end',[
    ('2026-03-08T02:30:00','2026-03-08T03:30:00'),
    ('2026-11-01T01:30:00','2026-11-01T02:30:00'),
    ('2026-03-01T19:00:00-03:00','2026-03-01T20:00:00-03:00')])
def test_gap_fold_and_wrong_offset_require_review(start,end):
    with pytest.raises(ValueError):
        tools.LocalEvent(id='x',title='Class',start=start,end=end,timezone='America/New_York')


def test_explicit_fold_is_preserved_as_utc_in_export(location):
    state={'dances':[],'setlists':[],'events':[{'id':'fold','title':'Late class','start':'2026-11-01T01:30:00-05:00',
        'end':'2026-11-01T02:30:00-05:00','timezone':'America/New_York'}]}
    tools.save_state(state,0)
    data=tools.export_ics()
    assert b'DTSTART:20261101T063000Z' in data
    assert tools.parse_ics(data.decode())[0].start=='2026-11-01T01:30:00-05:00'


@pytest.mark.parametrize('rule',['FREQ=MONTHLY;COUNT=2','FREQ=WEEKLY','FREQ=DAILY;COUNT=1000',
    'FREQ=WEEKLY;COUNT=2;BYSETPOS=1','FREQ=DAILY;COUNT=2;UNTIL=20260501T000000Z'])
def test_unsupported_recurrence_is_rejected(rule):
    with pytest.raises(ValueError):
        tools.recurrence_times(tools.local_time('2026-03-01T19:00:00','America/New_York'),rule)


def test_import_preview_commit_and_cancellation_preserve_private_notes(location,state):
    tools.save_state(state,0)
    calendar=Calendar.from_ical(tools.export_ics())
    event=calendar.walk('VEVENT')[0]
    event['STATUS']='CANCELLED'; event['SEQUENCE']=1
    text=calendar.to_ical().decode()
    preview=tools.import_ics(text,1)
    assert preview['changes'][0]['action']=='update' and not preview['applied']
    assert tools.get_state()['events'][0]['status']=='CONFIRMED'
    with pytest.raises(ValueError):
        tools.import_ics(text,1,True,'wrong')
    result=tools.import_ics(text,1,True,preview['preview_token'])
    assert result['state']['events'][0]['status']=='CANCELLED'
    assert result['state']['events'][0]['private_notes']=='PRIVATE-EVENT'
    with pytest.raises(tools.Conflict):
        tools.import_ics(text,1,True,preview['preview_token'])


def test_import_does_not_drop_unsupported_semantics(location,state):
    tools.save_state(state,0)
    calendar=Calendar.from_ical(tools.export_ics())
    calendar.walk('VEVENT')[0].add('exdate',datetime(2026,3,8,19,tzinfo=tools.ZoneInfo('America/New_York')))
    with pytest.raises(ValueError,match='Unsupported'):
        tools.parse_ics(calendar.to_ical().decode())
    assert tools.get_state()['revision']==1


def test_api_cas_and_safe_defaults(client,state):
    assert client.get('/api/creator/tools').json()['revision']==0
    saved=client.put('/api/creator/tools',json={'expected_revision':0,'state':state})
    assert saved.status_code==200
    assert client.put('/api/creator/tools',json={'expected_revision':0,'state':state}).status_code==409
    assert client.put('/api/creator/tools',json={'expected_revision':True,'state':state}).status_code==422
    assert 'PRIVATE' not in client.get('/api/creator/tools/setlists/class1/guide.html').text
    assert client.get('/api/creator/tools/events.ics').headers['content-type'].startswith('text/calendar')
    assert client.get('/api/creator/tools/setlists/missing/guide.txt').status_code==404


def test_missing_references_and_unknown_fields_do_not_erase_data(location,state):
    tools.save_state(state,0)
    invalid=copy.deepcopy(state); invalid['dances']=[]
    with pytest.raises(ValueError):
        tools.save_state(invalid,1)
    invalid=copy.deepcopy(state); invalid['future_unknown']='cannot silently drop'
    with pytest.raises(ValueError):
        tools.save_state(invalid,1)
    assert tools.get_state()['revision']==1


def test_private_calendar_note_remains_private_after_import(location,state):
    tools.save_state(state,0)
    parsed=tools.parse_ics(tools.export_ics(True).decode())[0]
    assert parsed.private_notes=='PRIVATE-EVENT'
    assert 'PRIVATE-EVENT' not in parsed.public_notes


def test_manual_calendar_update_increments_sequence(location,state):
    saved=tools.save_state(state,0)
    saved['events'][0]['status']='CANCELLED'
    updated=tools.save_state(saved,1)
    assert updated['events'][0]['sequence']==1


def test_recurrence_end_cannot_fall_in_dst_gap():
    with pytest.raises(ValueError,match='does not exist'):
        tools.LocalEvent(id='gap',title='Early class',start='2026-03-01T01:30:00',end='2026-03-01T02:30:00',
                         timezone='America/New_York',rrule='FREQ=WEEKLY;COUNT=2')


def test_alternate_calendar_scale_and_private_classification_rejected(location,state):
    tools.save_state(state,0)
    calendar=Calendar.from_ical(tools.export_ics())
    calendar['CALSCALE']='OTHER'
    with pytest.raises(ValueError,match='Gregorian'):
        tools.parse_ics(calendar.to_ical().decode())
    calendar['CALSCALE']='GREGORIAN'
    calendar.walk('VEVENT')[0].add('class','PRIVATE')
    with pytest.raises(ValueError,match='Private'):
        tools.parse_ics(calendar.to_ical().decode())


def test_embedded_timezone_conflict_is_not_silently_ignored(location,state):
    from datetime import timedelta
    tools.save_state(state,0)
    calendar=Calendar.from_ical(tools.export_ics())
    for component in calendar.walk('STANDARD'):
        component['TZOFFSETTO']=tools.Timezone.from_tzinfo(tools.ZoneInfo('Asia/Tokyo')).walk('STANDARD')[0]['TZOFFSETTO']
    with pytest.raises(ValueError,match='offsets disagree'):
        tools.parse_ics(calendar.to_ical().decode())


def test_sheet_and_video_links_are_clickable_and_safely_escaped(location,state):
    state['dances'][0]['sheet_url']='https://example.com/sheet?q="a"&mode=print'
    state['dances'][0]['video_url']='https://example.com/video'
    tools.save_state(state,0)
    result=tools.class_guide('class1')
    assert 'href="https://example.com/sheet?q=&quot;a&quot;&amp;mode=print"' in result
    assert 'rel="noopener noreferrer"' in result
    assert 'Demo video</a>' in result


@pytest.mark.parametrize('url',['javascript:alert(1)','file:///C:/secret.pdf','https://user:password@example.com/a','https://example.com/\r\nscript'])
def test_unsafe_external_links_are_rejected(state,url):
    state['dances'][0]['sheet_url']=url
    with pytest.raises(ValueError,match='http or https'):
        tools.State.model_validate(state)


def test_music_map_nonfinite_numbers_cannot_silently_become_null(state):
    state['dances'][0]['recordings'][0]['music_map']['bpm']=float('nan')
    with pytest.raises(ValueError,match='finite JSON'):
        tools.State.model_validate(state)


def test_calendar_property_parameters_are_not_silently_dropped(location,state):
    tools.save_state(state,0)
    calendar=Calendar.from_ical(tools.export_ics())
    calendar.walk('VEVENT')[0]['SUMMARY'].params['ALTREP']='https://example.com/meaningful-note'
    with pytest.raises(ValueError,match='parameters'):
        tools.parse_ics(calendar.to_ical().decode())
