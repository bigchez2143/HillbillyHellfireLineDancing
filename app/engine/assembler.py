"""Assembler: backtracking best-first DFS over the step library.

Implements STEERING.md section 5:
- Hard constraints enforced structurally (illegal branches never generated):
  count budget, foot continuity, final foot parity, wall rotation target,
  moves never straddle an 8-count block boundary, and no more than
  TRAVEL_RUN_CAP consecutive counts travelling the same floor direction
  (without this the search chains 14 heel struts and marches the line off
  the floor while still passing every other gate).
- Reachability DP runs BEFORE the search; infeasible inputs raise structured
  fail-loud errors (never silently padded or fudged).
- Branch ordering: hand-seeded Markov pairs + mirror-family bonus + phrasing
  alignment bonus + seeded noise (temperature).  A seed reproduces the result
  byte-for-byte.
- k-best with a diversity filter (MMR-style multiset similarity cap).

Wall math (exact):  walls = 360 / gcd(R, 360) where R = net rotation of one
pass mod 360.  target_R: 1-wall -> 0, 2-wall -> 180, 4-wall -> 90 or 270.
"""
import math
import random
from collections import Counter
from functools import lru_cache

from .steps import generator_moves, MARKOV_PAIRS, floor_travel, BODY_VEC

# Max consecutive counts of travel in one floor direction.  8 counts is a
# full block: e.g. two vines sideways, or four walks forward — the longest
# uninterrupted run real beginner sheets use.
TRAVEL_RUN_CAP = 8
# This is a product boundary, not a tempo detector limit.  Audio may still be
# analysed above it, but normal choreography generation is only validated up
# to this tempo.  See STEERING.md and the API's experimental-mode gate.
VALIDATED_MAX_BPM = 132


def _quality_profile(sequence, total_counts, publication_mode=True):
    """Score a legal sequence for choreographic variety, not just correctness.

    This is deliberately a ranking signal rather than a claim that an
    algorithm can publish a dance. A real floor test and a choreographer's
    signature moment remain required before a sheet is submitted.
    """
    families = [move.get("family") or move["move_id"] for move in sequence]
    ids = [move["move_id"] for move in sequence]
    family_counts = Counter(families)
    id_counts = Counter(ids)
    blocks = []
    pos, block = 0, []
    for move in sequence:
        block.append(move.get("family") or move["move_id"])
        pos += move["counts"]
        if pos % 8 == 0 or pos == total_counts:
            blocks.append(tuple(block))
            block = []

    unique_families = len(set(families))
    unique_blocks = len(set(blocks))
    turning = [move for move in sequence if move.get("turning")]
    travelling = [move for move in sequence if move.get("travel")]
    grounded = [move for move in sequence
                if not move.get("travel") and not move.get("turning")]
    repeated_ids = sum(max(0, count - 1) for count in id_counts.values())
    repeated_families = sum(max(0, count - 2) for count in family_counts.values())

    score = 45
    score += min(20, unique_families * 4)
    score += min(14, max(0, unique_blocks - 1) * 5)
    if travelling and grounded:
        score += 5
    if turning:
        score += 4
    score -= repeated_ids * 4
    score -= repeated_families * 5
    if len(blocks) >= 3 and len(set(blocks[:3])) == 1:
        score -= 10
    if publication_mode and unique_families < min(4, len(sequence)):
        score -= 8
    score = max(0, min(100, int(round(score))))

    strengths = []
    if unique_families >= 4:
        strengths.append(f"{unique_families} movement families")
    if unique_blocks >= max(2, len(blocks) - 1):
        strengths.append("distinct 8-count blocks")
    if travelling and grounded:
        strengths.append("travel and recovery balance")
    if turning:
        strengths.append("clear wall change")
    cautions = []
    most_repeated = max(id_counts, key=id_counts.get) if id_counts else None
    if most_repeated and id_counts[most_repeated] >= 3:
        cautions.append(f"{most_repeated.replace('_', ' ')} repeats {id_counts[most_repeated]} times")
    if unique_families < 4:
        cautions.append("limited movement variety")

    featured = sorted(sequence, key=lambda move: (
        bool(move.get("turning")), bool(move.get("travel")), move["counts"]), reverse=True)
    signature = featured[0]["name"] if featured else "Add a chorus signature in the editor"
    return {
        "score": score,
        "label": ("Strong foundation" if score >= 72 else
                  "Good draft - add personality" if score >= 58 else
                  "Needs a stronger edit"),
        "strengths": strengths,
        "cautions": cautions,
        "signature_opportunity": signature,
        "publication_note": ("Floor-test it, then personalize the signature moment before submitting."),
    }


class AssemblyError(Exception):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self):
        return {"error": self.code, "message": self.message, "details": self.details}


WALL_TARGETS = {"1": 0, "2": 180, "4R": 90, "4L": 270}


def wall_count(net_rot):
    r = net_rot % 360
    return 360 // math.gcd(int(r), 360) if r else 1


def _target_rot(wall, turn_dir):
    if wall == "1":
        return 0
    if wall == "2":
        return 180
    if wall == "4":
        return 90 if turn_dir == "R" else 270
    raise AssemblyError("CONTRADICTORY_INPUT", f"Unsupported wall target: {wall}")


def _block_end(pos, total):
    """First 8-count boundary at or after pos+1 (moves may not straddle it)."""
    return min(((pos // 8) + 1) * 8, total)


def _tempo_status(bpm, experimental_mode):
    """Validate the product's tempo boundary and return export-safe metadata."""
    if bpm is None:
        return {"bpm": None, "mode": "unmeasured", "validated_max_bpm": VALIDATED_MAX_BPM,
                "manual_review_required": True,
                "message": "Tempo has not been measured; analyse the song before publishing."}
    try:
        bpm = float(bpm)
    except (TypeError, ValueError):
        raise AssemblyError("CONTRADICTORY_INPUT", "BPM must be a positive number.")
    if bpm <= 0:
        raise AssemblyError("CONTRADICTORY_INPUT", "BPM must be a positive number.")
    if bpm > VALIDATED_MAX_BPM and not experimental_mode:
        raise AssemblyError(
            "EXPERIMENTAL_MODE_REQUIRED",
            f"This song measures {bpm:.0f} BPM, above the validated {VALIDATED_MAX_BPM} BPM "
            "limit. Analyse and edit it normally, but enable experimental/manual-review "
            "mode before generating choreography.",
            {"bpm": round(bpm, 2), "validated_max_bpm": VALIDATED_MAX_BPM,
             "manual_review_required": True})
    experimental = bpm > VALIDATED_MAX_BPM
    return {
        "bpm": round(bpm, 2),
        "mode": "experimental" if experimental else "normal",
        "validated_max_bpm": VALIDATED_MAX_BPM,
        "manual_review_required": experimental,
        "message": (f"{bpm:.0f} BPM is above the validated range; this candidate needs "
                    "manual choreography review before teaching or publishing."
                    if experimental else f"{bpm:.0f} BPM is within the validated range."),
    }


def assemble(total_counts=32, wall="2", turn_dir="L", level="AB",
             allow_sync=False, start_foot="R", seed=0, k=3,
             temperature=0.6, node_budget=200_000, bpm=None,
             experimental_mode=False, publication_mode=True,
             include_custom_moves=False):
    """Returns {"candidates": [...], "target_rot": int, "nodes": int}.

    Raises AssemblyError with a structured code on infeasible input.
    """
    if total_counts <= 0 or total_counts % 4 != 0:
        raise AssemblyError(
            "CONTRADICTORY_INPUT",
            f"Total counts must be a positive multiple of 4 (got {total_counts}). "
            "Line dance patterns phrase in 8s; 32 is the standard.")

    tempo = _tempo_status(bpm, experimental_mode)
    measured_bpm = tempo["bpm"]
    moves = generator_moves(level=level, allow_sync=allow_sync,
                            include_custom=include_custom_moves)
    if not moves:
        raise AssemblyError("CONTRADICTORY_INPUT",
                            "No moves available under these filters.")
    target = _target_rot(wall, turn_dir)

    rots = sorted({m["rot"] % 360 for m in moves} | {0})
    for r in rots:
        if r % 90 != 0:
            raise AssemblyError("CONTRADICTORY_INPUT",
                                f"Move rotation {r} is off the 90-degree grid.")

    def _step(m, foot, rot, tdir, trun):
        """Apply a move: returns (foot, rot, travel_dir, travel_run) after it,
        or None if it would exceed the travel-run cap."""
        fdir = floor_travel(m.get("travel", ""), rot)
        if fdir:
            nrun = (trun + m["counts"]) if fdir == tdir else m["counts"]
            if nrun > TRAVEL_RUN_CAP:
                return None
            ntdir = fdir
        else:
            ntdir, nrun = "", 0   # an in-place move breaks the travelling run
        nfoot = foot if m["end"] == "SAME" else m["end"]
        return nfoot, (rot + m["rot"]) % 360, ntdir, nrun

    # ---- reachability DP: can this state still reach the goal? -------------
    # check_continuity=False also relaxes MID-PATH foot continuity, which is
    # what distinguishes "the counts can't tile" from "the feet dead-end".
    def make_reach(check_foot=True, check_rot=True, check_continuity=True,
                   check_travel=True):
        @lru_cache(maxsize=None)
        def reach(pos, foot, rot, tdir, trun):
            if pos == total_counts:
                ok_foot = (foot == start_foot) if check_foot else True
                ok_rot = (rot == target) if check_rot else True
                return ok_foot and ok_rot
            bend = _block_end(pos, total_counts)
            for m in moves:
                if m["counts"] > bend - pos:
                    continue
                if check_continuity and m["start"] not in (foot, "F"):
                    continue
                nxt = _step(m, foot, rot, tdir, trun)
                if nxt is None:
                    if check_travel:
                        continue
                    nfoot = foot if m["end"] == "SAME" else m["end"]
                    nxt = (nfoot, (rot + m["rot"]) % 360, "", 0)
                if reach(pos + m["counts"], *nxt):
                    return True
            return False
        return reach

    reach_full = make_reach()
    if not reach_full(0, start_foot, 0, "", 0):
        # Diagnose which constraint kills it (fail loudly with the exact gap).
        if make_reach(check_foot=True, check_rot=False)(0, start_foot, 0, "", 0):
            # Enumerate the WHOLE 90-degree grid, not just single-move
            # rotations: a target reachable only by combining moves must not
            # be reported as unachievable.
            achievable = sorted(r for r in (0, 90, 180, 270)
                                if _rot_achievable(moves, total_counts,
                                                   start_foot, r))
            closest = min(achievable,
                          key=lambda r: min((r - target) % 360,
                                            (target - r) % 360)) \
                if achievable else None
            gap = min((closest - target) % 360, (target - closest) % 360) \
                if closest is not None else None
            raise AssemblyError(
                "INFEASIBLE_WALL",
                f"No sequence reaches the {wall}-wall rotation target "
                f"({target} deg) with these moves."
                + (f" Closest achievable is {closest} deg ({gap} deg short)."
                   if closest is not None else ""),
                {"target_rot": target, "achievable_rots": achievable,
                 "closest_rot": closest, "gap_deg": gap})
        if make_reach(check_foot=False, check_rot=True)(0, start_foot, 0, "", 0):
            raise AssemblyError(
                "INFEASIBLE_FOOT",
                "No sequence returns the free foot to the start foot "
                f"({start_foot}) — the dance could not loop.",
                {"start_foot": start_foot})
        if make_reach(check_foot=False, check_rot=False)(0, start_foot, 0, "", 0):
            raise AssemblyError(
                "CONTRADICTORY_INPUT",
                "Counts are fillable but foot parity and wall target cannot "
                "both be satisfied together with these moves.")
        # Counts tile only when mid-path foot continuity is relaxed => the real
        # blocker is a foot dead-end, NOT the count budget.  Naming the wrong
        # gap here would violate the "name the exact seam" contract.
        if make_reach(check_foot=False, check_rot=False,
                      check_continuity=False)(0, start_foot, 0, "", 0):
            raise AssemblyError(
                "INFEASIBLE_FOOT",
                f"The {total_counts} counts can be tiled, but foot continuity "
                "dead-ends part-way: at some point no available move starts on "
                "the free foot.",
                {"total_counts": total_counts, "start_foot": start_foot,
                 "available_start_feet": sorted({m["start"] for m in moves})})
        # Counts still don't tile even with travel relaxed?  Then it really is
        # the budget; otherwise the travel cap is the binding constraint.
        if make_reach(check_foot=False, check_rot=False, check_continuity=False,
                      check_travel=False)(0, start_foot, 0, "", 0):
            raise AssemblyError(
                "INFEASIBLE_TRAVEL",
                f"No sequence fills {total_counts} counts without travelling "
                f"more than {TRAVEL_RUN_CAP} counts in one direction — the "
                "available moves are all locomotion with nothing danced on the "
                "spot.",
                {"travel_run_cap": TRAVEL_RUN_CAP})
        raise AssemblyError(
            "INFEASIBLE_COUNT",
            f"The {total_counts}-count budget cannot be tiled by the "
            "available step lengths without straddling an 8-count block.",
            {"total_counts": total_counts,
             "move_lengths": sorted({m['counts'] for m in moves})})

    # ---- scored DFS ---------------------------------------------------------
    rng = random.Random(seed)
    solutions = []
    nodes = [0]
    candidate_pool = max(k * (30 if publication_mode else 8), 24)

    def score(m, prev, pos, rot, tdir, trun, famrun):
        s = 0.0
        if prev is not None:
            same_family = m["family"] == prev["family"]
            # Repetition decay: a mirrored pair (vine R -> vine L) is the
            # canonical beginner figure, but a THIRD and FOURTH repeat is a
            # machine tic, not choreography.  Bonuses decay with the run and
            # an escalating penalty takes over.
            decay = 1.0 / famrun if same_family else 1.0
            s += decay * MARKOV_PAIRS.get(prev["move_id"], {}).get(m["move_id"], 0.0)
            if same_family and m["lead"] != prev["lead"]:
                s += 2.5 * decay        # mirror pair (vine R -> vine L etc.)
            if same_family:
                s -= 1.8 * max(0, famrun - 1)
            if m["move_id"] == prev["move_id"] and m["lead"] == prev["lead"]:
                s -= 1.5  # discourage literal same-lead repeats
        end = pos + m["counts"]
        if end % 8 == 0:
            s += 1.0
        elif end % 4 == 0:
            s += 0.5
        if m["turning"]:
            s += 0.3  # gentle nudge so turns appear where legal
        # Travel shaping: the hard cap stops the pathological case; this makes
        # the ordinary case look like a real sheet rather than a route march.
        fdir = floor_travel(m.get("travel", ""), rot)
        if fdir:
            if fdir == tdir:
                s -= 1.2 * (trun / 2.0)   # escalating with the run so far
            if trun == 0 and tdir == "":
                s += 0.2                  # starting a fresh travel is fine
        else:
            s += 0.4 * min(trun, 4) / 4.0  # reward coming to rest after travel

        # High tempo needs more than a hard reject.  These penalties influence
        # movement selection, transition safety, travel, repetition tolerance,
        # and candidate ranking while keeping a reviewable experimental path.
        if measured_bpm is not None:
            tempo_pressure = max(0.0, (measured_bpm - 116.0) / 16.0)
            profile_penalty = m.get("high_tempo_penalty", 0.0)
            preferred_max = m.get("preferred_bpm_max", VALIDATED_MAX_BPM)
            over_preferred = max(0.0, measured_bpm - preferred_max) / 8.0
            s -= profile_penalty * (tempo_pressure + over_preferred)
            if tempo_pressure and m.get("travel"):
                s -= 0.8 * tempo_pressure
            if tempo_pressure and m.get("turning"):
                s -= 0.7 * tempo_pressure
            if prev is not None and tempo_pressure:
                # Consecutive travelling or turning moves are where a sequence
                # can feel safe on paper but hurried on a real floor.
                if prev.get("travel") and m.get("travel"):
                    s -= 0.9 * tempo_pressure
                if prev.get("turning") and m.get("turning"):
                    s -= 0.5 * tempo_pressure
                if m["family"] == prev["family"]:
                    s -= 0.5 * tempo_pressure * max(0, famrun - 1)
        return s + rng.gauss(0.0, temperature)

    def similarity(a, b):
        ids_a = [x["move_id"] for x in a]
        ids_b = [x["move_id"] for x in b]
        from collections import Counter
        ca, cb = Counter(ids_a), Counter(ids_b)
        inter = sum((ca & cb).values())
        return inter / max(len(ids_a), len(ids_b))

    def dfs(pos, foot, rot, tdir, trun, prev, seq, famrun=1):
        if len(solutions) >= candidate_pool or nodes[0] > node_budget:
            return
        if pos == total_counts:
            if foot == start_foot and rot == target:
                solutions.append(list(seq))
            return
        bend = _block_end(pos, total_counts)
        cands = []
        for m in moves:
            if m["counts"] > bend - pos:
                continue
            if m["start"] not in (foot, "F"):
                continue
            nxt = _step(m, foot, rot, tdir, trun)
            if nxt is None:
                continue          # would exceed the travel-run cap
            if not reach_full(pos + m["counts"], *nxt):
                continue
            cands.append((score(m, prev, pos, rot, tdir, trun, famrun), m, nxt))
        cands.sort(key=lambda t: -t[0])
        for sc, m, nxt in cands:
            nodes[0] += 1
            if nodes[0] > node_budget:
                return
            nfam = famrun + 1 if (prev and m["family"] == prev["family"]) else 1
            seq.append(m)
            dfs(pos + m["counts"], *nxt, m, seq, nfam)
            seq.pop()
            if len(solutions) >= candidate_pool:
                return

    dfs(0, start_foot, 0, "", 0, None, [])

    if not solutions:
        raise AssemblyError(
            "SEARCH_BUDGET_EXCEEDED",
            f"Search hit the node budget ({node_budget}) with no complete "
            "sequence. Not returning a partial dance.",
            {"nodes": nodes[0]})

    # ---- k-best with diversity ---------------------------------------------
    ranked = sorted(((_quality_profile(sol, total_counts, publication_mode), sol)
                     for sol in solutions), key=lambda item: item[0]["score"], reverse=True)
    picked = []
    for quality, sol in ranked:
        if all(similarity(sol, p["moves"]) < 0.75 for p in picked):
            net = sum(m["rot"] for m in sol) % 360
            assert net == target, "wall invariant violated"
            picked.append({"moves": sol, "net_rot": net,
                           "walls": wall_count(net), "seed": seed,
                           "quality": quality})
        if len(picked) >= k:
            break
    # Backfill with less-diverse solutions if the filter was too strict.
    for quality, sol in ranked:
        if len(picked) >= k:
            break
        if any(sol is p["moves"] for p in picked):
            continue
        net = sum(m["rot"] for m in sol) % 360
        entry = {"moves": sol, "net_rot": net,
                 "walls": wall_count(net), "seed": seed,
                 "quality": quality}
        if not any(similarity(sol, p["moves"]) >= 0.999 and
                   [x['move_id'] for x in sol] == [x['move_id'] for x in p['moves']]
                   for p in picked):
            picked.append(entry)

    return {"candidates": picked, "target_rot": target, "nodes": nodes[0],
            "tempo": tempo}


def assemble_anchored(required_slots, total_counts=32, wall="2", turn_dir="L",
                      level="AB", allow_sync=False, start_foot="R", seed=0,
                      k=3, node_budget=200_000, bpm=None,
                      experimental_mode=False, publication_mode=True,
                      include_custom_moves=False):
    """Fill around fixed lyric-derived move slots without moving the cues.

    ``required_slots`` uses one-based ``start_count`` values and vetted
    ``move_id``/``lead`` pairs.  A ``None`` lead lets foot continuity choose
    between the move's two mirrored variants.  Only open counts are generated;
    lyric anchors are never shifted, shortened, or silently dropped.
    """
    if total_counts <= 0 or total_counts % 4 != 0:
        raise AssemblyError(
            "CONTRADICTORY_INPUT",
            f"Total counts must be a positive multiple of 4 (got {total_counts}).")
    if not required_slots:
        raise AssemblyError(
            "NO_LYRIC_CUES",
            "No dependable lyric movement cues were available to lock into the dance.")

    tempo = _tempo_status(bpm, experimental_mode)
    measured_bpm = tempo["bpm"]
    moves = generator_moves(level=level, allow_sync=allow_sync,
                            include_custom=include_custom_moves)
    if not moves:
        raise AssemblyError("CONTRADICTORY_INPUT",
                            "No moves are available under these filters.")
    target = _target_rot(wall, turn_dir)
    variants_by_id = {}
    for move in moves:
        variants_by_id.setdefault(move["move_id"], {})[move["lead"]] = move

    slots = []
    occupied_until = 0
    for index, raw in enumerate(sorted(required_slots,
                                       key=lambda row: int(row["start_count"])), start=1):
        try:
            start_count = int(raw["start_count"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AssemblyError(
                "LYRIC_CUE_INFEASIBLE",
                f"Lyric cue {index} has no valid starting count.") from exc
        move_id = str(raw.get("move_id") or "")
        available = variants_by_id.get(move_id) or {}
        requested_lead = raw.get("lead")
        if requested_lead not in (None, "R", "L"):
            raise AssemblyError(
                "LYRIC_CUE_INFEASIBLE",
                f"Lyric cue {index} has an invalid lead foot: {requested_lead}.")
        variants = ([available[requested_lead]]
                    if requested_lead in available else
                    [available[key] for key in ("R", "L") if key in available]
                    if requested_lead is None else [])
        if not variants:
            raise AssemblyError(
                "LYRIC_CUE_FILTERED",
                f"The lyric cue '{raw.get('source_text') or move_id}' maps to a move "
                "outside the selected level or syncopation settings.",
                {"move_id": move_id, "lead": requested_lead})
        counts = int(variants[0]["counts"])
        start = start_count - 1
        end = start + counts
        if start < 0 or end > total_counts:
            raise AssemblyError(
                "LYRIC_CUE_INFEASIBLE",
                f"The lyric cue '{raw.get('source_text') or move_id}' does not fit "
                f"inside the {total_counts}-count pattern.",
                {"start_count": start_count, "counts": counts})
        if start < occupied_until:
            raise AssemblyError(
                "LYRIC_CUE_INFEASIBLE",
                f"The lyric cue at count {start_count} overlaps an earlier lyric move.")
        if end > _block_end(start, total_counts):
            raise AssemblyError(
                "LYRIC_CUE_INFEASIBLE",
                f"The lyric cue '{raw.get('source_text') or move_id}' would straddle "
                f"an 8-count boundary at count {_block_end(start, total_counts)}.",
                {"start_count": start_count, "counts": counts})
        slot = {
            "start": start, "start_count": start_count, "end": end,
            "move_id": move_id, "lead": requested_lead,
            "variants": variants,
            "source_text": str(raw.get("source_text") or ""),
            "detection_id": raw.get("detection_id"),
            "confidence": raw.get("confidence"),
        }
        slots.append(slot)
        occupied_until = end

    anchor_by_start = {slot["start"]: slot for slot in slots}
    anchor_starts = tuple(slot["start"] for slot in slots)

    def next_anchor(pos):
        return next((start for start in anchor_starts if start > pos), total_counts)

    def step(move, foot, rot, travel_dir, travel_run):
        absolute_travel = floor_travel(move.get("travel", ""), rot)
        if absolute_travel:
            run = (travel_run + move["counts"]
                   if absolute_travel == travel_dir else move["counts"])
            if run > TRAVEL_RUN_CAP:
                return None
            new_dir = absolute_travel
        else:
            new_dir, run = "", 0
        new_foot = foot if move["end"] == "SAME" else move["end"]
        return new_foot, (rot + move["rot"]) % 360, new_dir, run

    def choices(pos, foot):
        slot = anchor_by_start.get(pos)
        if slot:
            return [(move, slot) for move in slot["variants"]
                    if move["start"] in (foot, "F")]
        room = min(_block_end(pos, total_counts), next_anchor(pos)) - pos
        return [(move, None) for move in moves
                if move["counts"] <= room and move["start"] in (foot, "F")]

    @lru_cache(maxsize=None)
    def reachable(pos, foot, rot, travel_dir, travel_run):
        if pos == total_counts:
            return foot == start_foot and rot == target
        for move, _ in choices(pos, foot):
            nxt = step(move, foot, rot, travel_dir, travel_run)
            if nxt and reachable(pos + move["counts"], *nxt):
                return True
        return False

    if not reachable(0, start_foot, 0, "", 0):
        labels = [slot["source_text"] or slot["move_id"] for slot in slots]
        raise AssemblyError(
            "LYRIC_GAPS_INFEASIBLE",
            "The locked lyric moves cannot be connected into a valid "
            f"{total_counts}-count, {wall}-wall pattern without changing a cue. "
            "Try another detected passage, wall setting, or Manual Build.",
            {"locked_cues": labels, "target_rotation": target})

    rng = random.Random(seed)
    solutions = []
    nodes = [0]
    candidate_pool = max(k * (24 if publication_mode else 8), 18)

    def choice_score(move, previous, pos, rot, travel_dir, travel_run,
                     family_run, is_anchor):
        score = 50.0 if is_anchor else 0.0
        if previous:
            same_family = move.get("family") == previous.get("family")
            decay = 1.0 / family_run if same_family else 1.0
            score += decay * MARKOV_PAIRS.get(
                previous["move_id"], {}).get(move["move_id"], 0.0)
            if same_family and move.get("lead") != previous.get("lead"):
                # A mirrored pair is useful; a third and fourth copy is a
                # generator tic.  This mirrors the main assembler's decay so
                # gap filling does not turn two lyric vines into a wall of
                # repeated vines.
                score += 2.5 * decay
            if same_family:
                score -= 1.8 * max(0, family_run - 1)
            if (move["move_id"] == previous["move_id"] and
                    move.get("lead") == previous.get("lead")):
                score -= 1.5
        end = pos + move["counts"]
        score += 1.0 if end % 8 == 0 else 0.4 if end % 4 == 0 else 0.0
        absolute_travel = floor_travel(move.get("travel", ""), rot)
        if absolute_travel:
            if absolute_travel == travel_dir:
                score -= 1.2 * (travel_run / 2.0)
            if travel_run == 0 and not travel_dir:
                score += 0.2
        else:
            score += 0.4 * min(travel_run, 4) / 4.0
        if measured_bpm is not None:
            pressure = max(0.0, (measured_bpm - 116.0) / 16.0)
            preferred_max = move.get("preferred_bpm_max", VALIDATED_MAX_BPM)
            over_preferred = max(0.0, measured_bpm - preferred_max) / 8.0
            score -= float(move.get("high_tempo_penalty", 0.0)) * (
                pressure + over_preferred)
            if pressure and move.get("travel"):
                score -= 0.8 * pressure
            if pressure and move.get("turning"):
                score -= 0.7 * pressure
            if previous and pressure:
                if previous.get("travel") and move.get("travel"):
                    score -= 0.9 * pressure
                if previous.get("turning") and move.get("turning"):
                    score -= 0.5 * pressure
                if move.get("family") == previous.get("family"):
                    score -= 0.5 * pressure * max(0, family_run - 1)
        return score + rng.gauss(0.0, 0.45)

    def dfs(pos, foot, rot, travel_dir, travel_run, previous, sequence,
            family_run=1):
        if len(solutions) >= candidate_pool or nodes[0] >= node_budget:
            return
        if pos == total_counts:
            if foot == start_foot and rot == target:
                solutions.append(list(sequence))
            return
        ranked = []
        for move, slot in choices(pos, foot):
            nxt = step(move, foot, rot, travel_dir, travel_run)
            if not nxt or not reachable(pos + move["counts"], *nxt):
                continue
            ranked.append((choice_score(
                move, previous, pos, rot, travel_dir, travel_run,
                family_run, slot is not None),
                           move, nxt))
        ranked.sort(key=lambda item: -item[0])
        for _, move, nxt in ranked:
            nodes[0] += 1
            sequence.append(move)
            next_family_run = (family_run + 1
                               if previous and
                               move.get("family") == previous.get("family")
                               else 1)
            dfs(pos + move["counts"], *nxt, move, sequence,
                next_family_run)
            sequence.pop()
            if len(solutions) >= candidate_pool or nodes[0] >= node_budget:
                return

    dfs(0, start_foot, 0, "", 0, None, [])
    if not solutions:
        raise AssemblyError(
            "SEARCH_BUDGET_EXCEEDED",
            "The lyric-gap search reached its safety limit without a complete dance.",
            {"nodes": nodes[0]})

    def similarity(left, right):
        a, b = Counter(move["move_id"] for move in left), Counter(
            move["move_id"] for move in right)
        return sum((a & b).values()) / max(len(left), len(right))

    ranked_solutions = sorted(
        ((_quality_profile(solution, total_counts, publication_mode), solution)
         for solution in solutions),
        key=lambda item: item[0]["score"], reverse=True)
    picked = []
    for quality, solution in ranked_solutions:
        if picked and any(similarity(solution, item["moves"]) >= 0.82
                          for item in picked):
            continue
        position = 0
        provenance = []
        for move in solution:
            slot = anchor_by_start.get(position)
            if slot:
                provenance.append({
                    "kind": "lyric", "start_count": position + 1,
                    "detection_id": slot["detection_id"],
                    "source_text": slot["source_text"],
                    "confidence": slot["confidence"],
                })
            else:
                provenance.append({"kind": "gap_fill", "start_count": position + 1})
            position += move["counts"]
        quality = dict(quality)
        quality["strengths"] = [
            f"{len(slots)} lyric move{'s' if len(slots) != 1 else ''} locked"
        ] + list(quality.get("strengths") or [])
        net = sum(move["rot"] for move in solution) % 360
        picked.append({
            "moves": solution, "provenance": provenance,
            "net_rot": net, "walls": wall_count(net), "seed": seed,
            "quality": quality,
        })
        if len(picked) >= k:
            break
    if not picked:
        quality, solution = ranked_solutions[0]
        picked.append({"moves": solution, "provenance": [],
                       "net_rot": sum(move["rot"] for move in solution) % 360,
                       "walls": wall_count(sum(move["rot"] for move in solution) % 360),
                       "seed": seed, "quality": quality})

    gaps = []
    cursor = 0
    for slot in slots:
        if slot["start"] > cursor:
            gaps.append({"start_count": cursor + 1, "end_count": slot["start"],
                         "counts": slot["start"] - cursor})
        cursor = slot["end"]
    if cursor < total_counts:
        gaps.append({"start_count": cursor + 1, "end_count": total_counts,
                     "counts": total_counts - cursor})
    public_slots = [{key: slot[key] for key in (
        "start_count", "move_id", "lead", "source_text", "detection_id",
        "confidence")}
                    for slot in slots]
    return {
        "candidates": picked, "anchors": public_slots, "gaps": gaps,
        "target_rot": target, "nodes": nodes[0], "tempo": tempo,
    }


def _rot_achievable(moves, total_counts, start_foot, target_rot):
    """Is `target_rot` reachable at all (counts + feet + travel cap)?  Helper
    for the INFEASIBLE_WALL diagnostic, which must report the closest
    rotation actually achievable — including ones only reachable by
    COMBINING moves, not just single-move rotations."""
    @lru_cache(maxsize=None)
    def reach(pos, foot, rot, tdir, trun):
        if pos == total_counts:
            return foot == start_foot and rot == target_rot
        bend = _block_end(pos, total_counts)
        for m in moves:
            if m["counts"] > bend - pos:
                continue
            if m["start"] not in (foot, "F"):
                continue
            fdir = floor_travel(m.get("travel", ""), rot)
            if fdir:
                nrun = (trun + m["counts"]) if fdir == tdir else m["counts"]
                if nrun > TRAVEL_RUN_CAP:
                    continue
                ntdir = fdir
            else:
                ntdir, nrun = "", 0
            nfoot = foot if m["end"] == "SAME" else m["end"]
            if reach(pos + m["counts"], nfoot, (rot + m["rot"]) % 360,
                     ntdir, nrun):
                return True
        return False
    return reach(0, start_foot, 0, "", 0)


def validate_sequence(move_instances, total_counts, wall, turn_dir="L",
                      start_foot="R", bpm=None):
    """Live validator for the manual editor.  Returns a report dict, never
    raises: the editor needs to show problems, not crash on them."""
    target = _target_rot(wall, turn_dir) if wall in ("1", "2", "4") else None
    problems = []
    notes = []
    pos, foot, rot = 0, start_foot, 0
    tdir, trun, worst_run, net = "", 0, 0, [0, 0]
    for i, m in enumerate(move_instances):
        fdir = floor_travel(m.get("travel", ""), rot)
        if fdir:
            trun = (trun + m["counts"]) if fdir == tdir else m["counts"]
            tdir = fdir
            worst_run = max(worst_run, trun)
            dx, dy = {"N": (0, 1), "S": (0, -1), "E": (1, 0), "W": (-1, 0)}.get(fdir, (0, 0))
            net[0] += dx
            net[1] += dy
        else:
            tdir, trun = "", 0
        if m["start"] not in (foot, "F"):
            problems.append({
                "index": i, "code": "FOOT_BREAK",
                "message": f"Step {i+1} ({m['name']}) needs the {m['start']} foot "
                           f"free but the {foot} foot is free here."})
            foot = m["start"] if m["start"] in ("R", "L") else foot
        bend = _block_end(pos, max(total_counts, pos + m["counts"]))
        if pos < total_counts and m["counts"] > bend - pos:
            problems.append({
                "index": i, "code": "BLOCK_STRADDLE",
                "message": f"Step {i+1} ({m['name']}) straddles the 8-count "
                           f"boundary at count {bend}."})
        pos += m["counts"]
        foot = foot if m["end"] == "SAME" else m["end"]
        rot = (rot + m["rot"]) % 360
    if pos != total_counts:
        problems.append({
            "index": None, "code": "COUNT_MISMATCH",
            "message": f"Sequence is {pos} counts; the pattern needs exactly "
                       f"{total_counts}."})
    if pos == total_counts and foot != start_foot:
        problems.append({
            "index": None, "code": "FOOT_PARITY",
            "message": f"Dance ends with the {foot} foot free but must end "
                       f"with {start_foot} free to loop."})
    if target is not None and rot != target:
        problems.append({
            "index": None, "code": "WALL_MISMATCH",
            "message": f"Net rotation is {rot} deg; a {wall}-wall dance needs "
                       f"{target} deg. This sequence makes a "
                       f"{wall_count(rot)}-wall dance."})
    # Travel is advisory in the editor: a human may deliberately choose a
    # long traveling run.  The generator treats the same cap as hard.
    if worst_run > TRAVEL_RUN_CAP:
        notes.append(f"Travels {worst_run} counts in one direction without a "
                     f"break (over the {TRAVEL_RUN_CAP}-count guide) — check "
                     "it still fits a packed floor.")
    if abs(net[0]) + abs(net[1]) > 4:
        notes.append(f"Each pass ends about {abs(net[0])} steps sideways and "
                     f"{abs(net[1])} steps forward/back from where it started.")
    tempo = _tempo_status(bpm, experimental_mode=True) if bpm is not None else \
        _tempo_status(None, experimental_mode=False)
    if tempo["mode"] == "experimental":
        notes.insert(0, f"{tempo['bpm']:.0f} BPM exceeds the validated "
                     f"{VALIDATED_MAX_BPM} BPM range — manual review is required "
                     "before teaching or publishing.")
    elif tempo["mode"] == "normal" and tempo["bpm"] >= 125:
        high_risk = [m["name"] for m in move_instances
                     if m.get("high_tempo_penalty", 0) >= 1.2]
        if high_risk:
            notes.append("Fast-tempo review: " + ", ".join(high_risk[:3]) +
                         " carries extra timing or transition risk at this BPM.")
    return {
        "valid": not problems,
        "problems": problems,
        "notes": notes,
        "counts": pos,
        "end_foot": foot,
        "net_rot": rot,
        "walls": wall_count(rot),
        "max_travel_run": worst_run,
        "net_travel": {"sideways": net[0], "forward": net[1]},
        "tempo": tempo,
    }
