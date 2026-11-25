"""Centered modal export progress dialog with ETA, file size estimate, minimize, and cancel."""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QComboBox,
    QFormLayout,
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


class ExportOptionsDialog(QDialog):
    """Choose the output container and a quality/speed profile before export."""

    def __init__(self, parent=None, lang: str = "it", duration_sec: float = 0.0) -> None:
        super().__init__(parent)
        self._lang = lang
        self._duration_sec = max(1.0, duration_sec)
        is_en = lang == "en"
        self.setWindowTitle("Export options" if is_en else "Opzioni di esportazione")
        self.setModal(True)
        self.setMinimumWidth(470)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Choose the file type and encoding speed. Estimates depend on your computer."
            if is_en else "Scegli il tipo di file e la velocità di codifica. Le stime dipendono dal computer."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self.cmb_format = QComboBox()
        self.cmb_format.addItem("MP4 — H.264/AAC (consigliato)" if not is_en else "MP4 — H.264/AAC (recommended)", "mp4")
        self.cmb_format.addItem("MKV — H.264/AAC", "mkv")
        form.addRow("Formato:" if not is_en else "Format:", self.cmb_format)
        self.cmb_speed = QComboBox()
        self.cmb_speed.addItem("Standard — balanced quality" if is_en else "Standard — qualità bilanciata", "standard")
        self.cmb_speed.addItem("Fast — quicker encoding" if is_en else "Rapido — codifica più veloce", "quick")
        form.addRow("Profilo:" if not is_en else "Profile:", self.cmb_speed)
        layout.addLayout(form)

        self.lbl_details = QLabel()
        self.lbl_details.setWordWrap(True)
        self.lbl_details.setStyleSheet("color: #9AA7BE;")
        layout.addWidget(self.lbl_details)
        self.cmb_format.currentIndexChanged.connect(self._update_details)
        self.cmb_speed.currentIndexChanged.connect(self._update_details)
        self._update_details()

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.btn_cancel = QPushButton("Annulla" if not is_en else "Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        buttons.addWidget(self.btn_cancel)
        self.btn_start = QPushButton("Continua" if not is_en else "Continue")
        self.btn_start.clicked.connect(self.accept)
        buttons.addWidget(self.btn_start)
        layout.addLayout(buttons)
        if self.parentWidget():
            self.move(self.parentWidget().frameGeometry().center() - self.rect().center())

    @property
    def output_format(self) -> str:
        return str(self.cmb_format.currentData())

    @property
    def speed_mode(self) -> str:
        return str(self.cmb_speed.currentData())

    def _update_details(self) -> None:
        is_en = self._lang == "en"
        mult = 0.40 if self.speed_mode == "quick" else 0.35
        size_mb = max(1.0, self._duration_sec * mult)
        low, high = ((0.4, 2.0) if self.speed_mode == "quick" else (0.8, 3.0))
        run_min = self._duration_sec / 60
        estimate = f"~{max(1, int(run_min * low))}–{max(2, int(run_min * high))} min" if is_en else f"~{max(1, int(run_min * low))}–{max(2, int(run_min * high))} min"
        if self.speed_mode == "quick":
            profile_note = "Faster encoding; the file may be larger and image quality slightly lower." if is_en else "Codifica più rapida; il file può essere più grande e la qualità leggermente inferiore."
        else:
            profile_note = "Balanced quality and file size." if is_en else "Equilibrio tra qualità e dimensione del file."
        format_note = (
            "MKV uses the same video and audio codecs as MP4; the container alone does not speed up encoding."
            if is_en else "MKV usa gli stessi codec video e audio di MP4: il solo contenitore non accelera la codifica."
        ) if self.output_format == "mkv" else ""
        text = f"{profile_note}\n{('Estimated size' if is_en else 'Dimensione indicativa')}: ~{size_mb:.0f} MB  •  {('initial time range' if is_en else 'tempo iniziale indicativo')}: {estimate}."
        if format_note:
            text += f"\n{format_note}"
        self.lbl_details.setText(text)


class TaskProgressDialog(QDialog):
    """Progress and stop-after-current-item dialog for background tasks."""

    cancelRequested = Signal()

    def __init__(self, parent=None, lang: str = "it", title: str = "", description: str = "") -> None:
        super().__init__(parent)
        self._lang = lang
        self._start_ts = time.monotonic()
        self._last_pct = 0
        self.cancel_event = threading.Event()
        is_en = lang == "en"
        self.setWindowTitle(title or ("Working…" if is_en else "Elaborazione in corso…"))
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setFixedSize(470, 190)
        layout = QVBoxLayout(self)
        self.lbl_title = QLabel(title or ("Working…" if is_en else "Elaborazione in corso…"))
        self.lbl_title.setStyleSheet("font-size: 12pt; font-weight: bold; color: #E0B46A;")
        layout.addWidget(self.lbl_title)
        self.lbl_step = QLabel(description or ("Preparing…" if is_en else "Preparazione…"))
        self.lbl_step.setWordWrap(True)
        layout.addWidget(self.lbl_step)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)
        self.lbl_eta = QLabel("Tempo trascorso: 0 s • Tempo residuo stimato: calcolo…" if not is_en else "Elapsed: 0 s • Remaining estimate: calculating…")
        self.lbl_eta.setStyleSheet("color: #9AA7BE;")
        layout.addWidget(self.lbl_eta)
        row = QHBoxLayout()
        row.addStretch()
        self.btn_cancel = QPushButton("Ferma dopo l'elemento corrente" if not is_en else "Stop after current item")
        self.btn_cancel.clicked.connect(self._on_cancel)
        row.addWidget(self.btn_cancel)
        layout.addLayout(row)
        if self.parentWidget():
            self.move(self.parentWidget().frameGeometry().center() - self.rect().center())

    def update_progress(self, pct: int, message: str) -> None:
        self._last_pct = max(0, min(100, pct))
        self.progress_bar.setValue(self._last_pct)
        self.lbl_step.setText(message)
        elapsed = time.monotonic() - self._start_ts
        if self._last_pct > 0:
            remaining = elapsed * (100 - self._last_pct) / self._last_pct
            eta = _fmt_duration(remaining)
        else:
            eta = "calcolo…" if self._lang != "en" else "calculating…"
        if self._lang == "en":
            self.lbl_eta.setText(f"Elapsed: {_fmt_duration(elapsed)} • Remaining estimate: {eta}")
        else:
            self.lbl_eta.setText(f"Trascorso: {_fmt_duration(elapsed)} • Residuo stimato: {eta}")

    def _on_cancel(self) -> None:
        self.cancel_event.set()
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setText("Annullamento…" if self._lang != "en" else "Stopping…")
        self.cancelRequested.emit()

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self.cancel_event.is_set() and self._last_pct < 100:
            self._on_cancel()
            event.ignore()
        else:
            super().closeEvent(event)


class ExportProgressDialog(QDialog):
    """Modal progress window that blocks editing, supports taskbar minimize, ETA, size, and cancel."""

    cancelRequested = Signal()

    def __init__(self, parent=None, lang: str = "it", total_duration_sec: float = 0.0, speed_mode: str = "standard") -> None:
        super().__init__(parent)
        self._lang = lang
        self._speed_mode = speed_mode
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
        self.setWindowTitle("Exporting VideoBook..." if is_en else "Esportazione VideoLibro...")

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
        rough_est_mb = max(1.0, self._total_duration_sec * (0.40 if speed_mode == "quick" else 0.35))
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
        if self.parentWidget():
            self.move(self.parentWidget().frameGeometry().center() - self.rect().center())

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
            factor = 0.40 if self._speed_mode == "quick" else 0.35
            est_str = f"~{max(1.0, self._total_duration_sec * factor):.0f} MB"

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
