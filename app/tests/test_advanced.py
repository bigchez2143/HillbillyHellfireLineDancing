"""Advanced drawer: empty by default, keys stay local, BootStepper search is read-only."""
import json
import os
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from advanced_api import router
from engine import bootstepper, settings
from engine.community_shelf import save_shelf
from engine.creator_exports import _redact
from engine.full_backup import _safe_settings


SECRET = "FAKE-BOOT-KEY"
AI_SECRET = "FAKE-AI-KEY"


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    monkeypatch.setattr(settings, "_protect_for_current_windows_user", lambda value, description="Line Dance Creator API key": "PROTECTED-FIXTURE:" + value)
    monkeypatch.setattr(settings, "_unprotect_for_current_windows_user", lambda value, label="AI key": value.removeprefix("PROTECTED-FIXTURE:"))
    monkeypatch.setattr(bootstepper, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Unexpected network operation")))


def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class Reply:
    def __init__(self, raw):
        self.raw = raw
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, size):
        return self.raw[:size]


def dance_row():
    return {
        "id": "D4B57G68FMQH7MN",
        "title": "Cup of Practice",
        "difficultyLevel": "beginner",
        "counts": 32,
        "walls": 4,
        "stepSheetBlobUrl": "https://blobs.example/SECRET-SHEET",
        "api_key": SECRET,
        "danceChoreographers": [{"choreographer": {"id": "C36HB4RNBQ69F5D", "name": "Alex Example", "country": "US"}}],
        "danceSongs": [{"song": {"id": "S4B5D8S8K7K5Q82", "title": "Practice Song", "artist": "Example Band",
                                 "spotifyUrl": "https://open.spotify.com/track/secret", "spotifyTrackId": "secret"}}],
    }


def test_advanced_is_empty_by_default_and_does_not_write_settings_or_call_bootstepper():
    path = Path(settings.SETTINGS_FILE)
    with client() as browser:
        status = browser.get("/api/settings/advanced")
        refused = browser.post("/api/settings/advanced/bootstepper/search", json={"kind": "dances", "query": "cupid"})
        missing = browser.put("/api/settings/advanced/spotify", json={"client_id": "DO-NOT-SAVE"})
    assert status.status_code == 200
    body = status.json()
    assert body["bootstepper"] == {"api_key_configured": False, "read_only": True, "writes_enabled": False}
    assert body["ai"]["enabled"] is False and body["ai"]["api_key_configured"] is False
    assert body["spotify"]["enabled"] is False and body["spotify"]["client_id_collected"] is False
    assert "not enabled" in body["spotify"]["note"]
    assert set(body["spotify"]) == {"enabled", "client_id_collected", "note"}
    assert missing.status_code in {404, 405}
    assert "DO-NOT-SAVE" not in missing.text
    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "KEY_REQUIRED"
    assert not path.exists()


def test_saved_key_stays_out_of_status_search_backup_and_export(monkeypatch):
    with client() as browser:
        saved = browser.put("/api/settings/advanced/bootstepper", json={"api_key": SECRET, "spotify_client_id": "NO"})
        assert saved.status_code == 422
        saved = browser.put("/api/settings/advanced/bootstepper", json={"api_key": SECRET})
        assert saved.status_code == 200
        assert saved.json()["api_key_configured"] is True
        assert SECRET not in saved.text and "PROTECTED-FIXTURE" not in saved.text
        status = browser.get("/api/settings/advanced")
        assert SECRET not in status.text and "PROTECTED-FIXTURE" not in status.text
        leaked = browser.post("/api/settings/advanced/bootstepper/search", json={"kind": "dances", "query": "cupid", "api_key": SECRET})
        assert leaked.status_code == 422
    stored = json.loads(Path(settings.SETTINGS_FILE).read_text(encoding="utf-8"))
    assert stored["bootstepper"] == {"api_key_protected": "PROTECTED-FIXTURE:" + SECRET}
    assert "api_key" not in stored["bootstepper"]
    safe = _safe_settings(stored)
    assert "bootstepper" not in safe
    assert SECRET not in json.dumps(safe)
    redacted = _redact({"name": "Dance", "api_key_protected": SECRET, "nested": {"client_id": "SPOTIFY-CLIENT", "api_key_protected": SECRET}})
    blob = json.dumps(redacted)
    assert SECRET not in blob and "SPOTIFY-CLIENT" not in blob
    assert settings.load_bootstepper_key() == SECRET

    captured = []
    def reply(request, timeout):
        captured.append(request)
        return Reply(json.dumps({"items": [dance_row(), {"title": ""}, "skip"]}).encode())
    monkeypatch.setattr(bootstepper, "urlopen", reply)
    before = Path(settings.SETTINGS_FILE).read_text(encoding="utf-8")
    with client() as browser:
        found = browser.post("/api/settings/advanced/bootstepper/search", json={"kind": "dances", "query": "cupid"})
    assert found.status_code == 200
    text = found.text
    assert SECRET not in text and "PROTECTED-FIXTURE" not in text
    assert "SECRET-SHEET" not in text and "spotify" not in text.lower() and "secret" not in text.lower()
    item = found.json()["items"][0]
    assert item["title"] == "Cup of Practice"
    assert item["url"] == "https://bootstepper.com/dances/D4B57G68FMQH7MN"
    assert item["choreographers"] == ["Alex Example"]
    assert item["songs"] == ["Practice Song — Example Band"]
    assert found.json()["stored"] is False and found.json()["read_only"] is True
    request = captured[0]
    assert request.method == "GET" and request.data is None
    assert request.full_url == "https://api.bootstepper.com/dances/search?query=cupid&limit=10"
    assert "apiKey" not in request.full_url and SECRET not in request.full_url
    assert request.get_header("X-bootstepper-api-key") == SECRET
    assert Path(settings.SETTINGS_FILE).read_text(encoding="utf-8") == before


@pytest.mark.parametrize("kind,row,url", [
    ("songs", {"id": "S4B5D8S8K7K5Q82", "title": "Practice Song", "artist": "Example Band", "danceCount": 3,
               "spotifyUrl": "https://open.spotify.com/track/secret", "api_key": SECRET},
     "https://bootstepper.com/songs/S4B5D8S8K7K5Q82"),
    ("choreographers", {"id": "C36HB4RNBQ69F5D", "name": "Alex Example", "country": "US", "danceCount": 12,
                        "awards": [{"notes": SECRET}], "api_key": SECRET},
     "https://bootstepper.com/choreographers/C36HB4RNBQ69F5D"),
])
def test_song_and_choreographer_search_keeps_a_public_summary(kind, row, url, monkeypatch):
    settings.save_bootstepper_key(SECRET)
    monkeypatch.setattr(bootstepper, "urlopen", lambda request, timeout: Reply(json.dumps({"items": [row]}).encode()))
    with client() as browser:
        found = browser.post("/api/settings/advanced/bootstepper/search", json={"kind": kind, "query": "Alex"})
    assert found.status_code == 200
    assert SECRET not in found.text and "spotify" not in found.text.lower()
    assert found.json()["items"][0]["url"] == url
    assert found.json()["kind"] == kind


def test_blank_save_keeps_the_key_and_other_settings_survive():
    settings.save_ai_settings({
        "enabled": True, "provider": "openai_compatible", "base_url": "https://example.ai/v1",
        "model": "user-model", "timeout_seconds": 60, "api_key": AI_SECRET,
    })
    settings.save_bootstepper_key(SECRET)
    kept = settings.save_bootstepper_key("   ")
    assert kept["api_key_configured"] is True
    assert settings.load_bootstepper_key() == SECRET
    assert settings.load_ai_connection()["api_key"] == AI_SECRET
    save_shelf([{"name": "Studio", "url": "https://example.com/studio", "note": ""}])
    assert settings.load_bootstepper_key() == SECRET
    assert settings.load_ai_connection()["api_key"] == AI_SECRET
    settings.save_ai_settings({"enabled": True, "provider": "openai_compatible", "base_url": "https://example.ai/v1",
                               "model": "user-model", "timeout_seconds": 60, "api_key": ""})
    assert settings.load_bootstepper_key() == SECRET
    cleared = settings.clear_bootstepper_key()
    assert cleared["api_key_configured"] is False
    assert settings.load_ai_connection()["api_key"] == AI_SECRET
    stored = json.loads(Path(settings.SETTINGS_FILE).read_text(encoding="utf-8"))
    assert "bootstepper" not in stored
    assert SECRET not in json.dumps(stored)


def test_unsafe_key_is_refused_before_a_file_is_written():
    with client() as browser:
        for value in ("short", "https://example.com/key", "line\nbreak", "has space-key"):
            refused = browser.put("/api/settings/advanced/bootstepper", json={"api_key": value})
            assert refused.status_code == 400
    assert not Path(settings.SETTINGS_FILE).exists()


def test_provider_errors_never_echo_the_key_or_response_body(monkeypatch):
    settings.save_bootstepper_key(SECRET)
    def fail(request, timeout):
        raise HTTPError(request.full_url, 401, SECRET, {"Location": "https://leak.invalid"}, BytesIO(SECRET.encode()))
    monkeypatch.setattr(bootstepper, "urlopen", fail)
    with client() as browser:
        result = browser.post("/api/settings/advanced/bootstepper/search", json={"kind": "dances", "query": "cupid"})
    assert result.status_code == 502
    assert result.json()["detail"]["code"] == "AUTH_FAILED"
    assert SECRET not in result.text and "leak.invalid" not in result.text


def test_network_failure_is_sanitized(monkeypatch):
    settings.save_bootstepper_key(SECRET)
    monkeypatch.setattr(bootstepper, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(URLError(SECRET)))
    with client() as browser:
        result = browser.post("/api/settings/advanced/bootstepper/search", json={"kind": "songs", "query": "shuffle"})
    assert result.status_code == 502
    assert result.json()["detail"]["code"] == "NETWORK_ERROR"
    assert SECRET not in result.text


def test_redirect_does_not_forward_the_key(monkeypatch):
    settings.save_bootstepper_key(SECRET)
    def redirect(request, timeout):
        raise HTTPError(request.full_url, 302, "Moved", {"Location": "https://elsewhere.example/?apiKey=" + SECRET}, BytesIO(b""))
    monkeypatch.setattr(bootstepper, "urlopen", redirect)
    with client() as browser:
        result = browser.post("/api/settings/advanced/bootstepper/search", json={"kind": "choreographers", "query": "Alex"})
    assert result.status_code == 502
    assert result.json()["detail"]["code"] == "REDIRECT_BLOCKED"
    assert SECRET not in result.text and "elsewhere.example" not in result.text
    handler = bootstepper._NoRedirect()
    from urllib.request import Request
    assert handler.redirect_request(Request("https://api.bootstepper.com/dances/search"), None, 302, "Moved", {}, "https://elsewhere.example") is None


def test_bad_identifier_is_not_turned_into_a_link(monkeypatch):
    settings.save_bootstepper_key(SECRET)
    row = dance_row()
    row["id"] = "javascript:alert(1)"
    monkeypatch.setattr(bootstepper, "urlopen", lambda *args, **kwargs: Reply(json.dumps({"items": [row]}).encode()))
    with client() as browser:
        found = browser.post("/api/settings/advanced/bootstepper/search", json={"kind": "dances", "query": "cupid"})
    assert "url" not in found.json()["items"][0]
    assert "javascript" not in found.text


def test_windows_dpapi_keeps_the_bootstepper_key_out_of_the_settings_file(monkeypatch, tmp_path):
    if os.name != "nt":
        pytest.skip("The desktop app uses Windows credential protection.")
    monkeypatch.undo()
    monkeypatch.setattr(settings, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    public = settings.save_bootstepper_key("testing-only-bootstepper-key")
    assert public["api_key_configured"] is True
    raw = Path(settings.SETTINGS_FILE).read_text(encoding="utf-8")
    assert "testing-only-bootstepper-key" not in raw
    assert settings.load_bootstepper_key() == "testing-only-bootstepper-key"
