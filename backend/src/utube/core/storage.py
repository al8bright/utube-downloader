"""저장 폴더와 받은 파일 관리."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

TEMP_DIR_NAME = ".utube_tmp"  # 변환 전 중간 파일을 격리하는 폴더

AUDIO_EXTS = (".mp3", ".flac")
VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".avi")
KINDS = {"audio": AUDIO_EXTS, "video": VIDEO_EXTS}


class StorageError(Exception):
    """사용자에게 그대로 보여 줄 수 있는 문구를 담는다."""


def default_save_dir() -> str:
    """처음 쓰는 저장 폴더. 설치 폴더(Program Files·AppData)에 음원이 쌓이면 찾기 어렵다."""
    home = Path.home()
    for candidate in (home / "Music", home / "Downloads", home):
        if candidate.is_dir():
            return str(candidate)
    return str(home)


def resolve_save_dir(raw_dir: str | None) -> tuple[str, bool]:
    """저장 폴더 경로를 검증한다. (정리한 경로, 쓸 수 있는가)

    폴더가 아닌 경로(파일, 끊긴 네트워크 드라이브)를 그대로 통과시키면
    다운로드와 일괄 삭제가 엉뚱한 곳에서 일어나므로 isdir 로 확인한다.
    """
    save_dir = (raw_dir or "").strip()
    if not save_dir:
        return "", False
    save_dir = os.path.normpath(save_dir)
    return save_dir, os.path.isdir(save_dir)


def escape_ydl_path(path: str | None) -> str:
    """yt-dlp 가 경로의 %VAR% 를 환경변수로 확장하지 못하도록 % 를 이스케이프한다."""
    return (path or "").replace("%", "%%")


def cleanup_temp_dir(save_dir: str | None) -> None:
    """앱이 만든 임시 폴더만 지운다. 사용자 파일에는 손대지 않는다."""
    if not save_dir:
        return
    temp_dir = os.path.join(save_dir, TEMP_DIR_NAME)
    if os.path.isdir(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)


def kind_of(name: str) -> str | None:
    lower = name.lower()
    for kind, exts in KINDS.items():
        if lower.endswith(exts):
            return kind
    return None


def list_files(save_dir: str) -> dict[str, list[dict]]:
    """저장 폴더의 음성·영상 파일. 하위 폴더는 보지 않는다."""
    found: dict[str, list[dict]] = {"audio": [], "video": []}
    with os.scandir(save_dir) as it:
        for entry in it:
            if not entry.is_file():
                continue
            kind = kind_of(entry.name)
            if kind is None:
                continue
            stat = entry.stat()
            found[kind].append({
                "name": entry.name,
                "ext": os.path.splitext(entry.name)[1][1:].upper(),
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            })
    return found


def file_in_dir(save_dir: str, name: str) -> str:
    """화면이 보낸 파일 이름을 저장 폴더 안의 실제 경로로 바꾼다.

    이름에 경로가 섞여 있으면(..\\, C:\\) 저장 폴더 밖의 파일을 지우거나 열 수 있으므로 막는다.
    음성·영상 파일만 다룬다.
    """
    if not name or os.path.basename(name) != name or name in (".", ".."):
        raise StorageError("파일 이름이 올바르지 않습니다.")
    if kind_of(name) is None:
        raise StorageError("음성·영상 파일만 다룰 수 있습니다.")
    path = os.path.join(save_dir, name)
    if not os.path.isfile(path):
        raise StorageError(f"파일을 찾을 수 없습니다: {name}")
    return path


def delete_kind(save_dir: str, kind: str) -> tuple[int, list[str]]:
    """저장 폴더의 한 종류 파일을 모두 지운다. (지운 개수, 실패 사유 목록)"""
    if kind not in KINDS:
        raise StorageError("알 수 없는 파일 종류입니다.")
    deleted, errors = 0, []
    for entry in list_files(save_dir)[kind]:
        try:
            os.remove(os.path.join(save_dir, entry["name"]))
            deleted += 1
        except OSError as e:
            errors.append(f"{entry['name']}: {e.strerror or e}")
    return deleted, errors
