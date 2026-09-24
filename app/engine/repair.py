"""Audio repair helpers for Sound Repair Studio.

The repair process is intentionally conservative: it never invents an entire
arrangement.  It reuses an approved earlier passage from a separated stem,
time-matches it to the selected gap, and blends it into the original mix with
short equal-power fades.  This is especially useful for a dropped drum groove
or an otherwise identical chorus that lost its accompaniment.
"""
from __future__ import annotations

import os

import librosa
import numpy as np
import soundfile as sf


class RepairError(ValueError):
    """A repair selection cannot safely be rendered."""


def _as_channels_first(audio: np.ndarray) -> np.ndarray:
    """Normalise mono/stereo libsndfile output to (channels, samples)."""
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 1:
        return audio[np.newaxis, :]
    return audio.T


def _match_channels(audio: np.ndarray, channels: int) -> np.ndarray:
    if audio.shape[0] == channels:
        return audio
    if audio.shape[0] == 1:
        return np.repeat(audio, channels, axis=0)
    return np.mean(audio, axis=0, keepdims=True).repeat(channels, axis=0)


def _read_audio(path: str) -> tuple[np.ndarray, int]:
    """Read WAV stems and common uploaded formats, keeping their channels."""
    try:
        audio, sr = sf.read(path, always_2d=True, dtype="float32")
        return _as_channels_first(audio), int(sr)
    except Exception:
        # Some Windows soundfile builds cannot decode MP3/AAC even though the
        # app accepts them.  Librosa's decoder is a dependable local fallback.
        audio, sr = librosa.load(path, sr=None, mono=False)
        audio = np.asarray(audio, dtype=np.float32)
        if audio.ndim == 1:
            audio = audio[np.newaxis, :]
        return audio, int(sr)


def _time_stretch(audio: np.ndarray, output_samples: int) -> np.ndarray:
    """Stretch each channel independently, then correct the one-sample tail."""
    if output_samples < 1:
        raise RepairError("The target area must be longer than zero seconds.")
    if audio.shape[1] < 32:
        raise RepairError("The reference passage is too short to repair cleanly.")
    if audio.shape[1] == output_samples:
        return audio.copy()
    rate = audio.shape[1] / output_samples
    rendered = []
    for channel in audio:
        try:
            stretched = librosa.effects.time_stretch(channel, rate=rate)
        except Exception as exc:  # pragma: no cover - librosa format-specific
            raise RepairError(f"Could not time-match the reference phrase: {exc}")
        if len(stretched) < output_samples:
            stretched = np.pad(stretched, (0, output_samples - len(stretched)))
        rendered.append(stretched[:output_samples])
    return np.asarray(rendered, dtype=np.float32)


def _equal_power_window(length: int, fade_samples: int) -> np.ndarray:
    """Envelope that cleanly enters and exits the selected repair passage."""
    envelope = np.ones(length, dtype=np.float32)
    fade = min(max(0, fade_samples), length // 2)
    if not fade:
        return envelope
    ramp = np.linspace(0.0, np.pi / 2, fade, endpoint=True, dtype=np.float32)
    envelope[:fade] = np.sin(ramp)
    envelope[-fade:] = np.sin(ramp[::-1])
    return envelope


def validate_selection(duration: float, source_start: float, source_end: float,
                       target_start: float, target_end: float) -> None:
    values = (source_start, source_end, target_start, target_end)
    if not all(np.isfinite(value) for value in values):
        raise RepairError("All selection times must be real numbers.")
    if source_start < 0 or target_start < 0:
        raise RepairError("A selection cannot start before 0:00.")
    if source_end <= source_start or target_end <= target_start:
        raise RepairError("Each selection needs a start time before its end time.")
    if source_end > duration + 0.05 or target_end > duration + 0.05:
        raise RepairError("One of the selections is past the end of the song.")


def render_overlay(mix_path: str, stem_path: str, output_path: str, *,
                   source_start: float, source_end: float,
                   target_start: float, target_end: float,
                   fade_ms: int = 120, gain_db: float = -2.0) -> dict:
    """Overlay a time-matched source phrase from ``stem_path`` onto ``mix_path``.

    The original master is not touched.  A full-length 24-bit WAV is written
    to ``output_path`` and a JSON-safe summary is returned for the UI.
    """
    if not os.path.isfile(mix_path) or not os.path.isfile(stem_path):
        raise RepairError("The song or its selected stem is no longer available.")
    mix, sr = _read_audio(mix_path)
    stem, stem_sr = _read_audio(stem_path)
    if stem_sr != sr:
        stem = librosa.resample(stem, orig_sr=stem_sr, target_sr=sr, axis=1)
    stem = _match_channels(stem, mix.shape[0])
    duration = mix.shape[1] / sr
    validate_selection(duration, source_start, source_end, target_start, target_end)

    source_a, source_b = int(round(source_start * sr)), int(round(source_end * sr))
    target_a, target_b = int(round(target_start * sr)), int(round(target_end * sr))
    phrase = stem[:, source_a:source_b]
    target_len = target_b - target_a
    repaired = _time_stretch(phrase, target_len)
    fade_samples = int(sr * max(0, min(int(fade_ms), 2000)) / 1000)
    repaired *= _equal_power_window(target_len, fade_samples)[np.newaxis, :]
    repaired *= float(10 ** (float(gain_db) / 20.0))

    output = mix.copy()
    output[:, target_a:target_b] += repaired
    # Avoid wrap-around clipping without flattening quiet material.  A gentle
    # ceiling also makes the browser preview safer after an energetic drum fill.
    peak = float(np.max(np.abs(output))) if output.size else 0.0
    if peak > 0.995:
        output *= 0.995 / peak
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    sf.write(output_path, output.T, sr, subtype="PCM_24")
    return {
        "duration": round(duration, 3),
        "sample_rate": int(sr),
        "source_duration": round((source_b - source_a) / sr, 3),
        "target_duration": round(target_len / sr, 3),
        "time_stretched": source_b - source_a != target_len,
        "fade_ms": int(fade_ms),
        "gain_db": round(float(gain_db), 2),
        "peak": round(min(peak, 0.995), 4),
    }
