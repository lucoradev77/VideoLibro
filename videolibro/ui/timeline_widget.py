"""Interactive multi-track visual timeline widget for VideoLibro Studio."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..i18n import tr
from ..models import TimelineEntry


class TimelineWidget(QWidget):
    """Custom-painted multi-track timeline (Chapters, Scenes/Text, Media, Audio)."""

    entrySelected = Signal(int, object)  # (chapter_index, scene_index_or_None)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entries: list[TimelineEntry] = []
        self._total_duration: float = 0.0
        self._px_per_sec: float = 28.0
        self._selected_key: tuple[int, int | None] | None = None
        self._hit_boxes: list[tuple[QRectF, TimelineEntry]] = []
        self._lang: str = "it"
        self.setMinimumHeight(195)
        self.setMouseTracking(True)

    def set_language(self, lang: str) -> None:
        self._lang = lang
        self.update()

    def set_timeline(self, entries: list[TimelineEntry], total_duration: float) -> None:
        self._entries = entries
        self._total_duration = max(10.0, total_duration)
        needed_w = max(860, int(self._total_duration * self._px_per_sec) + 180)
        self.setMinimumWidth(needed_w)
        self.update()

    def set_selected(self, chapter_idx: int, scene_idx: int | None) -> None:
        self._selected_key = (chapter_idx, scene_idx)
        self.update()

    def zoom_in(self) -> None:
        self._px_per_sec = min(90.0, self._px_per_sec * 1.25)
        self.set_timeline(self._entries, self._total_duration)

    def zoom_out(self) -> None:
        self._px_per_sec = max(8.0, self._px_per_sec / 1.25)
        self.set_timeline(self._entries, self._total_duration)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        label_w = 128

        # Background
        painter.fillRect(0, 0, w, h, QColor("#11141C"))

        # Track definitions
        tracks = [
            (tr(self._lang, "tl_track_chapters"), 28, 34, QColor("#171B26")),
            (tr(self._lang, "tl_track_scenes"), 66, 42, QColor("#141822")),
            (tr(self._lang, "tl_track_media"), 112, 34, QColor("#171B26")),
            (tr(self._lang, "tl_track_audio"), 150, 34, QColor("#141822")),
        ]

        # Draw track lanes & headers
        header_font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        painter.setFont(header_font)
        for name, y, th, bg in tracks:
            painter.fillRect(label_w, y, w - label_w, th, bg)
            painter.fillRect(0, y, label_w - 2, th, QColor("#1B202D"))
            painter.setPen(QColor("#9AA4B8"))
            painter.drawText(10, y, label_w - 16, th, Qt.AlignmentFlag.AlignVCenter, name)

        # Time ruler
        painter.fillRect(label_w, 0, w - label_w, 24, QColor("#1A1F2B"))
        painter.setPen(QPen(QColor("#2C3447"), 1))
        painter.drawLine(label_w, 24, w, 24)

        step_sec = 5 if self._px_per_sec >= 20 else 10
        ruler_font = QFont("Segoe UI", 8)
        painter.setFont(ruler_font)
        t = 0
        while t <= self._total_duration + step_sec:
            x = label_w + t * self._px_per_sec
            painter.setPen(QPen(QColor("#3A445C"), 1))
            painter.drawLine(int(x), 14, int(x), 24)
            painter.setPen(QColor("#7F8BA3"))
            mins, secs = divmod(int(t), 60)
            painter.drawText(int(x) + 3, 2, 48, 16, Qt.AlignmentFlag.AlignLeft, f"{mins:02d}:{secs:02d}")
            t += step_sec

        # Draw timeline blocks
        self._hit_boxes.clear()
        block_font = QFont("Segoe UI", 8)
        painter.setFont(block_font)

        for entry in self._entries:
            x = label_w + entry.start_sec * self._px_per_sec
            bw = max(6.0, entry.duration_sec * self._px_per_sec - 2.0)
            is_sel = self._selected_key == (entry.chapter_index, entry.scene_index)

            if entry.kind == "title_card":
                rect = QRectF(x, 31, bw, 28)
                fill = QColor("#D4A14E") if is_sel else QColor("#9C7434")
                border = QColor("#FFF3D1") if is_sel else QColor("#C69749")
                painter.setBrush(QBrush(fill))
                painter.setPen(QPen(border, 1.5 if is_sel else 1.0))
                painter.drawRoundedRect(rect, 4, 4)
                painter.setPen(QColor("#111318"))
                painter.drawText(rect.adjusted(6, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter, entry.label)
                self._hit_boxes.append((rect, entry))
            else:
                # Scene / Text track
                rect = QRectF(x, 69, bw, 36)
                fill = QColor("#3B6EB8") if is_sel else QColor("#284B7E")
                border = QColor("#9CC2FF") if is_sel else QColor("#3B69AB")
                painter.setBrush(QBrush(fill))
                painter.setPen(QPen(border, 1.8 if is_sel else 1.0))
                painter.drawRoundedRect(rect, 4, 4)
                painter.setPen(QColor("#F0F4FA"))
                if bw > 24:
                    painter.drawText(rect.adjusted(6, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter, entry.label)
                self._hit_boxes.append((rect, entry))

                # Media track
                m_rect = QRectF(x, 115, bw, 28)
                if entry.media_type == "video":
                    m_col = QColor("#7A459E")
                    m_lbl = "VIDEO"
                elif entry.media_type == "image":
                    m_col = QColor("#2E7D6B")
                    m_lbl = "IMG"
                else:
                    m_col = QColor("#252B3B")
                    m_lbl = "SFONDO"
                painter.setBrush(QBrush(m_col))
                painter.setPen(QPen(QColor("#3D465E"), 1))
                painter.drawRoundedRect(m_rect, 3, 3)
                if bw > 34:
                    painter.setPen(QColor("#E6ECF5"))
                    painter.drawText(m_rect.adjusted(5, 0, -3, 0), Qt.AlignmentFlag.AlignVCenter, m_lbl)
                self._hit_boxes.append((m_rect, entry))

                # Audio track (TTS + BGM volume indicator)
                a_rect = QRectF(x, 153, bw, 28)
                a_col = QColor("#2D6A4F") if entry.has_tts else QColor("#2D3548")
                painter.setBrush(QBrush(a_col))
                painter.setPen(QPen(QColor("#3D465E"), 1))
                painter.drawRoundedRect(a_rect, 3, 3)
                if entry.bg_audio_path:
                    vol_h = max(3.0, 22.0 * min(1.0, entry.bg_audio_volume))
                    painter.fillRect(
                        QRectF(x + 2, 153 + 26 - vol_h, max(2.0, bw - 4), vol_h),
                        QColor(224, 180, 106, 95),
                    )
                if bw > 36:
                    painter.setPen(QColor("#DCE6F2"))
                    tts_txt = "TTS ✓" if entry.has_tts else "TTS auto"
                    painter.drawText(a_rect.adjusted(5, 0, -3, 0), Qt.AlignmentFlag.AlignVCenter, tts_txt)
                self._hit_boxes.append((a_rect, entry))

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.position()
        for rect, entry in self._hit_boxes:
            if rect.contains(pos):
                self._selected_key = (entry.chapter_index, entry.scene_index)
                self.update()
                self.entrySelected.emit(entry.chapter_index, entry.scene_index)
                return
        super().mousePressEvent(event)
