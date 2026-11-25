"""테스트 공통: 실제 yt-dlp·스레드·ffmpeg 없이 Service 를 돌린다."""

from __future__ import annotations

import pytest

from utube.config import Settings, SettingsStore
from utube.core.service import Service


def entry(video_id: str, title: str = "곡", **kw) -> dict:
    """yt-dlp 검색 결과 한 건 모양."""
    return {"id": video_id, "ie_key": "Youtube", "title": title, "url": f"https://www.youtube.com/watch?v={video_id}",
            "duration": 200, "uploader": "채널", **kw}


class FakeYtDlp:
    def __init__(self) -> None:
        self.search_entries: list[dict] = []
        self.search_error: Exception | None = None
        self.infos: dict[str, dict | Exception] = {}
        self.behaviour: dict[str, object] = {}  # url -> 예외 또는 callable(hook, opts)
        self.downloads: list[tuple[str, dict]] = []

    def search(self, query, limit):
        yield from self.search_entries
        if self.search_error:
            raise self.search_error

    def analyze(self, url):
        info = self.infos.get(url, {"id": "n61ULEU7CO0", "title": "분석된 곡", "uploader": "채널", "duration": 61})
        if isinstance(info, Exception):
            raise info
        return info

    def download(self, url, opts):
        self.downloads.append((url, opts))
        hook = opts["progress_hooks"][0]
        b = self.behaviour.get(url)
        if isinstance(b, BaseException):
            raise b
        if callable(b):
            b(hook, opts)
            return
        hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100, "speed": 2048, "eta": 3})
        hook({"status": "finished"})


def run_now(fn, *args):
    """스레드 대신 그 자리에서 돌린다."""
    fn(*args)


@pytest.fixture
def save_dir(tmp_path):
    d = tmp_path / "music"
    d.mkdir()
    return d


@pytest.fixture
def store(tmp_path, save_dir):
    s = SettingsStore(tmp_path / "settings.json")
    s.save(Settings(save_dir=str(save_dir)))
    return s


@pytest.fixture
def ytdl():
    return FakeYtDlp()


@pytest.fixture
def killed():
    return []


@pytest.fixture
def svc(ytdl, store, killed):
    def kill():
        killed.append(1)
        return 0

    return Service(ytdl=ytdl, settings=store, spawn=run_now, kill_ffmpeg=kill)
