"""Main Studio Window for VideoLibro Studio."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PIL.ImageQt import ImageQt
from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
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
    QTabWidget,
    QTextEdit,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..importer import import_manuscript_file, split_text_into_scenes
from ..models import Chapter, SceneBlock, VideoBookProject
from ..renderer import export_project_to_mp4, render_preview_frame
from ..sample_generator import build_demo_project
from ..tts_engine import ITALIAN_VOICES, synthesize_scene_tts
from .timeline_widget import TimelineWidget


class ExportWorker(QThread):
    progress = Signal(int, str)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, project: VideoBookProject, output_path: str) -> None:
        super().__init__()
        self.project = project
        self.output_path = output_path

    def run(self) -> None:
        try:
            out = export_project_to_mp4(
                self.project,
                self.output_path,
                generate_missing_tts=True,
                progress_cb=lambda p, m: self.progress.emit(p, m),
            )
            self.finished_ok.emit(str(out))
        except Exception as exc:
            self.failed.emit(str(exc))


class TTSBatchWorker(QThread):
    progress = Signal(int, str)
    finished_ok = Signal()
    failed = Signal(str)

    def __init__(self, project: VideoBookProject, cache_dir: Path) -> None:
        super().__init__()
        self.project = project
        self.cache_dir = cache_dir

    def run(self) -> None:
        try:
            total = sum(len(c.scenes) for c in self.project.chapters)
            done = 0
            for ch in self.project.chapters:
                for sc in ch.scenes:
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
            self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    """Main IDE-like Studio window for creating MP4 VideoBooks."""

    def __init__(self, workspace_dir: Path) -> None:
        super().__init__()
        self.workspace_dir = workspace_dir
        self.tts_cache_dir = Path(tempfile.gettempdir()) / "videolibro_tts_cache"
        self.tts_cache_dir.mkdir(parents=True, exist_ok=True)

        self.project = VideoBookProject()
        self._sel_chapter: int = 0
        self._sel_scene: int | None = None
        self._updating_ui: bool = False
        self._worker: QThread | None = None

        self._audio_out = QAudioOutput(self)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio_out)

        self.setWindowTitle("VideoLibro Studio — Manoscritti in Cinema per TV")
        self.resize(1420, 900)
        self._apply_dark_theme()
        self._build_toolbar()
        self._build_layout()

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

    def _build_toolbar(self) -> None:
        tb = QToolBar("Principale")
        tb.setMovable(False)
        self.addToolBar(tb)

        btn_import = QPushButton("📄 Importa Manoscritto (.docx / .txt)")
        btn_import.clicked.connect(self.import_manuscript_dialog)
        tb.addWidget(btn_import)

        btn_demo = QPushButton("✨ Carica Demo")
        btn_demo.clicked.connect(self.load_demo_project)
        tb.addWidget(btn_demo)

        btn_open = QPushButton("📂 Apri (.vlibro)")
        btn_open.clicked.connect(self.open_project_dialog)
        tb.addWidget(btn_open)

        btn_save = QPushButton("💾 Salva")
        btn_save.clicked.connect(self.save_project_dialog)
        tb.addWidget(btn_save)

        tb.addSeparator()

        btn_tts_all = QPushButton("🎙️ Genera Voci TTS")
        btn_tts_all.clicked.connect(self.generate_all_tts)
        tb.addWidget(btn_tts_all)

        self.btn_export = QPushButton("🎬 Esporta VideoLibro MP4 (TV)")
        self.btn_export.setObjectName("ExportBtn")
        self.btn_export.clicked.connect(self.export_mp4_dialog)
        tb.addWidget(self.btn_export)

    def _build_layout(self) -> None:
        central = QWidget()
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(6)

        main_splitter = QSplitter(Qt.Orientation.Vertical)
        top_splitter = QSplitter(Qt.Orientation.Horizontal)

        # LEFT: Chapters & Scenes tree
        left_panel = QWidget()
        left_lay = QVBoxLayout(left_panel)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.addWidget(QLabel("📚 Capitoli e Scene del Manoscritto"))

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemSelectionChanged.connect(self._on_tree_selection)
        left_lay.addWidget(self.tree)

        ch_btns = QHBoxLayout()
        b_add_ch = QPushButton("+ Capitolo")
        b_add_ch.clicked.connect(self.add_chapter)
        b_add_sc = QPushButton("+ Scena")
        b_add_sc.clicked.connect(self.add_scene)
        b_del = QPushButton("Elimina")
        b_del.clicked.connect(self.delete_selected)
        ch_btns.addWidget(b_add_ch)
        ch_btns.addWidget(b_add_sc)
        ch_btns.addWidget(b_del)
        left_lay.addLayout(ch_btns)

        # CENTER: Live 16:9 TV Preview
        center_panel = QWidget()
        center_lay = QVBoxLayout(center_panel)
        center_lay.setContentsMargins(6, 0, 6, 0)

        hdr_row = QHBoxLayout()
        self.lbl_preview_info = QLabel("📺 Anteprima TV 16:9")
        self.lbl_preview_info.setStyleSheet("font-weight: bold; color: #E0B46A;")
        btn_listen = QPushButton("🔊 Ascolta Scena (TTS)")
        btn_listen.clicked.connect(self.preview_scene_tts)
        hdr_row.addWidget(self.lbl_preview_info)
        hdr_row.addStretch()
        hdr_row.addWidget(btn_listen)
        center_lay.addLayout(hdr_row)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(640, 360)
        self.preview_label.setStyleSheet("background-color: #0B0D13; border: 1px solid #2A3244; border-radius: 8px;")
        center_lay.addWidget(self.preview_label, 1)

        # RIGHT: Inspector Tabs
        right_tabs = QTabWidget()
        right_tabs.setMinimumWidth(360)

        # Tab 1: Scene & Media
        tab_scene = QWidget()
        ts_lay = QVBoxLayout(tab_scene)
        ts_lay.addWidget(QLabel("Testo proiettato su TV:"))
        self.txt_scene = QTextEdit()
        self.txt_scene.textChanged.connect(self._on_scene_edited)
        ts_lay.addWidget(self.txt_scene, 1)

        scene_form = QFormLayout()
        media_row = QHBoxLayout()
        self.lbl_scene_media = QLineEdit()
        self.lbl_scene_media.setReadOnly(True)
        btn_pick_sc_media = QPushButton("Sfoglia...")
        btn_pick_sc_media.clicked.connect(self.pick_scene_media)
        media_row.addWidget(self.lbl_scene_media)
        media_row.addWidget(btn_pick_sc_media)
        scene_form.addRow("Media Scena:", media_row)

        self.chk_use_ch_media = QCheckBox("Usa media del Capitolo")
        self.chk_use_ch_media.toggled.connect(self._on_scene_edited)
        scene_form.addRow("", self.chk_use_ch_media)

        self.cmb_ken_burns = QComboBox()
        self.cmb_ken_burns.addItems(["zoom_in", "zoom_out", "pan_left", "pan_right", "static"])
        self.cmb_ken_burns.currentTextChanged.connect(self._on_scene_edited)
        scene_form.addRow("Movimento (Ken Burns):", self.cmb_ken_burns)

        self.spin_pause = QDoubleSpinBox()
        self.spin_pause.setRange(0.0, 5.0)
        self.spin_pause.setSingleStep(0.2)
        self.spin_pause.valueChanged.connect(self._on_scene_edited)
        scene_form.addRow("Pausa finale (sec):", self.spin_pause)

        ts_lay.addLayout(scene_form)
        right_tabs.addTab(tab_scene, "Scena & Media")

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
        btn_ch_media = QPushButton("Immagine/Video...")
        btn_ch_media.clicked.connect(self.pick_chapter_media)
        ch_m_row.addWidget(self.edt_ch_media)
        ch_m_row.addWidget(btn_ch_media)
        tc_form.addRow("Sfondo Capitolo:", ch_m_row)

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

        right_tabs.addTab(tab_ch, "Capitolo & Musica")

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
        self.cmb_style.addItems(["Libro Cinematografico", "Sottotitoli Cinema", "Pagina Antica"])
        self.cmb_style.currentTextChanged.connect(self._on_settings_edited)
        tset_form.addRow("Stile Testo TV:", self.cmb_style)

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

        right_tabs.addTab(tab_set, "Voce & Stile TV")

        top_splitter.addWidget(left_panel)
        top_splitter.addWidget(center_panel)
        top_splitter.addWidget(right_tabs)
        top_splitter.setSizes([280, 700, 400])

        # BOTTOM: Multi-track Timeline
        bottom_box = QGroupBox("Timeline VideoLibro (Capitoli • Testo • Media • Audio)")
        bot_lay = QVBoxLayout(bottom_box)
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

        main_splitter.addWidget(top_splitter)
        main_splitter.addWidget(bottom_box)
        main_splitter.setSizes([560, 260])

        root_layout.addWidget(main_splitter, 1)

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
        self.tree.clear()
        for c_idx, ch in enumerate(self.project.chapters):
            ch_item = QTreeWidgetItem([f"📖 {ch.title}"])
            ch_item.setData(0, Qt.ItemDataRole.UserRole, (c_idx, None))
            for s_idx, sc in enumerate(ch.scenes):
                snippet = sc.text.strip().replace("\n", " ")
                if len(snippet) > 32:
                    snippet = snippet[:29] + "..."
                sc_item = QTreeWidgetItem([f"  🎬 {s_idx + 1}. {snippet}"])
                sc_item.setData(0, Qt.ItemDataRole.UserRole, (c_idx, s_idx))
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

        mins, secs = divmod(int(total), 60)
        self.lbl_total_dur.setText(f"Durata Totale: {mins:02d}:{secs:02d}  ({len(entries)} blocchi)")

        selected_entry = None
        for e in entries:
            if e.chapter_index == self._sel_chapter and e.scene_index == self._sel_scene:
                selected_entry = e
                break
        if selected_entry is None and entries:
            selected_entry = entries[0]

        img = render_preview_frame(self.project, selected_entry, (960, 540))
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
        self.edt_ch_title.setText(ch.title)
        self.edt_ch_sub.setText(ch.subtitle)
        self.chk_title_card.setChecked(ch.show_title_card)
        self.edt_ch_media.setText(ch.default_media_path)
        self.edt_ch_audio.setText(ch.bg_audio_path)
        vol_pct = int(round(ch.bg_audio_volume * 100))
        self.sld_ch_vol.setValue(vol_pct)
        self.lbl_ch_vol.setText(f"{vol_pct}%")

        if self._sel_scene is not None and 0 <= self._sel_scene < len(ch.scenes):
            sc = ch.scenes[self._sel_scene]
            self.txt_scene.setEnabled(True)
            self.txt_scene.setPlainText(sc.text)
            self.lbl_scene_media.setText(sc.media_path)
            self.chk_use_ch_media.setChecked(sc.use_chapter_media)
            self.cmb_ken_burns.setCurrentText(sc.ken_burns)
            self.spin_pause.setValue(sc.pause_after_sec)
            self.lbl_preview_info.setText(f"📺 Anteprima TV 16:9 — {ch.title} • Scena {self._sel_scene + 1}")
        else:
            self.txt_scene.setEnabled(False)
            self.txt_scene.setPlainText("")
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
        self._refresh_timeline_and_preview()

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

    def _on_settings_edited(self) -> None:
        if self._updating_ui:
            return
        self.project.title = self.edt_book_title.text()
        self.project.author = self.edt_book_author.text()
        s = self.project.settings
        s.tts_voice = self.cmb_voice.currentData() or "it-IT-DiegoNeural"
        s.tts_engine = self.cmb_tts_engine.currentText()  # type: ignore[assignment]
        s.text_style = self.cmb_style.currentText()  # type: ignore[assignment]
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
        ch = self.project.chapters[self._sel_chapter]
        if self._sel_scene is not None and len(ch.scenes) > 1:
            ch.scenes.pop(self._sel_scene)
            self._sel_scene = max(0, self._sel_scene - 1)
        elif len(self.project.chapters) > 1:
            self.project.chapters.pop(self._sel_chapter)
            self._sel_chapter = max(0, self._sel_chapter - 1)
            self._sel_scene = 0 if self.project.chapters[self._sel_chapter].scenes else None
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
        self._populate_inspector()
        self._refresh_timeline_and_preview()

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
        if ap:
            self._audio_out.setVolume(0.95)
            self._player.setSource(QUrl.fromLocalFile(ap))
            self._player.play()
            self.lbl_status.setText(f"Riproduzione TTS ({dur:.1f}s)...")

    def generate_all_tts(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self.progress_bar.setValue(0)
        worker = TTSBatchWorker(self.project, self.tts_cache_dir)
        worker.progress.connect(lambda p, m: (self.progress_bar.setValue(p), self.lbl_status.setText(m)))
        worker.finished_ok.connect(self._on_tts_batch_done)
        worker.failed.connect(lambda err: QMessageBox.critical(self, "Errore TTS", err))
        self._worker = worker
        worker.start()

    def _on_tts_batch_done(self) -> None:
        self.progress_bar.setValue(100)
        self.lbl_status.setText("Voci TTS generate per tutto il manoscritto!")
        self._refresh_timeline_and_preview()

    def export_mp4_dialog(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        default_out = self.workspace_dir / f"{self.project.title.replace(' ', '_')}.mp4"
        out_path, _ = QFileDialog.getSaveFileName(self, "Esporta VideoLibro MP4", str(default_out), "Video MP4 (*.mp4)")
        if not out_path:
            return

        self.btn_export.setEnabled(False)
        self.progress_bar.setValue(0)
        worker = ExportWorker(self.project, out_path)
        worker.progress.connect(lambda p, m: (self.progress_bar.setValue(p), self.lbl_status.setText(m)))
        worker.finished_ok.connect(self._on_export_done)
        worker.failed.connect(self._on_export_failed)
        self._worker = worker
        worker.start()

    def _on_export_done(self, out_path: str) -> None:
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

    def _on_export_failed(self, err: str) -> None:
        self.btn_export.setEnabled(True)
        self.lbl_status.setText("Errore durante l'esportazione.")
        QMessageBox.critical(self, "Errore Esportazione MP4", err)
