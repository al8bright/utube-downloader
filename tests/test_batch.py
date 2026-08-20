"""app 모듈 — 배치 다운로드 루프."""
import os

import pytest

from utube_downloader import app as app_module
from .stubs import FakeApp


class TestBatchLoopDeadlock:
    def _item(self):
        return {"title": "t", "url": "u", "status": "waiting"}

    def test_다운로드가_예외를_던져도_batch_running_이_해제된다(self):
        app = FakeApp([self._item()])

        def boom(url, fmt, quality, save_dir):
            raise RuntimeError("포맷 코드 예외 등 예기치 못한 실패")

        app.download_single = boom

        with pytest.raises(RuntimeError):
            app_module.YoutubeDownloaderApp.batch_download_loop(app, [0], FakeApp.settings(os.getcwd()))

        assert app.batch_running is False, "예외가 나도 batch_running 은 반드시 풀려야 한다"

    def test_정상_완료시에도_batch_running_이_해제된다(self):
        app = FakeApp([self._item()])
        app.download_single = lambda url, fmt, quality, save_dir: True
        app_module.YoutubeDownloaderApp.batch_download_loop(app, [0], FakeApp.settings(os.getcwd()))
        assert app.batch_running is False
        assert app.queue_items[0]["status"] == "finished"

    def test_실패한_항목은_failed_로_표시된다(self):
        app = FakeApp([self._item()])
        app.download_single = lambda url, fmt, quality, save_dir: False
        app_module.YoutubeDownloaderApp.batch_download_loop(app, [0], FakeApp.settings(os.getcwd()))
        assert app.queue_items[0]["status"] == "failed"

class TestWorkerDoesNotTouchTk:
    def test_배치_루프는_Tk_변수를_읽지_않는다(self):
        """워커 스레드에서 Tk 변수를 읽으면 mainloop 밖에서 RuntimeError 로 배치가 죽는다."""
        app = FakeApp([{"title": "t", "url": "u", "status": "waiting"}])

        class Exploding:
            def get(self):
                raise RuntimeError("main thread is not in main loop")

        app.format_var = Exploding()
        app.quality_var = Exploding()
        app.save_dir_var = Exploding()
        app.download_single = lambda url, fmt, quality, save_dir: True

        app_module.YoutubeDownloaderApp.batch_download_loop(
            app, [0], FakeApp.settings(os.getcwd()))

        assert app.queue_items[0]["status"] == "finished"
        assert app.batch_running is False

    def test_설정은_인자로_받은_값을_쓴다(self, tmp_path):
        app = FakeApp([{"title": "t", "url": "u", "status": "waiting"}])
        seen = {}

        def capture(url, fmt, quality, save_dir):
            seen.update({"fmt": fmt, "quality": quality, "save_dir": save_dir})
            return True

        app.download_single = capture
        app_module.YoutubeDownloaderApp.batch_download_loop(
            app, [0], {"format": "FLAC", "quality": "0", "save_dir": str(tmp_path)})
        assert seen == {"fmt": "FLAC", "quality": "0", "save_dir": str(tmp_path)}

# --------------------------------------------------------------------------
# 실패 사유: print 로 흘리지 말고 항목에 남겨 UI 에 보여줘야 한다
# --------------------------------------------------------------------------
class TestFailureReason:
    def test_다운로드_실패시_사유가_항목에_기록된다(self):
        app = FakeApp([{"title": "t", "url": "u", "status": "waiting"}])

        def failing(url, fmt, quality, save_dir):
            app.last_error = "FFmpeg 를 찾을 수 없습니다"
            return False

        app.download_single = failing
        app_module.YoutubeDownloaderApp.batch_download_loop(app, [0], FakeApp.settings(os.getcwd()))
        assert app.queue_items[0].get("error") == "FFmpeg 를 찾을 수 없습니다"

    def test_사용자가_중단한_항목은_실패가_아니라_중단으로_기록된다(self):
        app = FakeApp([{"title": "t", "url": "u", "status": "waiting"}])

        def stopped(url, fmt, quality, save_dir):
            app.stop_requested = True
            return False

        app.download_single = stopped
        app_module.YoutubeDownloaderApp.batch_download_loop(app, [0], FakeApp.settings(os.getcwd()))
        assert app.queue_items[0]["status"] == "stopped"

    def test_ffmpeg_오류는_설치_안내로_바뀐다(self):
        msg = app_module.describe_download_error(Exception("ffprobe/ffmpeg not found"))
        assert "FFmpeg" in msg and "winget" in msg

    def test_비공개_영상_오류는_한국어로_설명된다(self):
        msg = app_module.describe_download_error(Exception("ERROR: Private video"))
        assert "비공개" in msg
