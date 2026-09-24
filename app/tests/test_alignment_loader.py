"""Compatibility checks for the optional local WhisperX loader."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import alignment


class _FakeModel:
    def __init__(self, model_name, **kwargs):
        self.model_name = model_name
        self.load_kwargs = kwargs

    def transcribe(self, path, **kwargs):
        word = SimpleNamespace(word="Holler", start=1.0, end=1.5,
                               probability=0.9)
        segment = SimpleNamespace(start=1.0, end=3.0, text="Holler back",
                                  words=[word])
        return iter([segment]), SimpleNamespace(language="en")


def _fake_modules(monkeypatch, captured):
    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False, empty_cache=lambda: None)
    )

    class CapturingModel(_FakeModel):
        def __init__(self, model_name, **kwargs):
            super().__init__(model_name, **kwargs)
            captured.update(model_name=model_name, load_kwargs=kwargs)

        def transcribe(self, path, **kwargs):
            captured.update(path=path, transcribe_kwargs=kwargs)
            return super().transcribe(path, **kwargs)

    fake_whisperx = SimpleNamespace(
        load_audio=lambda path: "decoded-audio",
        load_align_model=lambda language_code, device: ("align-model", {"lang": language_code}),
        align=lambda segments, model, metadata, audio, device,
                     return_char_alignments: {"segments": segments},
    )
    fake_faster_whisper = SimpleNamespace(WhisperModel=CapturingModel)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "whisperx", fake_whisperx)
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_faster_whisper)


def test_transcription_scans_the_full_song_without_speech_vad(monkeypatch):
    captured = {}
    _fake_modules(monkeypatch, captured)

    segments, metadata = alignment._transcribe_with_whisperx("song.mp3")

    assert segments == [{
        "start": 1.0, "end": 3.0, "text": "Holler back",
        "words": [{"word": "Holler", "start": 1.0, "end": 1.5,
                   "score": 0.9}],
    }]
    assert captured["model_name"] == "small"
    assert captured["load_kwargs"]["device"] == "cpu"
    assert captured["load_kwargs"]["compute_type"] == "int8"
    assert captured["path"] == "decoded-audio"
    assert captured["transcribe_kwargs"]["language"] == "en"
    assert captured["transcribe_kwargs"]["task"] == "transcribe"
    assert captured["transcribe_kwargs"]["vad_filter"] is False
    assert captured["transcribe_kwargs"]["word_timestamps"] is True
    assert captured["transcribe_kwargs"]["no_speech_threshold"] == 0.6
    assert captured["transcribe_kwargs"]["condition_on_previous_text"] is True
    assert metadata["transcription_mode"] == "full_song"


def test_transcription_wraps_full_song_model_failures(monkeypatch):
    captured = {}
    _fake_modules(monkeypatch, captured)

    class BrokenModel:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("model unavailable")

    monkeypatch.setitem(sys.modules, "faster_whisper",
                        SimpleNamespace(WhisperModel=BrokenModel))

    with pytest.raises(alignment.AlignmentError, match="model unavailable"):
        alignment._transcribe_with_whisperx("song.mp3")


def test_scan_path_keeps_direct_words_and_skips_forced_alignment(monkeypatch):
    captured = {}
    _fake_modules(monkeypatch, captured)
    fake_whisperx = sys.modules["whisperx"]
    fake_whisperx.align = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("scan drafts should not invoke forced alignment"))

    segments, metadata = alignment._transcribe_with_whisperx(
        "song.mp3", refine_timestamps=False)

    assert segments[0]["words"] == [{
        "word": "Holler", "start": 1.0, "end": 1.5, "score": 0.9,
    }]
    assert metadata["engine"] == "faster-whisper"
