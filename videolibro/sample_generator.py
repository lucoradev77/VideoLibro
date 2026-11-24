"""Creates a ready-to-use demo manuscript (.docx), atmospheric backgrounds, and ambient music."""

from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path

from docx import Document
from PIL import Image, ImageDraw, ImageFilter

from .importer import import_manuscript_file
from .models import VideoBookProject


def _create_atmospheric_image(path: Path, palette: tuple[tuple[int, int, int], tuple[int, int, int]], motif: str) -> None:
    w, h = 1920, 1080
    img = Image.new("RGB", (w, h), palette[0])
    draw = ImageDraw.Draw(img)

    # Vertical gradient sky/atmosphere
    r1, g1, b1 = palette[0]
    r2, g2, b2 = palette[1]
    for y in range(h):
        t = y / h
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))

    rng = random.Random(motif)
    if motif == "library":
        # Warm candlelit arches & dust motes
        for x in range(180, w, 380):
            draw.ellipse([x - 140, 140, x + 140, 520], fill=(72, 48, 28))
            draw.rectangle([x - 140, 320, x + 140, h], fill=(56, 36, 22))
        for _ in range(90):
            px, py = rng.randint(0, w), rng.randint(0, h)
            rad = rng.randint(2, 6)
            draw.ellipse([px - rad, py - rad, px + rad, py + rad], fill=(240, 195, 110))
    elif motif == "tower":
        # Moonlit mountains & stars
        for _ in range(180):
            sx, sy = rng.randint(0, w), rng.randint(0, int(h * 0.65))
            draw.point((sx, sy), fill=(235, 240, 255))
        draw.ellipse([1360, 120, 1540, 300], fill=(235, 228, 200))
        draw.polygon([(0, h), (350, 560), (760, h)], fill=(18, 24, 38))
        draw.polygon([(520, h), (980, 460), (1460, h)], fill=(14, 19, 30))
        draw.polygon([(1150, h), (1620, 580), (w, h)], fill=(20, 26, 40))
    else:
        # Starry sea horizon
        for _ in range(220):
            sx, sy = rng.randint(0, w), rng.randint(0, int(h * 0.55))
            draw.point((sx, sy), fill=(210, 230, 255))
        draw.rectangle([0, int(h * 0.58), w, h], fill=(10, 24, 42))
        for i in range(40):
            ry = int(h * 0.60) + i * 10
            rw = max(20, 260 - i * 5)
            draw.line([(w // 2 - rw, ry), (w // 2 + rw, ry)], fill=(140, 185, 220), width=2)

    img = img.filter(ImageFilter.GaussianBlur(radius=2.5))
    img.save(path, "JPEG", quality=92)


def _create_ambient_wav(path: Path, duration_sec: float = 24.0) -> None:
    """Synthesize a gentle, warm ambient chord drone in pure Python."""
    sample_rate = 22050
    total_samples = int(sample_rate * duration_sec)
    freqs = [110.0, 164.81, 220.0, 277.18]  # A2, E3, A3, C#4 (warm A-major ambient pad)

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)

        frames = bytearray()
        for i in range(total_samples):
            t = i / sample_rate
            # Gentle breathing envelope
            env = 0.55 + 0.45 * math.sin(2 * math.pi * 0.12 * t)
            fade = min(1.0, t / 1.5, (duration_sec - t) / 1.5)
            val = sum(math.sin(2 * math.pi * f * t) for f in freqs) / len(freqs)
            sample = int(max(-1.0, min(1.0, val * env * fade * 0.45)) * 32767)
            frames.extend(struct.pack("<h", sample))
        wf.writeframes(bytes(frames))


def build_demo_project(workspace_dir: str | Path) -> VideoBookProject:
    """Create a complete demo .docx manuscript, media assets, and VideoBookProject."""
    demo_dir = Path(workspace_dir) / "demo_assets"
    demo_dir.mkdir(parents=True, exist_ok=True)

    docx_path = demo_dir / "Il_Manoscritto_di_Pietra.docx"
    bg1 = demo_dir / "bg_biblioteca.jpg"
    bg2 = demo_dir / "bg_torre.jpg"
    bg3 = demo_dir / "bg_mare.jpg"
    bgm = demo_dir / "ambient_sottofondo.wav"

    if not docx_path.exists():
        doc = Document()
        doc.add_heading("Il Manoscritto di Pietra", level=0)
        doc.add_heading("Capitolo I - La Biblioteca Sommersa", level=1)
        doc.add_paragraph(
            "Quando Elena aprì la porta di quercia, l'odore di pergamena antica e polvere d'oro "
            "riempì la stanza silenziosa. Sul tavolo di marmo riposava un manoscritto cucito a mano."
        )
        doc.add_paragraph(
            "Le parole sembravano cambiare colore sotto la luce delle candele, come se l'inchiostro "
            "conservasse ancora il respiro di chi lo aveva tracciato secoli prima."
        )
        doc.add_heading("Capitolo II - La Torre della Luna", level=1)
        doc.add_paragraph(
            "Salendo la scala a chiocciola verso la cima della torre, il vento della notte portava "
            "echi di storie dimenticate. Ogni gradino inciso raccontava una rotta verso il nord."
        )
        doc.add_heading("Capitolo III - Oltre l'Orizzonte", level=1)
        doc.add_paragraph(
            "All'alba, il mare si aprì davanti ai suoi occhi come una pagina bianca. "
            "Il manoscritto non era più soltanto un libro: era diventato un viaggio da guardare e ascoltare."
        )
        doc.save(str(docx_path))

    if not bg1.exists():
        _create_atmospheric_image(bg1, ((28, 18, 12), (64, 42, 24)), "library")
    if not bg2.exists():
        _create_atmospheric_image(bg2, ((12, 18, 36), (34, 48, 74)), "tower")
    if not bg3.exists():
        _create_atmospheric_image(bg3, ((14, 22, 44), (24, 46, 72)), "sea")
    if not bgm.exists():
        _create_ambient_wav(bgm, duration_sec=24.0)

    title, chapters = import_manuscript_file(docx_path)
    bgs = [str(bg1), str(bg2), str(bg3)]
    for idx, ch in enumerate(chapters):
        ch.default_media_path = bgs[idx % len(bgs)]
        ch.default_media_type = "image"
        ch.bg_audio_path = str(bgm)
        ch.bg_audio_volume = 0.25

    project = VideoBookProject(
        title=title,
        author="Archivio VideoLibro",
        source_file=str(docx_path),
        chapters=chapters,
    )
    project.settings.global_bg_audio_path = str(bgm)
    return project
