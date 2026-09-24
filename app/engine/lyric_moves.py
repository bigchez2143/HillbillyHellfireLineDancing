"""Conservative lyric-command detection for reviewable line-dance drafts.

The module deliberately separates *recognising words* from *authoring
footwork*.  A lyric is allowed to pin a move only when a narrow, reviewed
grammar identifies a move whose counts, feet, and rotation already exist in
``engine.steps``.  Figurative or mechanically incomplete phrases remain
visible as unresolved review items; they are never turned into plausible
looking choreography.

``build_draft`` is pure with respect to project persistence.  It reads a
project dictionary, optionally asks the anchored assembler for complete gap
filled candidates, and returns a JSON-safe review draft.  Saving or applying
one of those candidates is intentionally the server/UI's responsibility.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from typing import Any

from . import assembler as assembler_engine
from .steps import get_move


SCHEMA_VERSION = 1
ALGORITHM_VERSION = "lyric-moves-v1"
SUPPORTED_LEVELS = {"AB", "B", "I", "INT", "A"}

_SPACE_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)
_SLIDE_DIRECTION_RE = re.compile(
    r"^(?:now\s+)?slide(?:\s+to)?(?:\s+the)?\s+(right|left)(?:\s+now)?$"
)
_COUNT_TO_TOUCH_RE = re.compile(
    r"^(?:(?:one|1)\s+)?(?:two|2)\s+(?:three|3)\s+(?:and\s+)?touch(?:\s+it)?$"
)
_COUNTED_SLIDE_RE = re.compile(
    r"^(?:now\s+)?slide(?:\s+to)?(?:\s+the)?\s+(right|left)(?:\s+now)?\s+"
    r"(?:(?:one|1)\s+)?(?:two|2)\s+(?:three|3)\s+(?:and\s+)?touch(?:\s+it)?$"
)
_TOUCH_ON_TIME_RE = re.compile(r"^touch\s+it\s+on\s+time$")
_STEP_TOUCH_RE = re.compile(
    r"^step(?:\s+to)?(?:\s+the)?\s+(right|left)(?:\s+and)?\s+touch"
    r"(?:\s+(?:right|left))?$"
)
_VINE_TOUCH_RE = re.compile(
    r"^(?:grapevine|vine)(?:\s+to)?(?:\s+the)?\s+(right|left)"
    r"(?:\s+and)?\s+touch$"
)
_QUARTER_PIVOT_PATTERNS = (
    re.compile(
        r"^(?:make\s+(?:a\s+)?)?(?:quarter|one\s+quarter|1\s+4)\s+"
        r"pivot(?:\s+turn)?\s+(left|right)$"
    ),
    re.compile(
        r"^pivot(?:\s+(?:a\s+)?)?(?:quarter|one\s+quarter|1\s+4)\s+"
        r"(?:turn\s+)?(left|right)$"
    ),
)

_TEACHING_CONTEXT_RE = re.compile(
    r"\b(?:watch\s+my\s+feet|follow\s+my\s+feet|half\s+speed|slow\s+it\s+down|"
    r"new\s+folks|line\s+it\s+up|learn\s+the\s+dance)\b"
)

# These are common lyric phrases, not physical instructions.  Keeping the
# deny-list next to the command grammar makes the false-positive policy easy
# to audit and extend with real songs.
_FIGURATIVE_EXCLUSIONS = (
    re.compile(r"^kick\s+(?:off\s+)?(?:your|my|those)\s+(?:shoes|boots)\s+off$"),
    re.compile(r"^kick\s+(?:your|my|those)\s+(?:shoes|boots)\s+off$"),
    re.compile(r"^two\s+left\s+boots?\b"),
    re.compile(r"^wall\s+to\s+wall$"),
    re.compile(r"^take\s+it\s+home\b"),
)


def _normalise_text(value: Any) -> str:
    text = str(value or "").lower().replace("’", "'")
    return _SPACE_RE.sub(" ", " ".join(_TOKEN_RE.findall(text))).strip()


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if minimum <= number <= maximum else default


def _normalise_settings(project: dict, raw: dict | None) -> tuple[dict, list[dict]]:
    raw = raw if isinstance(raw, dict) else {}
    issues: list[dict] = []
    phrase = project.get("phrase") or {}
    dance_fit = phrase.get("dance_fit") or {}
    default_counts = _bounded_int(dance_fit.get("pattern_len"), 32, 4, 256)
    if default_counts % 4:
        default_counts = 32
    counts = _bounded_int(raw.get("counts", raw.get("pattern_len", default_counts)),
                          default_counts, 4, 256)
    if counts % 4:
        issues.append({
            "severity": "error", "code": "INVALID_PATTERN_COUNTS",
            "message": "Dance counts must be a positive multiple of four.",
        })
        counts = int(default_counts or 32)
        if counts < 4 or counts > 256 or counts % 4:
            counts = 32

    wall = str(raw.get("wall", "2"))
    if wall not in {"1", "2", "4"}:
        issues.append({
            "severity": "error", "code": "INVALID_WALL_COUNT",
            "message": "Walls must be 1, 2, or 4; the draft used 2 for review.",
        })
        wall = "2"
    turn_dir = str(raw.get("turn_dir", "L")).upper()
    if turn_dir not in {"L", "R"}:
        issues.append({
            "severity": "error", "code": "INVALID_TURN_DIRECTION",
            "message": "Turn direction must be L or R; the draft used L for review.",
        })
        turn_dir = "L"
    level = str(raw.get("level", "AB")).upper()
    if level not in SUPPORTED_LEVELS:
        issues.append({
            "severity": "error", "code": "INVALID_LEVEL",
            "message": "Unknown dance level; the draft used Absolute Beginner.",
        })
        level = "AB"
    start_foot = str(raw.get("start_foot", "R")).upper()
    if start_foot not in {"R", "L"}:
        issues.append({
            "severity": "error", "code": "INVALID_START_FOOT",
            "message": "Start foot must be R or L; the draft used R for review.",
        })
        start_foot = "R"

    selected = raw.get("selected_detection_ids")
    selected_ids = sorted({str(item) for item in selected}) \
        if isinstance(selected, (list, tuple, set)) else []
    rejected = raw.get("rejected_detection_ids")
    rejected_ids = sorted({str(item) for item in rejected}) \
        if isinstance(rejected, (list, tuple, set)) else []

    settings = {
        "counts": counts,
        "wall": wall,
        "turn_dir": turn_dir,
        "level": level,
        "allow_sync": _as_bool(raw.get("allow_sync")),
        "start_foot": start_foot,
        "seed": _bounded_int(raw.get("seed"), 0, -2_147_483_648, 2_147_483_647),
        "k": _bounded_int(raw.get("k"), 3, 1, 6),
        "experimental_mode": _as_bool(raw.get("experimental_mode")),
        "publication_mode": _as_bool(raw.get("publication_mode"), True),
        "include_custom_moves": _as_bool(raw.get("include_custom_moves")),
        "passage_start_count": _bounded_int(
            raw.get("passage_start_count"), 1, 1, counts),
        "anchor_min_confidence": max(0.0, min(
            1.0,
            (0.9 if _finite_float(raw.get("anchor_min_confidence")) is None
             else _finite_float(raw.get("anchor_min_confidence"))),
        )),
        "selected_detection_ids": selected_ids,
        "rejected_detection_ids": rejected_ids,
    }
    return settings, issues


def _caption_rows(project: dict) -> list[dict]:
    alignment = project.get("alignment") or {}
    rows = []
    for ordinal, raw in enumerate(alignment.get("captions") or [], start=1):
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or "").strip()
        if not text:
            continue
        start = _finite_float(raw.get("start"))
        end = _finite_float(raw.get("end"))
        confidence = _finite_float(raw.get("confidence"))
        caption_id = raw.get("id", ordinal)
        rows.append({
            # This index addresses the filtered ``rows`` collection below;
            # using the raw ordinal would break passage slicing if a malformed
            # empty caption was skipped.
            "position": len(rows),
            "id": caption_id,
            "text": text,
            "normalised": _normalise_text(text),
            "start": start,
            "end": end,
            "source_confidence": confidence,
            "timed": start is not None and end is not None and end > start >= 0,
            "label": raw.get("label"),
            "section_index": raw.get("section_index"),
        })
    return rows


def _seconds_per_beat(project: dict) -> float | None:
    analysis = project.get("analysis") or {}
    direct = _finite_float(analysis.get("seconds_per_beat"))
    if direct and direct > 0:
        return direct
    bpm = _finite_float(analysis.get("bpm"))
    if bpm and bpm > 0:
        return 60.0 / bpm
    beats = [_finite_float(item) for item in analysis.get("beat_times") or []]
    beats = [item for item in beats if item is not None]
    intervals = [right - left for left, right in zip(beats, beats[1:])
                 if right > left]
    if not intervals:
        return None
    intervals.sort()
    return intervals[len(intervals) // 2]


def _source_confidence(rows: list[dict]) -> float | None:
    values = [row["source_confidence"] for row in rows
              if row.get("source_confidence") is not None]
    return round(sum(values) / len(values), 3) if values else None


def _move_public(move_id: str, lead: str) -> dict | None:
    move = get_move(move_id)
    if move is None:
        return None
    variant = move.variant(lead)
    return {
        "move_id": move_id,
        "lead": lead,
        "name": variant["name"],
        "counts": variant["counts"],
        "start_foot": variant["start"],
        "end_foot": variant["end"],
        "rotation": variant["rot"],
    }


def _detection(rows: list[dict], move_id: str, lead: str,
               mapping_confidence: float, rule: str, evidence: str,
               *, anchor_eligible: bool) -> dict:
    move = _move_public(move_id, lead)
    first, last = rows[0], rows[-1]
    caption_ids = [row["id"] for row in rows]
    suffix = lead.lower() if lead else "either"
    detection_id = f"cue-{first['id']}-{last['id']}-{move_id}-{suffix}"
    payload = {
        "id": detection_id,
        "passage_id": None,
        "caption_ids": caption_ids,
        "text": " / ".join(row["text"] for row in rows),
        "start": first["start"],
        "end": last["end"],
        # Mapping confidence describes the lyric-to-move semantics.  The ASR
        # score remains separate so a perfect command can still show that its
        # audio timing needs an ear-check.
        "confidence": round(mapping_confidence, 3),
        "mapping_confidence": round(mapping_confidence, 3),
        "source_confidence": _source_confidence(rows),
        "status": "matched" if anchor_eligible else "needs_review",
        "anchor_eligible": bool(anchor_eligible),
        "requires_review": True,
        "rule": rule,
        "evidence": evidence,
        "move_id": move_id,
        "lead": lead,
        "move_name": move["name"] if move else None,
        "counts": move["counts"] if move else None,
        "start_foot": move["start_foot"] if move else None,
        "end_foot": move["end_foot"] if move else None,
        "rotation": move["rotation"] if move else None,
        "start_count": None,
        "end_count": None,
        "_first_position": first["position"],
        "_last_position": last["position"],
    }
    if move is None:
        payload.update({
            "status": "unsupported", "anchor_eligible": False,
            "evidence": f"{evidence} The mapped move is not in the vetted builder library.",
        })
    return payload


def _unresolved(row: dict, code: str, message: str) -> dict:
    return {
        "id": f"cue-{row['id']}-unresolved-{code.lower().replace('_', '-')}",
        "passage_id": None,
        "caption_ids": [row["id"]],
        "text": row["text"],
        "start": row["start"],
        "end": row["end"],
        "source_confidence": row.get("source_confidence"),
        "status": "unresolved",
        "reason_code": code,
        "message": message,
        "requires_review": True,
        "_first_position": row["position"],
        "_last_position": row["position"],
    }


def _is_figurative(text: str) -> bool:
    return any(pattern.search(text) for pattern in _FIGURATIVE_EXCLUSIONS)


def _detect_commands(captions: list[dict]) -> tuple[list[dict], list[dict]]:
    detections: list[dict] = []
    unresolved: list[dict] = []
    consumed: set[int] = set()

    # Adjacent two-line counted vines are the strongest grammar in songs such
    # as Holler Back: “Slide right” followed by “two, three, touch.”
    for index, row in enumerate(captions):
        if index in consumed or not row["timed"]:
            continue
        match = _SLIDE_DIRECTION_RE.fullmatch(row["normalised"])
        if not match or index + 1 >= len(captions):
            continue
        following = captions[index + 1]
        if (not following["timed"] or
                not _COUNT_TO_TOUCH_RE.fullmatch(following["normalised"])):
            continue
        direction = match.group(1)
        detections.append(_detection(
            [row, following], "vine_touch", "R" if direction == "right" else "L",
            0.97, "counted_vine_touch",
            f"Explicit {direction} slide followed by counts two, three, touch.",
            anchor_eligible=True,
        ))
        consumed.update({index, index + 1})

    for index, row in enumerate(captions):
        if index in consumed or not row["timed"]:
            continue
        text = row["normalised"]
        if _is_figurative(text):
            consumed.add(index)
            continue

        match = _COUNTED_SLIDE_RE.fullmatch(text)
        if match:
            direction = match.group(1)
            detections.append(_detection(
                [row], "vine_touch", "R" if direction == "right" else "L",
                0.97, "counted_vine_touch",
                f"Explicit {direction} slide with counts two, three, touch.",
                anchor_eligible=True,
            ))
            consumed.add(index)
            continue

        match = _VINE_TOUCH_RE.fullmatch(text)
        if match:
            direction = match.group(1)
            detections.append(_detection(
                [row], "vine_touch", "R" if direction == "right" else "L",
                0.94, "named_vine_touch",
                f"The complete vine direction and touch ending are explicit.",
                anchor_eligible=True,
            ))
            consumed.add(index)
            continue

        match = _STEP_TOUCH_RE.fullmatch(text)
        if match:
            direction = match.group(1)
            detections.append(_detection(
                [row], "step_touch", "R" if direction == "right" else "L",
                0.94, "explicit_step_touch",
                f"Step, direction, and weightless touch are all explicit.",
                anchor_eligible=True,
            ))
            consumed.add(index)
            continue

        pivot_match = next((pattern.fullmatch(text)
                            for pattern in _QUARTER_PIVOT_PATTERNS
                            if pattern.fullmatch(text)), None)
        if pivot_match:
            direction = pivot_match.group(1)
            # The canonical R-lead pivot rotates left; mirroring it rotates
            # right.  This rule states the relationship explicitly instead of
            # inferring it from a direction word at run time.
            lead = "R" if direction == "left" else "L"
            detections.append(_detection(
                [row], "pivot_quarter", lead, 0.96,
                "explicit_quarter_pivot",
                f"Quarter-pivot type and {direction} turn direction are explicit.",
                anchor_eligible=True,
            ))
            consumed.add(index)
            continue

        if text in {"rocking chair", "do a rocking chair"}:
            detections.append(_detection(
                [row], "rocking_chair", "R", 0.93,
                "exact_named_move", "Exact vetted move name.",
                anchor_eligible=True,
            ))
            consumed.add(index)
            continue
        if text in {"jazz box", "do a jazz box"}:
            detections.append(_detection(
                [row], "jazz_box", "R", 0.93,
                "exact_named_move", "Exact vetted move name.",
                anchor_eligible=True,
            ))
            consumed.add(index)
            continue

        # “Slide right / touch it on time” is useful evidence but lacks the
        # counted cross-behind mechanics. Keep it selectable, never pinned by
        # default.
        match = _SLIDE_DIRECTION_RE.fullmatch(text)
        if match and index + 1 < len(captions):
            following = captions[index + 1]
            if (following["timed"] and
                    _TOUCH_ON_TIME_RE.fullmatch(following["normalised"])):
                direction = match.group(1)
                detections.append(_detection(
                    [row, following], "vine_touch",
                    "R" if direction == "right" else "L", 0.72,
                    "slide_touch_inference",
                    "Direction and touch are present, but the middle vine steps are not stated.",
                    anchor_eligible=False,
                ))
                consumed.update({index, index + 1})

    # Preserve command-like but mechanically incomplete language as review
    # rows.  This is also where the dangerous heel-strut/stomp-weight fork is
    # made explicit instead of guessed.
    for index, row in enumerate(captions):
        if index in consumed or not row["timed"]:
            continue
        text = row["normalised"]
        if _is_figurative(text):
            continue
        if text.startswith("heel") and "stomp" in text:
            unresolved.append(_unresolved(
                row, "HEEL_STOMP_AMBIGUOUS",
                "Heel touches and stomps need exact feet and weight changes; a heel strut is not equivalent.",
            ))
        elif re.fullmatch(r"(?:now\s+)?roll\s+it\s+(?:down|low)(?:\s+slow)?", text):
            unresolved.append(_unresolved(
                row, "ROLL_AMBIGUOUS",
                "A body roll has no vetted count or foot mechanics in the builder library.",
            ))
        elif re.fullmatch(r"(?:hit\s+your\s+turn|take\s+that\s+corner|"
                          r"make\s+the\s+turn|turn(?:\s+left|\s+right)?)", text):
            unresolved.append(_unresolved(
                row, "TURN_AMBIGUOUS",
                "The lyric does not specify a vetted turn type, degree, and direction.",
            ))
        elif re.fullmatch(r"slide\s+it(?:\s+on)?\s+back", text):
            unresolved.append(_unresolved(
                row, "SLIDE_BACK_AMBIGUOUS",
                "The lyric does not say which foot leads or whether the slide takes weight.",
            ))
        elif text.startswith("stomp"):
            unresolved.append(_unresolved(
                row, "STOMP_WEIGHT_AMBIGUOUS",
                "A stomp may take weight or be a stomp-up; the lyric does not say which.",
            ))
        elif text.startswith("heel"):
            unresolved.append(_unresolved(
                row, "HEEL_ACTION_AMBIGUOUS",
                "A heel touch is not automatically a weighted heel strut.",
            ))

    detections.sort(key=lambda item: (item["start"], item["end"], item["id"]))
    unresolved.sort(key=lambda item: (item["start"], item["end"], item["id"]))
    return detections, unresolved


def _build_passages(captions: list[dict], detections: list[dict],
                    unresolved: list[dict], seconds_per_beat: float | None) -> list[dict]:
    cues = [(item["_first_position"], item["_last_position"], item)
            for item in detections + unresolved]
    cues.sort(key=lambda item: (item[0], item[1], item[2]["id"]))
    if not cues:
        return []

    max_time_gap = max(3.0, (seconds_per_beat or 0.5) * 5.0)
    groups: list[list[tuple[int, int, dict]]] = []
    for cue in cues:
        if not groups:
            groups.append([cue])
            continue
        previous = groups[-1][-1]
        previous_end = _finite_float(previous[2].get("end"))
        current_start = _finite_float(cue[2].get("start"))
        caption_gap = cue[0] - previous[1] - 1
        time_gap = ((current_start - previous_end)
                    if current_start is not None and previous_end is not None
                    else float("inf"))
        if caption_gap <= 1 and time_gap <= max_time_gap:
            groups[-1].append(cue)
        else:
            groups.append([cue])

    passages = []
    for group in groups:
        first_position = group[0][0]
        last_position = group[-1][1]
        context_start = first_position
        teaching_context = False
        for position in range(first_position - 1, max(-1, first_position - 5), -1):
            if position < 0:
                break
            candidate = captions[position]
            if _TEACHING_CONTEXT_RE.search(candidate["normalised"]):
                context_start = position
                teaching_context = True
                break

        passage_id = (f"passage-{captions[first_position]['id']}-"
                      f"{captions[last_position]['id']}")
        detection_rows = [cue[2] for cue in group if "move_id" in cue[2]]
        unresolved_rows = [cue[2] for cue in group if "reason_code" in cue[2]]
        for item in detection_rows + unresolved_rows:
            item["passage_id"] = passage_id

        anchorable = [item for item in detection_rows if item["anchor_eligible"]]
        directions = {(item["move_id"], item["lead"]) for item in anchorable}
        mirrored_vines = ({("vine_touch", "R"), ("vine_touch", "L")}
                          <= directions)
        score = (len(anchorable) * 100 + len(detection_rows) * 20
                 + (160 if teaching_context else 0)
                 + (80 if mirrored_vines else 0)
                 - len(unresolved_rows) * 4)
        context_rows = captions[context_start:last_position + 1]
        passages.append({
            "id": passage_id,
            "start": context_rows[0]["start"],
            "end": context_rows[-1]["end"],
            "command_start": captions[first_position]["start"],
            "command_end": captions[last_position]["end"],
            "caption_ids": [row["id"] for row in context_rows],
            "text": "\n".join(row["text"] for row in context_rows),
            "detection_ids": [item["id"] for item in detection_rows],
            "unresolved_ids": [item["id"] for item in unresolved_rows],
            "matched_moves": len(detection_rows),
            "high_confidence_moves": len(anchorable),
            "matched_counts": sum(item.get("counts") or 0 for item in anchorable),
            "teaching_context": teaching_context,
            "mirrored_vine_pair": mirrored_vines,
            "score": score,
            "recommended": False,
        })

    passages.sort(key=lambda item: (item["start"], item["id"]))
    recommended = max(
        passages,
        key=lambda item: (item["score"], item["high_confidence_moves"],
                          item["matched_moves"], -float(item["start"] or 0)),
    )
    recommended["recommended"] = True
    recommended["recommendation_reason"] = (
        "Teaching language plus a counted right/left move pair gives the clearest review draft."
        if recommended["teaching_context"] and recommended["mirrored_vine_pair"]
        else "This passage contains the strongest mechanically complete lyric commands."
    )
    return passages


def _place_anchors(selected_passage: dict, detections: list[dict], settings: dict,
                   seconds_per_beat: float | None) -> tuple[list[dict], list[dict]]:
    issues = []
    passage_detections = [item for item in detections
                          if item.get("passage_id") == selected_passage["id"]]
    passage_detections.sort(key=lambda item: (item["start"], item["end"], item["id"]))
    explicitly_selected = set(settings.get("selected_detection_ids") or [])
    explicitly_rejected = set(settings.get("rejected_detection_ids") or [])
    if explicitly_selected:
        selected = [item for item in passage_detections
                    if item["id"] in explicitly_selected and
                    item["id"] not in explicitly_rejected]
    else:
        selected = [item for item in passage_detections
                    if item["anchor_eligible"] and
                    item["mapping_confidence"] >= settings["anchor_min_confidence"] and
                    item["id"] not in explicitly_rejected]

    anchors = []
    prior_detection = None
    prior_start = None
    first_detection = selected[0] if selected else None
    for item in selected:
        if not item.get("counts"):
            continue
        if prior_detection is None:
            start_count = settings["passage_start_count"]
        else:
            packed_start = int(prior_start + prior_detection["counts"])
            seam_gap = (_finite_float(item.get("start")) or 0) - \
                (_finite_float(prior_detection.get("end")) or 0)
            # Adjacent counted commands should remain adjacent even when ASR
            # split points wobble around the beat.  Otherwise retain the
            # observed beat distance so an actual lyric gap remains a gap.
            if seam_gap <= (seconds_per_beat or 0.5) * 1.25:
                start_count = packed_start
            else:
                observed = settings["passage_start_count"] + int(round(
                    ((_finite_float(item.get("start")) or 0) -
                     (_finite_float(first_detection.get("start")) or 0)) /
                    (seconds_per_beat or 0.5)
                ))
                start_count = max(packed_start, observed)
        end_count = start_count + int(item["counts"]) - 1
        item["start_count"] = start_count
        item["end_count"] = end_count

        problem = None
        if start_count < 1 or end_count > settings["counts"]:
            problem = "The detected move falls outside the selected dance-count pattern."
        elif (start_count - 1) // 8 != (end_count - 1) // 8:
            problem = "The detected move would straddle an 8-count block boundary."
        elif anchors and start_count <= anchors[-1]["end_count"]:
            problem = "The detected move overlaps another lyric-locked move."
        if problem:
            item["status"] = "conflict"
            item["anchor_eligible"] = False
            issues.append({
                "severity": "warn", "code": "LYRIC_ANCHOR_CONFLICT",
                "detection_id": item["id"], "message": problem,
            })
        else:
            anchors.append({
                "start_count": start_count,
                "end_count": end_count,
                "counts": int(item["counts"]),
                "move_id": item["move_id"],
                "lead": item["lead"],
                "detection_id": item["id"],
                "caption_ids": list(item["caption_ids"]),
                "lyric_text": item["text"],
                "confidence": item["mapping_confidence"],
            })
        prior_detection = item
        prior_start = start_count
    return anchors, issues


def _gap_rows(anchors: list[dict], total_counts: int, filled: bool) -> list[dict]:
    gaps = []
    cursor = 1
    for anchor in sorted(anchors, key=lambda item: item["start_count"]):
        if cursor < anchor["start_count"]:
            gaps.append({
                "start_count": cursor, "end_count": anchor["start_count"] - 1,
                "counts": anchor["start_count"] - cursor,
                "status": "filled" if filled else "unfilled",
            })
        cursor = max(cursor, anchor["end_count"] + 1)
    if cursor <= total_counts:
        gaps.append({
            "start_count": cursor, "end_count": total_counts,
            "counts": total_counts - cursor + 1,
            "status": "filled" if filled else "unfilled",
        })
    return gaps


def _candidate_preserves_anchors(candidate: dict, anchors: list[dict],
                                 settings: dict) -> tuple[bool, dict | None]:
    moves = candidate.get("moves") if isinstance(candidate, dict) else None
    if not isinstance(moves, list) or not moves:
        return False, None
    positions = {}
    cursor = 1
    for move in moves:
        if not isinstance(move, dict):
            return False, None
        counts = _bounded_int(move.get("counts"), 0, 1, 256)
        if not counts:
            return False, None
        positions[cursor] = move
        cursor += counts
    if cursor - 1 != settings["counts"]:
        return False, None
    for anchor in anchors:
        move = positions.get(anchor["start_count"])
        if (not move or move.get("move_id") != anchor["move_id"] or
                (anchor.get("lead") and move.get("lead") != anchor["lead"])):
            return False, None
    try:
        report = assembler_engine.validate_sequence(
            moves, settings["counts"], settings["wall"], settings["turn_dir"],
            start_foot=settings["start_foot"],
            bpm=settings.get("bpm"),
        )
    except Exception:
        return False, None
    return bool(report.get("valid")), report


def _fill_candidates(anchors: list[dict], settings: dict) -> tuple[list[dict], list[dict]]:
    issues = []
    solver = getattr(assembler_engine, "assemble_anchored", None)
    if not callable(solver):
        return [], [{
            "severity": "warn", "code": "GAP_FILLER_UNAVAILABLE",
            "message": "The lyric moves were detected, but the safe anchored gap filler is unavailable.",
        }]
    required_slots = [{
        "start_count": item["start_count"],
        "move_id": item["move_id"],
        "lead": item["lead"],
    } for item in anchors]
    try:
        result = solver(
            required_slots,
            total_counts=settings["counts"],
            wall=settings["wall"],
            turn_dir=settings["turn_dir"],
            level=settings["level"],
            allow_sync=settings["allow_sync"],
            start_foot=settings["start_foot"],
            seed=settings["seed"],
            k=settings["k"],
            bpm=settings.get("bpm"),
            experimental_mode=settings["experimental_mode"],
            publication_mode=settings["publication_mode"],
            include_custom_moves=settings["include_custom_moves"],
        )
    except assembler_engine.AssemblyError as exc:
        detail = exc.to_dict()
        return [], [{
            "severity": "warn", "code": detail.get("error", "ANCHORS_UNFILLABLE"),
            "message": detail.get("message", str(exc)),
            "details": detail.get("details") or {},
        }]
    except Exception as exc:
        return [], [{
            "severity": "warn", "code": "GAP_FILL_FAILED",
            "message": f"The lyric anchors were kept, but gap filling could not finish: {exc}",
        }]

    raw_candidates = result.get("candidates", []) if isinstance(result, dict) else result
    if not isinstance(raw_candidates, list):
        raw_candidates = []
    candidates = []
    anchor_by_count = {item["start_count"]: item for item in anchors}
    for index, raw in enumerate(raw_candidates, start=1):
        candidate = copy.deepcopy(raw) if isinstance(raw, dict) else {}
        valid, report = _candidate_preserves_anchors(candidate, anchors, settings)
        if not valid:
            issues.append({
                "severity": "warn", "code": "INVALID_FILL_CANDIDATE",
                "message": f"Gap-fill candidate {index} did not preserve every lyric anchor and was discarded.",
            })
            continue
        candidate["validation"] = report
        provenance = candidate.get("provenance")
        if not isinstance(provenance, list) or len(provenance) != len(candidate["moves"]):
            provenance = []
            cursor = 1
            for move in candidate["moves"]:
                anchor = anchor_by_count.get(cursor)
                provenance.append({
                    "kind": "lyric" if anchor else "filler",
                    **({"detection_id": anchor["detection_id"],
                        "lyric_text": anchor["lyric_text"]} if anchor else {}),
                })
                cursor += int(move["counts"])
        else:
            enriched = []
            cursor = 1
            for entry, move in zip(provenance, candidate["moves"]):
                value = dict(entry) if isinstance(entry, dict) else {"kind": str(entry)}
                anchor = anchor_by_count.get(cursor)
                if anchor:
                    value.update({
                        "kind": "lyric", "detection_id": anchor["detection_id"],
                        "lyric_text": anchor["lyric_text"],
                    })
                else:
                    value.setdefault("kind", "filler")
                enriched.append(value)
                cursor += int(move["counts"])
            provenance = enriched
        candidate["provenance"] = provenance
        candidate["anchors"] = copy.deepcopy(anchors)
        candidate["gaps"] = _gap_rows(anchors, settings["counts"], filled=True)
        candidates.append(candidate)
    if not candidates and not issues:
        issues.append({
            "severity": "warn", "code": "NO_FILL_CANDIDATES",
            "message": "No complete sequence could safely fill the counts around these lyric moves.",
        })
    return candidates, issues


def _fingerprint(project: dict, settings: dict) -> dict:
    alignment = project.get("alignment") or {}
    analysis = project.get("analysis") or {}
    phrase = project.get("phrase") or {}
    source = {
        "algorithm": ALGORITHM_VERSION,
        "song": {
            "path": (project.get("song") or {}).get("path"),
            "filename": (project.get("song") or {}).get("filename"),
        },
        "alignment": {
            "mode": alignment.get("mode"),
            "source_file_signature": alignment.get("source_file_signature"),
            "source_analysis_signature": alignment.get("source_analysis_signature"),
            "captions": [{
                key: row.get(key) for key in
                ("id", "text", "start", "end", "confidence", "status")
            } for row in alignment.get("captions") or [] if isinstance(row, dict)],
        },
        "analysis": {
            "bpm": analysis.get("bpm"),
            "seconds_per_beat": analysis.get("seconds_per_beat"),
            "beat_times": analysis.get("beat_times") or [],
            "octave_alternates": analysis.get("octave_alternates") or [],
        },
        "dance_fit": {
            "status": phrase.get("status"),
            "pattern_len": (phrase.get("dance_fit") or {}).get("pattern_len"),
            "anchor": (phrase.get("dance_fit") or {}).get("anchor"),
        },
        "settings": settings,
    }
    encoded = json.dumps(source, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, default=str).encode("utf-8")
    return {
        "algorithm": ALGORITHM_VERSION,
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _public_rows(rows: list[dict]) -> list[dict]:
    return [{key: value for key, value in row.items() if not key.startswith("_")}
            for row in rows]


def build_draft(project: dict, settings: dict, passage_id: str | None = None,
                fill_gaps: bool = True) -> dict:
    """Build a deterministic, review-only choreography proposal from lyrics.

    The returned object is safe to persist, but this function never changes
    ``project``.  ``selected_detection_ids`` in settings lets a future review
    UI explicitly opt a medium-confidence proposal into the anchor set;
    without that choice, only high-confidence mechanically complete commands
    are pinned.
    """
    project = project if isinstance(project, dict) else {}
    normalised, issues = _normalise_settings(project, settings)
    analysis = project.get("analysis") or {}
    normalised["bpm"] = _finite_float(analysis.get("bpm"))
    fingerprint = _fingerprint(project, normalised)
    captions = _caption_rows(project)
    timed_captions = [row for row in captions if row["timed"]]
    seconds_per_beat = _seconds_per_beat(project)

    if not captions:
        issues.append({
            "severity": "error", "code": "NO_TIMED_LYRICS",
            "message": "Scan or align the lyrics before building from lyric moves.",
        })
    elif not timed_captions:
        issues.append({
            "severity": "error", "code": "NO_TIMED_LYRICS",
            "message": "The lyric rows have no dependable audio times; align them before building.",
        })
    if not seconds_per_beat:
        issues.append({
            "severity": "warn", "code": "NO_BEAT_GRID",
            "message": "No dependable beat duration is available, so lyric placement needs extra review.",
        })

    detections, unresolved = _detect_commands(captions)
    passages = _build_passages(captions, detections, unresolved, seconds_per_beat)
    selected_passage = None
    if passage_id is not None:
        selected_passage = next((row for row in passages if row["id"] == passage_id), None)
        if selected_passage is None:
            issues.append({
                "severity": "error", "code": "PASSAGE_NOT_FOUND",
                "message": "The selected lyric passage no longer exists. Review the latest detections.",
            })
    elif passages:
        selected_passage = next((row for row in passages if row["recommended"]), passages[0])

    anchors = []
    candidates = []
    if selected_passage is not None:
        anchors, anchor_issues = _place_anchors(
            selected_passage, detections, normalised, seconds_per_beat)
        issues.extend(anchor_issues)
        selected_unresolved = [item for item in unresolved
                               if item.get("passage_id") == selected_passage["id"]]
        selected_review_matches = [item for item in detections
                                   if item.get("passage_id") == selected_passage["id"] and
                                   not item.get("anchor_eligible")]
        if selected_unresolved:
            issues.append({
                "severity": "warn", "code": "UNRESOLVED_LYRIC_COMMANDS",
                "message": (f"{len(selected_unresolved)} command-like lyric cue(s) need a "
                            "human move/count decision and were not used as footwork."),
            })
        if selected_review_matches:
            issues.append({
                "severity": "info", "code": "OPTIONAL_LYRIC_MATCHES",
                "message": (f"{len(selected_review_matches)} possible move match(es) were "
                            "left unlocked for review."),
            })
        if not anchors:
            issues.append({
                "severity": "warn", "code": "NO_SAFE_LYRIC_ANCHORS",
                "message": "This passage has no mechanically complete lyric moves safe to pin automatically.",
            })
        elif fill_gaps:
            candidates, fill_issues = _fill_candidates(anchors, normalised)
            issues.extend(fill_issues)
        elif _gap_rows(anchors, normalised["counts"], filled=False):
            issues.append({
                "severity": "info", "code": "GAPS_LEFT_OPEN",
                "message": "Lyric moves were placed, and the remaining counts were intentionally left open.",
            })

    if not passages and captions:
        issues.append({
            "severity": "warn", "code": "NO_COMMAND_PASSAGES",
            "message": "No mechanically complete dance-command passage was found in the timed lyrics.",
        })

    alignment = project.get("alignment") or {}
    alignment_confidence = _finite_float((alignment.get("summary") or {}).get("confidence"))
    if alignment_confidence is not None and alignment_confidence < 0.6:
        issues.append({
            "severity": "warn", "code": "LOW_TRANSCRIPT_CONFIDENCE",
            "message": "The timed lyric copy is uncertain; verify every detected command against the audio.",
        })
    if analysis.get("octave_alternates"):
        issues.append({
            "severity": "warn", "code": "OCTAVE_AMBIGUOUS",
            "message": "The song has a half/double-time alternative; confirm the count grid on the floor.",
        })
    issues.append({
        "severity": "info", "code": "HUMAN_REVIEW_REQUIRED",
        "message": "This is a review draft. Confirm lyric meaning, counts, feet, timing, and floor feel before saving it as the dance.",
    })

    gap_rows = _gap_rows(
        anchors, normalised["counts"], filled=bool(fill_gaps and candidates))
    selected_id = selected_passage["id"] if selected_passage else None
    selected_detection_count = sum(
        1 for row in detections if row.get("passage_id") == selected_id)
    selected_unresolved_count = sum(
        1 for row in unresolved if row.get("passage_id") == selected_id)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "REVIEW",
        "source_fingerprint": fingerprint,
        "settings": normalised,
        "passages": copy.deepcopy(passages),
        "selected_passage_id": selected_id,
        "detections": _public_rows(detections),
        "unresolved": _public_rows(unresolved),
        "anchors": copy.deepcopy(anchors),
        "gaps": gap_rows,
        "candidates": candidates,
        "issues": issues,
        "summary": {
            "passage_count": len(passages),
            "detection_count": len(detections),
            "selected_detection_count": selected_detection_count,
            "unresolved_count": len(unresolved),
            "selected_unresolved_count": selected_unresolved_count,
            "anchored_moves": len(anchors),
            "anchored_counts": sum(item["counts"] for item in anchors),
            "total_counts": normalised["counts"],
            "gap_counts": sum(item["counts"] for item in gap_rows),
            "candidate_count": len(candidates),
            "fill_gaps_requested": bool(fill_gaps),
        },
    }
