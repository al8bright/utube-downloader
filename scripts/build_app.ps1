<#
.SYNOPSIS
  Build the Windows installer: PyInstaller backend + FFmpeg + Deno, then the Tauri NSIS bundle.

.DESCRIPTION
  Output: app\src-tauri\target\release\bundle\nsis\YoutubeDownloader_<version>_x64-setup.exe

  The installer holds the app, the Python backend and ffmpeg.exe, so conversion works on
  machines without FFmpeg. ffmpeg.exe alone is enough: MP3/FLAC conversion and MP4 merging
  need no ffprobe.

  yt-dlp is upgraded to the newest release first. YouTube changes often and an old yt-dlp
  starts failing with HTTP 403. The upgraded version is written to backend\uv.lock; commit it.

  FFmpeg is taken from, in order: $env:FFMPEG_DIR, PATH, chocolatey, scoop, winget.
  Anything under 2 MB is skipped: chocolatey's ffmpeg.exe on PATH is a small launcher (shim)
  that only works where chocolatey is installed.

  Deno runs YouTube's signature JavaScript for yt-dlp. Without a JS runtime some videos fail
  or lose formats. Deno is taken from $env:DENO_EXE, PATH, ~\.deno\bin, scoop or winget; if none
  is found, the official Windows build is downloaded from github.com/denoland/deno (checked
  against its published SHA-256) and cached in backend\.tools.

  The licenses of everything shipped (app MIT, FFmpeg GPL with its source pointer, Deno, Python
  packages, Rust crates, JS packages and fonts) are written to backend\licenses in the install
  folder. See THIRD_PARTY_NOTICES.md.

  Needs: uv, pnpm, Rust (stable MSVC), FFmpeg. Run from anywhere.
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Find-FFmpeg {
    $candidates = @()
    if ($env:FFMPEG_DIR) { $candidates += Join-Path $env:FFMPEG_DIR "ffmpeg.exe" }
    $candidates += @(Get-Command ffmpeg.exe -All -ErrorAction SilentlyContinue | ForEach-Object Source)
    $candidates += Join-Path $env:ProgramData "chocolatey\lib\ffmpeg\tools\ffmpeg\bin\ffmpeg.exe"
    $candidates += Join-Path $env:USERPROFILE "scoop\apps\ffmpeg\current\bin\ffmpeg.exe"
    $winget = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    if (Test-Path $winget) {
        $candidates += @(Get-ChildItem $winget -Directory -Filter "Gyan.FFmpeg*" |
            ForEach-Object { Get-ChildItem $_.FullName -Recurse -Filter ffmpeg.exe } | ForEach-Object FullName)
    }
    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c) -and (Get-Item $c).Length -gt 2MB) { return (Get-Item $c).FullName }
    }
    return $null
}

function Find-Deno {
    $candidates = @()
    if ($env:DENO_EXE) { $candidates += $env:DENO_EXE }
    $candidates += @(Get-Command deno.exe -All -ErrorAction SilentlyContinue | ForEach-Object Source)
    $candidates += Join-Path $env:USERPROFILE ".deno\bin\deno.exe"
    $candidates += Join-Path $env:USERPROFILE "scoop\apps\deno\current\deno.exe"
    $winget = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    if (Test-Path $winget) {
        $candidates += @(Get-ChildItem $winget -Directory -Filter "DenoLand.Deno*" |
            ForEach-Object { Get-ChildItem $_.FullName -Recurse -Filter deno.exe } | ForEach-Object FullName)
    }
    $candidates += Join-Path $root "backend\.tools\deno\deno.exe"
    foreach ($c in $candidates) {
        # Skip small launcher shims: the real deno.exe is tens of MB
        if ($c -and (Test-Path $c) -and (Get-Item $c).Length -gt 20MB) { return (Get-Item $c).FullName }
    }
    return $null
}

function Get-Deno {
    $dir = Join-Path $root "backend\.tools\deno"
    New-Item -ItemType Directory -Force $dir | Out-Null
    $zip = Join-Path $dir "deno.zip"
    $url = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"
    Write-Host "Downloading Deno from $url"  # Write-Host: a bare string would become part of the return value
    Invoke-WebRequest $url -OutFile $zip -UseBasicParsing
    $sum = (Invoke-WebRequest "$url.sha256sum" -UseBasicParsing).Content
    if ($sum -is [byte[]]) { $sum = [Text.Encoding]::ASCII.GetString($sum) }
    $want = ([regex]::Match($sum, "[0-9a-fA-F]{64}")).Value.ToLower()
    $got = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
    if (-not $want -or $want -ne $got) { Remove-Item $zip; throw "Deno download checksum mismatch (expected $want, got $got)" }
    Expand-Archive $zip -DestinationPath $dir -Force
    Remove-Item $zip
    return (Join-Path $dir "deno.exe")
}

# FFmpeg is GPL: its license and the build's README (which names the exact source commit) must ship with it.
# gyan.dev / chocolatey / winget builds keep them one level above bin\ffmpeg.exe.
function Find-FFmpegDocs([string]$exe) {
    $dir = Split-Path -Parent $exe
    foreach ($d in @($dir, (Split-Path -Parent $dir))) {
        $lic = Get-ChildItem $d -File -ErrorAction SilentlyContinue | Where-Object Name -match "^(LICENSE|COPYING)" | Select-Object -First 1
        if ($lic) { return @{ License = $lic.FullName; Readme = (Join-Path $d "README.txt") } }
    }
    return $null
}

$ffmpeg = Find-FFmpeg
if (-not $ffmpeg) {
    throw "FFmpeg not found. Install it (winget install Gyan.FFmpeg) or set FFMPEG_DIR to the folder holding ffmpeg.exe."
}
"Bundling FFmpeg from $ffmpeg"
$ffmpegDocs = Find-FFmpegDocs $ffmpeg
if (-not $ffmpegDocs) {
    throw "No LICENSE found next to $ffmpeg. FFmpeg is GPL and its license must ship with it: use a gyan.dev build (winget install Gyan.FFmpeg) or set FFMPEG_DIR to an unpacked release."
}
$deno = Find-Deno
if (-not $deno) { $deno = Get-Deno }
"Bundling Deno from $deno"

Push-Location (Join-Path $root "backend")
try {
    uv lock --upgrade-package yt-dlp
    if ($LASTEXITCODE) { throw "uv lock (yt-dlp upgrade) failed" }
    uv sync
    if ($LASTEXITCODE) { throw "uv sync failed" }
    uv run pyinstaller --noconfirm --clean --distpath dist --workpath build packaging\utube-backend.spec
    if ($LASTEXITCODE) { throw "PyInstaller failed" }
    Copy-Item $ffmpeg ".\dist\utube-backend\ffmpeg.exe" -Force
    Copy-Item $deno ".\dist\utube-backend\deno.exe" -Force

    # Licenses of everything the installer ships (THIRD_PARTY_NOTICES.md explains them)
    $lic = New-Item -ItemType Directory -Force ".\dist\utube-backend\licenses"
    Copy-Item (Join-Path $root "LICENSE") (Join-Path $lic "LICENSE.txt") -Force
    Copy-Item (Join-Path $root "THIRD_PARTY_NOTICES.md") $lic -Force
    Copy-Item $ffmpegDocs.License (Join-Path $lic "FFmpeg-LICENSE.txt") -Force
    if (Test-Path $ffmpegDocs.Readme) { Copy-Item $ffmpegDocs.Readme (Join-Path $lic "FFmpeg-README.txt") -Force }
    Copy-Item (Join-Path $root "licenses\Deno-LICENSE.md") (Join-Path $lic "Deno-LICENSE.txt") -Force
    $collect = Join-Path $root "scripts\collect_licenses.py"
    uv export --no-dev --no-hashes --format requirements-txt | uv run python $collect python (Join-Path $lic "python-packages.txt")
    if ($LASTEXITCODE) { throw "collecting Python package licenses failed" }
    uv run python $collect cargo (Join-Path $root "app\src-tauri") (Join-Path $lic "rust-crates.txt")
    if ($LASTEXITCODE) { throw "collecting Rust crate licenses failed" }
    & .\dist\utube-backend\utube-backend.exe doctor --bundled
    if ($LASTEXITCODE) { throw "the packaged backend is missing yt-dlp, its JS solver, FFmpeg or Deno" }
} finally { Pop-Location }

Push-Location (Join-Path $root "app")
try {
    pnpm install --frozen-lockfile
    if ($LASTEXITCODE) { throw "pnpm install failed" }
    # needs node_modules, so it runs here rather than with the other licenses
    $jsLicenses = Join-Path $root "backend\dist\utube-backend\licenses\js-packages.txt"
    uv run --project (Join-Path $root "backend") python (Join-Path $root "scripts\collect_licenses.py") npm . $jsLicenses
    if ($LASTEXITCODE) { throw "collecting JavaScript package licenses failed" }
    pnpm tauri build
    if ($LASTEXITCODE) { throw "tauri build failed" }
} finally { Pop-Location }

Get-ChildItem (Join-Path $root "app\src-tauri\target\release\bundle\nsis\*.exe") | ForEach-Object {
    "{0}  {1:N1} MB" -f $_.FullName, ($_.Length / 1MB)
}
