"""설정 파일 위치와 읽고 쓰기.

설정은 %APPDATA%\\YoutubeDownloader\\settings.json 에 둔다(UTUBE_HOME 으로 바꿀 수 있다).
설치 폴더에 두면 업데이트 때 지워지고, 권한이 없는 폴더일 수도 있다.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from utube.core.storage import default_save_dir

Format = Literal["MP3", "FLAC", "MP4"]
Quality = Literal["320", "256", "192"]
Sidebar = Literal["open", "closed"]


class Settings(BaseModel):
    save_dir: str = ""
    format: Format = "MP3"
    quality: Quality = "320"
    hide_queued: bool = False  # 검색 화면의 '이미 담은 곡 숨기기'
    sidebar: Sidebar = "open"  # 사이드바 접기/펴기. 다음 실행에도 그대로 연다


def app_home() -> Path:
    override = os.environ.get("UTUBE_HOME")
    if override:
        return Path(override)
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "YoutubeDownloader"


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_home() / "settings.json"
        self.lock = threading.Lock()
        self.value = self._load()

    def _load(self) -> Settings:
        try:
            s = Settings.model_validate_json(self.path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError):
            s = Settings()
        if not s.save_dir:
            s.save_dir = default_save_dir()
        return s

    def get(self) -> Settings:
        with self.lock:
            return self.value.model_copy()

    def save(self, value: Settings) -> None:
        with self.lock:
            self.value = value.model_copy()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(value.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
