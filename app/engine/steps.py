"""Step library: machine-encoded moves with foot continuity, rotation, and
emit templates.

Semantics (per data/step-database.seed.json conventions):
- free_foot = the foot available to step with next.  A move may follow only if
  its start foot == current free foot (or 'F' = either).
- end = the free foot AFTER the move (encodes the odd/even weight-change parity
  crux from the seed database).
- rot = signed net rotation in degrees for the canonical R-lead variant.
  + = clockwise/right, - = counter-clockwise/left.
- travel = net displacement direction, BODY-relative: "N" forward,
  "S" back, "E" to the dancer's right, "W" to the dancer's left, "" in place.
  The assembler rotates this by the current facing to get floor-absolute
  travel, so it can stop a dance from marching off the floor.  Without this
  the search happily chains 14 heel struts (28 counts of forward travel) and
  still passes every count/foot/wall gate.
- Mirroring an R-lead move: swap R<->L feet, negate rotation, mirror the
  left/right travel axis, swap direction words.  Every move here is stored
  canonical R-lead with mirrorable=True.

Emit templates: each move renders as lines of 1-2 beats.  Placeholders:
  {F} lead foot letter, {O} other foot, {DIR} lead direction word,
  {ODIR} opposite direction word, {TURN} turn direction word.
"""
from dataclasses import dataclass, field
from typing import List, Optional
import json
import os
import re


@dataclass(frozen=True)
class Line:
    beats: int          # whole beats this line spans (1 or 2)
    text: str
    sync: bool = False  # True -> counted with '&' (e.g. 1&2)


@dataclass(frozen=True)
class Move:
    id: str
    name: str           # display name template (may contain {DIR}/{TURN})
    header: str         # short section-header name template
    counts: int
    rot: int            # canonical R-lead net rotation, degrees, + = CW
    start: str          # 'R' | 'L' | 'F' (either)
    end: str            # free foot after: 'R' | 'L' | 'SAME' (only for start='F')
    level: str          # 'AB' | 'B' | 'I' (Improver) | 'INT' | 'A'
    ab_safe: bool
    sync: bool          # contains & syncopation
    turning: bool
    lines: tuple
    travel: str = ""    # body-relative net travel: N/S/E/W or "" = in place
    family: str = ""    # mirror-family key (same family, flipped lead pairs well)
    in_generator: bool = True  # False -> editor-only (odd counts / styling)

    def tempo_profile(self) -> dict:
        """Return the conservative tempo guidance for this movement.

        These values describe *validated* use, rather than a claim that a
        step becomes physically impossible beyond a particular BPM.  The
        assembler uses the high-tempo penalty to favor simpler, lower-travel
        material as tempo rises; experimental mode can still show candidates
        for a human choreographer to review.
        """
        penalty = 0.0
        preferred_max = 132
        if self.travel:
            penalty += 0.8
            preferred_max = min(preferred_max, 128)
        if self.turning:
            penalty += 1.2
            preferred_max = min(preferred_max, 126)
        if self.sync:
            penalty += 0.9
            preferred_max = min(preferred_max, 124)
        if self.counts >= 4 and (self.travel or self.turning):
            penalty += 0.4
        return {
            "minimum_bpm": 70,
            "preferred_bpm_min": 96,
            "preferred_bpm_max": preferred_max,
            "maximum_bpm": 132,
            "high_tempo_penalty": penalty,
        }

    def variant(self, lead: str) -> dict:
        """Concrete R-lead or L-lead instance as a plain dict."""
        if lead == "R":
            sub = {"F": "R", "O": "L", "DIR": "right", "ODIR": "left",
                   "TURN": "left" if self.rot < 0 else "right"}
            rot, start, end = self.rot, self.start, self.end
            travel = self.travel
        else:
            sub = {"F": "L", "O": "R", "DIR": "left", "ODIR": "right",
                   "TURN": "right" if self.rot < 0 else "left"}
            rot = -self.rot
            start = _flip(self.start)
            end = _flip(self.end)
            travel = _mirror_travel(self.travel)
        def fmt(s):
            out = s
            for k, v in sub.items():
                out = out.replace("{" + k + "}", v)
            return out
        return {
            "move_id": self.id,
            "lead": lead,
            "name": fmt(self.name),
            "header": fmt(self.header),
            "counts": self.counts,
            "rot": rot,
            "start": start,
            "end": end,
            "level": self.level,
            "sync": self.sync,
            "turning": self.turning,
            "travel": travel,
            "family": self.family or self.id,
            "lines": [{"beats": ln.beats, "text": fmt(ln.text), "sync": ln.sync}
                      for ln in self.lines],
            **self.tempo_profile(),
        }


def _flip(f: str) -> str:
    return {"R": "L", "L": "R", "F": "F", "SAME": "SAME"}[f]


def _mirror_travel(t: str) -> str:
    """Mirroring a move reflects the left/right axis; forward/back is unchanged."""
    return {"E": "W", "W": "E"}.get(t, t)


# Body-relative travel unit vectors: +y = forward, +x = dancer's right.
BODY_VEC = {"": (0, 0), "N": (0, 1), "S": (0, -1), "E": (1, 0), "W": (-1, 0)}
_VEC_DIR = {(0, 0): "", (0, 1): "N", (0, -1): "S", (1, 0): "E", (-1, 0): "W"}


def floor_travel(body_dir: str, rot: int):
    """Rotate a body-relative travel direction by the dancer's facing.

    rot is degrees clockwise from the home wall (12:00).  Returns a
    floor-absolute direction key, so 'forward' after a quarter turn is
    correctly a different direction on the floor than 'forward' before it.
    """
    dx, dy = BODY_VEC.get(body_dir, (0, 0))
    if dx == 0 and dy == 0:
        return ""
    r = rot % 360
    if r == 0:
        v = (dx, dy)
    elif r == 90:
        v = (dy, -dx)
    elif r == 180:
        v = (-dx, -dy)
    elif r == 270:
        v = (-dy, dx)
    else:
        return "?"
    return _VEC_DIR[v]


# ---------------------------------------------------------------------------
# The library.  Continuity encodings verified against the seed database:
# odd weight changes SWITCH the free foot, even KEEP it.
# ---------------------------------------------------------------------------
MOVES: List[Move] = [
    Move("vine_touch", "Grapevine {DIR}", "Grapevine {DIR}", 4, 0, "R", "L",
         "AB", True, False, False, (
             Line(2, "Step {F} to {DIR} side, cross {O} behind {F}"),
             Line(2, "Step {F} to {DIR} side, touch {O} beside {F}"),
         ), travel="E", family="vine"),
    Move("vine_quarter", "Vine {DIR} with ¼ turn", "Vine ¼ Turn {DIR}", 4, 90, "R", "L",
         "B", True, False, True, (
             Line(2, "Step {F} to {DIR} side, cross {O} behind {F}"),
             Line(2, "Turn ¼ {DIR} stepping {F} forward, scuff {O} forward"),
         ), travel="E", family="vine"),
    Move("jazz_box", "Jazz Box", "Jazz Box", 4, 0, "R", "R",
         "AB", True, False, False, (
             Line(2, "Cross {F} over {O}, step {O} back"),
             Line(2, "Step {F} to {DIR} side, step {O} beside {F}"),
         ), family="jazzbox"),
    Move("jazz_box_quarter", "Jazz Box with ¼ turn {DIR}", "Jazz Box ¼ Turn", 4, 90, "R", "R",
         "B", True, False, True, (
             Line(2, "Cross {F} over {O}, step {O} back turning ¼ {DIR}"),
             Line(2, "Step {F} to {DIR} side, step {O} beside {F}"),
         ), family="jazzbox"),
    Move("rocking_chair", "Rocking Chair", "Rocking Chair", 4, 0, "R", "R",
         "AB", True, False, False, (
             Line(2, "Rock {F} forward, recover on {O}"),
             Line(2, "Rock {F} back, recover on {O}"),
         ), family="rock"),
    Move("rock_fwd", "Forward Rock", "Rock Forward, Recover", 2, 0, "R", "R",
         "AB", True, False, False, (
             Line(2, "Rock {F} forward, recover on {O}"),
         ), family="rock"),
    Move("rock_back", "Back Rock", "Rock Back, Recover", 2, 0, "R", "R",
         "AB", True, False, False, (
             Line(2, "Rock {F} back, recover on {O}"),
         ), family="rock"),
    Move("step_touch", "Step Touch {DIR}", "Side Touch {DIR}", 2, 0, "R", "L",
         "AB", True, False, False, (
             Line(2, "Step {F} to {DIR} side, touch {O} beside {F}"),
         ), travel="E", family="steptouch"),
    Move("heel_strut", "Heel Strut {F}", "Heel Struts", 2, 0, "R", "L",
         "AB", True, False, False, (
             Line(2, "Touch {F} heel forward, drop {F} toe taking weight"),
         ), travel="N", family="strut"),
    Move("toe_strut", "Toe Strut {F}", "Toe Struts", 2, 0, "R", "L",
         "AB", True, False, False, (
             Line(2, "Touch {F} toe forward, drop {F} heel taking weight"),
         ), travel="N", family="toestrut"),
    Move("charleston", "Charleston", "Charleston", 4, 0, "R", "R",
         "AB", True, False, False, (
             Line(2, "Step {F} forward, kick {O} forward"),
             Line(2, "Step {O} back, touch {F} back"),
         ), family="charleston"),
    Move("side_together", "Side Together {DIR}", "Side Together {DIR}", 2, 0, "R", "R",
         "AB", True, False, False, (
             Line(2, "Step {F} to {DIR} side, step {O} beside {F}"),
         ), travel="E", family="sidetogether"),
    Move("walk_fwd", "Walk Forward ×2", "Walk, Walk", 2, 0, "R", "R",
         "AB", True, False, False, (
             Line(2, "Walk forward {F}, walk forward {O}"),
         ), travel="N", family="walk"),
    Move("walk_back", "Walk Back ×2", "Walk Back ×2", 2, 0, "R", "R",
         "AB", True, False, False, (
             Line(2, "Walk back {F}, walk back {O}"),
         ), travel="S", family="walkback"),
    Move("pivot_quarter", "¼ Pivot Turn {TURN}", "¼ Pivot {TURN}", 2, -90, "R", "R",
         "B", True, False, True, (
             Line(2, "Step {F} forward, pivot ¼ turn {TURN} (weight to {O})"),
         ), family="pivot"),
    Move("pivot_half", "½ Pivot Turn {TURN}", "½ Pivot {TURN}", 2, -180, "R", "R",
         "B", False, False, True, (
             Line(2, "Step {F} forward, pivot ½ turn {TURN} (weight to {O})"),
         ), family="pivot"),
    Move("shuffle_fwd", "Forward Shuffle {F}", "Shuffle Forward", 2, 0, "R", "L",
         "B", False, True, False, (
             Line(2, "Shuffle forward stepping {F}, {O}, {F}", sync=True),
         ), travel="N", family="shuffle"),
    Move("chasse_side", "Side Chasse {DIR}", "Chasse {DIR}", 2, 0, "R", "L",
         "B", False, True, False, (
             Line(2, "Step {F} to {DIR} side, close {O} beside {F}, step {F} to {DIR} side", sync=True),
         ), travel="E", family="chasse"),
    Move("kick_ball_change", "Kick-Ball-Change {F}", "Kick-Ball-Change", 2, 0, "R", "R",
         "B", False, True, False, (
             Line(2, "Kick {F} forward, step ball of {F} beside {O}, change weight to {O}", sync=True),
         ), family="kbc"),
    Move("coaster", "Coaster Step {F}", "Coaster Step", 2, 0, "R", "L",
         "B", False, True, False, (
             Line(2, "Step {F} back, step {O} beside {F}, step {F} forward", sync=True),
         ), family="coaster"),
    Move("sailor", "Sailor Step {F}", "Sailor Step", 2, 0, "R", "L",
         "B", False, True, False, (
             Line(2, "Cross {F} behind {O}, step {O} to {ODIR} side, step {F} to {DIR} side", sync=True),
         ), family="sailor"),
    Move("weave", "Weave {ODIR}", "Weave {ODIR}", 4, 0, "R", "R",
         "B", False, False, False, (
             Line(2, "Cross {F} over {O}, step {O} to {ODIR} side"),
             Line(2, "Cross {F} behind {O}, step {O} to {ODIR} side"),
         ), travel="W", family="weave"),
    Move("monterey_half", "Monterey ½ Turn {DIR}", "Monterey ½ Turn", 4, 180, "R", "R",
         "B", False, False, True, (
             Line(2, "Point {F} to {DIR} side, turn ½ {DIR} stepping {F} beside {O}"),
             Line(2, "Point {O} to {ODIR} side, step {O} beside {F}"),
         ), family="monterey"),
    Move("cross_rock", "Cross Rock {F}", "Cross Rock", 2, 0, "R", "R",
         "B", False, False, False, (
             Line(2, "Cross rock {F} over {O}, recover on {O}"),
         ), family="crossrock"),
    Move("scissor", "Scissor Step {F}", "Scissor Step", 2, 0, "R", "L",
         "B", False, True, False, (
             Line(2, "Step {F} to {DIR} side, step {O} beside {F}, cross {F} over {O}", sync=True),
         ), travel="E", family="scissor"),
    # --- improver ------------------------------------------------------------
    Move("cross_shuffle", "Cross Shuffle {F}", "Cross Shuffle", 2, 0, "R", "L",
         "I", False, True, False, (
             Line(2, "Cross {F} over {O}, step {O} to {ODIR} side, cross {F} over {O}", sync=True),
         ), travel="E", family="crossshuffle"),
    Move("back_lock_back", "Back Lock Back {F}", "Back Lock Back", 2, 0, "R", "L",
         "I", False, True, False, (
             Line(2, "Step {F} back, lock {O} across {F}, step {F} back", sync=True),
         ), travel="S", family="backlock"),
    Move("mambo_quarter", "Mambo ¼ Turn {TURN}", "Mambo ¼ Turn", 4, 90, "R", "R",
         "I", False, False, True, (
             Line(2, "Rock {F} forward, recover on {O}"),
             Line(2, "Turn ¼ {TURN} stepping {F} to side, cross {O} over {F}"),
         ), travel="E", family="mambo"),
    Move("heel_grind_quarter", "Heel Grind ¼ Turn {TURN}", "Heel Grind ¼ Turn", 2, 90, "R", "R",
         "I", False, False, True, (
             Line(2, "Touch {F} heel forward, turn ¼ {TURN} as you step {O} to side"),
         ), travel="W", family="heelgrind"),
    Move("monterey_quarter", "Monterey ¼ Turn {TURN}", "Monterey ¼ Turn", 4, 90, "R", "R",
         "I", False, False, True, (
             Line(2, "Point {F} to {DIR} side, turn ¼ {TURN} stepping {F} beside {O}"),
             Line(2, "Point {O} to {ODIR} side, step {O} beside {F}"),
         ), family="monterey"),
    Move("paddle_half", "Paddle ½ Turn {TURN}", "Paddle ½ Turn", 4, 180, "R", "R",
         "I", False, False, True, (
             Line(2, "Step {F} forward and turn ¼ {TURN}, push from {O}"),
             Line(2, "Step {F} forward and turn ¼ {TURN}, push from {O}"),
         ), family="paddle"),
    # --- advanced ------------------------------------------------------------
    Move("full_turn_walk", "Full Turn {TURN}", "Full Turn", 2, 360, "R", "R",
         "A", False, False, True, (
             Line(2, "Turn ½ {TURN} stepping {F} forward, turn ½ {TURN} stepping {O} back"),
         ), family="fullturn"),
    Move("rolling_vine", "Rolling Vine {DIR}", "Rolling Vine", 4, 360, "R", "L",
         "A", False, False, True, (
             Line(2, "Turn ¼ {DIR} stepping {F} to side, turn ½ {DIR} stepping {O} to side"),
             Line(2, "Turn ¼ {DIR} stepping {F} to side, touch {O} beside {F}"),
         ), travel="E", family="rollingvine"),
    # --- editor-only fillers (odd counts / weight-neutral) -------------------
    Move("hold", "Hold", "Hold", 1, 0, "F", "SAME",
         "AB", True, False, False, (Line(1, "Hold"),), in_generator=False),
    Move("clap", "Clap", "Clap", 1, 0, "F", "SAME",
         "AB", True, False, False, (Line(1, "Hold and clap hands"),), in_generator=False),
    Move("scuff", "Scuff", "Scuff", 1, 0, "F", "SAME",
         "AB", True, False, False, (Line(1, "Scuff {F} heel forward"),), in_generator=False),
    Move("hitch", "Hitch", "Hitch", 1, 0, "F", "SAME",
         "AB", True, False, False, (Line(1, "Hitch {F} knee up"),), in_generator=False),
    Move("point_side", "Point {F} Side", "Point", 1, 0, "F", "SAME",
         "AB", True, False, False, (Line(1, "Point {F} toe to {DIR} side"),), in_generator=False),
    Move("stomp_weighted", "Stomp {F} (takes weight)", "Stomp", 1, 0, "R", "L",
         "AB", True, False, False, (Line(1, "Stomp {F} beside {O} taking weight"),),
         in_generator=False),
]

MOVE_BY_ID = {m.id: m for m in MOVES}

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = os.path.dirname(APP_DIR)
from .paths import runtime_path
CUSTOM_MOVES_PATH = runtime_path('custom-moves.json', os.path.join(ROOT_DIR, "data", "custom-moves.json"))
LEVEL_RANK = {"AB": 0, "B": 1, "I": 2, "INT": 3, "A": 4}
LEVEL_ALIASES = {
    "absolute beginner": "AB", "ab": "AB", "beginner": "B", "b": "B",
    "improver": "I", "i": "I", "intermediate": "INT", "int": "INT",
    "advanced": "A", "a": "A",
}


def _slug(value):
    value = re.sub(r"[^a-z0-9]+", "-", (value or "move").lower()).strip("-")
    return value or "move"


def _canonical_level(value):
    result = LEVEL_ALIASES.get(str(value or "").strip().lower())
    if not result:
        raise ValueError("Level must be Absolute Beginner, Beginner, Improver, Intermediate, or Advanced.")
    return result


def _as_bool(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _read_custom_records():
    try:
        with open(CUSTOM_MOVES_PATH, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        rows = value.get("moves", []) if isinstance(value, dict) else []
        return rows if isinstance(rows, list) else []
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return []


def _write_custom_records(rows):
    os.makedirs(os.path.dirname(CUSTOM_MOVES_PATH), exist_ok=True)
    temp_path = CUSTOM_MOVES_PATH + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump({"schema_version": 1, "moves": rows}, handle, indent=1)
    os.replace(temp_path, CUSTOM_MOVES_PATH)


def _custom_move_from_record(record):
    """Turn a curated user record into the same move object used by the editor.

    Imported records must state mechanics.  We deliberately refuse to guess a
    dancer's free foot or turn from prose, because doing so would make a
    plausible-looking but invalid step sheet.
    """
    if not isinstance(record, dict):
        raise ValueError("Each move must be an object with its dance mechanics.")
    name = str(record.get("name") or "").strip()
    if not name or len(name) > 120:
        raise ValueError("Move name is required and must be under 120 characters.")
    try:
        counts = int(record.get("counts"))
        rotation = int(record.get("rotation", record.get("rot", 0)))
    except (TypeError, ValueError):
        raise ValueError(f"{name}: counts and rotation must be whole numbers.")
    if not 1 <= counts <= 8:
        raise ValueError(f"{name}: a move must be between 1 and 8 counts.")
    if rotation % 90:
        raise ValueError(f"{name}: rotation must be on the 90-degree grid.")
    start = str(record.get("start") or "").upper()
    end = str(record.get("end") or "").upper()
    if start not in ("R", "L", "F") or end not in ("R", "L", "SAME"):
        raise ValueError(f"{name}: start must be R, L, or F and end must be R, L, or SAME.")
    if start == "F" and end != "SAME":
        raise ValueError(f"{name}: an either-foot move must end with SAME free foot.")
    travel = str(record.get("travel") or "").upper()
    if travel not in ("", "N", "S", "E", "W"):
        raise ValueError(f"{name}: travel must be forward, back, dancer's right, dancer's left, or in place.")
    instructions = str(record.get("instructions") or record.get("description") or "").strip()
    if not instructions:
        raise ValueError(f"{name}: add clear teaching instructions before using this move.")
    move_id = _slug(record.get("id") or "custom-" + name)
    if not move_id.startswith("custom-"):
        move_id = "custom-" + move_id
    return Move(
        move_id, name, str(record.get("header") or name).strip()[:80], counts, rotation,
        start, end, _canonical_level(record.get("level") or "I"),
        _as_bool(record.get("ab_safe")), _as_bool(record.get("sync")), bool(rotation),
        (Line(counts, instructions, _as_bool(record.get("sync"))),),
        travel=travel, family=_slug(record.get("family") or name),
        in_generator=_as_bool(record.get("in_generator")),
    )


def custom_moves():
    out = []
    for record in _read_custom_records():
        try:
            out.append(_custom_move_from_record(record))
        except ValueError:
            continue
    return out


def all_moves(include_custom=True):
    return MOVES + (custom_moves() if include_custom else [])


def get_move(move_id):
    if move_id in MOVE_BY_ID:
        return MOVE_BY_ID[move_id]
    return next((move for move in custom_moves() if move.id == move_id), None)


def list_custom_move_records():
    return _read_custom_records()


def save_custom_move(record):
    move = _custom_move_from_record(record)  # validates before writing anything
    rows = _read_custom_records()
    public = dict(record)
    public.update({"id": move.id, "name": str(record.get("name")).strip(),
                   "counts": move.counts, "rotation": move.rot, "start": move.start,
                   "end": move.end, "level": move.level,
                   "instructions": str(record.get("instructions") or record.get("description")).strip(),
                   "travel": move.travel, "sync": move.sync,
                   "in_generator": move.in_generator, "family": move.family})
    rows = [row for row in rows if row.get("id") != move.id]
    rows.append(public)
    rows.sort(key=lambda row: str(row.get("name", "")).lower())
    _write_custom_records(rows)
    return move.variant("R")


def delete_custom_move(move_id):
    if not str(move_id).startswith("custom-"):
        raise ValueError("Built-in moves cannot be deleted.")
    rows = _read_custom_records()
    kept = [row for row in rows if row.get("id") != move_id]
    if len(kept) == len(rows):
        raise ValueError("Custom move not found.")
    _write_custom_records(kept)

# Hand-seeded Markov preferred pairs (STEERING section 5): canonical beginner
# transitions.  Key: (prev_move_id) -> {next_move_id: bonus}.  Mirror-lead
# handling lives in the assembler (same-family flipped-lead bonus).
#
# Self-pair bonuses on TRAVELING moves are deliberately modest: a self-pair
# bonus and the assembler's mirror-family bonus stack, and on a traveling move
# that stack is what produced 14-strut chains that march off the floor.  Real
# sheets do vine-R then vine-L once, not seven times.  In-place moves
# (charleston, jazz box, rocking chair) can afford the larger self bonus.
MARKOV_PAIRS = {
    "vine_touch": {"vine_touch": 1.5, "rocking_chair": 1.5, "step_touch": 1.0,
                   "jazz_box": 1.2},
    "vine_quarter": {"walk_fwd": 1.5, "shuffle_fwd": 1.5, "rock_fwd": 1.0},
    "jazz_box": {"jazz_box": 1.0, "jazz_box_quarter": 1.5, "vine_touch": 1.0},
    "jazz_box_quarter": {"vine_touch": 1.5, "side_together": 1.0},
    "rocking_chair": {"vine_touch": 1.5, "step_touch": 1.0, "walk_fwd": 1.0},
    "rock_fwd": {"coaster": 2.0, "walk_back": 1.5, "rock_back": 0.5},
    "rock_back": {"walk_fwd": 1.5, "shuffle_fwd": 1.5, "kick_ball_change": 1.0},
    "walk_fwd": {"pivot_quarter": 2.5, "pivot_half": 2.5, "rock_fwd": 1.5,
                 "shuffle_fwd": 0.5},
    "walk_back": {"coaster": 2.0, "rock_back": 1.5},
    "step_touch": {"step_touch": 1.5, "vine_touch": 1.0, "jazz_box": 1.0},
    "heel_strut": {"heel_strut": 1.2, "rock_back": 1.5, "jazz_box": 1.0},
    "toe_strut": {"toe_strut": 1.2, "rock_back": 1.5, "jazz_box": 1.0},
    "charleston": {"charleston": 3.0},
    "side_together": {"side_together": 1.0, "step_touch": 1.0, "rocking_chair": 1.2},
    "chasse_side": {"rock_back": 2.5, "cross_rock": 1.5},
    "shuffle_fwd": {"shuffle_fwd": 1.0, "rock_fwd": 2.5},
    "coaster": {"shuffle_fwd": 1.5, "walk_fwd": 1.0},
    "kick_ball_change": {"kick_ball_change": 1.5, "walk_fwd": 1.0},
    "pivot_quarter": {"cross_rock": 1.0, "jazz_box": 1.0, "vine_touch": 1.0},
    "pivot_half": {"walk_fwd": 1.5, "shuffle_fwd": 1.5},
    "sailor": {"sailor": 2.0, "step_touch": 0.5},
    "weave": {"rock_back": 1.0, "step_touch": 1.0},
    "monterey_half": {"monterey_half": 1.5, "jazz_box": 1.0},
    "cross_rock": {"chasse_side": 2.0, "side_together": 1.0},
    "scissor": {"scissor": 2.0},
}


def generator_moves(level: str = "AB", allow_sync: bool = False,
                    include_custom: bool = False) -> List[dict]:
    """All concrete variants (R and L lead) eligible for the assembler."""
    out = []
    level = _canonical_level(level)
    for m in all_moves(include_custom=include_custom):
        if not m.in_generator:
            continue
        if level == "AB" and not m.ab_safe:
            continue
        # Absolute Beginner is deliberately curated by the stricter ab_safe
        # flag, which includes a small number of otherwise Beginner turns.
        if level != "AB" and LEVEL_RANK.get(m.level, 99) > LEVEL_RANK[level]:
            continue
        if m.sync and not allow_sync:
            continue
        for lead in ("R", "L"):
            out.append(m.variant(lead))
    return out


def library_json() -> List[dict]:
    """Full library for the editor UI (both leads, including fillers)."""
    out = []
    for m in all_moves(include_custom=True):
        for lead in ("R", "L"):
            v = m.variant(lead)
            v["ab_safe"] = m.ab_safe
            v["in_generator"] = m.in_generator
            out.append(v)
    return out


def editor_moves(include_expansion=False) -> List[dict]:
    """Creator may opt into exact-event manual moves; legacy lists stay stable."""
    result = library_json()
    if include_expansion:
        from .move_expansion import variants
        result.extend(variants())
    return result
