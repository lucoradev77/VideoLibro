"""TV-grade visual overlay renderer and FFmpeg MP4 VideoLibro exporter."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Callable

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .models import Chapter, KenBurnsMode, SceneBlock, TimelineEntry, VideoBookProject
from .tts_engine import synthesize_scene_tts

ProgressCallback = Callable[[int, str], None]
SizeCallback = Callable[[int], None]


def write_export_log(log_path: Path, message: str) -> None:
    """Append a timestamped diagnostic line to the export log."""
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"{datetime.now().astimezone().isoformat(timespec='seconds')}  {message}\n")


def _fmt_log_bytes(size: int) -> str:
    return f"{size / (1024 * 1024):.1f} MB"


class ExportCancelledError(Exception):
    """Raised when the user cancels MP4 export."""

_WIN_FONTS_DIR = Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts"


def _load_font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in candidates:
        fp = _WIN_FONTS_DIR / name
        if fp.exists():
            try:
                return ImageFont.truetype(str(fp), size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def _get_serif_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if bold:
        return _load_font(["georgiab.ttf", "palab.ttf", "timesbd.ttf", "segoeuib.ttf"], size)
    return _load_font(["georgia.ttf", "pala.ttf", "times.ttf", "segoeui.ttf"], size)


def _get_sans_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if bold:
        return _load_font(["segoeuib.ttf", "arialbd.ttf", "calibrib.ttf"], size)
    return _load_font(["segoeui.ttf", "arial.ttf", "calibri.ttf"], size)


_FONT_MAP: dict[str, dict[str, list[str]]] = {
    "Georgia": {
        "Normale": ["georgia.ttf"],
        "Grassetto": ["georgiab.ttf", "georgia.ttf"],
        "Corsivo": ["georgiai.ttf", "georgia.ttf"],
        "Grassetto Corsivo": ["georgiaz.ttf", "georgiab.ttf"],
    },
    "Palatino Linotype": {
        "Normale": ["pala.ttf"],
        "Grassetto": ["palab.ttf", "pala.ttf"],
        "Corsivo": ["palai.ttf", "pala.ttf"],
        "Grassetto Corsivo": ["palabi.ttf", "palab.ttf"],
    },
    "Times New Roman": {
        "Normale": ["times.ttf"],
        "Grassetto": ["timesbd.ttf", "times.ttf"],
        "Corsivo": ["timesi.ttf", "times.ttf"],
        "Grassetto Corsivo": ["timesbi.ttf", "timesbd.ttf"],
    },
    "Segoe UI": {
        "Normale": ["segoeui.ttf"],
        "Grassetto": ["segoeuib.ttf", "segoeui.ttf"],
        "Corsivo": ["segoeuii.ttf", "segoeui.ttf"],
        "Grassetto Corsivo": ["segoeuiz.ttf", "segoeuib.ttf"],
    },
    "Calibri": {
        "Normale": ["calibri.ttf"],
        "Grassetto": ["calibrib.ttf", "calibri.ttf"],
        "Corsivo": ["calibrii.ttf", "calibri.ttf"],
        "Grassetto Corsivo": ["calibriz.ttf", "calibrib.ttf"],
    },
    "Arial": {
        "Normale": ["arial.ttf"],
        "Grassetto": ["arialbd.ttf", "arial.ttf"],
        "Corsivo": ["ariali.ttf", "arial.ttf"],
        "Grassetto Corsivo": ["arialbi.ttf", "arialbd.ttf"],
    },
    "Garamond": {
        "Normale": ["gara.ttf", "georgia.ttf"],
        "Grassetto": ["garabd.ttf", "georgiab.ttf"],
        "Corsivo": ["garait.ttf", "georgiai.ttf"],
        "Grassetto Corsivo": ["garabd.ttf", "georgiaz.ttf"],
    },
}


def get_custom_font(family: str, variant: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Resolve user-selected font family and variant (Normale/Grassetto/Corsivo/Grassetto Corsivo)."""
    fam_map = _FONT_MAP.get(family, _FONT_MAP["Georgia"])
    candidates = fam_map.get(variant, fam_map["Normale"]) + ["georgia.ttf", "segoeui.ttf"]
    return _load_font(candidates, size)


def _hex_to_rgb(hex_color: str, fallback: tuple[int, int, int] = (224, 180, 106)) -> tuple[int, int, int]:
    h = hex_color.strip().lstrip("#")
    if len(h) == 6:
        try:
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        except ValueError:
            pass
    return fallback


def _wrap_text_to_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for w in words[1:]:
        candidate = f"{current} {w}"
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = w
    lines.append(current)
    return lines


def render_title_card_overlay(
    project: VideoBookProject,
    chapter: Chapter,
    width: int,
    height: int,
) -> Image.Image:
    """Create a transparent RGBA title card overlay for a chapter."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Dark cinematic scrim
    scrim = Image.new("RGBA", (width, height), (8, 10, 16, 175))
    img = Image.alpha_composite(img, scrim)
    draw = ImageDraw.Draw(img)

    accent = _hex_to_rgb(project.settings.accent_color)
    scale = width / 1920.0

    book_font = _get_sans_font(max(16, int(26 * scale)), bold=True)
    title_font = _get_serif_font(max(28, int(68 * scale)), bold=True)
    sub_font = _get_serif_font(max(18, int(34 * scale)), bold=False)

    # Book header
    book_label = f"{project.title.upper()}  •  {project.author.upper()}"
    bbox = draw.textbbox((0, 0), book_label, font=book_font)
    bw = bbox[2] - bbox[0]
    draw.text(((width - bw) / 2, height * 0.34), book_label, font=book_font, fill=(*accent, 230))

    # Ornamental line
    line_w = int(320 * scale)
    ly = int(height * 0.40)
    draw.line([(width // 2 - line_w // 2, ly), (width // 2 + line_w // 2, ly)], fill=(*accent, 180), width=max(2, int(3 * scale)))

    # Chapter title wrapped
    lines = _wrap_text_to_width(draw, chapter.title, title_font, int(width * 0.78))
    ty = int(height * 0.45)
    for line in lines[:3]:
        tb = draw.textbbox((0, 0), line, font=title_font)
        tw = tb[2] - tb[0]
        th = tb[3] - tb[1]
        draw.text(((width - tw) / 2 + 2, ty + 3), line, font=title_font, fill=(0, 0, 0, 180))
        draw.text(((width - tw) / 2, ty), line, font=title_font, fill=(248, 245, 238, 255))
        ty += th + int(16 * scale)

    if chapter.subtitle:
        sb = draw.textbbox((0, 0), chapter.subtitle, font=sub_font)
        sw = sb[2] - sb[0]
        draw.text(((width - sw) / 2, ty + int(16 * scale)), chapter.subtitle, font=sub_font, fill=(210, 212, 220, 220))

    return img


def render_scene_overlay(
    project: VideoBookProject,
    chapter: Chapter,
    scene: SceneBlock,
    progress_ratio: float,
    width: int,
    height: int,
    active_word_index: int | None = None,
) -> Image.Image:
    """Create a transparent RGBA text/UI overlay for a scene ready for TV viewing."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    scale = width / 1920.0
    accent = _hex_to_rgb(project.settings.accent_color)
    style = project.settings.text_style

    font_size = max(20, int(project.settings.font_size * scale))
    badge_font = _get_sans_font(max(14, int(22 * scale)), bold=True)

    # Top-left chapter badge
    pad_x = int(56 * scale)
    pad_y = int(42 * scale)
    badge_text = chapter.title
    if len(badge_text) > 48:
        badge_text = badge_text[:45] + "..."
    bb = draw.textbbox((0, 0), badge_text, font=badge_font)
    bw, bh = bb[2] - bb[0], bb[3] - bb[1]
    draw.rounded_rectangle(
        [pad_x, pad_y, pad_x + bw + int(32 * scale), pad_y + bh + int(32 * scale)],
        radius=int(10 * scale),
        fill=(12, 15, 24, 175),
        outline=(*accent, 140),
        width=max(1, int(2 * scale)),
    )
    draw.text((pad_x + int(16 * scale), pad_y + int(7 * scale)), badge_text, font=badge_font, fill=(*accent, 245))

    # Main text rendering by style
    text_font = get_custom_font(project.settings.font_family, project.settings.font_variant, font_size)
    word_offset = 0

    def draw_karaoke_row(line, x, y, base_fill, shadow=False):
        nonlocal word_offset
        row_word_index = None
        if active_word_index is not None:
            local_index = active_word_index - word_offset
            if 0 <= local_index < len(line.split()):
                row_word_index = local_index
        _draw_karaoke_line(draw, line, x, y, text_font, row_word_index,
                           base_fill, (*accent, 255), shadow=shadow)
        word_offset += len(line.split())

    if style == "Sottotitoli Cinema":
        lines = _wrap_text_to_width(draw, scene.text, text_font, int(width * 0.80))
        line_h = int(font_size * 1.38)
        total_h = len(lines) * line_h
        start_y = height - total_h - int(85 * scale)

        # Bottom gradient band
        band_top = max(0, start_y - int(45 * scale))
        draw.rectangle([0, band_top, width, height], fill=(8, 10, 16, 170))

        y = start_y
        for line in lines:
            lb = draw.textbbox((0, 0), line, font=text_font)
            lw = lb[2] - lb[0]
            x = (width - lw) / 2
            # Crisp cinema outline
            for ox, oy in ((-2, -2), (2, -2), (-2, 2), (2, 2), (0, 3)):
                draw.text((x + ox, y + oy), line, font=text_font, fill=(0, 0, 0, 235))
            draw_karaoke_row(line, x, y, (252, 250, 242, 255))
            y += line_h

    elif style == "Pagina Antica":
        card_w = int(width * 0.78)
        lines = _wrap_text_to_width(draw, scene.text, text_font, card_w - int(110 * scale))
        line_h = int(font_size * 1.45)
        card_h = max(int(180 * scale), len(lines) * line_h + int(90 * scale))
        card_x = (width - card_w) // 2
        card_y = height - card_h - int(64 * scale)

        draw.rounded_rectangle(
            [card_x, card_y, card_x + card_w, card_y + card_h],
            radius=int(18 * scale),
            fill=(244, 234, 212, 228),
            outline=(168, 132, 76, 220),
            width=max(2, int(3 * scale)),
        )
        y = card_y + int(42 * scale)
        for line in lines:
            draw_karaoke_row(line, card_x + int(55 * scale), y, (44, 32, 20, 255))
            y += line_h

    elif style == "Minimal Elegante":
        lines = _wrap_text_to_width(draw, scene.text, text_font, int(width * 0.76))
        line_h = int(font_size * 1.48)
        total_h = len(lines) * line_h
        start_y = height - total_h - int(92 * scale)

        # Soft bottom gradient scrim
        band_top = max(0, start_y - int(65 * scale))
        draw.rectangle([0, band_top, width, height], fill=(8, 10, 16, 155))
        rule_w = int(280 * scale)
        rule_y = start_y - int(22 * scale)
        draw.line([(width // 2 - rule_w // 2, rule_y), (width // 2 + rule_w // 2, rule_y)], fill=(*accent, 210), width=max(1, int(2 * scale)))

        y = start_y
        for line in lines:
            lb = draw.textbbox((0, 0), line, font=text_font)
            lw = lb[2] - lb[0]
            x = (width - lw) / 2
            draw.text((x + 1, y + 2), line, font=text_font, fill=(0, 0, 0, 215))
            draw_karaoke_row(line, x, y, (248, 246, 240, 255))
            y += line_h

    elif style == "Notturno Blu":
        card_w = int(width * 0.82)
        lines = _wrap_text_to_width(draw, scene.text, text_font, card_w - int(120 * scale))
        line_h = int(font_size * 1.45)
        card_h = max(int(170 * scale), len(lines) * line_h + int(84 * scale))
        card_x = (width - card_w) // 2
        card_y = height - card_h - int(64 * scale)

        draw.rounded_rectangle(
            [card_x, card_y, card_x + card_w, card_y + card_h],
            radius=int(22 * scale),
            fill=(10, 20, 40, 215),
            outline=(120, 185, 245, 165),
            width=max(2, int(2 * scale)),
        )
        y = card_y + int(40 * scale)
        for line in lines:
            lb = draw.textbbox((0, 0), line, font=text_font)
            lw = lb[2] - lb[0]
            x = (width - lw) / 2
            draw.text((x + 1, y + 2), line, font=text_font, fill=(0, 0, 0, 200))
            draw_karaoke_row(line, x, y, (230, 242, 255, 255))
            y += line_h

    else:
        # "Libro Cinematografico" (Default)
        card_w = int(width * 0.82)
        lines = _wrap_text_to_width(draw, scene.text, text_font, card_w - int(120 * scale))
        line_h = int(font_size * 1.45)
        card_h = max(int(170 * scale), len(lines) * line_h + int(84 * scale))
        card_x = (width - card_w) // 2
        card_y = height - card_h - int(64 * scale)

        # Frosted dark glass panel
        draw.rounded_rectangle(
            [card_x, card_y, card_x + card_w, card_y + card_h],
            radius=int(22 * scale),
            fill=(12, 15, 24, 205),
            outline=(*accent, 110),
            width=max(1, int(2 * scale)),
        )
        y = card_y + int(40 * scale)
        for line in lines:
            lb = draw.textbbox((0, 0), line, font=text_font)
            lw = lb[2] - lb[0]
            x = (width - lw) / 2
            draw.text((x + 1, y + 2), line, font=text_font, fill=(0, 0, 0, 200))
            draw_karaoke_row(line, x, y, (246, 243, 236, 255), shadow=True)
            y += line_h

    # Subtle bottom TV reading progress bar
    bar_h = max(3, int(5 * scale))
    draw.rectangle([0, height - bar_h, width, height], fill=(255, 255, 255, 35))
    prog_w = int(width * max(0.0, min(1.0, progress_ratio)))
    if prog_w > 0:
        draw.rectangle([0, height - bar_h, prog_w, height], fill=(*accent, 230))

    return img


def _draw_karaoke_line(draw, line, x, y, font, active_word_index, base_fill,
                       active_fill, shadow=False):
    """Draw a line with a readable three-word karaoke reading window."""
    if active_word_index is None:
        if shadow:
            draw.text((x + 1, y + 2), line, font=font, fill=(0, 0, 0, 200))
        draw.text((x, y), line, font=font, fill=base_fill)
        return
    words = line.split()
    active_indices = (
        set(range(max(0, active_word_index - 1), min(len(words), active_word_index + 2)))
        if 0 <= active_word_index < len(words)
        else set()
    )
    space_width = draw.textlength(" ", font=font)
    cursor = x
    for index, word in enumerate(words):
        is_active = index in active_indices
        # The karaoke pill is light yellow, so use a dedicated dark foreground
        # instead of the normal white text/accent color.
        fill = (48, 35, 20, 255) if is_active else base_fill
        # Draw the style shadow first so the karaoke background fully covers
        # it; otherwise its offset glyph appears doubled inside the highlight.
        if shadow and not is_active:
            draw.text((cursor + 1, y + 2), word, font=font, fill=(0, 0, 0, 200))
        if is_active:
            bbox = draw.textbbox((cursor, y), word, font=font)
            pad_x, pad_y = 4, 3
            draw.rounded_rectangle(
                (bbox[0] - pad_x, bbox[1] - pad_y, bbox[2] + pad_x, bbox[3] + pad_y),
                radius=5,
                fill=(255, 226, 64, 255),
                outline=(255, 226, 64, 255),
                width=2,
            )
        draw.text((cursor, y), word, font=font, fill=fill)
        cursor += draw.textlength(word, font=font) + space_width


def render_preview_frame(
    project: VideoBookProject,
    entry: TimelineEntry | None,
    preview_size: tuple[int, int] = (960, 540),
    progress: float = 0.0,
    active_word_index: int | None = None,
) -> Image.Image:
    """Render a fast composite preview image for the GUI TV monitor."""
    w, h = preview_size
    bg_rgb = _hex_to_rgb(project.settings.bg_fallback_color, (18, 21, 30))
    canvas = Image.new("RGBA", (w, h), (*bg_rgb, 255))

    if entry is None:
        return canvas.convert("RGB")

    # Background media preview
    if entry.media_path and Path(entry.media_path).exists() and entry.media_type == "image":
        try:
            with Image.open(entry.media_path) as src:
                src_rgba = src.convert("RGBA")
                sw, sh = src_rgba.size
                scale = max(w / sw, h / sh)
                nw, nh = int(sw * scale), int(sh * scale)
                resized = src_rgba.resize((nw, nh), Image.Resampling.LANCZOS)
                progress = max(0.0, min(1.0, progress))
                mode = "zoom_in"
                image_zoom, image_x, image_y = 1.0, 0.0, 0.0
                if entry.kind == "scene":
                    scene = project.chapters[entry.chapter_index].scenes[entry.scene_index or 0]
                    mode = scene.ken_burns
                    image_zoom, image_x, image_y = scene.image_zoom, scene.image_x, scene.image_y
                # The manual framing defines the opening shot; Ken Burns motion is
                # applied from that same zoom/position as time advances.
                if mode == "zoom_in":
                    motion_zoom, motion_x = 1.0 + 0.14 * progress, 0.0
                elif mode == "zoom_out":
                    motion_zoom, motion_x = 1.14 - 0.14 * progress, 0.0
                elif mode == "pan_left":
                    motion_zoom, motion_x = 1.12, -progress
                elif mode == "pan_right":
                    motion_zoom, motion_x = 1.12, progress
                else:
                    motion_zoom, motion_x = 1.0, 0.0
                zoom = motion_zoom * image_zoom
                zw, zh = int(nw * zoom), int(nh * zoom)
                resized = resized.resize((zw, zh), Image.Resampling.LANCZOS)
                max_left, max_top = max(0, zw - w), max(0, zh - h)
                base_left = max_left / 2 - motion_x * max_left / 2
                left = max(0, min(max_left, int(base_left - w * image_x / 2)))
                top = max(0, min(max_top, int(max_top / 2 - h * image_y / 2)))
                canvas = resized.crop((left, top, left + w, top + h))
        except Exception:
            pass
    elif entry.media_type == "video" and entry.media_path:
        # Subtle indicator backdrop for video clips
        draw_bg = ImageDraw.Draw(canvas)
        draw_bg.rectangle([0, 0, w, h], fill=(20, 28, 42, 255))
        vfont = _get_sans_font(20, bold=True)
        draw_bg.text((w // 2 - 140, h // 3), f"VIDEO CLIP: {Path(entry.media_path).name}", font=vfont, fill=(140, 175, 220, 180))

    ch = project.chapters[entry.chapter_index]
    if entry.kind == "title_card":
        overlay = render_title_card_overlay(project, ch, w, h)
    else:
        sc = ch.scenes[entry.scene_index or 0]
        total_dur = max(1.0, project.total_duration())
        ratio = entry.end_sec / total_dur
        overlay = render_scene_overlay(project, ch, sc, ratio, w, h, active_word_index)

    combined = Image.alpha_composite(canvas.convert("RGBA"), overlay)
    return combined.convert("RGB")


def _zoompan_filter(mode: KenBurnsMode, width: int, height: int, fps: int, frames: int,
                    image_zoom: float = 1.0, image_x: float = 0.0, image_y: float = 0.0) -> str:
    frames = max(2, frames)
    # Pre-scale high enough for smooth subpixel Ken Burns motion
    pre_w = int(width * 1.25)
    pre_h = int(height * 1.25)
    base = f"scale={pre_w}:{pre_h}:force_original_aspect_ratio=increase,crop={pre_w}:{pre_h},setsar=1"

    if mode == "zoom_out":
        motion_z = f"max(1.0,1.14-0.14*on/({frames}-1))"
        motion_x = "0"
    elif mode == "pan_left":
        motion_z = "1.12"
        motion_x = f"-(on/({frames}-1))"
    elif mode == "pan_right":
        motion_z = "1.12"
        motion_x = f"(on/({frames}-1))"
    elif mode == "static":
        motion_z = "1.0"
        motion_x = "0"
    else:  # zoom_in
        motion_z = f"min(1.14,1.0+0.14*on/({frames}-1))"
        motion_x = "0"
    zp = (f"zoompan=z='min(3.0,({motion_z})*{image_zoom:.4f})':"
          f"x='iw/2-(iw/zoom/2)+({motion_x})*(iw-iw/zoom)/2-({image_x:.4f})*(iw-iw/zoom)/2':"
          f"y='ih/2-(ih/zoom/2)-({image_y:.4f})*(ih-ih/zoom)/2':"
          f"d=1:s={width}x{height}:fps={fps}")
    return f"{base},{zp}"


def _run_ffmpeg(
    args: list[str],
    cancel_event: threading.Event | None = None,
    progress_file: Path | None = None,
    duration_sec: float = 0.0,
    progress_cb: Callable[[float], None] | None = None,
    log_path: Path | None = None,
    log_label: str = "FFmpeg",
) -> None:
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    started = time.monotonic()
    last_log = started
    if log_path:
        write_export_log(log_path, f"{log_label}: avvio processo FFmpeg")
    proc = subprocess.Popen(
        [ffmpeg_exe, "-y", *args],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    stderr_lines: deque[str] = deque(maxlen=200)

    def _drain_stderr() -> None:
        if proc.stderr is None:
            return
        try:
            for line in proc.stderr:
                stderr_lines.append(line)
        finally:
            proc.stderr.close()

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    while proc.poll() is None:
        if cancel_event and cancel_event.is_set():
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
            stderr_thread.join(timeout=1)
            raise ExportCancelledError("Esportazione annullata dall'utente.")
        if progress_file and duration_sec > 0 and progress_cb and progress_file.exists():
            try:
                latest = {}
                for line in progress_file.read_text(encoding="utf-8", errors="ignore").splitlines()[-16:]:
                    if "=" in line:
                        key, value = line.split("=", 1)
                        latest[key] = value
                out_time = int(latest.get("out_time_us", "0")) / 1_000_000
                if out_time == 0:
                    out_time = int(latest.get("out_time_ms", "0")) / 1_000_000
                progress_cb(min(1.0, max(0.0, out_time / duration_sec)))
            except (OSError, ValueError):
                pass
        now = time.monotonic()
        if log_path and now - last_log >= 15:
            write_export_log(log_path, f"{log_label}: FFmpeg ancora in esecuzione da {int(now - started)} s")
            last_log = now
        time.sleep(0.15)
    proc.wait()
    stderr_thread.join(timeout=2)
    stderr = "".join(stderr_lines)
    if proc.returncode != 0:
        if log_path:
            write_export_log(log_path, f"{log_label}: errore FFmpeg (codice {proc.returncode})\n{(stderr or '')[-5000:]}")
        raise RuntimeError(f"FFmpeg error:\n{(stderr or '')[-1200:]}")
    if log_path:
        write_export_log(log_path, f"{log_label}: completato in {int(time.monotonic() - started)} s")


def export_project_to_mp4(
    project: VideoBookProject,
    output_mp4: str | Path,
    generate_missing_tts: bool = True,
    progress_cb: ProgressCallback | None = None,
    size_cb: SizeCallback | None = None,
    cancel_event: threading.Event | None = None,
    output_format: str = "mp4",
    speed_mode: str = "standard",
) -> Path:
    """Render the complete VideoLibro project to a TV-ready H.264/AAC MP4 file."""
    out_path = Path(output_mp4)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    log_path = out_path.with_name(f"{out_path.stem}_export.log")
    write_export_log(log_path, "=" * 60)
    write_export_log(log_path, f"Avvio esportazione: {out_path}")
    write_export_log(log_path, f"Risoluzione {project.settings.resolution}, {project.settings.fps} fps, profilo {speed_mode}")
    w, h = project.settings.width, project.settings.height
    fps = project.settings.fps
    output_format = "mkv" if output_format.lower() == "mkv" else "mp4"
    speed_mode = "quick" if speed_mode == "quick" else "standard"
    preset, crf = ("ultrafast", "23") if speed_mode == "quick" else ("fast", "20")

    with tempfile.TemporaryDirectory(prefix="videolibro_") as tmp:
        tmp_dir = Path(tmp)
        tts_dir = tmp_dir / "tts"

        # 1. Generate missing TTS audio if requested
        total_scenes = sum(len(ch.scenes) for ch in project.chapters)
        done_scenes = 0
        if generate_missing_tts:
            for ch in project.chapters:
                for sc in ch.scenes:
                    if cancel_event and cancel_event.is_set():
                        raise ExportCancelledError("Esportazione annullata dall'utente.")
                    done_scenes += 1
                    if not sc.tts_audio_path or not Path(sc.tts_audio_path).exists():
                        write_export_log(log_path, f"TTS scena {done_scenes}/{total_scenes}: avvio sintesi")
                        if progress_cb:
                            pct = int(5 + 25 * (done_scenes / max(1, total_scenes)))
                            progress_cb(pct, f"Sintesi vocale TTS ({done_scenes}/{total_scenes})...")
                        ap, dur, timings = synthesize_scene_tts(
                            sc.text,
                            tts_dir,
                            sc.id,
                            voice=project.settings.tts_voice,
                            rate=project.settings.tts_rate,
                            engine=project.settings.tts_engine,
                        )
                        sc.tts_audio_path = ap
                        sc.tts_duration_sec = dur
                        sc.word_timings = timings
                        write_export_log(log_path, f"TTS scena {done_scenes}/{total_scenes}: completata ({dur:.1f} s audio)")

        # Keep TTS generated in this temporary render directory after export.
        tts_store = out_path.parent / f"{out_path.stem}_tts"
        for chapter in project.chapters:
            for scene in chapter.scenes:
                source = Path(scene.tts_audio_path) if scene.tts_audio_path else None
                if source and source.is_file() and source.is_relative_to(tmp_dir):
                    tts_store.mkdir(parents=True, exist_ok=True)
                    destination = tts_store / f"{scene.id}{source.suffix}"
                    shutil.copy2(source, destination)
                    scene.tts_audio_path = str(destination)

        entries = project.compute_timeline()
        if not entries:
            raise ValueError("Il progetto non contiene capitoli o scene da esportare.")

        total_dur = max(1.0, project.total_duration())
        segment_paths: list[Path] = []

        # 2. Render each timeline segment
        accumulated_bytes = 0
        progress_file = tmp_dir / "ffmpeg_progress.txt"
        segment_ext = ".mkv" if output_format == "mkv" else ".mp4"
        for idx, entry in enumerate(entries):
            if cancel_event and cancel_event.is_set():
                raise ExportCancelledError("Esportazione annullata dall'utente.")
            if progress_cb:
                pct = int(30 + 60 * (idx / len(entries)))
                progress_cb(pct, f"Rendering scena {idx + 1}/{len(entries)}: {entry.label}")
            write_export_log(log_path, f"Scena {idx + 1}/{len(entries)} avvio: {entry.label!r}, tipo={entry.kind}, durata={entry.duration_sec:.2f} s, media={entry.media_path or '(nessuna)'}")

            ch = project.chapters[entry.chapter_index]
            dur = entry.duration_sec
            frames = int(round(dur * fps))

            # Render RGBA overlay PNG. When karaoke is enabled, use a short
            # overlay image sequence so the highlight follows the narration.
            overlay_png = tmp_dir / f"overlay_{idx:04d}.png"
            overlay_sequence = False
            if entry.kind == "title_card":
                ov_img = render_title_card_overlay(project, ch, w, h)
                kb_mode: KenBurnsMode = "zoom_in"
                image_zoom, image_x, image_y = 1.0, 0.0, 0.0
                tts_path = ""
            else:
                sc = ch.scenes[entry.scene_index or 0]
                tts_path = sc.tts_audio_path if sc.tts_audio_path and Path(sc.tts_audio_path).is_file() else ""
                overlay_sequence = bool(project.settings.karaoke_enabled and sc.text.strip())
                if overlay_sequence:
                    overlay_fps = fps
                    count = max(1, int(round(dur * overlay_fps)))
                    for frame_index in range(count):
                        elapsed = frame_index / overlay_fps
                        if sc.word_timings and tts_path:
                            active_word = next(
                                (
                                    word_index
                                    for word_index, timing in enumerate(sc.word_timings)
                                    if float(timing.get("offset_sec", 0.0)) <= elapsed
                                    < float(timing.get("offset_sec", 0.0))
                                    + max(0.05, float(timing.get("duration_sec", 0.0)))
                                ),
                                None,
                            )
                        else:
                            # TTS engines without word boundaries still get a
                            # usable timed karaoke effect across the scene.
                            speech_dur = max(0.1, min(dur, sc.tts_duration_sec or dur))
                            active_word = min(
                                max(0, len(sc.text.split()) - 1),
                                int(elapsed / speech_dur * len(sc.text.split())),
                            ) if elapsed < speech_dur else None
                        frame = render_scene_overlay(
                            project, ch, sc, entry.end_sec / total_dur, w, h, active_word
                        )
                        frame.save(tmp_dir / f"overlay_{idx:04d}_{frame_index:05d}.png", "PNG")
                    ov_img = render_scene_overlay(project, ch, sc, entry.end_sec / total_dur, w, h)
                else:
                    ov_img = render_scene_overlay(project, ch, sc, entry.end_sec / total_dur, w, h)
                kb_mode = sc.ken_burns
                image_zoom, image_x, image_y = sc.image_zoom, sc.image_x, sc.image_y
            ov_img.save(overlay_png, "PNG")
            write_export_log(log_path, f"Scena {idx + 1}/{len(entries)} overlay pronto" + (f" (sequenza karaoke: {count} fotogrammi)" if overlay_sequence else ""))

            seg_mp4 = tmp_dir / f"seg_{idx:04d}{segment_ext}"
            args: list[str] = []

            # Video input 0
            has_media = bool(entry.media_path and Path(entry.media_path).exists())
            if has_media and entry.media_type == "video":
                args += ["-stream_loop", "-1", "-t", f"{dur:.2f}", "-i", entry.media_path]
                v_base = f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={fps}[bg]"
            elif has_media and entry.media_type == "image":
                args += ["-loop", "1", "-t", f"{dur:.2f}", "-i", entry.media_path]
                v_base = f"[0:v]{_zoompan_filter(kb_mode, w, h, fps, frames, image_zoom, image_x, image_y)}[bg]"
            else:
                bg_hex = project.settings.bg_fallback_color.lstrip("#")
                args += ["-f", "lavfi", "-t", f"{dur:.2f}", "-i", f"color=c=0x{bg_hex}:s={w}x{h}:r={fps}"]
                v_base = "[0:v]null[bg]"

            # Overlay input 1
            if overlay_sequence:
                args += ["-framerate", str(overlay_fps), "-i", str(tmp_dir / f"overlay_{idx:04d}_%05d.png")]
                # Numbered PNG inputs need their input cadence retained;
                # otherwise FFmpeg treats them as 25 fps and fades/flattens
                # the karaoke progression before the output frame rate step.
                v_base = v_base.replace("[bg]", f"[bg];[1:v]fps={fps}[karaoke]", 1)
                overlay_input = "[karaoke]"
            else:
                args += ["-loop", "1", "-t", f"{dur:.2f}", "-i", str(overlay_png)]
                overlay_input = "[1:v]"

            fade_out_st = max(0.1, dur - 0.35)
            v_filter = (
                f"{v_base};"
                f"{overlay_input}format=rgba,fade=t=in:st=0:d=0.35:alpha=1,fade=t=out:st={fade_out_st:.2f}:d=0.35:alpha=1[ov];"
                f"[bg][ov]overlay=0:0:shortest=1,trim=duration={dur:.2f},setpts=PTS-STARTPTS[vout]"
            )

            # Audio mixing (TTS + optional background music with auto-ducking)
            has_bg_music = bool(entry.bg_audio_path and Path(entry.bg_audio_path).exists())
            a_inputs: list[str] = []
            a_filters: list[str] = []
            next_in = 2

            if tts_path:
                args += ["-i", tts_path]
                a_filters.append(f"[{next_in}:a]apad=whole_dur={dur:.2f},atrim=0:{dur:.2f}[tts]")
                a_inputs.append("[tts]")
                next_in += 1

            if has_bg_music:
                # Seek into background music by entry.start_sec so music flows across scenes!
                args += ["-stream_loop", "-1", "-ss", f"{entry.start_sec:.2f}", "-t", f"{dur:.2f}", "-i", entry.bg_audio_path]
                vol = entry.bg_audio_volume
                if tts_path and project.settings.auto_ducking:
                    vol *= project.settings.ducking_factor
                a_filters.append(f"[{next_in}:a]volume={vol:.3f},atrim=0:{dur:.2f}[bgm]")
                a_inputs.append("[bgm]")
                next_in += 1

            if len(a_inputs) == 2:
                a_filters.append("[tts][bgm]amix=inputs=2:duration=first:normalize=0[aout]")
            elif len(a_inputs) == 1:
                a_filters.append(f"{a_inputs[0]}anull[aout]")
            else:
                args += ["-f", "lavfi", "-t", f"{dur:.2f}", "-i", "anullsrc=r=44100:cl=stereo"]
                a_filters.append(f"[{next_in}:a]atrim=0:{dur:.2f}[aout]")

            full_filter = f"{v_filter};{';'.join(a_filters)}"
            args += [
                "-filter_complex",
                full_filter,
                "-map",
                "[vout]",
                "-map",
                "[aout]",
                "-c:v",
                "libx264",
                "-preset",
                preset,
                "-crf",
                crf,
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "44100",
                "-ac",
                "2",
                "-t",
                f"{dur:.2f}",
                str(seg_mp4),
            ]
            if progress_file.exists():
                progress_file.unlink()
            args = ["-progress", str(progress_file), "-stats_period", "0.5", "-nostats", *args]
            def report_segment_progress(fraction: float, segment_index: int = idx) -> None:
                overall = (segment_index + fraction) / len(entries)
                if progress_cb:
                    pct = int(30 + 60 * overall)
                    progress_cb(pct, f"Rendering scena {segment_index + 1}/{len(entries)}: {entries[segment_index].label}")

            _run_ffmpeg(
                args,
                cancel_event=cancel_event,
                progress_file=progress_file,
                duration_sec=dur,
                progress_cb=report_segment_progress,
                log_path=log_path,
                log_label=f"Scena {idx + 1}/{len(entries)}",
            )
            segment_paths.append(seg_mp4)
            if seg_mp4.exists():
                accumulated_bytes += seg_mp4.stat().st_size
                write_export_log(log_path, f"Scena {idx + 1}/{len(entries)} completata, file temporaneo {_fmt_log_bytes(seg_mp4.stat().st_size)}")
                if size_cb:
                    size_cb(accumulated_bytes)

        # 3. Concatenate all segments into the selected output container
        if progress_cb:
            progress_cb(93, "Assemblaggio finale del VideoLibro MP4...")
        write_export_log(log_path, f"Assemblaggio finale di {len(segment_paths)} segmenti")

        concat_txt = tmp_dir / "concat.txt"
        concat_txt.write_text(
            "\n".join(f"file '{p.as_posix()}'" for p in segment_paths),
            encoding="utf-8",
        )
        temp_fd, temp_name = tempfile.mkstemp(
            prefix=f".{out_path.stem}_rendering_", suffix=segment_ext, dir=out_path.parent
        )
        os.close(temp_fd)
        temp_output = Path(temp_name)
        try:
            _run_ffmpeg(
                [
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(concat_txt),
                    "-c",
                    "copy",
                    *( ["-movflags", "+faststart"] if output_format == "mp4" else [] ),
                    str(temp_output),
                ],
                cancel_event=cancel_event,
                log_path=log_path,
                log_label="Assemblaggio finale",
            )
            temp_output.replace(out_path)
        except Exception:
            temp_output.unlink(missing_ok=True)
            raise
        if out_path.exists() and size_cb:
            size_cb(out_path.stat().st_size)

    if progress_cb:
        progress_cb(100, f"VideoLibro completato: {out_path.name}")
    write_export_log(log_path, f"Esportazione completata: {out_path} ({out_path.stat().st_size} byte)")
    return out_path
