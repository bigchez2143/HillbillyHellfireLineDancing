import copy

from engine import lyric_moves
from engine.assembler import AssemblyError
from engine.steps import get_move


def _caption(cid, text, start, end, confidence=0.9):
    return {
        "id": cid, "label": "Lyrics", "section_index": 0,
        "text": text, "start": start, "end": end,
        "confidence": confidence, "status": "matched",
    }


def _project(captions):
    return {
        "song": {"path": "C:/songs/holler-back.mp3", "filename": "holler-back.mp3"},
        "analysis": {
            "bpm": 108.0, "seconds_per_beat": 60.0 / 108.0,
            "beat_times": [round(i * 60.0 / 108.0, 4) for i in range(400)],
            "downbeat_times": [round(i * 4 * 60.0 / 108.0, 4) for i in range(100)],
        },
        "alignment": {
            "mode": "scan", "captions": captions,
            "summary": {"confidence": 0.78},
            "source_file_signature": {"size": 123, "mtime_ns": 456},
            "source_analysis_signature": "analysis-sha",
        },
        "phrase": {
            "status": "REVIEW",
            "dance_fit": {"pattern_len": 32,
                          "anchor": {"section": "Section 1", "time": 2.1}},
        },
    }


def _holler_teaching_project():
    return _project([
        _caption(61, "All right", 131.40, 132.68, 0.77),
        _caption(62, "New folks", 132.68, 133.70, 0.75),
        _caption(63, "Watch my feet", 133.70, 135.18, 0.95),
        _caption(64, "Half speed", 135.18, 136.28, 0.64),
        _caption(65, "Slide right", 136.28, 137.72, 0.12),
        _caption(66, "Two, three, touch", 137.72, 139.38, 0.63),
        _caption(67, "Slide left", 139.38, 140.56, 0.77),
        _caption(68, "Two, three, touch", 140.56, 142.28, 0.97),
        _caption(69, "Heel, heel, stomp", 142.28, 143.96, 0.73),
        _caption(70, "Now roll it low", 143.96, 145.32, 0.60),
        _caption(71, "Hit your turn", 145.32, 146.68, 0.59),
        _caption(72, "And what do we do?", 146.68, 148.18, 0.91),
    ])


def test_holler_teaching_passage_maps_both_counted_vines_and_recommends_it():
    draft = lyric_moves.build_draft(
        _holler_teaching_project(), {"counts": 32, "wall": "2"},
        fill_gaps=False,
    )

    assert draft["status"] == "REVIEW"
    selected = next(row for row in draft["passages"]
                    if row["id"] == draft["selected_passage_id"])
    assert selected["recommended"] is True
    assert selected["teaching_context"] is True
    assert selected["mirrored_vine_pair"] is True

    chosen = [row for row in draft["detections"]
              if row["passage_id"] == selected["id"]]
    assert [(row["move_id"], row["lead"], row["confidence"])
            for row in chosen] == [
                ("vine_touch", "R", 0.97),
                ("vine_touch", "L", 0.97),
            ]
    assert [(row["start_count"], row["end_count"]) for row in chosen] == [
        (1, 4), (5, 8),
    ]
    assert [(row["move_id"], row["lead"], row["start_count"])
            for row in draft["anchors"]] == [
                ("vine_touch", "R", 1),
                ("vine_touch", "L", 5),
            ]
    assert draft["gaps"] == [{
        "start_count": 9, "end_count": 32, "counts": 24,
        "status": "unfilled",
    }]


def test_incomplete_heel_roll_and_turn_language_stays_unresolved():
    draft = lyric_moves.build_draft(
        _holler_teaching_project(), {}, fill_gaps=False)

    assert {row["reason_code"] for row in draft["unresolved"]} == {
        "HEEL_STOMP_AMBIGUOUS", "ROLL_AMBIGUOUS", "TURN_AMBIGUOUS",
    }
    assert all(row["requires_review"] for row in draft["unresolved"])
    assert not any(row["move_id"] == "heel_strut" for row in draft["detections"])


def test_figurative_dance_words_do_not_become_moves_or_review_cues():
    project = _project([
        _caption(1, "Kick your shoes off, honey", 1.0, 2.0),
        _caption(2, "Two left boots, sugar", 2.0, 3.0),
        _caption(3, "Wall to wall", 3.0, 4.0),
        _caption(4, "Take it home to your people", 4.0, 5.0),
    ])
    draft = lyric_moves.build_draft(project, {}, fill_gaps=False)

    assert draft["detections"] == []
    assert draft["unresolved"] == []
    assert draft["passages"] == []
    assert draft["selected_passage_id"] is None
    assert any(issue["code"] == "NO_COMMAND_PASSAGES" for issue in draft["issues"])


def test_slide_touch_without_counted_middle_steps_is_not_pinned_by_default():
    project = _project([
        _caption(1, "Slide to the right now", 10.0, 11.5),
        _caption(2, "Touch it on time", 11.5, 12.5),
    ])
    draft = lyric_moves.build_draft(project, {}, fill_gaps=False)

    assert len(draft["detections"]) == 1
    match = draft["detections"][0]
    assert match["move_id"] == "vine_touch"
    assert match["status"] == "needs_review"
    assert match["anchor_eligible"] is False
    assert draft["anchors"] == []


def test_review_can_explicitly_select_a_medium_confidence_detection():
    project = _project([
        _caption(1, "Slide to the right now", 10.0, 11.5),
        _caption(2, "Touch it on time", 11.5, 12.5),
    ])
    first = lyric_moves.build_draft(project, {}, fill_gaps=False)
    detection_id = first["detections"][0]["id"]
    selected = lyric_moves.build_draft(
        project, {"selected_detection_ids": [detection_id]}, fill_gaps=False)

    assert [(row["move_id"], row["lead"], row["start_count"])
            for row in selected["anchors"]] == [("vine_touch", "R", 1)]


def test_gap_filler_receives_only_required_slots_and_returns_valid_candidates(monkeypatch):
    calls = []
    moves = []
    for index in range(8):
        moves.append(get_move("vine_touch").variant("R" if index % 2 == 0 else "L"))

    def fake_solver(required_slots, **kwargs):
        calls.append((required_slots, kwargs))
        return [{
            "moves": moves,
            "net_rot": 0,
            "walls": 1,
            "quality": {"score": 70},
            "provenance": [
                {"kind": "lyric"}, {"kind": "lyric"},
                *({"kind": "filler"} for _ in range(6)),
            ],
        }]

    monkeypatch.setattr(lyric_moves.assembler_engine, "assemble_anchored", fake_solver)
    draft = lyric_moves.build_draft(
        _holler_teaching_project(), {"counts": 32, "wall": "1"},
        fill_gaps=True,
    )

    assert calls[0][0] == [
        {"start_count": 1, "move_id": "vine_touch", "lead": "R"},
        {"start_count": 5, "move_id": "vine_touch", "lead": "L"},
    ]
    assert calls[0][1]["total_counts"] == 32
    assert len(draft["candidates"]) == 1
    assert draft["candidates"][0]["validation"]["valid"] is True
    assert draft["candidates"][0]["provenance"][0]["detection_id"]
    assert draft["summary"]["candidate_count"] == 1
    assert draft["gaps"][0]["status"] == "filled"


def test_unfillable_anchors_return_review_issue_instead_of_partial_candidate(monkeypatch):
    def fail_solver(*args, **kwargs):
        raise AssemblyError("INFEASIBLE_FOOT", "Pinned moves break foot continuity.",
                            {"count": 5})

    monkeypatch.setattr(lyric_moves.assembler_engine, "assemble_anchored", fail_solver)
    draft = lyric_moves.build_draft(
        _holler_teaching_project(), {"counts": 32}, fill_gaps=True)

    assert draft["candidates"] == []
    issue = next(row for row in draft["issues"] if row["code"] == "INFEASIBLE_FOOT")
    assert issue["details"] == {"count": 5}
    assert all(row["status"] == "unfilled" for row in draft["gaps"])


def test_source_fingerprint_changes_with_alignment_or_generation_settings():
    project = _holler_teaching_project()
    original = lyric_moves.build_draft(project, {}, fill_gaps=False)

    changed_project = copy.deepcopy(project)
    changed_project["alignment"]["captions"][4]["text"] = "Slide somewhere"
    changed_lyrics = lyric_moves.build_draft(changed_project, {}, fill_gaps=False)
    changed_settings = lyric_moves.build_draft(
        project, {"wall": "4", "turn_dir": "R"}, fill_gaps=False)

    assert original["source_fingerprint"]["algorithm"] == "lyric-moves-v1"
    assert original["source_fingerprint"]["sha256"] != \
        changed_lyrics["source_fingerprint"]["sha256"]
    assert original["source_fingerprint"]["sha256"] != \
        changed_settings["source_fingerprint"]["sha256"]


def test_explicit_unknown_passage_does_not_silently_choose_another():
    draft = lyric_moves.build_draft(
        _holler_teaching_project(), {}, passage_id="passage-old-scan",
        fill_gaps=True,
    )

    assert draft["selected_passage_id"] is None
    assert draft["anchors"] == []
    assert draft["candidates"] == []
    assert any(issue["code"] == "PASSAGE_NOT_FOUND" for issue in draft["issues"])


def test_malformed_empty_caption_and_phrase_default_do_not_break_passage_indexing():
    project = _holler_teaching_project()
    project["alignment"]["captions"].insert(0, {"id": "empty", "text": ""})
    project["phrase"]["dance_fit"]["pattern_len"] = "not-a-count"

    draft = lyric_moves.build_draft(project, {}, fill_gaps=False)

    assert draft["settings"]["counts"] == 32
    assert [(row["move_id"], row["lead"])
            for row in draft["anchors"]] == [
                ("vine_touch", "R"), ("vine_touch", "L"),
            ]
