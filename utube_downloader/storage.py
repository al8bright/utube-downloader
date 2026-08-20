"""저장 폴더와 임시 파일 관리."""
import os
import shutil


def resolve_save_dir(raw_dir):
    """저장 폴더 경로를 검증한다. (사용할 경로, 유효여부) 를 돌려준다.

    폴더가 아닌 경로(파일, 끊긴 네트워크 드라이브)를 그대로 통과시키면
    다운로드와 일괄 삭제가 엉뚱한 폴더에서 일어나므로 isdir 로 확인한다.
    """
    save_dir = (raw_dir or '').strip()
    if not save_dir or not os.path.isdir(save_dir):
        return os.getcwd(), False
    return save_dir, True


def escape_ydl_path(path):
    """yt-dlp 가 경로의 %VAR% 를 환경변수로 확장하지 못하도록 % 를 이스케이프한다."""
    return (path or '').replace('%', '%%')


def cleanup_temp_dir(save_dir):
    """앱이 만든 임시 폴더만 지운다. 사용자 파일에는 손대지 않는다."""
    if not save_dir:
        return
    temp_dir = os.path.join(save_dir, TEMP_DIR_NAME)
    if not os.path.isdir(temp_dir):
        return
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass


TEMP_DIR_NAME = ".utube_tmp"  # 변환 전 중간 파일을 격리하는 폴더
