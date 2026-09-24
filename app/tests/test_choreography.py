"""Independent golden expectations for the S03 pure choreography compiler."""
from copy import deepcopy
from fractions import Fraction
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from engine.choreography import compile_choreography, exact_count, format_count
from engine.steps import MOVES, MOVE_BY_ID


def event(identifier, duration="1", before="L", after="L", turn="0", **extra):
    return {"id": identifier, "duration_counts": duration, "text": identifier,
            "support_before": before, "support_after": after, "rotation_deg": turn, **extra}


def move(identifier, duration="1", before="L", after="L", turn="0", **extra):
    return {"id": identifier, "name": identifier, "duration_counts": duration,
            "events": [event("action", duration, before, after, turn)], **extra}


def document(moves, **extra):
    return {"schema_version": 1, "parts": [{"id": "A", "moves": moves}],
            "routine": [{"id": "main", "part_id": "A"}], **extra}


def codes(result):
    return {issue["code"] for issue in result["issues"]}


def test_triplets_and_sixteenths_are_exact_without_accumulated_float_error():
    events = [event(f"third-{i}", "1/3") for i in range(3)]
    events += [event(f"sixteenth-{i}", "1/4") for i in range(4)]
    result = compile_choreography(document([{"id": "mixed", "events": events}]))
    assert result["status"] == "VALID"
    assert result["total_counts"] == "2"
    assert [row["start_count"] for row in result["events"]] == ["0", "1/3", "2/3", "1", "5/4", "3/2", "7/4"]
    assert [row["end_count"] for row in result["events"]] == ["1/3", "2/3", "1", "5/4", "3/2", "7/4", "2"]


def test_decimal_input_is_converted_once_and_added_rationally():
    result = compile_choreography(document([move(f"m{i}", 0.1) for i in range(100)]))
    assert result["total_counts"] == "10"
    assert result["events"][-1]["start_count"] == "99/10"


def test_six_count_grouping_does_not_restrict_move_boundaries_or_total():
    result = compile_choreography(document([move("long", "11"), move("short", "2")],
                                          meter={"beats": 3, "unit": 4, "group_counts": 6}))
    assert result["verified"] is True
    assert result["total_counts"] == "13"
    assert result["events"][1]["count_label"] == "6"
    assert result["meter"] == {"beats": "3", "unit": "4", "group_counts": "6"}
    assert not any("BLOCK" in code or "STRADDLE" in code for code in codes(result))


def test_left_start_diagonal_turn_and_known_weight_transfer():
    result = compile_choreography(document([move("step", "1", "R", "L", "45")],
                                          start={"free_foot": "L", "facing_deg": "45"}))
    assert result["verified"]
    assert result["start_state"] == {"support": "R", "free_foot": "L", "facing_deg": "45"}
    assert result["end_state"] == {"support": "L", "free_foot": "R", "facing_deg": "90"}
    assert result["net_rotation_deg"] == "45"
    assert result["facing_cycle"] == 8


def test_nonrepeating_part_tag_and_ending_need_not_individually_close():
    doc = {"parts": [
        {"id": "A", "moves": [move("step-right", before="L", after="R")]},
        {"id": "T", "kind": "tag", "moves": [move("step-left", before="R", after="L")]},
        {"id": "E", "kind": "ending", "moves": [move("finish-right", before="L", after="R")]},
    ], "routine": [{"id": "a", "part_id": "A"}, {"id": "tag", "part_id": "T"}, {"id": "end", "part_id": "E"}]}
    result = compile_choreography(doc)
    assert result["verified"]
    assert result["total_counts"] == "3"
    assert result["end_state"]["support"] == "R"
    assert [row["kind"] for row in result["occurrences"]] == ["part", "tag", "ending"]


def test_restart_is_counted_part_occurrence_three_even_on_identical_wall():
    doc = {"parts": [{"id": "A", "moves": [move("first"), move("second")]}],
           "routine": [{"id": "first-two", "part_id": "A", "repeat": 2},
                       {"id": "third-restart", "part_id": "A", "end_after_counts": "1", "reason": "restart"},
                       {"id": "fourth", "part_id": "A"}]}
    result = compile_choreography(doc)
    assert result["verified"]
    assert result["total_counts"] == "7"
    assert [row["part_occurrence_number"] for row in result["occurrences"]] == [1, 2, 3, 4]
    assert [row["state_before"]["facing_deg"] for row in result["occurrences"]] == ["0"] * 4
    third = result["occurrences"][2]
    assert third["id"] == "third-restart#1"
    assert third["start_count"] == "4" and third["end_count"] == "5"
    assert third["reason"] == "restart"
    assert third["event_ids"] == ["third-restart#1/first/action"]


def test_specific_occurrence_override_changes_only_that_occurrence():
    doc = document([move("motif", "2")])
    doc["routine"] = [{"id": "usual", "part_id": "A", "repeat": 2},
                      {"id": "variation", "part_id": "A", "overrides": {"motif": move("ignored", "1", turn="45")}},
                      {"id": "usual-again", "part_id": "A"}]
    original = deepcopy(doc)
    result = compile_choreography(doc)
    assert result["verified"]
    assert [row["duration_counts"] for row in result["occurrences"]] == ["2", "2", "1", "2"]
    assert [row["rotation_deg"] for row in result["events"]] == ["0", "0", "45", "0"]
    assert result["events"][2]["id"] == "variation#1/motif/action"
    assert doc == original


def test_restart_partial_weight_transfer_is_checked_against_next_occurrence():
    doc = document([move("step-right", before="L", after="R"), move("step-left", before="R", after="L")])
    doc["routine"] = [{"id": "restart", "part_id": "A", "end_after_counts": "1", "reason": "restart"},
                      {"id": "resume", "part_id": "A"}]
    result = compile_choreography(doc)
    assert result["status"] == "INVALID"
    mismatch = next(issue for issue in result["issues"] if issue["code"] == "SUPPORT_MISMATCH")
    assert mismatch["event_id"] == "resume#1/step-right/action"
    assert mismatch["start_count"] == "1"
    assert mismatch["expected"] == "L" and mismatch["actual"] == "R"
    assert mismatch["action"]


def test_restart_boundary_cannot_invent_state_inside_an_aggregate_move():
    doc = document([move("four-count-aggregate", "4")])
    doc["routine"][0].update(end_after_counts="2", reason="restart")
    result = compile_choreography(doc)
    assert "BOUNDARY_SPLITS_EVENT" in codes(result)
    assert "OCCURRENCE_COVERAGE" in codes(result)
    assert result["events"] == []
    assert result["end_state"]["support"] == "unknown"
    assert not result["valid"]


def test_explicit_subdivision_allows_restart_at_a_fractional_boundary():
    doc = document([{"id": "three-actions", "events": [event("a", "1/3"), event("b", "1/3"), event("c", "1/3")]}])
    doc["routine"][0].update(end_after_counts="2/3", reason="restart")
    result = compile_choreography(doc)
    assert result["verified"]
    assert result["total_counts"] == "2/3"
    assert len(result["events"]) == 2


def test_unknown_mechanics_propagate_until_explicitly_resolved():
    result = compile_choreography(document([{"id": "description", "duration_counts": "2", "text": "Personal styling"},
                                           move("known", before="L", after="R", turn="0")]))
    assert result["valid"] is True and result["verified"] is False
    assert result["status"] == "UNVERIFIED"
    assert result["events"][0]["state_after"] == {"support": "unknown", "free_foot": "unknown", "facing_deg": None}
    assert result["events"][1]["state_before"]["support"] == "unknown"
    assert result["end_state"]["support"] == "R"
    assert result["end_state"]["facing_deg"] is None
    assert "ENTRY_UNVERIFIED" in codes(result)


def test_absolute_facing_resolves_unknown_facing_without_retroactive_verification():
    result = compile_choreography(document([{"id": "unknown", "duration_counts": "1", "text": "Unreviewed"},
        {"id": "resolve", "events": [event("finish", before="any", after="both", turn=None, facing_after_deg="90")]}]))
    assert result["status"] == "UNVERIFIED"
    assert result["end_state"] == {"support": "both", "free_foot": "unknown", "facing_deg": "90"}


def test_repeating_whole_routine_checks_actual_next_pass_entry():
    doc = document([move("weighted-step", before="L", after="R")], repeat=True)
    result = compile_choreography(doc)
    assert "REPEAT_SUPPORT_MISMATCH" in codes(result)
    assert result["end_state"]["support"] == "R"
    assert result["total_counts"] == "1" and len(result["events"]) == 1


def test_repeat_can_rotate_and_need_not_return_to_original_facing():
    result = compile_choreography(document([move("turn", "2", turn="90")], repeat=True))
    assert result["verified"]
    assert result["end_state"]["facing_deg"] == "90"
    assert result["facing_cycle"] == 4


def test_repeat_replay_catches_constraint_after_neutral_first_event():
    doc = document([move("neutral", before="any", after="same"), move("weighted", before="L", after="R")], repeat=True)
    result = compile_choreography(doc)
    mismatch = next(issue for issue in result["issues"] if issue["code"] == "REPEAT_SUPPORT_MISMATCH")
    assert mismatch["event_id"] == "main#1/weighted/action"


def test_legacy_concrete_moves_bridge_preserves_known_mechanics_and_instructions():
    legacy = [MOVE_BY_ID["vine_touch"].variant("R"), MOVE_BY_ID["vine_touch"].variant("L")]
    original = deepcopy(legacy)
    result = compile_choreography(legacy)
    assert result["verified"]
    assert result["total_counts"] == "8"
    assert result["events"][0]["definition_id"] == "vine_touch"
    assert result["events"][0]["lines"] == original[0]["lines"]
    assert result["events"][0]["state_after"]["free_foot"] == "L"
    assert result["events"][1]["state_after"]["free_foot"] == "R"
    assert legacy == original
    assert len(MOVES) == 39
    assert len([m.variant(lead) for m in MOVES for lead in ("R", "L")]) == 78


def test_legacy_neutral_move_keeps_current_support_instead_of_inventing_weight():
    result = compile_choreography([MOVE_BY_ID["vine_touch"].variant("R"), MOVE_BY_ID["scuff"].variant("L")])
    assert result["verified"]
    assert result["end_state"]["support"] == "R"


def test_snapshot_resolution_is_pure_and_no_live_catalog_fallback_exists():
    snapshots = {"frozen-v1": move("original", "3", turn="45")}
    original = deepcopy(snapshots)
    result = compile_choreography(document([{"id": "instance", "snapshot_id": "frozen-v1"}]), snapshots)
    assert result["verified"]
    assert result["total_counts"] == "3"
    assert snapshots == original
    missing = compile_choreography(document([{"id": "instance", "snapshot_id": "missing"}]))
    assert "SNAPSHOT_MISSING" in codes(missing)
    assert not missing["valid"]


def test_normalized_document_compiles_identically_and_is_json_serializable():
    doc = document([{"id": "fractions", "events": [event("one", {"numerator": 1, "denominator": 3}), event("two", "2/3")]}])
    first = compile_choreography(doc)
    second = compile_choreography(json.loads(json.dumps(first["normalized_document"])))
    assert second["verified"]
    assert first["source_hash"] == second["source_hash"]
    assert first["events"] == second["events"]


def test_normalized_snapshot_document_is_self_contained_without_live_snapshot_lookup():
    original = compile_choreography(document([{"id": "instance", "snapshot_id": "s1"}]),
                                    {"s1": move("frozen", "2", turn="45")})
    restored = compile_choreography(original["normalized_document"])
    assert restored["verified"]
    assert restored["events"] == original["events"]
    assert restored["source_hash"] == original["source_hash"]


def test_overridden_snapshot_content_is_in_source_hash_and_portable_normalization():
    doc = document([move("base")])
    doc["routine"][0]["overrides"] = {"base": {"snapshot_id": "variation"}}
    first = compile_choreography(doc, {"variation": move("variant", "2")})
    changed = compile_choreography(doc, {"variation": move("variant", "3")})
    restored = compile_choreography(first["normalized_document"])
    assert first["verified"] and changed["verified"] and restored["verified"]
    assert first["source_hash"] != changed["source_hash"]
    assert first["events"] == restored["events"]
    assert first["source_hash"] == restored["source_hash"]


def test_authored_event_ids_stay_stable_when_earlier_duration_changes():
    first_doc = document([move("first"), move("second")])
    second_doc = document([move("first", "2"), move("second")])
    first, second = compile_choreography(first_doc), compile_choreography(second_doc)
    assert first["events"][1]["id"] == second["events"][1]["id"] == "main#1/second/action"
    assert first["events"][1]["start_count"] == "1" and second["events"][1]["start_count"] == "2"
    assert first["source_hash"] != second["source_hash"]


def test_issue_identity_does_not_shift_when_an_unrelated_earlier_issue_is_added():
    doc = document([move("first", after="R"), move("second", before="L")])
    first = compile_choreography(doc)
    doc["meter"] = {"beats": 0}
    second = compile_choreography(doc)
    first_issue = next(issue for issue in first["issues"] if issue["code"] == "SUPPORT_MISMATCH")
    second_issue = next(issue for issue in second["issues"] if issue["code"] == "SUPPORT_MISMATCH")
    assert first_issue["id"] == second_issue["id"]


def test_pickup_origin_and_instant_marker_are_explicit():
    doc = document([move("pickup", "1/2"), {"id": "marker", "events": [event("count-one", "0")]}, move("first-count")], pickup_counts="1/2")
    result = compile_choreography(doc)
    assert result["verified"]
    assert result["start_count"] == "-1/2" and result["end_count"] == "1"
    assert result["total_counts"] == "3/2"
    assert result["events"][0]["count_label"] == "pickup 1/2"
    assert result["events"][1]["start_count"] == result["events"][1]["end_count"] == "0"


@pytest.mark.parametrize("value", [True, None, "1/0", float("nan"), float("inf"), {"numerator": 1, "denominator": False}])
def test_invalid_rationals_fail_explicitly(value):
    with pytest.raises((ValueError, ZeroDivisionError)):
        exact_count(value)


def test_display_labels_keep_triplets_distinct_from_ampersands():
    assert [format_count(x) for x in ("0", "1/4", "1/2", "3/4", "1/3", "2/3")] == ["1", "1e", "1&", "1a", "1+1/3", "1+2/3"]
    assert format_count("6", 6) == "1"
    assert exact_count("0.125") == Fraction(1, 8)


def test_count_targets_and_facing_contradictions_are_actionable():
    doc = document([{"id": "contradiction", "duration_counts": "2", "events": [event("wrong-facing", turn="45", facing_after_deg="90")]}], target_counts="4")
    doc["parts"][0]["target_counts"] = "3"
    result = compile_choreography(doc)
    assert {"MOVE_COUNT_MISMATCH", "PART_COUNT_MISMATCH", "ROUTINE_COUNT_MISMATCH", "TURN_CONTRADICTION"} <= codes(result)
    assert all(issue["id"] and issue["action"] for issue in result["issues"])


def test_overlapping_or_uncovered_events_do_not_claim_validity():
    doc = document([{"id": "bad", "events": [event("a", "2"), event("b", "1", offset_counts="1"), event("c", "1", offset_counts="4")]}])
    result = compile_choreography(doc)
    assert {"EVENT_OVERLAP", "EVENT_GAP"} <= codes(result)
    assert not result["valid"]


def test_duplicate_ids_and_missing_parts_are_reported_without_mutating_input():
    doc = document([move("same"), move("same")])
    doc["routine"].append({"id": "missing", "part_id": "not-there"})
    original = deepcopy(doc)
    result = compile_choreography(doc)
    assert {"DUPLICATE_ID", "PART_MISSING"} <= codes(result)
    assert len({row["id"] for row in result["events"]}) == len(result["events"])
    assert doc == original


def test_duplicate_id_recovery_cannot_collide_with_authored_suffix():
    result = compile_choreography(document([move("x"), move("x~3"), move("x")]))
    assert "DUPLICATE_ID" in codes(result)
    assert len({row["id"] for row in result["events"]}) == 3


def test_missing_duration_is_not_silently_assumed_to_be_instantaneous():
    result = compile_choreography(document([{"id": "blank"}, {"id": "partial", "events": [{"id": "undated", "text": "Step"}]}]))
    assert "DURATION_MISSING" in codes(result)
    assert not result["valid"]


def test_unsupported_schema_start_conflict_and_excessive_repeats_are_errors():
    doc = document([move("known")], schema_version=2, start={"support": "L", "free_foot": "L"})
    doc["routine"][0]["repeat"] = 100000000
    result = compile_choreography(doc)
    assert {"UNSUPPORTED_SCHEMA", "START_STATE_CONTRADICTION", "INVALID_REPEAT"} <= codes(result)
    assert len(result["events"]) == 1
