# 🎬 VideoLibro Studio

**🌐 Lingua / Language:** **Italiano** · [English](README.en.md) · **🚀 Sito & Download:** [lucoradev77.github.io/VideoLibro](https://lucoradev77.github.io/VideoLibro/)

> **Trasforma i tuoi manoscritti (`.docx`, `.txt`, `.md`) in VideoLibri cinematografici MP4.**
> *Leggi, ascolta e guarda le tue storie direttamente sulla TV di casa.*

[![Licenza: MIT](https://img.shields.io/badge/Licenza-MIT-E0B46A.svg)](LICENSE)
[![Windows 11](https://img.shields.io/badge/Piattaforma-Windows%2011-0078D6.svg?logo=windows11)](#)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB.svg?logo=python)](#)
[![Download EXE](https://img.shields.io/badge/Download-Windows%20.exe-success.svg)](https://github.com/lucoradev77/VideoLibro/releases/latest)

---

## 👋 Perché nasce VideoLibro Studio

Ciao, mi chiamo [**Luca Corallo**](mailto:lucoradev@outlook.it).

Da qualche anno sono appassionato di manoscritti. Oggi esistono i libri in PDF, gli EPUB e gli audiolibri. Un giorno però mi sono chiesto: *se guardo un film che di fatto è una storia scritta... perché non inventiamo i **VideoLibri**?*

Da questa idea è nato **VideoLibro Studio**: uno strumento open source per Windows 11 pensato per prendere un manoscritto (come un file Word `.docx`), suddividerlo in capitoli, arricchirlo su una timeline con immagini, clip video, musica di sottofondo e voce narrante TTS, ed esportare un vero file **MP4 Full HD** da guardare e ascoltare comodamente in TV.

Se ti va di usarlo, migliorarlo o semplicemente curiosare nel codice, sei il benvenuto. 🎬📖

---

## ✨ Funzionalità principali

- **Importazione intelligente da Word (`.docx`) e testo (`.txt`, `.md`)**: rileva automaticamente i capitoli dai titoli oppure ti permette di crearli e dividerli manualmente.
- **Timeline Multi-Traccia**: visualizza e gestisci **Capitoli**, **Scene/Testo**, **Media (Immagini/Video)** e **Audio/Musica di sottofondo**.
- **Anteprima TV 16:9 Live** con 3 stili visivi:
  - *Libro Cinematografico* (pannello vetro scuro + barra di avanzamento lettura)
  - *Sottotitoli Cinema* (testo stile film ad alta leggibilità)
  - *Pagina Antica* (effetto pergamena calda con font serif)
- **Voci Neurali TTS (`edge-tts`) + Fallback Offline**: narratore italiano naturale (*Diego*, *Elsa*, *Isabella*, *Giuseppe*) con sincronizzazione automatica della durata delle scene, più supporto offline Windows SAPI5.
- **Regia Visiva & Audio**: effetto **Ken Burns** su immagini (`zoom_in`, `zoom_out`, `pan_left`, `pan_right`), supporto clip video di sfondo, musica di sottofondo con **volume regolabile** e **Auto-Ducking** automatico.
- **Export MP4 Full HD (H.264 / AAC)**: compatibile con qualsiasi Smart TV, chiavetta USB, Plex o YouTube.
- **Progetti Salvabili (`.vlibro`)**: salva l'intera timeline e riapri il progetto quando vuoi.

---

## 📥 Download rapido (Windows 11)

Puoi scaricare l'eseguibile già compilato (`VideoLibroStudio-Windows-x64.exe`, nessuna installazione richiesta) dalla pagina [**Releases**](https://github.com/lucoradev77/VideoLibro/releases/latest) oppure dal [**sito web del progetto**](https://lucoradev77.github.io/VideoLibro/).

---

## 🚀 Avvio per sviluppatori

```powershell
# Clona il repository
git clone https://github.com/lucoradev77/VideoLibro.git
cd VideoLibro

# Avvia con uv (installa automaticamente Python 3.12 e dipendenze)
uv run python main.py
```

### 📦 Compilazione locale in `.exe`

```powershell
.\build_exe.ps1
```
L'eseguibile verrà generato in `dist\VideoLibroStudio.exe`.

---

## 📄 Licenza

Distribuito sotto licenza **MIT**. Vedi [LICENSE](LICENSE) per i dettagli.
