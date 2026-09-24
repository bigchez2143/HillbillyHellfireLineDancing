"""Engine unit tests: wall math, foot parity, assembler, phrasing, emitter."""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from engine.steps import MOVES, MOVE_BY_ID, generator_moves
from engine.assembler import (assemble, validate_sequence, wall_count,
                              AssemblyError, VALIDATED_MAX_BPM)
from engine.database import initialize_database
from engine.alignment import build_alignment
from engine.phrasing import parse_tagged_lyrics, phrase_check
from engine.emitter import (build_sheet, render_txt, build_challenge_kit,
                            build_publish_kit)
from engine import settings as app_settings
from engine import ai_assistant
from engine import move_import


# ---------------------------------------------------------------- wall math
def test_wall_count():
    assert wall_count(0) == 1
    assert wall_count(180) == 2
    assert wall_count(90) == 4
    assert wall_count(270) == 4


# ---------------------------------------------------------------- mirroring
def test_mirror_flips_feet_and_rotation():
    m = MOVE_BY_ID["vine_quarter"]
    r = m.variant("R")
    l = m.variant("L")
    assert r["rot"] == 90 and l["rot"] == -90
    assert r["start"] == "R" and l["start"] == "L"
    assert r["end"] == "L" and l["end"] == "R"
    assert "right" in r["name"].lower() and "left" in l["name"].lower()


def test_mirror_direction_words_swap():
    m = MOVE_BY_ID["vine_touch"]
    r = m.variant("R")["lines"][0]["text"]
    l = m.variant("L")["lines"][0]["text"]
    assert "right side" in r and "cross L behind R" in r
    assert "left side" in l and "cross R behind L" in l


# ------------------------------------------------------------ foot parity
def test_seed_parity_encodings():
    """Spot-check the odd/even weight-change crux against the seed DB."""
    # even weight changes -> free foot unchanged
    for mid in ("jazz_box", "rocking_chair", "rock_fwd", "charleston",
                "side_together", "walk_fwd", "pivot_quarter", "pivot_half",
                "kick_ball_change", "weave", "monterey_half", "cross_rock"):
        m = MOVE_BY_ID[mid].variant("R")
        assert m["start"] == "R" and m["end"] == "R", mid
    # odd weight changes -> free foot switches
    for mid in ("vine_touch", "vine_quarter", "step_touch", "heel_strut",
                "toe_strut", "shuffle_fwd", "chasse_side", "coaster",
                "sailor", "scissor"):
        m = MOVE_BY_ID[mid].variant("R")
        assert m["start"] == "R" and m["end"] == "L", mid


# ------------------------------------------------------------- assembler
def _check_solution(cand, total, target_rot, start_foot="R"):
    moves = cand["moves"]
    assert sum(m["counts"] for m in moves) == total
    # foot continuity
    foot = start_foot
    pos = 0
    for m in moves:
        assert m["start"] in (foot, "F"), f"foot break at count {pos}"
        # no straddling 8-count blocks
        block_end = ((pos // 8) + 1) * 8
        assert pos + m["counts"] <= min(block_end, total)
        foot = foot if m["end"] == "SAME" else m["end"]
        pos += m["counts"]
    assert foot == start_foot
    assert sum(m["rot"] for m in moves) % 360 == target_rot


def test_assemble_ab_2wall():
    r = assemble(total_counts=32, wall="2", level="AB", seed=1, k=3)
    assert r["candidates"]
    for c in r["candidates"]:
        _check_solution(c, 32, 180)
        assert c["walls"] == 2


def test_assemble_ab_4wall_both_directions():
    for td, target in (("L", 270), ("R", 90)):
        r = assemble(total_counts=32, wall="4", turn_dir=td, level="AB", seed=2)
        for c in r["candidates"]:
            _check_solution(c, 32, target)
            assert c["walls"] == 4


def test_assemble_1wall_and_beginner_sync():
    r = assemble(total_counts=32, wall="1", level="B", allow_sync=True, seed=3)
    for c in r["candidates"]:
        _check_solution(c, 32, 0)
        assert c["walls"] == 1


def test_assemble_deterministic():
    a = assemble(total_counts=32, wall="2", level="AB", seed=42, k=2)
    b = assemble(total_counts=32, wall="2", level="AB", seed=42, k=2)
    ids_a = [[m["move_id"] for m in c["moves"]] for c in a["candidates"]]
    ids_b = [[m["move_id"] for m in c["moves"]] for c in b["candidates"]]
    assert ids_a == ids_b


def test_generated_candidates_include_publication_quality_guidance():
    result = assemble(total_counts=32, wall="2", level="AB", seed=7, k=2)
    for candidate in result["candidates"]:
        quality = candidate["quality"]
        assert 0 <= quality["score"] <= 100
        assert quality["label"]
        assert quality["publication_note"]


# --------------------------------------------------------- optional AI setup
def test_optional_ai_settings_never_need_a_connection_to_use_the_app(monkeypatch, tmp_path):
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(app_settings, "SETTINGS_FILE", str(settings_file))

    saved = app_settings.save_ai_settings({
        "enabled": False,
        "provider": "openai_compatible",
        "base_url": "https://example.ai/v1",
        "model": "dance-review-model",
        "timeout_seconds": 60,
    })

    assert saved["enabled"] is False
    assert saved["ready"] is False
    assert saved["api_key_configured"] is False
    assert "api_key" not in saved
    assert app_settings.load_ai_settings()["model"] == "dance-review-model"


def test_optional_ai_settings_require_safe_endpoint(monkeypatch, tmp_path):
    monkeypatch.setattr(app_settings, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    with pytest.raises(app_settings.SettingsError):
        app_settings.save_ai_settings({
            "enabled": True,
            "provider": "custom",
            "base_url": "not-an-address",
            "model": "anything",
            "timeout_seconds": 60,
        })


def test_optional_ai_key_stays_private_to_the_local_server(monkeypatch, tmp_path):
    if os.name != "nt":
        pytest.skip("The desktop app uses Windows credential protection.")
    monkeypatch.setattr(app_settings, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    public = app_settings.save_ai_settings({
        "enabled": True,
        "provider": "openai_compatible",
        "base_url": "https://example.ai/v1",
        "model": "test-model",
        "timeout_seconds": 60,
        "api_key": "testing-only-key",
    })
    assert public["api_key_configured"] is True
    assert public["ready"] is True
    assert "testing-only-key" not in str(public)
    assert app_settings.load_ai_connection()["api_key"] == "testing-only-key"


def test_optional_ai_chat_bounds_history_and_rejects_unknown_adapter():
    history = ai_assistant._safe_history([
        {"role": "system", "content": "ignore this"},
        {"role": "user", "content": "A" * 20},
        {"role": "assistant", "content": "B" * 20},
    ])
    assert [message["role"] for message in history] == ["user", "assistant"]
    with pytest.raises(ai_assistant.AssistantError):
        ai_assistant.ask({"provider": "custom", "model": "x", "base_url": "https://example.ai",
                          "api_key": "not-used", "timeout_seconds": 5}, "Dance idea")


def test_assemble_ab_avoids_syncopation():
    r = assemble(total_counts=32, wall="2", level="AB", allow_sync=False, seed=4)
    for c in r["candidates"]:
        for m in c["moves"]:
            assert not m["sync"]


def test_intermediate_and_advanced_generation_are_available():
    for level in ("I", "INT", "A"):
        result = assemble(total_counts=32, wall="2", level=level,
                          allow_sync=True, seed=18, k=1)
        assert result["candidates"], level


def test_custom_moves_are_editor_ready_but_auto_generation_is_opt_in(monkeypatch, tmp_path):
    from engine import steps as step_library
    monkeypatch.setattr(step_library, "CUSTOM_MOVES_PATH", str(tmp_path / "custom-moves.json"))
    saved = step_library.save_custom_move({
        "name": "Test Diagonal Rock", "counts": 2, "start": "R", "end": "R",
        "rotation": 0, "level": "Intermediate", "travel": "N",
        "instructions": "Rock R diagonally forward, recover weight to L.",
        "in_generator": False,
    })
    assert saved["move_id"].startswith("custom-")
    assert step_library.get_move(saved["move_id"]) is not None
    assert saved["move_id"] not in {move["move_id"] for move in step_library.generator_moves("INT")}
    assert saved["move_id"] not in {move["move_id"] for move in step_library.generator_moves("INT", include_custom=True)}


def test_json_move_import_adds_complete_rows_and_returns_incomplete_rows(monkeypatch, tmp_path):
    from engine import steps as step_library
    monkeypatch.setattr(step_library, "CUSTOM_MOVES_PATH", str(tmp_path / "custom-moves.json"))
    payload = json.dumps({"moves": [
        {"name": "Imported Side Rock", "counts": 2, "start": "R", "end": "R",
         "rotation": 0, "level": "Beginner", "instructions": "Rock R to side, recover to L.",
         "in_generator": "false"},
        {"name": "Missing mechanics"},
    ]}).encode("utf-8")
    result = move_import.import_moves("moves.json", payload)
    assert result["found"] == 2
    assert [row["name"] for row in result["accepted"]] == ["Imported Side Rock"]
    assert result["needs_review"] and result["needs_review"][0]["name"] == "Missing mechanics"
    imported = step_library.get_move(result["accepted"][0]["id"])
    assert imported.in_generator is False


def test_assemble_bad_counts():
    with pytest.raises(AssemblyError) as e:
        assemble(total_counts=30, wall="2")
    assert e.value.code == "CONTRADICTORY_INPUT"


def test_tempo_boundary_requires_explicit_override():
    with pytest.raises(AssemblyError) as e:
        assemble(total_counts=32, wall="2", level="AB", seed=1,
                 bpm=VALIDATED_MAX_BPM + 1)
    assert e.value.code == "EXPERIMENTAL_MODE_REQUIRED"

    r = assemble(total_counts=32, wall="2", level="AB", seed=1, k=1,
                 bpm=VALIDATED_MAX_BPM + 4, experimental_mode=True)
    assert r["tempo"]["mode"] == "experimental"
    assert r["tempo"]["manual_review_required"]


def test_high_tempo_validation_names_manual_review():
    r = assemble(total_counts=16, wall="1", level="AB", seed=11, k=1)
    report = validate_sequence(r["candidates"][0]["moves"], 16, "1", bpm=136)
    assert report["valid"]
    assert report["tempo"]["mode"] == "experimental"
    assert any("manual review" in note.lower() for note in report["notes"])


def test_step_catalog_database_builds(tmp_path):
    summary = initialize_database(str(tmp_path / "line-dance.db"))
    assert summary["schema_version"] == "1"
    assert summary["steps"] == 216
    # Transition rows stay empty until a curator reviews real pairings; the
    # app must never manufacture a confident transition graph from prose.
    assert summary["transitions"] == 0


def test_assemble_infeasible_wall(monkeypatch):
    # With every turning move removed, a 2-wall target is provably
    # unreachable and must fail loudly with the structured code — never a
    # silently wrong sheet.  (The full AB library is deliberately rich enough
    # that real infeasibility is rare: even 4 counts reaches 180 via two
    # quarter pivots.)
    from engine import assembler as asm
    no_turns = [m for m in generator_moves("AB", False) if m["rot"] == 0]
    monkeypatch.setattr(asm, "generator_moves", lambda **kw: no_turns)
    with pytest.raises(AssemblyError) as e:
        asm.assemble(total_counts=32, wall="2", level="AB")
    assert e.value.code == "INFEASIBLE_WALL"


def test_assemble_4count_2wall_is_actually_feasible():
    # Regression of a wrong assumption: two 1/4 pivots = 180 in 4 counts.
    r = assemble(total_counts=4, wall="2", level="AB", seed=0, k=1)
    _check_solution(r["candidates"][0], 4, 180)


# ------------------------------------------------------------- validator
def test_validate_good_sequence():
    r = assemble(total_counts=16, wall="1", level="AB", seed=5, k=1)
    moves = r["candidates"][0]["moves"]
    rep = validate_sequence(moves, 16, "1")
    assert rep["valid"]


def test_validate_catches_foot_break():
    # two R-lead vines in a row: first ends L free, second needs R free
    v = MOVE_BY_ID["vine_touch"]
    moves = [v.variant("R"), v.variant("R")]
    rep = validate_sequence(moves, 8, "1")
    assert any(p["code"] == "FOOT_BREAK" for p in rep["problems"])


def test_validate_catches_count_and_wall():
    v = MOVE_BY_ID["vine_touch"]
    moves = [v.variant("R"), v.variant("L")]  # 8 counts, rot 0
    rep = validate_sequence(moves, 16, "2")
    codes = {p["code"] for p in rep["problems"]}
    assert "COUNT_MISMATCH" in codes
    rep2 = validate_sequence(moves, 8, "2")
    codes2 = {p["code"] for p in rep2["problems"]}
    assert "WALL_MISMATCH" in codes2 and "COUNT_MISMATCH" not in codes2


# ------------------------------------------------------------- phrasing
def _fake_analysis(bpm=120.0, duration=120.0):
    spb = 60.0 / bpm
    beats = [round(i * spb, 4) for i in range(int(duration / spb))]
    return {"bpm": bpm, "duration": duration, "beat_times": beats,
            "downbeat_times": beats[::4], "octave_alternates": [],
            "drift": None, "phase_contrast": 0.5}


def test_parse_tagged_lyrics():
    txt = "[Intro]\n\n[Verse 1]\nline one\nline two\n[Chorus]\nhook here\n"
    secs = parse_tagged_lyrics(txt)
    assert [s["label"] for s in secs] == ["Intro", "Verse 1", "Chorus"]
    assert secs[1]["lyrics"] == "line one\nline two"


def test_lyric_alignment_builds_reviewable_timed_rows_and_sections():
    segments = [{"text": "Yeah hey roll it up", "words": [
        {"word": "Yeah", "start": 1.03, "end": 1.20, "score": .98},
        {"word": "hey", "start": 1.22, "end": 1.42, "score": .97},
        {"word": "Roll", "start": 4.08, "end": 4.26, "score": .95},
        {"word": "it", "start": 4.30, "end": 4.39, "score": .95},
        {"word": "up", "start": 4.42, "end": 4.61, "score": .95},
    ]}]
    lyrics = "[Verse 1]\nYeah hey\n[Chorus]\nRoll it up\n"
    result = build_alignment(segments, lyrics, downbeat_times=[1.0, 4.0, 5.0])
    assert result["summary"] == {
        "lyric_lines": 2, "timed_lines": 2, "matched_words": 5,
        "expected_words": 5, "confidence": 1.0,
    }
    assert result["captions"][0]["start"] == 1.03
    assert result["captions"][1]["end"] == 4.61
    assert [s["label"] for s in result["suggested_sections"]] == ["Verse 1", "Chorus"]
    assert result["suggested_sections"][0]["start"] == 1.0


def test_lyric_alignment_keeps_unmatched_lines_untimed():
    result = build_alignment(
        [{"words": [{"word": "hello", "start": .5, "end": .8}]}],
        "[Verse]\nA lyric that is not sung\n")
    row = result["captions"][0]
    assert row["status"] == "unmatched"
    assert row["start"] is None and row["end"] is None
    assert result["suggested_sections"] == []


def test_lyric_alignment_does_not_merge_repeated_choruses():
    segments = [{"words": [
        {"word": "first", "start": 1.0, "end": 1.2},
        {"word": "verse", "start": 1.2, "end": 1.5},
        {"word": "hook", "start": 3.0, "end": 3.3},
        {"word": "again", "start": 5.0, "end": 5.3},
    ]}]
    lyrics = "[Verse]\nfirst verse\n[Chorus]\nhook\n[Verse]\nagain\n"
    result = build_alignment(segments, lyrics)
    assert [s["label"] for s in result["suggested_sections"]] == ["Verse", "Chorus", "Verse"]


def test_phrase_check_clean():
    a = _fake_analysis()
    # 120 BPM -> 0.5s per beat. 32 beats = 16s sections, all clean.
    secs = [{"label": "V1", "start": 8.0, "end": 24.0},
            {"label": "C1", "start": 24.0, "end": 40.0}]
    r = phrase_check(secs, a, pattern_len=32)
    assert r["status"] == "CLEAN"
    assert all(s["classification"] == "clean" for s in r["sections"])
    assert r["intro"]["beats"] == 16
    assert r["tiling"]["clean"]


def test_phrase_check_flags_half_block():
    a = _fake_analysis()
    # A human music section can be 28 counts. That does not force a restart:
    # the continuous dance fit simply carries the pattern through the change.
    secs = [{"label": "V1", "start": 8.0, "end": 24.0},
            {"label": "V2", "start": 24.0, "end": 38.0}]
    r = phrase_check(secs, a, pattern_len=32)
    assert r["status"] == "CLEAN"
    codes = {f["code"] for f in r["flags"]}
    assert "ODD_PHRASE" in codes
    assert "RESTART_NEEDED" not in codes
    assert r["dance_fit"]["mode"] == "continuous"
    assert r["dance_fit"]["tail_counts"] == 28


def test_phrase_check_keeps_song_map_and_tracks_continuous_dance_count():
    a = _fake_analysis()
    secs = [{"label": "Verse", "start": 0.0, "end": 8.0},
            {"label": "Chorus", "start": 8.0, "end": 20.0}]
    r = phrase_check(secs, a, pattern_len=32)
    verse, chorus = r["sections"]
    assert r["music_map"] == {"markers_preserved": True, "source": "manual"}
    assert verse["dance_start_count"] == 1
    assert verse["dance_end_count"] == 16
    assert chorus["dance_start_count"] == 17
    assert chorus["dance_end_count"] == 8
    assert "count 17" in chorus["dance_cue"]


def test_phrase_check_never_forces():
    a = _fake_analysis()
    secs = [{"label": "V1", "start": 8.0, "end": 24.0}]
    a["drift"] = {"first_half_bpm": 118, "second_half_bpm": 122, "drift_pct": 3.3}
    r = phrase_check(secs, a, pattern_len=32)
    assert r["status"] == "UNCERTAIN"  # drift is an error-severity flag


# -------------------------------------------------------------- emitter
def test_emitter_txt_format():
    r = assemble(total_counts=32, wall="2", level="AB", seed=7, k=1)
    cand = r["candidates"][0]
    dance = {"moves": cand["moves"], "total_counts": 32, "wall": "2",
             "walls": cand["walls"], "net_rot": cand["net_rot"]}
    meta = {"title": "Test Song", "artist": "Hillbilly Hellfire",
            "choreographer": "Lee B", "country": "USA",
            "signature_note": "hit it with attitude"}
    analysis = {"bpm": 122.0}
    phrase = {"intro": {"beats": 16, "residual": 0, "suggest": 16},
              "flags": [], "status": "CLEAN"}
    sheet = build_sheet(meta, dance, analysis, phrase)
    txt = render_txt(sheet)
    assert "Count: 32" in txt and "Wall: 2" in txt
    assert "Music: Test Song - Hillbilly Hellfire" in txt
    assert "Section 1" in txt and "Section 4" in txt
    assert "Intro: 16 counts" in txt
    assert "BPM: 122" in txt
    assert "(hit it with attitude)" in txt
    # a 2-wall dance must annotate at least one facing
    assert "facing" in txt
    # block labels restart at 1 in each section
    assert txt.count("Section ") == 4


def test_emitter_count_labels_within_blocks():
    r = assemble(total_counts=16, wall="1", level="AB", seed=9, k=1)
    cand = r["candidates"][0]
    dance = {"moves": cand["moves"], "total_counts": 16, "wall": "1",
             "walls": 1, "net_rot": 0}
    sheet = build_sheet({"title": "X"}, dance)
    for b in sheet["blocks"]:
        # first label of each block starts at count 1
        assert b["lines"][0]["label"].startswith("1")


def test_challenge_kit():
    sheet = {"level": "Absolute Beginner", "count": 32, "wall": 2}
    kit = build_challenge_kit(sheet, {"title": "Firefly Rave",
                                      "artist": "Hillbilly Hellfire"},
                              {"bpm": 122.0})
    assert "Firefly Rave" in kit["youtube_title"]
    assert "32 Count" in kit["youtube_title"]
    assert "Music: Firefly Rave - Hillbilly Hellfire" in kit["description"]
    assert "YOUR name" in kit["description"]


# ----------------------------------------------------- review regressions
def _max_runs(moves):
    """(max consecutive same-direction travel counts, max family run)."""
    from engine.steps import floor_travel
    tdir, trun, worst = "", 0, 0
    famrun, famworst = 1, 1
    rot = 0
    prev_fam = None
    for m in moves:
        f = floor_travel(m.get("travel", ""), rot)
        if f:
            trun = trun + m["counts"] if f == tdir else m["counts"]
            tdir = f
            worst = max(worst, trun)
        else:
            tdir, trun = "", 0
        rot = (rot + m["rot"]) % 360
        famrun = famrun + 1 if m["family"] == prev_fam else 1
        famworst = max(famworst, famrun)
        prev_fam = m["family"]
    return worst, famworst


def test_no_marching_off_the_floor():
    """Review finding: 14 consecutive heel struts = 28 counts of forward
    travel passed every gate.  The travel cap and repetition decay must hold
    across seeds, levels and walls."""
    from engine.assembler import TRAVEL_RUN_CAP
    for level, sync in (("AB", False), ("B", True)):
        for wall in ("1", "2", "4"):
            for seed in range(10):
                r = assemble(32, wall=wall, level=level, allow_sync=sync,
                             seed=seed, k=3)
                for c in r["candidates"]:
                    travel, fam = _max_runs(c["moves"])
                    assert travel <= TRAVEL_RUN_CAP, (level, wall, seed, travel)
                    assert fam <= 3, (level, wall, seed, fam)


def test_parse_ignores_adlibs_and_directives():
    """Review finding: '(hey hey!)' ad-libs and [Big Finish]/[end] directives
    became sections and stole lyric lines."""
    txt = ("[Verse 1]\nline one\n(hey hey!)\nline two\n"
           "[Chorus]\nhook here\n(oh oh oh)\n"
           "[Big Finish]\nbig line\n[end]\n")
    secs = parse_tagged_lyrics(txt)
    assert [s["label"] for s in secs] == ["Verse 1", "Chorus"]
    assert "(hey hey!)" in secs[0]["lyrics"]
    assert "line two" in secs[0]["lyrics"]
    assert "big line" in secs[1]["lyrics"]


def test_intro_measured_never_rounded():
    """Review finding: a measured 12-beat intro printed as 'Intro: 16 counts'
    and a 0-beat intro fabricated 16.  The sheet must print what was
    measured."""
    a = _fake_analysis()
    # 12-beat intro (6s at 120 BPM) -> flagged, printed as 12
    secs = [{"label": "V1", "start": 6.0, "end": 22.0}]
    r = phrase_check(secs, a, pattern_len=32)
    assert any(f["code"] == "ODD_INTRO" for f in r["flags"])
    dance = {"moves": [], "total_counts": 32, "wall": "2", "walls": 2,
             "net_rot": 180}
    txt = render_txt(build_sheet({"title": "X"}, dance, a, r))
    assert "Intro: 12 counts" in txt
    assert "Intro: 16" not in txt
    # 0-beat intro -> start on vocals, not a fabricated 16
    r0 = phrase_check([{"label": "V1", "start": 0.0, "end": 16.0}], a, 32)
    txt0 = render_txt(build_sheet({"title": "X"}, dance, a, r0))
    assert "Start on Vocals" in txt0 or "start on the first beat" in txt0
    # no phrase report at all -> says NOT MEASURED, no invented number
    txtn = render_txt(build_sheet({"title": "X"}, dance, a, None))
    assert "NOT MEASURED" in txtn


def test_draft_banner_on_invalid_dance():
    """Review finding: a foot/wall/count-broken dance exported as a clean
    sheet.  The artifact itself must carry the failure."""
    v = MOVE_BY_ID["vine_touch"]
    moves = [v.variant("R"), v.variant("R")]  # foot break + wrong count
    rep = validate_sequence(moves, 32, "2")
    assert not rep["valid"]
    dance = {"moves": moves, "total_counts": 32, "wall": "2",
             "walls": rep["walls"], "net_rot": rep["net_rot"],
             "validation": rep}
    txt = render_txt(build_sheet({"title": "X"}, dance))
    assert "DRAFT" in txt and "FAILED" in txt
    for p in rep["problems"]:
        assert p["message"] in txt


def test_sheet_carries_phrase_uncertainty():
    """Review finding: UNCERTAIN phrase status never reached the artifact."""
    a = _fake_analysis()
    a["drift"] = {"first_half_bpm": 118, "second_half_bpm": 122,
                  "drift_pct": 3.3}
    r = phrase_check([{"label": "V1", "start": 8.0, "end": 24.0}], a, 32)
    assert r["status"] == "UNCERTAIN"
    dance = {"moves": [], "total_counts": 32, "wall": "2", "walls": 2,
             "net_rot": 180}
    txt = render_txt(build_sheet({"title": "X"}, dance, a, r))
    assert "PHRASING UNCERTAIN" in txt


def test_challenge_kit_never_overclaims():
    """Review finding: kit said 'steady'/'Verified BPM' under drift and
    octave ambiguity."""
    sheet = {"level": "Absolute Beginner", "count": 32, "wall": 2}
    meta = {"title": "T", "artist": "HH"}
    shaky = {"bpm": 160.0, "bpm_confidence": "medium",
             "bpm_confidence_notes": ["octave ambiguity"],
             "tempo_steady": False, "drift": None,
             "octave_alternates": [{"bpm": 80.0, "score": 1.1}]}
    kit = build_challenge_kit(sheet, meta, shaky)
    assert "steady" not in kit["description"].lower()
    assert "Verified BPM" not in kit["description"]
    assert "80" in kit["description"]  # both octaves presented
    solid = {"bpm": 122.0, "bpm_confidence": "high",
             "bpm_confidence_notes": [], "tempo_steady": True,
             "drift": None, "octave_alternates": []}
    kit2 = build_challenge_kit(sheet, meta, solid)
    assert "steady 122 BPM" in kit2["description"]
    assert "Verified BPM: 122" in kit2["description"]


def test_publisher_kit_separates_dance_and_song_titles():
    sheet = {
        "title": "Sweet Tea Stomp", "song_title": "Sweet Tea",
        "artist": "Hillbilly Hellfire", "count": 32, "wall": 2,
        "level": "Beginner",
        "choreographer_line": "Choreographer: Hillbilly Hellfire (USA) - August 2026",
        "intro_line": "Intro: 16 counts",
    }
    kit = build_publish_kit(sheet, {"youtube_url": "https://youtu.be/example"},
                            {"bpm": 124}, {"status": "CLEAN"})
    assert kit["youtube_title"].startswith("Sweet Tea Stomp | 32 Count 2 Wall")
    assert "Music: Sweet Tea - Hillbilly Hellfire" in kit["youtube_add_on"]
    assert "https://youtu.be/example" in kit["copperknob_comments"]
    assert len(kit["copperknob_checklist"]) == 4


def test_infeasible_wall_reports_composite_rotations(monkeypatch):
    """Review finding: achievable_rots only listed single-move rotations, so
    a target reachable only by combining moves was reported unachievable."""
    from engine import assembler as asm
    keep = {"jazz_box_quarter", "side_together"}
    subset = [m for m in generator_moves("B", False)
              if m["move_id"] in keep and m["lead"] == "R"]
    monkeypatch.setattr(asm, "generator_moves", lambda **kw: subset)
    with pytest.raises(AssemblyError) as e:
        asm.assemble(total_counts=8, wall="4", turn_dir="L")
    det = e.value.details
    assert 180 in det["achievable_rots"]  # two jazz-box quarters
    # 0 and 180 are both 90 deg from the 270 target — either is a valid
    # "closest"; the point is the gap is named and composite rots included
    assert det["gap_deg"] == 90 and det["closest_rot"] in (0, 180)


def test_foot_deadend_not_reported_as_count(monkeypatch):
    """Review finding: a mid-path foot dead-end raised INFEASIBLE_COUNT with
    a message claiming the counts can't tile (they can — the feet dead-end)."""
    from engine import assembler as asm
    only_r_vine = [m for m in generator_moves("AB", False)
                   if m["move_id"] == "vine_touch" and m["lead"] == "R"]
    monkeypatch.setattr(asm, "generator_moves", lambda **kw: only_r_vine)
    with pytest.raises(AssemblyError) as e:
        asm.assemble(total_counts=8, wall="1")
    assert e.value.code == "INFEASIBLE_FOOT"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
