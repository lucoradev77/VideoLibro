# Build standalone Windows 11 executable for VideoLibro Studio
$ErrorActionPreference = "Stop"

Write-Host "Installazione PyInstaller nell'ambiente uv..." -ForegroundColor Cyan
uv add --dev pyinstaller

Write-Host "Compilazione VideoLibroStudio.exe..." -ForegroundColor Cyan
$pythonDllDir = (uv run python -c "import sys; print(sys.base_prefix + r'\DLLs')").Trim()
$opensslDlls = @(
    "$pythonDllDir\libcrypto-3-x64.dll",
    "$pythonDllDir\libssl-3-x64.dll"
)
foreach ($dll in $opensslDlls) {
    if (-not (Test-Path $dll)) {
        throw "DLL OpenSSL richiesta non trovata: $dll"
    }
}

uv run pyinstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "VideoLibroStudio" `
    --icon "assets/videolibro.ico" `
    --add-data "assets;assets" `
    --add-binary "$($opensslDlls[0]);." `
    --add-binary "$($opensslDlls[1]);." `
    --collect-all imageio_ffmpeg `
    --collect-all edge_tts `
    --hidden-import pyttsx3.drivers `
    --hidden-import pyttsx3.drivers.sapi5 `
    --runtime-hook rthook_windows_dll_path.py `
    main.py

Write-Host "Build completata! File pronto in: dist\VideoLibroStudio.exe" -ForegroundColor Green
