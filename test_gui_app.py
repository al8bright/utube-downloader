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


# --------------------------------------------------------------------------
# 회귀: 차단된 재생목록이 재시도 경로로 되살아나면 안 된다
# --------------------------------------------------------------------------
class FakeVar:
    def __init__(self, value=True):
        self.value = value

    def get(self):
        return self.value

    def set(self, v):
        self.value = v


class FakeStartApp:
    def __init__(self, items):
        self.queue_items = items
        self.batch_running = False
        self.stop_requested = False
        self.errors = []
        self.started = None
        self.locked = None
        self.save_dir_var = FakeVar(os.getcwd())
        self.format_var = FakeVar("MP3")
        self.quality_var = FakeVar("320kbps")

    def show_error(self, msg):
        self.errors.append(msg)

    def set_controls_locked(self, locked):
        self.locked = locked

    def batch_download_loop(self, indices, settings):
        pass


def _start(app, monkeypatch):
    """start_selected_download 를 실제 스레드 없이 돌린다."""
    captured = {}

    class FakeThread:
        def __init__(self, target=None, args=(), daemon=None):
            captured["args"] = args

        def start(self):
            captured["started"] = True

    monkeypatch.setattr(gui_app.threading, "Thread", FakeThread)
    gui_app.YoutubeDownloaderApp.start_selected_download(app)
    return captured


class TestBlockedPlaylistNotRetried:
    def _blocked_item(self):
        return {"title": "재생목록", "url": "https://www.youtube.com/playlist?list=PLx",
                "check_var": FakeVar(True), "status": "failed", "blocked": True}

    def _normal_item(self):
        return {"title": "곡", "url": "https://www.youtube.com/watch?v=n61ULEU7CO0",
                "check_var": FakeVar(True), "status": "waiting"}

    def test_차단된_재생목록은_다운로드_대상에서_빠진다(self, monkeypatch):
        app = FakeStartApp([self._blocked_item(), self._normal_item()])
        cap = _start(app, monkeypatch)
        assert cap.get("started"), "정상 항목이 있으니 배치는 시작돼야 한다"
        assert cap["args"][0] == [1], "차단된 재생목록이 대상에 들어가면 영상 수백 개를 받는다"

    def test_차단_항목만_있으면_배치가_시작되지_않는다(self, monkeypatch):
        app = FakeStartApp([self._blocked_item()])
        cap = _start(app, monkeypatch)
        assert not cap.get("started")
        assert app.errors, "받을 것이 없다는 안내가 있어야 한다"

    def test_전체_선택은_차단_항목을_체크하지_않는다(self):
        blocked = self._blocked_item()
        blocked["check_var"].set(False)
        normal = self._normal_item()
        normal["check_var"].set(False)
        app = FakeStartApp([blocked, normal])
        app.start_selected_download = lambda: None
        gui_app.YoutubeDownloaderApp.start_all_download(app)
        assert blocked["check_var"].get() is False, "차단 항목을 다시 체크하면 가드가 무력해진다"
        assert normal["check_var"].get() is True

    def test_일반_실패_항목은_재시도할_수_있다(self, monkeypatch):
        failed = self._normal_item()
        failed["status"] = "failed"
        app = FakeStartApp([failed])
        cap = _start(app, monkeypatch)
        assert cap["args"][0] == [0], "일반 실패는 재시도 가능해야 한다"


# --------------------------------------------------------------------------
# 회귀: 저장 폴더가 유효하지 않으면 다운로드를 시작하면 안 된다
# --------------------------------------------------------------------------
class TestInvalidSaveDirStops:
    def test_없는_폴더면_배치를_시작하지_않는다(self, monkeypatch, tmp_path):
        item = {"title": "곡", "url": "https://youtu.be/n61ULEU7CO0",
                "check_var": FakeVar(True), "status": "waiting"}
        app = FakeStartApp([item])
        app.save_dir_var = FakeVar(str(tmp_path / "없는폴더"))
        cap = _start(app, monkeypatch)
        assert not cap.get("started"), "안내만 하고 cwd 로 받아버리면 파일이 엉뚱한 곳에 쌓인다"
        assert app.errors
        assert app.locked is not True, "시작하지 않았으면 컨트롤을 잠그면 안 된다"

    def test_유효한_폴더면_정상_시작한다(self, monkeypatch, tmp_path):
        item = {"title": "곡", "url": "https://youtu.be/n61ULEU7CO0",
                "check_var": FakeVar(True), "status": "waiting"}
        app = FakeStartApp([item])
        app.save_dir_var = FakeVar(str(tmp_path))
        cap = _start(app, monkeypatch)
        assert cap.get("started")
        assert cap["args"][1]["save_dir"] == str(tmp_path)


# --------------------------------------------------------------------------
# 회귀: 대문자 도메인도 같은 영상으로 잡아야 한다
# --------------------------------------------------------------------------
class TestVideoIdCaseInsensitive:
    def test_대문자_도메인도_ID를_뽑는다(self):
        assert gui_app.extract_video_id("https://www.YouTube.com/watch?v=n61ULEU7CO0") == "n61ULEU7CO0"
        assert gui_app.extract_video_id("https://YOUTU.BE/n61ULEU7CO0") == "n61ULEU7CO0"

    def test_대소문자가_달라도_같은_영상으로_본다(self):
        assert gui_app.is_same_video(
            "https://www.youtube.com/watch?v=n61ULEU7CO0",
            "https://www.YouTube.com/watch?v=n61ULEU7CO0",
        ) is True

    def test_구형_v_경로도_인식한다(self):
        assert gui_app.extract_video_id("https://www.youtube.com/v/n61ULEU7CO0") == "n61ULEU7CO0"

    def test_영상_ID_자체의_대소문자는_보존한다(self):
        assert gui_app.extract_video_id("https://youtu.be/AbCdEfGhIjK") == "AbCdEfGhIjK"


class TestAlreadyQueuedFeedback:
    def _app(self, queue_urls, selected_url):
        app = FakeStartApp([{"title": "q", "url": u, "check_var": FakeVar(True),
                             "status": "waiting"} for u in queue_urls])
        app.search_scroll = types.SimpleNamespace(search_results_data=[{
            "title": "곡", "url": selected_url, "duration": "03:00",
            "uploader": "ch", "check_var": FakeVar(True)}])
        app.queue_scroll = types.SimpleNamespace(populate_queue=lambda *a: None)
        app.tabview = types.SimpleNamespace(set=lambda *a: None)
        app.update_queue_list_ui = lambda: None
        app.pending_added_during_batch = 0
        return app

    def test_전부_이미_있으면_안내한다(self):
        url = "https://www.youtube.com/watch?v=n61ULEU7CO0"
        app = self._app([url], url)
        gui_app.YoutubeDownloaderApp.add_selected_to_queue(app)
        assert len(app.queue_items) == 1
        assert app.errors, "조용히 넘어가면 사용자는 추가된 줄 안다"
        assert "이미 대기열" in app.errors[0]

    def test_새로_추가되면_안내하지_않는다(self, monkeypatch):
        monkeypatch.setattr(gui_app.ctk, "BooleanVar", FakeVar)
        app = self._app(["https://youtu.be/aqz-KE-bpKQ"],
                        "https://www.youtube.com/watch?v=n61ULEU7CO0")
        gui_app.YoutubeDownloaderApp.add_selected_to_queue(app)
        assert len(app.queue_items) == 2
        assert app.errors == []


# ==========================================================================
# minor 묶음 A: 순수 함수 정밀화
# ==========================================================================
class TestVideoIdStrictness:
    def test_유튜브가_아닌_호스트는_ID를_뽑지_않는다(self):
        assert gui_app.extract_video_id("https://evil.com/watch?v=n61ULEU7CO0") is None
        assert gui_app.extract_video_id("https://notyoutube.com/embed/n61ULEU7CO0") is None

    def test_도메인을_포함한_사칭_호스트도_거른다(self):
        assert gui_app.extract_video_id("https://youtube.com.evil.net/watch?v=n61ULEU7CO0") is None

    def test_서브도메인은_허용한다(self):
        assert gui_app.extract_video_id("https://m.youtube.com/watch?v=n61ULEU7CO0") == "n61ULEU7CO0"
        assert gui_app.extract_video_id("https://music.youtube.com/watch?v=n61ULEU7CO0") == "n61ULEU7CO0"

    def test_12자_이상_토큰은_앞_11자로_자르지_않는다(self):
        assert gui_app.extract_video_id("https://youtu.be/aaaaaaaaaaaaBBB") is None

    def test_양쪽_모두_비어있으면_같은_영상이_아니다(self):
        assert gui_app.is_same_video("", "") is False
        assert gui_app.is_same_video(None, None) is False
        assert gui_app.is_same_video("   ", "") is False


class TestBatchResultDetail:
    def test_예외로_일부만_처리되면_성공이_아니다(self):
        text, ok = gui_app.describe_batch_result(2, 0, 0, total=5)
        assert ok is False, "5곡 중 2곡만 처리됐는데 전부 성공으로 보고하면 안 된다"

    def test_전부_처리하고_전부_성공하면_성공이다(self):
        text, ok = gui_app.describe_batch_result(5, 0, 0, total=5)
        assert ok is True

    def test_단위를_바꿀_수_있다(self):
        text, _ = gui_app.describe_batch_result(2, 0, 0, unit="편")
        assert "2편" in text

    def test_기본_단위는_곡이다(self):
        text, _ = gui_app.describe_batch_result(2, 0, 0)
        assert "2곡" in text


class TestBatchDetailMessage:
    def test_실패가_있을_때만_사유_안내를_한다(self):
        assert "사유" in gui_app.describe_batch_detail(1, 1, 0)

    def test_중단만_있으면_사유_안내를_하지_않는다(self):
        detail = gui_app.describe_batch_detail(1, 0, 2)
        assert "사유" not in detail
        assert "중단" in detail

    def test_전부_성공이면_안내가_없다(self):
        assert gui_app.describe_batch_detail(3, 0, 0) == ""


class TestBatchProgress:
    def test_전량_실패면_진행바를_채우지_않는다(self):
        assert gui_app.batch_progress_value(0, 3, 0) == 0.0

    def test_전부_성공이면_가득_채운다(self):
        assert gui_app.batch_progress_value(3, 0, 0) == 1.0

    def test_일부_성공은_비율만큼만_채운다(self):
        assert gui_app.batch_progress_value(1, 1, 0) == 0.5

    def test_아무것도_없으면_0이다(self):
        assert gui_app.batch_progress_value(0, 0, 0) == 0.0


# ==========================================================================
# minor 묶음 B: 잠금과 상태 복구
# ==========================================================================
class TestLockedWidgetNames:
    def test_잠금_대상_위젯_이름이_실제로_존재한다(self):
        """getattr 기본값 None 때문에 오타가 무증상이 되는 것을 막는 회귀 테스트."""
        import inspect
        src = inspect.getsource(gui_app.YoutubeDownloaderApp.set_controls_locked)
        assert "LOCKED_WIDGETS" in src, "잠금 대상은 상수로 두어야 검증할 수 있다"
        assert isinstance(gui_app.LOCKED_WIDGETS, tuple)
        assert len(gui_app.LOCKED_WIDGETS) >= 12

    def test_위젯_이름은_생성부에_모두_존재한다(self):
        import re as _re
        src = io.open("gui_app.py", encoding="utf-8").read() if False else None
        with open("gui_app.py", encoding="utf-8") as fh:
            code = fh.read()
        missing = [n for n in gui_app.LOCKED_WIDGETS if f"self.{n} = ctk." not in code]
        assert missing == [], f"생성되지 않는 위젯 이름: {missing}"


class TestStartFailureRecovery:
    def _app(self):
        item = {"title": "곡", "url": "https://youtu.be/n61ULEU7CO0",
                "check_var": FakeVar(True), "status": "waiting"}
        app = FakeStartApp([item])
        return app

    def test_스레드_기동_실패시_잠금이_풀린다(self, monkeypatch, tmp_path):
        app = self._app()
        app.save_dir_var = FakeVar(str(tmp_path))

        class BoomThread:
            def __init__(self, **kwargs):
                pass

            def start(self):
                raise RuntimeError("스레드 생성 실패")

        monkeypatch.setattr(gui_app.threading, "Thread", BoomThread)
        gui_app.YoutubeDownloaderApp.start_selected_download(app)

        assert app.batch_running is False, "기동에 실패했는데 실행 중으로 남으면 영구 잠금이다"
        assert app.locked is False
        assert app.errors


class TestStopButtonAppearance:
    def test_중단_요청_후_버튼_색이_회색으로_바뀐다(self):
        calls = []

        class App:
            batch_running = True
            stop_requested = False
            stop_message = None
            stop_download_btn = types.SimpleNamespace(configure=lambda **k: calls.append(k))
            queue_status_lbl = types.SimpleNamespace(configure=lambda **k: None)

        gui_app.YoutubeDownloaderApp.request_stop_download(App())
        states = [c for c in calls if c.get("state") == "disabled"]
        assert states, "중단 버튼은 비활성화돼야 한다"
        assert any("fg_color" in c for c in calls), "빨간 배경 그대로면 눌리는 버튼처럼 보인다"


# ==========================================================================
# minor 묶음 C: 검색 견고성
# ==========================================================================
class FakeSearchApp:
    def __init__(self, query="키워드"):
        self.searching = False
        self.search_generation = 0
        self.search_btn_state = {}
        self.search_btn = types.SimpleNamespace(
            configure=lambda **k: self.search_btn_state.update(k))
        self.search_entry = types.SimpleNamespace(get=lambda: query)
        self.errors = []
        self.after_calls = []
        self.search_scroll = types.SimpleNamespace(populate_results=lambda *a, **k: None)

    def show_error(self, msg):
        self.errors.append(msg)

    def search_thread_target(self, query, generation):
        pass

    def after(self, delay, fn=None, *args):
        self.after_calls.append((delay, fn, args))
        return f"job{len(self.after_calls)}"

    def after_cancel(self, job):
        pass

    is_current_search = gui_app.YoutubeDownloaderApp.is_current_search
    finish_search = gui_app.YoutubeDownloaderApp.finish_search
    on_search_timeout = gui_app.YoutubeDownloaderApp.on_search_timeout


class TestSearchRobustness:
    def _start(self, app, monkeypatch, thread_cls=None):
        class OkThread:
            def __init__(self, **kwargs):
                pass

            def start(self):
                pass

        monkeypatch.setattr(gui_app.threading, "Thread", thread_cls or OkThread)
        gui_app.YoutubeDownloaderApp.start_search(app)

    def test_검색_중_재입력은_안내를_준다(self, monkeypatch):
        app = FakeSearchApp()
        self._start(app, monkeypatch)
        assert app.searching is True
        app.errors.clear()
        gui_app.YoutubeDownloaderApp.start_search(app)
        assert app.errors, "아무 피드백 없이 무시하면 사용자는 고장으로 느낀다"

    def test_스레드_기동_실패시_검색_상태가_복구된다(self, monkeypatch):
        app = FakeSearchApp()

        class BoomThread:
            def __init__(self, **kwargs):
                pass

            def start(self):
                raise RuntimeError("기동 실패")

        self._start(app, monkeypatch, BoomThread)
        assert app.searching is False, "복구하지 않으면 검색이 영영 막힌다"
        assert app.search_btn_state.get("state") == "normal"
        assert app.errors

    def test_세대가_어긋나도_검색_잠금은_풀린다(self):
        app = FakeSearchApp()
        app.searching = True
        app.search_generation = 9
        gui_app.YoutubeDownloaderApp.on_search_success(app, [], generation=3)
        assert app.searching is False, "가드가 발동해도 버튼이 영구 잠기면 안 된다"

    def test_타임아웃이_예약된다(self, monkeypatch):
        app = FakeSearchApp()
        self._start(app, monkeypatch)
        delays = [d for d, _fn, _a in app.after_calls]
        assert any(d >= 10000 for d in delays), "응답이 없으면 풀어줄 안전장치가 필요하다"

    def test_타임아웃이_현재_검색만_해제한다(self):
        app = FakeSearchApp()
        app.searching = True
        app.search_generation = 4
        gui_app.YoutubeDownloaderApp.on_search_timeout(app, 2)   # 낡은 세대
        assert app.searching is True
        gui_app.YoutubeDownloaderApp.on_search_timeout(app, 4)   # 현재 세대
        assert app.searching is False
        assert app.errors


# ==========================================================================
# minor 묶음 D: 렌더링 견고성
# ==========================================================================
class TestRenderRobustness:
    def _results(self, n):
        return [{"title": f"곡{i}", "url": f"u{i}", "duration": "03:00",
                 "uploader": "ch", "thumbnail": None} for i in range(n)]

    def _frame(self, monkeypatch):
        frame = FakeSearchFrame()
        monkeypatch.setattr(gui_app.ctk, "BooleanVar", lambda value=False: {"v": value})
        return frame

    def test_한_행이_실패해도_나머지가_그려진다(self, monkeypatch):
        frame = self._frame(monkeypatch)
        failed = []

        def flaky(idx, item):
            if idx == 3:
                failed.append(idx)
                raise RuntimeError("이 행만 실패")
            frame.rendered_rows.append(idx)
            frame.search_widgets.append(FakeSearchFrame.Row())

        frame._render_row = flaky
        gui_app.ScrollableSearchFrame.populate_results(frame, self._results(10))
        frame.drain()
        assert failed == [3]
        assert len(frame.rendered_rows) == 9, "한 행 실패로 나머지가 사라지면 안 된다"

    def test_데이터가_비워지면_렌더링을_멈춘다(self, monkeypatch):
        """새 검색이 데이터를 지운 뒤 낡은 청크가 돌면 IndexError 가 난다."""
        frame = self._frame(monkeypatch)
        gui_app.ScrollableSearchFrame.populate_results(frame, self._results(50))
        frame.search_results_data.clear()          # 새 검색이 지운 상황을 흉내
        frame.drain()                              # 예약된 낡은 청크 실행
        # 예외 없이 조용히 멈춰야 한다

    def test_결과_0건_안내는_초기_안내와_다르다(self, monkeypatch):
        frame = self._frame(monkeypatch)
        texts = []

        class FakeLabel:
            def __init__(self, *a, **k):
                texts.append(k.get("text", ""))

            def pack(self, **k):
                pass

        monkeypatch.setattr(gui_app.ctk, "CTkLabel", FakeLabel)
        gui_app.ScrollableSearchFrame.populate_results(
            frame, [], empty_text=gui_app.SEARCH_NO_RESULT_TEXT)
        assert texts and "일치하는" in texts[0], "초기 안내와 같으면 결과 없음을 구분할 수 없다"

    def test_검색_성공_경로가_결과없음_문구를_넘긴다(self):
        import inspect
        src = inspect.getsource(gui_app.YoutubeDownloaderApp.on_search_success)
        assert "SEARCH_NO_RESULT_TEXT" in src, "empty_text 를 넘기지 않으면 인자가 죽은 코드가 된다"

    def test_렌더링_함수에_한번만_도는_반복문_꼼수가_없다(self):
        import inspect
        src = inspect.getsource(gui_app.ScrollableSearchFrame._render_row)
        assert "_once" not in src, "for _once in (0,) 는 continue/break 를 넣는 순간 조용히 오작동한다"


# ==========================================================================
# minor 묶음 E/F: 진행률 표시와 종료 처리
# ==========================================================================
class TestProgressIndexGuard:
    def test_인덱스가_범위를_벗어나면_그리지_않는다(self):
        """워커가 current_download_idx 를 바꾸는 사이에도 죽지 않아야 한다."""
        calls = []

        class App:
            batch_running = True
            current_download_idx = 5          # 범위 밖
            queue_items = [{"title": "곡", "status": "downloading"}]
            stop_requested = False
            stop_message = None
            current_download_status = {"status": "downloading", "percent": 0.5,
                                       "speed": "1MB/s", "eta": "00:10"}
            overall_progress = 0.5
            active_format = "MP3"
            convert_started_at = None
            convert_pulse = 0

            def update_progress_loop(self):
                pass

            def after(self, *a):
                calls.append(a)

            queue_status_lbl = types.SimpleNamespace(configure=lambda **k: None)
            cur_prog_bar = types.SimpleNamespace(set=lambda v: None)
            cur_stats_lbl = types.SimpleNamespace(configure=lambda **k: None)
            total_prog_bar = types.SimpleNamespace(set=lambda v: None)
            overall_status_lbl = types.SimpleNamespace(configure=lambda **k: None)

        gui_app.YoutubeDownloaderApp.update_progress_loop(App())
        assert calls, "예외로 죽으면 이후 모든 진행 표시가 멈춘다"


class TestStopSuppressesConvertPulse:
    def test_중단_요청_후에는_변환_경과를_갱신하지_않는다(self):
        stats = []

        class App:
            batch_running = True
            current_download_idx = 0
            queue_items = [{"title": "곡", "status": "converting"}]
            stop_requested = True
            stop_message = "변환을 중단했습니다."
            current_download_status = {"status": "converting", "percent": 1.0,
                                       "speed": "", "eta": "--:--"}
            overall_progress = 0.5
            active_format = "MP3"
            convert_started_at = None
            convert_pulse = 0

            def update_progress_loop(self):
                pass

            def after(self, *a):
                pass

            queue_status_lbl = types.SimpleNamespace(configure=lambda **k: None)
            cur_prog_bar = types.SimpleNamespace(set=lambda v: None)
            cur_stats_lbl = types.SimpleNamespace(configure=lambda **k: stats.append(k.get("text", "")))
            total_prog_bar = types.SimpleNamespace(set=lambda v: None)
            overall_status_lbl = types.SimpleNamespace(configure=lambda **k: None)

        gui_app.YoutubeDownloaderApp.update_progress_loop(App())
        assert not any("경과" in t for t in stats), "중단했는데 변환 경과가 계속 늘면 혼란스럽다"


class TestClosingCleansConversion:
    def test_종료시_변환_프로세스를_정리한다(self, monkeypatch):
        killed = []
        monkeypatch.setattr(gui_app, "terminate_child_ffmpeg",
                            lambda: killed.append(True) or 1)
        app = FakeClosingApp(batch_running=True)
        gui_app.YoutubeDownloaderApp.on_closing(app)
        assert killed, "변환 중 종료하면 ffmpeg 를 먼저 끊어야 워커가 정리된다"

    def test_취소하면_변환을_끊지_않는다(self, monkeypatch):
        killed = []
        monkeypatch.setattr(gui_app, "terminate_child_ffmpeg",
                            lambda: killed.append(True) or 1)
        app = FakeClosingApp(batch_running=True)
        app.confirm_result = False
        gui_app.YoutubeDownloaderApp.on_closing(app)
        assert killed == []


# ==========================================================================
# minor 묶음 G: 오류 대화상자
# ==========================================================================
class TestErrorMessageMerge:
    def test_새_메시지를_아래에_덧붙인다(self):
        merged = gui_app.merge_error_messages("첫 번째", "두 번째")
        assert "첫 번째" in merged and "두 번째" in merged

    def test_같은_메시지는_중복해서_쌓지_않는다(self):
        merged = gui_app.merge_error_messages("같은 말", "같은 말")
        assert merged.count("같은 말") == 1

    def test_기존이_비어있으면_새_메시지만_남는다(self):
        assert gui_app.merge_error_messages("", "새 메시지") == "새 메시지"


class TestDialogWidth:
    def test_긴_한_줄은_창을_넓힌다(self):
        narrow, _ = gui_app.measure_error_dialog("짧다")
        wide, _ = gui_app.measure_error_dialog("가" * 120)
        assert wide >= narrow

    def test_너비는_상한을_넘지_않는다(self):
        width, _ = gui_app.measure_error_dialog("가" * 5000)
        assert width <= gui_app.DIALOG_MAX_WIDTH

    def test_높이는_상한을_넘지_않는다(self):
        _, height = gui_app.measure_error_dialog("줄" + chr(10) * 500)
        assert height <= gui_app.DIALOG_MAX_HEIGHT

    def test_최소_크기를_보장한다(self):
        width, height = gui_app.measure_error_dialog("")
        assert width >= gui_app.DIALOG_MIN_WIDTH
        assert height >= gui_app.DIALOG_MIN_HEIGHT


class TestSingleDialog:
    def test_show_error_가_기존_창을_재사용한다(self):
        import inspect
        src = inspect.getsource(gui_app.YoutubeDownloaderApp.show_error)
        assert "_error_win" in src, "창을 추적하지 않으면 대화상자가 계속 쌓인다"
        assert "merge_error_messages" in src
