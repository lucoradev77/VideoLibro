"""Main Studio Window for VideoLibro Studio."""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
import threading
import uuid
from pathlib import Path

from PIL.ImageQt import ImageQt
from PySide6.QtCore import QEvent, QSettings, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QInputDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QStyle,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..i18n import tr
from .. import __version__
from ..importer import import_manuscript_file, split_text_into_scenes
from ..models import Chapter, SceneBlock, VideoBookProject
from ..renderer import ExportCancelledError, export_project_to_mp4, render_preview_frame
from ..sample_generator import build_demo_project
from ..tts_engine import ITALIAN_VOICES, synthesize_scene_tts
from .export_dialog import ExportOptionsDialog, ExportProgressDialog, TaskProgressDialog
from .timeline_widget import TimelineWidget

BUILTIN_BACKGROUNDS = [
    ("Biblioteca Antica (Calda)", "biblioteca_antica.jpg"),
    ("Torre della Luna (Notte)", "torre_luna.jpg"),
    ("Mare Stellato (Orizzonte)", "mare_stellato.jpg"),
    ("Foresta d'Oro (Bosco)", "foresta_oro.jpg"),
]


class ExtendMediaDialog(QDialog):
    """Choose how far a scene's media should be propagated."""

    def __init__(self, parent, remaining_scenes: int, lang: str = "it") -> None:
        super().__init__(parent)
        is_en = lang == "en"
        self.setWindowTitle("Extend media" if is_en else "Estendi media")
        self.setModal(True)
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Choose which scenes should use the selected image or video."
            if is_en else "Scegli quali scene devono usare l'immagine o il video selezionato."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self.cmb_scope = QComboBox()
        self.cmb_scope.addItem("Tutte le scene del libro" if not is_en else "All scenes in the book", "book")
        if remaining_scenes > 0:
            self.cmb_scope.addItem("Solo la prossima scena" if not is_en else "Next scene only", "next")
            self.cmb_scope.addItem("Un numero di scene successive…" if not is_en else "A number of following scenes…", "count")
        self.cmb_scope.addItem("Tutte le scene di questo capitolo" if not is_en else "All scenes in this chapter", "chapter")
        self.cmb_scope.setCurrentIndex(self.cmb_scope.findData("chapter"))
        form.addRow("Estensione:" if not is_en else "Apply to:", self.cmb_scope)
        self.spin_count = QSpinBox()
        self.spin_count.setRange(1, max(1, remaining_scenes))
        self.spin_count.setValue(min(3, max(1, remaining_scenes)))
        form.addRow("Numero di scene successive:" if not is_en else "Number of following scenes:", self.spin_count)
        layout.addLayout(form)
        self.cmb_scope.currentIndexChanged.connect(self._update_count_enabled)
        self._update_count_enabled()

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Annulla" if not is_en else "Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        apply = QPushButton("Applica" if not is_en else "Apply")
        apply.clicked.connect(self.accept)
        buttons.addWidget(apply)
        layout.addLayout(buttons)

    @property
    def scope(self) -> str:
        return str(self.cmb_scope.currentData())

    def _update_count_enabled(self) -> None:
        enabled = self.scope == "count"
        self.spin_count.setEnabled(enabled)


class ExportWorker(QThread):
    progress = Signal(int, str)
    size_updated = Signal(int)
    finished_ok = Signal(str)
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, project: VideoBookProject, output_path: str, cancel_event: threading.Event,
                 output_format: str = "mp4", speed_mode: str = "standard") -> None:
        super().__init__()
        self.project = project
        self.output_path = output_path
        self.cancel_event = cancel_event
        self.output_format = output_format
        self.speed_mode = speed_mode

    def run(self) -> None:
        try:
            out = export_project_to_mp4(
                self.project,
                self.output_path,
                generate_missing_tts=True,
                progress_cb=lambda p, m: self.progress.emit(p, m),
                size_cb=lambda b: self.size_updated.emit(b),
                cancel_event=self.cancel_event,
                output_format=self.output_format,
                speed_mode=self.speed_mode,
            )
            self.finished_ok.emit(str(out))
        except ExportCancelledError:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class TTSBatchWorker(QThread):
    progress = Signal(int, str)
    finished_ok = Signal()
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, project: VideoBookProject, cache_dir: Path, cancel_event: threading.Event | None = None) -> None:
        super().__init__()
        self.project = project
        self.cache_dir = cache_dir
        self.cancel_event = cancel_event or threading.Event()

    def run(self) -> None:
        try:
            total = sum(len(c.scenes) for c in self.project.chapters)
            done = 0
            for ch in self.project.chapters:
                for sc in ch.scenes:
                    if self.cancel_event.is_set():
                        self.cancelled.emit()
                        return
                    done += 1
                    self.progress.emit(int(100 * done / max(1, total)), f"Generazione TTS {done}/{total}...")
                    ap, dur, timings = synthesize_scene_tts(
                        sc.text,
                        self.cache_dir,
                        sc.id,
                        voice=self.project.settings.tts_voice,
                        rate=self.project.settings.tts_rate,
                        engine=self.project.settings.tts_engine,
                    )
                    sc.tts_audio_path = ap
                    sc.tts_duration_sec = dur
                    sc.word_timings = timings
            if self.cancel_event.is_set():
                self.cancelled.emit()
                return
            self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class TTSPrepareWorker(QThread):
    progress = Signal(int, str)
    scene_ready = Signal(str, str, float, object)
    finished_ok = Signal()
    failed = Signal(str)

    def __init__(self, jobs: list[tuple[str, str, str, str, str]], cache_dir: Path) -> None:
        super().__init__()
        self.jobs = jobs
        self.cache_dir = cache_dir

    def run(self) -> None:
        try:
            total = len(self.jobs)
            for index, (text, scene_id, voice, rate, engine) in enumerate(self.jobs, 1):
                self.progress.emit(int((index - 1) * 100 / max(1, total)), f"Generazione TTS {index}/{total}…")
                path, duration, timings = synthesize_scene_tts(
                    text, self.cache_dir, scene_id, voice=voice, rate=rate, engine=engine
                )
                self.scene_ready.emit(scene_id, path, duration, timings)
                self.progress.emit(int(index * 100 / max(1, total)), f"TTS pronto {index}/{total}")
            self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    """Main IDE-like Studio window for creating MP4 VideoBooks."""

    def __init__(self, workspace_dir: Path) -> None:
        super().__init__()
        self.workspace_dir = workspace_dir
        self.media_library_dir = workspace_dir / "media_library"
        self.tts_cache_dir = Path(tempfile.gettempdir()) / "videolibro_tts_cache"
        self.tts_cache_dir.mkdir(parents=True, exist_ok=True)

        self.project = VideoBookProject()
        self._settings_store = QSettings("VideoLibroStudio", "App")
        self._lang: str = str(self._settings_store.value("ui_language", "it"))
        self._sel_chapter: int = 0
        self._sel_scene: int | None = None
        self._multi_select_mode = False
        self._updating_ui: bool = False
        self._worker: QThread | None = None
        self._preview_tts_worker: TTSPrepareWorker | None = None
        self._preview_tts_workers: list[TTSPrepareWorker] = []
        self._preview_tts_dialog: TaskProgressDialog | None = None
        self._preview_tts_remaining_jobs: list[tuple[str, str, str, str, str]] = []
        self._latest_release_tag: str | None = None
        self._update_manager = QNetworkAccessManager(self)
        self._update_manager.finished.connect(self._on_update_check_finished)

        self._audio_out = QAudioOutput(self)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio_out)
        self._player.positionChanged.connect(lambda _pos: self._refresh_preview_motion())

        self._bgm_out = QAudioOutput(self)
        self._bgm_player = QMediaPlayer(self)
        self._bgm_player.setAudioOutput(self._bgm_out)

        self._test_timer = QTimer(self)
        self._test_timer.setSingleShot(True)
        self._test_timer.timeout.connect(self._advance_full_preview)
        self._preview_motion_timer = QTimer(self)
        self._preview_motion_timer.setInterval(120)
        self._preview_motion_timer.timeout.connect(self._refresh_preview_motion)
        self._karaoke_timer = QTimer(self)
        self._karaoke_timer.setInterval(50)
        self._karaoke_timer.timeout.connect(self._refresh_preview_motion)
        self._test_entries: list = []
        self._test_index: int = 0
        self._is_testing: bool = False
        self._test_paused: bool = False
        self._is_listening_scene: bool = False
        self._paused_entry_elapsed: float = 0.0
        self._paused_remaining_ms: int = 0
        self._preview_fullscreen_window = None
        self._fullscreen_preview_label = None

        self.setWindowTitle("VideoLibro Studio — Manoscritti in Cinema per TV")
        self.resize(1420, 900)
        self._apply_dark_theme()
        self._build_toolbar()
        self._build_layout()
        self._layout_screen_signature = self._current_screen_signature()
        self.top_splitter.splitterMoved.connect(lambda _pos, _index: self._save_layout_settings())
        self.main_splitter.splitterMoved.connect(lambda _pos, _index: self._save_layout_settings())
        # Restore after the initial maximized geometry has settled; otherwise
        # Qt scales the splitter sizes from the constructor's temporary size.
        QTimer.singleShot(250, self._restore_layout_settings)
        QTimer.singleShot(0, self._connect_screen_signals)
        QTimer.singleShot(5000, self.check_for_updates)
        self._retranslate_ui()

        # Load demo project on first launch so user sees something rich immediately
        self.load_demo_project()

    def _apply_dark_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background-color: #151922;
                color: #E8ECF4;
                font-family: 'Segoe UI';
                font-size: 10pt;
            }
            QToolBar {
                background-color: #1C212E;
                border-bottom: 1px solid #2A3244;
                spacing: 8px;
                padding: 6px;
            }
            QLabel#QuickStyleLabel, QComboBox#QuickStyleCombo {
                background-color: #252C3D;
                border: 1px solid #353F57;
                border-radius: 6px;
                padding: 6px 10px;
                color: #E8ECF4;
            }
            QPushButton {
                background-color: #252C3D;
                border: 1px solid #353F57;
                border-radius: 6px;
                padding: 6px 12px;
                color: #E8ECF4;
            }
            QPushButton:hover { background-color: #2F384E; }
            QPushButton#ExportBtn {
                background-color: #C9943B;
                color: #11141C;
                font-weight: bold;
                border: 1px solid #E5B460;
            }
            QPushButton#ExportBtn:hover { background-color: #DDA74D; }
            QTreeWidget, QTextEdit, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                background-color: #10131B;
                border: 1px solid #2C3447;
                border-radius: 5px;
                padding: 4px 6px;
                color: #E8ECF4;
            }
            QTreeWidget::indicator {
                width: 14px;
                height: 14px;
                background-color: #FFFFFF;
                border: 1px solid #AEB8CC;
                border-radius: 3px;
            }
            QTreeWidget::indicator:checked {
                background-color: #E0B46A;
                border: 1px solid #D83B3B;
            }
            QTreeWidget::indicator:checked:hover { background-color: #F0C875; }
            QGroupBox {
                border: 1px solid #2A3244;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
                font-weight: bold;
                color: #E0B46A;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QTabWidget::pane { border: 1px solid #2A3244; border-radius: 6px; }
            QTabBar::tab {
                background: #1C212E;
                padding: 7px 14px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                margin-right: 2px;
            }
            QTabBar::tab:selected { background: #2A3347; color: #E0B46A; font-weight: bold; }
            QProgressBar {
                background: #10131B;
                border: 1px solid #2C3447;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk { background-color: #C9943B; border-radius: 4px; }
            """
        )

    def _current_screen_signature(self, screen=None) -> str:
        screen = screen or self.screen() or QApplication.primaryScreen()
        if screen is None:
            return "unknown"
        geometry = screen.geometry()
        return (
            f"{screen.name()}:{geometry.width()}x{geometry.height()}"
            f"@{screen.devicePixelRatio():.2f}:{screen.logicalDotsPerInch():.1f}dpi"
        )

    @staticmethod
    def _stored_splitter_sizes(value, expected: int) -> list[int] | None:
        if isinstance(value, str):
            value = value.split(",")
        if not isinstance(value, (list, tuple)) or len(value) != expected:
            return None
        try:
            sizes = [int(part) for part in value]
        except (TypeError, ValueError):
            return None
        return sizes if all(size > 0 for size in sizes) else None

    def _restore_layout_settings(self) -> None:
        top_sizes = self._stored_splitter_sizes(self._settings_store.value("layout/top_splitter_sizes", []), 3)
        main_sizes = self._stored_splitter_sizes(self._settings_store.value("layout/main_splitter_sizes", []), 2)
        if top_sizes:
            self.top_splitter.setSizes(top_sizes)
        if main_sizes:
            self.main_splitter.setSizes(main_sizes)

    def _save_layout_settings(self) -> None:
        self._layout_screen_signature = self._current_screen_signature()
        self._settings_store.setValue("layout/screen_signature", self._layout_screen_signature)
        self._settings_store.setValue("layout/top_splitter_sizes", self.top_splitter.sizes())
        self._settings_store.setValue("layout/main_splitter_sizes", self.main_splitter.sizes())

    def _connect_screen_signals(self) -> None:
        handle = self.windowHandle()
        if handle:
            handle.screenChanged.connect(self._on_screen_changed)
        self._watch_screen(self.screen() or QApplication.primaryScreen())

    def _watch_screen(self, screen) -> None:
        if screen is None:
            return
        if getattr(self, "_watched_screen", None) is screen:
            return
        self._watched_screen = screen
        screen.geometryChanged.connect(self._on_screen_metrics_changed)
        screen.logicalDotsPerInchChanged.connect(self._on_screen_metrics_changed)

    def _on_screen_changed(self, screen) -> None:
        self._watch_screen(screen)
        self._reset_layout_if_screen_changed(screen)

    def _on_screen_metrics_changed(self, *_args) -> None:
        self._reset_layout_if_screen_changed()

    def _reset_layout_if_screen_changed(self, screen=None) -> None:
        signature = self._current_screen_signature(screen)
        if signature == self._layout_screen_signature:
            return
        self._layout_screen_signature = signature
        self.top_splitter.setSizes([280, 700, 400])
        self.main_splitter.setSizes([560, 260])
        self._save_layout_settings()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._save_layout_settings()
        super().closeEvent(event)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Principale")
        tb.setMovable(False)
        self.addToolBar(tb)

        self.btn_import = QPushButton("📄 Importa Manoscritto (.docx / .txt)")
        self.btn_import.clicked.connect(self.import_manuscript_dialog)
        tb.addWidget(self.btn_import)

        self.btn_demo = QPushButton("✨ Carica Demo")
        self.btn_demo.clicked.connect(self.load_demo_project)
        tb.addWidget(self.btn_demo)

        self.btn_open = QPushButton("📂 Apri (.vlibro)")
        self.btn_open.clicked.connect(self.open_project_dialog)
        tb.addWidget(self.btn_open)

        self.btn_save = QPushButton("💾 Salva")
        self.btn_save.clicked.connect(self.save_project_dialog)
        tb.addWidget(self.btn_save)

        self.btn_media_library = QPushButton("📚 Libreria Media")
        self.btn_media_library.clicked.connect(self.import_to_media_library)
        tb.addWidget(self.btn_media_library)

        tb.addSeparator()

        self.btn_tts_all = QPushButton("🎙️ Genera Voci TTS")
        self.btn_tts_all.clicked.connect(self.generate_all_tts)
        tb.addWidget(self.btn_tts_all)

        self.btn_export = QPushButton("🎬 Esporta VideoLibro MP4 (TV)")
        self.btn_export.setObjectName("ExportBtn")
        self.btn_export.clicked.connect(self.export_mp4_dialog)
        tb.addWidget(self.btn_export)

        tb.addSeparator()

        self.btn_help = QPushButton("❓ Guida")
        self.btn_help.clicked.connect(self.show_help_dialog)
        tb.addWidget(self.btn_help)

        self.cmb_lang = QComboBox()
        self.cmb_lang.addItem("🌐 Italiano", "it")
        self.cmb_lang.addItem("🌐 English", "en")
        l_idx = self.cmb_lang.findData(self._lang)
        if l_idx >= 0:
            self.cmb_lang.setCurrentIndex(l_idx)
        self.cmb_lang.currentIndexChanged.connect(self._on_language_changed)
        tb.addWidget(self.cmb_lang)
        self.lbl_quick_style = QLabel("🎨 Stile TV")
        self.lbl_quick_style.setObjectName("QuickStyleLabel")
        tb.addWidget(self.lbl_quick_style)
        self.cmb_quick_style = QComboBox()
        self.cmb_quick_style.setObjectName("QuickStyleCombo")
        self.cmb_quick_style.addItems(
            ["Libro Cinematografico", "Sottotitoli Cinema", "Pagina Antica", "Minimal Elegante", "Notturno Blu"]
        )
        self.cmb_quick_style.setMinimumWidth(190)
        self.cmb_quick_style.setToolTip("Stile visivo sulla TV")
        self.cmb_quick_style.currentTextChanged.connect(self._on_quick_style_changed)
        tb.addWidget(self.cmb_quick_style)
        self.btn_fullscreen = QPushButton()
        self.btn_fullscreen.clicked.connect(self.toggle_fullscreen)
        tb.addWidget(self.btn_fullscreen)
        self.btn_update = QPushButton()
        self.btn_update.setObjectName("UpdateAvailableBtn")
        self.btn_update.setVisible(False)
        self.btn_update.clicked.connect(self.open_latest_release)
        tb.addWidget(self.btn_update)

    def check_for_updates(self) -> None:
        request = QNetworkRequest(QUrl("https://api.github.com/repos/lucoradev77/VideoLibro/releases/latest"))
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setRawHeader(b"User-Agent", b"VideoLibroStudio")
        request.setTransferTimeout(10000)
        self._update_manager.get(request)

    def _on_update_check_finished(self, reply) -> None:
        try:
            if reply.error():
                if hasattr(self, "lbl_status"):
                    self.lbl_status.setText(
                        f"Controllo aggiornamenti non riuscito: {reply.errorString()}"
                    )
                return
            import json

            payload = json.loads(bytes(reply.readAll()).decode("utf-8"))
            latest_tag = str(payload.get("tag_name", ""))
            latest_version = self._parse_version(latest_tag)
            current_version = self._parse_version(__version__)
            if latest_version is None or current_version is None:
                return
            # Previous public builds reported 1.0.0 internally despite using v0.1.x tags.
            if __version__ == "1.0.0":
                current_version = (0, 0, 0)
            if latest_version > current_version:
                self._latest_release_tag = latest_tag
                self._update_update_button()
                if hasattr(self, "lbl_status"):
                    self.lbl_status.setText(f"Aggiornamento {latest_tag} disponibile.")
            elif hasattr(self, "lbl_status"):
                self.lbl_status.setText(f"VideoLibro è aggiornato ({__version__}).")
        except (ValueError, TypeError, AttributeError):
            if hasattr(self, "lbl_status"):
                self.lbl_status.setText("Risposta GitHub non valida durante il controllo aggiornamenti.")
        finally:
            reply.deleteLater()

    @staticmethod
    def _parse_version(version: str) -> tuple[int, int, int] | None:
        match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", version.strip())
        return tuple(map(int, match.groups())) if match else None

    def _update_update_button(self) -> None:
        if not hasattr(self, "btn_update") or not self._latest_release_tag:
            return
        self.btn_update.setText(
            tr(self._lang, "update_available", version=self._latest_release_tag)
        )
        self.btn_update.setToolTip(tr(self._lang, "update_tooltip"))
        self.btn_update.setVisible(True)

    def open_latest_release(self) -> None:
        if self._latest_release_tag:
            QDesktopServices.openUrl(
                QUrl(f"https://github.com/lucoradev77/VideoLibro/releases/tag/{self._latest_release_tag}")
            )

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showMaximized()
        else:
            self.showFullScreen()
        self._update_fullscreen_button()

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "btn_fullscreen"):
            self._update_fullscreen_button()

    def _update_fullscreen_button(self) -> None:
        if hasattr(self, "btn_fullscreen"):
            self.btn_fullscreen.setText(
                ("⤢ Schermo normale" if self.isFullScreen() else "⛶ Schermo intero")
                if self._lang == "it"
                else ("⤢ Normal screen" if self.isFullScreen() else "⛶ Full screen")
            )


    def _build_layout(self) -> None:
        central = QWidget()
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(6)

        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.top_splitter = QSplitter(Qt.Orientation.Horizontal)

        # LEFT: Chapters & Scenes tree
        left_panel = QWidget()
        left_lay = QVBoxLayout(left_panel)
        left_lay.setContentsMargins(0, 0, 0, 0)
        self.lbl_left_hdr = QLabel("📚 Capitoli e Scene del Manoscritto")
        left_lay.addWidget(self.lbl_left_hdr)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemSelectionChanged.connect(self._on_tree_selection)
        left_lay.addWidget(self.tree)

        ch_btns = QHBoxLayout()
        ch_btns.setContentsMargins(0, 5, 0, 0)
        self.b_add_ch = QPushButton()
        self.b_add_ch.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder))
        self.b_add_ch.setFixedWidth(38)
        self.b_add_ch.clicked.connect(self.add_chapter)
        self.b_add_sc = QPushButton()
        self.b_add_sc.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
        self.b_add_sc.setFixedWidth(38)
        self.b_add_sc.clicked.connect(self.add_scene)
        self.b_del = QPushButton()
        self.b_del.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        self.b_del.setFixedWidth(38)
        self.b_del.clicked.connect(self.delete_selected)
        self.b_up = QPushButton("↑")
        self.b_up.setFixedWidth(34)
        self.b_up.setToolTip("Sposta in alto")
        self.b_up.clicked.connect(self.move_selected_up)
        self.b_down = QPushButton("↓")
        self.b_down.setFixedWidth(34)
        self.b_down.setToolTip("Sposta in basso")
        self.b_down.clicked.connect(self.move_selected_down)
        self.b_merge = QPushButton()
        self.b_merge.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
        self.b_merge.setFixedWidth(38)
        self.b_merge.clicked.connect(self.merge_selected_scene)
        self.b_multi = QPushButton()
        self.b_multi.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogListView))
        self.b_multi.setFixedWidth(38)
        self.b_multi.setCheckable(True)
        self.b_multi.toggled.connect(self.set_multi_select_mode)
        self.b_add_ch.setToolTip("Aggiungi capitolo / Add chapter")
        self.b_add_sc.setToolTip("Aggiungi scena / Add scene")
        self.b_del.setToolTip("Elimina elemento selezionato / Delete selected item")
        self.b_merge.setToolTip("Unisci scene selezionate / Merge selected scenes")
        self.b_multi.setToolTip("Attiva o termina la selezione multipla / Toggle multi-select")
        ch_btns.addWidget(self.b_up)
        ch_btns.addWidget(self.b_down)
        ch_btns.addWidget(self.b_add_ch)
        ch_btns.addWidget(self.b_add_sc)
        ch_btns.addWidget(self.b_merge)
        ch_btns.addWidget(self.b_multi)
        ch_btns.addWidget(self.b_del)
        left_lay.addLayout(ch_btns)

        # CENTER: Live 16:9 TV Preview
        center_panel = QWidget()
        center_lay = QVBoxLayout(center_panel)
        center_lay.setContentsMargins(6, 0, 6, 0)

        hdr_row = QHBoxLayout()
        self.lbl_preview_info = QLabel("📺 Anteprima TV 16:9")
        self.lbl_preview_info.setStyleSheet("font-weight: bold; color: #E0B46A;")

        self.btn_test_play = QPushButton("▶ Test Completo")
        self.btn_test_play.clicked.connect(self.start_full_preview)
        self.btn_test_pause = QPushButton("⏸ Pausa")
        self.btn_test_pause.setEnabled(False)
        self.btn_test_pause.clicked.connect(self.toggle_full_preview_pause)
        self.btn_test_stop = QPushButton("⏹ Stop")
        self.btn_test_stop.setEnabled(False)
        self.btn_test_stop.clicked.connect(self.stop_full_preview)
        self.btn_listen = QPushButton("🔊 Ascolta Scena (TTS)")
        self.btn_listen.clicked.connect(self.preview_scene_tts)

        hdr_row.addWidget(self.lbl_preview_info)
        hdr_row.addStretch()
        hdr_row.addWidget(self.btn_test_play)
        hdr_row.addWidget(self.btn_test_pause)
        hdr_row.addWidget(self.btn_test_stop)
        hdr_row.addWidget(self.btn_listen)
        self.btn_preview_fullscreen = QPushButton("⛶ Anteprima intera")
        self.btn_preview_fullscreen.clicked.connect(self.toggle_preview_fullscreen)
        hdr_row.addWidget(self.btn_preview_fullscreen)
        self.chk_karaoke = QCheckBox("Effetto Karaoke")
        self.chk_karaoke.setToolTip("Evidenzia le parole durante la lettura, anche nel video esportato")
        self.chk_karaoke.setChecked(self.project.settings.karaoke_enabled)
        self.chk_karaoke.toggled.connect(self._on_karaoke_toggled)
        hdr_row.addWidget(self.chk_karaoke)
        center_lay.addLayout(hdr_row)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(420, 236)
        self.preview_label.setStyleSheet("background-color: #0B0D13; border: 1px solid #2A3244; border-radius: 8px;")
        center_lay.addWidget(self.preview_label, 1)

        # RIGHT: Inspector Tabs
        self.right_tabs = QTabWidget()
        self.right_tabs.setMinimumWidth(320)

        # Tab 1: Scene & Media
        tab_scene = QWidget()
        ts_lay = QVBoxLayout(tab_scene)
        self.lbl_scene_text = QLabel("Testo proiettato su TV:")
        ts_lay.addWidget(self.lbl_scene_text)
        self.txt_scene = QTextEdit()
        self.txt_scene.textChanged.connect(self._on_scene_edited)
        ts_lay.addWidget(self.txt_scene, 1)

        scene_form = QFormLayout()
        media_row = QHBoxLayout()
        self.lbl_scene_media = QLineEdit()
        self.lbl_scene_media.setReadOnly(True)
        self.cmb_scene_library = QComboBox()
        self.cmb_scene_library.currentIndexChanged.connect(self._on_scene_library_selected)
        scene_form.addRow("Dalla Libreria Media:", self.cmb_scene_library)
        self.btn_pick_sc_media = QPushButton("Sfoglia...")
        self.btn_pick_sc_media.clicked.connect(self.pick_scene_media)
        media_row.addWidget(self.lbl_scene_media)
        media_row.addWidget(self.btn_pick_sc_media)
        scene_form.addRow("Media Scena:", media_row)

        self.chk_use_ch_media = QCheckBox("Usa media del Capitolo")
        self.chk_use_ch_media.toggled.connect(self._on_scene_edited)
        self.btn_extend_media = QPushButton("Estendi alle successive")
        self.btn_extend_media.setToolTip("Applica l'immagine/video di questa scena anche a tutte le scene successive del capitolo")
        self.btn_extend_media.clicked.connect(self.extend_media_to_next_scenes)
        ext_row = QHBoxLayout()
        ext_row.addWidget(self.chk_use_ch_media)
        ext_row.addWidget(self.btn_extend_media)
        scene_form.addRow("", ext_row)

        self.cmb_ken_burns = QComboBox()
        self.cmb_ken_burns.addItems(["zoom_in", "zoom_out", "pan_left", "pan_right", "static"])
        self.cmb_ken_burns.currentTextChanged.connect(self._on_scene_edited)
        scene_form.addRow("Movimento (Ken Burns):", self.cmb_ken_burns)

        self.chk_pause_override = QCheckBox("Pausa personalizzata per questa scena")
        self.chk_pause_override.toggled.connect(self._on_scene_edited)
        scene_form.addRow("", self.chk_pause_override)

        self.spin_pause = QDoubleSpinBox()
        self.spin_pause.setRange(0.0, 5.0)
        self.spin_pause.setSingleStep(0.2)
        self.spin_pause.valueChanged.connect(self._on_scene_edited)
        scene_form.addRow("Pausa finale (sec):", self.spin_pause)
        self.spin_global_pause = QDoubleSpinBox()
        self.spin_global_pause.setRange(0.0, 10.0)
        self.spin_global_pause.setSingleStep(0.2)
        self.spin_global_pause.valueChanged.connect(self._on_global_pause_edited)
        scene_form.addRow("Pausa predefinita libro (sec):", self.spin_global_pause)

        ts_lay.addLayout(scene_form)
        self.right_tabs.addTab(tab_scene, "Scena & Media")

        # Tab 2: Chapter & Background Audio
        tab_ch = QWidget()
        tc_form = QFormLayout(tab_ch)
        self.edt_ch_title = QLineEdit()
        self.edt_ch_title.textChanged.connect(self._on_chapter_edited)
        tc_form.addRow("Titolo Capitolo:", self.edt_ch_title)

        self.edt_ch_sub = QLineEdit()
        self.edt_ch_sub.textChanged.connect(self._on_chapter_edited)
        tc_form.addRow("Sottotitolo:", self.edt_ch_sub)

        self.chk_title_card = QCheckBox("Mostra copertina capitolo")
        self.chk_title_card.toggled.connect(self._on_chapter_edited)
        tc_form.addRow("", self.chk_title_card)

        ch_m_row = QHBoxLayout()
        self.edt_ch_media = QLineEdit()
        self.edt_ch_media.setReadOnly(True)
        self.cmb_chapter_library = QComboBox()
        self.cmb_chapter_library.currentIndexChanged.connect(self._on_chapter_library_selected)
        tc_form.addRow("Dalla Libreria Media:", self.cmb_chapter_library)
        btn_ch_media = QPushButton("Immagine/Video...")
        btn_ch_media.clicked.connect(self.pick_chapter_media)
        ch_m_row.addWidget(self.edt_ch_media)
        ch_m_row.addWidget(btn_ch_media)
        tc_form.addRow("Sfondo Capitolo:", ch_m_row)

        preset_row = QHBoxLayout()
        self.cmb_preset_bg = QComboBox()
        for label, fname in BUILTIN_BACKGROUNDS:
            self.cmb_preset_bg.addItem(label, fname)
        self.cmb_preset_bg.currentIndexChanged.connect(self.apply_preset_bg_to_chapter)
        self.btn_apply_bg_all = QPushButton("Applica a tutto il libro")
        self.btn_apply_bg_all.clicked.connect(self.apply_chapter_bg_to_whole_book)
        preset_row.addWidget(self.cmb_preset_bg, 1)
        preset_row.addWidget(self.btn_apply_bg_all)
        tc_form.addRow("Sfondo Predefinito:", preset_row)

        ch_a_row = QHBoxLayout()
        self.edt_ch_audio = QLineEdit()
        self.edt_ch_audio.setReadOnly(True)
        btn_ch_audio = QPushButton("Audio/Musica...")
        btn_ch_audio.clicked.connect(self.pick_chapter_audio)
        ch_a_row.addWidget(self.edt_ch_audio)
        ch_a_row.addWidget(btn_ch_audio)
        tc_form.addRow("Musica Sottofondo:", ch_a_row)

        vol_row = QHBoxLayout()
        self.sld_ch_vol = QSlider(Qt.Orientation.Horizontal)
        self.sld_ch_vol.setRange(0, 100)
        self.sld_ch_vol.valueChanged.connect(self._on_chapter_edited)
        self.lbl_ch_vol = QLabel("25%")
        vol_row.addWidget(self.sld_ch_vol)
        vol_row.addWidget(self.lbl_ch_vol)
        tc_form.addRow("Volume Sottofondo:", vol_row)

        self.right_tabs.addTab(tab_ch, "Capitolo & Musica")

        # Tab 3: Global TV & TTS Settings
        tab_set = QWidget()
        tset_form = QFormLayout(tab_set)

        self.edt_book_title = QLineEdit()
        self.edt_book_title.textChanged.connect(self._on_settings_edited)
        tset_form.addRow("Titolo Libro:", self.edt_book_title)

        self.edt_book_author = QLineEdit()
        self.edt_book_author.textChanged.connect(self._on_settings_edited)
        tset_form.addRow("Autore:", self.edt_book_author)

        self.cmb_voice = QComboBox()
        for vid, label in ITALIAN_VOICES:
            self.cmb_voice.addItem(label, vid)
        self.cmb_voice.currentIndexChanged.connect(self._on_settings_edited)
        tset_form.addRow("Voce Narrante:", self.cmb_voice)

        self.cmb_tts_engine = QComboBox()
        self.cmb_tts_engine.addItems(["edge-tts", "offline"])
        self.cmb_tts_engine.currentTextChanged.connect(self._on_settings_edited)
        tset_form.addRow("Motore TTS:", self.cmb_tts_engine)

        self.cmb_style = QComboBox()
        self.cmb_style.addItems(
            ["Libro Cinematografico", "Sottotitoli Cinema", "Pagina Antica", "Minimal Elegante", "Notturno Blu"]
        )
        self.cmb_style.currentTextChanged.connect(self._on_settings_edited)

        self.cmb_font_family = QComboBox()
        self.cmb_font_family.addItems(
            ["Georgia", "Palatino Linotype", "Times New Roman", "Segoe UI", "Calibri", "Arial", "Garamond"]
        )
        self.cmb_font_family.currentTextChanged.connect(self._on_settings_edited)
        tset_form.addRow("Carattere (Font):", self.cmb_font_family)

        self.cmb_font_variant = QComboBox()
        self.cmb_font_variant.addItems(["Normale", "Grassetto", "Corsivo", "Grassetto Corsivo"])
        self.cmb_font_variant.currentTextChanged.connect(self._on_settings_edited)
        tset_form.addRow("Stile Carattere:", self.cmb_font_variant)

        self.spin_font = QSpinBox()
        self.spin_font.setRange(24, 68)
        self.spin_font.valueChanged.connect(self._on_settings_edited)
        tset_form.addRow("Dimensione Testo:", self.spin_font)

        self.cmb_res = QComboBox()
        self.cmb_res.addItems(["1920x1080", "1280x720"])
        self.cmb_res.currentTextChanged.connect(self._on_settings_edited)
        tset_form.addRow("Risoluzione MP4:", self.cmb_res)

        self.chk_ducking = QCheckBox("Auto-Ducking (abbassa musica quando parla)")
        self.chk_ducking.toggled.connect(self._on_settings_edited)
        tset_form.addRow("", self.chk_ducking)

        self.right_tabs.addTab(tab_set, "Voce & Stile TV")

        self.top_splitter.addWidget(left_panel)
        self.top_splitter.addWidget(center_panel)
        self.top_splitter.addWidget(self.right_tabs)
        self.top_splitter.setSizes([280, 700, 400])

        # BOTTOM: Multi-track Timeline
        self.bottom_box = QGroupBox("Timeline VideoLibro (Capitoli • Testo • Media • Audio)")
        bot_lay = QVBoxLayout(self.bottom_box)
        tl_tools = QHBoxLayout()
        self.lbl_total_dur = QLabel("Durata Totale: 00:00")
        b_zin = QPushButton("🔍 +")
        b_zin.clicked.connect(lambda: self.timeline.zoom_in())
        b_zout = QPushButton("🔍 -")
        b_zout.clicked.connect(lambda: self.timeline.zoom_out())
        tl_tools.addWidget(self.lbl_total_dur)
        tl_tools.addStretch()
        tl_tools.addWidget(b_zout)
        tl_tools.addWidget(b_zin)
        bot_lay.addLayout(tl_tools)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.timeline = TimelineWidget()
        self.timeline.entrySelected.connect(self._on_timeline_selected)
        scroll.setWidget(self.timeline)
        bot_lay.addWidget(scroll)

        self.main_splitter.addWidget(self.top_splitter)
        self.main_splitter.addWidget(self.bottom_box)
        self.main_splitter.setSizes([560, 260])

        root_layout.addWidget(self.main_splitter, 1)

        # Progress bar at bottom
        prog_row = QHBoxLayout()
        self.lbl_status = QLabel("Pronto.")
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(280)
        self.progress_bar.setValue(0)
        prog_row.addWidget(self.lbl_status, 1)
        prog_row.addWidget(self.progress_bar)
        root_layout.addLayout(prog_row)

        self.setCentralWidget(central)

    # ---------- Project & Tree Sync ----------

    def _refresh_all(self) -> None:
        self._updating_ui = True
        self.chk_karaoke.blockSignals(True)
        self.chk_karaoke.setChecked(self.project.settings.karaoke_enabled)
        self.chk_karaoke.blockSignals(False)
        self._refresh_media_library()
        self.tree.clear()
        for c_idx, ch in enumerate(self.project.chapters):
            ch_item = QTreeWidgetItem([f"📖 {ch.title}"])
            ch_item.setData(0, Qt.ItemDataRole.UserRole, (c_idx, None))
            if self._multi_select_mode:
                ch_item.setFlags(ch_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                ch_item.setCheckState(0, Qt.CheckState.Unchecked)
            for s_idx, sc in enumerate(ch.scenes):
                snippet = sc.text.strip().replace("\n", " ")
                if len(snippet) > 32:
                    snippet = snippet[:29] + "..."
                sc_item = QTreeWidgetItem([f"  🎬 {s_idx + 1}. {snippet}"])
                sc_item.setData(0, Qt.ItemDataRole.UserRole, (c_idx, s_idx))
                if self._multi_select_mode:
                    sc_item.setFlags(sc_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    sc_item.setCheckState(0, Qt.CheckState.Unchecked)
                ch_item.addChild(sc_item)
            self.tree.addTopLevelItem(ch_item)
            ch_item.setExpanded(True)

        # Settings controls
        s = self.project.settings
        self.edt_book_title.setText(self.project.title)
        self.edt_book_author.setText(self.project.author)
        idx = self.cmb_voice.findData(s.tts_voice)
        if idx >= 0:
            self.cmb_voice.setCurrentIndex(idx)
        self.cmb_tts_engine.setCurrentText(s.tts_engine)
        self.cmb_style.setCurrentText(s.text_style)
        self.cmb_quick_style.setCurrentText(s.text_style)
        self.cmb_font_family.setCurrentText(s.font_family)
        self.cmb_font_variant.setCurrentText(s.font_variant)
        self.spin_font.setValue(s.font_size)
        self.cmb_res.setCurrentText(s.resolution)
        self.chk_ducking.setChecked(s.auto_ducking)

        self._updating_ui = False
        self._refresh_timeline_and_preview()
        self._populate_inspector()

    def _refresh_timeline_and_preview(self) -> None:
        entries = self.project.compute_timeline()
        total = self.project.total_duration()
        self.timeline.set_timeline(entries, total)
        self.timeline.set_selected(self._sel_chapter, self._sel_scene)
        if self._is_testing:
            self._refresh_playhead()

        mins, secs = divmod(int(total), 60)
        self.lbl_total_dur.setText(f"Durata Totale: {mins:02d}:{secs:02d}  ({len(entries)} blocchi)")

        selected_entry = None
        for e in entries:
            if e.chapter_index == self._sel_chapter and e.scene_index == self._sel_scene:
                selected_entry = e
                break
        if selected_entry is None and entries:
            selected_entry = entries[0]

        img = render_preview_frame(self.project, selected_entry, (960, 540), self._preview_progress())
        qimg = ImageQt(img)
        pix = QPixmap.fromImage(qimg).scaled(
            self.preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(pix)

    def _populate_inspector(self) -> None:
        if not self.project.chapters or self._sel_chapter >= len(self.project.chapters):
            return
        self._updating_ui = True
        ch = self.project.chapters[self._sel_chapter]
        self.spin_global_pause.blockSignals(True)
        self.spin_global_pause.setValue(self.project.settings.global_pause_sec)
        self.spin_global_pause.blockSignals(False)
        self.edt_ch_title.setText(ch.title)
        self.edt_ch_sub.setText(ch.subtitle)
        self.chk_title_card.setChecked(ch.show_title_card)
        self.edt_ch_media.setText(ch.default_media_path)
        self._select_library_path(self.cmb_chapter_library, ch.default_media_path)
        self.edt_ch_audio.setText(ch.bg_audio_path)
        vol_pct = int(round(ch.bg_audio_volume * 100))
        self.sld_ch_vol.setValue(vol_pct)
        self.lbl_ch_vol.setText(f"{vol_pct}%")

        if self._sel_scene is not None and 0 <= self._sel_scene < len(ch.scenes):
            sc = ch.scenes[self._sel_scene]
            self.txt_scene.setEnabled(True)
            self.txt_scene.setPlainText(sc.text)
            self.lbl_scene_media.setText(sc.media_path)
            self._select_library_path(self.cmb_scene_library, sc.media_path)
            self.chk_use_ch_media.setChecked(sc.use_chapter_media)
            self.cmb_ken_burns.setCurrentText(sc.ken_burns)
            self.spin_pause.setValue(sc.pause_after_sec)
            self.chk_pause_override.setChecked(sc.pause_override)
            self.spin_pause.setEnabled(sc.pause_override)
            self.lbl_preview_info.setText(f"📺 Anteprima TV 16:9 — {ch.title} • Scena {self._sel_scene + 1}")
        else:
            self.txt_scene.setEnabled(False)
            self.txt_scene.setPlainText("")
            self.lbl_scene_media.clear()
            self._select_library_path(self.cmb_scene_library, "")
            self.lbl_preview_info.setText(f"📺 Anteprima TV 16:9 — Copertina: {ch.title}")
        self._updating_ui = False

    # ---------- UI Callbacks ----------

    def _on_tree_selection(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            return
        data = items[0].data(0, Qt.ItemDataRole.UserRole)
        if data:
            self._sel_chapter, self._sel_scene = data
            self._populate_inspector()
            self._refresh_timeline_and_preview()

    def set_multi_select_mode(self, enabled: bool) -> None:
        self._multi_select_mode = enabled
        self.b_multi.setToolTip(tr(self._lang, "btn_multi_done" if enabled else "btn_multi"))
        self._refresh_all()

    def _checked_tree_targets(self) -> tuple[set[int], dict[int, set[int]]]:
        chapter_indices: set[int] = set()
        scenes_by_chapter: dict[int, set[int]] = {}
        for c_idx in range(self.tree.topLevelItemCount()):
            chapter_item = self.tree.topLevelItem(c_idx)
            if chapter_item.checkState(0) == Qt.CheckState.Checked:
                chapter_indices.add(c_idx)
                continue
            checked = {
                s_idx for s_idx in range(chapter_item.childCount())
                if chapter_item.child(s_idx).checkState(0) == Qt.CheckState.Checked
            }
            if checked:
                scenes_by_chapter[c_idx] = checked
        return chapter_indices, scenes_by_chapter

    def _select_tree_item(self) -> None:
        if not self.project.chapters or not (0 <= self._sel_chapter < len(self.project.chapters)):
            return
        chapter = self.tree.topLevelItem(self._sel_chapter)
        item = chapter.child(self._sel_scene) if self._sel_scene is not None else chapter
        if item is not None:
            self.tree.setCurrentItem(item)

    def _move_selected(self, delta: int) -> None:
        if not self.project.chapters:
            return
        if self._sel_scene is None:
            target = self._sel_chapter + delta
            if not 0 <= target < len(self.project.chapters):
                return
            chapters = self.project.chapters
            chapters[self._sel_chapter], chapters[target] = chapters[target], chapters[self._sel_chapter]
            self._sel_chapter = target
        else:
            chapter = self.project.chapters[self._sel_chapter]
            target = self._sel_scene + delta
            if not 0 <= target < len(chapter.scenes):
                return
            chapter.scenes[self._sel_scene], chapter.scenes[target] = chapter.scenes[target], chapter.scenes[self._sel_scene]
            self._sel_scene = target
        self._refresh_all()
        self._select_tree_item()

    def move_selected_up(self) -> None:
        self._move_selected(-1)

    def move_selected_down(self) -> None:
        self._move_selected(1)

    def merge_selected_scene(self) -> None:
        if self._sel_scene is None or not self.project.chapters:
            return
        chapter = self.project.chapters[self._sel_chapter]
        if len(chapter.scenes) < 2:
            return
        choices = [f"{i + 1}. {scene.text.strip().replace(chr(10), ' ')[:70]}" for i, scene in enumerate(chapter.scenes)]
        start, ok = QInputDialog.getItem(self, "Unisci scene", "Prima scena da unire:", choices, self._sel_scene, False)
        if not ok:
            return
        start_idx = choices.index(start)
        possible_ends = list(range(start_idx + 1, len(chapter.scenes)))
        end_choices = [f"{i + 1}. {chapter.scenes[i].text.strip().replace(chr(10), ' ')[:70]}" for i in possible_ends]
        end, ok = QInputDialog.getItem(self, "Unisci scene", "Unisci fino alla scena:", end_choices, 0, False)
        if not ok:
            return
        end_idx = possible_ends[end_choices.index(end)]
        selected_scenes = chapter.scenes[start_idx:end_idx + 1]
        first = selected_scenes[0]
        first.text = "\n\n".join(scene.text.strip() for scene in selected_scenes if scene.text.strip())
        first.tts_audio_path = ""
        first.tts_duration_sec = 0.0
        first.word_timings = []
        del chapter.scenes[start_idx + 1:end_idx + 1]
        self._sel_scene = start_idx
        self._refresh_all()
        self._select_tree_item()

    def _on_timeline_selected(self, ch_idx: int, sc_idx: object) -> None:
        self._sel_chapter = ch_idx
        self._sel_scene = sc_idx if isinstance(sc_idx, int) else None
        self._populate_inspector()
        self._refresh_timeline_and_preview()

    def _on_scene_edited(self) -> None:
        if self._updating_ui or self._sel_scene is None:
            return
        ch = self.project.chapters[self._sel_chapter]
        sc = ch.scenes[self._sel_scene]
        new_text = self.txt_scene.toPlainText()
        if new_text != sc.text:
            sc.text = new_text
            sc.tts_audio_path = ""
            sc.tts_duration_sec = 0.0
        sc.use_chapter_media = self.chk_use_ch_media.isChecked()
        sc.ken_burns = self.cmb_ken_burns.currentText()  # type: ignore[assignment]
        sc.pause_after_sec = self.spin_pause.value()
        sc.pause_override = self.chk_pause_override.isChecked()
        self.spin_pause.setEnabled(sc.pause_override)
        self._refresh_timeline_and_preview()

    def _on_global_pause_edited(self, value: float) -> None:
        if self._updating_ui:
            return
        self.project.settings.global_pause_sec = value
        self._refresh_timeline_and_preview()

    def _preview_progress(self) -> float:
        entry = next((e for e in self.project.compute_timeline()
                      if e.chapter_index == self._sel_chapter and e.scene_index == self._sel_scene), None)
        if entry is None:
            return 0.0
        elapsed = self._player.position() / 1000.0
        if self._is_testing and self._test_timer.isActive():
            entry_start_ms = self._test_timer.remainingTime()
            elapsed = max(elapsed, entry.duration_sec - max(0, entry_start_ms) / 1000.0)
        elif self._test_paused:
            elapsed = self._paused_entry_elapsed
        return max(0.0, min(1.0, elapsed / max(0.1, entry.duration_sec - entry.pause_sec)))

    def _refresh_preview_motion(self) -> None:
        if self._is_testing:
            self._refresh_playhead()
        if self._sel_scene is None or not self.project.chapters:
            return
        entry = next((e for e in self.project.compute_timeline()
                      if e.chapter_index == self._sel_chapter and e.scene_index == self._sel_scene), None)
        if entry is None:
            return
        active_word = self._active_word_index() if self.project.settings.karaoke_enabled else None
        img = render_preview_frame(self.project, entry, (960, 540), self._preview_progress(), active_word)
        target_label = self._fullscreen_preview_label if self._fullscreen_preview_label and self._fullscreen_preview_label.isVisible() else self.preview_label
        pix = QPixmap.fromImage(ImageQt(img)).scaled(
            target_label.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        target_label.setPixmap(pix)

    def _on_karaoke_toggled(self, enabled: bool) -> None:
        self.project.settings.karaoke_enabled = enabled
        self._refresh_preview_motion()

    def _active_word_index(self) -> int | None:
        if self._sel_scene is None or not self.project.chapters:
            return None
        scene = self.project.chapters[self._sel_chapter].scenes[self._sel_scene]
        timings = scene.word_timings or []
        # Word boundaries tend to feel a little late in visual playback;
        # compensate for display refresh and TTS/audio output startup latency.
        current = self._player.position() / 1000.0 + 0.12
        if self._test_paused:
            current = self._paused_entry_elapsed
        words = scene.text.split()
        if not timings:
            # Offline voices do not expose word boundaries; estimate a moving
            # word cursor across the known speech duration as a fallback.
            duration = max(0.1, scene.tts_duration_sec)
            if not words or current < 0:
                return None
            return min(len(words) - 1, int(current / duration * len(words)))
        def normalize(value: str) -> str:
            return "".join(char.casefold() for char in value if char.isalnum())

        # Edge TTS WordBoundary text is not guaranteed to match the source
        # token exactly (punctuation and contractions can differ). Align each
        # boundary to the next matching source word before returning its index.
        mapped_indices: list[int] = []
        search_from = 0
        for timing in timings:
            boundary = normalize(str(timing.get("text", "")))
            match_index = None
            for word_index in range(search_from, len(words)):
                source_word = normalize(words[word_index])
                if boundary and (source_word == boundary or source_word.startswith(boundary) or boundary.startswith(source_word)):
                    match_index = word_index
                    search_from = word_index + 1
                    break
            mapped_indices.append(match_index if match_index is not None else min(len(mapped_indices), max(0, len(words) - 1)))

        active_timing = None
        for index, timing in enumerate(timings):
            start = float(timing.get("offset_sec", 0.0))
            if start <= current:
                active_timing = index
            else:
                break
        return mapped_indices[active_timing] if active_timing is not None else None

    def toggle_preview_fullscreen(self) -> None:
        if self._preview_fullscreen_window and self._preview_fullscreen_window.isVisible():
            self._preview_fullscreen_window.close()
            return
        window = QWidget(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        window.setStyleSheet("background-color: #0B0D13;")
        layout = QVBoxLayout(window)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        window.installEventFilter(self)
        window.destroyed.connect(lambda: setattr(self, "_fullscreen_preview_label", None))
        self._preview_fullscreen_window = window
        self._fullscreen_preview_label = label
        window.showFullScreen()
        self._refresh_preview_motion()

    def eventFilter(self, watched, event):
        if watched is self._preview_fullscreen_window and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_F11):
                watched.close()
                return True
        return super().eventFilter(watched, event)

    def _refresh_playhead(self) -> None:
        if not self._is_testing or not self._test_entries:
            self.timeline.set_playhead(None)
            return
        elapsed_in_entry = self._test_entries[self._test_index].duration_sec
        if self._test_timer.isActive():
            elapsed_in_entry -= max(0, self._test_timer.remainingTime()) / 1000.0
        elapsed_in_entry = max(0.0, elapsed_in_entry)
        if self._test_paused:
            elapsed_in_entry = self._paused_entry_elapsed
        self.timeline.set_playhead(self._test_entries[self._test_index].start_sec + elapsed_in_entry)

    def _on_chapter_edited(self) -> None:
        if self._updating_ui or not self.project.chapters:
            return
        ch = self.project.chapters[self._sel_chapter]
        ch.title = self.edt_ch_title.text()
        ch.subtitle = self.edt_ch_sub.text()
        ch.show_title_card = self.chk_title_card.isChecked()
        vol_pct = self.sld_ch_vol.value()
        self.lbl_ch_vol.setText(f"{vol_pct}%")
        ch.bg_audio_volume = vol_pct / 100.0
        self._refresh_timeline_and_preview()

    def _on_quick_style_changed(self, style_text: str) -> None:
        if self._updating_ui:
            return
        self.cmb_style.setCurrentText(style_text)

    def _on_settings_edited(self) -> None:
        if self._updating_ui:
            return
        self.project.title = self.edt_book_title.text()
        self.project.author = self.edt_book_author.text()
        s = self.project.settings
        s.tts_voice = self.cmb_voice.currentData() or "it-IT-DiegoNeural"
        s.tts_engine = self.cmb_tts_engine.currentText()  # type: ignore[assignment]
        s.text_style = self.cmb_style.currentText()  # type: ignore[assignment]
        if self.cmb_quick_style.currentText() != s.text_style:
            self._updating_ui = True
            self.cmb_quick_style.setCurrentText(s.text_style)
            self._updating_ui = False
        s.font_family = self.cmb_font_family.currentText()
        s.font_variant = self.cmb_font_variant.currentText()
        s.font_size = self.spin_font.value()
        s.resolution = self.cmb_res.currentText()
        s.auto_ducking = self.chk_ducking.isChecked()
        self._refresh_timeline_and_preview()

    # ---------- Actions ----------

    def load_demo_project(self) -> None:
        self.project = build_demo_project(self.workspace_dir)
        self._sel_chapter = 0
        self._sel_scene = 0 if self.project.chapters and self.project.chapters[0].scenes else None
        self._refresh_all()
        self.lbl_status.setText("Progetto demo 'Il Manoscritto di Pietra' caricato.")

    def import_manuscript_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Importa Manoscritto",
            str(self.workspace_dir),
            "Manoscritti (*.docx *.txt *.md)",
        )
        if not path:
            return
        reply = QMessageBox.question(
            self,
            "Rilevamento Capitoli",
            "Vuoi rilevare automaticamente i capitoli dai titoli di Word/testo?\n"
            "(Scegli 'No' per importare tutto in un capitolo e dividerlo manualmente)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        auto = reply == QMessageBox.StandardButton.Yes
        title, chapters = import_manuscript_file(path, auto_detect_chapters=auto)
        default_bg = self._resolve_builtin_bg("biblioteca_antica.jpg")
        if default_bg:
            for ch in chapters:
                ch.default_media_path = default_bg
                ch.default_media_type = "image"
        self.project = VideoBookProject(title=title, source_file=path, chapters=chapters)
        self._sel_chapter = 0
        self._sel_scene = 0 if chapters and chapters[0].scenes else None
        self._refresh_all()
        self.lbl_status.setText(f"Importato '{title}' ({len(chapters)} capitoli).")

    def open_project_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Apri Progetto VideoLibro", str(self.workspace_dir), "VideoLibro (*.vlibro)")
        if not path:
            return
        self.project = VideoBookProject.load(path)
        self._sel_chapter = 0
        self._sel_scene = 0 if self.project.chapters and self.project.chapters[0].scenes else None
        self._refresh_all()
        self.lbl_status.setText(f"Progetto aperto: {Path(path).name}")

    def save_project_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Salva Progetto VideoLibro",
            str(self.workspace_dir / f"{self.project.title.replace(' ', '_')}.vlibro"),
            "VideoLibro (*.vlibro)",
        )
        if not path:
            return
        self.project.save(path)
        self.lbl_status.setText(f"Progetto salvato in {Path(path).name}")

    def add_chapter(self) -> None:
        idx = len(self.project.chapters) + 1
        self.project.chapters.append(
            Chapter(title=f"Capitolo {idx}", scenes=[SceneBlock(text="Nuova scena del capitolo...")])
        )
        self._sel_chapter = len(self.project.chapters) - 1
        self._sel_scene = 0
        self._refresh_all()

    def add_scene(self) -> None:
        if not self.project.chapters:
            self.add_chapter()
            return
        ch = self.project.chapters[self._sel_chapter]
        ch.scenes.append(SceneBlock(text="Nuovo paragrafo del manoscritto..."))
        self._sel_scene = len(ch.scenes) - 1
        self._refresh_all()

    def delete_selected(self) -> None:
        if not self.project.chapters:
            return
        if self._multi_select_mode:
            chapter_targets, scene_targets = self._checked_tree_targets()
            count = len(chapter_targets) + sum(len(indices) for indices in scene_targets.values())
            if not count:
                return
            answer = QMessageBox.question(
                self, "Conferma eliminazione",
                f"Eliminare {count} elemento/i selezionato/i?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            for c_idx, indices in sorted(scene_targets.items(), reverse=True):
                if c_idx >= len(self.project.chapters) or c_idx in chapter_targets:
                    continue
                chapter = self.project.chapters[c_idx]
                for s_idx in sorted(indices, reverse=True):
                    if s_idx < len(chapter.scenes):
                        del chapter.scenes[s_idx]
            for c_idx in sorted(chapter_targets, reverse=True):
                if c_idx < len(self.project.chapters):
                    del self.project.chapters[c_idx]
            if not self.project.chapters:
                self._sel_chapter, self._sel_scene = 0, None
            else:
                self._sel_chapter = min(self._sel_chapter, len(self.project.chapters) - 1)
                scenes = self.project.chapters[self._sel_chapter].scenes
                self._sel_scene = min(self._sel_scene or 0, len(scenes) - 1) if scenes else None
            self.b_multi.setChecked(False)
            self.set_multi_select_mode(False)
            self._refresh_all()
            return
        ch = self.project.chapters[self._sel_chapter]
        target_label = f"la scena {self._sel_scene + 1}" if self._sel_scene is not None else f"il capitolo '{ch.title}'"
        answer = QMessageBox.question(
            self, "Conferma eliminazione", f"Eliminare {target_label}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if self._sel_scene is not None:
            ch.scenes.pop(self._sel_scene)
            if ch.scenes:
                self._sel_scene = min(self._sel_scene, len(ch.scenes) - 1)
            elif len(self.project.chapters) > 1:
                self.project.chapters.pop(self._sel_chapter)
                self._sel_chapter = min(self._sel_chapter, len(self.project.chapters) - 1)
                self._sel_scene = 0 if self.project.chapters[self._sel_chapter].scenes else None
            else:
                self._sel_scene = None
        else:
            self.project.chapters.pop(self._sel_chapter)
            if self.project.chapters:
                self._sel_chapter = min(self._sel_chapter, len(self.project.chapters) - 1)
                self._sel_scene = 0 if self.project.chapters[self._sel_chapter].scenes else None
            else:
                self._sel_chapter, self._sel_scene = 0, None
        self._refresh_all()

    def pick_scene_media(self) -> None:
        if self._sel_scene is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleziona Immagine o Video per la Scena", str(self.workspace_dir), "Media (*.jpg *.jpeg *.png *.mp4 *.mov *.avi)"
        )
        if not path:
            return
        sc = self.project.chapters[self._sel_chapter].scenes[self._sel_scene]
        sc.media_path = path
        sc.media_type = "video" if Path(path).suffix.lower() in {".mp4", ".mov", ".avi", ".mkv"} else "image"
        sc.use_chapter_media = False
        self._select_library_path(self.cmb_scene_library, path)
        self._populate_inspector()
        self._refresh_timeline_and_preview()

    def pick_chapter_media(self) -> None:
        if not self.project.chapters:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleziona Sfondo del Capitolo", str(self.workspace_dir), "Media (*.jpg *.jpeg *.png *.mp4 *.mov *.avi)"
        )
        if not path:
            return
        ch = self.project.chapters[self._sel_chapter]
        ch.default_media_path = path
        ch.default_media_type = "video" if Path(path).suffix.lower() in {".mp4", ".mov", ".avi", ".mkv"} else "image"
        self._select_library_path(self.cmb_chapter_library, path)
        self._populate_inspector()
        self._refresh_timeline_and_preview()

    def _refresh_media_library(self) -> None:
        self.media_library_dir.mkdir(parents=True, exist_ok=True)
        paths = sorted(
            (p for p in self.media_library_dir.iterdir() if p.is_file() and p.suffix.lower() in {
                ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".mp4", ".mov", ".avi", ".mkv", ".webm"
            }),
            key=lambda p: p.name.casefold(),
        )
        for combo in (self.cmb_scene_library, self.cmb_chapter_library):
            selected_path = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("Seleziona dalla libreria…", "")
            for path in paths:
                kind = "Video" if path.suffix.lower() in {".mp4", ".mov", ".avi", ".mkv", ".webm"} else "Immagine"
                combo.addItem(f"{kind}: {path.name}", str(path))
            self._select_library_path(combo, selected_path)
            combo.blockSignals(False)

    @staticmethod
    def _select_library_path(combo: QComboBox, path: str | None) -> None:
        if path:
            index = combo.findData(path)
            combo.setCurrentIndex(index if index >= 0 else 0)
        else:
            combo.setCurrentIndex(0)

    def import_to_media_library(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Carica immagini o video nella Libreria Media",
            str(self.workspace_dir),
            "Immagini e video (*.jpg *.jpeg *.png *.webp *.bmp *.mp4 *.mov *.avi *.mkv *.webm)",
        )
        if not paths:
            return
        self.media_library_dir.mkdir(parents=True, exist_ok=True)
        added = 0
        for source in paths:
            src = Path(source)
            dest = self.media_library_dir / f"{uuid.uuid4().hex[:8]}_{src.name}"
            try:
                shutil.copy2(src, dest)
                added += 1
            except OSError as exc:
                QMessageBox.warning(self, "Caricamento non riuscito", f"Non riesco a copiare {src.name}:\n{exc}")
        self._refresh_media_library()
        self.lbl_status.setText(f"Aggiunti {added} file alla Libreria Media.")

    def _on_scene_library_selected(self, index: int) -> None:
        if self._updating_ui or index <= 0 or self._sel_scene is None:
            return
        path = str(self.cmb_scene_library.itemData(index))
        sc = self.project.chapters[self._sel_chapter].scenes[self._sel_scene]
        sc.media_path = path
        sc.media_type = self._media_type_for_path(path)
        sc.use_chapter_media = False
        self._populate_inspector()
        self._refresh_timeline_and_preview()

    def _on_chapter_library_selected(self, index: int) -> None:
        if self._updating_ui or index <= 0 or not self.project.chapters:
            return
        path = str(self.cmb_chapter_library.itemData(index))
        ch = self.project.chapters[self._sel_chapter]
        ch.default_media_path = path
        ch.default_media_type = self._media_type_for_path(path)
        self._populate_inspector()
        self._refresh_timeline_and_preview()

    @staticmethod
    def _media_type_for_path(path: str) -> str:
        return "video" if Path(path).suffix.lower() in {".mp4", ".mov", ".avi", ".mkv", ".webm"} else "image"

    def pick_chapter_audio(self) -> None:
        if not self.project.chapters:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleziona Musica di Sottofondo", str(self.workspace_dir), "Audio (*.mp3 *.wav *.ogg *.m4a)"
        )
        if not path:
            return
        ch = self.project.chapters[self._sel_chapter]
        ch.bg_audio_path = path
        self._populate_inspector()
        self._refresh_timeline_and_preview()

    def preview_scene_tts(self) -> None:
        if self._sel_scene is None:
            return
        sc = self.project.chapters[self._sel_chapter].scenes[self._sel_scene]
        self.lbl_status.setText("Generazione anteprima vocale TTS...")
        self._karaoke_timer.stop()
        ap, dur, timings = synthesize_scene_tts(
            sc.text,
            self.tts_cache_dir,
            sc.id,
            voice=self.project.settings.tts_voice,
            rate=self.project.settings.tts_rate,
            engine=self.project.settings.tts_engine,
        )
        sc.tts_audio_path = ap
        sc.tts_duration_sec = dur
        sc.word_timings = timings
        self._refresh_timeline_and_preview()
        if not ap:
            return
        self._player.setSource(QUrl.fromLocalFile(ap))
        self._audio_out.setVolume(0.95)
        self._player.play()
        self._is_listening_scene = True
        self.btn_test_play.setEnabled(False)
        self.btn_test_pause.setEnabled(True)
        self.btn_test_stop.setEnabled(True)
        self._karaoke_timer.start()
        self.lbl_status.setText(f"Riproduzione TTS ({dur:.1f}s)...")

    def generate_all_tts(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self.progress_bar.setValue(0)
        total_scenes = sum(len(ch.scenes) for ch in self.project.chapters)
        cancel_event = threading.Event()
        dlg = TaskProgressDialog(
            self,
            lang=self._lang,
            title="Generazione voci TTS" if self._lang == "it" else "Generating TTS voices",
            description=f"Elaborazione di {total_scenes} scene…" if self._lang == "it" else f"Processing {total_scenes} scenes…",
        )
        dlg.cancel_event = cancel_event
        dlg.cancelRequested.connect(cancel_event.set)
        worker = TTSBatchWorker(self.project, self.tts_cache_dir, cancel_event)
        worker.progress.connect(dlg.update_progress)
        worker.progress.connect(lambda p, m: (self.progress_bar.setValue(p), self.lbl_status.setText(m)))
        worker.finished_ok.connect(self._on_tts_batch_done)
        worker.cancelled.connect(self._on_tts_batch_cancelled)
        worker.failed.connect(self._on_tts_batch_failed)
        self._worker = worker
        worker.start()
        self._task_dialog = dlg
        dlg.show()

    def _on_tts_batch_done(self) -> None:
        self._close_task_dialog()
        self.progress_bar.setValue(100)
        self.lbl_status.setText("Voci TTS generate per tutto il manoscritto!")
        self._refresh_timeline_and_preview()

    def _on_tts_batch_cancelled(self) -> None:
        self._close_task_dialog()
        self.lbl_status.setText("Generazione fermata. Le voci già completate sono state conservate." if self._lang == "it" else "Generation stopped. Completed voice files were kept.")
        self._refresh_timeline_and_preview()

    def _on_tts_batch_failed(self, error: str) -> None:
        self._close_task_dialog()
        QMessageBox.critical(self, "Errore TTS", error)

    def _close_task_dialog(self) -> None:
        dlg = getattr(self, "_task_dialog", None)
        if dlg is not None:
            dlg._last_pct = 100
            dlg.close()
            self._task_dialog = None

    def export_mp4_dialog(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        options = ExportOptionsDialog(self, self._lang, self.project.total_duration())
        if options.exec() != QDialog.DialogCode.Accepted:
            return
        ext = options.output_format
        default_out = self.workspace_dir / f"{self.project.title.replace(' ', '_')}.{ext}"
        filter_text = "Video MP4 (*.mp4)" if ext == "mp4" else "Video MKV (*.mkv)"
        out_path, _ = QFileDialog.getSaveFileName(self, "Esporta VideoLibro", str(default_out), filter_text)
        if not out_path:
            return
        if Path(out_path).suffix.lower() != f".{ext}":
            out_path = str(Path(out_path).with_suffix(f".{ext}"))

        self.btn_export.setEnabled(False)
        self.progress_bar.setValue(0)
        dlg = ExportProgressDialog(
            self, lang=self._lang, total_duration_sec=self.project.total_duration(), speed_mode=options.speed_mode
        )
        self._export_dialog = dlg

        worker = ExportWorker(self.project, out_path, dlg.cancel_event, ext, options.speed_mode)
        worker.progress.connect(dlg.update_progress)
        worker.progress.connect(lambda p, m: (self.progress_bar.setValue(p), self.lbl_status.setText(m)))
        worker.size_updated.connect(dlg.update_size)
        worker.finished_ok.connect(self._on_export_done)
        worker.cancelled.connect(self._on_export_cancelled)
        worker.failed.connect(self._on_export_failed)
        self._worker = worker
        worker.start()
        dlg.show()

    def _close_export_dialog(self) -> None:
        dlg = getattr(self, "_export_dialog", None)
        if dlg is not None:
            dlg._last_pct = 100
            dlg.close()
            self._export_dialog = None

    def _on_export_done(self, out_path: str) -> None:
        self._close_export_dialog()
        self.btn_export.setEnabled(True)
        self.progress_bar.setValue(100)
        self.lbl_status.setText(f"Esportazione completata: {out_path}")
        self._refresh_timeline_and_preview()
        ans = QMessageBox.information(
            self,
            "VideoLibro Pronto!",
            f"Il tuo VideoLibro MP4 è stato generato:\n{out_path}\n\nVuoi aprire la cartella di destinazione?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            os.startfile(str(Path(out_path).parent))

    def _on_export_cancelled(self) -> None:
        self._close_export_dialog()
        self.btn_export.setEnabled(True)
        self.progress_bar.setValue(0)
        self.lbl_status.setText("Esportazione annullata.")

    def _on_export_failed(self, err: str) -> None:
        self._close_export_dialog()
        self.btn_export.setEnabled(True)
        self.lbl_status.setText("Errore durante l'esportazione.")
        QMessageBox.critical(self, "Errore Esportazione MP4", err)

    # ---------- Built-in Backgrounds ----------

    def _resolve_builtin_bg(self, filename: str) -> str:
        bundle_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
        p = bundle_dir / "assets" / "backgrounds" / filename
        if not p.exists():
            p = self.workspace_dir / "assets" / "backgrounds" / filename
        return str(p) if p.exists() else ""

    def apply_preset_bg_to_chapter(self) -> None:
        if self._updating_ui or not self.project.chapters:
            return
        fname = self.cmb_preset_bg.currentData()
        if not fname:
            return
        bg_path = self._resolve_builtin_bg(str(fname))
        if not bg_path:
            return
        ch = self.project.chapters[self._sel_chapter]
        ch.default_media_path = bg_path
        ch.default_media_type = "image"
        self._populate_inspector()
        self._refresh_timeline_and_preview()

    def apply_chapter_bg_to_whole_book(self) -> None:
        if not self.project.chapters:
            return
        cur = self.project.chapters[self._sel_chapter]
        media_path = cur.default_media_path
        media_type = cur.default_media_type
        if not media_path:
            fname = self.cmb_preset_bg.currentData()
            if fname:
                media_path = self._resolve_builtin_bg(str(fname))
                media_type = "image"
        if not media_path:
            return
        for ch in self.project.chapters:
            ch.default_media_path = media_path
            ch.default_media_type = media_type
            for sc in ch.scenes:
                sc.use_chapter_media = True
        self._populate_inspector()
        self._refresh_timeline_and_preview()
        self.lbl_status.setText(f"Sfondo applicato a tutti i {len(self.project.chapters)} capitoli del libro.")

    # ---------- Help, Media Propagation & Full Live Test Preview ----------

    def show_help_dialog(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(tr(self._lang, "help_title"))
        dlg.resize(620, 520)
        lay = QVBoxLayout(dlg)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(tr(self._lang, "help_html"))
        lay.addWidget(browser)
        btn_ok = QPushButton(tr(self._lang, "help_close"))
        btn_ok.clicked.connect(dlg.accept)
        lay.addWidget(btn_ok, alignment=Qt.AlignmentFlag.AlignRight)
        dlg.exec()

    def _on_language_changed(self) -> None:
        lang = self.cmb_lang.currentData() or "it"
        self._lang = str(lang)
        self._settings_store.setValue("ui_language", self._lang)
        self._retranslate_ui()
        self.btn_preview_fullscreen.setText("⛶ Schermo intero anteprima" if self._lang == "it" else "⛶ Full-screen preview")

    def _retranslate_ui(self) -> None:
        L = self._lang
        self.setWindowTitle(tr(L, "window_title"))
        self.btn_import.setText(tr(L, "tb_import"))
        self.btn_demo.setText(tr(L, "tb_demo"))
        self.btn_open.setText(tr(L, "tb_open"))
        self.btn_save.setText(tr(L, "tb_save"))
        self.btn_tts_all.setText(tr(L, "tb_tts_all"))
        self.btn_export.setText(tr(L, "tb_export"))
        self.btn_help.setText(tr(L, "tb_help"))
        self.btn_preview_fullscreen.setText("⛶ Schermo intero anteprima" if L == "it" else "⛶ Full-screen preview")
        self._update_fullscreen_button()
        self._update_update_button()
        self.lbl_left_hdr.setText(tr(L, "left_header"))
        self.b_up.setToolTip(tr(L, "tip_up"))
        self.b_down.setToolTip(tr(L, "tip_down"))
        self.b_add_ch.setToolTip(tr(L, "btn_add_ch"))
        self.b_add_sc.setToolTip(tr(L, "btn_add_sc"))
        self.b_del.setToolTip(tr(L, "btn_del"))
        self.b_merge.setToolTip(tr(L, "btn_merge"))
        self.b_multi.setToolTip(tr(L, "btn_multi_done" if self._multi_select_mode else "btn_multi"))
        self.btn_test_play.setText(tr(L, "btn_test_play"))
        self.btn_test_pause.setText("⏸ Pausa" if L == "it" else "⏸ Pause")
        self.btn_test_stop.setText(tr(L, "btn_test_stop"))
        self.btn_listen.setText(tr(L, "btn_listen"))
        _style_tip = "Stile visivo TV" if L == "it" else "TV Visual Style"
        self.cmb_quick_style.setToolTip(_style_tip)
        self.lbl_scene_text.setText(tr(L, "lbl_scene_text"))
        self.btn_pick_sc_media.setText(tr(L, "btn_browse"))
        self.chk_use_ch_media.setText(tr(L, "chk_use_ch_media"))
        self.btn_extend_media.setText(tr(L, "btn_extend_media"))
        self.btn_extend_media.setToolTip(tr(L, "tip_extend_media"))
        self.chk_title_card.setText(tr(L, "chk_title_card"))
        self.btn_apply_bg_all.setText(tr(L, "btn_apply_bg_all"))
        self.chk_ducking.setText(tr(L, "chk_ducking"))
        self.right_tabs.setTabText(0, tr(L, "tab_scene"))
        self.right_tabs.setTabText(1, tr(L, "tab_chapter"))
        self.right_tabs.setTabText(2, tr(L, "tab_settings"))
        self.bottom_box.setTitle(tr(L, "tl_group"))
        self.timeline.set_language(L)
        self._populate_inspector()
        self._refresh_timeline_and_preview()

    def extend_media_to_next_scenes(self) -> None:
        if self._sel_scene is None or not self.project.chapters:
            return
        ch = self.project.chapters[self._sel_chapter]
        src = ch.scenes[self._sel_scene]
        media_path = ch.default_media_path if src.use_chapter_media else src.media_path
        media_type = ch.default_media_type if src.use_chapter_media else src.media_type
        if not media_path:
            QMessageBox.information(
                self,
                "Nessun media",
                "Seleziona prima un'immagine o un video per questa scena.",
            )
            return
        dlg = ExtendMediaDialog(
            self,
            remaining_scenes=len(ch.scenes) - self._sel_scene - 1,
            lang=self._lang,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        if dlg.scope == "next":
            targets = ch.scenes[self._sel_scene + 1 : self._sel_scene + 2]
        elif dlg.scope == "count":
            targets = ch.scenes[self._sel_scene + 1 : self._sel_scene + 1 + dlg.spin_count.value()]
        elif dlg.scope == "book":
            targets = [scene for chapter in self.project.chapters for scene in chapter.scenes]
        else:
            targets = ch.scenes

        for sc in targets:
            sc.media_path = media_path
            sc.media_type = media_type
            sc.use_chapter_media = False
        self._populate_inspector()
        self._refresh_timeline_and_preview()
        scope_description = {
            "next": "alla scena successiva",
            "count": f"a {len(targets)} scene successive",
            "book": "a tutte le scene del libro",
            "chapter": f"a tutte le scene del capitolo '{ch.title}'",
        }[dlg.scope]
        self.lbl_status.setText(f"Media esteso {scope_description} ({len(targets)} scene aggiornate).")

    def start_full_preview(self) -> None:
        entries = self.project.compute_timeline()
        if not entries:
            return
        horizon_scene_ids = {
            self.project.chapters[e.chapter_index].scenes[e.scene_index].id
            for e in entries
            if e.kind == "scene" and e.scene_index is not None and e.start_sec < 120
        }
        first_jobs, later_jobs = [], []
        for chapter in self.project.chapters:
            for scene in chapter.scenes:
                if (scene.tts_audio_path and Path(scene.tts_audio_path).is_file()
                        and (self.project.settings.tts_engine != "edge-tts" or scene.word_timings)):
                    continue
                job = (scene.text, scene.id, self.project.settings.tts_voice,
                       self.project.settings.tts_rate, self.project.settings.tts_engine)
                (first_jobs if scene.id in horizon_scene_ids else later_jobs).append(job)
        self._preview_tts_remaining_jobs = later_jobs
        if first_jobs:
            self._show_preview_tts_dialog(first_jobs)
            return
        self._begin_full_preview()
        self._start_background_preview_tts()

    def _show_preview_tts_dialog(self, jobs: list[tuple[str, str, str, str, str]]) -> None:
        dlg = TaskProgressDialog(
            self, lang=self._lang,
            title="Preparazione anteprima vocale" if self._lang == "it" else "Preparing voice preview",
            description="Preparo la voce per i primi due minuti…" if self._lang == "it" else "Preparing narration for the first two minutes…",
        )
        dlg.btn_cancel.setVisible(False)
        worker = TTSPrepareWorker(jobs, self.tts_cache_dir)
        worker.progress.connect(dlg.update_progress)
        worker.scene_ready.connect(self._on_preview_scene_tts_ready)
        worker.finished_ok.connect(self._on_initial_preview_tts_done)
        worker.failed.connect(self._on_preview_tts_failed)
        self._preview_tts_dialog = dlg
        self._preview_tts_worker = worker
        self._preview_tts_workers.append(worker)
        dlg.show()
        worker.start()

    def _on_preview_scene_tts_ready(self, scene_id: str, path: str, duration: float, timings) -> None:
        for chapter in self.project.chapters:
            for scene in chapter.scenes:
                if scene.id == scene_id:
                    scene.tts_audio_path = path
                    scene.tts_duration_sec = duration
                    scene.word_timings = list(timings or [])
                    return

    def _on_initial_preview_tts_done(self) -> None:
        if self._preview_tts_dialog:
            self._preview_tts_dialog.cancel_event.set()
            self._preview_tts_dialog.accept()
        self._begin_full_preview()
        self._start_background_preview_tts()

    def _on_preview_tts_failed(self, message: str) -> None:
        if self._preview_tts_dialog:
            self._preview_tts_dialog.cancel_event.set()
            self._preview_tts_dialog.accept()
        self.lbl_status.setText(f"Errore preparazione TTS: {message}")
        self._begin_full_preview()

    def _start_background_preview_tts(self) -> None:
        if not self._preview_tts_remaining_jobs:
            return
        worker = TTSPrepareWorker(self._preview_tts_remaining_jobs, self.tts_cache_dir)
        self._preview_tts_remaining_jobs = []
        worker.scene_ready.connect(self._on_preview_scene_tts_ready)
        worker.failed.connect(lambda message: self.lbl_status.setText(f"Errore TTS in background: {message}"))
        self._preview_tts_worker = worker
        self._preview_tts_workers.append(worker)
        worker.start()

    def _begin_full_preview(self) -> None:
        if not self.project.compute_timeline():
            return
        self.stop_full_preview()
        self._test_entries = self.project.compute_timeline()
        self._test_index = 0
        self._is_testing = True
        self._test_paused = False
        self._preview_motion_timer.start()
        self.btn_test_play.setEnabled(False)
        self.btn_test_pause.setEnabled(True)
        self.btn_test_pause.setText("⏸ Pausa" if self._lang == "it" else "⏸ Pause")
        self.btn_test_stop.setEnabled(True)
        self._play_test_entry(0)

    def stop_full_preview(self) -> None:
        was_listening = self._is_listening_scene
        self._is_listening_scene = False
        self._is_testing = False
        self._test_paused = False
        self._preview_motion_timer.stop()
        self._test_timer.stop()
        self._karaoke_timer.stop()
        self._player.stop()
        self._bgm_player.stop()
        self.btn_test_play.setEnabled(True)
        self.btn_test_pause.setEnabled(False)
        self.btn_test_pause.setText("⏸ Pausa" if self._lang == "it" else "⏸ Pause")
        self.btn_test_stop.setEnabled(False)
        self.timeline.set_playhead(None)
        self.lbl_status.setText("Riproduzione scena fermata." if was_listening else "Anteprima completa fermata.")

    def _advance_full_preview(self) -> None:
        if not self._is_testing:
            return
        if self._test_paused:
            self._test_timer.start(250)
            return
        next_idx = self._test_index + 1
        if next_idx >= len(self._test_entries):
            self.stop_full_preview()
            self.lbl_status.setText("Anteprima completa terminata.")
            return
        self._play_test_entry(next_idx)

    def _play_test_entry(self, idx: int) -> None:
        if not self._is_testing or idx >= len(self._test_entries):
            return
        # Cancel any previous segment deadline before replacing its media.
        self._test_timer.stop()
        self._test_index = idx
        self._test_paused = False
        entry = self._test_entries[idx]
        self._sel_chapter = entry.chapter_index
        self._sel_scene = entry.scene_index
        self._populate_inspector()
        self._refresh_timeline_and_preview()
        self._player.setPosition(0)

        # Background music with live auto-ducking
        if entry.bg_audio_path and Path(entry.bg_audio_path).exists():
            vol = entry.bg_audio_volume
            if entry.kind == "scene" and self.project.settings.auto_ducking:
                vol *= self.project.settings.ducking_factor
            self._bgm_out.setVolume(max(0.0, min(1.0, vol)))
            bgm_url = QUrl.fromLocalFile(entry.bg_audio_path)
            if self._bgm_player.source() != bgm_url:
                self._bgm_player.setSource(bgm_url)
                self._bgm_player.setLoops(QMediaPlayer.Loops.Infinite)
            if self._bgm_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self._bgm_player.play()
        else:
            self._bgm_player.stop()

        dur_sec = entry.duration_sec
        if entry.kind == "scene":
            sc = self.project.chapters[entry.chapter_index].scenes[entry.scene_index or 0]
            if sc.tts_audio_path and Path(sc.tts_audio_path).exists():
                self._audio_out.setVolume(0.95)
                self._player.setSource(QUrl.fromLocalFile(sc.tts_audio_path))
                self._player.play()
                if sc.word_timings:
                    self._karaoke_timer.start()
                else:
                    self._karaoke_timer.stop()
            else:
                self._karaoke_timer.stop()
                self.lbl_status.setText(
                    f"TTS non ancora generato: {entry.label}. La scena prosegue senza voce."
                )
        else:
            self._player.stop()
            self._karaoke_timer.stop()

        self.lbl_status.setText(f"▶ Test Live ({idx + 1}/{len(self._test_entries)}): {entry.label}")
        self._test_timer.start(max(1200, int(dur_sec * 1000)))

    def toggle_full_preview_pause(self) -> None:
        if self._is_listening_scene and not self._is_testing:
            if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self._player.pause()
                self._karaoke_timer.stop()
                self.btn_test_pause.setText("▶ Riprendi" if self._lang == "it" else "▶ Resume")
            else:
                self._player.play()
                self._karaoke_timer.start()
                self.btn_test_pause.setText("⏸ Pausa" if self._lang == "it" else "⏸ Pause")
            return
        if not self._is_testing:
            return
        if not self._test_paused:
            current = self._test_entries[self._test_index]
            self._paused_remaining_ms = max(0, self._test_timer.remainingTime())
            self._paused_entry_elapsed = max(0.0, current.duration_sec - self._paused_remaining_ms / 1000.0)
            self._test_timer.stop()
            self._player.pause()
            self._bgm_player.pause()
            self._test_paused = True
            self.btn_test_pause.setText("▶ Riprendi" if self._lang == "it" else "▶ Resume")
        else:
            self._test_paused = False
            self._test_timer.start(max(1, self._paused_remaining_ms))
            if self._player.source().isValid():
                self._player.play()
            if self._bgm_player.source().isValid():
                self._bgm_player.play()
            self.btn_test_pause.setText("⏸ Pausa" if self._lang == "it" else "⏸ Pause")
