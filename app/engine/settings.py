"""Local, optional connection settings for the AI dance assistant.

Project files must stay portable and safe to share, so connection settings are
kept once for this Windows account under app/settings.json.  The API key is
encrypted with Windows Data Protection API (DPAPI) before it is written; it is
never returned to the browser, included in project backups, or sent to an AI
unless a future, explicit AI action is requested by the dancer.
"""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import json
import os
import hashlib
import hmac
import secrets
import tempfile
import threading
from functools import wraps
from urllib.parse import urlparse


APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from .paths import runtime_path
SETTINGS_FILE = runtime_path('settings.json', os.path.join(APP_DIR, "settings.json"))
_LOCK = threading.RLock()
_FINGERPRINT_SECRET = secrets.token_bytes(32)

DEFAULT_AI_SETTINGS = {
    "enabled": False,
    "provider": "openai_compatible",
    "base_url": "",
    "model": "",
    "timeout_seconds": 60,
}


class SettingsError(ValueError):
    """A configuration value is not safe or complete enough to save."""


class ConnectionChanged(SettingsError):
    """The user must preview the newly saved destination before testing it."""


def _synchronized(function):
    @wraps(function)
    def call(*args, **kwargs):
        with _LOCK:
            return function(*args, **kwargs)
    return call


def _read_raw():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        # A bad preferences file should not prevent the dance app from opening.
        return {}


def read_lenient():
    """Settings for display. A damaged file yields an empty document."""
    return _read_raw()


def _read_strict():
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise SettingsError("Local settings could not be read, so this change was not saved.") from exc
    if not isinstance(value, dict):
        raise SettingsError("Local settings could not be read, so this change was not saved.")
    return value


@_synchronized
def update_settings(mutator):
    """Update one part of local settings without dropping the rest of the file."""
    raw = _read_strict()
    mutator(raw)
    if not isinstance(raw, dict):
        raise SettingsError("Local settings could not be saved.")
    _write_raw(raw)
    return raw


def _write_raw(value):
    parent = os.path.dirname(SETTINGS_FILE)
    os.makedirs(parent, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix='.settings-', suffix='.tmp', dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=1, allow_nan=False)
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temp_path, SETTINGS_FILE)
    finally:
        if os.path.exists(temp_path): os.unlink(temp_path)


def _safe_public(ai):
    """Return settings that are always safe to place in an API response."""
    merged = dict(DEFAULT_AI_SETTINGS)
    if not isinstance(ai, dict): ai = {}
    for key in DEFAULT_AI_SETTINGS:
        if key in ai:
            merged[key] = ai[key]
    merged['enabled'] = merged['enabled'] is True
    if not isinstance(merged['provider'], str) or merged['provider'] not in {'openai_compatible', 'anthropic_messages', 'custom'}:
        merged['provider'] = 'custom'
    if not isinstance(merged['model'], str): merged['model'] = ''
    merged['model'] = merged['model'][:160]
    if type(merged['timeout_seconds']) is not int or not 5 <= merged['timeout_seconds'] <= 180:
        merged['timeout_seconds'] = 60
    try:
        merged['base_url'] = _validate_endpoint(merged['base_url'])
    except SettingsError:
        # Old credential-bearing or invalid URLs must not be echoed to a browser.
        merged['base_url'] = ''
        merged['endpoint_error'] = 'The saved API address needs updating. Use a URL without a query, fragment or credentials.'
    merged["api_key_configured"] = bool(ai.get("api_key_protected"))
    local = _keyless_local(merged)
    merged['authentication'] = 'api_key' if merged['api_key_configured'] else 'none_local' if local else 'required'
    merged["configured"] = bool(merged["enabled"] and merged["base_url"] and
                                merged["model"] and (merged["api_key_configured"] or local))
    # A truly custom endpoint has no universal message format.  It may be
    # saved for later, but it is not presented as ready until an adapter exists.
    merged["ready"] = bool(merged["configured"] and merged["provider"] != "custom")
    return merged


@_synchronized
def load_ai_settings():
    return _safe_public((_read_raw().get("ai") or {}))


def _validate_endpoint(value):
    if value is not None and not isinstance(value, str):
        raise SettingsError('The API address must be text.')
    if value and (len(value) > 2048 or any(ord(c) < 32 or ord(c) == 127 for c in value) or '\\' in value):
        raise SettingsError('Use an API address without control characters or backslashes.')
    value = (value or "").strip().rstrip("/")
    if not value:
        return ""
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError as exc:
        raise SettingsError('Use a valid API host and port.') from exc
    if parsed.scheme not in ("https", "http") or not parsed.hostname:
        raise SettingsError("Use a full API address beginning with https:// or http://.")
    if parsed.username or parsed.password:
        raise SettingsError("Put credentials in the API key field, not in the API address.")
    if parsed.query or parsed.fragment or '?' in value or '#' in value or parsed.params:
        raise SettingsError('Use an API address without query parameters or fragments. Put credentials only in the API key field.')
    if port is not None and not 1 <= port <= 65535:
        raise SettingsError('Use a valid API port between 1 and 65535.')
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise SettingsError("Use HTTPS unless you are connecting to an AI running on this computer.")
    return value


def _keyless_local(ai):
    return (ai.get('provider') == 'openai_compatible' and
            urlparse(ai.get('base_url') or '').hostname in {'localhost', '127.0.0.1', '::1'})


def _fingerprint(ai):
    # A keyed digest binds the credential version without exposing a key or its
    # stored ciphertext. A server restart intentionally invalidates old tests.
    value = {key: ai.get(key) for key in (*DEFAULT_AI_SETTINGS, 'api_key_protected')}
    data = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    return hmac.new(_FINGERPRINT_SECRET, data, hashlib.sha256).hexdigest()


@_synchronized
def public_connection():
    ai = _read_raw().get('ai') or {}
    if not isinstance(ai, dict): ai = {}
    return {**_safe_public(ai), 'connection_fingerprint': _fingerprint(ai), 'test_status': 'not_tested'}


def _protect_for_current_windows_user(secret):
    """Encrypt a small secret with DPAPI.  It can only be read by this user."""
    if os.name != "nt":
        raise SettingsError("Secure API-key storage is available in the Windows desktop app only.")
    if not secret:
        raise SettingsError("The API key cannot be empty.")

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_byte))]

    payload = secret.encode("utf-8")
    source_buffer = ctypes.create_string_buffer(payload)
    source = DataBlob(len(payload), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_byte)))
    protected = DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    ok = crypt32.CryptProtectData(ctypes.byref(source), "Line Dance Creator API key",
                                  None, None, None, 0x01, ctypes.byref(protected))
    if not ok:
        raise SettingsError("Windows could not securely store this API key.")
    try:
        return base64.b64encode(ctypes.string_at(protected.pbData, protected.cbData)).decode("ascii")
    finally:
        kernel32.LocalFree(protected.pbData)


def _unprotect_for_current_windows_user(protected_text):
    """Read a DPAPI-protected key inside the local server only."""
    if os.name != "nt":
        raise SettingsError("Secure API-key storage is available in the Windows desktop app only.")
    try:
        payload = base64.b64decode(protected_text.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError):
        raise SettingsError("The saved AI key could not be read. Please save it again.")
    if not payload:
        raise SettingsError("The saved AI key could not be read. Please save it again.")

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_byte))]

    source_buffer = ctypes.create_string_buffer(payload)
    source = DataBlob(len(payload), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_byte)))
    clear = DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    ok = crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None,
                                    0x01, ctypes.byref(clear))
    if not ok:
        raise SettingsError("Windows could not unlock the saved AI key. Please save it again.")
    try:
        return ctypes.string_at(clear.pbData, clear.cbData).decode("utf-8")
    finally:
        kernel32.LocalFree(clear.pbData)


@_synchronized
def save_ai_settings(values):
    """Save non-secret preferences and, if supplied, a DPAPI-protected key.

    A blank key retains a saved key only for the same provider and exact endpoint.
    Changing either clears it unless the user explicitly supplies a new key.
    """
    raw = _read_raw()
    current = raw.get("ai") or {}
    if not isinstance(current, dict): current = {}
    provider = (values.get("provider") or DEFAULT_AI_SETTINGS["provider"]).strip()
    if provider not in ("openai_compatible", "anthropic_messages", "custom"):
        raise SettingsError("Choose a supported connection type.")
    model = (values.get("model") or "").strip()
    if len(model) > 160 or any(ord(c) < 32 or ord(c) == 127 for c in model):
        raise SettingsError("The model name is too long.")
    try:
        timeout = int(values.get("timeout_seconds", DEFAULT_AI_SETTINGS["timeout_seconds"]))
    except (TypeError, ValueError):
        raise SettingsError("Connection timeout must be a whole number of seconds.")
    if not 5 <= timeout <= 180:
        raise SettingsError("Connection timeout must be between 5 and 180 seconds.")

    ai = {
        "enabled": bool(values.get("enabled", False)),
        "provider": provider,
        "base_url": _validate_endpoint(values.get("base_url")),
        "model": model,
        "timeout_seconds": timeout,
    }
    try:
        prior_endpoint = _validate_endpoint(current.get('base_url'))
    except SettingsError:
        prior_endpoint = None
    same_destination = current.get('provider') == provider and prior_endpoint == ai['base_url']
    if same_destination and current.get("api_key_protected"):
        ai["api_key_protected"] = current["api_key_protected"]
    api_key = values.get("api_key")
    if api_key is not None and (not isinstance(api_key, str) or len(api_key) > 8192 or any(ord(c) < 32 or ord(c) == 127 for c in api_key)):
        raise SettingsError('Enter an API key without line breaks or control characters.')
    if api_key is not None and api_key.strip():
        ai["api_key_protected"] = _protect_for_current_windows_user(api_key.strip())
    raw["ai"] = ai
    _write_raw(raw)
    return _safe_public(ai)


@_synchronized
def clear_ai_key():
    raw = _read_raw()
    ai = raw.get("ai") or {}
    if not isinstance(ai, dict): ai = {}
    ai.pop("api_key_protected", None)
    raw["ai"] = ai
    _write_raw(raw)
    return _safe_public(ai)


@_synchronized
def load_ai_connection(expected_fingerprint=None):
    """Private server-only connection data, including the decrypted API key.

    Do not use this function in a web response or any project/export code.
    """
    raw = _read_raw()
    ai = raw.get("ai") or {}
    if not isinstance(ai, dict): ai = {}
    if expected_fingerprint is not None and (not isinstance(expected_fingerprint, str) or not hmac.compare_digest(expected_fingerprint, _fingerprint(ai))):
        raise ConnectionChanged('The saved connection changed. Reload its settings and review the destination before testing.')
    public = _safe_public(ai)
    if not public["enabled"]:
        raise SettingsError("Optional AI assistant is turned off. Enable it in Settings when you are ready.")
    if not public["base_url"] or not public["model"] or (not ai.get("api_key_protected") and not _keyless_local(public)):
        raise SettingsError("Add an API address, model name, and key in Settings before asking the AI.")
    key = _unprotect_for_current_windows_user(ai['api_key_protected']) if ai.get('api_key_protected') else ''
    return {**public, 'api_key': key, 'connection_fingerprint': _fingerprint(ai)}
