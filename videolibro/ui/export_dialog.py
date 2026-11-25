"""Centered modal export progress dialog with ETA, file size estimate, minimize, and cancel."""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)


def _fmt_duration(seconds: float) -> str:
    s = max(0, int(round(seconds)))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h > 0:
        return f"{h}h {m:02d}m {sec:02d}s"
    return f"{m:02d}m {sec:02d}s"


def _fmt_mb(num_bytes: int) -> str:
    mb = num_bytes / (1024 * 1024)
    return f"{mb:.1f} MB"


class ExportProgressDialog(QDialog):
    """Modal progress window that blocks editing, supports taskbar minimize, ETA, size, and cancel."""

    cancelRequested = Signal()

    def __init__(self, parent=None, lang: str = "it", total_duration_sec: float = 0.0) -> None:
        super().__init__(parent)
        self._lang = lang
        self._total_duration_sec = max(1.0, total_duration_sec)
        self._start_ts = time.monotonic()
        self._last_pct = 0
        self._current_bytes = 0
        self.cancel_event = threading.Event()

        # Modal + minimizable window flags
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setFixedSize(500, 240)

        is_en = lang == "en"
        self.setWindowTitle("Exporting VideoBook MP4..." if is_en else "Esportazione VideoLibro MP4...")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)

        self.lbl_title = QLabel(
            "🎬 Rendering VideoBook for TV..." if is_en else "🎬 Creazione VideoLibro per TV in corso..."
        )
        self.lbl_title.setStyleSheet("font-size: 12pt; font-weight: bold; color: #E0B46A;")
        lay.addWidget(self.lbl_title)

        self.lbl_step = QLabel("Preparing..." if is_en else "Preparazione...")
        self.lbl_step.setWordWrap(True)
        lay.addWidget(self.lbl_step)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(22)
        lay.addWidget(self.progress_bar)

        self.lbl_eta = QLabel(
            "Elapsed: 00m 00s  •  Remaining (ETA): calculating..."
            if is_en
            else "Trascorso: 00m 00s  •  Tempo residuo stimato: calcolo..."
        )
        self.lbl_eta.setStyleSheet("color: #9AA7BE; font-size: 9.5pt;")
        lay.addWidget(self.lbl_eta)

        # Rough initial size estimate (~0.35 MB/sec for 1080p still/ken-burns H.264)
        rough_est_mb = max(1.0, self._total_duration_sec * 0.35)
        self.lbl_size = QLabel(
            f"Rendered: 0.0 MB  •  Estimated final size: ~{rough_est_mb:.0f} MB"
            if is_en
            else f"Generati: 0.0 MB  •  Dimensione finale stimata: ~{rough_est_mb:.0f} MB"
        )
        self.lbl_size.setStyleSheet("color: #9AA7BE; font-size: 9.5pt;")
        lay.addWidget(self.lbl_size)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_cancel = QPushButton("Cancel" if is_en else "Annulla")
        self.btn_cancel.setMinimumWidth(110)
        self.btn_cancel.clicked.connect(self._on_cancel)
        btn_row.addWidget(self.btn_cancel)
        lay.addLayout(btn_row)

    def update_progress(self, pct: int, msg: str) -> None:
        self._last_pct = max(0, min(100, pct))
        self.progress_bar.setValue(self._last_pct)
        self.lbl_step.setText(msg)

        elapsed = time.monotonic() - self._start_ts
        is_en = self._lang == "en"
        if self._last_pct >= 5:
            eta_sec = elapsed * (100 - self._last_pct) / self._last_pct
            eta_str = f"~{_fmt_duration(eta_sec)}"
        else:
            eta_str = "calculating..." if is_en else "calcolo..."

        if is_en:
            self.lbl_eta.setText(f"Elapsed: {_fmt_duration(elapsed)}  •  Remaining (ETA): {eta_str}")
        else:
            self.lbl_eta.setText(f"Trascorso: {_fmt_duration(elapsed)}  •  Tempo residuo stimato: {eta_str}")

    def update_size(self, current_bytes: int) -> None:
        self._current_bytes = current_bytes
        is_en = self._lang == "en"
        cur_str = _fmt_mb(current_bytes)
        if self._last_pct > 32:
            # Rendering phase runs from 30% to 90%
            render_frac = max(0.05, min(1.0, (self._last_pct - 30) / 60.0))
            est_total = int(current_bytes / render_frac)
            est_str = f"~{_fmt_mb(est_total)}"
        else:
            est_str = f"~{max(1.0, self._total_duration_sec * 0.35):.0f} MB"

        if is_en:
            self.lbl_size.setText(f"Rendered: {cur_str}  •  Estimated final size: {est_str}")
        else:
            self.lbl_size.setText(f"Generati: {cur_str}  •  Dimensione finale stimata: {est_str}")

    def _on_cancel(self) -> None:
        self.cancel_event.set()
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setText("Cancelling..." if self._lang == "en" else "Annullamento...")
        self.cancelRequested.emit()

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self.cancel_event.is_set() and self._last_pct < 100:
            self._on_cancel()
            event.ignore()
            return
        super().closeEvent(event)
