"""Modal Chapter Media Studio with interactive per-chapter cards."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from PIL import Image, ImageDraw
from PIL.ImageQt import ImageQt
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..models import Chapter, VideoBookProject

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


class _InteractiveCardPreview(QLabel):
    """16:9 thumbnail that lets the user drag to pan (X, Y) and scroll to zoom."""

    transformChanged = Signal(float, float, float)  # zoom, x, y

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(360, 202)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("Trascina per impostare la posizione iniziale • Rotellina per zoom")
        self.setStyleSheet(
            "background-color: #0D1018; border: 1px solid #2A3244; border-radius: 6px;"
        )
        self._zoom = 1.0
        self._x = 0.0
        self._y = 0.0
        self._drag_start = None
        self._start_xy = (0.0, 0.0)
        self._cached_path: str = ""
        self._cached_img: Image.Image | None = None

    def set_state(self, media_path: str, zoom: float, x: float, y: float) -> None:
        self._zoom = max(1.0, min(3.0, float(zoom)))
        self._x = max(-1.0, min(1.0, float(x)))
        self._y = max(-1.0, min(1.0, float(y)))
        if media_path != self._cached_path:
            self._cached_path = media_path
            self._cached_img = None
            if media_path and Path(media_path).is_file():
                suf = Path(media_path).suffix.lower()
                if suf in IMAGE_EXTS:
                    try:
                        with Image.open(media_path) as im:
                            self._cached_img = im.convert("RGB")
                    except Exception:
                        self._cached_img = None
        self._render()

    def _render(self) -> None:
        w, h = self.width(), self.height()
        if self._cached_img is not None:
            src = self._cached_img
            sw, sh = src.size
            target_aspect = w / h
            src_aspect = sw / max(1, sh)
            if src_aspect > target_aspect:
                crop_h = sh
                crop_w = int(round(sh * target_aspect))
            else:
                crop_w = sw
                crop_h = int(round(sw / target_aspect))

            zoom = max(1.0, self._zoom)
            zw = max(16, int(round(crop_w / zoom)))
            zh = max(9, int(round(crop_h / zoom)))
            max_dx = max(0, (sw - zw) // 2)
            max_dy = max(0, (sh - zh) // 2)
            cx = sw // 2 + int(round(self._x * max_dx))
            cy = sh // 2 + int(round(self._y * max_dy))
            left = max(0, min(sw - zw, cx - zw // 2))
            top = max(0, min(sh - zh, cy - zh // 2))
            cropped = src.crop((left, top, left + zw, top + zh)).resize(
                (w, h), Image.Resampling.LANCZOS
            )
            # Subtle center crosshair guide so starting position is obvious
            draw = ImageDraw.Draw(cropped)
            mx, my = w // 2, h // 2
            draw.line([(mx - 10, my), (mx + 10, my)], fill=(224, 180, 106), width=1)
            draw.line([(mx, my - 10), (mx, my + 10)], fill=(224, 180, 106), width=1)
            qimg = ImageQt(cropped)
            self.setPixmap(QPixmap.fromImage(qimg))
            return

        # Placeholder for video or empty media
        canvas = Image.new("RGB", (w, h), (15, 19, 30))
        draw = ImageDraw.Draw(canvas)
        draw.rectangle([8, 8, w - 9, h - 9], outline=(46, 56, 80), width=1)
        if self._cached_path and Path(self._cached_path).suffix.lower() in VIDEO_EXTS:
            label = f"VIDEO: {Path(self._cached_path).name[:28]}"
        elif self._cached_path:
            label = Path(self._cached_path).name[:32]
        else:
            label = "Nessun media impostato"
        draw.text((20, h // 2 - 8), label, fill=(170, 182, 204))
        self.setPixmap(QPixmap.fromImage(ImageQt(canvas)))

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position()
            self._start_xy = (self._x, self._y)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_start is not None:
            dx = (event.position().x() - self._drag_start.x()) / max(1, self.width())
            dy = (event.position().y() - self._drag_start.y()) / max(1, self.height())
            # Dragging image right moves viewport left (negative offset)
            nx = max(-1.0, min(1.0, round(self._start_xy[0] - dx * 2.0, 2)))
            ny = max(-1.0, min(1.0, round(self._start_xy[1] - dy * 2.0, 2)))
            if nx != self._x or ny != self._y:
                self._x, self._y = nx, ny
                self._render()
                self.transformChanged.emit(self._zoom, self._x, self._y)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_start = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if delta != 0:
            step = 0.1 if delta > 0 else -0.1
            nz = max(1.0, min(3.0, round(self._zoom + step, 2)))
            if nz != self._zoom:
                self._zoom = nz
                self._render()
                self.transformChanged.emit(self._zoom, self._x, self._y)
        event.accept()


class ChapterMediaCard(QFrame):
    """Card widget for configuring one chapter's visual media and starting position."""

    applyToAllRequested = Signal(object)

    def __init__(
        self,
        chapter_index: int,
        chapter: Chapter,
        library_items: Sequence[tuple[str, str]],
        workspace_dir: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.chapter_index = chapter_index
        self.chapter = chapter
        self.workspace_dir = workspace_dir
        self._updating = False

        # Derive initial transform from first scene if available
        first_scene = chapter.scenes[0] if chapter.scenes else None
        self._media_path = chapter.default_media_path or ""
        self._ken_burns = first_scene.ken_burns if first_scene else "zoom_in"
        self._zoom = first_scene.image_zoom if first_scene else 1.0
        self._x = first_scene.image_x if first_scene else 0.0
        self._y = first_scene.image_y if first_scene else 0.0

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "ChapterMediaCard { background-color: #151A26; border: 1px solid #2A3348; border-radius: 10px; }"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Header
        hdr = QHBoxLayout()
        title_lbl = QLabel(f"Capitolo {chapter_index + 1}: {chapter.title}")
        title_lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #E0B46A;")
        badge = QLabel(f"{len(chapter.scenes)} scene")
        badge.setStyleSheet(
            "background-color: #20283B; color: #A9B7D0; padding: 2px 8px; border-radius: 9px; font-size: 11px;"
        )
        hdr.addWidget(title_lbl, 1)
        hdr.addWidget(badge)
        root.addLayout(hdr)

        # Interactive 16:9 preview
        self.preview = _InteractiveCardPreview()
        self.preview.transformChanged.connect(self._on_preview_transform)
        root.addWidget(self.preview, alignment=Qt.AlignmentFlag.AlignCenter)

        # File path + browse / clear
        file_row = QHBoxLayout()
        self.lbl_file = QLabel()
        self.lbl_file.setStyleSheet("color: #B4C0D6; font-size: 11px;")
        btn_browse = QPushButton("📁 Sfoglia…")
        btn_browse.clicked.connect(self._browse_media)
        btn_clear = QPushButton("✕")
        btn_clear.setFixedWidth(28)
        btn_clear.setToolTip("Rimuovi media dal capitolo")
        btn_clear.clicked.connect(self._clear_media)
        file_row.addWidget(self.lbl_file, 1)
        file_row.addWidget(btn_browse)
        file_row.addWidget(btn_clear)
        root.addLayout(file_row)

        # Library / preset quick selector
        lib_row = QHBoxLayout()
        self.cmb_library = QComboBox()
        self.cmb_library.addItem("Scegli da Libreria / Predefiniti…", "")
        for label, path_str in library_items:
            self.cmb_library.addItem(label, path_str)
        self.cmb_library.currentIndexChanged.connect(self._on_library_picked)
        lib_row.addWidget(self.cmb_library, 1)
        root.addLayout(lib_row)

        # Motion & Starting position controls
        grid = QGridLayout()
        grid.setSpacing(6)

        self.cmb_motion = QComboBox()
        self.cmb_motion.addItems(["zoom_in", "zoom_out", "pan_left", "pan_right", "static"])
        self.cmb_motion.setCurrentText(self._ken_burns)
        self.cmb_motion.currentTextChanged.connect(self._on_controls_changed)

        self.spin_zoom = QDoubleSpinBox()
        self.spin_zoom.setRange(1.0, 3.0)
        self.spin_zoom.setSingleStep(0.05)
        self.spin_zoom.setSuffix("×")
        self.spin_zoom.setValue(self._zoom)
        self.spin_zoom.valueChanged.connect(self._on_controls_changed)

        self.spin_x = QDoubleSpinBox()
        self.spin_x.setRange(-1.0, 1.0)
        self.spin_x.setSingleStep(0.05)
        self.spin_x.setValue(self._x)
        self.spin_x.valueChanged.connect(self._on_controls_changed)

        self.spin_y = QDoubleSpinBox()
        self.spin_y.setRange(-1.0, 1.0)
        self.spin_y.setSingleStep(0.05)
        self.spin_y.setValue(self._y)
        self.spin_y.valueChanged.connect(self._on_controls_changed)

        btn_center = QPushButton("⌖ Centra")
        btn_center.setToolTip("Riporta posizione iniziale a (0, 0) e zoom 1.0×")
        btn_center.clicked.connect(self._reset_transform)

        grid.addWidget(QLabel("Movimento:"), 0, 0)
        grid.addWidget(self.cmb_motion, 0, 1)
        grid.addWidget(QLabel("Zoom:"), 0, 2)
        grid.addWidget(self.spin_zoom, 0, 3)

        grid.addWidget(QLabel("Pos. X:"), 1, 0)
        grid.addWidget(self.spin_x, 1, 1)
        grid.addWidget(QLabel("Pos. Y:"), 1, 2)
        grid.addWidget(self.spin_y, 1, 3)
        grid.addWidget(btn_center, 1, 4)
        root.addLayout(grid)

        # Footer: apply to all scenes + propagate to all chapters
        foot = QHBoxLayout()
        self.chk_apply_scenes = QCheckBox("Applica a tutte le scene del capitolo")
        self.chk_apply_scenes.setChecked(True)
        btn_copy_all = QPushButton("✨ Copia su tutti i capitoli")
        btn_copy_all.setToolTip("Applica questa immagine e posizione a tutti i capitoli del libro")
        btn_copy_all.clicked.connect(lambda: self.applyToAllRequested.emit(self))
        foot.addWidget(self.chk_apply_scenes, 1)
        foot.addWidget(btn_copy_all)
        root.addLayout(foot)

        self._sync_ui()

    def _sync_ui(self) -> None:
        self._updating = True
        try:
            self.lbl_file.setText(
                Path(self._media_path).name if self._media_path else "Nessun file selezionato"
            )
            self.lbl_file.setToolTip(self._media_path or "")
            idx = self.cmb_library.findData(self._media_path)
            self.cmb_library.setCurrentIndex(idx if idx >= 0 else 0)
            self.cmb_motion.setCurrentText(self._ken_burns)
            self.spin_zoom.setValue(self._zoom)
            self.spin_x.setValue(self._x)
            self.spin_y.setValue(self._y)
            self.preview.set_state(self._media_path, self._zoom, self._x, self._y)
        finally:
            self._updating = False

    def _browse_media(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Scegli Media per {self.chapter.title}",
            str(self.workspace_dir),
            "Immagini e video (*.jpg *.jpeg *.png *.webp *.bmp *.mp4 *.mov *.avi *.mkv *.webm)",
        )
        if not path:
            return
        self._media_path = path
        self._sync_ui()

    def _clear_media(self) -> None:
        self._media_path = ""
        self._sync_ui()

    def _on_library_picked(self, index: int) -> None:
        if self._updating or index <= 0:
            return
        self._media_path = str(self.cmb_library.itemData(index) or "")
        self._sync_ui()

    def _on_preview_transform(self, zoom: float, x: float, y: float) -> None:
        self._zoom, self._x, self._y = zoom, x, y
        self._updating = True
        try:
            self.spin_zoom.setValue(zoom)
            self.spin_x.setValue(x)
            self.spin_y.setValue(y)
        finally:
            self._updating = False

    def _on_controls_changed(self) -> None:
        if self._updating:
            return
        self._ken_burns = self.cmb_motion.currentText()
        self._zoom = self.spin_zoom.value()
        self._x = self.spin_x.value()
        self._y = self.spin_y.value()
        self.preview.set_state(self._media_path, self._zoom, self._x, self._y)

    def _reset_transform(self) -> None:
        self._zoom = 1.0
        self._x = 0.0
        self._y = 0.0
        self._sync_ui()

    def copy_from(self, other: "ChapterMediaCard") -> None:
        self._media_path = other._media_path
        self._ken_burns = other._ken_burns
        self._zoom = other._zoom
        self._x = other._x
        self._y = other._y
        self._sync_ui()

    def apply_to_chapter(self) -> None:
        p = self._media_path
        if p:
            mtype = "video" if Path(p).suffix.lower() in VIDEO_EXTS else "image"
            self.chapter.default_media_path = p
            self.chapter.default_media_type = mtype  # type: ignore[assignment]
        else:
            self.chapter.default_media_path = ""
            self.chapter.default_media_type = "none"

        if self.chk_apply_scenes.isChecked():
            for sc in self.chapter.scenes:
                sc.use_chapter_media = True
                sc.ken_burns = self._ken_burns  # type: ignore[assignment]
                sc.image_zoom = self._zoom
                sc.image_x = self._x
                sc.image_y = self._y


class ChapterMediaStudioDialog(QDialog):
    """Modal grid of Chapter Media Cards for fast chapter-level visual setup."""

    def __init__(
        self,
        project: VideoBookProject,
        library_items: Sequence[tuple[str, str]],
        workspace_dir: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("🖼️ Studio Visuale Capitoli — Immagini e Posizione di Partenza")
        self.resize(1040, 740)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        intro = QLabel(
            "Assegna un'immagine o un video a ogni capitolo. Puoi trascinare l'anteprima 16:9 "
            "per scegliere l'inquadratura di partenza e usare la rotellina per lo zoom; "
            "al salvataggio del progetto i file verranno copiati automaticamente nella cartella del progetto."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #B9C4D8; font-size: 12px;")
        layout.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(14)

        self.cards: list[ChapterMediaCard] = []
        cols = 2
        for idx, ch in enumerate(project.chapters):
            card = ChapterMediaCard(idx, ch, library_items, workspace_dir, container)
            card.applyToAllRequested.connect(self._propagate_card_to_all)
            self.cards.append(card)
            grid.addWidget(card, idx // cols, idx % cols)

        grid.setRowStretch((len(project.chapters) + cols - 1) // cols, 1)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_cancel = QPushButton("Annulla")
        btn_cancel.clicked.connect(self.reject)
        btn_apply = QPushButton("✅ Applica a Capitoli e Scene")
        btn_apply.setObjectName("ExportBtn")
        btn_apply.clicked.connect(self._apply_and_accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_apply)
        layout.addLayout(btn_row)

    def _propagate_card_to_all(self, source_card: ChapterMediaCard) -> None:
        for card in self.cards:
            if card is not source_card:
                card.copy_from(source_card)

    def _apply_and_accept(self) -> None:
        for card in self.cards:
            card.apply_to_chapter()
        self.accept()
