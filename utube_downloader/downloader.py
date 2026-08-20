"""yt-dlp 다운로드 설정과 오류 해석.

Tk 를 건드리지 않는다. 창 없이 그대로 시험할 수 있어야 한다.
"""
import os

from .storage import TEMP_DIR_NAME, escape_ydl_path


def describe_download_error(exc):
    """yt-dlp 예외를 사용자가 조치할 수 있는 한국어 문구로 바꾼다."""
    raw = str(exc)
    low = raw.lower()
    if 'ffmpeg' in low or 'ffprobe' in low:
        return "FFmpeg 를 찾을 수 없습니다. winget install Gyan.FFmpeg 로 설치한 뒤 다시 시도해 주세요."
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
