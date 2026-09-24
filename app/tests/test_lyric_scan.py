import os
import sys


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.alignment import build_lyric_scan


def _segment(text, start, score=0.94):
    parts = text.split()
    words = []
    cursor = float(start)
    for part in parts:
        words.append({
            "word": part,
            "start": round(cursor, 3),
            "end": round(cursor + 0.22, 3),
            "score": score,
        })
        cursor += 0.28
    return {"text": text, "words": words}


def _analysis(duration=24.0, downbeats=True):
    beats = [round(index * 0.5, 3) for index in range(int(duration / 0.5) + 1)]
    return {
        "duration": duration,
        "bpm": 120.0,
        "seconds_per_beat": 0.5,
        "beat_times": beats,
        "downbeat_times": beats[::4] if downbeats else [],
        "phase_contrast": 0.4,
        "octave_alternates": [],
    }


def test_scan_refuses_to_fabricate_sections_without_timed_vocals():
    result = build_lyric_scan([
        {"text": "words without dependable timestamps", "words": []},
    ], _analysis())

    assert result["mode"] == "auto_scan"
    assert result["status"] == "BLOCKED"
    assert result["suggested_sections"] == []
    assert result["lyrics_text"] == ""
    assert {issue["code"] for issue in result["issues"]} == {
        "NO_DEPENDABLE_VOCALS"
    }


def test_unique_vocal_blocks_get_conservative_section_names():
    transcript = [
        _segment("dust rolls tonight", 2.2),
        _segment("boots find daylight", 7.2),
    ]
    result = build_lyric_scan(transcript, _analysis(downbeats=False))

    sections = result["suggested_sections"]
    assert [section["label"] for section in sections] == ["Section 1", "Section 2"]
    assert all(section["label_source"] == "vocal_block" for section in sections)
    assert all(section["label_confidence"] < 0.75 for section in sections)
    assert all(section["review_required"] for section in sections)
    assert "[Section 1]" in result["lyrics_text"]
    assert "Chorus" not in result["lyrics_text"]


def test_only_evidence_supported_repeated_blocks_become_chorus_occurrences():
    transcript = [
        _segment("dust road carries me home", 2.0),
        _segment("light it up all night", 7.0),
        _segment("river moon pulls me along", 12.0),
        _segment("light it up all night", 17.0),
    ]
    result = build_lyric_scan(transcript, _analysis(duration=24.0,
                                                     downbeats=False))

    sections = result["suggested_sections"]
    assert [section["label"] for section in sections] == [
        "Verse 1", "Chorus 1", "Verse 2", "Chorus 2"
    ]
    choruses = [section for section in sections
                if section["label_source"] == "repeated_lyrics"]
    assert len(choruses) == 2
    assert all(section["label_evidence"]["repeat_similarity"] == 1.0
               for section in choruses)


def test_downbeat_snapping_is_bounded_to_one_beat():
    transcript = [
        _segment("first vocal phrase", 1.2),
        _segment("second vocal phrase", 6.8),
    ]
    result = build_lyric_scan(transcript, _analysis())

    boundaries = result["boundaries"]
    # 1.2 is 0.8 seconds from the nearest 4/4 downbeat (2.0), farther
    # than the 0.5-second beat, so the vocal time must not be pulled over.
    assert boundaries[0]["raw_time"] == 1.2
    assert boundaries[0]["time"] == 1.2
    assert boundaries[0]["snapped"] is False
    # The last vocal word ends at 7.58, within one beat of 8.0.
    assert boundaries[-1]["time"] == 8.0
    assert boundaries[-1]["snapped"] is True
    assert boundaries[-1]["snap_delta"] <= 0.5


def test_suggested_sections_are_positive_ordered_and_exactly_contiguous():
    transcript = [
        _segment("one two three", 2.1),
        _segment("four five six", 7.1),
        _segment("seven eight nine", 12.1),
    ]
    first = build_lyric_scan(transcript, _analysis())
    second = build_lyric_scan(transcript, _analysis())
    assert first == second

    sections = first["suggested_sections"]
    assert sections
    for section in sections:
        assert section["start"] >= 0
        assert section["end"] > section["start"]
        assert "boundary_confidence" in section
        assert "label_confidence" in section
        assert "review_required" in section
    for left, right in zip(sections, sections[1:]):
        assert left["end"] == right["start"]


def test_intro_and_outro_are_metadata_outside_the_vocal_section_draft():
    transcript = [
        _segment("opening sung line", 4.1),
        _segment("closing sung line", 13.1),
    ]
    result = build_lyric_scan(transcript, _analysis(duration=20.0))
    sections = result["suggested_sections"]

    assert result["intro"]["start"] == 0.0
    assert result["intro"]["end"] == sections[0]["start"]
    assert result["intro"]["duration"] > 0
    assert result["outro"]["start"] == sections[-1]["end"]
    assert result["outro"]["end"] == 20.0
    assert result["outro"]["duration"] > 0
    assert all(not section["label"].startswith(("Intro", "Outro"))
               for section in sections)
