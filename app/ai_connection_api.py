"""Explicit, destination-bound connection tests for the user's own AI account."""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from engine import settings, ai_assistant

router = APIRouter(prefix='/api/creator/ai', tags=['optional-ai'])


class TestBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    confirmed: StrictBool = False
    expected_connection_fingerprint: str = Field(pattern=r'^[a-f0-9]{64}$')


@router.get('/connection')
def connection():
    public = settings.public_connection()
    endpoint = ''
    if public['base_url'] and public['provider'] in {'openai_compatible', 'anthropic_messages'}:
        endpoint = ai_assistant._endpoint(public['base_url'], '/chat/completions' if public['provider'] == 'openai_compatible' else '/messages')
    return {**public, 'endpoint': endpoint, 'test_prompt': ai_assistant.TEST_PROMPT,
            'test_max_output_tokens': ai_assistant.TEST_MAX_TOKENS, 'test_socket_timeout_seconds': min(public['timeout_seconds'], 30),
            'project_data_sent_by_test': False}


@router.post('/test')
def test(body: TestBody):
    if body.confirmed is not True:
        raise HTTPException(422, detail={'code': 'CONFIRM_TEST', 'message': 'Review the saved destination and confirm sending this connection test.'})
    try:
        private = settings.load_ai_connection(body.expected_connection_fingerprint)
        result = ai_assistant.test_connection(private)
        if settings.public_connection()['connection_fingerprint'] != body.expected_connection_fingerprint:
            raise settings.ConnectionChanged('Settings changed while the test was running. Its result applies to the earlier connection; preview and test the current settings.')
        return {**result, 'connection_fingerprint': body.expected_connection_fingerprint,
                'provider': private['provider'], 'model': private['model'], 'tested_at': datetime.now(timezone.utc).isoformat()}
    except settings.ConnectionChanged as exc:
        raise HTTPException(409, detail={'code': 'CONNECTION_CHANGED', 'message': str(exc)}) from None
    except settings.SettingsError as exc:
        raise HTTPException(422, detail={'code': 'CONNECTION_NOT_READY', 'message': str(exc)}) from None
    except ai_assistant.AssistantError as exc:
        raise HTTPException(502, detail={'code': exc.code, 'message': str(exc)}) from None
