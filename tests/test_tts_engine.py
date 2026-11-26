"""Tests for VideoLibro TTS engine (Kokoro ONNX, voice mapping, and rate parsing)."""

from __future__ import annotations

from pathlib import Path
import wave

import pytest

from videolibro.tts_engine import (
    KOKORO_VOICES,
    _kokoro_tts,
    _parse_rate_to_speed,
    _resolve_kokoro_voice,
    get_audio_duration,
    kokoro_models_present,
    synthesize_scene_tts,
    voices_for_engine,
)


def test_voice_mapping_and_rate_parsing() -> None:
    assert _resolve_kokoro_voice("if_sara") == ("if_sara", "it")
    assert _resolve_kokoro_voice("im_nicola") == ("im_nicola", "it")
    assert _resolve_kokoro_voice("it-IT-DiegoNeural") == ("im_nicola", "it")
    assert _resolve_kokoro_voice("it-IT-ElsaNeural") == ("if_sara", "it")
    assert _resolve_kokoro_voice("en-US-AndrewNeural") == ("am_adam", "en-us")
    assert _resolve_kokoro_voice("en-US-AriaNeural") == ("af_heart", "en-us")

    assert _parse_rate_to_speed("+0%") == 1.0
    assert _parse_rate_to_speed("+15%") == pytest.approx(1.15)
    assert _parse_rate_to_speed("-20%") == pytest.approx(0.80)
    assert _parse_rate_to_speed("+500%") == 2.0
    assert _parse_rate_to_speed("-90%") == 0.5


def test_voices_for_engine() -> None:
    kokoro_list = voices_for_engine("kokoro")
    assert kokoro_list == KOKORO_VOICES
    assert any(vid == "if_sara" for vid, _ in kokoro_list)
    assert any(vid == "im_nicola" for vid, _ in kokoro_list)

    edge_list = voices_for_engine("edge-tts")
    assert any(vid == "it-IT-DiegoNeural" for vid, _ in edge_list)


def test_kokoro_missing_models_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("videolibro.tts_engine.default_models_dir", lambda: tmp_path)
    assert not kokoro_models_present(tmp_path)
    with pytest.raises(FileNotFoundError):
        synthesize_scene_tts(
            "Ciao mondo",
            tmp_path / "out",
            "scene1",
            voice="if_sara",
            engine="kokoro",
        )


def test_kokoro_synthesis_real_if_models_available(tmp_path: Path) -> None:
    doctts_models = Path(r"d:\DEV\PY\DocTTS\models")
    if not kokoro_models_present(doctts_models):
        pytest.skip("Local Kokoro models not available in d:\\DEV\\PY\\DocTTS\\models")

    wav_out = tmp_path / "test_sara.wav"
    _kokoro_tts(
        "Benvenuti in VideoLibro Studio. Questa è una prova di lettura naturale.",
        wav_out,
        voice="if_sara",
        rate="+0%",
        models_dir=doctts_models,
    )
    assert wav_out.is_file()
    dur = get_audio_duration(wav_out)
    assert dur > 1.0
    with wave.open(str(wav_out), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 24000
