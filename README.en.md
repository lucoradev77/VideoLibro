# 🎬 VideoLibro Studio

**🌐 Language / Lingua:** [Italiano](README.md) · **English** · **🚀 Website & Download:** [lucoradev77.github.io/VideoLibro](https://lucoradev77.github.io/VideoLibro/)

> **Turn your manuscripts (`.docx`, `.txt`, `.md`) into cinematic MP4 VideoBooks.**
> *Read, listen, and watch your stories directly on your TV.*

[![License: MIT](https://img.shields.io/badge/License-MIT-E0B46A.svg)](LICENSE)
[![Windows 11](https://img.shields.io/badge/Platform-Windows%2011-0078D6.svg?logo=windows11)](#)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB.svg?logo=python)](#)
[![Download EXE](https://img.shields.io/badge/Download-Windows%20.exe-success.svg)](https://github.com/lucoradev77/VideoLibro/releases/latest)

---

## 👋 Why VideoLibro Studio exists

Hi, I'm [**Luca Corallo**](mailto:lucoradev@outlook.it).

For some years now I've been passionate about manuscripts. Today we have PDFs, EPUBs, and audiobooks. One day I asked myself: *when I watch a movie, it's really a written story brought to life... so why don't we invent **VideoBooks**?*

That idea led to **VideoLibro Studio**: an open-source Windows 11 application designed to import a manuscript (such as a Word `.docx` file), organize it into chapters, enrich it on a visual timeline with images, video clips, background music, and neural TTS narration, and export a ready-to-watch **Full HD MP4** file for your TV.

If you'd like to use it, improve it, or simply explore the code, you're very welcome. 🎬📖

---

## ✨ Key Features

- **Smart Word (`.docx`) & Text (`.txt`, `.md`) Import**: automatically detects chapters from headings or lets you split and organize them manually.
- **Multi-Track Timeline**: visually manage **Chapters**, **Scenes/Text**, **Media (Images/Video)**, and **Audio/Background Music**.
- **Live 16:9 TV Preview** with 3 visual styles:
  - *Libro Cinematografico* (dark frosted-glass card + reading progress bar)
  - *Sottotitoli Cinema* (crisp movie-style subtitles)
  - *Pagina Antica* (warm parchment card with serif typography)
- **Neural TTS (`edge-tts`) + Offline Fallback**: natural voices with automatic scene duration sync, plus offline Windows SAPI5 fallback.
- **Visual & Audio Direction**: **Ken Burns** motion on images (`zoom_in`, `zoom_out`, `pan_left`, `pan_right`), looping background video clips, per-chapter background music with **volume slider**, and automatic **Auto-Ducking** during narration.
- **Full HD MP4 Export (H.264 / AAC)**: ready for any Smart TV, USB drive, Plex, or YouTube.
- **Saveable Projects (`.vlibro`)**: save your timeline and come back to edit anytime.

---

## 📥 Quick Download (Windows 11)

You can download the standalone pre-built executable (`VideoLibroStudio-Windows-x64.exe`, no installation required) from the [**Releases**](https://github.com/lucoradev77/VideoLibro/releases/latest) page or from the [**project website**](https://lucoradev77.github.io/VideoLibro/).

---

## 🚀 Running from Source

```powershell
# Clone the repository
git clone https://github.com/lucoradev77/VideoLibro.git
cd VideoLibro

# Run with uv (automatically sets up Python 3.12 and dependencies)
uv run python main.py
```

### 📦 Building the `.exe` locally

```powershell
.\build_exe.ps1
```
The executable will be created at `dist\VideoLibroStudio.exe`.

---

## 📄 License

Distributed under the **MIT** License. See [LICENSE](LICENSE) for details.
