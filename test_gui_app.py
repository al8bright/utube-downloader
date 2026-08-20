"""gui_app 핵심 로직 테스트.

GUI 창을 띄우지 않고 검증할 수 있도록, 순수 함수와
언바운드 메서드 + 가짜 self 조합으로 작성했다.
"""
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gui_app


# --------------------------------------------------------------------------
# 시간 포맷: 라이브 방송(None)과 float 값에서 예외가 나면 안 된다
# --------------------------------------------------------------------------
class TestFormatDuration:
    def test_정상_초를_분초로_변환한다(self):
        assert gui_app.format_duration(215) == "03:35"

    def test_한시간_이상은_시분초로_변환한다(self):
        assert gui_app.format_duration(3725) == "01:02:05"

    def test_라이브방송의_None_은_예외없이_기본값을_준다(self):
        assert gui_app.format_duration(None) == "--:--"

    def test_float_초도_예외없이_변환한다(self):
        assert gui_app.format_duration(215.0) == "03:35"

    def test_문자열이_들어와도_죽지_않는다(self):
        assert gui_app.format_duration("bad") == "--:--"


class TestFormatEta:
    def test_정상_eta를_변환한다(self):
        assert gui_app.format_eta(93) == "01:33"

    def test_float_eta도_예외없이_변환한다(self):
        assert gui_app.format_eta(93.4) == "01:33"

    def test_None_은_기본값을_준다(self):
        assert gui_app.format_eta(None) == "--:--"


# --------------------------------------------------------------------------
# 저장 경로: 조용한 cwd 폴백이 아니라 유효성을 알려줘야 한다
# --------------------------------------------------------------------------
class TestResolveSaveDir:
    def test_유효한_폴더는_그대로_반환한다(self, tmp_path):
        path, ok = gui_app.resolve_save_dir(str(tmp_path))
        assert ok is True
        assert os.path.normpath(path) == os.path.normpath(str(tmp_path))

    def test_존재하지_않는_경로는_실패를_알린다(self, tmp_path):
        missing = str(tmp_path / "없는폴더")
        path, ok = gui_app.resolve_save_dir(missing)
        assert ok is False
        assert os.path.normpath(path) == os.path.normpath(os.getcwd())

    def test_폴더가_아닌_파일경로는_실패를_알린다(self, tmp_path):
        f = tmp_path / "a.mp3"
        f.write_bytes(b"x")
        path, ok = gui_app.resolve_save_dir(str(f))
        assert ok is False

    def test_빈_문자열은_실패를_알린다(self):
        path, ok = gui_app.resolve_save_dir("   ")
        assert ok is False


# --------------------------------------------------------------------------
# yt-dlp 옵션: 파일명에 영상 ID가 들어가야 덮어쓰기를 막는다
# --------------------------------------------------------------------------
class TestBuildYdlOpts:
    def test_출력_템플릿에_영상_ID가_포함된다(self, tmp_path):
        opts = gui_app.build_ydl_opts(str(tmp_path), "MP3", "320", hook=None)
        assert "%(id)s" in opts["outtmpl"]

    def test_MP3는_음질을_후처리기에_전달한다(self, tmp_path):
        opts = gui_app.build_ydl_opts(str(tmp_path), "MP3", "320", hook=None)
        pp = opts["postprocessors"][0]
        assert pp["key"] == "FFmpegExtractAudio"
        assert pp["preferredcodec"] == "mp3"
        assert pp["preferredquality"] == "320"

    def test_MP4는_오디오_추출_후처리기를_쓰지_않는다(self, tmp_path):
        opts = gui_app.build_ydl_opts(str(tmp_path), "MP4", "320", hook=None)
        assert "postprocessors" not in opts

    def test_MP4는_병합_컨테이너를_mp4로_고정한다(self, tmp_path):
        opts = gui_app.build_ydl_opts(str(tmp_path), "MP4", "320", hook=None)
        assert opts["merge_output_format"] == "mp4"

    def test_모든_포맷에서_재생목록을_비활성화한다(self, tmp_path):
        for fmt in ("MP3", "FLAC", "MP4"):
            assert gui_app.build_ydl_opts(str(tmp_path), fmt, "320", hook=None)["noplaylist"] is True


class TestTempDirIsolation:
    def test_중간_파일은_전용_임시폴더에_받는다(self, tmp_path):
        opts = gui_app.build_ydl_opts(str(tmp_path), "MP3", "320", hook=None)
        assert "paths" in opts
        assert opts["paths"]["home"] == str(tmp_path)
        assert opts["paths"]["temp"] == os.path.join(str(tmp_path), gui_app.TEMP_DIR_NAME)

    def test_임시폴더_정리는_해당_폴더만_지운다(self, tmp_path):
        keep = tmp_path / "내음악.mp3"
        keep.write_bytes(b"precious")
        tmp = tmp_path / gui_app.TEMP_DIR_NAME
        tmp.mkdir()
        (tmp / "찌꺼기.webm").write_bytes(b"junk")

        gui_app.cleanup_temp_dir(str(tmp_path))

        assert keep.exists(), "사용자 파일을 지우면 안 된다"
        assert not tmp.exists()

    def test_임시폴더가_없어도_예외가_없다(self, tmp_path):
        gui_app.cleanup_temp_dir(str(tmp_path))

    def test_잘못된_경로에도_죽지_않는다(self):
        gui_app.cleanup_temp_dir("")


# --------------------------------------------------------------------------
# 재생목록 URL: 항목 1개가 수백 개를 받으면 안 된다
# --------------------------------------------------------------------------
class TestPlaylistDetection:
    def test_재생목록_정보는_재생목록으로_판정한다(self):
        info = {"_type": "playlist", "entries": [{}, {}], "title": "믹스"}
        assert gui_app.is_playlist_info(info) is True

    def test_단일_영상_정보는_재생목록이_아니다(self):
        assert gui_app.is_playlist_info({"_type": "url", "title": "곡"}) is False

    def test_타입이_없는_단일_영상도_재생목록이_아니다(self):
        assert gui_app.is_playlist_info({"title": "곡", "duration": 100}) is False

    def test_None_은_재생목록이_아니다(self):
        assert gui_app.is_playlist_info(None) is False


# --------------------------------------------------------------------------
# 배치 루프: 예외가 나도 batch_running 이 풀려야 한다 (데드락 방지)
# --------------------------------------------------------------------------
class FakeApp:
    """batch_download_loop 를 GUI 없이 돌리기 위한 최소 스텁."""

    def __init__(self, items):
        self.queue_items = items
        self.batch_running = True
        self.stop_requested = False
        self.current_download_idx = -1
        self.current_download_status = {}
        self.overall_progress = 0.0
        self.active_format = "MP3"
        self.after_calls = []

    SETTINGS = {"format": "MP3", "quality": "320", "save_dir": None}

    @classmethod
    def settings(cls, tmp_dir):
        return {"format": "MP3", "quality": "320", "save_dir": tmp_dir}

    def after(self, delay, fn=None, *a):
        self.after_calls.append(fn)

    def update_queue_list_ui(self):
        pass

    def on_batch_download_complete(self):
        pass


class TestBatchLoopDeadlock:
    def _item(self):
        return {"title": "t", "url": "u", "status": "waiting"}

    def test_다운로드가_예외를_던져도_batch_running_이_해제된다(self):
        app = FakeApp([self._item()])

        def boom(url, fmt, quality, save_dir):
            raise RuntimeError("포맷 코드 예외 등 예기치 못한 실패")

        app.download_single = boom

        with pytest.raises(RuntimeError):
            gui_app.YoutubeDownloaderApp.batch_download_loop(app, [0], FakeApp.settings(os.getcwd()))

        assert app.batch_running is False, "예외가 나도 batch_running 은 반드시 풀려야 한다"

    def test_정상_완료시에도_batch_running_이_해제된다(self):
        app = FakeApp([self._item()])
        app.download_single = lambda url, fmt, quality, save_dir: True
        gui_app.YoutubeDownloaderApp.batch_download_loop(app, [0], FakeApp.settings(os.getcwd()))
        assert app.batch_running is False
        assert app.queue_items[0]["status"] == "finished"

    def test_실패한_항목은_failed_로_표시된다(self):
        app = FakeApp([self._item()])
        app.download_single = lambda url, fmt, quality, save_dir: False
        gui_app.YoutubeDownloaderApp.batch_download_loop(app, [0], FakeApp.settings(os.getcwd()))
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

        gui_app.YoutubeDownloaderApp.batch_download_loop(
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
        gui_app.YoutubeDownloaderApp.batch_download_loop(
            app, [0], {"format": "FLAC", "quality": "0", "save_dir": str(tmp_path)})
        assert seen == {"fmt": "FLAC", "quality": "0", "save_dir": str(tmp_path)}


# --------------------------------------------------------------------------
# 종료 처리: 진행 중이면 확인을 받고, 워커를 정리한 뒤에 닫아야 한다
# --------------------------------------------------------------------------
class FakeExecutor:
    def __init__(self):
        self.shutdown_calls = []

    def shutdown(self, wait=True, cancel_futures=False):
        self.shutdown_calls.append({"wait": wait, "cancel_futures": cancel_futures})


class FakeClosingApp:
    def __init__(self, batch_running):
        self.batch_running = batch_running
        self.stop_requested = False
        self.destroyed = False
        self.confirm_result = True
        self.confirm_asked = False
        self.executor = FakeExecutor()
        self.render_cancelled = False

        def cancel_render():
            self.render_cancelled = True

        self.search_scroll = types.SimpleNamespace(
            thumb_executor=self.executor, cancel_render=cancel_render)

    def confirm_exit_during_download(self):
        self.confirm_asked = True
        return self.confirm_result

    def destroy(self):
        self.destroyed = True


class TestOnClosing:
    def test_다운로드_중이_아니면_바로_닫는다(self):
        app = FakeClosingApp(batch_running=False)
        gui_app.YoutubeDownloaderApp.on_closing(app)
        assert app.confirm_asked is False
        assert app.destroyed is True

    def test_다운로드_중이면_사용자에게_확인을_받는다(self):
        app = FakeClosingApp(batch_running=True)
        gui_app.YoutubeDownloaderApp.on_closing(app)
        assert app.confirm_asked is True
        assert app.destroyed is True

    def test_사용자가_취소하면_닫지_않는다(self):
        app = FakeClosingApp(batch_running=True)
        app.confirm_result = False
        gui_app.YoutubeDownloaderApp.on_closing(app)
        assert app.destroyed is False, "취소했는데 창이 닫히면 진행 중인 다운로드가 소실된다"

    def test_닫을때_중단_플래그를_세운다(self):
        app = FakeClosingApp(batch_running=True)
        gui_app.YoutubeDownloaderApp.on_closing(app)
        assert app.stop_requested is True

    def test_닫을때_썸네일_워커를_취소하며_종료한다(self):
        app = FakeClosingApp(batch_running=False)
        gui_app.YoutubeDownloaderApp.on_closing(app)
        assert app.executor.shutdown_calls, "executor.shutdown 이 호출되지 않으면 프로세스가 남는다"
        assert app.executor.shutdown_calls[0]["cancel_futures"] is True

    def test_닫을때_진행중인_렌더링도_취소한다(self):
        app = FakeClosingApp(batch_running=False)
        gui_app.YoutubeDownloaderApp.on_closing(app)
        assert app.render_cancelled is True

    def test_렌더링_취소가_실패해도_워커는_종료된다(self):
        app = FakeClosingApp(batch_running=False)

        def boom():
            raise RuntimeError("취소 실패")

        app.search_scroll.cancel_render = boom
        gui_app.YoutubeDownloaderApp.on_closing(app)
        assert app.executor.shutdown_calls, "앞 단계 실패로 executor 종료를 건너뛰면 프로세스가 남는다"

    def test_취소하면_워커를_종료하지_않는다(self):
        app = FakeClosingApp(batch_running=True)
        app.confirm_result = False
        gui_app.YoutubeDownloaderApp.on_closing(app)
        assert app.executor.shutdown_calls == []


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
        gui_app.YoutubeDownloaderApp.batch_download_loop(app, [0], FakeApp.settings(os.getcwd()))
        assert app.queue_items[0].get("error") == "FFmpeg 를 찾을 수 없습니다"

    def test_사용자가_중단한_항목은_실패가_아니라_중단으로_기록된다(self):
        app = FakeApp([{"title": "t", "url": "u", "status": "waiting"}])

        def stopped(url, fmt, quality, save_dir):
            app.stop_requested = True
            return False

        app.download_single = stopped
        gui_app.YoutubeDownloaderApp.batch_download_loop(app, [0], FakeApp.settings(os.getcwd()))
        assert app.queue_items[0]["status"] == "stopped"

    def test_ffmpeg_오류는_설치_안내로_바뀐다(self):
        msg = gui_app.describe_download_error(Exception("ffprobe/ffmpeg not found"))
        assert "FFmpeg" in msg and "winget" in msg

    def test_비공개_영상_오류는_한국어로_설명된다(self):
        msg = gui_app.describe_download_error(Exception("ERROR: Private video"))
        assert "비공개" in msg


# --------------------------------------------------------------------------
# import 누락 회귀 방지
# --------------------------------------------------------------------------
class TestImports:
    def test_filedialog_가_임포트되어_있다(self):
        assert hasattr(gui_app, "filedialog"), "폴더 변경 버튼이 NameError 로 죽는다"
        assert hasattr(gui_app.filedialog, "askdirectory")


# --------------------------------------------------------------------------
# 영상 ID 추출: 링크 형태가 달라도 같은 영상이면 중복으로 잡아야 한다
# --------------------------------------------------------------------------
class TestExtractVideoId:
    def test_표준_watch_링크(self):
        assert gui_app.extract_video_id("https://www.youtube.com/watch?v=n61ULEU7CO0") == "n61ULEU7CO0"

    def test_단축_링크(self):
        assert gui_app.extract_video_id("https://youtu.be/n61ULEU7CO0") == "n61ULEU7CO0"

    def test_타임스탬프가_붙어도_같은_ID(self):
        assert gui_app.extract_video_id("https://youtu.be/n61ULEU7CO0?t=42") == "n61ULEU7CO0"

    def test_재생목록_파라미터가_붙어도_같은_ID(self):
        url = "https://www.youtube.com/watch?v=n61ULEU7CO0&list=PLabc&index=3"
        assert gui_app.extract_video_id(url) == "n61ULEU7CO0"

    def test_shorts_와_embed(self):
        assert gui_app.extract_video_id("https://youtube.com/shorts/n61ULEU7CO0") == "n61ULEU7CO0"
        assert gui_app.extract_video_id("https://www.youtube.com/embed/n61ULEU7CO0") == "n61ULEU7CO0"

    def test_유튜브가_아니면_None(self):
        assert gui_app.extract_video_id("https://example.com/watch?v=abc") is None

    def test_빈값은_None(self):
        assert gui_app.extract_video_id("") is None
        assert gui_app.extract_video_id(None) is None


class TestIsSameVideo:
    def test_형태가_달라도_같은_영상이면_참(self):
        assert gui_app.is_same_video(
            "https://youtu.be/n61ULEU7CO0?t=42",
            "https://www.youtube.com/watch?v=n61ULEU7CO0&list=PLx",
        ) is True

    def test_다른_영상이면_거짓(self):
        assert gui_app.is_same_video(
            "https://youtu.be/n61ULEU7CO0", "https://youtu.be/aqz-KE-bpKQ"
        ) is False

    def test_ID를_못뽑으면_문자열_비교로_떨어진다(self):
        assert gui_app.is_same_video("https://x.com/a", "https://x.com/a") is True
        assert gui_app.is_same_video("https://x.com/a", "https://x.com/b") is False


# --------------------------------------------------------------------------
# 저장 경로의 %VAR% 가 환경변수로 치환되면 안 된다
# --------------------------------------------------------------------------
class TestPathEscaping:
    def test_퍼센트가_이스케이프된다(self):
        assert gui_app.escape_ydl_path(r"D:\Music%USERNAME%") == r"D:\Music%%USERNAME%%"

    def test_퍼센트가_없으면_그대로(self):
        assert gui_app.escape_ydl_path(r"D:\Music") == r"D:\Music"

    def test_옵션의_paths가_이스케이프된_경로를_쓴다(self):
        opts = gui_app.build_ydl_opts(r"D:\Music%USERNAME%", "MP3", "320", hook=None)
        assert "%%USERNAME%%" in opts["paths"]["home"]


# --------------------------------------------------------------------------
# 배치 결과 보고: 전량 실패를 성공으로 보고하면 안 된다
# --------------------------------------------------------------------------
class TestBatchResultMessage:
    def test_전부_성공(self):
        text, ok = gui_app.describe_batch_result(3, 0, 0)
        assert ok is True
        assert "3" in text

    def test_전부_실패면_성공으로_보고하지_않는다(self):
        text, ok = gui_app.describe_batch_result(0, 3, 0)
        assert ok is False, "전량 실패인데 성공색으로 표시하면 안 된다"
        assert "실패" in text

    def test_일부_실패도_성공이_아니다(self):
        text, ok = gui_app.describe_batch_result(2, 1, 0)
        assert ok is False
        assert "2" in text and "1" in text

    def test_중단이_섞이면_중단을_알린다(self):
        text, ok = gui_app.describe_batch_result(1, 0, 2)
        assert "중단" in text

    def test_아무것도_안했으면_성공이_아니다(self):
        text, ok = gui_app.describe_batch_result(0, 0, 0)
        assert ok is False


# --------------------------------------------------------------------------
# 진행 단계 문구: MP4 인데 '음원 변환 중' 이라고 하면 안 된다
# --------------------------------------------------------------------------
class TestStageText:
    def test_MP4_후처리는_병합으로_표기한다(self):
        assert "병합" in gui_app.describe_postprocess_stage("MP4")

    def test_MP3_후처리는_음원_변환으로_표기한다(self):
        assert "변환" in gui_app.describe_postprocess_stage("MP3")

    def test_FLAC도_변환으로_표기한다(self):
        assert "변환" in gui_app.describe_postprocess_stage("FLAC")


# --------------------------------------------------------------------------
# 점진 렌더링: 데이터는 즉시, 위젯만 나눠 그려야 한다
# --------------------------------------------------------------------------
class FakeSearchFrame:
    """ScrollableSearchFrame 의 렌더링 로직만 떼어 검증하기 위한 스텁."""

    def __init__(self):
        self.search_widgets = []
        self.search_results_data = []
        self.render_job = None
        self.rendered_rows = []
        self.after_queue = []

    def after(self, delay, fn, *args):
        self.after_queue.append((fn, args))
        return f"job{len(self.after_queue)}"

    def after_cancel(self, job):
        self.after_queue.clear()

    # 실제 클래스의 메서드를 그대로 빌려 쓴다
    cancel_render = gui_app.ScrollableSearchFrame.cancel_render
    _render_chunk = gui_app.ScrollableSearchFrame._render_chunk

    class Row:
        def destroy(self):
            pass

    def _render_row(self, idx, item):
        self.rendered_rows.append(idx)
        self.search_widgets.append(FakeSearchFrame.Row())

    def drain(self):
        """예약된 렌더링을 끝까지 실행한다."""
        while self.after_queue:
            fn, args = self.after_queue.pop(0)
            fn(*args)


class TestProgressiveRender:
    def _results(self, n):
        return [{"title": f"곡{i}", "url": f"u{i}", "duration": "03:00",
                 "uploader": "ch", "thumbnail": None} for i in range(n)]

    def _frame(self, monkeypatch):
        frame = FakeSearchFrame()
        # ctk.BooleanVar 대신 가벼운 대체물을 쓴다 (GUI 없이 돌리기 위함)
        monkeypatch.setattr(gui_app.ctk, "BooleanVar", lambda value=False: {"v": value})
        return frame

    def test_데이터는_즉시_전부_채워진다(self, monkeypatch):
        frame = self._frame(monkeypatch)
        gui_app.ScrollableSearchFrame.populate_results(frame, self._results(100))
        assert len(frame.search_results_data) == 100, "렌더링 전에도 선택 대상 데이터는 전부 있어야 한다"

    def test_첫_호출에_전부_그리지_않는다(self, monkeypatch):
        frame = self._frame(monkeypatch)
        gui_app.ScrollableSearchFrame.populate_results(frame, self._results(100))
        assert len(frame.rendered_rows) < 100, "한 번에 다 그리면 UI 가 멈춘다"

    def test_끝까지_돌리면_전부_그려진다(self, monkeypatch):
        frame = self._frame(monkeypatch)
        gui_app.ScrollableSearchFrame.populate_results(frame, self._results(100))
        frame.drain()
        assert frame.rendered_rows == list(range(100))

    def test_빈_결과는_안내만_남긴다(self, monkeypatch):
        frame = self._frame(monkeypatch)

        class FakeLabel:
            def __init__(self, *a, **k):
                self.kwargs = k

            def pack(self, **k):
                pass

        monkeypatch.setattr(gui_app.ctk, "CTkLabel", FakeLabel)
        gui_app.ScrollableSearchFrame.populate_results(frame, [])
        assert frame.search_results_data == []
        assert len(frame.search_widgets) == 1
        assert frame.rendered_rows == []

    def test_새_검색이_들어오면_이전_렌더링을_취소한다(self, monkeypatch):
        frame = self._frame(monkeypatch)
        gui_app.ScrollableSearchFrame.populate_results(frame, self._results(100))
        assert frame.after_queue, "아직 그릴 것이 남아 있어야 한다"

        class FakeLabel:
            def __init__(self, *a, **k):
                pass

            def pack(self, **k):
                pass

        monkeypatch.setattr(gui_app.ctk, "CTkLabel", FakeLabel)
        gui_app.ScrollableSearchFrame.populate_results(frame, [])
        assert frame.after_queue == [], "이전 렌더링을 취소하지 않으면 옛 결과가 새 화면에 섞인다"
