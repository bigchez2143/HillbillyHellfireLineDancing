"""Community links stay in local settings and never carry a key."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from engine import community_shelf, settings
from engine.full_backup import _safe_settings
from community_api import router


@pytest.fixture()
def shelf_file(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings, "SETTINGS_FILE", str(path))
    return path


def test_unsaved_shelf_returns_starter_links_and_does_not_write_settings(shelf_file):
    shelf = community_shelf.load_shelf()
    assert shelf["saved"] is False
    urls = [item["url"] for item in shelf["links"]]
    assert urls == [
        "https://bootstepper.com/",
        "https://www.copperknob.co.uk/",
        "https://www.linedance.com/",
        "https://bootstepper.com/dances/create",
        "https://hillbillyhellfire.com",
        "https://www.youtube.com/@HillbillyHellfire",
    ]
    assert not shelf_file.exists()
    assert all("api" not in item["note"].lower() for item in shelf["links"])


def test_add_edit_remove_persist_without_touching_a_saved_key(shelf_file):
    shelf_file.write_text(json.dumps({"ai": {"api_key_protected": "PROTECTED-SECRET", "enabled": True}}), encoding="utf-8")
    saved = community_shelf.save_shelf(community_shelf.starter_links() + [
        {"name": "Thursday class", "url": "https://example.com/class", "note": "Our studio page"}
    ])
    assert saved["saved"] is True
    assert saved["links"][-1]["name"] == "Thursday class"
    edited = community_shelf.save_shelf([
        dict(saved["links"][-1], name="Thursday beginners", url="https://example.com/beginners")
    ])
    assert [item["name"] for item in edited["links"]] == ["Thursday beginners"]
    again = community_shelf.load_shelf()
    assert again["saved"] is True and again["links"][0]["url"] == "https://example.com/beginners"
    stored = json.loads(shelf_file.read_text(encoding="utf-8"))
    assert stored["ai"]["api_key_protected"] == "PROTECTED-SECRET"
    assert "PROTECTED-SECRET" not in json.dumps(again)
    restored = community_shelf.reset_shelf()
    assert restored["saved"] is False and len(restored["links"]) == 6
    assert "community" not in json.loads(shelf_file.read_text(encoding="utf-8"))
    assert json.loads(shelf_file.read_text(encoding="utf-8"))["ai"]["api_key_protected"] == "PROTECTED-SECRET"


@pytest.mark.parametrize("url", [
    "javascript:alert(1)",
    "https://user:secret@example.com/dance",
    "https://example.com/dance?api_key=SECRET",
    "https://example.com/dance?token=SECRET",
    "not a website",
])
def test_secret_or_non_website_links_are_refused(shelf_file, url):
    with pytest.raises(community_shelf.CommunityError):
        community_shelf.save_shelf([{"name": "Class", "url": url}])
    assert not shelf_file.exists()


def test_damaged_settings_are_not_replaced(shelf_file):
    shelf_file.write_text("{not json", encoding="utf-8")
    with pytest.raises(settings.SettingsError):
        community_shelf.save_shelf([{"name": "Class", "url": "https://example.com/class"}])
    assert shelf_file.read_text(encoding="utf-8") == "{not json"


def test_backup_keeps_links_and_drops_keys():
    raw = {
        "ai": {"enabled": True, "provider": "openai_compatible", "model": "user-model",
               "base_url": "https://example.com?api_key=URL-SECRET", "api_key_protected": "PROTECTED-SECRET",
               "api_key": "PLAIN-SECRET"},
        "community": {"links": community_shelf.starter_links() + [
            {"name": "Class", "url": "https://example.com/class?api_key=SECRET", "note": "skip me"},
            {"name": "Studio", "url": "https://example.com/studio", "note": "Thursday"}]},
        "unexpected": {"password": "NESTED-SECRET"},
    }
    safe = _safe_settings(raw)
    blob = json.dumps(safe)
    for secret in ("URL-SECRET", "PROTECTED-SECRET", "PLAIN-SECRET", "NESTED-SECRET", "SECRET"):
        assert secret not in blob
    assert safe["ai"]["base_url"] == ""
    assert "unexpected" not in safe
    assert any(item["url"] == "https://example.com/studio" for item in safe["community"]["links"])
    assert _safe_settings(safe) == safe


def test_community_routes_round_trip(shelf_file):
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    first = client.get("/api/settings/community")
    assert first.status_code == 200 and first.json()["saved"] is False
    saved = client.put("/api/settings/community", json={"links": [
        {"name": "Studio", "url": "https://example.com/studio", "note": "Class page", "api_key": "DO-NOT-KEEP"}
    ]})
    assert saved.status_code == 200
    assert saved.json()["links"] == [{"id": "link-1", "name": "Studio", "url": "https://example.com/studio", "note": "Class page"}]
    assert "DO-NOT-KEEP" not in shelf_file.read_text(encoding="utf-8")
    refused = client.put("/api/settings/community", json={"links": [{"name": "Bad", "url": "javascript:alert(1)"}]})
    assert refused.status_code == 400
    assert client.get("/api/settings/community").json()["links"][0]["name"] == "Studio"
    reset = client.post("/api/settings/community/reset")
    assert reset.status_code == 200 and reset.json()["saved"] is False
    assert len(reset.json()["links"]) == 6
