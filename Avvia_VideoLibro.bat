@echo off
setlocal
cd /d "%~dp0"

set "VENV_PY=%~dp0.venv\Scripts\python.exe"
if not exist "%VENV_PY%" goto find_python
"%VENV_PY%" -c "import sys; raise SystemExit(sys.version_info < (3, 12))" >nul 2>&1
if errorlevel 1 goto find_python
"%VENV_PY%" -c "import sys; raise SystemExit(sys.version_info >= (3, 14))" >nul 2>&1
if errorlevel 1 goto find_python
"%VENV_PY%" -c "import PySide6.QtMultimedia, PIL.ImageQt, docx, edge_tts, imageio_ffmpeg, pyttsx3, kokoro_onnx, onnxruntime, httpx, numpy" >nul 2>&1
if errorlevel 1 goto install_dependencies
goto run_app

:find_python
set "PYTHON_CMD=py -3.12"
%PYTHON_CMD% -c "import sys; raise SystemExit(sys.version_info < (3, 12) or sys.version_info >= (3, 14))" >nul 2>&1
if not errorlevel 1 goto create_venv
for /d %%D in ("%APPDATA%\uv\python\cpython-3.12*") do (
    if exist "%%~D\python.exe" (
        set "PYTHON_CMD=""%%~D\python.exe"""
        goto create_venv
    )
)
set "PYTHON_CMD=py -3.13"
%PYTHON_CMD% -c "import sys; raise SystemExit(sys.version_info < (3, 12) or sys.version_info >= (3, 14))" >nul 2>&1
if not errorlevel 1 goto create_venv
for /d %%D in ("%APPDATA%\uv\python\cpython-3.13*") do (
    if exist "%%~D\python.exe" (
        set "PYTHON_CMD=""%%~D\python.exe"""
        goto create_venv
    )
)
set "PYTHON_CMD=py -3"
%PYTHON_CMD% -c "import sys; raise SystemExit(sys.version_info < (3, 12) or sys.version_info >= (3, 14))" >nul 2>&1
if not errorlevel 1 goto create_venv
set "PYTHON_CMD=python"
%PYTHON_CMD% -c "import sys; raise SystemExit(sys.version_info < (3, 12) or sys.version_info >= (3, 14))" >nul 2>&1
if errorlevel 1 goto no_python

:create_venv
echo Creating the project virtual environment...
%PYTHON_CMD% -m venv --clear "%~dp0.venv"
if errorlevel 1 goto setup_failed

:install_dependencies
echo Installing project dependencies...
"%VENV_PY%" -m pip install -e "%~dp0."
if errorlevel 1 goto setup_failed

:run_app
"%VENV_PY%" "%~dp0main.py"
set "APP_EXIT=%ERRORLEVEL%"
goto finish

:no_python
echo Python 3.12 or 3.13 is required. Install a supported version and try again.
set "APP_EXIT=1"
goto finish

:setup_failed
echo Setup failed. Check the error above and try again.
set "APP_EXIT=1"

:finish
pause
exit /b %APP_EXIT%
