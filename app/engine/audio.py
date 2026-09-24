"""Audio analysis: BPM consensus, beat/downbeat grid, waveform peaks.

Adapts the 4-method cross-check from Trends/song-tools/bpmcheck.py (the BPM
oracle per STEERING.md section 9).  Never trusts a label BPM: everything is
measured from the rendered audio.  Octave ambiguity is detected and reported,
never silently resolved.
"""
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import librosa
from librosa.feature.rhythm import tempo as lr_tempo, tempogram as lr_tempogram, \
    tempo_frequencies as lr_tempo_freqs

HOP = 512
SR = 22050

# A tempo estimate only gets to overrule the normal grid-scoring resolution
# when at least three independent methods agree this tightly.  The score floor
# keeps that preference conservative: consensus is evidence, not permission to
# select a grid that the onset envelope does not support.
_CONSENSUS_SPREAD_LIMIT = 0.03
_CONSENSUS_CANDIDATE_LIMIT = 0.03
_CONSENSUS_SCORE_FLOOR = 0.90


def _comb_score(onset, sr, hop, bpm):
    """Metronome-vs-onsets alignment score at every phase (from bpmcheck.py)."""
    period = 60.0 / bpm * sr / hop
    if period < 2 or period > len(onset) / 4:
        return 0.0, 0.0
    n = int((len(onset) - 1) / period)
    if n < 8:
        return 0.0, 0.0
    best, best_ph = 0.0, 0.0
    for ph in np.linspace(0, period, 24, endpoint=False):
        idx = (ph + period * np.arange(n)).astype(int)
        idx = idx[idx < len(onset)]
        s = float(onset[idx].mean())
        if s > best:
            best, best_ph = s, ph
    return best / (float(onset.mean()) + 1e-9), best_ph


def _waveform_peaks(y, n_bins=1600):
    """Min/max peaks per bin for canvas drawing."""
    if len(y) < n_bins:
        n_bins = max(1, len(y))
    edges = np.linspace(0, len(y), n_bins + 1).astype(int)
    mins, maxs = [], []
    for i in range(n_bins):
        seg = y[edges[i]:edges[i + 1]]
        if len(seg) == 0:
            mins.append(0.0)
            maxs.append(0.0)
        else:
            mins.append(float(seg.min()))
            maxs.append(float(seg.max()))
    return {"mins": mins, "maxs": maxs}


def _tight_tempo_consensus(method_tempos, min_methods=3):
    """Return the strongest tight method cluster, or ``None``.

    ``method_tempos`` contains one scalar result per independent estimator.
    A cluster is tight when its total range is no more than 3% of its median.
    Choosing the largest cluster first lets a four-method agreement beat any
    three-method subset; the spread tie-break keeps the result deterministic.
    """
    values = sorted(
        float(value) for value in method_tempos
        if value is not None and np.isfinite(value) and value > 0
    )
    clusters = []
    for start in range(len(values)):
        for stop in range(start + min_methods, len(values) + 1):
            cluster = values[start:stop]
            center = float(np.median(cluster))
            spread = (cluster[-1] - cluster[0]) / center
            if spread <= _CONSENSUS_SPREAD_LIMIT:
                clusters.append((len(cluster), spread, center, cluster))
    if not clusters:
        return None
    size, spread, center, cluster = min(
        clusters, key=lambda item: (-item[0], item[1], item[2])
    )
    return {
        "bpm": center,
        "method_count": size,
        "spread_pct": spread * 100.0,
        "values": cluster,
    }


def _resolve_tempo_candidates(scored, method_tempos):
    """Resolve scored BPM candidates while respecting strong method consensus.

    Without a tight three-method consensus this deliberately reproduces the
    historical behavior: select the best-scoring grid, then prefer a slower
    simple subdivision within 3% of that score.  With consensus, a nearby grid
    may be preferred if it retains at least 90% of the winning onset score.
    """
    ordered = sorted(scored, reverse=True)
    if not ordered:
        raise ValueError("at least one scored tempo candidate is required")

    bestscore, bestbpm, _ = ordered[0]

    # Historical resolution path.  Keep this byte-for-byte equivalent in
    # behavior for songs that do not have a tight method consensus.
    resolved = bestbpm
    for score, candidate, _ in ordered:
        if candidate < resolved and score >= bestscore * 0.97:
            ratio = resolved / candidate
            if abs(ratio - round(ratio)) < 0.04 and round(ratio) in (2, 3, 4):
                resolved = candidate

    consensus = _tight_tempo_consensus(method_tempos)
    consensus_preferred = False
    if consensus is not None and bestscore > 0:
        center = consensus["bpm"]
        nearby = [
            item for item in ordered
            if abs(item[1] - center) / center <= _CONSENSUS_CANDIDATE_LIMIT
        ]
        if nearby:
            # Within the tightly bounded neighborhood, use the onset-supported
            # candidate; closeness to the method median breaks score ties.
            consensus_score, consensus_bpm, _ = max(
                nearby, key=lambda item: (item[0], -abs(item[1] - center))
            )
            if consensus_score >= bestscore * _CONSENSUS_SCORE_FLOOR:
                resolved = consensus_bpm
                consensus_preferred = True

    # Preserve the original ambiguity rule without consensus.  When consensus
    # decides between octave-related grids, use the same competitive score
    # floor that allowed the preference so the rejected half/double grid stays
    # visible to callers and lowers confidence rather than disappearing.
    octave_floor = (_CONSENSUS_SCORE_FLOOR if consensus_preferred else 0.97)
    octave_pool = ordered if consensus_preferred else ordered[:10]
    octave_alternates = []
    for score, candidate, _ in octave_pool:
        if abs(candidate - resolved) < 0.9:
            continue
        ratio = max(candidate, resolved) / min(candidate, resolved)
        if (abs(ratio - 2.0) < 0.08
                and score >= bestscore * octave_floor):
            octave_alternates.append({
                "bpm": candidate,
                "score": round(float(score), 3),
            })

    return {
        "bpm": resolved,
        "octave_alternates": octave_alternates,
        "consensus": consensus,
        "consensus_preferred": consensus_preferred,
    }


def analyze(path, progress=None):
    """Full analysis. Returns a JSON-safe dict.

    progress: optional callable(str) for status updates.
    """
    def note(msg):
        if progress:
            progress(msg)

    note("Loading audio...")
    y, sr = librosa.load(path, sr=SR, mono=True)
    duration = float(librosa.get_duration(y=y, sr=sr))
    note("Computing onset envelope...")
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)

    # --- method 1: onset-autocorrelation tempo -------------------------------
    note("Measuring tempo (method 1/4: autocorrelation)...")
    m1 = float(np.atleast_1d(lr_tempo(
        onset_envelope=onset, sr=sr, hop_length=HOP, aggregate=np.mean))[0])

    # --- method 2: beat tracker, median inter-beat interval ------------------
    note("Measuring tempo (method 2/4: beat tracker)...")
    _, bf = librosa.beat.beat_track(y=y, sr=sr, onset_envelope=onset, hop_length=HOP)
    bt = librosa.frames_to_time(bf, sr=sr, hop_length=HOP)
    ibi = np.diff(bt)
    m2 = 60.0 / float(np.median(ibi)) if len(ibi) else float("nan")
    ibi_cv = float(np.std(ibi) / np.mean(ibi)) if len(ibi) else float("nan")

    # --- method 3: tempogram peak -------------------------------------------
    note("Measuring tempo (method 3/4: tempogram)...")
    try:
        tg = lr_tempogram(onset_envelope=onset, sr=sr, hop_length=HOP)
        freqs = lr_tempo_freqs(tg.shape[0], sr=sr, hop_length=HOP)
        prof = tg.mean(axis=1)
        band = (freqs >= 50) & (freqs <= 240)
        m3 = float(freqs[band][np.argmax(prof[band])])
    except Exception:
        m3 = float("nan")

    # --- method 4: windowed tempo (drift check) ------------------------------
    note("Measuring tempo (method 4/4: stability windows)...")
    win = int(20 * sr / HOP)
    locals_ = []
    for s in range(0, max(1, len(onset) - win), win):
        seg = onset[s:s + win]
        if len(seg) < win // 2:
            continue
        try:
            locals_.append(float(np.atleast_1d(lr_tempo(
                onset_envelope=seg, sr=sr, hop_length=HOP))[0]))
        except Exception:
            pass
    locals_ = np.array(locals_) if locals_ else np.array([])

    # --- candidate scoring ---------------------------------------------------
    note("Scoring tempo candidates against the onset grid...")
    cands = set()
    for v in (m1, m2, m3):
        if np.isnan(v):
            continue
        for mult in (0.25, 1 / 3, 0.5, 2 / 3, 0.75, 1.0, 4 / 3, 1.5, 2.0, 3.0, 4.0):
            c = v * mult
            if 55 <= c <= 220:
                cands.add(round(c, 1))
    snapped = {}
    for c in sorted(cands):
        r = round(c)
        if abs(c - r) < 0.8 and 55 <= r <= 220:
            snapped[float(r)] = True
        else:
            snapped[c] = True
    scored = []
    for c in sorted(snapped):
        s, ph = _comb_score(onset, sr, HOP, c)
        scored.append((s, c, ph))
    scored.sort(reverse=True)

    method_tempos = [m1, m2, m3]
    if len(locals_):
        method_tempos.append(float(np.median(locals_)))
    resolution = _resolve_tempo_candidates(scored, method_tempos)
    resolved = resolution["bpm"]
    octave_alternates = resolution["octave_alternates"]

    tempo_steady = bool(len(locals_) > 2 and (locals_.max() - locals_.min()) < 8)
    drift_flag = None
    if len(bt) > 16:
        half = len(bt) // 2
        bpm_a = 60.0 / float(np.median(np.diff(bt[:half])))
        bpm_b = 60.0 / float(np.median(np.diff(bt[half:])))
        drift_pct = abs(bpm_a - bpm_b) / resolved * 100
        if drift_pct > 1.5:
            drift_flag = {"first_half_bpm": round(bpm_a, 2),
                          "second_half_bpm": round(bpm_b, 2),
                          "drift_pct": round(drift_pct, 2)}

    # --- beat grid at the resolved tempo ------------------------------------
    note("Building the beat grid...")
    _, bf2 = librosa.beat.beat_track(
        y=y, sr=sr, onset_envelope=onset, hop_length=HOP,
        start_bpm=resolved, tightness=100)
    beat_times = librosa.frames_to_time(bf2, sr=sr, hop_length=HOP)
    beat_times = [float(t) for t in beat_times]

    # --- downbeat phase: which of the 4 beat phases carries the most energy --
    onset_at = []
    for t in beat_times:
        fr = int(round(t * sr / HOP))
        onset_at.append(float(onset[fr]) if fr < len(onset) else 0.0)
    onset_at = np.array(onset_at)
    best_phase, best_energy = 0, -1.0
    for p in range(4):
        e = float(onset_at[p::4].mean()) if len(onset_at[p::4]) else 0.0
        if e > best_energy:
            best_energy, best_phase = e, p
    downbeat_times = beat_times[best_phase::4]

    # Meter sanity: we only support 4/4 (STEERING section 8 rule 5).  The
    # downbeat test above assumes 4; a 3/4 song shows as a weak phase contrast.
    phase_energies = [float(onset_at[p::4].mean()) if len(onset_at[p::4]) else 0.0
                      for p in range(4)]
    phase_contrast = (max(phase_energies) - min(phase_energies)) / (max(phase_energies) + 1e-9)

    confidence = "high"
    conf_notes = []
    if ibi_cv > 0.08:
        confidence = "medium"
        conf_notes.append(f"beat spacing jitter {ibi_cv*100:.1f}% (above 8%)")
    if not tempo_steady:
        confidence = "medium"
        conf_notes.append("tempo varies across 20s windows")
    if octave_alternates:
        confidence = "medium"
        conf_notes.append("octave ambiguity: a half/double-time grid scores nearly as well")
    if drift_flag:
        confidence = "low"
        conf_notes.append(f"tempo drift {drift_flag['drift_pct']}% between song halves")

    note("Analysis complete.")
    return {
        "duration": round(duration, 3),
        "bpm": round(float(resolved), 2),
        "bpm_confidence": confidence,
        "bpm_confidence_notes": conf_notes,
        "methods": {
            "autocorrelation": round(m1, 2),
            "beat_tracker_median_ibi": round(m2, 2) if not np.isnan(m2) else None,
            "tempogram_peak": round(m3, 2) if not np.isnan(m3) else None,
            "windowed_median": round(float(np.median(locals_)), 2) if len(locals_) else None,
            "windowed_spread": [round(float(locals_.min()), 1), round(float(locals_.max()), 1)] if len(locals_) else None,
            "ibi_jitter_pct": round(ibi_cv * 100, 2) if not np.isnan(ibi_cv) else None,
        },
        "candidates": [{"bpm": c, "score": round(float(s), 3)} for s, c, ph in scored[:8]],
        "octave_alternates": octave_alternates,
        "tempo_steady": tempo_steady,
        "drift": drift_flag,
        "seconds_per_beat": round(60.0 / resolved, 4),
        "seconds_per_bar": round(240.0 / resolved, 4),
        "beat_times": [round(t, 4) for t in beat_times],
        "downbeat_times": [round(t, 4) for t in downbeat_times],
        "downbeat_phase": best_phase,
        "phase_contrast": round(float(phase_contrast), 3),
        "waveform": _waveform_peaks(y),
    }
