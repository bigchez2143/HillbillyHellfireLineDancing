"""Focused tests for the count-locked tutorial production contract."""
import csv
import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.assembler import validate_sequence
from engine.steps import MOVE_BY_ID
from engine.tutorial import (
    build_tutorial_plan,
    confirm_tutorial_segment,
    render_tutorial_csv,
    render_tutorial_json,
    render_tutorial_txt,
    update_tutorial_plan,
    validate_tutorial_plan,
)


def _analysis(bpm=120.0, start=0.0, methods=None):
    step = 60.0 / bpm
    beats = [round(start + i * step, 6) for i in range(160)]
    return {
        "bpm": bpm,
        "duration": beats[-1] + step,
        "beat_times": beats,
        "downbeat_times": beats[::4],
        "octave_alternates": [],
        "drift": None,
        "phase_contrast": 0.5,
        "bpm_confidence": "high",
        "methods": methods or {},
    }


def _dance():
    moves = [
        MOVE_BY_ID["vine_touch"].variant("R"),
        MOVE_BY_ID["vine_touch"].variant("L"),
    ]
    validation = validate_sequence(moves, 8, "1", bpm=120)
    assert validation["valid"]
    return {
        "moves": moves,
        "total_counts": 8,
        "wall": "1",
        "walls": 1,
        "net_rot": 0,
        "turn_dir": "L",
        "validation": validation,
    }


def _phrase(anchor=4.0):
    return {
        "status": "CLEAN",
        "flags": [],
        "dance_fit": {
            "mode": "continuous",
            "pattern_len": 8,
            "anchor": {"section": "Verse", "time": anchor, "marker_offset_ms": 0},
        },
    }


def _plan(**kwargs):
    return build_tutorial_plan(_dance(), _analysis(), _phrase(), **kwargs)


def test_builds_review_plan_from_exact_move_lines_and_canonical_beat_indexes():
    dance = _dance()
    plan = build_tutorial_plan(dance, _analysis(), _phrase())

    assert plan["status"] == "REVIEW"
    assert plan["validation"]["errors"] == []
    assert plan["validation"]["confirmation_pending"] == 2
    assert plan["settings"]["count_in"] == "Five, six, seven, eight"
    assert plan["source"]["anchor_beat_index"] == 8
    first = plan["segments"][0]
    assert first["start_beat_index"] == 8
    assert first["end_beat_index_exclusive"] == 12
    assert first["start_seconds"] == 4.0
    assert first["timecode"] == "00:00:04.000"
    assert first["callout"]["beat_index"] == 6
    assert first["callout"]["seconds"] == 3.0
    assert first["callout"]["text"] == first["move_name"]
    assert first["camera"]["view"] == "rear_wide"
    assert first["camera"]["feet_visible"] is True
    assert [line["text"] for line in first["instruction_lines"]] == [
        line["text"] for line in dance["moves"][0]["lines"]
    ]
    assert plan["wall_plan"][0]["start_facing"] == "12:00"
    assert plan["wall_plan"][0]["end_facing"] == "12:00"
    json.dumps(plan, allow_nan=False)


def test_negative_grid_indexes_are_valid_when_the_audio_contains_preroll():
    # The detector's returned grid begins at the dance anchor, but the source
    # recording has eight seconds before it. Calls and count-in may use
    # relative negative indexes without pretending the audio starts late.
    analysis = _analysis(start=8.0)
    plan = build_tutorial_plan(_dance(), analysis, _phrase(anchor=8.0))
    first = plan["segments"][0]

    assert plan["source"]["anchor_beat_index"] == 0
    assert plan["source"]["count_in_beat_index"] == -4
    assert plan["source"]["count_in_seconds"] == 6.0
    assert first["callout"]["beat_index"] == -2
    assert first["callout"]["seconds"] == 7.0
    assert plan["validation"]["errors"] == []


def test_initial_intro_section_moves_default_count_one_to_after_intro():
    phrase = _phrase(anchor=0.0)
    phrase["sections"] = [
        {"label": "Intro", "start": 0.0, "end": 4.0},
        {"label": "Verse 1", "start": 4.0, "end": 20.0},
    ]
    plan = build_tutorial_plan(_dance(), _analysis(), phrase)
    assert plan["source"]["anchor_policy"] == "after_intro"
    assert plan["source"]["anchor_source_label"] == "Intro"
    assert plan["source"]["anchor_seconds"] == 4.0
    assert plan["source"]["anchor_beat_index"] == 8
    assert plan["validation"]["errors"] == []

    manual = build_tutorial_plan(
        _dance(), _analysis(), phrase, anchor_seconds=6.0,
    )
    assert manual["source"]["anchor_policy"] == "manual_override"
    assert manual["source"]["anchor_source_seconds"] == 6.0
    assert manual["source"]["anchor_beat_index"] == 12


def test_real_audio_without_preroll_blocks_negative_count_in_and_callout():
    plan = build_tutorial_plan(_dance(), _analysis(), _phrase(anchor=0.0))
    codes = {issue["code"] for issue in plan["validation"]["errors"]}
    assert plan["status"] == "BLOCKED"
    assert "COUNT_IN_PREROLL_MISSING" in codes
    assert "CALLOUT_TIMING_INVALID" in codes


def test_selected_bpm_must_match_saved_beat_index_cadence():
    analysis = _analysis(bpm=120.0, start=8.0)
    analysis["bpm"] = 60.0  # stale label over a still-120-BPM beat grid
    plan = build_tutorial_plan(
        _dance(), analysis, _phrase(anchor=8.0), tempo_grid_confirmed=True,
    )
    assert plan["source"]["grid_bpm"] == 120.0
    assert plan["source"]["bpm_grid_mismatch"] is True
    assert any(issue["code"] == "BPM_GRID_MISMATCH"
               for issue in plan["validation"]["errors"])
    assert plan["status"] == "BLOCKED"


def test_half_double_method_consensus_requires_explicit_floor_confirmation():
    methods = {
        "autocorrelation": 123.8,
        "beat_tracker_median_ibi": 124.1,
        "tempogram_peak": 123.9,
        "windowed_median": 124.0,
    }
    analysis = _analysis(bpm=62.0, methods=methods)
    phrase = _phrase(anchor=60.0 / 62.0 * 8)
    blocked = build_tutorial_plan(_dance(), analysis, phrase)
    codes = {issue["code"] for issue in blocked["validation"]["errors"]}
    assert blocked["source"]["method_octave_mismatch"] is True
    assert "TEMPO_GRID_UNCONFIRMED" in codes

    accepted = build_tutorial_plan(
        _dance(), analysis, phrase, tempo_grid_confirmed=True,
    )
    assert accepted["status"] == "REVIEW"
    assert "TEMPO_GRID_UNCONFIRMED" not in {
        issue["code"] for issue in accepted["validation"]["errors"]
    }
    assert any(issue["code"] == "METHOD_CONSENSUS_MISMATCH"
               for issue in accepted["validation"]["warnings"])


def test_human_edits_are_narrow_revisioned_and_can_make_plan_ready():
    plan = _plan()
    old_hash = plan["provenance_hash"]
    edits = []
    for index, segment in enumerate(plan["segments"]):
        edits.append({
            "id": segment["id"],
            "callout": "Vine right" if index == 0 else "Vine left",
            "camera": "side_full" if index == 0 else segment["camera"]["view"],
            "confirmed": True,
            "review_note": "Floor tested",
        })
    updated = update_tutorial_plan(
        plan, edits,
        count_in="Five, six, seven, eight",
        voice_notes="Clear and early",
        producer_notes="Rear master plus insert",
    )

    assert updated["status"] == "READY"  # a side primary is a warning, not a hidden block
    assert updated["validation"]["ready"] is True
    assert updated["blueprint_revision"] == 2
    assert updated["provenance_hash"] != old_hash
    assert updated["segments"][0]["callout"]["text"] == "Vine right"
    assert updated["segments"][0]["camera"]["orientation"] == "side-teaching-view"
    assert "Side teaching view" in updated["segments"][0]["camera"]["reason"]
    assert any(issue["code"] == "NON_REAR_PRIMARY"
               for issue in updated["validation"]["warnings"])

    with pytest.raises(ValueError, match="immutable"):
        update_tutorial_plan(plan, [{"id": plan["segments"][0]["id"], "counts": 99}])


def test_single_confirmation_helper_never_skips_remaining_reviews():
    plan = _plan()
    first = confirm_tutorial_segment(
        plan, plan["segments"][0]["id"], review_note="Checked", confirmed_at="2026-09-03T00:00:00Z",
    )
    assert first["status"] == "REVIEW"
    assert first["validation"]["confirmation_pending"] == 1
    second = confirm_tutorial_segment(
        first, first["segments"][1]["id"], confirmed_at="2026-09-03T00:00:01Z",
    )
    assert second["status"] == "READY"
    assert second["blueprint_revision"] == 3


def test_mutable_edit_path_cannot_launder_tampering_or_silently_keep_confirmation():
    plan = _plan()
    ready = update_tutorial_plan(plan, [
        {
            "id": segment["id"],
            "callout": segment["callout"]["text"],
            "camera": segment["camera"]["view"],
            "confirmed": True,
            "review_note": "Checked",
        }
        for segment in plan["segments"]
    ])
    assert ready["status"] == "READY"

    revised = update_tutorial_plan(ready, [{
        "id": ready["segments"][0]["id"],
        "callout": "Shorter human call",
    }])
    assert revised["status"] == "REVIEW"
    assert revised["segments"][0]["confirmed"] is False
    assert revised["validation"]["confirmation_pending"] == 1

    tampered = json.loads(json.dumps(ready))
    tampered["segments"][0]["move_name"] = "Laundered move"
    with pytest.raises(ValueError, match="provenance"):
        update_tutorial_plan(tampered, [], producer_notes="Try to bless it")
    with pytest.raises(ValueError, match="provenance"):
        confirm_tutorial_segment(tampered, tampered["segments"][0]["id"])


def test_rebuild_does_not_transfer_confirmations_to_different_same_span_moves():
    plan = _plan()
    ready = update_tutorial_plan(plan, [
        {
            "id": segment["id"],
            "callout": segment["callout"]["text"],
            "camera": segment["camera"]["view"],
            "confirmed": True,
            "review_note": "Checked",
        }
        for segment in plan["segments"]
    ])
    alternate_moves = [
        MOVE_BY_ID["rocking_chair"].variant("R"),
        MOVE_BY_ID["rocking_chair"].variant("R"),
    ]
    alternate_validation = validate_sequence(alternate_moves, 8, "1", bpm=120)
    alternate = {
        "moves": alternate_moves,
        "total_counts": 8,
        "wall": "1",
        "walls": 1,
        "net_rot": 0,
        "turn_dir": "L",
        "validation": alternate_validation,
    }
    rebuilt = build_tutorial_plan(
        alternate, _analysis(), _phrase(),
        confirmations={segment["id"]: segment for segment in ready["segments"]},
    )
    assert rebuilt["status"] == "REVIEW"
    assert rebuilt["validation"]["confirmation_pending"] == 2
    assert all(segment["confirmed"] is False for segment in rebuilt["segments"])

    shifted_analysis = _analysis(start=0.1)
    shifted = build_tutorial_plan(
        _dance(), shifted_analysis, _phrase(anchor=4.1),
        confirmations={segment["id"]: segment for segment in ready["segments"]},
    )
    assert shifted["status"] == "REVIEW"
    assert all(segment["confirmed"] is False for segment in shifted["segments"])


def test_invalid_dance_missing_phrasing_and_stale_sources_are_blocked():
    dance = _dance()
    dance["validation"] = {
        "valid": False,
        "problems": [{"code": "FOOT_BREAK", "message": "Feet do not loop."}],
    }
    invalid = build_tutorial_plan(dance, _analysis(), _phrase())
    assert invalid["status"] == "BLOCKED"
    assert any(issue["code"] == "INVALID_DANCE" for issue in invalid["validation"]["errors"])

    missing_phrase = build_tutorial_plan(_dance(), _analysis(), {})
    codes = {issue["code"] for issue in missing_phrase["validation"]["errors"]}
    assert {"PHRASE_MISSING", "MISSING_COUNT_ANCHOR"} <= codes

    current_dance = _dance()
    plan = build_tutorial_plan(current_dance, _analysis(), _phrase())
    changed = _dance()
    changed["moves"][0] = dict(changed["moves"][0], name="Edited Vine")
    report = validate_tutorial_plan(plan, changed, _analysis(), _phrase())
    stale_codes = {issue["code"] for issue in report["errors"]}
    assert {"STALE_DANCE", "STALE_SEGMENT_MOVE"} <= stale_codes

    changed_direction = _dance()
    changed_direction["turn_dir"] = "R"
    direction_report = validate_tutorial_plan(
        plan, changed_direction, _analysis(), _phrase(),
    )
    assert any(issue["code"] == "STALE_DANCE"
               for issue in direction_report["errors"])


def test_instruction_timing_callout_and_camera_tampering_is_detected():
    plan = _plan()
    segment = plan["segments"][0]
    segment["instruction_lines"][0]["text"] = "Invented atomic footwork"
    segment["callout"]["beat_index"] += 1
    segment["camera"]["feet_visible"] = False
    report = validate_tutorial_plan(plan)
    codes = {issue["code"] for issue in report["errors"]}
    assert {
        "PROVENANCE_MISMATCH",
        "INSTRUCTION_SOURCE_CHANGED",
        "CALLOUT_TIMING_INVALID",
        "FEET_OBSTRUCTED",
    } <= codes


def test_txt_csv_and_json_renderers_carry_production_contract():
    plan = _plan()
    txt = render_tutorial_txt(plan)
    assert "LINE-DANCE TUTORIAL BLUEPRINT" in txt
    assert "GB count-in: Five, six, seven, eight" in txt
    assert "SOURCE INSTRUCTIONS ARE VERBATIM" in txt
    assert plan["segments"][0]["move_name"] in txt

    csv_text = render_tutorial_csv(plan)
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert len(rows) == len(plan["segments"])
    assert rows[0]["gb_callout"] == plan["segments"][0]["move_name"]
    assert rows[0]["camera_primary"] == "rear_wide"

    payload = json.loads(render_tutorial_json(plan))
    assert payload["provenance_hash"] == plan["provenance_hash"]
    assert payload["validation"]["status"] == "REVIEW"


def test_renderers_refuse_a_forged_cached_ready_status():
    plan = _plan()
    plan["status"] = "READY"
    plan["validation"] = {
        "status": "READY", "ready": True, "errors": [], "warnings": [],
        "confirmation_pending": 0,
    }
    assert "STATUS: REVIEW" in render_tutorial_txt(plan)
    rows = list(csv.DictReader(io.StringIO(render_tutorial_csv(plan))))
    assert rows[0]["plan_status"] == "REVIEW"
    payload = json.loads(render_tutorial_json(plan))
    assert payload["status"] == "REVIEW"
    assert payload["validation"]["ready"] is False
