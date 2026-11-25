"""Lightweight Italiano / English localization dictionary for VideoLibro Studio."""

from __future__ import annotations

TRANSLATIONS: dict[str, dict[str, str]] = {
    "it": {
        "window_title": "VideoLibro Studio — Manoscritti in Cinema per TV",
        "tb_import": "📄 Importa Manoscritto (.docx / .txt)",
        "tb_demo": "✨ Carica Demo",
        "tb_open": "📂 Apri (.vlibro)",
        "tb_save": "💾 Salva",
        "tb_tts_all": "🎙️ Genera Voci TTS",
        "tb_export": "🎬 Esporta VideoLibro MP4 (TV)",
        "tb_help": "❓ Guida",
        "left_header": "📚 Capitoli e Scene del Manoscritto",
        "btn_add_ch": "+ Capitolo",
        "btn_add_sc": "+ Scena",
        "btn_del": "Elimina",
        "preview_hdr": "📺 Anteprima TV 16:9",
        "preview_scene": "📺 Anteprima TV 16:9 — {ch} • Scena {num}",
        "preview_cover": "📺 Anteprima TV 16:9 — Copertina: {ch}",
        "btn_test_play": "▶ Test Completo",
        "btn_test_stop": "⏹ Stop",
        "btn_listen": "🔊 Ascolta Scena (TTS)",
        "tab_scene": "Scena & Media",
        "tab_chapter": "Capitolo & Musica",
        "tab_settings": "Voce & Stile TV",
        "lbl_scene_text": "Testo proiettato su TV:",
        "lbl_scene_media": "Media Scena:",
        "btn_browse": "Sfoglia...",
        "chk_use_ch_media": "Usa media del Capitolo",
        "btn_extend_media": "Estendi alle successive",
        "tip_extend_media": "Applica l'immagine/video di questa scena anche a tutte le scene successive del capitolo",
        "lbl_ken_burns": "Movimento (Ken Burns):",
        "lbl_pause": "Pausa finale (sec):",
        "lbl_ch_title": "Titolo Capitolo:",
        "lbl_ch_sub": "Sottotitolo:",
        "chk_title_card": "Mostra copertina capitolo",
        "lbl_ch_media": "Sfondo Capitolo:",
        "btn_ch_media": "Immagine/Video...",
        "lbl_preset_bg": "Sfondo Predefinito:",
        "btn_apply_bg_all": "Applica a tutto il libro",
        "lbl_ch_audio": "Musica Sottofondo:",
        "btn_ch_audio": "Audio/Musica...",
        "lbl_ch_vol": "Volume Sottofondo:",
        "lbl_book_title": "Titolo Libro:",
        "lbl_book_author": "Autore:",
        "lbl_voice": "Voce Narrante:",
        "lbl_tts_engine": "Motore TTS:",
        "lbl_tv_style": "Stile Testo TV:",
        "lbl_font_family": "Carattere (Font):",
        "lbl_font_variant": "Stile Carattere:",
        "lbl_font_size": "Dimensione Testo:",
        "lbl_res": "Risoluzione MP4:",
        "chk_ducking": "Auto-Ducking (abbassa musica quando parla)",
        "tl_group": "Timeline VideoLibro (Capitoli • Testo • Media • Audio)",
        "tl_dur": "Durata Totale: {mm:02d}:{ss:02d}  ({n} blocchi)",
        "tl_track_chapters": "CAPITOLI",
        "tl_track_scenes": "SCENE / TESTO",
        "tl_track_media": "MEDIA (IMG/VID)",
        "tl_track_audio": "AUDIO / BGM",
        "ready": "Pronto.",
        "demo_loaded": "Progetto demo 'Il Manoscritto di Pietra' caricato.",
        "help_title": "Guida d'uso — VideoLibro Studio",
        "help_close": "Chiudi",
        "help_html": """
            <div style="font-family:'Segoe UI'; color:#E8ECF4; line-height:1.55;">
              <h2 style="color:#E0B46A; margin-bottom:4px;">🎬 VideoLibro Studio</h2>
              <p style="margin-top:0; color:#D8C39A;">
                <b>Ideato da <a href="mailto:lucoradev@outlook.it" style="color:#E0B46A;">Luca Corallo</a></b> — Da una passione per i manoscritti, per trasformare le storie scritte in VideoLibri da leggere, ascoltare e guardare in TV come un film.
              </p>
              <hr style="border:1px solid #2A3244;" />
              <h3 style="color:#E0B46A;">Guida rapida d'uso</h3>
              <ol>
                <li><b>Importa un manoscritto</b>: clicca su <i>Importa Manoscritto (.docx / .txt)</i>. Puoi far rilevare i capitoli automaticamente dai titoli oppure gestirli a mano con <i>+ Capitolo</i> e <i>+ Scena</i>.</li>
                <li><b>Scegli sfondi e musica</b>: nella scheda <i>Capitolo &amp; Musica</i> imposta lo sfondo principale e la musica di sottofondo con il relativo volume. In <i>Scena &amp; Media</i> puoi personalizzare una singola scena e usare <b>Estendi alle successive</b> per applicare la stessa immagine/video alle scene seguenti.</li>
                <li><b>Personalizza voce e stile TV</b>: nella scheda <i>Voce &amp; Stile TV</i> scegli la voce narrante TTS, lo stile, il <b>carattere</b>, lo <b>stile</b> e la dimensione del testo.</li>
                <li><b>Testa senza attendere il rendering</b>: clicca <b>▶ Test Completo</b> per vedere l'anteprima animata dall'inizio con voce e musica direttamente nella finestra TV.</li>
                <li><b>Esporta per la TV</b>: clicca <b>🎬 Esporta VideoLibro MP4 (TV)</b> per generare il file MP4 Full HD pronto per chiavetta USB o Smart TV.</li>
              </ol>
            </div>
        """,
    },
    "en": {
        "window_title": "VideoLibro Studio — Manuscripts to Cinema for TV",
        "tb_import": "📄 Import Manuscript (.docx / .txt)",
        "tb_demo": "✨ Load Demo",
        "tb_open": "📂 Open (.vlibro)",
        "tb_save": "💾 Save",
        "tb_tts_all": "🎙️ Generate All TTS",
        "tb_export": "🎬 Export VideoBook MP4 (TV)",
        "tb_help": "❓ Help",
        "left_header": "📚 Manuscript Chapters & Scenes",
        "btn_add_ch": "+ Chapter",
        "btn_add_sc": "+ Scene",
        "btn_del": "Delete",
        "preview_hdr": "📺 TV 16:9 Live Preview",
        "preview_scene": "📺 TV 16:9 Preview — {ch} • Scene {num}",
        "preview_cover": "📺 TV 16:9 Preview — Cover: {ch}",
        "btn_test_play": "▶ Full Test",
        "btn_test_stop": "⏹ Stop",
        "btn_listen": "🔊 Listen Scene (TTS)",
        "tab_scene": "Scene & Media",
        "tab_chapter": "Chapter & Music",
        "tab_settings": "Voice & TV Style",
        "lbl_scene_text": "Text projected on TV:",
        "lbl_scene_media": "Scene Media:",
        "btn_browse": "Browse...",
        "chk_use_ch_media": "Use Chapter media",
        "btn_extend_media": "Extend to next scenes",
        "tip_extend_media": "Apply this scene's image/video to all following scenes in this chapter",
        "lbl_ken_burns": "Motion (Ken Burns):",
        "lbl_pause": "End pause (sec):",
        "lbl_ch_title": "Chapter Title:",
        "lbl_ch_sub": "Subtitle:",
        "chk_title_card": "Show chapter cover card",
        "lbl_ch_media": "Chapter Background:",
        "btn_ch_media": "Image/Video...",
        "lbl_preset_bg": "Preset Background:",
        "btn_apply_bg_all": "Apply to whole book",
        "lbl_ch_audio": "Background Music:",
        "btn_ch_audio": "Audio/Music...",
        "lbl_ch_vol": "Background Volume:",
        "lbl_book_title": "Book Title:",
        "lbl_book_author": "Author:",
        "lbl_voice": "Narrator Voice:",
        "lbl_tts_engine": "TTS Engine:",
        "lbl_tv_style": "TV Text Style:",
        "lbl_font_family": "Font Family:",
        "lbl_font_variant": "Font Style:",
        "lbl_font_size": "Text Size:",
        "lbl_res": "MP4 Resolution:",
        "chk_ducking": "Auto-Ducking (lower music while speaking)",
        "tl_group": "VideoBook Timeline (Chapters • Text • Media • Audio)",
        "tl_dur": "Total Duration: {mm:02d}:{ss:02d}  ({n} blocks)",
        "tl_track_chapters": "CHAPTERS",
        "tl_track_scenes": "SCENES / TEXT",
        "tl_track_media": "MEDIA (IMG/VID)",
        "tl_track_audio": "AUDIO / BGM",
        "ready": "Ready.",
        "demo_loaded": "Demo project 'Il Manoscritto di Pietra' loaded.",
        "help_title": "User Guide — VideoLibro Studio",
        "help_close": "Close",
        "help_html": """
            <div style="font-family:'Segoe UI'; color:#E8ECF4; line-height:1.55;">
              <h2 style="color:#E0B46A; margin-bottom:4px;">🎬 VideoLibro Studio</h2>
              <p style="margin-top:0; color:#D8C39A;">
                <b>Created by <a href="mailto:lucoradev@outlook.it" style="color:#E0B46A;">Luca Corallo</a></b> — Born from a passion for manuscripts, to turn written stories into VideoBooks you can read, listen to, and watch on TV like a movie.
              </p>
              <hr style="border:1px solid #2A3244;" />
              <h3 style="color:#E0B46A;">Quick User Guide</h3>
              <ol>
                <li><b>Import a manuscript</b>: click <i>Import Manuscript (.docx / .txt)</i>. Chapters can be detected automatically from headings or managed manually with <i>+ Chapter</i> and <i>+ Scene</i>.</li>
                <li><b>Pick backgrounds &amp; music</b>: in <i>Chapter &amp; Music</i>, set the default background and music volume. In <i>Scene &amp; Media</i>, customize any scene and click <b>Extend to next scenes</b> to propagate its media forward.</li>
                <li><b>Customize voice &amp; TV style</b>: in <i>Voice &amp; TV Style</i>, pick the TTS voice, visual style, <b>font family</b>, <b>font style</b>, and text size.</li>
                <li><b>Test without rendering</b>: click <b>▶ Full Test</b> to preview the entire VideoBook from the start with narration and music right inside the TV window.</li>
                <li><b>Export for TV</b>: click <b>🎬 Export VideoBook MP4 (TV)</b> to render a Full HD MP4 file ready for USB drives or Smart TVs.</li>
              </ol>
            </div>
        """,
    },
}


def tr(lang: str, key: str, **kwargs) -> str:
    """Return translated string for 'it' or 'en' with optional format args."""
    table = TRANSLATIONS.get(lang, TRANSLATIONS["it"])
    text = table.get(key, TRANSLATIONS["it"].get(key, key))
    return text.format(**kwargs) if kwargs else text
