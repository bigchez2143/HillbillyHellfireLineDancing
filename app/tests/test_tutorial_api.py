"""Route-function checks for the Tutorial Blueprint workflow."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server
from engine.assembler import assemble
from engine import project as store


def _project_with_ready_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "PROJECTS_DIR", str(tmp_path / "projects"))
    project = store.create_project("Tutorial Route Test", "Route Song", "Hillbilly Hellfire")
    beat_times = [round(1.0 + index * 0.5, 4) for index in range(180)]
    project["analysis"] = {
        "bpm": 120.0,
        "duration": 92.0,
        "beat_times": beat_times,
        "downbeat_times": beat_times[::4],
        "bpm_confidence": "high",
        "bpm_confidence_notes": [],
        "octave_alternates": [],
        "drift": None,
        "phase_contrast": 0.5,
        "methods": {
            "autocorrelation": 120.0,
            "beat_tracker_median_ibi": 120.0,
            "tempogram_peak": 120.0,
            "windowed_median": 120.0,
        },
    }
    project["phrase"] = {
        "status": "CLEAN",
        "flags": [],
        "sections": [{"label": "Verse 1", "start": 3.0, "end": 35.0}],
        "music_map": {"markers_preserved": True},
        "dance_fit": {
            "pattern_len": 16,
            "anchor": {"section": "Verse 1", "time": 3.0},
        },
        "intro": {"beats": 4, "residual": 0},
        "outro_beats": 0,
        "tiling": {"pattern_len": 16, "danced_beats": 64,
                   "repetitions": 4, "clean": True},
        "totals": {"forward": 64, "measured": 64},
        "bpm": 120.0,
    }
    generated = assemble(total_counts=16, wall="1", turn_dir="L",
                         level="AB", seed=9, k=1, bpm=120.0)
    project["dance"] = {
        "source": "generated", "counts": 16, "wall": "1",
        "turn_dir": "L", "level": "AB", "chosen": 0,
        "tempo": generated["tempo"], "candidates": generated["candidates"],
        "gen_params": {"counts": 16, "wall": "1", "turn_dir": "L",
                       "level": "AB", "tempo": generated["tempo"]},
    }
    store.save_project(project["id"], project)
    return project


def test_tutorial_routes_build_review_confirm_and_export(tmp_path, monkeypatch):
    project = _project_with_ready_sources(tmp_path, monkeypatch)
    built = server.build_tutorial(
        project["id"],
        server.TutorialBuildBody(voice_name="Georgia Belle", callout_lead_counts=2),
    )
    plan = built["tutorial"]
    assert plan["validation"]["status"] == "REVIEW"
    assert plan["validation"]["confirmation_pending"] == len(plan["segments"])

    edits = [{
        "id": segment["id"],
        "callout": segment["callout"]["text"],
        "camera": segment["camera"]["primary"],
        "confirmed": True,
        "review_note": "Counts and feet checked.",
    } for segment in plan["segments"]]
    saved = server.update_tutorial(
        project["id"], server.TutorialUpdateBody(segments=edits),
    )
    assert saved["tutorial"]["validation"]["ready"] is True

    assert "LINE-DANCE TUTORIAL BLUEPRINT" in server.tutorial_txt(project["id"]).body.decode()
    csv_response = server.tutorial_csv(project["id"])
    assert "gb_callout" in csv_response.body.decode()
    json_response = server.tutorial_json(project["id"])
    assert json.loads(json_response.body)["validation"]["ready"] is True

    monkeypatch.setattr(server, "APP_DIR", str(tmp_path / "app"))
    exported = server.export_files(project["id"])
    assert any(name.endswith("tutorial call and shot list.txt")
               for name in exported["files"])
    assert any(name.endswith("tutorial timeline.csv") for name in exported["files"])
    assert any(name.endswith("tutorial blueprint.json") for name in exported["files"])
    assert "WARNING - tutorial blueprint not ready.txt" not in exported["files"]


def test_tutorial_route_reports_stale_analysis(tmp_path, monkeypatch):
    project = _project_with_ready_sources(tmp_path, monkeypatch)
    server.build_tutorial(project["id"], server.TutorialBuildBody())

    changed = store.load_project(project["id"])
    changed["analysis"]["bpm"] = 121.0
    store.save_project(project["id"], changed)

    report = server.get_tutorial(project["id"])["tutorial"]["validation"]
    assert report["ready"] is False
    assert any(issue["code"] == "STALE_ANALYSIS" for issue in report["errors"])
