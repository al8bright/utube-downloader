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
REM yt-dlp is the one dependency that goes stale fast. YouTube changes its
REM signature scheme every few weeks and an old copy fails with HTTP 403,
REM so every release build picks up the newest version.
echo       Updating yt-dlp to the newest release...
"%VENV_PY%" -m pip install -U yt-dlp --disable-pip-version-check
if errorlevel 1 goto :pip_failed

REM ---------------------------------------------------
REM Locate FFmpeg to bundle. Without it the app downloads fine but every
REM conversion fails on machines that do not have FFmpeg installed.
REM ---------------------------------------------------
REM Set FFMPEG_DIR to override. Otherwise: PATH first, then the usual
REM install folders. Chocolatey and Scoop put a ~400KB launcher stub on PATH,
REM and bundling that stub ships a launcher instead of FFmpeg, so anything
REM under 2MB is rejected and the search continues.
set "FFMPEG_EXE="
if defined FFMPEG_DIR call :pick_ffmpeg "%FFMPEG_DIR%\ffmpeg.exe"
if not defined FFMPEG_EXE for /f "delims=" %%I in ('where ffmpeg 2^>nul') do call :pick_ffmpeg "%%I"
if not defined FFMPEG_EXE call :pick_ffmpeg "%ProgramData%\chocolatey\lib\ffmpeg\tools\ffmpeg\bin\ffmpeg.exe"
if not defined FFMPEG_EXE call :pick_ffmpeg "%USERPROFILE%\scoop\apps\ffmpeg\current\bin\ffmpeg.exe"
if not defined FFMPEG_EXE for /d %%D in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*") do (
    for /r "%%D" %%F in (ffmpeg.exe) do call :pick_ffmpeg "%%F"
)
if not defined FFMPEG_EXE goto :no_ffmpeg

REM ffmpeg.exe alone is enough for this app: MP3/FLAC conversion and MP4
REM merging all work without ffprobe, and leaving it out keeps the exe ~35MB
REM smaller. (Verified by downloading in all three formats with ffmpeg only.)
for %%I in ("%FFMPEG_EXE%") do set "FFMPEG_BIN=%%~dpI"
set "FFMPEG_ARGS=--add-binary "%FFMPEG_EXE%;.""
echo       Bundling FFmpeg from %FFMPEG_BIN%

echo       Build environment ready.
echo [2/3] Building single executable with PyInstaller...
echo       This may take 1-2 minutes. Please wait...
echo.

"%VENV_PY%" -m PyInstaller --noconfirm --onefile --windowed ^
    --name "YoutubeDownloader" ^
    --icon "youtube_icon.ico" ^
    --add-data ".venv\Lib\site-packages\customtkinter;customtkinter" ^
    --add-data "youtube_icon.ico;." ^
    %FFMPEG_ARGS% ^
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
:no_ffmpeg
echo.
echo [ERROR] No usable FFmpeg was found, so it cannot be bundled.
echo         Install it first, then run this script again:
echo             winget install Gyan.FFmpeg
echo         If it is installed elsewhere, point this script at it:
echo             set FFMPEG_DIR=C:\path\to\ffmpeg\bin
echo         (The exe carries FFmpeg; users should not have to install it.)
echo.
pause
exit /b 1

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

REM ---------------------------------------------------
REM Accept a candidate FFmpeg path only if it is the real binary.
REM Chocolatey/Scoop launcher stubs are a few hundred KB; FFmpeg is ~100MB.
REM ---------------------------------------------------
:pick_ffmpeg
if defined FFMPEG_EXE exit /b 0
if not exist "%~1" exit /b 0
if %~z1 LSS 2000000 exit /b 0
set "FFMPEG_EXE=%~1"
exit /b 0
