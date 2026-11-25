# 🚀 Guida alla Pubblicazione su GitHub, Build `.exe` e GitHub Pages

Questa guida spiega passo dopo passo come pubblicare **VideoLibro Studio** su GitHub, generare automaticamente il file `.exe` per Windows 11 tramite GitHub Actions e attivare la pagina web di download (GitHub Pages).

---

## 1. Crea il repository su GitHub

1. Accedi a [GitHub](https://github.com) e clicca su **New repository**.
2. Imposta come nome `VideoLibro` (o il nome che preferisci).
3. Lascia **deselezionati** `Add a README file`, `.gitignore` e `license` (sono già presenti nel progetto).
4. Clicca **Create repository**.

---

## 2. Carica il codice dal tuo PC

Apri PowerShell nella cartella del progetto (`f:\PROJECTS\py\VideoLibro`) ed esegui (sostituendo `TUO_UTENTE` con il tuo username GitHub):

```powershell
git init
git add .
git commit -m "Initial release: VideoLibro Studio"
git branch -M main
git remote add origin https://github.com/lucoradev77/VideoLibro.git
git push -u origin main
```

> **Nota:** Il file `.gitignore` esclude automaticamente `.venv/`, `dist/`, `build/`, i file `.mp4`, `.vlibro`, `demo_assets/` e la cartella `LibroWeb/`.

---

## 3. Genera automaticamente il file `.exe` (GitHub Actions)

Il progetto include il workflow [`.github/workflows/release.yml`](.github/workflows/release.yml), che compila `VideoLibroStudio-Windows-x64.exe` su Windows ogni volta che pubblichi un tag `v*`:

```powershell
git tag v1.0.0
git push origin v1.0.0
```

1. Vai su GitHub nella scheda **Actions** del repository per vedere l'avanzamento della compilazione (richiede circa 2-3 minuti).
2. Al termine, troverai il file **`VideoLibroStudio-Windows-x64.exe`** pronto per il download nella sezione **Releases**.

### Compilazione manuale in locale (opzionale)
Se vuoi creare l'`.exe` direttamente sul tuo PC senza aspettare GitHub:

```powershell
.\build_exe.ps1
```
L'eseguibile verrà salvato in `dist\VideoLibroStudio.exe`.

---

## 4. Attiva il sito web di download (GitHub Pages)

Il sito vetrina è già pronto nella cartella [`docs/`](docs/index.html):

1. Su GitHub, apri **Settings** → **Pages**.
2. In **Build and deployment → Source**, scegli **`Deploy from a branch`**.
3. Seleziona il branch **`main`** e la cartella **`/docs`**, poi clicca **Save**.
4. Dopo qualche secondo, il sito sarà online all'indirizzo:
   ```
   https://lucoradev77.github.io/VideoLibro/
   ```

Il pulsante **"Scarica per Windows 11 (.exe)"** presente nella pagina rileva automaticamente il tuo username e il nome del repository e punta all'ultima versione pubblicata nelle **Releases**.

---

## 5. Come pubblicare futuri aggiornamenti

Quando modifichi il codice e vuoi rilasciare una nuova versione:

```powershell
git add .
git commit -m "Descrizione delle novità"
git push

git tag v1.0.1
git push origin v1.0.1
```
GitHub Actions aggiornerà automaticamente la Release con il nuovo `.exe`.
