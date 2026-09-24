"""Song card stores a Spotify share link and rehearses from a local file."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest
from fastapi.testclient import TestClient

from engine import project as store
from engine.creator_exports import export_project, portable_project
from engine.song_card import CONNECT, KEY, PASTE, normalize_spotify_url, rehearsal_source
from test_creator_exports import fixture_project
import server

TRACK = "Aa1Bb2Cc3Dd4Ee5Ff6Gg7H"
PLAYLIST = "37i9dQZF1DXcBWIGoYBM5M"
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "PROJECTS_DIR", str(tmp_path / "projects"))
    return TestClient(server.app)


@pytest.mark.parametrize("raw, expected", [
    ("", ""),
    ("  ", ""),
    (f"https://open.spotify.com/track/{TRACK}?si=share", f"https://open.spotify.com/track/{TRACK}"),
    (f"https://open.spotify.com/intl-de/album/{TRACK}/", f"https://open.spotify.com/album/{TRACK}"),
    (f"https://open.spotify.com/embed/playlist/{PLAYLIST}", f"https://open.spotify.com/playlist/{PLAYLIST}"),
    (f"https://play.spotify.com/episode/{TRACK}", f"https://open.spotify.com/episode/{TRACK}"),
    (f"spotify:artist:{TRACK}", f"https://open.spotify.com/artist/{TRACK}"),
    ("https://spotify.link/AbCd12?si=1", "https://spotify.link/AbCd12"),
])
def test_spotify_share_links_are_canonical(raw, expected):
    assert normalize_spotify_url(raw) == expected


@pytest.mark.parametrize("raw, message", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", PASTE),
    (r"C:\Music\private.mp3", PASTE),
    ("/home/dancer/song.wav", PASTE),
    ("javascript:alert(1)", PASTE),
    ("http://open.spotify.com/track/" + TRACK, PASTE),
    (f"https://api.spotify.com/v1/tracks/{TRACK}?client_id=SECRET", CONNECT),
    (f"https://accounts.spotify.com/authorize?client_id=SECRET", CONNECT),
    (f"https://open.spotify.com/track/{TRACK}?client_id=SECRET", KEY),
    (f"https://open.spotify.com/track/{TRACK}?client_secret=SECRET", KEY),
])
def test_spotify_field_rejects_playback_keys_and_other_sites(raw, message):
    with pytest.raises(ValueError) as error:
        normalize_spotify_url(raw)
    assert str(error.value) == message
    assert "SECRET" not in str(error.value)


def test_rehearsal_uses_the_local_file_and_never_the_link():
    link = f"https://open.spotify.com/track/{TRACK}"
    quiet = rehearsal_source({"path": None, "title": "Practice"}, link)
    assert quiet == {
        "kind": "metronome",
        "path": "",
        "open_url": link,
        "plays_spotify": False,
        "note": "Rehearsal uses the metronome. The Spotify link is only for sharing and opening the song.",
    }
    local = rehearsal_source({"path": r"C:\Music\practice.wav", "filename": "practice.wav"}, link)
    assert local["kind"] == "local"
    assert local["path"] == r"C:\Music\practice.wav"
    assert local["plays_spotify"] is False
    assert link not in local["path"]
    disguised = rehearsal_source({"path": link}, "")
    assert disguised["kind"] == "metronome"
    assert disguised["plays_spotify"] is False


def test_dance_stores_the_link_and_an_optional_local_file(client, tmp_path):
    pid = client.post("/api/projects", json={"name": "Song card"}).json()["id"]
    created = store.load_project(pid)
    assert not created["song"].get("path")
    workspace = client.get(f"/api/projects/{pid}/workspace").json()
    draft = {
        "sheet_meta": {"dance_title": "Song card", "spotify_url": f"https://open.spotify.com/playlist/{PLAYLIST}?si=drop"},
        "song": {"title": "Practice", "artist": "Example", "path": r"C:\should\not\stick.wav"},
    }
    saved = client.put(f"/api/projects/{pid}/workspace", json={"expected_revision": workspace["document_revision"], "draft": draft})
    assert saved.status_code == 200
    project = store.load_project(pid)
    assert project["sheet_meta"]["spotify_url"] == f"https://open.spotify.com/playlist/{PLAYLIST}"
    assert project["draft"]["sheet_meta"]["spotify_url"] == project["sheet_meta"]["spotify_url"]
    assert project["sheet_meta"]["dance_title"] == "Song card"
    assert not project["song"].get("path")

    rejected = client.put(
        f"/api/projects/{pid}/workspace",
        json={"expected_revision": project["document_revision"], "draft": {"sheet_meta": {"spotify_url": "https://api.spotify.com/v1/me?client_id=SECRET"}}},
    )
    assert rejected.status_code == 422
    assert "SECRET" not in rejected.text
    assert store.load_project(pid)["sheet_meta"]["spotify_url"].endswith(PLAYLIST)

    audio = tmp_path / "practice.wav"
    audio.write_bytes(b"RIFF-local")
    uploaded = client.post(f"/api/projects/{pid}/song-path", json={"path": str(audio)})
    assert uploaded.status_code == 200
    project = store.load_project(pid)
    assert project["song"]["path"] == str(audio)
    assert project["sheet_meta"]["spotify_url"] == f"https://open.spotify.com/playlist/{PLAYLIST}"
    plan = rehearsal_source(project["song"], project["sheet_meta"]["spotify_url"])
    assert plan["kind"] == "local" and plan["plays_spotify"] is False
    assert plan["path"] == str(audio)

    cleared = client.get(f"/api/projects/{pid}/workspace").json()
    result = client.put(
        f"/api/projects/{pid}/workspace",
        json={"expected_revision": cleared["document_revision"], "draft": {"sheet_meta": {"spotify_url": "  ", "dance_title": "Song card"}}},
    )
    assert result.status_code == 200
    assert store.load_project(pid)["sheet_meta"]["spotify_url"] == ""
    assert store.load_project(pid)["song"]["path"] == str(audio)


def test_sheet_shares_the_link_and_leaves_the_local_file_behind():
    project = fixture_project()
    project["draft"]["sheet_meta"]["spotify_url"] = f"https://open.spotify.com/track/{TRACK}?si=drop"
    text = export_project(project, "txt")[0].decode()
    html = export_project(project, "html")[0].decode()
    assert f"Spotify link: https://open.spotify.com/track/{TRACK}" in text
    assert f'href="https://open.spotify.com/track/{TRACK}"' in html
    assert r"C:\Private\unreleased.wav" not in text + html
    package = portable_project(project)
    encoded = json.dumps(package)
    assert package["draft"]["sheet_meta"]["spotify_url"] == f"https://open.spotify.com/track/{TRACK}"
    assert "unreleased.wav" not in encoded
    assert "spotify_url" in encoded

    project["draft"]["sheet_meta"]["spotify_url"] = "https://example.org/not-spotify"
    omitted = export_project(project, "txt")[0].decode()
    assert "not-spotify" not in omitted
    assert "Spotify link:" not in omitted
    assert portable_project(project)["draft"]["sheet_meta"]["spotify_url"] == ""


def test_song_card_copy_does_not_promise_a_spotify_connection():
    html = (ROOT / "app" / "static" / "creator.html").read_text(encoding="utf-8")
    music = html.split('data-page="music"', 1)[1].split('data-page="practice"', 1)[0]
    practice = html.split('id="practiceSource"', 1)[1].split("</p>", 1)[0]
    visible = music + practice
    for phrase in (
        "A Spotify link is for sharing and opening the song.",
        "A local audio file is optional",
        "The link does not play with the dance.",
        "They do not load into rehearsal",
        "this app does not sign in to Spotify",
        "Rehearsal uses the metronome.",
        "Local audio file (optional)",
        "Open Spotify link",
    ):
        assert phrase in visible
    lowered = visible.lower()
    for banned in ("api", "client id", "client secret", "oauth", "sync", "iframe", "embed", "web playback"):
        assert banned not in lowered
