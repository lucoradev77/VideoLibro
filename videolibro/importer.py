"""Manuscript importer for .docx, .txt, and .md files with automatic or manual chapters."""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document

from .models import Chapter, SceneBlock

CHAPTER_PATTERN = re.compile(
    r"^(?:capitolo|chapter|parte|part|prologo|epilogo|prologue|epilogue|atto)\b.*$"
    r"|^(?:[IVXLCDM]+)\s*[.\-–—:]\s*.+$",
    re.IGNORECASE,
)


def split_text_into_scenes(text: str, max_chars: int = 250) -> list[SceneBlock]:
    """Split a block of prose into TV-readable scenes at sentence boundaries."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
    scenes: list[SceneBlock] = []

    for para in paragraphs:
        if len(para) <= max_chars:
            scenes.append(SceneBlock(text=para, duration_sec=_estimate_reading_sec(para)))
            continue

        sentences = re.split(r"(?<=[.!?…»\"])\s+", para)
        buffer = ""
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            if not buffer:
                buffer = sent
            elif len(buffer) + 1 + len(sent) <= max_chars:
                buffer = f"{buffer} {sent}"
            else:
                scenes.append(SceneBlock(text=buffer, duration_sec=_estimate_reading_sec(buffer)))
                buffer = sent
        if buffer:
            scenes.append(SceneBlock(text=buffer, duration_sec=_estimate_reading_sec(buffer)))

    return scenes


def _estimate_reading_sec(text: str) -> float:
    words = max(1, len(text.split()))
    # ~145 words per minute comfortable narration/reading pace
    return round(max(3.0, (words / 2.4)), 1)


def _is_heading_paragraph(para) -> bool:
    style_name = (para.style.name or "").lower() if para.style else ""
    if any(k in style_name for k in ("heading 1", "heading 2", "titolo 1", "titolo 2", "title")):
        return True
    txt = para.text.strip()
    if len(txt) <= 80 and CHAPTER_PATTERN.match(txt):
        return True
    return False


def import_docx(
    file_path: str | Path,
    auto_detect_chapters: bool = True,
    max_chars_per_scene: int = 250,
) -> tuple[str, list[Chapter]]:
    """Import a Word (.docx) manuscript into structured Chapters and SceneBlocks."""
    path = Path(file_path)
    doc = Document(str(path))
    book_title = path.stem.replace("_", " ").strip() or "Manoscritto"

    chapters: list[Chapter] = []
    current_title = "Capitolo 1"
    current_paragraphs: list[str] = []
    found_first_heading = False

    for para in doc.paragraphs:
        txt = para.text.strip()
        if not txt:
            continue

        if auto_detect_chapters and _is_heading_paragraph(para):
            style_name = (para.style.name or "").lower() if para.style else ""
            if "title" in style_name and not found_first_heading and not current_paragraphs:
                book_title = txt
                continue

            if current_paragraphs:
                chapters.append(
                    Chapter(
                        title=current_title,
                        scenes=split_text_into_scenes("\n\n".join(current_paragraphs), max_chars_per_scene),
                    )
                )
                current_paragraphs = []
            current_title = txt
            found_first_heading = True
        else:
            current_paragraphs.append(txt)

    if current_paragraphs or not chapters:
        chapters.append(
            Chapter(
                title=current_title,
                scenes=split_text_into_scenes("\n\n".join(current_paragraphs), max_chars_per_scene),
            )
        )

    return book_title, chapters


def import_plain_text(
    text: str,
    title: str = "Manoscritto",
    auto_detect_chapters: bool = True,
    max_chars_per_scene: int = 250,
) -> tuple[str, list[Chapter]]:
    """Import raw text or .txt/.md content into Chapters and SceneBlocks."""
    lines = text.splitlines()
    chapters: list[Chapter] = []
    current_title = "Capitolo 1"
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            current_lines.append("")
            continue

        is_md_heading = stripped.startswith("# ") or stripped.startswith("## ")
        is_pattern_heading = len(stripped) <= 80 and bool(CHAPTER_PATTERN.match(stripped))

        if auto_detect_chapters and (is_md_heading or is_pattern_heading):
            clean_heading = stripped.lstrip("# ").strip()
            if any(l.strip() for l in current_lines):
                chapters.append(
                    Chapter(
                        title=current_title,
                        scenes=split_text_into_scenes("\n".join(current_lines), max_chars_per_scene),
                    )
                )
                current_lines = []
            current_title = clean_heading
        else:
            current_lines.append(stripped)

    if any(l.strip() for l in current_lines) or not chapters:
        chapters.append(
            Chapter(
                title=current_title,
                scenes=split_text_into_scenes("\n".join(current_lines), max_chars_per_scene),
            )
        )

    return title, chapters


def import_manuscript_file(
    file_path: str | Path,
    auto_detect_chapters: bool = True,
    max_chars_per_scene: int = 250,
) -> tuple[str, list[Chapter]]:
    """Unified entry point for .docx, .txt, and .md manuscripts."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return import_docx(path, auto_detect_chapters, max_chars_per_scene)
    text = path.read_text(encoding="utf-8", errors="replace")
    return import_plain_text(
        text,
        title=path.stem.replace("_", " ").strip() or "Manoscritto",
        auto_detect_chapters=auto_detect_chapters,
        max_chars_per_scene=max_chars_per_scene,
    )
