"""명령줄 진입점: `utube serve`, `utube doctor`."""

from __future__ import annotations

import argparse
import sys

from utube import __version__


def cmd_doctor(args: argparse.Namespace) -> int:
    """설치 파일을 만들기 전에 꼭 필요한 것이 들어 있는지 확인한다."""
    import subprocess

    from utube.core.ytdl import bundled_ffmpeg_dir, bundled_tool, detect_js_runtimes, ffmpeg_path, ytdlp_version

    ok = True

    def row(name: str, good: bool, detail: str) -> None:
        nonlocal ok
        ok = ok and good
        print(f"[{'OK' if good else 'NO'}] {name:<10} {detail}")

    version = ytdlp_version()
    row("yt-dlp", version != "?", version)
    try:
        import yt_dlp_ejs  # noqa: F401 - 서명 계산 스크립트. 없으면 일부 영상이 403 으로 막힌다
        row("yt-dlp-ejs", True, "present")
    except ImportError:
        row("yt-dlp-ejs", False, "missing")
    ff = ffmpeg_path()
    if args.bundled:
        row("ffmpeg", bool(bundled_ffmpeg_dir()), ff or "not bundled next to the executable")
    else:
        row("ffmpeg", bool(ff), ff or "not found on PATH (winget install Gyan.FFmpeg)")
    runtimes = list(detect_js_runtimes())
    if args.bundled:
        # 유튜브 서명 계산용. 함께 넣은 deno 가 실제로 실행되는지까지 본다
        deno = bundled_tool("deno.exe")
        version = ""
        if deno:
            try:
                out = subprocess.run([deno, "--version"], capture_output=True, text=True, timeout=30)
                version = out.stdout.splitlines()[0].strip() if out.stdout else ""
            except (OSError, subprocess.SubprocessError):
                version = ""
        row("deno", bool(version), version or (f"{deno} does not run" if deno else "not bundled next to the executable"))
    print(f"[--] {'js':<10} {', '.join(runtimes) or 'none (optional)'}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="utube", description="YouTube Music Downloader backend")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    from utube.api.base import add_serve_command

    add_serve_command(sub)

    d = sub.add_parser("doctor", help="check yt-dlp, FFmpeg and JS runtimes")
    d.add_argument("--bundled", action="store_true", help="require the FFmpeg and Deno shipped next to the executable")
    d.set_defaults(fn=cmd_doctor)

    args = p.parse_args(argv)
    sys.exit(args.fn(args))
