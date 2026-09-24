"""Regression tests for the real lyric-anchored dance solver."""
import os
import sys

import pytest


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.assembler import AssemblyError, assemble_anchored, validate_sequence


VINE_ANCHORS = [
    {
        "start_count": 1,
        "move_id": "vine_touch",
        "lead": "R",
        "detection_id": "slide-right-counted",
        "source_text": "Slide right / Two, three, touch",
        "confidence": 0.97,
    },
    {
        "start_count": 5,
        "move_id": "vine_touch",
        "lead": "L",
        "detection_id": "slide-left-counted",
        "source_text": "Slide left / Two, three, touch",
        "confidence": 0.97,
    },
]


def _solve(seed=17):
    return assemble_anchored(
        VINE_ANCHORS,
        total_counts=32,
        wall="2",
        turn_dir="L",
        level="AB",
        seed=seed,
        k=3,
        bpm=108,
    )


def _moves_at_counts(candidate):
    """Index generated move variants by their one-based starting count."""
    position = 1
    indexed = {}
    for move in candidate["moves"]:
        indexed[position] = move
        position += move["counts"]
    return indexed


def _candidate_signature(result):
    """Compare only stable, user-relevant solver output."""
    return [
        {
            "moves": [
                (move["move_id"], move["lead"], move["counts"], move["rot"])
                for move in candidate["moves"]
            ],
            "provenance": candidate["provenance"],
            "net_rot": candidate["net_rot"],
            "walls": candidate["walls"],
            "quality": candidate["quality"],
        }
        for candidate in result["candidates"]
    ]


def test_exact_mirrored_vine_anchors_are_preserved_in_valid_candidates():
    result = _solve()

    assert result["candidates"]
    assert result["anchors"] == VINE_ANCHORS
    assert result["gaps"] == [
        {"start_count": 9, "end_count": 32, "counts": 24},
    ]

    for candidate in result["candidates"]:
        report = validate_sequence(
            candidate["moves"], 32, "2", turn_dir="L", bpm=108,
        )
        assert report["valid"], report
        assert report["counts"] == 32
        assert candidate["net_rot"] == 180
        assert candidate["walls"] == 2

        by_count = _moves_at_counts(candidate)
        assert (by_count[1]["move_id"], by_count[1]["lead"]) == (
            "vine_touch", "R",
        )
        assert (by_count[5]["move_id"], by_count[5]["lead"]) == (
            "vine_touch", "L",
        )

        assert len(candidate["provenance"]) == len(candidate["moves"])
        expected_starts = []
        position = 1
        for move in candidate["moves"]:
            expected_starts.append(position)
            position += move["counts"]
        assert [row["start_count"] for row in candidate["provenance"]] == expected_starts
        assert candidate["provenance"][0] == {
            "kind": "lyric",
            "start_count": 1,
            "detection_id": "slide-right-counted",
            "source_text": "Slide right / Two, three, touch",
            "confidence": 0.97,
        }
        assert candidate["provenance"][1] == {
            "kind": "lyric",
            "start_count": 5,
            "detection_id": "slide-left-counted",
            "source_text": "Slide left / Two, three, touch",
            "confidence": 0.97,
        }
        assert all(
            row["kind"] == "gap_fill"
            for row in candidate["provenance"][2:]
        )


def test_anchor_that_straddles_an_eight_count_boundary_is_rejected():
    with pytest.raises(AssemblyError) as caught:
        assemble_anchored(
            [{
                "start_count": 7,
                "move_id": "vine_touch",
                "lead": "R",
                "source_text": "Slide right / Two, three, touch",
            }],
            total_counts=32,
            wall="2",
            turn_dir="L",
            level="AB",
            seed=17,
        )

    assert caught.value.code == "LYRIC_CUE_INFEASIBLE"
    assert "straddle" in caught.value.message.lower()
    assert caught.value.details == {"start_count": 7, "counts": 4}


def test_same_seed_produces_the_same_candidates_and_provenance():
    first = _solve(seed=29)
    second = _solve(seed=29)

    assert _candidate_signature(first) == _candidate_signature(second)

