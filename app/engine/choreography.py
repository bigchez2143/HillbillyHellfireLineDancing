"""Pure S03 choreography compiler; no filesystem, catalog, or audio dependency.

Version 1 input uses ``parts[{id, moves}]`` and ordered
``routine[{id, part_id, repeat?, end_after_counts?, reason?, overrides?}]``.
Tags/endings are ordinary parts with kind ``tag``/``ending``. A restart is an
explicit elapsed-count boundary on ONE routine entry; the next entry names
what follows. Split entries to change only a particular numbered occurrence.
Never identify an occurrence by its facing wall.

Moves contain exact ``duration_counts`` and sequential ``events`` (optional
``offset_counts``, ``duration_counts``, ``text``, ``support_before``,
``support_after``, ``rotation_deg``, ``facing_before_deg``, ``facing_after_deg``).
Supports are L/R/both/neither/unknown; entry may say any and exit may say same.
Absent mechanics are unknown, not implicit holds. Count positions are zero
based, ends exclusive; ``pickup_counts`` places the start before count zero.
Fractions accept integers, finite decimals, strings, or numerator/denominator
objects and are serialized as reduced strings. No float accumulation is used.

Legacy concrete move dictionaries (counts/start/end/rot/lines) are accepted as
one aggregate event each, without inventing their internal weight transfers.
A list of these is shorthand for one nonrepeating A part. Frozen snapshots may
be supplied as a mapping keyed by snapshot_id; no live catalog lookup occurs.
"""

from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import math


SCHEMA_VERSION = 1
MAX_EVENTS = 20000
MAX_REPEATS = 1000
SUPPORTS = {"L", "R", "both", "neither", "unknown"}


def exact_count(value):
    """Parse an exact rational without accepting booleans or nonfinite floats."""
    if isinstance(value, bool) or value is None:
        raise ValueError("Use a number or fraction such as 1/2.")
    if isinstance(value, Fraction):
        return value
    if isinstance(value, dict):
        numerator, denominator = value.get("numerator"), value.get("denominator")
        if type(numerator) is not int or type(denominator) is not int:
            raise ValueError("Fraction numerator and denominator must be integers.")
        return Fraction(numerator, denominator)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Counts must be finite.")
        value = str(value)
    if not isinstance(value, (int, str)):
        raise ValueError("Use a number or fraction such as 1/2.")
    if len(str(value)) > 100:
        raise ValueError("This count value is too large.")
    return Fraction(value)


def format_count(position, group_counts=None):
    """Teaching label for a zero-based onset; thirds remain explicit fractions."""
    position = exact_count(position)
    if position < 0:
        return "pickup " + str(-position)
    if group_counts is not None:
        group = exact_count(group_counts)
        if group <= 0:
            raise ValueError("Display grouping must be positive.")
        position %= group
    whole = position.numerator // position.denominator
    rest = position - whole
    suffix = {Fraction(0): "", Fraction(1, 4): "e", Fraction(1, 2): "&", Fraction(3, 4): "a"}
    return str(whole + 1) + suffix.get(rest, "+" + str(rest))


def _json_value(value):
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _free(support):
    return {"L": "R", "R": "L"}.get(support, "unknown")


def _state(support, facing):
    return {"support": support, "free_foot": _free(support),
            "facing_deg": None if facing is None else str(facing % 360)}


def _support_for_free(free):
    return {"L": "R", "R": "L"}.get(free, "unknown")


class _Compiler:
    def __init__(self, document, snapshots):
        self.document = deepcopy(document)
        self.snapshots = deepcopy(snapshots or {})
        self.issues = []
        self.events = []
        self.occurrences = []
        self.group = Fraction(8)
        self.position = Fraction(0)
        self.support, self.facing = "L", Fraction(0)

    def issue(self, code, message, action, severity="error", **where):
        anchor = {key: where[key] for key in ("occurrence_id", "event_id", "source_event_id", "part_id", "move_id", "routine_id", "field", "boundary") if key in where}
        digest = hashlib.sha256(json.dumps(_json_value([code, anchor, message]), sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
        identifier = "issue-" + digest
        duplicates = sum(issue["id"] == identifier or issue["id"].startswith(identifier + "-") for issue in self.issues)
        if duplicates:
            identifier += f"-{duplicates + 1}"
        self.issues.append({"id": identifier,
                            "code": code, "severity": severity,
                            "message": message, "action": action, **_json_value(where)})

    def number(self, value, field, default=Fraction(0), minimum=None, **where):
        try:
            result = exact_count(value)
            if minimum is not None and result < minimum:
                raise ValueError(f"{field} must be at least {minimum}.")
            return result
        except (ValueError, ZeroDivisionError, OverflowError) as exc:
            self.issue("INVALID_NUMBER", f"Invalid {field}: {exc}",
                       f"Enter an exact value for {field}.", field=field, **where)
            return default

    def identity(self, raw, fallback, used, kind, **where):
        identifier = str(raw or fallback)
        if identifier in used:
            self.issue("DUPLICATE_ID", f"Duplicate {kind} ID {identifier}.",
                       "Give each sibling a distinct stable ID.", **where)
            stem, suffix = identifier, len(used) + 1
            while identifier in used:
                identifier = f"{stem}~{suffix}"
                suffix += 1
        used.add(identifier)
        return identifier

    def support_value(self, value, field, extra=(), **where):
        if value is None:
            return "unknown"
        aliases = {"left": "L", "right": "R", "l": "L", "r": "R", "SAME": "same", "F": "any"}
        value = aliases.get(str(value), str(value))
        if value not in SUPPORTS | set(extra):
            self.issue("INVALID_SUPPORT", f"Unsupported {field}: {value}.",
                       "Choose left, right, both, neither, or unknown support.", **where)
            return "unknown"
        return value

    def prepare_move(self, raw, index, used, part_id):
        if not isinstance(raw, dict):
            self.issue("INVALID_MOVE", "A movement occurrence must be an object.",
                       "Replace this row with a movement definition.", part_id=part_id)
            raw = {}
        mid = self.identity(raw.get("id"), f"move-{index + 1}", used, "move", part_id=part_id)
        loc = {"part_id": part_id, "move_id": mid}
        definition = raw
        sid = raw.get("snapshot_id")
        if sid is not None:
            snapshot = self.snapshots.get(str(sid)) if isinstance(self.snapshots, dict) else None
            if not isinstance(snapshot, dict):
                # Normalized documents embed the exact resolved events and keep
                # snapshot_id as provenance, so they are portable independently.
                if not isinstance(raw.get("events"), list):
                    self.issue("SNAPSHOT_MISSING", f"Snapshot {sid} is unavailable.",
                               "Restore the frozen move snapshot; do not substitute a live definition.", **loc)
                snapshot = {}
            definition = {**snapshot, **raw}
        elif isinstance(raw.get("definition"), dict):
            definition = {**raw["definition"], **{k: v for k, v in raw.items() if k != "definition"}}
        duration = self.number(definition.get("duration_counts", definition.get("counts", 0)),
                               "duration_counts", minimum=0, **loc)
        event_rows = definition.get("events")
        if event_rows is None:
            if "duration_counts" not in definition and "counts" not in definition:
                self.issue("DURATION_MISSING", "This move has no duration or timed events.",
                           "Enter its count duration; use explicit zero only for an instant marker.", **loc)
            legacy = any(key in definition for key in ("start", "end", "rot", "lines"))
            start, end = definition.get("start"), definition.get("end")
            event_rows = [{"id": "event-1", "duration_counts": str(duration),
                           "text": definition.get("text", definition.get("name", "Unnamed move")),
                           "support_before": ("any" if start == "F" else _support_for_free(start)) if legacy else definition.get("support_before"),
                           "support_after": ("same" if end == "SAME" else _support_for_free(end)) if legacy else definition.get("support_after"),
                           "rotation_deg": definition.get("rot") if legacy else definition.get("rotation_deg"),
                           "lines": deepcopy(definition.get("lines", []))}]
            for key in ("facing_before_deg", "facing_after_deg"):
                if key in definition:
                    event_rows[0][key] = definition[key]
        if not isinstance(event_rows, list) or not event_rows:
            self.issue("EMPTY_EVENTS", "The movement has no event definitions.",
                       "Add an event with duration and instructions.", **loc)
            event_rows = []
        cursor, prepared, event_ids = Fraction(0), [], set()
        for event_index, event in enumerate(event_rows[:MAX_EVENTS]):
            if not isinstance(event, dict):
                self.issue("INVALID_EVENT", "An event must be an object.", "Correct this event row.", **loc)
                continue
            eid = self.identity(event.get("id"), f"event-{event_index + 1}", event_ids, "event", **loc)
            event_loc = {**loc, "source_event_id": eid}
            if "duration_counts" not in event and event.get("instant") is not True:
                self.issue("DURATION_MISSING", "This event has no count duration.",
                           "Enter duration_counts, or explicitly mark the event instant.", **event_loc)
            offset = self.number(event.get("offset_counts", str(cursor)), "offset_counts", minimum=0, **event_loc)
            span = self.number(event.get("duration_counts", 0), "duration_counts", minimum=0, **event_loc)
            if offset != cursor:
                code = "EVENT_OVERLAP" if offset < cursor else "EVENT_GAP"
                self.issue(code, "Movement events must explicitly cover time in order.",
                           "Split overlapping actions or add an explicit hold for the gap.", **event_loc)
            prepared_event = {"id": eid, "offset_counts": str(offset), "duration_counts": str(span),
                              "text": str(event.get("text", event.get("action_text", ""))),
                              "support_before": self.support_value(event.get("support_before"), "entry support", ("any",), **event_loc),
                              "support_after": self.support_value(event.get("support_after"), "exit support", ("same",), **event_loc)}
            for key in ("rotation_deg", "facing_before_deg", "facing_after_deg"):
                value = event.get(key)
                prepared_event[key] = None if value is None else str(self.number(value, key, **event_loc))
            for key in ("lines", "moving_foot", "travel", "callout", "notes"):
                if key in event:
                    prepared_event[key] = deepcopy(event[key])
            prepared.append(prepared_event)
            cursor = offset + span
        if len(event_rows) > MAX_EVENTS:
            self.issue("EXPANSION_LIMIT", "This move has too many events.", "Split the document into smaller routines.", **loc)
        if "duration_counts" not in definition and "counts" not in definition:
            duration = cursor
        if duration != cursor:
            self.issue("MOVE_COUNT_MISMATCH", f"Events span {cursor} counts; move declares {duration}.",
                       "Correct the duration or explicit event coverage.", expected=str(duration), actual=str(cursor), **loc)
        result = {"id": mid, "name": str(definition.get("name", mid)),
                  "definition_id": definition.get("definition_id", definition.get("move_id")),
                  "duration_counts": str(duration), "events": prepared}
        if sid is not None:
            result["snapshot_id"] = str(sid)
        return result

    def apply_state(self, event, loc, repeat_boundary=False):
        before = _state(self.support, self.facing)
        required = event["support_before"]
        prefix = "REPEAT_" if repeat_boundary else ""
        if required == "unknown":
            self.issue(prefix + "ENTRY_UNVERIFIED", "The entry support rule is unspecified.",
                       "Review and declare the entry support rule.", severity="unverified", **loc)
        elif required != "any":
            if self.support == "unknown":
                self.issue(prefix + "ENTRY_UNVERIFIED", "Previous support is unknown; this transition cannot be checked.",
                           "Review the preceding movement's exit support.", severity="unverified", expected=required, **loc)
            elif required != self.support:
                self.issue(prefix + "SUPPORT_MISMATCH", f"Move needs {required} support, but previous movement ends on {self.support}.",
                           "Change the transition, lead variant, or declared weight transfer.", expected=required, actual=self.support, **loc)
        constraint = event.get("facing_before_deg")
        if constraint is not None:
            expected = exact_count(constraint) % 360
            if self.facing is None:
                self.issue(prefix + "FACING_UNVERIFIED", "Entry facing cannot be checked after an unknown turn.",
                           "Review the preceding turn or declare an absolute facing.", severity="unverified", **loc)
            elif expected != self.facing % 360:
                self.issue(prefix + "FACING_MISMATCH", f"Move requires facing {expected}°, currently {self.facing % 360}°.",
                           "Correct the turn or this occurrence's facing requirement.", **loc)
        after = event["support_after"]
        if after != "same":
            self.support = after
        if self.support == "unknown":
            self.issue(prefix + "SUPPORT_UNVERIFIED", "Exit support remains unknown.",
                       "Review the weight transfer; do not mark this movement mechanically verified.", severity="unverified", **loc)
        rotation, absolute = event.get("rotation_deg"), event.get("facing_after_deg")
        relative = None if self.facing is None or rotation is None else (self.facing + exact_count(rotation)) % 360
        if absolute is not None:
            absolute = exact_count(absolute) % 360
            if relative is not None and relative != absolute:
                self.issue(prefix + "TURN_CONTRADICTION", "Relative turn and absolute exit facing disagree.",
                           "Correct one of the two facing claims.", **loc)
            self.facing = absolute
        else:
            self.facing = relative
        if self.facing is None:
            self.issue(prefix + "FACING_UNVERIFIED", "Exit facing is unknown.",
                       "Declare the reviewed turn, including zero for no turn, or absolute facing.", severity="unverified", **loc)
        return before, _state(self.support, self.facing)

    def run(self):
        doc = self.document
        if isinstance(doc, list):
            doc = {"schema_version": 1, "parts": [{"id": "A", "moves": doc}],
                   "routine": [{"id": "routine-A", "part_id": "A"}], "repeat": False}
        if not isinstance(doc, dict):
            self.issue("INVALID_DOCUMENT", "A choreography must be an object or concrete move list.", "Supply a versioned choreography document.")
            doc = {}
        if doc.get("schema_version", 1) != SCHEMA_VERSION:
            self.issue("UNSUPPORTED_SCHEMA", "This choreography schema is unsupported.", "Open it in a compatible application version.")
        start = doc.get("start") or {}
        if not isinstance(start, dict):
            self.issue("INVALID_START", "Start state must be an object.", "Declare the initial foot and facing.")
            start = {}
        initial_free = start.get("free_foot", "R")
        self.support = self.support_value(start.get("support", _support_for_free(initial_free)), "initial support")
        if "free_foot" in start and initial_free not in ("L", "R", "unknown"):
            self.issue("INVALID_FREE_FOOT", "Initial free foot must be L, R, or unknown.", "Correct the initial free foot.")
        if "free_foot" in start and initial_free != "unknown" and _free(self.support) != initial_free:
            self.issue("START_STATE_CONTRADICTION", "Initial free foot and support disagree.", "Choose compatible initial support and free foot.")
        self.facing = None if start.get("facing_deg", 0) is None else self.number(start.get("facing_deg", 0), "initial facing") % 360
        initial = _state(self.support, self.facing)
        meter = doc.get("meter") or {}
        if not isinstance(meter, dict):
            self.issue("INVALID_METER", "Meter must be an object.", "Enter beats, unit, and display grouping.")
            meter = {}
        beats = self.number(meter.get("beats", 4), "meter beats", default=Fraction(4), minimum=1)
        unit = self.number(meter.get("unit", 4), "meter unit", default=Fraction(4), minimum=1)
        self.group = self.number(meter.get("group_counts", 8), "display grouping", default=Fraction(8), minimum=1)
        if any(value.denominator != 1 for value in (beats, unit, self.group)):
            self.issue("INVALID_METER", "Meter and display grouping must be whole counts.", "Use whole numbers; event timing still accepts fractions.")
        meter = {"beats": str(beats), "unit": str(unit), "group_counts": str(self.group)}
        pickup = self.number(doc.get("pickup_counts", 0), "pickup_counts", minimum=0)
        self.position = -pickup
        parts_raw = doc.get("parts", [])
        if not isinstance(parts_raw, list):
            self.issue("INVALID_PARTS", "Parts must be an ordered array.", "Supply named parts with movements.")
            parts_raw = []
        parts, part_ids = {}, set()
        for pindex, raw in enumerate(parts_raw[:1000]):
            if not isinstance(raw, dict):
                self.issue("INVALID_PART", "Each part must be an object.", "Correct the part definition.")
                continue
            pid = self.identity(raw.get("id"), f"part-{pindex + 1}", part_ids, "part")
            kind = raw.get("kind", "part")
            if kind not in ("part", "tag", "ending", "pickup"):
                self.issue("INVALID_PART_KIND", f"Unsupported part kind {kind}.", "Choose part, tag, ending, or pickup.", part_id=pid)
                kind = "part"
            moves_raw = raw.get("moves", [])
            if not isinstance(moves_raw, list):
                self.issue("INVALID_MOVES", "Part moves must be an array.", "Supply ordered movement occurrences.", part_id=pid)
                moves_raw = []
            mids = set()
            moves = [self.prepare_move(move, i, mids, pid) for i, move in enumerate(moves_raw[:MAX_EVENTS])]
            if not moves:
                self.issue("EMPTY_PART", f"Part {pid} has no moves.", "Add movements or remove the unused part.", part_id=pid)
            total = sum((exact_count(move["duration_counts"]) for move in moves), Fraction(0))
            part = {"id": pid, "name": str(raw.get("name", pid)), "kind": kind, "moves": moves,
                    "duration_counts": str(total)}
            if raw.get("target_counts") is not None:
                target = self.number(raw["target_counts"], "part target", minimum=0, part_id=pid)
                part["target_counts"] = str(target)
                if total != target:
                    self.issue("PART_COUNT_MISMATCH", f"Part {pid} has {total} counts; target is {target}.", "Correct the part or its target.", part_id=pid, expected=str(target), actual=str(total))
            parts[pid] = part
        if len(parts_raw) > 1000:
            self.issue("EXPANSION_LIMIT", "Too many parts.", "Split the routine into smaller documents.")
        routine = doc.get("routine")
        if routine is None:
            routine = [{"id": f"routine-{pid}", "part_id": pid} for pid in parts]
        if not isinstance(routine, list):
            self.issue("INVALID_ROUTINE", "Routine must be an ordered array.", "List each part occurrence in order.")
            routine = []
        normalized_routine, routine_ids, per_part = [], set(), {}
        for rindex, entry in enumerate(routine[:MAX_EVENTS]):
            if not isinstance(entry, dict):
                self.issue("INVALID_ROUTINE_ENTRY", "Routine entries must be objects.", "Name a part and repetition count.")
                continue
            rid = self.identity(entry.get("id"), f"routine-{rindex + 1}", routine_ids, "routine entry")
            pid = str(entry.get("part_id", ""))
            part = parts.get(pid)
            if part is None:
                self.issue("PART_MISSING", f"Part {pid} is missing.", "Restore the part or correct its reference.", routine_id=rid, part_id=pid)
                continue
            repeats = self.number(entry.get("repeat", 1), "repeat", minimum=1, routine_id=rid)
            if repeats.denominator != 1 or repeats > MAX_REPEATS:
                self.issue("INVALID_REPEAT", f"Repeat must be a whole number from 1 to {MAX_REPEATS}.", "Correct the repeat count.", routine_id=rid)
                repeats = Fraction(1)
            overrides = entry.get("overrides", {})
            if not isinstance(overrides, dict):
                self.issue("INVALID_OVERRIDES", "Occurrence overrides must map move IDs to definitions.", "Correct the replacement map.", routine_id=rid)
                overrides = {}
            known_ids = {move["id"] for move in part["moves"]}
            for unknown in set(overrides) - known_ids:
                self.issue("OVERRIDE_TARGET_MISSING", f"Move {unknown} does not exist in {pid}.", "Choose a movement occurrence in this part.", routine_id=rid, move_id=unknown)
            current_moves, override_ids = [], set()
            for mindex, move in enumerate(part["moves"]):
                if move["id"] in overrides:
                    replacement = overrides[move["id"]]
                    if not isinstance(replacement, dict):
                        self.issue("INVALID_OVERRIDE", "A replacement must be a complete move definition.", "Supply the replacement movement.", routine_id=rid, move_id=move["id"])
                        replacement = move
                    current_moves.append(self.prepare_move({**replacement, "id": move["id"]}, mindex, override_ids, pid))
                else:
                    current_moves.append(move)
                    override_ids.add(move["id"])
            span = sum((exact_count(move["duration_counts"]) for move in current_moves), Fraction(0))
            limit = self.number(entry.get("end_after_counts", str(span)), "end_after_counts", minimum=0, routine_id=rid)
            if limit > span:
                self.issue("BOUNDARY_OUT_OF_RANGE", f"Boundary {limit} exceeds part duration {span}.", "Choose an existing event boundary.", routine_id=rid)
                limit = span
            normalized_entry = {"id": rid, "part_id": pid, "repeat": int(repeats)}
            if "reason" in entry:
                normalized_entry["reason"] = deepcopy(entry["reason"])
            if "overrides" in entry:
                normalized_entry["overrides"] = {move["id"]: deepcopy(move) for move in current_moves if move["id"] in overrides}
            if "end_after_counts" in entry:
                normalized_entry["end_after_counts"] = str(limit)
            normalized_routine.append(normalized_entry)
            for repetition in range(1, int(repeats) + 1):
                if len(self.events) >= MAX_EVENTS or len(self.occurrences) >= MAX_EVENTS:
                    self.issue("EXPANSION_LIMIT", "Expanded routine exceeds the event limit.", "Reduce repetitions or split this routine.", routine_id=rid)
                    break
                oid = f"{rid}#{repetition}"
                per_part[pid] = per_part.get(pid, 0) + 1
                occurrence_start = self.position
                state_before = _state(self.support, self.facing)
                move_offset, applied_end = Fraction(0), Fraction(0)
                event_ids = []
                for move in current_moves:
                    for event in move["events"]:
                        local_start = move_offset + exact_count(event["offset_counts"])
                        local_end = local_start + exact_count(event["duration_counts"])
                        if local_start >= limit and local_end > local_start:
                            continue
                        if local_start > limit:
                            continue
                        eid = f"{oid}/{move['id']}/{event['id']}"
                        loc = {"occurrence_id": oid, "event_id": eid, "part_id": pid, "move_id": move["id"],
                               "start_count": str(occurrence_start + local_start), "end_count": str(occurrence_start + local_end)}
                        if local_end > limit:
                            self.issue("BOUNDARY_SPLITS_EVENT", "The requested ending/restart cuts through a movement event.", "Split the move into reviewed events at that boundary; partial footwork cannot be inferred.", **loc)
                            continue
                        if len(self.events) >= MAX_EVENTS:
                            self.issue("EXPANSION_LIMIT", "Expanded routine exceeds the event limit.", "Reduce repetitions or split this routine.", **loc)
                            break
                        before, after = self.apply_state(event, loc)
                        item = {**deepcopy(event), "id": eid, "source_event_id": event["id"],
                                "move_id": move["id"], "definition_id": move.get("definition_id"),
                                "move_name": move["name"], "part_id": pid, "occurrence_id": oid,
                                "start_count": loc["start_count"], "end_count": loc["end_count"],
                                "part_start_count": str(local_start), "part_end_count": str(local_end),
                                "count_label": format_count(occurrence_start + local_start, self.group),
                                "state_before": before, "state_after": after}
                        self.events.append(item)
                        event_ids.append(eid)
                        applied_end = max(applied_end, local_end)
                    move_offset += exact_count(move["duration_counts"])
                self.position = occurrence_start + limit
                if applied_end != limit:
                    self.issue("OCCURRENCE_COVERAGE", "The requested occurrence is not fully covered by valid whole events.", "Correct event coverage or choose a supported boundary.", occurrence_id=oid, start_count=str(occurrence_start), end_count=str(self.position))
                    self.support, self.facing = "unknown", None
                self.occurrences.append({"id": oid, "routine_id": rid, "part_id": pid, "part_name": part["name"], "kind": part["kind"],
                                         "occurrence_number": len(self.occurrences) + 1, "part_occurrence_number": per_part[pid],
                                         "repetition": repetition, "reason": entry.get("reason"),
                                         "start_count": str(occurrence_start), "end_count": str(self.position), "duration_counts": str(limit),
                                         "state_before": state_before, "state_after": _state(self.support, self.facing), "event_ids": event_ids})
        if not self.events:
            self.issue("EMPTY_ROUTINE", "No choreography events could be compiled.", "Add a part and include it in the routine.")
        total = self.position + pickup
        target = doc.get("target_counts")
        if target is not None:
            target = self.number(target, "routine target", minimum=0)
            if total != target:
                self.issue("ROUTINE_COUNT_MISMATCH", f"Routine has {total} counts; target is {target}.", "Correct the routine or its declared target.", expected=str(target), actual=str(total))
        final = _state(self.support, self.facing)
        repeat = doc.get("repeat", False)
        if not isinstance(repeat, bool):
            self.issue("INVALID_REPEAT_POLICY", "Routine repeat policy must be true or false.", "Choose whether the complete routine repeats.")
            repeat = False
        if repeat and self.events and not any(issue["severity"] == "error" for issue in self.issues):
            # Validate the next pass's actual transitions; do not demand that all
            # nonrepeating parts/tags/endings independently close their feet/wall.
            for event in self.events:
                self.apply_state(event, {"occurrence_id": event["occurrence_id"], "event_id": event["id"],
                                         "boundary": "routine_repeat", "start_count": event["start_count"], "end_count": event["end_count"]}, repeat_boundary=True)
            self.support = final["support"]
            self.facing = None if final["facing_deg"] is None else exact_count(final["facing_deg"])
        normalized = {"schema_version": 1, "start": initial, "meter": meter, "pickup_counts": str(pickup),
                      "repeat": repeat, "parts": list(parts.values()), "routine": normalized_routine}
        if target is not None:
            normalized["target_counts"] = str(target)
        error = any(issue["severity"] == "error" for issue in self.issues)
        unknown = any(issue["severity"] == "unverified" for issue in self.issues)
        payload = _json_value(normalized)
        source_hash = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        net = None if initial["facing_deg"] is None or final["facing_deg"] is None else (exact_count(final["facing_deg"]) - exact_count(initial["facing_deg"])) % 360
        return {"schema_version": 1, "source_hash": source_hash, "normalized_document": payload,
                "status": "INVALID" if error else "UNVERIFIED" if unknown else "VALID",
                "valid": not error, "verified": not error and not unknown, "total_counts": str(total),
                "start_count": str(-pickup), "end_count": str(self.position), "meter": meter,
                "net_rotation_deg": None if net is None else str(net),
                "facing_cycle": None if net is None else (net / 360).denominator,
                "start_state": initial, "end_state": final, "events": self.events,
                "occurrences": self.occurrences, "issues": self.issues}


def compile_choreography(document, snapshots=None):
    """Compile authored choreography without modifying inputs or any app state.

    ``valid`` means no known contradictions; ``verified`` additionally requires
    no unknown mechanical facts. Neither field is an instructor certification.
    Invalid drafts return actionable issues and can still be saved by callers.
    """
    return _Compiler(document, snapshots).run()
