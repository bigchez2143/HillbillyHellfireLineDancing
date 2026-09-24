"""Count-locked production blueprints for line-dance tutorial videos.

This module deliberately stops before video generation.  It turns an already
resolved, validated dance into a reviewable production contract: exact source
instructions, beat-grid timing, restrained GB callouts, and camera guidance.
Nothing here tries to split a compound step into guessed foot actions.

The detected beat index is the canonical clock.  Seconds and display
timecodes are derived views, never independently editable timing sources.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import math
from bisect import bisect_left
from datetime import datetime, timezone
from statistics import median

from .assembler import validate_sequence


SCHEMA_VERSION = "1.0"
DEFAULT_COUNT_IN = "Five, six, seven, eight"
ALLOWED_CAMERAS = {
    "rear_full",
    "rear_wide",
    "feet_rear",
    "side_full",
    "overhead_feet",
}

_CLOCK = {
    0: "12:00",
    45: "1:30",
    90: "3:00",
    135: "4:30",
    180: "6:00",
    225: "7:30",
    270: "9:00",
    315: "10:30",
}


def _json_safe(value):
    """Return a JSON primitive tree and remove non-finite numbers.

    Audio analysis normally reaches this module after it has already been
    saved as JSON.  The small ``item`` concession also makes NumPy scalars
    harmless when the engine is called directly in tests or a notebook.
    """
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_safe(item())
        except (TypeError, ValueError):
            pass
    return str(value)


def _canonical_hash(value) -> str:
    payload = json.dumps(
        _json_safe(value), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _dance_snapshot(dance) -> dict:
    dance = dance or {}
    moves = []
    for move in dance.get("moves") or []:
        moves.append({
            key: move.get(key)
            for key in (
                "move_id", "lead", "name", "header", "counts", "rot",
                "start", "end", "level", "sync", "turning", "travel",
                "family", "lines",
            )
        })
    validation = dance.get("validation") or {}
    return _json_safe({
        "total_counts": dance.get("total_counts"),
        "wall": dance.get("wall"),
        "turn_dir": _resolved_turn_dir(dance),
        "walls": dance.get("walls"),
        "net_rot": dance.get("net_rot"),
        "moves": moves,
        "validation": {
            "valid": validation.get("valid"),
            "problems": validation.get("problems") or [],
        },
    })


def _analysis_snapshot(analysis) -> dict:
    analysis = analysis or {}
    return _json_safe({
        key: analysis.get(key)
        for key in (
            "bpm", "duration", "beat_times", "downbeat_times", "methods",
            "candidates",
            "octave_alternates", "drift", "phase_contrast",
            "bpm_confidence", "bpm_confidence_notes",
        )
    })


def _phrase_snapshot(phrase) -> dict:
    phrase = phrase or {}
    return _json_safe({
        key: phrase.get(key)
        for key in (
            "status", "flags", "sections", "music_map", "dance_fit",
            "intro", "outro_beats", "tiling", "totals", "bpm",
        )
    })


def source_fingerprints(dance, analysis, phrase) -> dict:
    """Fingerprints used to invalidate a plan after upstream edits."""
    return {
        "dance_fingerprint": _canonical_hash(_dance_snapshot(dance)),
        "analysis_fingerprint": _canonical_hash(_analysis_snapshot(analysis)),
        "phrase_fingerprint": _canonical_hash(_phrase_snapshot(phrase)),
    }


def _plan_provenance_hash(plan) -> str:
    """Hash immutable sources plus every reviewable production decision."""
    return _canonical_hash({
        key: plan.get(key)
        for key in (
            "schema_version", "kind", "blueprint_revision", "settings",
            "source", "dance", "segments", "wall_plan",
        )
    })


def _timecode(seconds):
    if not isinstance(seconds, (int, float)) or not math.isfinite(seconds):
        return None
    milliseconds = max(0, int(round(float(seconds) * 1000)))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(milliseconds, 1_000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{milliseconds:03d}"


def _clock(degrees):
    try:
        normalized = int(degrees) % 360
    except (TypeError, ValueError):
        return "unknown"
    return _CLOCK.get(normalized, f"{normalized} deg")


def _finite_float(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _positive_int(value):
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _int_or(value, fallback=0):
    if isinstance(value, bool):
        return fallback
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _resolved_turn_dir(dance):
    value = str((dance or {}).get("turn_dir") or "").upper()
    if value in {"L", "R"}:
        return value
    # Resolved dances from older server versions omitted the source setting.
    # Infer only where wall geometry makes it unambiguous.
    if str((dance or {}).get("wall")) == "4":
        rotation = _int_or((dance or {}).get("net_rot"), 0) % 360
        if rotation == 90:
            return "R"
        if rotation == 270:
            return "L"
    return "L"


def _method_consensus(analysis):
    """Recheck the four saved estimators without importing the audio stack."""
    methods = (analysis or {}).get("methods") or {}
    values = sorted(
        value for value in (
            _finite_float(methods.get("autocorrelation")),
            _finite_float(methods.get("beat_tracker_median_ibi")),
            _finite_float(methods.get("tempogram_peak")),
            _finite_float(methods.get("windowed_median")),
        )
        if value is not None and value > 0
    )
    choices = []
    for start in range(len(values)):
        for stop in range(start + 3, len(values) + 1):
            cluster = values[start:stop]
            center = median(cluster)
            spread = (cluster[-1] - cluster[0]) / center
            if spread <= 0.03:
                choices.append((len(cluster), spread, center, cluster))
    if not choices:
        return None
    size, spread, center, cluster = min(
        choices, key=lambda item: (-item[0], item[1], item[2]),
    )
    return {
        "bpm": round(center, 3),
        "method_count": size,
        "spread_pct": round(spread * 100.0, 3),
        "values": [round(value, 3) for value in cluster],
    }


def _method_octave_mismatch(analysis):
    consensus = _method_consensus(analysis)
    selected = _finite_float((analysis or {}).get("bpm"))
    mismatch = False
    ratio = None
    if consensus and selected and selected > 0:
        ratio = max(consensus["bpm"], selected) / min(consensus["bpm"], selected)
        mismatch = abs(ratio - 2.0) <= 0.12
    return consensus, mismatch, (round(ratio, 3) if ratio is not None else None)


def _nearest_beat_index(beat_times, target):
    if not beat_times or target is None:
        return None
    idx = bisect_left(beat_times, target)
    options = []
    if idx < len(beat_times):
        options.append(idx)
    if idx:
        options.append(idx - 1)
    return min(options, key=lambda i: (abs(beat_times[i] - target), i))


def _grid_details(analysis, phrase, count_in_counts, anchor_seconds_override=None):
    raw_beats = (analysis or {}).get("beat_times") or []
    beat_times = [_finite_float(value) for value in raw_beats]
    grid_valid = (
        len(beat_times) >= 2
        and all(value is not None and value >= 0 for value in beat_times)
        and all(right > left for left, right in zip(beat_times, beat_times[1:]))
    )
    if not grid_valid:
        return {
            "beat_times": beat_times,
            "grid_valid": False,
            "anchor_source_seconds": None,
            "anchor_beat_index": None,
            "anchor_seconds": None,
            "anchor_offset_ms": None,
            "anchor_tolerance_ms": None,
            "anchor_on_grid": False,
            "count_in_beat_index": None,
            "grid_interval_seconds": None,
            "grid_bpm": None,
            "bpm_grid_ratio": None,
            "bpm_grid_mismatch": False,
        }

    intervals = [b - a for a, b in zip(beat_times, beat_times[1:])]
    typical_interval = median(intervals)
    grid_bpm = 60.0 / typical_interval if typical_interval > 0 else None
    selected_bpm = _finite_float((analysis or {}).get("bpm"))
    bpm_grid_ratio = (
        max(selected_bpm, grid_bpm) / min(selected_bpm, grid_bpm)
        if selected_bpm and selected_bpm > 0 and grid_bpm and grid_bpm > 0 else None
    )
    bpm_grid_mismatch = bpm_grid_ratio is not None and bpm_grid_ratio > 1.04

    anchor = ((phrase or {}).get("dance_fit") or {}).get("anchor") or {}
    anchor_source_label = anchor.get("section")
    anchor_policy = "dance_fit_anchor"
    anchor_source = _finite_float(anchor.get("time"))
    if anchor_seconds_override is not None:
        anchor_source = _finite_float(anchor_seconds_override)
        anchor_source_label = "Manual Count 1"
        anchor_policy = "manual_override"
    else:
        phrase_sections = (phrase or {}).get("sections") or []
        first = phrase_sections[0] if phrase_sections and isinstance(phrase_sections[0], dict) else None
        if first and str(first.get("label") or "").strip().lower().startswith("intro"):
            next_start = (
                _finite_float(phrase_sections[1].get("start"))
                if len(phrase_sections) > 1 and isinstance(phrase_sections[1], dict)
                else None
            )
            intro_end = _finite_float(first.get("end"))
            anchor_source = next_start if next_start is not None else intro_end
            anchor_source_label = str(first.get("label") or "Intro")
            anchor_policy = "after_intro"
    anchor_index = _nearest_beat_index(beat_times, anchor_source)
    if anchor_index is None:
        return {
            "beat_times": beat_times, "grid_valid": True,
            "anchor_source_seconds": anchor_source,
            "anchor_policy": anchor_policy,
            "anchor_source_label": anchor_source_label,
            "anchor_beat_index": None, "anchor_seconds": None,
            "anchor_offset_ms": None, "anchor_tolerance_ms": None,
            "anchor_on_grid": False, "count_in_beat_index": None,
            "grid_interval_seconds": round(typical_interval, 6),
            "grid_bpm": round(grid_bpm, 3) if grid_bpm else None,
            "bpm_grid_ratio": round(bpm_grid_ratio, 3) if bpm_grid_ratio else None,
            "bpm_grid_mismatch": bpm_grid_mismatch,
        }

    tolerance = max(0.12, typical_interval * 0.30)
    offset = anchor_source - beat_times[anchor_index]
    count_in_index = anchor_index - count_in_counts
    return {
        "beat_times": beat_times,
        "grid_valid": True,
        "anchor_source_seconds": anchor_source,
        "anchor_policy": anchor_policy,
        "anchor_source_label": anchor_source_label,
        "anchor_beat_index": anchor_index,
        "anchor_seconds": beat_times[anchor_index],
        "anchor_offset_ms": int(round(offset * 1000)),
        "anchor_tolerance_ms": int(round(tolerance * 1000)),
        "anchor_on_grid": abs(offset) <= tolerance,
        "count_in_beat_index": count_in_index,
        "grid_interval_seconds": round(typical_interval, 6),
        "grid_bpm": round(grid_bpm, 3) if grid_bpm else None,
        "bpm_grid_ratio": round(bpm_grid_ratio, 3) if bpm_grid_ratio else None,
        "bpm_grid_mismatch": bpm_grid_mismatch,
    }


def _seconds_at_beat_index(beat_index, beat_times, anchor_index, anchor_seconds, bpm):
    """Return source-grid seconds, extending only into real audio pre-roll.

    A detector can start its returned grid at the dance anchor even when the
    recording itself has an intro.  Negative indexes are therefore legitimate
    relative beat positions.  They are extrapolated from the selected BPM only
    when the derived time remains inside the recording (>= 0 seconds).
    """
    if not isinstance(beat_index, int):
        return None
    if 0 <= beat_index < len(beat_times):
        return beat_times[beat_index]
    if (beat_index < 0 and isinstance(anchor_index, int)
            and anchor_seconds is not None and bpm and bpm > 0):
        seconds = anchor_seconds + (beat_index - anchor_index) * (60.0 / bpm)
        return round(seconds, 6) if seconds >= 0 else None
    return None


def _resolve_dance_validation(dance, bpm):
    supplied = (dance or {}).get("validation")
    # Preserve a known failure because the resolved server representation may
    # carry the *actual* count total while its report remembers the requested
    # budget that failed.  A supplied success is still recomputed so an old
    # green badge cannot bless subsequently edited moves.
    if isinstance(supplied, dict) and supplied.get("valid") is False:
        return _json_safe(supplied)
    try:
        fresh = _json_safe(validate_sequence(
            (dance or {}).get("moves") or [],
            (dance or {}).get("total_counts") or 0,
            str((dance or {}).get("wall") or "1"),
            _resolved_turn_dir(dance),
            bpm=bpm,
        ))
        return fresh
    except Exception as exc:  # malformed imported project; report, do not crash
        return {
            "valid": False,
            "problems": [{"code": "DANCE_VALIDATION_FAILED", "message": str(exc)}],
            "notes": [],
        }


def _camera_reason(view):
    return {
        "rear_full": "Unmirrored student view from behind; keep the full body and both feet clear.",
        "rear_wide": "Wide unmirrored student view preserves travel, turns, and both feet.",
        "feet_rear": "Tight rear teaching view makes weight changes readable without reversing left and right.",
        "side_full": "Side teaching view clarifies weight placement; use only after the rear master is secure.",
        "overhead_feet": "Overhead insert clarifies the foot path; use only after the rear master is secure.",
    }.get(view, "Keep the dancer unobstructed and both feet visible.")


def _camera_for_view(view, secondary=None) -> dict:
    rear = view in {"rear_full", "rear_wide", "feet_rear"}
    orientation = (
        "student-view-from-behind" if rear else
        "side-teaching-view" if view == "side_full" else
        "overhead-foot-path"
    )
    return {
        "view": view,
        "id": view,
        "primary": view,
        "secondary": secondary,
        "orientation": orientation,
        "feet_visible": True,
        "unobstructed": True,
        "mirrored": False,
        "reason": _camera_reason(view),
    }


def _camera_for(move) -> dict:
    """Recommend teaching coverage without ever hiding the dancer's feet."""
    turning = bool(move.get("turning") or move.get("rot"))
    sync = bool(move.get("sync"))
    travel = str(move.get("travel") or "")
    text = " ".join(
        str(line.get("text") or "") for line in (move.get("lines") or [])
        if isinstance(line, dict)
    ).lower()
    if turning:
        primary = "rear_wide"
        secondary = "overhead_feet"
    elif sync:
        primary = "feet_rear"
        secondary = "side_full"
    elif travel:
        primary = "rear_wide"
        secondary = "side_full" if travel in ("N", "S") else None
    elif any(word in text for word in ("rock", "kick", "heel", "toe", "coaster")):
        primary = "feet_rear"
        secondary = "side_full"
    else:
        primary = "rear_full"
        secondary = None
    return _camera_for_view(primary, secondary)


def _cue_review_fingerprint(segment):
    callout = segment.get("callout") or {}
    camera = segment.get("camera") or {}
    return _canonical_hash({
        "move_id": segment.get("move_id"),
        "move_name": segment.get("move_name"),
        "lead_foot": segment.get("lead_foot"),
        "counts": segment.get("counts"),
        "start_count": segment.get("start_count"),
        "end_count": segment.get("end_count"),
        "start_beat_index": segment.get("start_beat_index"),
        "end_beat_index_exclusive": segment.get("end_beat_index_exclusive"),
        "start_seconds": segment.get("start_seconds"),
        "end_seconds": segment.get("end_seconds"),
        "facing_start_deg": segment.get("facing_start_deg"),
        "facing_end_deg": segment.get("facing_end_deg"),
        "source_line_fingerprint": segment.get("source_line_fingerprint"),
        "source_context_fingerprint": segment.get("source_context_fingerprint"),
        "callout": {
            "voice": callout.get("voice"),
            "text": callout.get("text"),
            "lead_counts": callout.get("lead_counts"),
        },
        "camera": {
            "view": camera.get("view") or camera.get("id") or camera.get("primary"),
            "secondary": camera.get("secondary"),
            "orientation": camera.get("orientation"),
            "feet_visible": camera.get("feet_visible"),
            "unobstructed": camera.get("unobstructed"),
            "mirrored": camera.get("mirrored"),
        },
    })


def _confirmation_for(confirmations, segment_id, expected_fingerprint):
    value = (confirmations or {}).get(segment_id)
    if isinstance(value, dict):
        safe_match = value.get("confirmation_fingerprint") == expected_fingerprint
        return (
            value.get("confirmed") is True and safe_match,
            str(value.get("review_note") or ""),
            value.get("confirmed_by"),
            value.get("confirmed_at"),
        )
    return False, "", None, None


def _segment_line_fingerprint(move):
    return _canonical_hash([
        {
            "beats": line.get("beats"),
            "text": line.get("text"),
            "sync": bool(line.get("sync", False)),
        }
        for line in (move.get("lines") or []) if isinstance(line, dict)
    ])


def _wall_plan(walls, net_rot, total_counts, segment_ids):
    rows = []
    for index in range(walls):
        start = (index * net_rot) % 360
        end = ((index + 1) * net_rot) % 360
        rows.append({
            "pass": index + 1,
            "wall_number": index + 1,
            "start_facing_deg": start,
            "start_facing": _clock(start),
            "end_facing_deg": end,
            "end_facing": _clock(end),
            "pattern_counts": total_counts,
            "segment_ids": list(segment_ids),
            "camera_baseline": "rear_wide",
            "feet_visible": True,
            "note": "Record as a separate clean teaching pass; keep the dancer unobstructed.",
        })
    return rows


def build_tutorial_plan(
    dance,
    analysis,
    phrase,
    *,
    callout_lead_counts=2,
    tempo_grid_confirmed=False,
    confirmations=None,
    voice_name="Georgia Belle",
    count_in=DEFAULT_COUNT_IN,
    count_in_counts=4,
    anchor_seconds=None,
    voice_notes="",
    producer_notes="",
):
    """Build a JSON-safe tutorial production blueprint.

    ``dance`` must be the resolved dance (expanded move variants), not the
    project's candidate wrapper.  The builder can return ``BLOCKED`` plans;
    that is intentional and lets the UI explain exactly which source needs
    attention rather than failing with an opaque exception.
    """
    dance = dance or {}
    analysis = analysis or {}
    phrase = phrase or {}
    total_counts = _positive_int(dance.get("total_counts")) or 0
    lead_counts = _positive_int(callout_lead_counts)
    if callout_lead_counts == 0:
        lead_counts = 0
    if lead_counts is None:
        lead_counts = -1
    resolved_count_in_counts = _positive_int(count_in_counts) or 4
    bpm = _finite_float(analysis.get("bpm"))
    grid = _grid_details(
        analysis, phrase, resolved_count_in_counts,
        anchor_seconds_override=anchor_seconds,
    )
    beat_times = grid["beat_times"]
    anchor_index = grid["anchor_beat_index"]
    anchor_seconds = grid.get("anchor_seconds")
    method_consensus, method_octave_mismatch, method_ratio = \
        _method_octave_mismatch(analysis)
    fingerprints = source_fingerprints(dance, analysis, phrase)
    dance_validation = _resolve_dance_validation(dance, bpm)

    segments = []
    count_pos = 0
    facing = 0
    for index, raw_move in enumerate(dance.get("moves") or []):
        move = raw_move if isinstance(raw_move, dict) else {}
        counts = _positive_int(move.get("counts")) or 0
        start_count = count_pos + 1
        end_count = count_pos + counts
        start_beat_index = anchor_index + count_pos if anchor_index is not None else None
        end_beat_index = anchor_index + end_count if anchor_index is not None else None
        callout_index = (
            start_beat_index - lead_counts
            if start_beat_index is not None and lead_counts >= 0 else None
        )

        def timing_value(beat_index):
            return _seconds_at_beat_index(
                beat_index, beat_times, anchor_index, anchor_seconds, bpm,
            )

        start_seconds = timing_value(start_beat_index)
        end_seconds = timing_value(end_beat_index)
        callout_seconds = timing_value(callout_index)
        move_name = str(move.get("name") or "").strip()
        segment_id = f"seg-{index + 1:03d}-c{start_count:03d}-{end_count:03d}"

        instruction_lines = []
        line_count_pos = start_count
        for line_index, raw_line in enumerate(move.get("lines") or []):
            line = raw_line if isinstance(raw_line, dict) else {}
            line_beats = _positive_int(line.get("beats")) or 0
            line_end = line_count_pos + line_beats - 1
            instruction_lines.append({
                "source_line_index": line_index,
                "beats": line_beats,
                "sync": bool(line.get("sync", False)),
                "text": str(line.get("text") or ""),
                "start_count": line_count_pos,
                "end_count": line_end,
                "count_label": (
                    str(line_count_pos) if line_count_pos == line_end
                    else f"{line_count_pos}-{line_end}"
                ),
            })
            line_count_pos += line_beats

        facing_end = (facing + _int_or(move.get("rot"), 0)) % 360
        segment = {
            "id": segment_id,
            "move_index": index,
            "move_id": move.get("move_id"),
            "move_name": move_name,
            "lead_foot": move.get("lead"),
            "counts": counts,
            "start_count": start_count,
            "end_count": end_count,
            "count_label": (
                str(start_count) if start_count == end_count
                else f"{start_count}-{end_count}"
            ),
            "start_beat_index": start_beat_index,
            "end_beat_index_exclusive": end_beat_index,
            "start_seconds": start_seconds,
            "end_seconds": end_seconds,
            "timecode": _timecode(start_seconds),
            "start_timecode": _timecode(start_seconds),
            "end_timecode": _timecode(end_seconds),
            "facing_start_deg": facing,
            "facing_end_deg": facing_end,
            "facing_start": _clock(facing),
            "facing_end": _clock(facing_end),
            "instruction_lines": instruction_lines,
            "lines": [line["text"] for line in instruction_lines],
            "source_line_fingerprint": _segment_line_fingerprint(move),
            "source_context_fingerprint": _canonical_hash(fingerprints),
            "callout": {
                "voice": str(voice_name or ""),
                "text": move_name,
                "lead_counts": lead_counts,
                "beat_index": callout_index,
                "seconds": callout_seconds,
                "timecode": _timecode(callout_seconds),
            },
            "camera": _camera_for(move),
            "confirmed": False,
            "review_note": "",
            "confirmed_by": None,
            "confirmed_at": None,
            "confirmation_fingerprint": None,
        }
        expected_confirmation = _cue_review_fingerprint(segment)
        confirmed, review_note, confirmed_by, confirmed_at = _confirmation_for(
            confirmations, segment_id, expected_confirmation,
        )
        segment.update({
            "confirmed": confirmed,
            "review_note": review_note,
            "confirmed_by": confirmed_by if confirmed else None,
            "confirmed_at": confirmed_at if confirmed else None,
            "confirmation_fingerprint": expected_confirmation if confirmed else None,
        })
        segments.append(segment)
        count_pos = end_count
        facing = facing_end

    try:
        walls = int(dance.get("walls") or 0)
    except (TypeError, ValueError):
        walls = 0
    net_rot = _int_or(dance.get("net_rot") or facing, 0) % 360
    if walls not in (1, 2, 4):
        walls = 0

    count_in_index = grid.get("count_in_beat_index")
    count_in_seconds = _seconds_at_beat_index(
        count_in_index, beat_times, anchor_index, anchor_seconds, bpm,
    )
    source = {
        **fingerprints,
        "bpm": bpm,
        "canonical_timing_unit": "beat_index",
        "beat_index_base": 0,
        "beat_times_count": len(beat_times),
        "timing_grid_valid": grid["grid_valid"],
        "grid_interval_seconds": grid.get("grid_interval_seconds"),
        "grid_bpm": grid.get("grid_bpm"),
        "bpm_grid_ratio": grid.get("bpm_grid_ratio"),
        "bpm_grid_mismatch": grid.get("bpm_grid_mismatch"),
        "octave_alternates": _json_safe(analysis.get("octave_alternates") or []),
        "methods": _json_safe(analysis.get("methods") or {}),
        "method_consensus": _json_safe(method_consensus),
        "method_octave_mismatch": method_octave_mismatch,
        "method_selected_ratio": method_ratio,
        "drift": _json_safe(analysis.get("drift")),
        "bpm_confidence": analysis.get("bpm_confidence"),
        "anchor_source_seconds": grid.get("anchor_source_seconds"),
        "anchor_policy": grid.get("anchor_policy"),
        "anchor_source_label": grid.get("anchor_source_label"),
        "anchor_beat_index": anchor_index,
        "anchor_seconds": grid.get("anchor_seconds"),
        "anchor_timecode": _timecode(grid.get("anchor_seconds")),
        "anchor_offset_ms": grid.get("anchor_offset_ms"),
        "anchor_tolerance_ms": grid.get("anchor_tolerance_ms"),
        "anchor_on_grid": grid.get("anchor_on_grid"),
        "count_in_beat_index": count_in_index,
        "count_in_seconds": count_in_seconds,
        "count_in_timecode": _timecode(count_in_seconds),
        "phrase_status": phrase.get("status"),
        "phrase_flags": _json_safe(phrase.get("flags") or []),
        "phrase_pattern_len": ((phrase.get("dance_fit") or {}).get("pattern_len")),
        "dance_validation": dance_validation,
    }
    plan = {
        "schema_version": SCHEMA_VERSION,
        "kind": "line_dance_tutorial_blueprint",
        "blueprint_revision": 1,
        "status": "REVIEW",
        "settings": {
            "callout_lead_counts": lead_counts,
            "voice_name": str(voice_name or ""),
            "tempo_grid_confirmed": tempo_grid_confirmed is True,
            "count_in": str(count_in or ""),
            "count_in_counts": resolved_count_in_counts,
            "anchor_seconds_override": (
                _finite_float(anchor_seconds) if anchor_seconds is not None else None
            ),
            "voice_notes": str(voice_notes or ""),
            "producer_notes": str(producer_notes or ""),
        },
        "source": source,
        "dance": {
            "total_counts": total_counts,
            "wall": str(dance.get("wall") or ""),
            "turn_dir": _resolved_turn_dir(dance),
            "walls": walls,
            "net_rot": net_rot,
        },
        "segments": segments,
        "wall_plan": _wall_plan(
            walls, net_rot, total_counts, [segment["id"] for segment in segments],
        ),
        "validation": {},
    }
    plan = _json_safe(plan)
    plan["provenance_hash"] = _plan_provenance_hash(plan)
    report = validate_tutorial_plan(plan, dance, analysis, phrase)
    plan["validation"] = report
    plan["status"] = report["status"]
    # An initial build must not be READY by accident.  It may be regenerated
    # with explicit confirmations, which is how saved human decisions survive.
    return plan


def _issue(bucket, code, message, **details):
    issue = {"code": code, "message": message}
    issue.update({key: _json_safe(value) for key, value in details.items()})
    # A tampered plan can trigger the same structural seam more than once;
    # keep the report compact and deterministic.
    if not any(existing.get("code") == code
               and existing.get("segment_id") == issue.get("segment_id")
               and existing.get("section") == issue.get("section")
               for existing in bucket):
        bucket.append(issue)


def validate_tutorial_plan(plan, dance=None, analysis=None, phrase=None):
    """Validate a blueprint and, when supplied, detect stale source data.

    Returns a report only; it does not mutate ``plan``.  Pass the current
    resolved dance, analysis, and phrase report before rendering/publishing.
    """
    plan = plan or {}
    errors = []
    warnings = []
    settings = plan.get("settings") or {}
    source = plan.get("source") or {}
    dance_info = plan.get("dance") or {}
    segments = plan.get("segments") or []

    if plan.get("schema_version") != SCHEMA_VERSION:
        _issue(errors, "SCHEMA_VERSION", "This tutorial plan uses an unsupported schema version.")
    if not isinstance(plan.get("blueprint_revision"), int) or plan.get("blueprint_revision") < 1:
        _issue(errors, "BLUEPRINT_REVISION_INVALID", "The blueprint revision is missing or invalid.")
    if (not plan.get("provenance_hash")
            or plan.get("provenance_hash") != _plan_provenance_hash(plan)):
        _issue(errors, "PROVENANCE_MISMATCH",
               "The tutorial plan changed outside the reviewed edit path; reload or rebuild it.")

    # Source freshness is an export gate.  Any edit to the expanded moves,
    # timing grid, or phrase map invalidates the old production plan.
    current = source_fingerprints(dance, analysis, phrase)
    supplied_sources = (("dance_fingerprint", dance),
                        ("analysis_fingerprint", analysis),
                        ("phrase_fingerprint", phrase))
    for key, value in supplied_sources:
        if value is not None and source.get(key) != current[key]:
            _issue(errors, "STALE_" + key.split("_")[0].upper(),
                   f"The {key.split('_')[0]} changed after this tutorial plan was built; regenerate it.")

    validation = source.get("dance_validation") or {}
    if validation.get("valid") is not True:
        message = "The current dance has not passed count, foot, wall, and loop validation."
        problems = validation.get("problems") or []
        if problems:
            message += " " + " ".join(str(item.get("message") or "") for item in problems[:3])
        _issue(errors, "INVALID_DANCE", message)

    total_counts = _positive_int(dance_info.get("total_counts")) or 0
    if total_counts <= 0:
        _issue(errors, "MISSING_DANCE_COUNTS", "The dance needs a positive count budget.")

    if source.get("timing_grid_valid") is not True:
        _issue(errors, "MISSING_TIMING_GRID",
               "No strictly increasing beat grid is available; analyse and confirm the song first.")
    bpm = _finite_float(source.get("bpm"))
    if bpm is None or bpm <= 0:
        _issue(errors, "INVALID_BPM", "The tutorial needs a measured positive BPM.")
    if source.get("bpm_grid_mismatch") is True:
        _issue(errors, "BPM_GRID_MISMATCH",
               f"The selected BPM is {source.get('bpm')} but the saved beat indexes run near "
               f"{source.get('grid_bpm')} BPM. Reanalyse or repair the timing grid before production.")
    if source.get("anchor_beat_index") is None or source.get("anchor_seconds") is None:
        _issue(errors, "MISSING_COUNT_ANCHOR",
               "The phrasing report does not provide a count-one anchor on the beat grid.")
    elif source.get("anchor_on_grid") is not True:
        _issue(errors, "ANCHOR_OFF_GRID",
               "The selected dance start is too far from the nearest detected beat; confirm the start by ear and rebuild.",
               offset_ms=source.get("anchor_offset_ms"),
               tolerance_ms=source.get("anchor_tolerance_ms"))

    alternates = source.get("octave_alternates") or []
    method_mismatch = source.get("method_octave_mismatch") is True
    if (alternates or method_mismatch) and settings.get("tempo_grid_confirmed") is not True:
        _issue(errors, "TEMPO_GRID_UNCONFIRMED",
               "Half/double-time tempo ambiguity is open. Confirm the floor-count grid before timing a tutorial.")
    if method_mismatch:
        consensus = source.get("method_consensus") or {}
        _issue(warnings, "METHOD_CONSENSUS_MISMATCH",
               f"The saved BPM is {source.get('bpm')} while {consensus.get('method_count', 3)} methods cluster near "
               f"{consensus.get('bpm')} BPM; retain the human floor-count confirmation with this plan.")
    if source.get("drift"):
        _issue(errors, "TEMPO_DRIFT",
               "Detected tempo drift makes a fixed beat-index tutorial unsafe until the grid is repaired or manually verified.")

    phrase_status = source.get("phrase_status")
    if not phrase_status:
        _issue(errors, "PHRASE_MISSING", "Run the dance-fit phrasing check before building a tutorial.")
    elif phrase_status == "UNCERTAIN":
        _issue(errors, "PHRASING_UNCERTAIN",
               "The phrasing report is uncertain; resolve its blocking flags before production.")
    elif phrase_status == "REVIEW":
        _issue(warnings, "PHRASING_REVIEW",
               "The phrasing report has review flags; keep them visible during the floor test.")
    for flag in source.get("phrase_flags") or []:
        severity = flag.get("severity") if isinstance(flag, dict) else None
        if severity == "error":
            _issue(errors, "PHRASE_FLAG_" + str(flag.get("code") or "ERROR"),
                   str(flag.get("message") or "A phrasing error remains open."),
                   section=flag.get("section"))
        elif severity == "warn":
            _issue(warnings, "PHRASE_FLAG_" + str(flag.get("code") or "WARN"),
                   str(flag.get("message") or "A phrasing warning needs review."),
                   section=flag.get("section"))
    pattern_len = _positive_int(source.get("phrase_pattern_len"))
    if pattern_len is None:
        _issue(errors, "PHRASE_PATTERN_MISSING",
               "The phrasing report does not identify the dance pattern length.")
    elif total_counts and pattern_len != total_counts:
        _issue(errors, "PHRASE_PATTERN_MISMATCH",
               f"The phrase overlay is {pattern_len} counts but the dance is {total_counts}; rerun dance fit.")

    lead_counts = settings.get("callout_lead_counts")
    if isinstance(lead_counts, bool) or not isinstance(lead_counts, int) or not 0 <= lead_counts <= 8:
        _issue(errors, "CALLOUT_LEAD_INVALID", "Callout lead must be a whole number from 0 to 8 counts.")
    if not str(settings.get("voice_name") or "").strip():
        _issue(errors, "VOICE_NAME_MISSING", "Name the callout voice (normally GB).")
    if not str(settings.get("count_in") or "").strip():
        _issue(errors, "COUNT_IN_MISSING", "Provide the exact spoken count-in script.")
    if source.get("count_in_beat_index") is None or source.get("count_in_seconds") is None:
        _issue(errors, "COUNT_IN_PREROLL_MISSING",
               "The beat grid does not contain enough pre-roll for the spoken count-in.")

    expected_start = 1
    expected_beat = source.get("anchor_beat_index")
    seen_ids = set()
    previous_callout = None
    confirmed = 0
    for index, segment in enumerate(segments):
        sid = str(segment.get("id") or "")
        if not sid or sid in seen_ids:
            _issue(errors, "SEGMENT_ID_INVALID", "Each segment needs a unique stable ID.", segment_id=sid or None)
        seen_ids.add(sid)
        counts = _positive_int(segment.get("counts")) or 0
        start = segment.get("start_count")
        end = segment.get("end_count")
        if start != expected_start or end != expected_start + counts - 1:
            _issue(errors, "COUNT_COVERAGE",
                   "Tutorial segments must cover every dance count once, in order.", segment_id=sid)
        expected_start += counts

        start_beat = segment.get("start_beat_index")
        end_beat = segment.get("end_beat_index_exclusive")
        if (expected_beat is None or start_beat != expected_beat
                or end_beat != (start_beat + counts if isinstance(start_beat, int) else None)):
            _issue(errors, "BEAT_COVERAGE",
                   "Segment beat indexes must be contiguous and count-locked.", segment_id=sid)
        if isinstance(end_beat, int):
            expected_beat = end_beat
        if segment.get("start_seconds") is None or segment.get("end_seconds") is None:
            _issue(errors, "TIMING_OUT_OF_RANGE",
                   "The beat grid does not cover this segment's complete duration.", segment_id=sid)
        if not segment.get("timecode") or not segment.get("end_timecode"):
            _issue(errors, "TIMECODE_MISSING",
                   "Derived start and end timecodes are required for every segment.", segment_id=sid)

        lines = segment.get("instruction_lines") or []
        line_total = 0
        line_next = start
        comparable_lines = []
        for line in lines:
            beats = _positive_int(line.get("beats")) if isinstance(line, dict) else None
            text = str(line.get("text") or "") if isinstance(line, dict) else ""
            if not beats or not text:
                _issue(errors, "INSTRUCTION_LINE_INVALID",
                       "Every source instruction line needs text and a positive beat span.", segment_id=sid)
                continue
            if line.get("start_count") != line_next or line.get("end_count") != line_next + beats - 1:
                _issue(errors, "LINE_COUNT_COVERAGE",
                       "Instruction lines must cover the segment counts without gaps.", segment_id=sid)
            line_total += beats
            line_next += beats
            comparable_lines.append({"beats": beats, "text": text,
                                     "sync": bool(line.get("sync", False))})
        if line_total != counts:
            _issue(errors, "LINE_COUNT_COVERAGE",
                   "The exact source instruction lines do not cover the move's count span.", segment_id=sid)
        if _canonical_hash(comparable_lines) != segment.get("source_line_fingerprint"):
            _issue(errors, "INSTRUCTION_SOURCE_CHANGED",
                   "An instruction line differs from the exact source move; regenerate instead of inventing footwork.",
                   segment_id=sid)

        callout = segment.get("callout") or {}
        if callout.get("voice") != settings.get("voice_name"):
            _issue(errors, "CALLOUT_VOICE_MISMATCH",
                   "Each segment callout must use the selected GB voice label.", segment_id=sid)
        callout_text = str(callout.get("text") or "").strip()
        if not callout_text or len(callout_text) > 120:
            _issue(errors, "CALLOUT_TEXT_INVALID",
                   "Each GB callout needs a concise move name (120 characters maximum).",
                   segment_id=sid)
        if callout.get("lead_counts") != lead_counts:
            _issue(errors, "CALLOUT_LEAD_MISMATCH",
                   "Every callout must use the plan's configured lead counts.", segment_id=sid)
        expected_callout = start_beat - lead_counts if isinstance(start_beat, int) and isinstance(lead_counts, int) else None
        if callout.get("beat_index") != expected_callout or callout.get("seconds") is None or not callout.get("timecode"):
            _issue(errors, "CALLOUT_TIMING_INVALID",
                   "A callout must land exactly the configured number of beat indexes before its move.", segment_id=sid)
        if isinstance(callout.get("beat_index"), int):
            if previous_callout is not None and callout["beat_index"] < previous_callout:
                _issue(errors, "CALLOUT_ORDER",
                       "Callouts must remain in timeline order.", segment_id=sid)
            previous_callout = callout["beat_index"]

        camera = segment.get("camera") or {}
        camera_view = camera.get("view") or camera.get("id") or camera.get("primary")
        if camera_view not in ALLOWED_CAMERAS:
            _issue(errors, "CAMERA_PRIMARY_INVALID",
                   "Choose one of the approved teaching camera views.", segment_id=sid)
        if camera.get("secondary") not in ALLOWED_CAMERAS | {None}:
            _issue(errors, "CAMERA_SECONDARY_INVALID", "The secondary camera recommendation is unknown.", segment_id=sid)
        if camera.get("feet_visible") is not True or camera.get("unobstructed") is not True:
            _issue(errors, "FEET_OBSTRUCTED",
                   "Every teaching shot must explicitly keep both feet visible and unobstructed.", segment_id=sid)
        expected_orientation = (
            "student-view-from-behind" if camera_view in {"rear_full", "rear_wide", "feet_rear"}
            else "side-teaching-view" if camera_view == "side_full"
            else "overhead-foot-path"
        )
        if camera.get("mirrored") is not False or camera.get("orientation") != expected_orientation:
            _issue(errors, "CAMERA_ORIENTATION_INVALID",
                   "The chosen camera must retain its unmirrored teaching orientation.", segment_id=sid)
        if camera_view not in {"rear_full", "rear_wide", "feet_rear"}:
            _issue(warnings, "NON_REAR_PRIMARY",
                   "A side or overhead primary is an intentional override; keep a clean rear/student master too.",
                   segment_id=sid)

        if segment.get("confirmed") is True:
            if segment.get("confirmation_fingerprint") == _cue_review_fingerprint(segment):
                confirmed += 1
            else:
                _issue(warnings, "CONFIRMATION_STALE",
                       "This cue changed after its human check and must be confirmed again.",
                       segment_id=sid)

        if dance is not None:
            current_moves = (dance or {}).get("moves") or []
            move_index = segment.get("move_index")
            if not isinstance(move_index, int) or not 0 <= move_index < len(current_moves):
                _issue(errors, "STALE_SEGMENT_MOVE",
                       "This segment no longer maps to a current dance move.", segment_id=sid)
            else:
                current_move = current_moves[move_index]
                if (segment.get("move_id") != current_move.get("move_id")
                        or segment.get("move_name") != current_move.get("name")
                        or segment.get("source_line_fingerprint") != _segment_line_fingerprint(current_move)):
                    _issue(errors, "STALE_SEGMENT_MOVE",
                           "The source move or its exact instruction lines changed; regenerate the plan.",
                           segment_id=sid)

    if expected_start - 1 != total_counts:
        _issue(errors, "COUNT_COVERAGE",
               f"Tutorial segments cover {expected_start - 1} counts, not the required {total_counts}.")
    if not segments:
        _issue(errors, "NO_SEGMENTS", "The tutorial plan has no choreographic segments.")

    walls = dance_info.get("walls")
    wall_plan = plan.get("wall_plan") or []
    if walls not in (1, 2, 4) or len(wall_plan) != walls:
        _issue(errors, "WALL_PLAN_INVALID",
               "The production plan must include one clean teaching pass for every wall.")
    else:
        net_rot = _int_or(dance_info.get("net_rot"), 0) % 360
        for index, row in enumerate(wall_plan):
            expected_wall_start = (index * net_rot) % 360
            expected_wall_end = ((index + 1) * net_rot) % 360
            if (row.get("pass") != index + 1
                    or row.get("start_facing_deg") != expected_wall_start
                    or row.get("end_facing_deg") != expected_wall_end
                    or row.get("segment_ids") != [s.get("id") for s in segments]
                    or row.get("feet_visible") is not True):
                _issue(errors, "WALL_PLAN_INVALID",
                       "Wall passes must preserve the validated rotation, segment order, and visible feet.")
                break

    confirmation_pending = len(segments) - confirmed
    if errors:
        status = "BLOCKED"
    elif confirmation_pending:
        status = "REVIEW"
    else:
        status = "READY"
    return {
        "status": status,
        "ready": status == "READY",
        "errors": errors,
        "warnings": warnings,
        "confirmed_segments": confirmed,
        "total_segments": len(segments),
        "confirmation_pending": confirmation_pending,
    }


def update_tutorial_plan(
    plan,
    edits,
    *,
    count_in=None,
    voice_notes=None,
    producer_notes=None,
    tempo_grid_confirmed=None,
):
    """Apply the small, explicit set of human-review edits to a plan.

    ``edits`` is normally the UI's list of ``{id, callout, camera,
    confirmed, review_note}`` rows.  A mapping keyed by segment ID is also
    accepted for API clients.  Timing, counts, footwork, source hashes, wall
    geometry, and move identity are deliberately immutable; those require a
    rebuild from the reviewed dance.
    """
    if (not isinstance(plan, dict) or not plan.get("provenance_hash")
            or plan.get("provenance_hash") != _plan_provenance_hash(plan)):
        raise ValueError(
            "This tutorial plan failed its provenance check; reload or rebuild before editing."
        )
    updated = copy.deepcopy(plan)
    segments = updated.get("segments") or []
    by_id = {segment.get("id"): segment for segment in segments}
    if isinstance(edits, dict):
        rows = []
        for segment_id, values in edits.items():
            if isinstance(values, dict):
                rows.append({"id": segment_id, **values})
            else:
                raise ValueError("Each tutorial segment edit must be an object.")
    elif isinstance(edits, list):
        rows = edits
    else:
        raise ValueError("Tutorial edits must be a list or a mapping by segment ID.")

    allowed = {"id", "callout", "camera", "confirmed", "review_note"}
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Each tutorial segment edit must be an object.")
        unknown = set(row) - allowed
        if unknown:
            raise ValueError(
                "Tutorial timing and footwork are immutable; unsupported edit fields: "
                + ", ".join(sorted(unknown))
            )
        segment_id = row.get("id")
        if segment_id not in by_id:
            raise KeyError(f"Unknown tutorial segment: {segment_id}")
        if segment_id in seen:
            raise ValueError(f"Duplicate tutorial segment edit: {segment_id}")
        seen.add(segment_id)
        segment = by_id[segment_id]
        cue_changed = False

        if "callout" in row:
            text = str(row.get("callout") or "").strip()
            if len(text) > 120:
                raise ValueError("GB callouts are limited to 120 characters.")
            cue_changed = text != str((segment.get("callout") or {}).get("text") or "")
            segment.setdefault("callout", {})["text"] = text
        if "camera" in row:
            view = str(row.get("camera") or "")
            if view not in ALLOWED_CAMERAS:
                raise ValueError(f"Unknown tutorial camera view: {view}")
            # Recompute all dependent safety/orientation fields.  Keeping old
            # reason text after changing the view would make the shot list lie.
            old_camera = segment.get("camera") or {}
            old_view = old_camera.get("view") or old_camera.get("id") or old_camera.get("primary")
            cue_changed = cue_changed or view != old_view
            if old_view == view:
                secondary = old_camera.get("secondary")
            elif view in {"side_full", "overhead_feet"}:
                secondary = "rear_wide"
            else:
                secondary = None
            segment["camera"] = _camera_for_view(view, secondary)
        if cue_changed:
            # A reviewed cue cannot stay green after its words or view change.
            # The same request may explicitly confirm the revised cue below.
            segment["confirmed"] = False
            segment["confirmed_at"] = None
            segment["confirmed_by"] = None
            segment["confirmation_fingerprint"] = None
        if "confirmed" in row:
            segment["confirmed"] = row.get("confirmed") is True
            if segment["confirmed"]:
                segment["confirmed_at"] = datetime.now(timezone.utc).isoformat()
                segment["confirmation_fingerprint"] = _cue_review_fingerprint(segment)
            else:
                segment["confirmed_at"] = None
                segment["confirmed_by"] = None
                segment["confirmation_fingerprint"] = None
        if "review_note" in row:
            note = str(row.get("review_note") or "")
            if len(note) > 240:
                raise ValueError("Tutorial review notes are limited to 240 characters.")
            segment["review_note"] = note

    settings = updated.setdefault("settings", {})
    if count_in is not None:
        value = str(count_in).strip()
        if len(value) > 160:
            raise ValueError("The spoken count-in is limited to 160 characters.")
        settings["count_in"] = value
    if voice_notes is not None:
        settings["voice_notes"] = str(voice_notes)
    if producer_notes is not None:
        settings["producer_notes"] = str(producer_notes)
    if tempo_grid_confirmed is not None:
        settings["tempo_grid_confirmed"] = tempo_grid_confirmed is True

    updated["blueprint_revision"] = int(updated.get("blueprint_revision") or 0) + 1
    updated["provenance_hash"] = _plan_provenance_hash(updated)
    report = validate_tutorial_plan(updated)
    updated["validation"] = report
    updated["status"] = report["status"]
    return _json_safe(updated)


def confirm_tutorial_segment(
    plan,
    segment_id,
    confirmed=True,
    review_note="",
    confirmed_by=None,
    confirmed_at=None,
):
    """Return a copied plan with one explicit human confirmation updated."""
    if (not isinstance(plan, dict) or not plan.get("provenance_hash")
            or plan.get("provenance_hash") != _plan_provenance_hash(plan)):
        raise ValueError(
            "This tutorial plan failed its provenance check; reload or rebuild before confirming."
        )
    updated = copy.deepcopy(plan)
    match = None
    for segment in updated.get("segments") or []:
        if segment.get("id") == segment_id:
            match = segment
            break
    if match is None:
        raise KeyError(f"Unknown tutorial segment: {segment_id}")
    match["confirmed"] = confirmed is True
    match["review_note"] = str(review_note or "")
    match["confirmed_by"] = confirmed_by if confirmed is True else None
    if confirmed is True:
        match["confirmed_at"] = confirmed_at or datetime.now(timezone.utc).isoformat()
        match["confirmation_fingerprint"] = _cue_review_fingerprint(match)
    else:
        match["confirmed_at"] = None
        match["confirmation_fingerprint"] = None
    updated["blueprint_revision"] = int(updated.get("blueprint_revision") or 0) + 1
    updated["provenance_hash"] = _plan_provenance_hash(updated)
    report = validate_tutorial_plan(updated)
    updated["validation"] = report
    updated["status"] = report["status"]
    return _json_safe(updated)


def _effective_validation(plan):
    """Use the strictest trustworthy view of derived plan state.

    Cached validation can legitimately be stricter than a source-free local
    check (for example, the server has just detected a stale current dance).
    It must never be allowed to make a structurally REVIEW/BLOCKED plan appear
    READY, because status and validation are intentionally not provenance
    inputs.
    """
    fresh = validate_tutorial_plan(plan)
    cached = plan.get("validation") if isinstance(plan, dict) else None
    if not isinstance(cached, dict) or cached.get("status") not in {"READY", "REVIEW", "BLOCKED"}:
        return fresh
    rank = {"READY": 0, "REVIEW": 1, "BLOCKED": 2}
    return cached if rank[cached["status"]] >= rank[fresh["status"]] else fresh


def render_tutorial_txt(plan) -> str:
    """Render a producer-readable plain-text review sheet."""
    source = plan.get("source") or {}
    settings = plan.get("settings") or {}
    dance = plan.get("dance") or {}
    validation = _effective_validation(plan)
    out = [
        "HILLBILLY HELLFIRE - LINE-DANCE TUTORIAL BLUEPRINT",
        "=" * 58,
        f"STATUS: {validation.get('status', 'REVIEW')}",
        f"Dance: {dance.get('total_counts', '?')} counts / {dance.get('walls', '?')} wall(s)",
        f"Tempo: {source.get('bpm', 'NOT MEASURED')} BPM",
        (f"Count-one anchor: beat index {source.get('anchor_beat_index')} / "
         f"{source.get('anchor_timecode') or 'NOT TIMED'}"),
        f"GB count-in: {settings.get('count_in') or 'NOT SET'}",
        f"Callout lead: {settings.get('callout_lead_counts')} counts",
        "",
        "SEGMENTS - SOURCE INSTRUCTIONS ARE VERBATIM",
        "-" * 58,
    ]
    for segment in plan.get("segments") or []:
        callout = segment.get("callout") or {}
        camera = segment.get("camera") or {}
        state = "CONFIRMED" if segment.get("confirmed") is True else "REVIEW REQUIRED"
        out.extend([
            (f"{segment.get('id')} | counts {segment.get('count_label')} | "
             f"{segment.get('timecode') or 'NOT TIMED'}-{segment.get('end_timecode') or 'NOT TIMED'}"),
            (f"Move: {segment.get('move_name')} | facing "
             f"{segment.get('facing_start')} -> {segment.get('facing_end')}"),
            (f"GB @ {callout.get('timecode') or 'NOT TIMED'} "
             f"(-{callout.get('lead_counts')}): {callout.get('text') or 'NOT SET'}"),
            (f"Camera: {camera.get('primary') or 'NOT SET'}"
             + (f"; insert {camera.get('secondary')}" if camera.get('secondary') else "")),
        ])
        for line in segment.get("instruction_lines") or []:
            out.append(f"  Counts {line.get('count_label')}: {line.get('text')}")
        out.append(f"Human check: {state}" +
                   (f" - {segment.get('review_note')}" if segment.get("review_note") else ""))
        out.append("")
    out.extend(["WALL / PASS PLAN", "-" * 58])
    for row in plan.get("wall_plan") or []:
        out.append(
            f"Pass {row.get('pass')}: {row.get('start_facing')} -> {row.get('end_facing')} "
            f"| {row.get('camera_baseline')} | feet visible"
        )
    if validation.get("errors") or validation.get("warnings"):
        out.extend(["", "VALIDATION", "-" * 58])
        for issue in validation.get("errors") or []:
            out.append(f"BLOCKED [{issue.get('code')}]: {issue.get('message')}")
        for issue in validation.get("warnings") or []:
            out.append(f"REVIEW [{issue.get('code')}]: {issue.get('message')}")
    out.append("")
    return "\n".join(out)


def render_tutorial_csv(plan) -> str:
    """Render one spreadsheet-ready row per move segment."""
    stream = io.StringIO(newline="")
    validation = _effective_validation(plan)
    fields = [
        "plan_status", "plan_ready",
        "segment_id", "counts", "start_beat_index", "end_beat_index_exclusive",
        "start_timecode", "end_timecode", "move_name", "instruction_lines",
        "facing_start", "facing_end", "gb_callout", "callout_beat_index",
        "callout_timecode", "callout_lead_counts", "camera_primary",
        "camera_secondary", "feet_visible", "unobstructed", "confirmed",
        "review_note",
    ]
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for segment in plan.get("segments") or []:
        callout = segment.get("callout") or {}
        camera = segment.get("camera") or {}
        writer.writerow({
            "plan_status": validation.get("status"),
            "plan_ready": validation.get("ready") is True,
            "segment_id": segment.get("id"),
            "counts": segment.get("count_label"),
            "start_beat_index": segment.get("start_beat_index"),
            "end_beat_index_exclusive": segment.get("end_beat_index_exclusive"),
            "start_timecode": segment.get("timecode"),
            "end_timecode": segment.get("end_timecode"),
            "move_name": segment.get("move_name"),
            "instruction_lines": " | ".join(
                str(line.get("text") or "") for line in segment.get("instruction_lines") or []
            ),
            "facing_start": segment.get("facing_start"),
            "facing_end": segment.get("facing_end"),
            "gb_callout": callout.get("text"),
            "callout_beat_index": callout.get("beat_index"),
            "callout_timecode": callout.get("timecode"),
            "callout_lead_counts": callout.get("lead_counts"),
            "camera_primary": camera.get("primary"),
            "camera_secondary": camera.get("secondary"),
            "feet_visible": camera.get("feet_visible"),
            "unobstructed": camera.get("unobstructed"),
            "confirmed": segment.get("confirmed") is True,
            "review_note": segment.get("review_note"),
        })
    return stream.getvalue()


def render_tutorial_json(plan, indent=2) -> str:
    """Serialize with strict JSON rules (NaN/Infinity are rejected)."""
    normalized = copy.deepcopy(plan)
    report = _effective_validation(normalized)
    normalized["validation"] = report
    normalized["status"] = report["status"]
    return json.dumps(_json_safe(normalized), ensure_ascii=False, indent=indent,
                      sort_keys=True, allow_nan=False)
