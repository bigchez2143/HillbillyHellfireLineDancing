"""Provider adapters for the optional, user-triggered AI conversation.

The browser talks only to our local FastAPI server.  This module is the only
place that reads the decrypted key and it only does so after the dancer presses
Ask AI.  The assistant returns words and draft ideas; it never edits a saved
dance, section marker, or sheet by itself.
"""
from __future__ import annotations

import json
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler


MAX_PROMPT_CHARS = 6_000
MAX_HISTORY_MESSAGES = 10
MAX_HISTORY_CHARS = 12_000
TEST_PROMPT = 'Connection test only. Reply with OK.'
TEST_MAX_TOKENS = 64
TEST_MAX_RESPONSE_BYTES = 32768


class AssistantError(RuntimeError):
    """A safe, human-readable optional-AI error."""
    def __init__(self, message, code='AI_ERROR'):
        self.code = code
        super().__init__(message)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def urlopen(request, timeout):
    """Keep authorization on the explicitly saved destination only."""
    return build_opener(_NoRedirect()).open(request, timeout=timeout)


SYSTEM_PROMPT = """You are an optional creative consultant inside Line Dance Creator.
Help the dancer develop a teachable, floor-friendly line dance. The app's local
rules and human music map are the source of truth. Do not claim a dance is
validated, submit-ready, or safe without a real floor test. Never silently move
song sections or invent a restart because a music section is not a clean
32-count multiple.

When suggesting choreography, clearly group moves into 8-count blocks, name the
count range, note direction/turns, keep the requested level in mind, and flag
anything a human should test. Favor contrast, a memorable chorus moment, and
plain teaching language over generic repetition. The dancer makes the final
decision; you are proposing ideas, not changing the project."""


def _endpoint(base_url, suffix):
    from .settings import _validate_endpoint, SettingsError
    try:
        base_url = _validate_endpoint(base_url)
    except SettingsError as exc:
        raise AssistantError('Update the saved API address before connecting.', 'INVALID_ENDPOINT') from exc
    base = base_url.rstrip("/")
    parsed = urlparse(base)
    if parsed.path.rstrip("/").endswith(suffix):
        return base
    return base + suffix


def _safe_history(history):
    """Keep a compact normal conversation; system messages come from the app."""
    if not isinstance(history, list):
        return []
    out = []
    total = 0
    for message in history[-MAX_HISTORY_MESSAGES:]:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = message.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        content = content.strip()
        if not content:
            continue
        remaining = MAX_HISTORY_CHARS - total
        if remaining <= 0:
            break
        content = content[:remaining]
        out.append({"role": role, "content": content})
        total += len(content)
    return out


def _post_json(url, headers, payload, timeout, max_response_bytes=1_500_000):
    request = Request(url, data=json.dumps(payload).encode("utf-8"),
                      headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(max_response_bytes + 1)
    except HTTPError as exc:
        # Provider error bodies may echo the request, authorization or endpoint.
        # Never return them to the browser or include them in application logs.
        status = exc.code
        exc.close()
        if 300 <= status < 400:
            raise AssistantError('The service redirected the request. Save its final API address and test again; credentials were not forwarded.', 'REDIRECT_BLOCKED') from None
        guidance = {
            400: ('REQUEST_REJECTED', 'The provider rejected this request format or model setting. Check its API type, model name and supported Chat Completions or Messages endpoint.'),
            401: ('AUTH_FAILED', 'The provider rejected the API key. Replace it with a key for this provider and account.'),
            403: ('ACCESS_DENIED', 'This account cannot use the selected model or API. Check provider permissions and model access.'),
            404: ('NOT_FOUND', 'The model or API endpoint was not found. Check the model name and full API base address.'),
            408: ('TIMEOUT', 'The provider timed out. Try again or increase the timeout.'),
            429: ('RATE_LIMITED', 'The provider reported a usage or rate limit. Check your account quota, billing and retry timing.'),
        }
        code, message = guidance.get(status, ('SERVICE_ERROR', f'The AI service returned HTTP {status}. Check its service status and try again.'))
        raise AssistantError(message, code) from None
    except (URLError, TimeoutError, OSError) as exc:
        if isinstance(exc, (TimeoutError, socket.timeout)) or isinstance(getattr(exc, 'reason', None), (TimeoutError, socket.timeout)):
            raise AssistantError('The connection timed out. Check the address or local AI server, then try again.', 'TIMEOUT') from None
        raise AssistantError('Could not reach the AI service. Check its address, network connection, certificate and whether a local server is running.', 'NETWORK_ERROR') from None
    if len(raw) > max_response_bytes:
        raise AssistantError('The provider response exceeded this action’s size limit.', 'RESPONSE_TOO_LARGE')
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise AssistantError("The AI service returned an unreadable response.", 'INVALID_RESPONSE')
    if not isinstance(value, dict):
        raise AssistantError("The AI service returned an unexpected response.", 'INVALID_RESPONSE')
    return value


def _message_from_error(raw):
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or "")[:500]
    if isinstance(error, str):
        return error[:500]
    return str(data.get("message") or "")[:500] if isinstance(data, dict) else ""


def _content_to_text(content):
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        return "\n".join(parts).strip()
    return ""


def _openai_compatible(connection, messages):
    payload = {
        "model": connection["model"],
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
    }
    headers = {'Content-Type': 'application/json'}
    if connection.get('api_key'): headers['Authorization'] = 'Bearer ' + connection['api_key']
    data = _post_json(
        _endpoint(connection["base_url"], "/chat/completions"),
        headers,
        payload, connection["timeout_seconds"],
    )
    choices = data.get("choices") or []
    first = choices[0] if choices else {}
    text = _content_to_text((first.get("message") or {}).get("content") if isinstance(first, dict) else "")
    if not text:
        raise AssistantError("The AI returned no text. Try a shorter prompt or another model.")
    return text


def test_connection(connection):
    """One short synthetic request; no caller prompt or project is accepted."""
    provider = connection.get('provider')
    messages = [{'role': 'user', 'content': TEST_PROMPT}]
    headers = {'Content-Type': 'application/json'}
    if provider == 'openai_compatible':
        endpoint = _endpoint(connection['base_url'], '/chat/completions')
        # OpenAI's current field bounds visible and reasoning tokens. Compatible
        # third-party/local APIs retain their usual max_tokens parameter.
        budget_field = 'max_completion_tokens' if urlparse(endpoint).hostname == 'api.openai.com' else 'max_tokens'
        payload = {'model': connection['model'], 'messages': messages, budget_field: TEST_MAX_TOKENS, 'stream': False}
        if connection.get('api_key'): headers['Authorization'] = 'Bearer ' + connection['api_key']
    elif provider == 'anthropic_messages':
        endpoint = _endpoint(connection['base_url'], '/messages')
        payload = {'model': connection['model'], 'messages': messages, 'max_tokens': TEST_MAX_TOKENS, 'stream': False}
        headers.update({'X-API-Key': connection['api_key'], 'anthropic-version': '2023-06-01'})
    else:
        raise AssistantError('This custom connection needs a provider adapter before it can be tested here.', 'UNSUPPORTED_PROVIDER')
    data = _post_json(endpoint, headers, payload, min(connection['timeout_seconds'], 30), TEST_MAX_RESPONSE_BYTES)
    if provider == 'openai_compatible':
        choices = data.get('choices')
        first = choices[0] if isinstance(choices, list) and choices else None
        valid = isinstance(first, dict) and isinstance(first.get('message'), dict) and (
            bool(_content_to_text(first['message'].get('content'))) or first.get('finish_reason') == 'length')
    else:
        valid = isinstance(data.get('content'), list) and (bool(_content_to_text(data['content'])) or data.get('stop_reason') == 'max_tokens')
    if not valid:
        raise AssistantError('The endpoint answered, but did not return a supported model response. Check the API type and model name.', 'INVALID_RESPONSE')
    # Do not expose the provider response text, headers or request identifiers.
    return {'ok': True, 'code': 'CONNECTED', 'message': 'Connection test succeeded. No project data was sent.'}


def _anthropic_messages(connection, messages):
    payload = {
        "model": connection["model"],
        "max_tokens": 1600,
        "system": SYSTEM_PROMPT,
        "messages": messages,
        "temperature": 0.65,
    }
    data = _post_json(
        _endpoint(connection["base_url"], "/messages"),
        {"Content-Type": "application/json", "X-API-Key": connection["api_key"],
         "anthropic-version": "2023-06-01"},
        payload, connection["timeout_seconds"],
    )
    text = _content_to_text(data.get("content"))
    if not text:
        raise AssistantError("The AI returned no text. Try a shorter prompt or another model.")
    return text


def ask(connection, prompt, history=None, project_context=None):
    prompt = (prompt or "").strip()
    if not prompt:
        raise AssistantError("Write a question or dance idea first.")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise AssistantError(f"Keep the prompt under {MAX_PROMPT_CHARS:,} characters.")
    if connection.get("provider") == "custom":
        raise AssistantError("Custom connections can be saved, but need a provider adapter before they can answer here.")

    context_text = ""
    if project_context:
        context_text = "\n\nCURRENT PROJECT CONTEXT (reference only; do not change it automatically):\n" + \
                       json.dumps(project_context, ensure_ascii=False, indent=1)
    messages = _safe_history(history)
    messages.append({"role": "user", "content": prompt + context_text})

    if connection.get("provider") == "openai_compatible":
        answer = _openai_compatible(connection, messages)
    elif connection.get("provider") == "anthropic_messages":
        answer = _anthropic_messages(connection, messages)
    else:
        raise AssistantError("Choose a supported AI connection type in Settings.")
    return {"answer": answer, "model": connection["model"],
            "provider": connection["provider"]}
