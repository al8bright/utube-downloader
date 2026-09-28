"""yt-dlp 다운로드 설정과 오류 해석.

Tk 를 건드리지 않는다. 창 없이 그대로 시험할 수 있어야 한다.
"""
import os
import shutil

from .storage import TEMP_DIR_NAME, escape_ydl_path

# yt-dlp 가 지원하는 JavaScript 런타임 (우선순위 순)
JS_RUNTIMES = ("deno", "node", "quickjs", "bun")


def detect_js_runtimes(which=None):
    """PATH 에 있는 JavaScript 런타임을 yt-dlp 설정 형태로 돌려준다.

    유튜브는 다운로드 주소 서명 계산에 JS 실행을 요구한다. yt-dlp 는 기본으로
    deno 만 찾는데, 없으면 '일부 형식이 빠질 수 있다' 는 경고와 함께
    추출이 불안정해진다. 흔히 깔려 있는 node 등도 함께 쓰게 한다.
    """
    # 기본 인자로 묶어 두면 테스트에서 shutil.which 를 바꿔 끼울 수 없다
    which = which or shutil.which
    return {name: {} for name in JS_RUNTIMES if which(name)}


def js_runtime_opts():
    """yt-dlp 옵션에 합칠 JS 런타임 설정. 없으면 빈 사전.

    빈 설정을 넘기면 yt-dlp 기본값(deno)까지 지워지므로 아예 키를 넣지 않는다.
    검색·분석·다운로드가 모두 같은 설정을 쓰도록 여기서 한 번만 만든다.
    """
    runtimes = detect_js_runtimes()
    return {'js_runtimes': runtimes} if runtimes else {}


def describe_download_error(exc):
    """yt-dlp 예외를 사용자가 조치할 수 있는 한국어 문구로 바꾼다."""
    raw = str(exc)
    low = raw.lower()
    if 'ffmpeg' in low or 'ffprobe' in low:
        return "FFmpeg 를 찾을 수 없습니다. winget install Gyan.FFmpeg 로 설치한 뒤 다시 시도해 주세요."
    if '403' in raw or 'forbidden' in low:
        # 유튜브가 주소 서명 방식을 바꾸면 낡은 yt-dlp 가 만든 주소를 거부한다.
        # 실제 원인은 대부분 '차단' 이 아니라 '구버전' 이라 그렇게 안내한다.
        return ("유튜브가 다운로드를 거부했습니다 (403)."
                " 대개 프로그램에 들어 있는 yt-dlp 가 오래돼 생깁니다."
                " 최신 버전의 실행 파일을 받아 주세요."
                " 소스로 실행 중이라면 pip install -U yt-dlp 로 올린 뒤 다시 시도해 주세요.")
    if 'not a bot' in low or 'sign in to confirm' in low:
        return ("유튜브가 사람인지 확인을 요구했습니다."
                " 잠시 뒤에 다시 시도하거나, 같은 영상을 브라우저에서 한 번 연 뒤 시도해 주세요.")
    if 'private video' in low:
        return "비공개 영상이라 다운로드할 수 없습니다."
    if 'age' in low and 'restrict' in low:
        return "연령 제한 영상이라 다운로드할 수 없습니다."
    if 'unavailable' in low or 'removed' in low:
        return "삭제되었거나 이용할 수 없는 영상입니다."
    if 'not available in your country' in low or 'geo' in low and 'block' in low:
        return "지역 제한으로 차단된 영상입니다."
    if 'no space' in low or 'disk' in low and 'full' in low:
        return "저장 공간이 부족합니다."
    if 'urlopen' in low or 'timed out' in low or 'connection' in low:
        return "네트워크 연결에 실패했습니다. 인터넷 상태를 확인해 주세요."
    return raw.strip() or "알 수 없는 오류가 발생했습니다."


def build_ydl_opts(save_dir, format_type, quality, hook):
    """포맷에 맞는 yt-dlp 옵션을 만든다."""
    opts = {
        # 영상 ID 를 붙여야 제목이 같은 다른 영상이 기존 파일을 덮어쓰지 않는다
        'outtmpl': '%(title)s [%(id)s].%(ext)s',
        # 중간 파일(.part/.webm)을 전용 폴더에 두어 저장 폴더가 더럽혀지지 않게 한다
        'paths': {
            # % 를 이스케이프하지 않으면 폴더 이름의 %VAR% 가 환경변수로 치환된다
            'home': escape_ydl_path(save_dir),
            'temp': escape_ydl_path(os.path.join(save_dir, TEMP_DIR_NAME)),
        },
        'noplaylist': True,
        'quiet': True,
    }

    opts.update(js_runtime_opts())
    if hook is not None:
        opts['progress_hooks'] = [hook]

    if format_type == 'MP4':
        opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        opts['merge_output_format'] = 'mp4'
    else:
        opts['format'] = 'bestaudio/best'
        postprocessor = {
            'key': 'FFmpegExtractAudio',
            'preferredcodec': format_type.lower(),
        }
        if format_type == 'MP3':
            # FLAC 은 무손실이라 비트레이트 개념이 없다. '0' 은 의미 없는 값이었다.
            postprocessor['preferredquality'] = quality
        opts['postprocessors'] = [postprocessor]
    return opts
