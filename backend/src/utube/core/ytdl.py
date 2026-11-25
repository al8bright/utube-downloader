"""yt-dlp 연동: 옵션 만들기, 검색·분석·다운로드, 오류 해석."""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

from utube.core.storage import TEMP_DIR_NAME, escape_ydl_path

# yt-dlp 가 지원하는 JavaScript 런타임 (우선순위 순)
JS_RUNTIMES = ("deno", "node", "quickjs", "bun")

SOCKET_TIMEOUT = 20  # 초. 응답 없는 연결이 검색·분석을 영원히 붙잡지 않게 한다


def detect_js_runtimes(
    which: Callable[[str], str | None] | None = None, bundled_deno: str | None = None
) -> dict[str, dict]:
    """쓸 수 있는 JavaScript 런타임을 yt-dlp 설정 형태로 돌려준다.

    유튜브는 다운로드 주소 서명 계산에 JS 실행을 요구한다. yt-dlp 는 기본으로
    deno 만 찾는데, 없으면 일부 형식이 빠지고 추출이 불안정해진다.
    설치 파일에 함께 넣은 deno 를 먼저 쓰고, PATH 에 있는 런타임(흔히 깔린 node 등)도 쓰게 한다.
    """
    which = which or shutil.which
    if bundled_deno is None:
        bundled_deno = bundled_tool("deno.exe")
    found = {name: {} for name in JS_RUNTIMES if which(name)}
    if bundled_deno:
        found["deno"] = {"path": bundled_deno}
    return {name: found[name] for name in JS_RUNTIMES if name in found}


def js_runtime_opts() -> dict:
    """yt-dlp 옵션에 합칠 JS 런타임 설정.

    빈 설정을 넘기면 yt-dlp 기본값(deno)까지 지워지므로 없으면 키를 넣지 않는다.
    """
    runtimes = detect_js_runtimes()
    return {"js_runtimes": runtimes} if runtimes else {}


def bundled_tool(exe: str) -> str | None:
    """설치 파일에 함께 들어 있는 도구(ffmpeg.exe, deno.exe)의 경로. 개발 실행이면 None(PATH 의 것을 쓴다).

    빌드 스크립트가 도구를 백엔드 실행 파일 옆에 둔다. UTUBE_TOOLS_DIR 로 다른 폴더를 가리킬 수 있다.
    """
    override = os.environ.get("UTUBE_TOOLS_DIR")
    if override and os.path.isfile(os.path.join(override, exe)):
        return os.path.join(override, exe)
    if getattr(sys, "frozen", False):
        here = Path(sys.executable).parent
        for d in (here, here / "_internal"):
            if (d / exe).is_file():
                return str(d / exe)
    return None


def bundled_ffmpeg_dir() -> str | None:
    """설치 파일에 함께 들어 있는 FFmpeg 폴더. 없으면 None."""
    p = bundled_tool("ffmpeg.exe")
    return os.path.dirname(p) if p else None


def ffmpeg_path() -> str | None:
    d = bundled_ffmpeg_dir()
    if d:
        return os.path.join(d, "ffmpeg.exe")
    return shutil.which("ffmpeg")


def describe_download_error(exc: BaseException | str) -> str:
    """yt-dlp 예외를 사용자가 조치할 수 있는 한국어 문구로 바꾼다."""
    raw = str(exc)
    low = raw.lower()
    if "ffmpeg" in low or "ffprobe" in low:
        if bundled_ffmpeg_dir():
            # 함께 넣어 두었는데도 못 쓰는 경우다. 설치 안내는 도움이 안 된다
            return ("함께 들어 있는 FFmpeg 를 실행하지 못했습니다."
                    " 백신이나 보안 프로그램이 막았을 수 있습니다."
                    " 프로그램을 예외로 등록한 뒤 다시 시도해 주세요.")
        return "FFmpeg 를 찾을 수 없습니다. winget install Gyan.FFmpeg 로 설치한 뒤 다시 시도해 주세요."
    if "403" in raw or "forbidden" in low:
        # 유튜브가 주소 서명 방식을 바꾸면 낡은 yt-dlp 가 만든 주소를 거부한다.
        # 실제 원인은 대부분 '차단' 이 아니라 '구버전' 이라 그렇게 안내한다.
        return ("유튜브가 다운로드를 거부했습니다 (403)."
                " 대개 프로그램에 들어 있는 yt-dlp 가 오래돼 생깁니다."
                " 최신 버전의 설치 파일로 다시 설치해 주세요.")
    if "not a bot" in low or "sign in to confirm" in low:
        return ("유튜브가 사람인지 확인을 요구했습니다."
                " 잠시 뒤에 다시 시도하거나, 같은 영상을 브라우저에서 한 번 연 뒤 시도해 주세요.")
    if "private video" in low:
        return "비공개 영상이라 다운로드할 수 없습니다."
    if "age" in low and "restrict" in low:
        return "연령 제한 영상이라 다운로드할 수 없습니다."
    if "in your country" in low or ("geo" in low and "block" in low):
        return "지역 제한으로 차단된 영상입니다."
    if "unavailable" in low or "removed" in low:
        return "삭제되었거나 이용할 수 없는 영상입니다."
    if "no space" in low or ("disk" in low and "full" in low):
        return "저장 공간이 부족합니다."
    if "urlopen" in low or "timed out" in low or "connection" in low or "getaddrinfo" in low:
        return "네트워크 연결에 실패했습니다. 인터넷 상태를 확인해 주세요."
    text = raw.strip()
    if text.startswith("ERROR: "):
        text = text[len("ERROR: "):]
    return text or "알 수 없는 오류가 발생했습니다."


def build_ydl_opts(save_dir: str, format_type: str, quality: str, hook: Callable[[dict], None] | None) -> dict:
    """형식에 맞는 yt-dlp 다운로드 옵션."""
    opts: dict = {
        # 영상 ID 를 붙여야 제목이 같은 다른 영상이 기존 파일을 덮어쓰지 않는다
        "outtmpl": "%(title)s [%(id)s].%(ext)s",
        # 중간 파일(.part/.webm)을 전용 폴더에 두어 저장 폴더가 더럽혀지지 않게 한다
        "paths": {
            # % 를 이스케이프하지 않으면 폴더 이름의 %VAR% 가 환경변수로 치환된다
            "home": escape_ydl_path(save_dir),
            "temp": escape_ydl_path(os.path.join(save_dir, TEMP_DIR_NAME)),
        },
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "socket_timeout": SOCKET_TIMEOUT,
        **js_runtime_opts(),
    }
    ffmpeg_dir = bundled_ffmpeg_dir()
    if ffmpeg_dir:
        opts["ffmpeg_location"] = ffmpeg_dir
    if hook is not None:
        opts["progress_hooks"] = [hook]

    if format_type == "MP4":
        opts["format"] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        opts["merge_output_format"] = "mp4"
    else:
        opts["format"] = "bestaudio/best"
        postprocessor = {"key": "FFmpegExtractAudio", "preferredcodec": format_type.lower()}
        if format_type == "MP3":
            # FLAC 은 무손실이라 비트레이트 개념이 없다
            postprocessor["preferredquality"] = quality
        opts["postprocessors"] = [postprocessor]
    return opts


def _info_opts(**extra) -> dict:
    return {"skip_download": True, "extract_flat": True, "quiet": True, "no_warnings": True,
            "socket_timeout": SOCKET_TIMEOUT, **js_runtime_opts(), **extra}


class YtDlp:
    """실제 yt-dlp 호출. 테스트는 같은 메서드를 가진 가짜로 바꿔 끼운다."""

    def search(self, query: str, limit: int) -> Iterator[dict]:
        """검색 결과를 받는 대로 하나씩 내준다.

        process=False 로 받으면 유튜브 페이지(약 20개)를 넘길 때마다 결과가 흘러나온다.
        다 모은 뒤 넘기면 5초 넘게 아무 변화가 없다가 한꺼번에 뜬다.
        """
        import yt_dlp

        with yt_dlp.YoutubeDL(_info_opts()) as ydl:
            info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False, process=False)
            yield from info.get("entries") or []

    def analyze(self, url: str) -> dict:
        import yt_dlp

        with yt_dlp.YoutubeDL(_info_opts(noplaylist=True)) as ydl:
            return ydl.extract_info(url, download=False) or {}

    def download(self, url: str, opts: dict) -> None:
        import yt_dlp

        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])


def ytdlp_version() -> str:
    try:
        from yt_dlp.version import __version__
        return __version__
    except Exception:
        return "?"
