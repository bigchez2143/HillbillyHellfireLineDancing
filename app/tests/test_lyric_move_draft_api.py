"""Backend contract checks for review-only lyric-to-move drafts."""
import copy
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server
from engine import lyric_moves as lyric_moves_engine
from engine import project as store
from engine.assembler import AssemblyError


@pytest.fixture(autouse=True)
def _isolated_projects(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "PROJECTS_DIR", str(tmp_path / "projects"))
    with server._jobs_lock:
        server._jobs.clear()
        server._alignment_jobs.clear()
    yield
    with server._jobs_lock:
        server._jobs.clear()
        server._alignment_jobs.clear()


def _make_project(tmp_path):
    project = store.create_project(
        "Lyric Move Draft Test", "Draft Song", "Hillbilly Hellfire",
    )
    song = tmp_path / "draft-song.wav"
    song.write_bytes(b"RIFF-test-audio")
    project["song"].update({"path": str(song), "filename": song.name})
    project["analysis"] = {
        "bpm": 120.0,
        "duration": 64.0,
        "source_path": str(song),
        "source_filename": song.name,
        "beat_times": [index * 0.5 for index in range(128)],
        "downbeat_times": [index * 2.0 for index in range(32)],
    }
    project["lyrics_raw"] = "[Chorus]\nStomp when the fire rolls"
    project["lyric_sections"] = [{
        "label": "Chorus", "lyrics": "Stomp when the fire rolls",
    }]
    project["alignment"] = {
        "mode": "scan",
        "suggested_sections": [{
            "label": "Chorus", "start": 8.0, "end": 24.0,
        }],
        "accepted": False,
    }
    project["dance"] = {
        "source": "generated", "counts": 32, "wall": "2", "chosen": 0,
        "candidates": [{"moves": [{"id": "grapevine-r", "counts": 4}]}],
    }
    store.save_project(project["id"], project)
    return project, song


def _review_draft():
    return {
        "schema_version": "1",
        "status": "REVIEW",
        "selected_passage_id": "chorus-1",
        "candidates": [{"id": "draft-1", "moves": []}],
        "issues": [],
    }


def test_new_projects_include_separate_empty_lyric_move_draft(tmp_path):
    project = store.create_project("Fresh Project")

    assert "lyric_move_draft" in project
    assert project["lyric_move_draft"] is None
    assert store.load_project(project["id"])["lyric_move_draft"] is None


def test_draft_route_saves_proposal_without_changing_existing_dance(
        tmp_path, monkeypatch):
    project, _ = _make_project(tmp_path)
    original_dance = copy.deepcopy(project["dance"])
    expected_draft = _review_draft()
    captured = {}

    def build_draft(project_input, settings, passage_id=None, fill_gaps=True):
        captured.update({
            "settings": settings,
            "passage_id": passage_id,
            "fill_gaps": fill_gaps,
        })
        # Even a poorly behaved engine call cannot mutate the persisted dance.
        project_input["dance"]["chosen"] = 999
        return copy.deepcopy(expected_draft)

    monkeypatch.setattr(lyric_moves_engine, "build_draft", build_draft)
    body = server.LyricMoveDraftBody(
        level="I", wall="4R", turn_dir="R", counts=64, seed=7, k=2,
        allow_sync=True, experimental_mode=True, publication_mode=False,
        include_custom_moves=True, passage_id="chorus-1", fill_gaps=False,
    )

    result = server.draft_lyric_moves(project["id"], body)

    assert result == expected_draft
    assert captured == {
        "settings": {
            "level": "I", "wall": "4R", "turn_dir": "R", "counts": 64,
            "seed": 7, "k": 2, "allow_sync": True,
            "experimental_mode": True, "publication_mode": False,
            "include_custom_moves": True,
        },
        "passage_id": "chorus-1",
        "fill_gaps": False,
    }
    saved = store.load_project(project["id"])
    assert saved["lyric_move_draft"] == expected_draft
    assert saved["dance"] == original_dance


def test_draft_route_returns_structured_422_and_preserves_project(
        tmp_path, monkeypatch):
    project, _ = _make_project(tmp_path)
    before = store.load_project(project["id"])

    def fail(*args, **kwargs):
        raise AssemblyError(
            "NO_VALID_PATH", "No safe movement sequence fits this passage.",
            {"passage_id": "chorus-1"},
        )

    monkeypatch.setattr(lyric_moves_engine, "build_draft", fail)
    response = server.draft_lyric_moves(
        project["id"], server.LyricMoveDraftBody(passage_id="chorus-1"),
    )

    assert response.status_code == 422
    assert json.loads(response.body) == {
        "error": "NO_VALID_PATH",
        "message": "No safe movement sequence fits this passage.",
        "details": {"passage_id": "chorus-1"},
    }
    assert store.load_project(project["id"]) == before


def test_lyrics_and_alignment_changes_mark_saved_draft_stale(tmp_path):
    project, _ = _make_project(tmp_path)
    project["lyric_move_draft"] = _review_draft()
    original_dance = copy.deepcopy(project["dance"])
    store.save_project(project["id"], project)

    server.set_lyrics(
        project["id"], server.LyricsBody(text="[Chorus]\nA corrected lyric"),
    )
    after_lyrics = store.load_project(project["id"])
    assert after_lyrics["lyric_move_draft"]["status"] == "STALE"
    assert after_lyrics["lyric_move_draft"]["previous_status"] == "REVIEW"
    assert "Lyrics" in after_lyrics["lyric_move_draft"]["stale_reason"]
    assert after_lyrics["dance"] == original_dance

    after_lyrics["lyric_move_draft"] = _review_draft()
    after_lyrics["alignment"] = {
        "suggested_sections": [{
            "label": "Chorus", "start": 8.0, "end": 24.0,
        }],
    }
    store.save_project(project["id"], after_lyrics)
    server.accept_alignment(project["id"])

    after_alignment = store.load_project(project["id"])
    assert after_alignment["lyric_move_draft"]["status"] == "STALE"
    assert "alignment" in after_alignment["lyric_move_draft"]["stale_reason"]
    assert after_alignment["dance"] == original_dance


def test_completed_audio_analysis_marks_saved_draft_stale(
        tmp_path, monkeypatch):
    project, song = _make_project(tmp_path)
    project["lyric_move_draft"] = _review_draft()
    original_dance = copy.deepcopy(project["dance"])
    store.save_project(project["id"], project)
    with server._jobs_lock:
        server._jobs[project["id"]] = {
            "status": "running", "generation": 1, "path": str(song),
        }

    monkeypatch.setattr(server.audio_engine, "analyze", lambda *args, **kwargs: {
        "bpm": 121.0, "duration": 64.0, "beat_times": [],
        "downbeat_times": [],
    })
    server._run_analysis(project["id"], str(song), 1)

    saved = store.load_project(project["id"])
    assert saved["analysis"]["bpm"] == 121.0
    assert saved["lyric_move_draft"]["status"] == "STALE"
    assert "Audio analysis" in saved["lyric_move_draft"]["stale_reason"]
    assert saved["dance"] == original_dance


def test_identical_audio_analysis_does_not_falsely_stale_draft(
        tmp_path, monkeypatch):
    project, song = _make_project(tmp_path)
    project["lyric_move_draft"] = _review_draft()
    store.save_project(project["id"], project)
    with server._jobs_lock:
        server._jobs[project["id"]] = {
            "status": "running", "generation": 1, "path": str(song),
        }

    same_analysis = copy.deepcopy(project["analysis"])
    monkeypatch.setattr(
        server.audio_engine, "analyze",
        lambda *args, **kwargs: copy.deepcopy(same_analysis),
    )
    server._run_analysis(project["id"], str(song), 1)

    saved = store.load_project(project["id"])
    assert saved["lyric_move_draft"]["status"] == "REVIEW"


def test_reaccepting_unchanged_alignment_does_not_falsely_stale_draft(tmp_path):
    project, _ = _make_project(tmp_path)
    project["alignment"].update({
        "accepted": True,
        "manual_decision": "accepted_suggestions",
    })
    project["lyric_move_draft"] = _review_draft()
    store.save_project(project["id"], project)

    server.accept_alignment(project["id"])

    saved = store.load_project(project["id"])
    assert saved["lyric_move_draft"]["status"] == "REVIEW"


def test_replacing_song_clears_saved_lyric_move_draft(tmp_path):
    project, _ = _make_project(tmp_path)
    project["lyric_move_draft"] = _review_draft()
    store.save_project(project["id"], project)
    replacement = tmp_path / "replacement.wav"
    replacement.write_bytes(b"RIFF-replacement")

    server.set_song_path(
        project["id"], server.SongPath(path=str(replacement)),
    )

    saved = store.load_project(project["id"])
    assert saved["song"]["path"] == str(replacement)
    assert saved["lyric_move_draft"] is None
