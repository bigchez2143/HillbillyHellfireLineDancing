"""Human-first music mapping and behind-the-scenes dance-fit analysis.

The dancer's manually placed song sections are always the source of truth.
This module measures the beat grid *against* those markers and builds a
continuous count overlay for choreography.  It never rounds, shifts, or
replaces a musical boundary just to make a 16/32/64-count dance look neat.
"""
import re


# SQUARE BRACKETS ONLY. Parenthesised lines are lyric ad-libs, not section tags.
SECTION_TAG_RE = re.compile(r"^\s*\[\s*([^\]]+?)\s*\]\s*$")

# Suno directives that are production instructions, not timed song sections.
DIRECTIVE_WORDS = {
    "end", "fade out", "fadeout", "fade", "big finish", "stop", "silence",
    "spoken", "ad lib", "adlib", "vocal fry", "whisper", "shout", "harmony",
    "build", "drop", "riff", "accelerando", "ritardando",
}


def _is_directive(label):
    key = label.strip().lower().strip("!.")
    if key in DIRECTIVE_WORDS:
        return True
    return any(key == word or key.startswith(word + " ")
               for word in ("end", "fade"))


def parse_tagged_lyrics(text):
    """Parse Suno-style tags as label/order hints only, never as timing."""
    sections = []
    current = None
    for raw in (text or "").splitlines():
        match = SECTION_TAG_RE.match(raw)
        if match:
            label = match.group(1).strip()
            if not label or _is_directive(label):
                continue
            current = {"label": label, "lyrics": []}
            sections.append(current)
        else:
            line = raw.strip()
            if line and current is not None:
                current["lyrics"].append(line)
    for section in sections:
        section["lyrics"] = "\n".join(section["lyrics"])
    return sections


def _beats_in(beat_times, start, end):
    return sum(1 for time in beat_times if start <= time < end)


def _round8(count):
    return int(round(count / 8.0)) * 8


def _fold_residual(count):
    """Distance from the nearest multiple of eight, folded to [-4, 4)."""
    remainder = count % 8
    return remainder - 8 if remainder >= 4 else remainder


def _nearest_time(times, target):
    if not times:
        return None
    return min(times, key=lambda time: abs(time - target))


def _marker_offset_ms(beat_times, target):
    """Return signed distance from the nearest detected beat, never a correction."""
    nearest = _nearest_time(beat_times, target)
    if nearest is None:
        return None
    return int(round((target - nearest) * 1000))


def _dance_cue(start_count, pattern_len):
    if start_count == 1:
        return f"New {pattern_len}-count dance loop starts here."
    return (f"Keep the dance moving - this song change arrives on "
            f"dance count {start_count}.")


def phrase_check(sections, analysis, pattern_len=32):
    """Measure a user-authored music map and layer a continuous dance count on it.

    ``sections`` are the markers a human placed where the *song* changes. A
    dance pattern may naturally run across a Verse/Chorus/Bridge boundary, so
    a section that is 17, 25, or 40 counts long is information, not an error.
    The returned ``dance_fit`` overlay says how a selected dance loop passes
    through that music without moving a single marker.
    """
    if not sections:
        return {"status": "UNCERTAIN", "flags": [{
            "severity": "error", "code": "NO_SECTIONS",
            "message": "No song sections are mapped yet. Add the musical changes you hear first."
        }], "sections": [], "music_map": {"markers_preserved": True}}

    try:
        pattern_len = int(pattern_len or 32)
    except (TypeError, ValueError):
        pattern_len = 32
    pattern_len = max(1, pattern_len)

    bpm = analysis["bpm"]
    beat_times = analysis.get("beat_times") or []
    duration = analysis["duration"]
    flags = []
    rows = []
    sections = sorted(sections, key=lambda section: section["start"])

    # This intro sits before the first *user-defined* dance/music anchor. It
    # is reported exactly as measured for a stepsheet, never rounded upward.
    intro_beats = _beats_in(beat_times, 0.0, sections[0]["start"])
    intro_residual = _fold_residual(intro_beats)
    if intro_beats and abs(intro_residual) >= 2:
        flags.append({
            "severity": "info", "code": "ODD_INTRO",
            "message": (f"Intro is {intro_beats} measured counts. Keep the musical start "
                        "you chose; use this only as count-in information.")
        })

    total_forward = 0.0
    total_measured = 0
    danced_so_far = 0
    for section in sections:
        start = float(section["start"])
        end = float(section["end"])
        label = section.get("label") or "Untitled section"
        duration_seconds = end - start
        if duration_seconds <= 0:
            flags.append({"severity": "error", "code": "BAD_BOUNDARY",
                          "section": label,
                          "message": f"'{label}' has no length. Check the start and end times."})
            continue

        forward_beats = duration_seconds * bpm / 60.0
        measured_beats = _beats_in(beat_times, start, end)
        residual = _fold_residual(measured_beats)
        total_forward += forward_beats
        total_measured += measured_beats

        # This is an analysis-confidence check, not a judgement on the
        # user's musical marker. The marker is still retained verbatim.
        agree = abs(forward_beats - measured_beats) <= 1.0
        if not agree:
            flags.append({
                "severity": "warn", "code": "PASS_DISAGREE", "section": label,
                "message": (f"The beat grid and clock disagree in '{label}' "
                            f"({forward_beats:.1f} vs {measured_beats} counts). "
                            "Your marker is kept; use your ear before trusting the count overlay here.")
            })

        start_count = danced_so_far % pattern_len + 1
        end_count = ((danced_so_far + measured_beats - 1) % pattern_len + 1
                     if measured_beats else start_count)
        marker_offset = _marker_offset_ms(beat_times, start)
        classification = "clean" if residual == 0 else "mid-phrase"
        if residual:
            flags.append({
                "severity": "info", "code": "ODD_PHRASE", "section": label,
                "message": (f"'{label}' changes the music {residual:+d} counts from an "
                            "eight-count boundary. That is normal song structure: let the "
                            "dance continue, or add a tag/restart only if your choreography wants one.")
            })

        rows.append({
            "label": label, "start": start, "end": end,
            "forward_beats": round(forward_beats, 2),
            "measured_beats": measured_beats,
            "round8": _round8(measured_beats),
            "residual": residual,
            "agree": agree,
            "classification": classification,
            "dance_start_count": start_count,
            "dance_end_count": end_count,
            "dance_cue": _dance_cue(start_count, pattern_len),
            "marker_offset_ms": marker_offset,
        })
        danced_so_far += measured_beats

    # The grid total remains valuable for finding true gaps/overlaps, but it
    # must never overwrite a song-structure decision made by the user.
    span_start = sections[0]["start"]
    span_end = sections[-1]["end"]
    span_beats = _beats_in(beat_times, span_start, span_end)
    if abs(span_beats - total_measured) > 0:
        flags.append({
            "severity": "warn", "code": "SECTION_GAPS",
            "message": ("The beat grid sees a gap or overlap between song sections. "
                        "Your markers were not changed; inspect the seam by ear.")
        })

    outro_beats = _beats_in(beat_times, span_end, duration)
    complete_loops, tail_counts = divmod(total_measured, pattern_len)
    dance_fit = {
        "mode": "continuous",
        "pattern_len": pattern_len,
        "anchor": {"section": rows[0]["label"] if rows else None,
                   "time": sections[0]["start"],
                   "marker_offset_ms": _marker_offset_ms(beat_times, sections[0]["start"])},
        "complete_loops": complete_loops,
        "tail_counts": tail_counts,
        "ending_count": tail_counts or pattern_len,
        "advice": (f"The {pattern_len}-count dance repeats continuously across your music map. "
                   "A song section can begin in the middle of a dance phrase; that does not need correction."),
    }
    # Retained for older saved reports and integrations. Unlike the old model,
    # a non-zero tail is not treated as a mandatory restart.
    tiling = {"pattern_len": pattern_len, "danced_beats": total_measured,
              "repetitions": round(total_measured / pattern_len, 3),
              "clean": tail_counts == 0}

    if analysis.get("octave_alternates"):
        alternatives = ", ".join(str(item["bpm"]) for item in analysis["octave_alternates"])
        flags.append({
            "severity": "warn", "code": "OCTAVE_AMBIGUOUS",
            "message": (f"The recording can be counted at {analysis['bpm']} or {alternatives} BPM. "
                        "Choose the grid that feels right on the floor; the music map stays unchanged.")
        })
    if analysis.get("drift"):
        drift = analysis["drift"]
        flags.append({
            "severity": "error", "code": "TEMPO_DRIFT",
            "message": (f"Tempo drifts {drift['drift_pct']}% across the song "
                        f"({drift['first_half_bpm']} to {drift['second_half_bpm']} BPM). "
                        "Keep the music map, but manually verify a fixed-count dance before publishing.")
        })
    if analysis.get("phase_contrast", 1.0) < 0.05:
        flags.append({
            "severity": "warn", "code": "WEAK_DOWNBEAT",
            "message": ("Downbeat detection is weak. Treat the dance-fit counts as a guide and "
                        "trust the song marker you hear.")
        })

    has_error = any(flag["severity"] == "error" for flag in flags)
    has_warn = any(flag["severity"] == "warn" for flag in flags)
    status = "UNCERTAIN" if has_error else ("REVIEW" if has_warn else "CLEAN")
    return {
        "status": status,
        "flags": flags,
        "sections": rows,
        "music_map": {"markers_preserved": True, "source": "manual"},
        "dance_fit": dance_fit,
        "intro": {"beats": intro_beats, "residual": intro_residual,
                  "suggest": _round8(intro_beats) or intro_beats},
        "outro_beats": outro_beats,
        "tiling": tiling,
        "totals": {"forward": round(total_forward, 1), "measured": total_measured},
        "bpm": bpm,
    }
