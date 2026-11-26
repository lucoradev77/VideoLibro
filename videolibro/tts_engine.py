"""Text-to-Speech engine supporting Edge Neural TTS, local Kokoro-82M ONNX, and Windows SAPI5."""

from __future__ import annotations

import asyncio
import re
import sys
import subprocess
import threading
import wave
from pathlib import Path
from typing import Callable

import edge_tts
import imageio_ffmpeg

MODEL_FILENAME = "kokoro-v1.0.onnx"
VOICES_FILENAME = "voices-v1.0.bin"

MODEL_DOWNLOAD_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
)
VOICES_DOWNLOAD_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
)

EDGE_VOICES: list[tuple[str, str]] = [
    ("it-IT-DiegoNeural", "Diego (Italiano - Uomo, Narratore)"),
    ("it-IT-ElsaNeural", "Elsa (Italiano - Donna, Chiara)"),
    ("it-IT-IsabellaNeural", "Isabella (Italiano - Donna, Calda)"),
    ("it-IT-GiuseppeNeural", "Giuseppe (Italiano - Uomo, Profondo)"),
    ("en-US-AndrewNeural", "Andrew (English - Male)"),
    ("en-US-AriaNeural", "Aria (English - Female)"),
]

# Kept for backwards compatibility with existing imports.
ITALIAN_VOICES = EDGE_VOICES

KOKORO_VOICES: list[tuple[str, str]] = [
    ("if_sara", "Sara (Italiano - Donna, Naturale)"),
    ("im_nicola", "Nicola (Italiano - Uomo, Caldo)"),
    ("af_heart", "Heart (English US - Female)"),
    ("af_bella", "Bella (English US - Female)"),
    ("af_sarah", "Sarah (English US - Female)"),
    ("am_adam", "Adam (English US - Male)"),
    ("am_michael", "Michael (English US - Male)"),
    ("bf_emma", "Emma (English UK - Female)"),
    ("bm_george", "George (English UK - Male)"),
]

KOKORO_VOICE_LANGS: dict[str, str] = {
    "if_sara": "it",
    "im_nicola": "it",
    "af_heart": "en-us",
    "af_bella": "en-us",
    "af_sarah": "en-us",
    "am_adam": "en-us",
    "am_michael": "en-us",
    "bf_emma": "en-gb",
    "bm_george": "en-gb",
}

_EDGE_TO_KOKORO: dict[str, str] = {
    "it-IT-DiegoNeural": "im_nicola",
    "it-IT-GiuseppeNeural": "im_nicola",
    "it-IT-ElsaNeural": "if_sara",
    "it-IT-IsabellaNeural": "if_sara",
    "en-US-AndrewNeural": "am_adam",
    "en-US-AriaNeural": "af_heart",
}

_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_KOKORO_LOCK = threading.Lock()
_KOKORO_INSTANCE: object | None = None
_KOKORO_ROOT: Path | None = None


def default_models_dir() -> Path:
    """Return the local models directory (next to .exe when frozen, or project root)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "models"
    return Path(__file__).resolve().parents[1] / "models"


def kokoro_models_present(models_dir: Path | None = None) -> bool:
    """Return True if both Kokoro ONNX model and voices archive exist locally."""
    root = models_dir or default_models_dir()
    model_file = root / MODEL_FILENAME
    voices_file = root / VOICES_FILENAME
    return (
        model_file.is_file()
        and model_file.stat().st_size > 0
        and voices_file.is_file()
        and voices_file.stat().st_size > 0
    )


def voices_for_engine(engine: str) -> list[tuple[str, str]]:
    """Return the (voice_id, display_label) list for the selected TTS engine."""
    if engine == "kokoro":
        return list(KOKORO_VOICES)
    if engine == "offline":
        if kokoro_models_present():
            return list(KOKORO_VOICES)
        return [("sapi5-default", "Voce di sistema Windows (SAPI5)")]
    return list(EDGE_VOICES)


def download_kokoro_models(
    models_dir: Path | None = None,
    progress_cb: Callable[[str, int, int], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> Path:
    """Download Kokoro v1.0 ONNX model and voices archive into models_dir."""
    import httpx

    root = models_dir or default_models_dir()
    root.mkdir(parents=True, exist_ok=True)

    targets = [
        (VOICES_FILENAME, VOICES_DOWNLOAD_URL),
        (MODEL_FILENAME, MODEL_DOWNLOAD_URL),
    ]

    with httpx.Client(follow_redirects=True, timeout=60.0) as client:
        for filename, url in targets:
            dest = root / filename
            if dest.is_file() and dest.stat().st_size > 0:
                continue

            part_path = root / f"{filename}.part"
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0))
                downloaded = 0
                with part_path.open("wb") as fh:
                    for chunk in resp.iter_bytes(chunk_size=1024 * 256):
                        if cancel_event and cancel_event.is_set():
                            part_path.unlink(missing_ok=True)
                            raise RuntimeError("Download annullato dall'utente.")
                        fh.write(chunk)
                        downloaded += len(chunk)
                        if progress_cb:
                            progress_cb(filename, downloaded, total)

            part_path.replace(dest)

    return root


def _get_kokoro(models_dir: Path | None = None):
    """Return a cached, thread-safe Kokoro ONNX instance."""
    global _KOKORO_INSTANCE, _KOKORO_ROOT
    from kokoro_onnx import Kokoro

    root = (models_dir or default_models_dir()).resolve()
    with _KOKORO_LOCK:
        if _KOKORO_INSTANCE is None or _KOKORO_ROOT != root:
            if not kokoro_models_present(root):
                raise FileNotFoundError(
                    "Modelli Kokoro offline non trovati. Scaricali prima dalla scheda Voce & Stile TV."
                )
            _KOKORO_INSTANCE = Kokoro(
                str(root / MODEL_FILENAME),
                str(root / VOICES_FILENAME),
            )
            _KOKORO_ROOT = root
        return _KOKORO_INSTANCE


def _resolve_kokoro_voice(voice: str) -> tuple[str, str]:
    """Map a voice identifier (Kokoro or Edge) to (kokoro_voice_id, lang_code)."""
    if voice in KOKORO_VOICE_LANGS:
        return voice, KOKORO_VOICE_LANGS[voice]
    if voice in _EDGE_TO_KOKORO:
        mapped = _EDGE_TO_KOKORO[voice]
        return mapped, KOKORO_VOICE_LANGS[mapped]
    if voice.lower().startswith("en-gb"):
        return "bf_emma", "en-gb"
    if voice.lower().startswith("en-"):
        return "af_heart", "en-us"
    return "if_sara", "it"


def _parse_rate_to_speed(rate: str) -> float:
    """Convert Edge-style rate string (e.g. '+10%', '-15%') to Kokoro speed float."""
    match = re.search(r"([+-]?\d+)\s*%", rate or "")
    if not match:
        return 1.0
    pct = int(match.group(1))
    return max(0.5, min(2.0, 1.0 + pct / 100.0))


def normalize_tts_text(text: str) -> str:
    """Remove punctuation-only fragments that speech engines cannot meaningfully read."""
    text = re.sub(r"[\u2010-\u2015\-_=*~#|]+", " ", text)
    text = re.sub(r"[\u200b-\u200f\u202a-\u202e\ufeff]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    # A scene made only of punctuation or symbols has no spoken content.
    if not re.search(r"[\w\u00c0-\u024f]", text, re.UNICODE):
        return ""
    return text


def _kokoro_tts(
    text: str,
    output_wav: Path,
    voice: str = "if_sara",
    rate: str = "+0%",
    models_dir: Path | None = None,
) -> None:
    """Synthesize speech locally using Kokoro-82M ONNX and write a 16-bit PCM WAV file."""
    import numpy as np

    kokoro = _get_kokoro(models_dir)
    kokoro_voice, lang_code = _resolve_kokoro_voice(voice)
    speed = _parse_rate_to_speed(rate)

    samples, sample_rate = kokoro.create(
        text,
        voice=kokoro_voice,
        speed=speed,
        lang=lang_code,
        trim=True,
    )
    pcm_float = np.asarray(samples, dtype=np.float32)
    pcm_int16 = (np.clip(pcm_float, -1.0, 1.0) * 32767.0).astype(np.int16)

    with wave.open(str(output_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(pcm_int16.tobytes())


def get_audio_duration(audio_path: str | Path) -> float:
    """Return duration in seconds for .wav or .mp3 using stdlib wave or ffmpeg."""
    p = Path(audio_path)
    if not p.exists():
        return 0.0

    if p.suffix.lower() == ".wav":
        try:
            with wave.open(str(p), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    return round(frames / float(rate), 2)
        except Exception:
            pass

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    proc = subprocess.run(
        [ffmpeg_exe, "-i", str(p)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    match = _DURATION_RE.search(proc.stderr or "")
    if match:
        h, m, s = int(match.group(1)), int(match.group(2)), float(match.group(3))
        return round(h * 3600 + m * 60 + s, 2)
    return 0.0


async def _edge_tts_async(
    text: str,
    output_path: Path,
    voice: str,
    rate: str,
) -> list[dict]:
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    word_timings: list[dict] = []
    with output_path.open("wb") as audio_file:
        async for chunk in communicate.stream():
            ctype = chunk.get("type")
            if ctype == "audio":
                audio_file.write(chunk["data"])
            elif ctype == "WordBoundary":
                word_timings.append(
                    {
                        "text": chunk.get("text", ""),
                        "offset_sec": round(chunk.get("offset", 0) / 10_000_000, 3),
                        "duration_sec": round(chunk.get("duration", 0) / 10_000_000, 3),
                    }
                )
    return word_timings


def _offline_tts(text: str, output_wav: Path) -> None:
    import pyttsx3

    engine = pyttsx3.init()
    engine.setProperty("rate", 165)
    # Try to pick an Italian SAPI5 voice if installed on Windows
    for v in engine.getProperty("voices") or []:
        name_id = f"{getattr(v, 'name', '')} {getattr(v, 'id', '')}".lower()
        if "italian" in name_id or "it-it" in name_id or "elsa" in name_id or "cosimo" in name_id:
            engine.setProperty("voice", v.id)
            break
    engine.save_to_file(text, str(output_wav))
    engine.runAndWait()
    engine.stop()


def synthesize_scene_tts(
    text: str,
    output_dir: str | Path,
    scene_id: str,
    voice: str = "it-IT-DiegoNeural",
    rate: str = "+0%",
    engine: str = "edge-tts",
) -> tuple[str, float, list[dict]]:
    """Generate narration audio for a scene and return (audio_path, duration_sec, word_timings)."""
    clean_text = normalize_tts_text(text)
    if not clean_text:
        return "", 2.0, []

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if engine == "kokoro":
        wav_path = out_dir / f"tts_{scene_id}.wav"
        _kokoro_tts(clean_text, wav_path, voice=voice, rate=rate)
        dur = get_audio_duration(wav_path)
        return str(wav_path), max(1.5, dur), []

    if engine == "edge-tts":
        mp3_path = out_dir / f"tts_{scene_id}.mp3"
        try:
            timings = asyncio.run(_edge_tts_async(clean_text, mp3_path, voice, rate))
            dur = get_audio_duration(mp3_path)
            if dur > 0:
                return str(mp3_path), dur, timings
        except Exception:
            # Automatic fallback: prefer local Kokoro neural voices if downloaded, else SAPI5
            pass

    wav_path = out_dir / f"tts_{scene_id}.wav"
    if kokoro_models_present():
        try:
            _kokoro_tts(clean_text, wav_path, voice=voice, rate=rate)
            dur = get_audio_duration(wav_path)
            if dur > 0:
                return str(wav_path), max(1.5, dur), []
        except Exception:
            pass

    _offline_tts(clean_text, wav_path)
    dur = get_audio_duration(wav_path)
    return str(wav_path), max(1.5, dur), []
