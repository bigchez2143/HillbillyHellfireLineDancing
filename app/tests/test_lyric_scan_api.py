"""Route-level safety checks for transcription-first lyric scanning."""
import os
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server
from engine import alignment as alignment_engine
from engine import project as store


class _ImmediateThread:
    """Run a background target inline so route tests stay deterministic."""

    def __init__(self, target, args=(), kwargs=None, daemon=None):
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}

    def start(self):
        self.target(*self.args, **self.kwargs)


@pytest.fixture(autouse=True)
def _isolated_projects(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(server.threading, "Thread", _ImmediateThread)
    with server._jobs_lock:
        server._jobs.clear()
        server._alignment_jobs.clear()
    yield
    with server._jobs_lock:
        server._jobs.clear()
        server._alignment_jobs.clear()


def _make_project(tmp_path, *, analyzed=True):
    project = store.create_project("Lyric Scan Test", "Scan Song", "Hillbilly Hellfire")
    song = tmp_path / "scan-song.wav"
    song.write_bytes(b"RIFF-original-audio")
    project["song"]["path"] = str(song)
    project["song"]["filename"] = song.name
    if analyzed:
        project["analysis"] = {
            "source_path": str(song),
            "source_filename": song.name,
            "bpm": 120.0,
            "duration": 64.0,
            "beat_times": [float(index) / 2 for index in range(128)],
            "downbeat_times": [float(index) * 2 for index in range(32)],
        }
    store.save_project(project["id"], project)
    return project, song


def _scan_payload():
    return {
        "mode": "scan",
        "status": "review",
        "issues": [{"severity": "info", "message": "Review the draft labels."}],
        "lyrics_text": "[Verse 1]\nBoots hit the floor\n[Chorus]\nStomp once more",
        "captions": [
            {"id": 1, "label": "Verse 1", "text": "Boots hit the floor",
             "start": 4.0, "end": 12.0, "confidence": 0.92},
            {"id": 2, "label": "Chorus", "text": "Stomp once more",
             "start": 20.0, "end": 30.0, "confidence": 0.89},
        ],
        "suggested_sections": [
            {"label": "Verse 1", "start": 4.0, "end": 20.0, "confidence": 0.92},
            {"label": "Chorus", "start": 20.0, "end": 36.0, "confidence": 0.89},
        ],
        "summary": {"confidence": 0.9, "timed_lines": 2, "lyric_lines": 2},
    }


def test_scan_blank_project_applies_transcript_and_section_draft(tmp_path, monkeypatch):
    project, _ = _make_project(tmp_path)
    before = store.load_project(project["id"])
    before["phrase"] = {"status": "CLEAN"}
    before["tutorial"] = {"status": "READY"}
    store.save_project(project["id"], before)

    monkeypatch.setattr(alignment_engine, "scan",
                        lambda path, analysis, progress=None: _scan_payload())
    started = server.scan_lyrics(project["id"])
    assert started["status"] == "running"
    assert started["mode"] == "scan"

    saved = store.load_project(project["id"])
    assert saved["lyrics_raw"].startswith("[Verse 1]")
    assert [row["label"] for row in saved["lyric_sections"]] == ["Verse 1", "Chorus"]
    assert saved["sections"] == [
        {"label": "Verse 1", "start": 4.0, "end": 20.0},
        {"label": "Chorus", "start": 20.0, "end": 36.0},
    ]
    assert saved["phrase"] is None
    assert saved["tutorial"] is None
    assert saved["alignment"]["lyrics_applied"] is True
    assert saved["alignment"]["sections_applied"] is True
    assert saved["alignment"]["manual_decision"] == "auto_assigned_scan"
    status = server.alignment_status(project["id"])
    assert status["status"] == "done"
    assert status["mode"] == "scan"
    assert "Draft" in status["message"] and "ready" in status["message"]


def test_scan_preserves_existing_lyrics_markers_phrase_and_tutorial(tmp_path, monkeypatch):
    project, _ = _make_project(tmp_path)
    existing = store.load_project(project["id"])
    existing["lyrics_raw"] = "[Verse]\nMy corrected lyric"
    existing["lyric_sections"] = [{"label": "Verse", "lyrics": "My corrected lyric"}]
    existing["sections"] = [{"label": "My marker", "start": 2.0, "end": 34.0}]
    existing["phrase"] = {"status": "REVIEW", "kept": True}
    existing["tutorial"] = {"status": "REVIEW", "kept": True}
    store.save_project(project["id"], existing)

    monkeypatch.setattr(alignment_engine, "scan",
                        lambda path, analysis, progress=None: _scan_payload())
    server.scan_lyrics(project["id"])

    saved = store.load_project(project["id"])
    assert saved["lyrics_raw"] == existing["lyrics_raw"]
    assert saved["lyric_sections"] == existing["lyric_sections"]
    assert saved["sections"] == existing["sections"]
    assert saved["phrase"] == existing["phrase"]
    assert saved["tutorial"] == existing["tutorial"]
    assert saved["alignment"]["lyrics_applied"] is False
    assert saved["alignment"]["sections_applied"] is False
    assert saved["alignment"]["suggested_sections"]


def test_rescan_replaces_unchanged_generated_draft_but_not_user_work(tmp_path, monkeypatch):
    project, _ = _make_project(tmp_path)
    existing = store.load_project(project["id"])
    old_lyrics = "[Section 1]\nOnly the spoken introduction"
    old_sections = [{"label": "Section 1", "start": 2.0, "end": 8.0}]
    existing["lyrics_raw"] = old_lyrics
    existing["lyric_sections"] = [
        {"label": "Section 1", "lyrics": "Only the spoken introduction"}
    ]
    existing["sections"] = old_sections
    existing["phrase"] = {"status": "CLEAN", "from_old_draft": True}
    existing["tutorial"] = {"status": "READY", "from_old_draft": True}
    existing["alignment"] = {
        "mode": "scan",
        "lyrics_text": old_lyrics,
        "suggested_sections": [
            {"label": "Section 1", "start": 2.0, "end": 8.0,
             "confidence": 0.5}
        ],
        # A prior rescan can have this value even though the visible material
        # still exactly matches the app-generated draft.
        "manual_decision": "preserved_existing_work",
    }
    store.save_project(project["id"], existing)

    monkeypatch.setattr(alignment_engine, "scan",
                        lambda path, analysis, progress=None: _scan_payload())
    server.scan_lyrics(project["id"])

    saved = store.load_project(project["id"])
    assert saved["lyrics_raw"] == _scan_payload()["lyrics_text"]
    assert saved["sections"] == [
        {"label": "Verse 1", "start": 4.0, "end": 20.0},
        {"label": "Chorus", "start": 20.0, "end": 36.0},
    ]
    assert saved["phrase"] is None
    assert saved["tutorial"] is None
    assert saved["alignment"]["lyrics_applied"] is True
    assert saved["alignment"]["sections_applied"] is True
    assert saved["alignment"]["manual_decision"] == "auto_assigned_scan"


def test_scan_requires_completed_audio_analysis(tmp_path, monkeypatch):
    project, _ = _make_project(tmp_path, analyzed=False)

    def should_not_run(*args, **kwargs):
        raise AssertionError("scan must not start without analysis")

    monkeypatch.setattr(alignment_engine, "scan", should_not_run, raising=False)
    with pytest.raises(HTTPException) as caught:
        server.scan_lyrics(project["id"])
    assert caught.value.status_code == 409
    assert "Analyze the song first" in caught.value.detail
    assert store.load_project(project["id"])["alignment"] is None


def test_scan_discards_result_when_same_path_file_is_replaced(tmp_path, monkeypatch):
    project, song = _make_project(tmp_path)

    def replace_during_scan(path, analysis, progress=None):
        song.write_bytes(b"RIFF-a-different-recording-with-a-different-size")
        return _scan_payload()

    monkeypatch.setattr(alignment_engine, "scan", replace_during_scan)
    server.scan_lyrics(project["id"])

    saved = store.load_project(project["id"])
    assert saved["lyrics_raw"] == ""
    assert saved["sections"] == []
    assert saved["alignment"] is None
    status = server.alignment_status(project["id"])
    assert status["status"] == "stale"
    assert "song file changed" in status["message"].lower()


def test_scan_error_does_not_partially_mutate_project(tmp_path, monkeypatch):
    project, _ = _make_project(tmp_path)
    original = store.load_project(project["id"])

    def fail_scan(path, analysis, progress=None):
        raise alignment_engine.AlignmentError("The vocals were not clear enough.")

    monkeypatch.setattr(alignment_engine, "scan", fail_scan)
    server.scan_lyrics(project["id"])

    saved = store.load_project(project["id"])
    assert saved == original
    status = server.alignment_status(project["id"])
    assert status["status"] == "error"
    assert status["mode"] == "scan"
    assert "not clear enough" in status["message"]


def test_blocked_no_vocal_result_surfaces_the_engine_reason(tmp_path, monkeypatch):
    project, _ = _make_project(tmp_path)
    original = store.load_project(project["id"])

    monkeypatch.setattr(alignment_engine, "scan", lambda *args, **kwargs: {
        "mode": "auto_scan",
        "status": "BLOCKED",
        "lyrics_text": "",
        "suggested_sections": [],
        "issues": [{
            "severity": "error",
            "code": "NO_DEPENDABLE_VOCALS",
            "message": "No dependable timed vocals were found; nothing was invented.",
        }],
    })
    server.scan_lyrics(project["id"])

    assert store.load_project(project["id"]) == original
    status = server.alignment_status(project["id"])
    assert status["status"] == "error"
    assert "nothing was invented" in status["message"]


def test_scan_discards_result_if_lyrics_are_edited_while_it_runs(tmp_path, monkeypatch):
    project, _ = _make_project(tmp_path)

    def edit_during_scan(path, analysis, progress=None):
        current = store.load_project(project["id"])
        current["lyrics_raw"] = "[Verse]\nMy edit wins"
        current["lyric_sections"] = [{"label": "Verse", "lyrics": "My edit wins"}]
        store.save_project(project["id"], current)
        return _scan_payload()

    monkeypatch.setattr(alignment_engine, "scan", edit_during_scan)
    server.scan_lyrics(project["id"])

    saved = store.load_project(project["id"])
    assert saved["lyrics_raw"] == "[Verse]\nMy edit wins"
    assert saved["alignment"] is None
    assert saved["sections"] == []
    status = server.alignment_status(project["id"])
    assert status["status"] == "stale"
    assert "your edit was kept" in status["message"]


def test_manual_section_save_wins_over_running_scan(tmp_path, monkeypatch):
    project, _ = _make_project(tmp_path)
    manual = [{"label": "My section", "start": 1.0, "end": 33.0}]

    def edit_sections_during_scan(path, analysis, progress=None):
        server.set_sections(project["id"], server.SectionsBody(sections=manual))
        return _scan_payload()

    monkeypatch.setattr(alignment_engine, "scan", edit_sections_during_scan)
    server.scan_lyrics(project["id"])

    saved = store.load_project(project["id"])
    assert saved["sections"] == manual
    assert saved["lyrics_raw"] == ""
    assert saved["alignment"] is None
    status = server.alignment_status(project["id"])
    assert status["status"] == "stale"
    assert "markers were kept" in status["message"]


def test_scan_discards_result_if_analysis_changes_while_it_runs(tmp_path, monkeypatch):
    project, _ = _make_project(tmp_path)

    def change_analysis(path, analysis, progress=None):
        current = store.load_project(project["id"])
        current["analysis"]["bpm"] = 121.0
        store.save_project(project["id"], current)
        return _scan_payload()

    monkeypatch.setattr(alignment_engine, "scan", change_analysis)
    server.scan_lyrics(project["id"])

    saved = store.load_project(project["id"])
    assert saved["analysis"]["bpm"] == 121.0
    assert saved["alignment"] is None
    assert saved["lyrics_raw"] == ""
    status = server.alignment_status(project["id"])
    assert status["status"] == "stale"
    assert "analysis changed" in status["message"].lower()
