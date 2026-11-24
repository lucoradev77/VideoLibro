"""Text-to-Speech engine supporting Edge Neural TTS and offline Windows SAPI5."""

from __future__ import annotations

import asyncio
import re
import subprocess
import wave
from pathlib import Path

import edge_tts
import imageio_ffmpeg

ITALIAN_VOICES = [
    ("it-IT-DiegoNeural", "Diego (Italiano - Uomo, Narratore)"),
    ("it-IT-ElsaNeural", "Elsa (Italiano - Donna, Chiara)"),
    ("it-IT-IsabellaNeural", "Isabella (Italiano - Donna, Calda)"),
    ("it-IT-GiuseppeNeural", "Giuseppe (Italiano - Uomo, Profondo)"),
    ("en-US-AndrewNeural", "Andrew (English - Male)"),
    ("en-US-AriaNeural", "Aria (English - Female)"),
]

_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


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
    clean_text = text.strip()
    if not clean_text:
        return "", 2.0, []

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if engine == "edge-tts":
        mp3_path = out_dir / f"tts_{scene_id}.mp3"
        try:
            timings = asyncio.run(_edge_tts_async(clean_text, mp3_path, voice, rate))
            dur = get_audio_duration(mp3_path)
            if dur > 0:
                return str(mp3_path), dur, timings
        except Exception:
            # Automatic fallback to offline Windows SAPI5 if internet/edge-tts fails
            pass

    wav_path = out_dir / f"tts_{scene_id}.wav"
    _offline_tts(clean_text, wav_path)
    dur = get_audio_duration(wav_path)
    return str(wav_path), max(1.5, dur), []
