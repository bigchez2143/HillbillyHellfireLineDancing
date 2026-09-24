"""Pure regression tests for tempo candidate resolution (no audio files)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.audio import _resolve_tempo_candidates, _tight_tempo_consensus


def _score(score, bpm):
    return (score, bpm, 0.0)


def test_four_method_consensus_beats_near_tied_half_time_grid():
    result = _resolve_tempo_candidates(
        [_score(1.000, 75.0), _score(0.985, 150.0), _score(0.70, 100.0)],
        [149.2, 150.0, 150.6, 149.8],
    )

    assert result["bpm"] == 150.0
    assert result["consensus_preferred"] is True
    assert result["consensus"]["method_count"] == 4
    assert {item["bpm"] for item in result["octave_alternates"]} == {75.0}


def test_three_method_consensus_tolerates_one_outlier():
    result = _resolve_tempo_candidates(
        [_score(1.000, 72.0), _score(0.94, 144.0), _score(0.75, 96.0)],
        [143.4, 144.1, 144.8, 72.0],
    )

    assert result["bpm"] == 144.0
    assert result["consensus_preferred"] is True
    assert result["consensus"]["method_count"] == 3
    assert result["octave_alternates"] == [{"bpm": 72.0, "score": 1.0}]


def test_consensus_does_not_override_poorly_scoring_grid():
    result = _resolve_tempo_candidates(
        [_score(1.000, 75.0), _score(0.89, 150.0), _score(0.70, 100.0)],
        [149.2, 150.0, 150.6, 149.8],
    )

    assert result["bpm"] == 75.0
    assert result["consensus_preferred"] is False
    assert result["octave_alternates"] == []


def test_no_consensus_preserves_slowest_near_tied_subdivision_behavior():
    result = _resolve_tempo_candidates(
        [_score(1.000, 150.0), _score(0.98, 75.0), _score(0.80, 100.0)],
        [75.0, 100.0, 150.0, 190.0],
    )

    assert result["consensus"] is None
    assert result["consensus_preferred"] is False
    assert result["bpm"] == 75.0
    assert result["octave_alternates"] == [{"bpm": 150.0, "score": 1.0}]


def test_loose_three_method_group_is_not_a_tight_consensus():
    assert _tight_tempo_consensus([140.0, 145.0, 150.0, 90.0]) is None


def test_consensus_uses_best_supported_candidate_near_method_center():
    result = _resolve_tempo_candidates(
        [_score(1.000, 75.0), _score(0.96, 149.0), _score(0.95, 150.0)],
        [149.4, 149.8, 150.2],
    )

    assert result["bpm"] == 149.0
    assert result["consensus_preferred"] is True
