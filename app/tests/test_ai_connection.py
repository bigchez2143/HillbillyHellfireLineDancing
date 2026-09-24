"""BYO-AI connection tests are fully offline and never need real credentials."""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import settings, ai_assistant
from ai_connection_api import router


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'SETTINGS_FILE', str(tmp_path / 'settings.json'))
    monkeypatch.setattr(settings, '_protect_for_current_windows_user', lambda value:'PROTECTED-FIXTURE:' + value)
    monkeypatch.setattr(settings, '_unprotect_for_current_windows_user', lambda value:value.removeprefix('PROTECTED-FIXTURE:'))
    monkeypatch.setattr(ai_assistant, 'urlopen', lambda *a, **k: (_ for _ in ()).throw(AssertionError('Unexpected network operation')))


def configured(**changes):
    value = {'enabled': True, 'provider': 'openai_compatible', 'base_url': 'https://example.ai/v1',
             'model': 'user-chosen-model', 'timeout_seconds': 60, 'api_key': 'FAKE-PRIVATE-KEY'}
    value.update(changes)
    return settings.save_ai_settings(value)


def client():
    app=FastAPI();app.include_router(router)
    return TestClient(app)


class Reply:
    def __init__(self, raw): self.raw=raw;self.requested_size=None
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, size): self.requested_size=size;return self.raw[:size]


def test_settings_get_is_offline_and_never_decrypts_or_exposes_credentials(monkeypatch):
    configured()
    monkeypatch.setattr(settings, '_unprotect_for_current_windows_user', lambda _: (_ for _ in ()).throw(AssertionError('GET decrypted')))
    with client() as browser:
        data=browser.get('/api/creator/ai/connection').json()
    assert data['ready'] and data['api_key_configured']
    assert data['authentication']=='api_key'
    assert data['endpoint']=='https://example.ai/v1/chat/completions'
    assert len(data['connection_fingerprint'])==64 and data['test_status']=='not_tested'
    assert 'FAKE-PRIVATE-KEY' not in json.dumps(data) and 'PROTECTED-FIXTURE' not in json.dumps(data)
    assert data['test_prompt']=='Connection test only. Reply with OK.'


@pytest.mark.parametrize('endpoint', ['https://user:pass@example.com/v1','https://example.com/v1?api_key=PRIVATE',
    'https://example.com/v1#SECRET','https://example.com/v1?', 'https://example.com/v1#',
    'http://example.com/v1','https://example.com:99999/v1','https://example.com:abc/v1',
    'https://example.com\\@elsewhere/v1','https://example.com/v1\n'])
def test_endpoint_rejects_credentials_queries_fragments_and_deceptive_addresses(endpoint):
    with pytest.raises(settings.SettingsError):configured(base_url=endpoint)
    assert not Path(settings.SETTINGS_FILE).exists()


def test_old_unsafe_url_is_hidden_and_never_used():
    Path(settings.SETTINGS_FILE).write_text(json.dumps({'ai': {'enabled':True,'provider':'openai_compatible',
        'base_url':'https://example.com?api_key=OLD-PRIVATE','model':'m','api_key_protected':'PROTECTED-FIXTURE:old'}}))
    public=settings.public_connection()
    assert public['base_url']=='' and not public['ready']
    assert 'OLD-PRIVATE' not in json.dumps(public)
    with pytest.raises(settings.SettingsError):settings.load_ai_connection()


@pytest.mark.parametrize('changes', [{'base_url':'https://new.example/v1'}, {'base_url':'https://example.ai/different'}, {'provider':'anthropic_messages'}])
def test_changed_destination_cannot_reuse_existing_key(changes):
    configured()
    value={**settings.load_ai_settings(), 'api_key':''};value.update(changes)
    saved=settings.save_ai_settings(value)
    assert not saved['api_key_configured']
    assert 'FAKE-PRIVATE-KEY' not in Path(settings.SETTINGS_FILE).read_text()


def test_same_destination_keeps_key_but_fingerprint_tracks_model_key_and_enablement():
    configured();a=settings.public_connection()['connection_fingerprint']
    values={**settings.load_ai_settings(),'model':'another-model','api_key':''}
    assert settings.save_ai_settings(values)['api_key_configured']
    b=settings.public_connection()['connection_fingerprint'];assert a!=b
    settings.save_ai_settings({**values,'api_key':'NEW-FAKE-KEY'})
    c=settings.public_connection()['connection_fingerprint'];assert b!=c
    assert settings.load_ai_connection()['api_key']=='NEW-FAKE-KEY'
    settings.clear_ai_key();assert settings.public_connection()['connection_fingerprint']!=c


def test_changing_destination_with_new_key_explicitly_rebinds():
    configured()
    configured(base_url='https://another.example/v1',api_key='NEW-FAKE-KEY')
    private=settings.load_ai_connection()
    assert private['api_key']=='NEW-FAKE-KEY' and private['base_url']=='https://another.example/v1'


@pytest.mark.parametrize('url', ['http://localhost:1234/v1', 'http://127.0.0.1:11434/v1', 'http://[::1]:8080/v1'])
def test_keyless_loopback_is_optional_and_omits_authorization(url, monkeypatch):
    configured(base_url=url,api_key='')
    connection=settings.load_ai_connection()
    assert connection['authentication']=='none_local' and connection['ready']
    requests=[]
    def reply(request, timeout):
        requests.append(request)
        return Reply(b'{"choices":[{"message":{"content":"OK"}}]}')
    monkeypatch.setattr(ai_assistant,'urlopen',reply)
    assert ai_assistant.test_connection(connection)['ok']
    assert requests[0].get_header('Authorization') is None


@pytest.mark.parametrize('provider,base,auth,suffix,budget', [
    ('openai_compatible','https://api.openai.com/v1','Authorization','/chat/completions','max_completion_tokens'),
    ('openai_compatible','https://third-party.example/v1','Authorization','/chat/completions','max_tokens'),
    ('anthropic_messages','https://api.anthropic.com/v1','X-api-key','/messages','max_tokens')])
def test_confirmed_test_sends_only_fixed_prompt_and_bounded_request(provider,base,auth,suffix,budget,monkeypatch):
    configured(provider=provider,base_url=base)
    captured=[]
    raw=b'{"choices":[{"message":{"content":"FAKE-PRIVATE-KEY echoed by provider"}}]}' if provider=='openai_compatible' else b'{"content":[{"type":"text","text":"FAKE-PRIVATE-KEY echoed by provider"}]}'
    response=Reply(raw)
    def reply(request, timeout):captured.append((request,timeout));return response
    monkeypatch.setattr(ai_assistant,'urlopen',reply)
    with client() as browser:
        public=browser.get('/api/creator/ai/connection').json()
        result=browser.post('/api/creator/ai/test',json={'confirmed':True,'expected_connection_fingerprint':public['connection_fingerprint']})
    assert result.status_code==200 and result.json()['ok']
    assert 'FAKE-PRIVATE-KEY' not in result.text and 'echoed' not in result.text
    request,timeout=captured[0];body=json.loads(request.data)
    assert request.full_url==base+suffix
    assert request.get_header(auth) in {'FAKE-PRIVATE-KEY','Bearer FAKE-PRIVATE-KEY'}
    assert body['messages']==[{'role':'user','content':ai_assistant.TEST_PROMPT}]
    assert body[budget]==64 and timeout==30 and response.requested_size==32769
    assert set(body)=={'model','messages',budget,'stream'}


def test_confirmation_extra_project_fields_and_changed_connection_are_blocked_before_network():
    configured();old=settings.public_connection()['connection_fingerprint']
    with client() as browser:
        assert browser.post('/api/creator/ai/test',json={'confirmed':False,'expected_connection_fingerprint':old}).status_code==422
        assert browser.post('/api/creator/ai/test',json={'confirmed':True,'expected_connection_fingerprint':old,'project_id':'private'}).status_code==422
        configured(model='a different model')
        result=browser.post('/api/creator/ai/test',json={'confirmed':True,'expected_connection_fingerprint':old})
        assert result.status_code==409 and result.json()['detail']['code']=='CONNECTION_CHANGED'


def test_success_for_earlier_connection_is_not_reported_as_current(monkeypatch):
    configured();old=settings.public_connection()['connection_fingerprint']
    def reply(request,timeout):
        configured(model='new model')
        return Reply(b'{"choices":[{"message":{"content":"OK"}}]}')
    monkeypatch.setattr(ai_assistant,'urlopen',reply)
    with client() as browser:
        result=browser.post('/api/creator/ai/test',json={'confirmed':True,'expected_connection_fingerprint':old})
    assert result.status_code==409 and 'earlier connection' in result.text


@pytest.mark.parametrize('status,code', [(301,'REDIRECT_BLOCKED'),(302,'REDIRECT_BLOCKED'),(307,'REDIRECT_BLOCKED'),
    (400,'REQUEST_REJECTED'),(401,'AUTH_FAILED'),(403,'ACCESS_DENIED'),(404,'NOT_FOUND'),(429,'RATE_LIMITED'),(500,'SERVICE_ERROR')])
def test_provider_error_bodies_and_headers_are_never_echoed(status,code,monkeypatch):
    configured()
    def fail(request,timeout):raise HTTPError(request.full_url,status,'FAKE-PRIVATE-KEY',{'Location':'https://leak.invalid'},BytesIO(b'{"error":{"message":"FAKE-PRIVATE-KEY"}}'))
    monkeypatch.setattr(ai_assistant,'urlopen',fail)
    with client() as browser:
        fingerprint=browser.get('/api/creator/ai/connection').json()['connection_fingerprint']
        result=browser.post('/api/creator/ai/test',json={'confirmed':True,'expected_connection_fingerprint':fingerprint})
    assert result.status_code==502 and result.json()['detail']['code']==code
    assert 'FAKE-PRIVATE-KEY' not in result.text and 'leak.invalid' not in result.text


def test_redirect_handler_never_creates_authorized_followup():
    handler=ai_assistant._NoRedirect()
    request=Request('https://original.example',headers={'Authorization':'Bearer FAKE-PRIVATE-KEY'})
    assert handler.redirect_request(request,None,302,'Moved',{},'https://other.example') is None


@pytest.mark.parametrize('raw,code', [(b'x'*32769,'RESPONSE_TOO_LARGE'),(b'not JSON','INVALID_RESPONSE'),(b'[]','INVALID_RESPONSE'),(b'{}','INVALID_RESPONSE')], ids=['oversized','bad-json','array','wrong-shape'])
def test_test_response_limits_and_shapes(raw,code,monkeypatch):
    configured();monkeypatch.setattr(ai_assistant,'urlopen',lambda *a,**k:Reply(raw))
    with pytest.raises(ai_assistant.AssistantError) as error:ai_assistant.test_connection(settings.load_ai_connection())
    assert error.value.code==code


def test_network_failure_sanitized_and_no_retry(monkeypatch):
    configured();calls=[]
    def fail(*args,**kwargs):calls.append(True);raise URLError('FAKE-PRIVATE-KEY https://secret.example')
    monkeypatch.setattr(ai_assistant,'urlopen',fail)
    with pytest.raises(ai_assistant.AssistantError) as error:ai_assistant.test_connection(settings.load_ai_connection())
    assert error.value.code=='NETWORK_ERROR' and 'FAKE-PRIVATE-KEY' not in str(error.value) and len(calls)==1


def test_reasoning_budget_completion_still_proves_connection(monkeypatch):
    configured(base_url='https://api.openai.com/v1')
    monkeypatch.setattr(ai_assistant,'urlopen',lambda *a,**k:Reply(b'{"choices":[{"message":{"content":""},"finish_reason":"length"}]}'))
    assert ai_assistant.test_connection(settings.load_ai_connection())['ok']


def test_actual_openai_chat_uses_provider_default_temperature(monkeypatch):
    configured(base_url='https://api.openai.com/v1')
    captured=[]
    def reply(request,timeout):
        captured.append(json.loads(request.data))
        return Reply(b'{"choices":[{"message":{"content":"A draft idea"}}]}')
    monkeypatch.setattr(ai_assistant,'urlopen',reply)
    result=ai_assistant.ask(settings.load_ai_connection(),'Suggest a short dance idea')
    assert result['answer']=='A draft idea'
    assert 'temperature' not in captured[0]
    assert captured[0]['model']=='user-chosen-model'
