# Build standalone Windows 11 executable for VideoLibro Studio
$ErrorActionPreference = "Stop"

Write-Host "Installazione PyInstaller nell'ambiente uv..." -ForegroundColor Cyan
uv add --dev pyinstaller

Write-Host "Compilazione VideoLibroStudio.exe..." -ForegroundColor Cyan
uv run pyinstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "VideoLibroStudio" `
    --icon "assets/videolibro.ico" `
    --add-data "assets;assets" `
    --collect-all imageio_ffmpeg `
    --collect-all edge_tts `
    --hidden-import pyttsx3.drivers `
    --hidden-import pyttsx3.drivers.sapi5 `
    main.py

Write-Host "Build completata! File pronto in: dist\VideoLibroStudio.exe" -ForegroundColor Green
