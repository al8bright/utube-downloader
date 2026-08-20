@echo off
setlocal
cd /d "%~dp0"

echo ===================================================
echo   YouTube Music Downloader Launcher
echo ===================================================
echo.

set "VENV_PY=.venv\Scripts\python.exe"

REM ---------------------------------------------------
REM [1/4] Check Python installation
REM ---------------------------------------------------
echo [1/4] Checking Python installation...
where python >nul 2>&1
if errorlevel 1 goto :no_python
python -c "import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)" >nul 2>&1
if errorlevel 1 goto :old_python
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo       Found %%v

REM ---------------------------------------------------
REM [2/4] Create virtual environment if missing
REM ---------------------------------------------------
echo [2/4] Checking virtual environment...
if exist "%VENV_PY%" goto :venv_ready

echo       No virtual environment found. Creating .venv ...
if exist ".venv" rmdir /s /q ".venv"
python -m venv .venv
if errorlevel 1 goto :venv_failed
if not exist "%VENV_PY%" goto :venv_failed
echo       Virtual environment created.
set "NEED_INSTALL=1"
goto :install_deps

:venv_ready
echo       Virtual environment found.

REM ---------------------------------------------------
REM [3/4] Install dependencies only when needed
REM ---------------------------------------------------
:install_deps
echo [3/4] Checking dependencies...
"%VENV_PY%" -c "import customtkinter, yt_dlp, PIL" >nul 2>&1
if not errorlevel 1 goto :deps_ready

echo       Missing packages detected. Installing from requirements.txt ...
echo       This may take a minute on first run. Please wait...
echo.
"%VENV_PY%" -m pip install --upgrade pip --quiet --disable-pip-version-check
"%VENV_PY%" -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 goto :pip_failed

"%VENV_PY%" -c "import customtkinter, yt_dlp, PIL" >nul 2>&1
if errorlevel 1 goto :pip_failed
echo.
echo       Dependencies installed successfully.
goto :check_ffmpeg

:deps_ready
echo       All dependencies are already installed.

REM ---------------------------------------------------
REM [4/4] Check FFmpeg, then launch
REM ---------------------------------------------------
:check_ffmpeg
echo [4/4] Checking FFmpeg...
where ffmpeg >nul 2>&1
if errorlevel 1 goto :no_ffmpeg
echo       FFmpeg found.
goto :launch

:no_ffmpeg
echo.
echo [WARNING] FFmpeg was not found in PATH.
echo           Downloads will work, but MP3 / FLAC conversion will fail.
echo           Install it with this command, then reopen this window:
echo.
echo               winget install Gyan.FFmpeg
echo.
echo           Press any key to continue anyway, or close this window to abort.
pause >nul

:launch
echo.
echo ===================================================
echo   Launching YouTube Music Downloader...
echo ===================================================
echo.
"%VENV_PY%" gui_app.py
if errorlevel 1 goto :app_failed
exit /b 0

REM ---------------------------------------------------
REM Error handlers
REM ---------------------------------------------------
:no_python
echo.
echo [ERROR] Python was not found in PATH.
echo         Download Python 3.8 or newer from:
echo             https://www.python.org/downloads/
echo         During installation, be sure to check "Add Python to PATH".
echo.
pause
exit /b 1

:old_python
echo.
echo [ERROR] Your Python version is too old. Python 3.8 or newer is required.
python --version
echo         Download the latest version from https://www.python.org/downloads/
echo.
pause
exit /b 1

:venv_failed
echo.
echo [ERROR] Failed to create the virtual environment.
echo         Try running this command manually to see the full error:
echo             python -m venv .venv
echo.
pause
exit /b 1

:pip_failed
echo.
echo [ERROR] Dependency installation failed.
echo         Check your internet connection and try again.
echo         If the problem persists, delete the .venv folder and rerun this script.
echo.
pause
exit /b 1

:app_failed
echo.
echo [ERROR] The program terminated unexpectedly.
echo         See the error message above for details.
echo.
pause
exit /b 1
