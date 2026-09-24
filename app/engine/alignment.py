"""Lyric-to-audio alignment for reviewable dance-section timing.

WhisperX transcribes the uploaded song and refines word times through forced
alignment.  The app then matches the supplied lyric lines to those timed words.
This is intentionally a proposal: a singer, ad-lib, or dense mix can confuse
ASR, so callers must explicitly accept suggested markers before they replace a
project's hand-edited sections.
"""
import gc
import os
import re
import statistics
from difflib import SequenceMatcher

from .phrasing import parse_tagged_lyrics


class AlignmentError(Exception):
    """A user-facing failure while creating timed lyrics."""


WORD_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?", re.I)


def _section_name(label):
    """Keep Suno's detailed production note out of an editable marker name."""
    return (label or "Lyrics").split("|", 1)[0].strip() or "Lyrics"


def _word(value):
    """Normalize a word just enough for a conservative lyric comparison."""
    found = WORD_RE.findall((value or "").lower().replace("’", "'"))
    return "".join(found)


def _expected_lines(lyrics_text):
    """Return lyric lines with their Suno label retained as a section hint."""
    tagged = parse_tagged_lyrics(lyrics_text)
    lines = []
    if tagged:
        for section_index, section in enumerate(tagged):
            for text in section.get("lyrics", "").splitlines():
                text = text.strip()
                if text:
                    lines.append({"label": _section_name(section["label"]), "text": text,
                                  "section_index": section_index})
    else:
        for text in (lyrics_text or "").splitlines():
            text = text.strip()
            if text and not (text.startswith("[") and text.endswith("]")):
                lines.append({"label": "Lyrics", "text": text,
                              "section_index": 0})
    return lines


def _nearest(value, grid):
    if not grid:
        return round(float(value), 3)
    return round(min(grid, key=lambda point: abs(point - value)), 3)


def _seconds_per_beat(analysis):
    """Return a dependable beat duration without inventing a tempo."""
    analysis = analysis or {}
    try:
        seconds = float(analysis.get("seconds_per_beat"))
        if seconds > 0:
            return seconds
    except (TypeError, ValueError):
        pass
    try:
        bpm = float(analysis.get("bpm"))
        if bpm > 0:
            return 60.0 / bpm
    except (TypeError, ValueError):
        pass
    beats = []
    for value in analysis.get("beat_times") or []:
        try:
            beats.append(float(value))
        except (TypeError, ValueError):
            continue
    intervals = [right - left for left, right in zip(beats, beats[1:])
                 if right > left]
    return statistics.median(intervals) if intervals else None


def _bounded_downbeat(value, analysis):
    """Snap to a downbeat only when it is no farther than one beat away."""
    raw = round(float(value), 3)
    analysis = analysis or {}
    grid = []
    for point in analysis.get("downbeat_times") or []:
        try:
            grid.append(float(point))
        except (TypeError, ValueError):
            continue
    seconds_per_beat = _seconds_per_beat(analysis)
    weak_phase = (analysis.get("phase_contrast") is not None and
                  float(analysis.get("phase_contrast") or 0) < 0.05)
    if not grid or not seconds_per_beat or weak_phase:
        return raw, False, None
    nearest = min(grid, key=lambda point: abs(point - raw))
    delta = abs(nearest - raw)
    if delta <= seconds_per_beat + 1e-9:
        return round(nearest, 3), True, round(delta, 3)
    return raw, False, round(delta, 3)


def _transcript_rows(transcript_segments):
    """Normalize WhisperX segments while retaining only real word timings."""
    words = []
    rows = []
    raw_captions = []
    for segment in transcript_segments or []:
        timed = []
        for item in segment.get("words") or []:
            token = _word(item.get("word"))
            if not token or item.get("start") is None or item.get("end") is None:
                continue
            try:
                start = float(item["start"])
                end = float(item["end"])
            except (TypeError, ValueError):
                continue
            if start < 0 or end <= start:
                continue
            try:
                score = (round(float(item.get("score")), 3)
                         if item.get("score") is not None else None)
            except (TypeError, ValueError):
                score = None
            word = {
                "word": (item.get("word") or "").strip(),
                "normalized": token,
                "start": round(start, 3),
                "end": round(end, 3),
                "score": score,
            }
            words.append(word)
            timed.append(word)
        text = (segment.get("text") or "").strip()
        if not text and timed:
            text = " ".join(item["word"] for item in timed)
        if timed:
            start, end = timed[0]["start"], timed[-1]["end"]
            raw_captions.append({"text": text, "start": start, "end": end})
            scores = [item["score"] for item in timed if item["score"] is not None]
            rows.append({
                "text": text,
                "tokens": [item["normalized"] for item in timed],
                "words": timed,
                "start": start,
                "end": end,
                # A valid timestamp is useful evidence even when WhisperX did
                # not expose a per-word alignment score.
                "confidence": (sum(scores) / len(scores)) if scores else 0.75,
            })
        elif text:
            start = segment.get("start")
            end = segment.get("end")
            raw_captions.append({"text": text, "start": start, "end": end})
    rows.sort(key=lambda row: (row["start"], row["end"], row["text"]))
    return rows, words, raw_captions


def _vocal_blocks(rows, analysis):
    """Join nearby caption rows into conservative, pause-delimited blocks."""
    seconds_per_beat = _seconds_per_beat(analysis)
    # Two clearly separated lyric phrases should not be fused merely because
    # Whisper chose an inconvenient sentence boundary.  Conversely, tiny ASR
    # segmentation gaps within a sung line are not song-section evidence.
    join_gap = max(0.75, (seconds_per_beat or 0.5) * 1.5)
    blocks = []
    for row in rows:
        if (blocks and row["start"] - blocks[-1]["end"] <= join_gap):
            block = blocks[-1]
            block["rows"].append(row)
            block["tokens"].extend(row["tokens"])
            block["end"] = max(block["end"], row["end"])
            if row["text"]:
                block["texts"].append(row["text"])
        else:
            blocks.append({
                "rows": [row], "tokens": list(row["tokens"]),
                "texts": [row["text"]] if row["text"] else [],
                "start": row["start"], "end": row["end"],
            })
    for block in blocks:
        confidences = [row["confidence"] for row in block["rows"]]
        block["confidence"] = sum(confidences) / len(confidences)
        block["text"] = "\n".join(block["texts"])
    return blocks


def _block_similarity(left, right):
    """Conservative evidence that two complete lyric blocks repeat."""
    a, b = left.get("tokens") or [], right.get("tokens") or []
    if min(len(a), len(b)) < 3:
        return 0.0
    length_ratio = min(len(a), len(b)) / max(len(a), len(b))
    if length_ratio < 0.7:
        return 0.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def _scan_labels(blocks):
    """Name repeated hooks as choruses and leave everything else modest."""
    pairs = []
    for left in range(len(blocks)):
        for right in range(left + 1, len(blocks)):
            similarity = _block_similarity(blocks[left], blocks[right])
            if similarity >= 0.82:
                pairs.append((similarity, left, right))

    chorus_members = set()
    chorus_similarity = 0.0
    if pairs:
        # Build connected repeat clusters, then select the strongest cluster.
        parent = list(range(len(blocks)))

        def find(index):
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def union(left, right):
            left, right = find(left), find(right)
            if left != right:
                parent[max(left, right)] = min(left, right)

        for _, left, right in pairs:
            union(left, right)
        clusters = {}
        for index in range(len(blocks)):
            clusters.setdefault(find(index), []).append(index)
        repeated = [members for members in clusters.values() if len(members) >= 2]
        if repeated:
            def cluster_key(members):
                evidence = [score for score, left, right in pairs
                            if left in members and right in members]
                mean = sum(evidence) / len(evidence) if evidence else 0.0
                token_support = sum(len(blocks[index]["tokens"])
                                    for index in members)
                return (token_support * mean, len(members), -members[0])

            selected = max(repeated, key=cluster_key)
            chorus_members = set(selected)
            evidence = [score for score, left, right in pairs
                        if left in chorus_members and right in chorus_members]
            chorus_similarity = sum(evidence) / len(evidence)

    labels = []
    chorus_number = 0
    verse_number = 0
    section_number = 0
    has_chorus = bool(chorus_members)
    for index in range(len(blocks)):
        if index in chorus_members:
            chorus_number += 1
            labels.append({
                "label": f"Chorus {chorus_number}",
                "source": "repeated_lyrics",
                "confidence": round(min(0.97, 0.78 + 0.19 * chorus_similarity), 3),
                "evidence": {"repeat_similarity": round(chorus_similarity, 3)},
            })
        elif has_chorus:
            verse_number += 1
            labels.append({
                "label": f"Verse {verse_number}",
                "source": "sequence_between_repeated_hooks",
                "confidence": 0.55,
                "evidence": {"note": "Unique vocal block; verify the section name."},
            })
        else:
            section_number += 1
            labels.append({
                "label": f"Section {section_number}",
                "source": "vocal_block",
                "confidence": 0.4,
                "evidence": {"note": "No repeated hook proved a verse/chorus name."},
            })
    return labels


def _span_metadata(start, end, beat_times):
    start, end = round(max(0.0, float(start)), 3), round(max(0.0, float(end)), 3)
    return {
        "start": start,
        "end": end,
        "duration": round(max(0.0, end - start), 3),
        "measured_beats": sum(1 for beat in beat_times if start <= beat < end),
        "present": end > start,
    }


def build_lyric_scan(transcript_segments, analysis=None):
    """Create a deterministic, reviewable song-section draft from ASR words.

    This intentionally does not pretend that transcription can hear every
    instrumental arrangement change.  It uses vocal pauses as boundaries and
    calls a block a chorus only when another complete block repeats.  The
    first and last suggested markers bound the vocals; intro/outro remain
    metadata so ``phrase_check`` can measure the real intro before Count 1.
    """
    analysis = analysis or {}
    rows, words, raw_captions = _transcript_rows(transcript_segments)
    issues = []
    timed_token_count = sum(len(row["tokens"]) for row in rows)
    if not rows or timed_token_count < 2:
        return {
            "mode": "auto_scan", "lyrics_text": "", "status": "BLOCKED",
            "issues": [{
                "severity": "error", "code": "NO_DEPENDABLE_VOCALS",
                "message": ("No dependable timed vocals were found. The scanner did not "
                            "invent song sections; add markers by ear or try a cleaner vocal stem."),
            }],
            "captions": [], "words": words, "raw_captions": raw_captions,
            "suggested_sections": [],
            "summary": {"lyric_lines": len(raw_captions), "timed_lines": 0,
                        "matched_words": 0, "expected_words": timed_token_count,
                        "confidence": 0.0},
            "intro": None, "outro": None, "accepted": False,
            "manual_decision": None,
        }

    blocks = _vocal_blocks(rows, analysis)
    labels = _scan_labels(blocks)
    beat_times = []
    for value in analysis.get("beat_times") or []:
        try:
            beat_times.append(float(value))
        except (TypeError, ValueError):
            continue
    duration = max(float(analysis.get("duration") or 0), blocks[-1]["end"])

    raw_boundaries = [blocks[0]["start"]]
    for left, right in zip(blocks, blocks[1:]):
        raw_boundaries.append((left["end"] + right["start"]) / 2.0)
    raw_boundaries.append(blocks[-1]["end"])

    boundary_rows = []
    for index, raw in enumerate(raw_boundaries):
        snapped, used_grid, delta = _bounded_downbeat(raw, analysis)
        # A snap that crosses the neighboring raw seam can collapse or reorder
        # sections.  In that case the vocal timestamp is safer.
        lower = raw_boundaries[index - 1] if index else -1.0
        upper = (raw_boundaries[index + 1]
                 if index + 1 < len(raw_boundaries) else duration + 1.0)
        if snapped <= lower or snapped >= upper:
            snapped, used_grid, delta = round(raw, 3), False, delta
        word_confidences = []
        if index > 0:
            word_confidences.append(blocks[index - 1]["confidence"])
        if index < len(blocks):
            word_confidences.append(blocks[index]["confidence"])
        word_confidence = (sum(word_confidences) / len(word_confidences)
                           if word_confidences else 0.75)
        if used_grid:
            seconds_per_beat = _seconds_per_beat(analysis) or 1.0
            timing = max(0.6, 0.95 - 0.3 * ((delta or 0) / seconds_per_beat))
            evidence = "nearby_downbeat"
        else:
            timing = 0.48 if analysis.get("downbeat_times") else 0.38
            evidence = "vocal_timestamp"
        boundary_rows.append({
            "raw_time": round(raw, 3), "time": round(snapped, 3),
            "snapped": used_grid, "snap_delta": delta,
            "confidence": round(0.55 * timing + 0.45 * word_confidence, 3),
            "evidence": evidence,
        })

    # A final deterministic guard protects the flat section contract consumed
    # by the waveform editor: every section must share exactly one seam.
    for index in range(1, len(boundary_rows)):
        if boundary_rows[index]["time"] <= boundary_rows[index - 1]["time"]:
            boundary_rows[index]["time"] = round(raw_boundaries[index], 3)
            boundary_rows[index]["snapped"] = False
            boundary_rows[index]["evidence"] = "vocal_timestamp"
            boundary_rows[index]["confidence"] = min(
                boundary_rows[index]["confidence"], 0.48)

    sections = []
    for index, (block, label) in enumerate(zip(blocks, labels)):
        start_boundary = boundary_rows[index]
        end_boundary = boundary_rows[index + 1]
        boundary_confidence = round(min(start_boundary["confidence"],
                                        end_boundary["confidence"]), 3)
        label_confidence = label["confidence"]
        review_required = boundary_confidence < 0.75 or label_confidence < 0.75
        confidence = round((boundary_confidence + label_confidence) / 2.0, 3)
        sections.append({
            "label": label["label"],
            "start": start_boundary["time"], "end": end_boundary["time"],
            "confidence": confidence,
            "boundary_confidence": boundary_confidence,
            "label_confidence": label_confidence,
            "label_source": label["source"],
            "label_evidence": label["evidence"],
            "review_required": review_required,
            "matched_lines": len(block["rows"]),
        })

    if not analysis.get("downbeat_times"):
        issues.append({
            "severity": "warn", "code": "NO_DOWNBEAT_GRID",
            "message": "No downbeat grid was available, so vocal timestamps were kept unsnapped.",
        })
    if (analysis.get("phase_contrast") is not None and
            float(analysis.get("phase_contrast") or 0) < 0.05):
        issues.append({
            "severity": "warn", "code": "WEAK_DOWNBEAT",
            "message": "Downbeat detection is weak; no automatic downbeat snapping was trusted.",
        })
    if analysis.get("octave_alternates"):
        issues.append({
            "severity": "warn", "code": "OCTAVE_AMBIGUOUS",
            "message": "The tempo has a half/double-time alternative; verify the grid by ear.",
        })
    issues.append({
        "severity": "info", "code": "INFERRED_LABELS",
        "message": "Section names were inferred from vocal repetition and require review.",
    })

    captions = []
    row_index = 0
    for section_index, (block, label) in enumerate(zip(blocks, labels)):
        for row in block["rows"]:
            row_index += 1
            captions.append({
                "id": row_index, "label": label["label"], "text": row["text"],
                "section_index": section_index,
                "start": row["start"], "end": row["end"],
                "confidence": round(row["confidence"], 3),
                "matched_words": len(row["tokens"]),
                "total_words": len(row["tokens"]), "status": "matched",
            })

    lyrics_text = "\n\n".join(
        f"[{section['label']}]\n{block['text']}"
        for section, block in zip(sections, blocks)
    )
    known_scores = [word["score"] for word in words if word["score"] is not None]
    transcript_confidence = (sum(known_scores) / len(known_scores)
                             if known_scores else 0.75)
    first, last = sections[0]["start"], sections[-1]["end"]
    intro = _span_metadata(0.0, first, beat_times)
    outro = _span_metadata(last, duration, beat_times)
    status = "REVIEW" if (issues or any(row["review_required"] for row in sections)) else "CLEAN"
    return {
        "mode": "auto_scan", "lyrics_text": lyrics_text, "status": status,
        "issues": issues, "captions": captions, "words": words,
        "raw_captions": raw_captions, "suggested_sections": sections,
        "boundaries": boundary_rows,
        "summary": {
            "lyric_lines": len(captions), "timed_lines": len(captions),
            "matched_words": timed_token_count, "expected_words": timed_token_count,
            "confidence": round(transcript_confidence, 3),
        },
        "vocal_span": {"start": first, "end": last},
        "intro": intro, "outro": outro,
        "accepted": False, "manual_decision": None,
    }


def build_alignment(transcript_segments, lyrics_text, downbeat_times=None):
    """Match known lyric lines to WhisperX word timestamps.

    ``transcript_segments`` uses the public WhisperX shape: each segment has a
    text field and zero or more words with ``word``, ``start``, and ``end``.
    Keeping this pure makes the editorial behavior testable without loading a
    speech model.
    """
    timed_words = []
    raw_captions = []
    for segment in transcript_segments or []:
        words = []
        for item in segment.get("words") or []:
            token = _word(item.get("word"))
            if not token or item.get("start") is None or item.get("end") is None:
                continue
            word = {
                "word": item.get("word", "").strip(),
                "normalized": token,
                "start": round(float(item["start"]), 3),
                "end": round(float(item["end"]), 3),
                "score": round(float(item.get("score", 0)), 3) if item.get("score") is not None else None,
            }
            timed_words.append(word)
            words.append(word)
        if words:
            raw_captions.append({
                "text": (segment.get("text") or "").strip(),
                "start": words[0]["start"], "end": words[-1]["end"],
            })

    expected = _expected_lines(lyrics_text)
    expected_tokens = []
    line_ranges = []
    for line in expected:
        start = len(expected_tokens)
        expected_tokens.extend(_word(part) for part in line["text"].split() if _word(part))
        line_ranges.append((start, len(expected_tokens)))
    actual_tokens = [item["normalized"] for item in timed_words]

    # Exact, in-order matching is intentionally conservative.  It avoids
    # presenting a confident timestamp when the recognizer heard a different
    # lyric; unmatched lines stay visible for the human to place or ignore.
    matched = {}
    matcher = SequenceMatcher(None, expected_tokens, actual_tokens, autojunk=False)
    for tag, a0, a1, b0, b1 in matcher.get_opcodes():
        if tag == "equal":
            matched.update({a0 + offset: b0 + offset for offset in range(a1 - a0)})

    captions = []
    for index, (line, bounds) in enumerate(zip(expected, line_ranges), start=1):
        a0, a1 = bounds
        matched_positions = [matched[pos] for pos in range(a0, a1) if pos in matched]
        total = a1 - a0
        confidence = round(len(matched_positions) / total, 3) if total else 0.0
        if matched_positions:
            first, last = min(matched_positions), max(matched_positions)
            start, end = timed_words[first]["start"], timed_words[last]["end"]
        else:
            start = end = None
        captions.append({
            "id": index, "label": line["label"], "text": line["text"],
            "section_index": line["section_index"],
            "start": start, "end": end, "confidence": confidence,
            "matched_words": len(matched_positions), "total_words": total,
            "status": "matched" if matched_positions else "unmatched",
        })

    # Keep repeated names separate.  A song can have three [Chorus] blocks;
    # folding them into one giant section would make its suggestion useless.
    suggested_sections = []
    runs = []
    active = None
    for caption in captions:
        if active and caption["section_index"] != active["section_index"]:
            runs.append(active)
            active = None
        if caption["start"] is None:
            continue
        if active is None:
            active = {"label": caption["label"],
                      "section_index": caption["section_index"],
                      "rows": [caption]}
        else:
            active["rows"].append(caption)
    if active:
        runs.append(active)

    for run in runs:
        label, rows = run["label"], run["rows"]
        confidence = round(sum(row["confidence"] for row in rows) / len(rows), 3)
        start = _nearest(min(row["start"] for row in rows), downbeat_times or [])
        end = _nearest(max(row["end"] for row in rows), downbeat_times or [])
        if end <= start:
            end = round(max(row["end"] for row in rows), 3)
        if end > start:
            suggested_sections.append({"label": label, "start": start, "end": end,
                                       "confidence": confidence,
                                       "matched_lines": len(rows)})

    total_expected = len(expected_tokens)
    total_matched = len(matched)
    return {
        "captions": captions,
        "words": timed_words,
        "raw_captions": raw_captions,
        "suggested_sections": suggested_sections,
        "summary": {
            "lyric_lines": len(expected),
            "timed_lines": sum(1 for row in captions if row["start"] is not None),
            "matched_words": total_matched,
            "expected_words": total_expected,
            "confidence": round(total_matched / total_expected, 3) if total_expected else 0.0,
        },
    }


def _transcribe_with_whisperx(path, progress=None, refine_timestamps=True):
    """Transcribe a full song, optionally refining words with WhisperX."""
    try:
        import torch
        import whisperx
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise AlignmentError(
            "Lyric alignment is not installed yet. Install the optional WhisperX "
            "package, then restart Line Dance Creator.") from exc

    def note(message):
        if progress:
            progress(message)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    model_name = os.environ.get("LINE_DANCE_WHISPER_MODEL", "small")
    language_hint = os.environ.get("LINE_DANCE_WHISPER_LANGUAGE", "en")
    try:
        note(f"Loading the {model_name} lyric model ({device})...")
        # Speech-oriented VADs can classify sustained singing over a loud mix as
        # silence.  Analyze the complete recording in Faster Whisper's normal
        # windows, then retain WhisperX for its more precise word alignment.
        # This also avoids WhisperX's legacy Pyannote checkpoint without
        # weakening PyTorch's safe checkpoint-loading defaults.
        model = WhisperModel(
            model_name, device=device, compute_type=compute_type,
            cpu_threads=max(1, min(4, os.cpu_count() or 1)),
        )
        audio = whisperx.load_audio(path)
        note("Transcribing vocals across the full song...")
        raw_segments, info = model.transcribe(
            audio,
            language=language_hint,
            task="transcribe",
            beam_size=5,
            best_of=5,
            word_timestamps=True,
            vad_filter=False,
            no_speech_threshold=0.6,
            condition_on_previous_text=True,
        )
        segments = []
        for segment in raw_segments:
            if not str(segment.text or "").strip():
                continue
            row = {
                "start": float(segment.start), "end": float(segment.end),
                "text": segment.text,
            }
            words = []
            for item in (getattr(segment, "words", None) or []):
                if item.start is None or item.end is None:
                    continue
                probability = getattr(item, "probability", None)
                words.append({
                    "word": item.word,
                    "start": float(item.start),
                    "end": float(item.end),
                    "score": (float(probability)
                              if probability is not None else None),
                })
            if words:
                row["words"] = words
            segments.append(row)
        language = getattr(info, "language", None) or language_hint
        del model
        gc.collect()
        if device == "cuda":
            torch.cuda.empty_cache()

        if not refine_timestamps:
            return segments, {
                "engine": "faster-whisper",
                "model": model_name,
                "device": device,
                "transcription_mode": "full_song",
                "language": language,
            }

        note("Refining word timestamps...")
        align_model, metadata = whisperx.load_align_model(
            language_code=language, device=device)
        aligned = whisperx.align(segments, align_model, metadata,
                                 audio, device, return_char_alignments=False)
        del align_model
        gc.collect()
        if device == "cuda":
            torch.cuda.empty_cache()
    except Exception as exc:
        raise AlignmentError(f"Lyric alignment could not finish: {exc}") from exc

    return aligned.get("segments", []), {
        "engine": "whisperx",
        "model": model_name,
        "device": device,
        "transcription_mode": "full_song",
        "language": language,
    }


def align(path, lyrics_text, analysis=None, progress=None):
    """Run local WhisperX and return a reviewable alignment payload.

    Models download on first use.  CPU is supported for ordinary laptops but
    can take longer; CUDA is selected automatically when available.
    """
    if not _expected_lines(lyrics_text):
        raise AlignmentError("Paste the song lyrics first so their words can be timed.")

    segments, metadata = _transcribe_with_whisperx(path, progress=progress)

    def note(message):
        if progress:
            progress(message)

    note("Matching your lyrics to the timed vocal words...")
    payload = build_alignment(segments, lyrics_text,
                              (analysis or {}).get("downbeat_times"))
    payload.update(metadata)
    payload.update({"accepted": False, "manual_decision": None})
    return payload


def scan(path, analysis=None, progress=None):
    """Transcribe a song and return a conservative automatic section draft."""
    # Faster Whisper's own timed singing transcript keeps the natural phrase
    # gaps used for section discovery. Forced alignment remains available for
    # matching lyrics the user pastes, but is unnecessary for an auto draft.
    segments, metadata = _transcribe_with_whisperx(
        path, progress=progress, refine_timestamps=False)
    if progress:
        progress("Building a reviewable lyric and section draft...")
    payload = build_lyric_scan(segments, analysis=analysis)
    payload.update(metadata)
    return payload
