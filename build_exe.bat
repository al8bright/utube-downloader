@echo off
setlocal
cd /d "%~dp0"

echo ===================================================
echo   YouTube Music Downloader - Build Executable
echo ===================================================
echo.

set "VENV_PY=.venv\Scripts\python.exe"

REM ---------------------------------------------------
REM [1/3] Prepare build environment
REM ---------------------------------------------------
echo [1/3] Preparing build environment...
if exist "%VENV_PY%" goto :check_pyinstaller

echo       No virtual environment found. Run run_app.bat once to set it up.
echo       Creating it now instead...
where python >nul 2>&1
if errorlevel 1 goto :no_python
python -m venv .venv
if errorlevel 1 goto :venv_failed
"%VENV_PY%" -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 goto :pip_failed

:check_pyinstaller
"%VENV_PY%" -c "import PyInstaller" >nul 2>&1
if not errorlevel 1 goto :do_build
echo       Installing PyInstaller...
"%VENV_PY%" -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 goto :pip_failed

REM ---------------------------------------------------
REM [2/3] Build
REM ---------------------------------------------------
:do_build
echo       Build environment ready.
echo [2/3] Building single executable with PyInstaller...
echo       This may take 1-2 minutes. Please wait...
echo.

"%VENV_PY%" -m PyInstaller --noconfirm --onefile --windowed ^
    --name "YoutubeDownloader" ^
    --icon "youtube_icon.ico" ^
    --add-data ".venv\Lib\site-packages\customtkinter;customtkinter" ^
    --add-data "youtube_icon.ico;." ^
    gui_app.py

if errorlevel 1 goto :build_failed
if not exist "dist\YoutubeDownloader.exe" goto :build_failed

REM ---------------------------------------------------
REM [3/3] Report
REM ---------------------------------------------------
echo [3/3] Verifying output...
echo.
echo ===================================================
echo   Build Successful!
echo   Output: %~dp0dist\YoutubeDownloader.exe
echo ===================================================
echo.
echo   NOTE: FFmpeg is NOT bundled inside the executable.
echo         The target machine still needs FFmpeg in PATH
echo         for MP3 / FLAC conversion:
echo             winget install Gyan.FFmpeg
echo.
pause
exit /b 0

REM ---------------------------------------------------
REM Error handlers
REM ---------------------------------------------------
:no_python
echo.
echo [ERROR] Python was not found in PATH.
echo         Install Python 3.8+ from https://www.python.org/downloads/
echo.
pause
exit /b 1

:venv_failed
echo.
echo [ERROR] Failed to create the virtual environment.
echo.
pause
exit /b 1

:pip_failed
echo.
echo [ERROR] Dependency installation failed. Check your internet connection.
echo.
pause
exit /b 1

:build_failed
echo.
echo [ERROR] Build failed! See the PyInstaller output above for details.
echo.
pause
exit /b 1
