"""Data models and JSON persistence for VideoLibro Studio."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

TextStyleMode = Literal[
    "Libro Cinematografico",
    "Sottotitoli Cinema",
    "Pagina Antica",
    "Minimal Elegante",
    "Notturno Blu",
]
MediaType = Literal["none", "image", "video"]
KenBurnsMode = Literal["zoom_in", "zoom_out", "pan_left", "pan_right", "static"]
TTSEngine = Literal["edge-tts", "kokoro", "offline"]


def _new_id() -> str:
    return uuid.uuid4().hex[:10]


@dataclass
class SceneBlock:
    """A single readable scene/paragraph projected over visual media."""

    id: str = field(default_factory=_new_id)
    text: str = ""
    media_path: str = ""
    media_type: MediaType = "none"
    ken_burns: KenBurnsMode = "zoom_in"
    image_zoom: float = 1.0
    image_x: float = 0.0
    image_y: float = 0.0
    duration_sec: float = 5.0
    pause_after_sec: float = 0.8
    pause_override: bool = False
    tts_audio_path: str = ""
    tts_duration_sec: float = 0.0
    word_timings: list[dict] = field(default_factory=list)
    use_chapter_media: bool = True

    @property
    def effective_duration(self) -> float:
        base = self.tts_duration_sec if self.tts_duration_sec > 0 else self.duration_sec
        return max(2.0, base) + self.pause_after_sec


@dataclass
class Chapter:
    """A book chapter containing ordered scenes and chapter-level defaults."""

    id: str = field(default_factory=_new_id)
    title: str = "Capitolo 1"
    subtitle: str = ""
    show_title_card: bool = True
    title_card_duration: float = 3.5
    default_media_path: str = ""
    default_media_type: MediaType = "none"
    bg_audio_path: str = ""
    bg_audio_volume: float = 0.22
    scenes: list[SceneBlock] = field(default_factory=list)

    def total_duration(self) -> float:
        total = self.title_card_duration if self.show_title_card else 0.0
        for s in self.scenes:
            total += max(2.0, s.tts_duration_sec if s.tts_duration_sec > 0 else s.duration_sec) + s.pause_after_sec
        return total


@dataclass
class ProjectSettings:
    """Global rendering, typography, and TTS settings for the VideoLibro."""

    resolution: str = "1920x1080"
    fps: int = 30
    tts_engine: TTSEngine = "edge-tts"
    tts_voice: str = "it-IT-DiegoNeural"
    tts_rate: str = "+0%"
    text_style: TextStyleMode = "Libro Cinematografico"
    font_family: str = "Georgia"
    font_variant: str = "Normale"
    font_size: int = 40
    global_bg_audio_path: str = ""
    global_bg_audio_volume: float = 0.20
    auto_ducking: bool = True
    ducking_factor: float = 0.35
    accent_color: str = "#E0B46A"
    karaoke_enabled: bool = False
    bg_fallback_color: str = "#12151E"
    global_pause_sec: float = 0.8

    @property
    def width(self) -> int:
        return int(self.resolution.split("x")[0])

    @property
    def height(self) -> int:
        return int(self.resolution.split("x")[1])


@dataclass
class TimelineEntry:
    """Computed timeline placement for preview and timeline widget rendering."""

    kind: Literal["title_card", "scene"]
    chapter_index: int
    scene_index: int | None
    label: str
    start_sec: float
    duration_sec: float
    media_path: str
    media_type: MediaType
    bg_audio_path: str
    bg_audio_volume: float
    has_tts: bool
    pause_sec: float = 0.0

    @property
    def end_sec(self) -> float:
        return self.start_sec + self.duration_sec


@dataclass
class VideoBookProject:
    """Root project container with JSON serialization and timeline calculation."""

    title: str = "Nuovo VideoLibro"
    author: str = "Autore"
    source_file: str = ""
    settings: ProjectSettings = field(default_factory=ProjectSettings)
    chapters: list[Chapter] = field(default_factory=list)

    def compute_timeline(self) -> list[TimelineEntry]:
        """Compute sequential timeline entries across all chapters and scenes."""
        entries: list[TimelineEntry] = []
        cursor = 0.0
        for c_idx, ch in enumerate(self.chapters):
            ch_audio = ch.bg_audio_path or self.settings.global_bg_audio_path
            ch_vol = ch.bg_audio_volume if ch.bg_audio_path else self.settings.global_bg_audio_volume

            if ch.show_title_card:
                entries.append(
                    TimelineEntry(
                        kind="title_card",
                        chapter_index=c_idx,
                        scene_index=None,
                        label=ch.title,
                        start_sec=cursor,
                        duration_sec=ch.title_card_duration,
                        media_path=ch.default_media_path,
                        media_type=ch.default_media_type,
                        bg_audio_path=ch_audio,
                        bg_audio_volume=ch_vol,
                        has_tts=False,
                    )
                )
                cursor += ch.title_card_duration

            for s_idx, sc in enumerate(ch.scenes):
                media_path = ch.default_media_path if sc.use_chapter_media else sc.media_path
                media_type = ch.default_media_type if sc.use_chapter_media else sc.media_type
                pause = sc.pause_after_sec if sc.pause_override else self.settings.global_pause_sec
                dur = max(2.0, sc.tts_duration_sec if sc.tts_duration_sec > 0 else sc.duration_sec) + pause
                preview_txt = sc.text.strip().replace("\n", " ")
                if len(preview_txt) > 36:
                    preview_txt = preview_txt[:33] + "..."
                entries.append(
                    TimelineEntry(
                        kind="scene",
                        chapter_index=c_idx,
                        scene_index=s_idx,
                        label=preview_txt or f"Scena {s_idx + 1}",
                        start_sec=cursor,
                        duration_sec=dur,
                        media_path=media_path,
                        media_type=media_type,
                        bg_audio_path=ch_audio,
                        bg_audio_volume=ch_vol,
                        has_tts=bool(sc.tts_audio_path),
                        pause_sec=pause,
                    )
                )
                cursor += dur
        return entries

    def total_duration(self) -> float:
        return sum(
            (ch.title_card_duration if ch.show_title_card else 0.0)
            + sum(
                max(2.0, sc.tts_duration_sec if sc.tts_duration_sec > 0 else sc.duration_sec)
                + (sc.pause_after_sec if sc.pause_override else self.settings.global_pause_sec)
                for sc in ch.scenes
            )
            for ch in self.chapters
        )

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str | Path) -> "VideoBookProject":
        with Path(path).open("r", encoding="utf-8") as f:
            raw = json.load(f)
        settings = ProjectSettings(**raw.get("settings", {}))
        chapters: list[Chapter] = []
        for ch_raw in raw.get("chapters", []):
            scenes = [SceneBlock(**s) for s in ch_raw.get("scenes", [])]
            ch_data = {k: v for k, v in ch_raw.items() if k != "scenes"}
            chapters.append(Chapter(**ch_data, scenes=scenes))
        return cls(
            title=raw.get("title", "VideoLibro"),
            author=raw.get("author", "Autore"),
            source_file=raw.get("source_file", ""),
            settings=settings,
            chapters=chapters,
        )
