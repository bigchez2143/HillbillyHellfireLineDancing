"""Regression checks for background audio-analysis job state."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server
from engine import project as store


class _DeferredThread:
    """Record a requested worker without running audio analysis in the test."""

    created = []

    def __init__(self, target, args=(), kwargs=None, daemon=None):
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}
        self.daemon = daemon
        self.started = False
        self.__class__.created.append(self)

    def start(self):
        self.started = True


@pytest.fixture(autouse=True)
def _isolated_projects(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(server.threading, "Thread", _DeferredThread)
    _DeferredThread.created.clear()
    with server._jobs_lock:
        server._jobs.clear()
    yield
    with server._jobs_lock:
        server._jobs.clear()


def _make_project(tmp_path):
    project = store.create_project("Analysis Job Test", "Test Song",
                                   "Hillbilly Hellfire")
    song = tmp_path / "same-name.mp3"
    song.write_bytes(b"ID3-test-audio")
    project["song"]["path"] = str(song)
    project["song"]["filename"] = song.name
    store.save_project(project["id"], project)
    return project, song


def test_superseded_analysis_is_marked_stale(tmp_path):
    project, song = _make_project(tmp_path)
    with server._jobs_lock:
        server._jobs[project["id"]] = {
            "status": "running",
            "generation": 1,
            "path": str(song),
            "message": "Measuring tempo (method 2/4: beat tracker)...",
        }

    server._supersede_job(project["id"])

    status = server.analysis_status(project["id"])
    assert status["status"] == "stale"
    assert status["generation"] == 2
    assert status["superseded"] is True
    assert "Run Analyze again" in status["message"]


def test_analyze_restarts_a_superseded_same_path_job(tmp_path):
    project, song = _make_project(tmp_path)
    with server._jobs_lock:
        server._jobs[project["id"]] = {
            "status": "running",
            "generation": 2,
            "path": str(song),
            "message": "Old worker status",
            "superseded": True,
        }

    started = server.analyze(project["id"])

    assert started["status"] == "running"
    status = server.analysis_status(project["id"])
    assert status["status"] == "running"
    assert status["generation"] == 3
    assert status["superseded"] is False
    assert len(_DeferredThread.created) == 1
    assert _DeferredThread.created[0].started is True
