"""app 모듈 — 종료, 잠금, 검색, 대기열 시작."""
import os
import types

from utube_downloader import app as app_module
from .stubs import FakeClosingApp, FakeSearchApp, FakeStartApp, FakeVar, start_download


class TestOnClosing:
    def test_다운로드_중이_아니면_바로_닫는다(self):
        app = FakeClosingApp(batch_running=False)
        app_module.YoutubeDownloaderApp.on_closing(app)
        assert app.confirm_asked is False
        assert app.destroyed is True

    def test_다운로드_중이면_사용자에게_확인을_받는다(self):
        app = FakeClosingApp(batch_running=True)
        app_module.YoutubeDownloaderApp.on_closing(app)
        assert app.confirm_asked is True
        assert app.destroyed is True

    def test_사용자가_취소하면_닫지_않는다(self):
        app = FakeClosingApp(batch_running=True)
        app.confirm_result = False
        app_module.YoutubeDownloaderApp.on_closing(app)
        assert app.destroyed is False, "취소했는데 창이 닫히면 진행 중인 다운로드가 소실된다"

    def test_닫을때_중단_플래그를_세운다(self):
        app = FakeClosingApp(batch_running=True)
        app_module.YoutubeDownloaderApp.on_closing(app)
        assert app.stop_requested is True

    def test_닫을때_썸네일_워커를_취소하며_종료한다(self):
        app = FakeClosingApp(batch_running=False)
        app_module.YoutubeDownloaderApp.on_closing(app)
        assert app.executor.shutdown_calls, "executor.shutdown 이 호출되지 않으면 프로세스가 남는다"
        assert app.executor.shutdown_calls[0]["cancel_futures"] is True

    def test_닫을때_진행중인_렌더링도_취소한다(self):
        app = FakeClosingApp(batch_running=False)
        app_module.YoutubeDownloaderApp.on_closing(app)
        assert app.render_cancelled is True

    def test_렌더링_취소가_실패해도_워커는_종료된다(self):
        app = FakeClosingApp(batch_running=False)

        def boom():
            raise RuntimeError("취소 실패")

        app.search_scroll.cancel_render = boom
        app_module.YoutubeDownloaderApp.on_closing(app)
        assert app.executor.shutdown_calls, "앞 단계 실패로 executor 종료를 건너뛰면 프로세스가 남는다"

    def test_취소하면_워커를_종료하지_않는다(self):
        app = FakeClosingApp(batch_running=True)
        app.confirm_result = False
        app_module.YoutubeDownloaderApp.on_closing(app)
        assert app.executor.shutdown_calls == []

class TestClosingCleansConversion:
    def test_종료시_변환_프로세스를_정리한다(self, monkeypatch):
        killed = []
        monkeypatch.setattr(app_module, "terminate_child_ffmpeg",
                            lambda: killed.append(True) or 1)
        app = FakeClosingApp(batch_running=True)
        app_module.YoutubeDownloaderApp.on_closing(app)
        assert killed, "변환 중 종료하면 ffmpeg 를 먼저 끊어야 워커가 정리된다"

    def test_취소하면_변환을_끊지_않는다(self, monkeypatch):
        killed = []
        monkeypatch.setattr(app_module, "terminate_child_ffmpeg",
                            lambda: killed.append(True) or 1)
        app = FakeClosingApp(batch_running=True)
        app.confirm_result = False
        app_module.YoutubeDownloaderApp.on_closing(app)
        assert killed == []

# ==========================================================================
# minor 묶음 B: 잠금과 상태 복구
# ==========================================================================
class TestLockedWidgetNames:
    def test_잠금_대상_위젯_이름이_실제로_존재한다(self):
        """getattr 기본값 None 때문에 오타가 무증상이 되는 것을 막는 회귀 테스트."""
        import inspect
        src = inspect.getsource(app_module.YoutubeDownloaderApp.set_controls_locked)
        assert "LOCKED_WIDGETS" in src, "잠금 대상은 상수로 두어야 검증할 수 있다"
        assert isinstance(app_module.LOCKED_WIDGETS, tuple)
        assert len(app_module.LOCKED_WIDGETS) >= 12

    def test_위젯_이름은_생성부에_모두_존재한다(self):
        """오타나 이름 변경이 getattr 기본값 None 뒤에 숨지 않도록 소스에서 확인한다."""
        from .test_project_health import read_all

        code = read_all()
        missing = [n for n in app_module.LOCKED_WIDGETS
                   if f"self.{n} = ctk." not in code and f"app.{n} = ctk." not in code]
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

        monkeypatch.setattr(app_module.threading, "Thread", BoomThread)
        app_module.YoutubeDownloaderApp.start_selected_download(app)

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

        app_module.YoutubeDownloaderApp.request_stop_download(App())
        states = [c for c in calls if c.get("state") == "disabled"]
        assert states, "중단 버튼은 비활성화돼야 한다"
        # 외곽선 버튼이므로 테두리/글자색으로 비활성 상태를 드러낸다.
        # 어떤 형태로든 시각 변화가 없으면 '눌리는데 반응 없는 버튼' 이 된다.
        visual = {"fg_color", "border_color", "text_color"}
        assert any(visual & set(c) for c in calls), "색 변화가 없으면 눌리는 버튼처럼 보인다"

class TestSearchRobustness:
    def _start_search(self, app, monkeypatch, thread_cls=None):
        class OkThread:
            def __init__(self, **kwargs):
                pass

            def start(self):
                pass

        monkeypatch.setattr(app_module.threading, "Thread", thread_cls or OkThread)
        app_module.YoutubeDownloaderApp.start_search(app)

    def test_검색_중_재입력은_안내를_준다(self, monkeypatch):
        app = FakeSearchApp()
        self._start_search(app, monkeypatch)
        assert app.searching is True
        app.errors.clear()
        app_module.YoutubeDownloaderApp.start_search(app)
        assert app.errors, "아무 피드백 없이 무시하면 사용자는 고장으로 느낀다"

    def test_스레드_기동_실패시_검색_상태가_복구된다(self, monkeypatch):
        app = FakeSearchApp()

        class BoomThread:
            def __init__(self, **kwargs):
                pass

            def start(self):
                raise RuntimeError("기동 실패")

        self._start_search(app, monkeypatch, BoomThread)
        assert app.searching is False, "복구하지 않으면 검색이 영영 막힌다"
        assert app.search_btn_state.get("state") == "normal"
        assert app.errors

    def test_세대가_어긋나도_검색_잠금은_풀린다(self):
        app = FakeSearchApp()
        app.searching = True
        app.search_generation = 9
        app_module.YoutubeDownloaderApp.on_search_success(app, [], generation=3)
        assert app.searching is False, "가드가 발동해도 버튼이 영구 잠기면 안 된다"

    def test_타임아웃이_예약된다(self, monkeypatch):
        app = FakeSearchApp()
        self._start_search(app, monkeypatch)
        delays = [d for d, _fn, _a in app.after_calls]
        assert any(d >= 10000 for d in delays), "응답이 없으면 풀어줄 안전장치가 필요하다"

    def test_타임아웃이_현재_검색만_해제한다(self):
        app = FakeSearchApp()
        app.searching = True
        app.search_generation = 4
        app_module.YoutubeDownloaderApp.on_search_timeout(app, 2)   # 낡은 세대
        assert app.searching is True
        app_module.YoutubeDownloaderApp.on_search_timeout(app, 4)   # 현재 세대
        assert app.searching is False
        assert app.errors

class TestBlockedPlaylistNotRetried:
    def _blocked_item(self):
        return {"title": "재생목록", "url": "https://www.youtube.com/playlist?list=PLx",
                "check_var": FakeVar(True), "status": "failed", "blocked": True}

    def _normal_item(self):
        return {"title": "곡", "url": "https://www.youtube.com/watch?v=n61ULEU7CO0",
                "check_var": FakeVar(True), "status": "waiting"}

    def test_차단된_재생목록은_다운로드_대상에서_빠진다(self, monkeypatch):
        app = FakeStartApp([self._blocked_item(), self._normal_item()])
        cap = start_download(app, monkeypatch)
        assert cap.get("started"), "정상 항목이 있으니 배치는 시작돼야 한다"
        assert cap["args"][0] == [1], "차단된 재생목록이 대상에 들어가면 영상 수백 개를 받는다"

    def test_차단_항목만_있으면_배치가_시작되지_않는다(self, monkeypatch):
        app = FakeStartApp([self._blocked_item()])
        cap = start_download(app, monkeypatch)
        assert not cap.get("started")
        assert app.errors, "받을 것이 없다는 안내가 있어야 한다"

    def test_전체_선택은_차단_항목을_체크하지_않는다(self):
        blocked = self._blocked_item()
        blocked["check_var"].set(False)
        normal = self._normal_item()
        normal["check_var"].set(False)
        app = FakeStartApp([blocked, normal])
        app.start_selected_download = lambda: None
        app_module.YoutubeDownloaderApp.start_all_download(app)
        assert blocked["check_var"].get() is False, "차단 항목을 다시 체크하면 가드가 무력해진다"
        assert normal["check_var"].get() is True

    def test_일반_실패_항목은_재시도할_수_있다(self, monkeypatch):
        failed = self._normal_item()
        failed["status"] = "failed"
        app = FakeStartApp([failed])
        cap = start_download(app, monkeypatch)
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
        cap = start_download(app, monkeypatch)
        assert not cap.get("started"), "안내만 하고 cwd 로 받아버리면 파일이 엉뚱한 곳에 쌓인다"
        assert app.errors
        assert app.locked is not True, "시작하지 않았으면 컨트롤을 잠그면 안 된다"

    def test_유효한_폴더면_정상_시작한다(self, monkeypatch, tmp_path):
        item = {"title": "곡", "url": "https://youtu.be/n61ULEU7CO0",
                "check_var": FakeVar(True), "status": "waiting"}
        app = FakeStartApp([item])
        app.save_dir_var = FakeVar(str(tmp_path))
        cap = start_download(app, monkeypatch)
        assert cap.get("started")
        assert cap["args"][1]["save_dir"] == str(tmp_path)

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
        app_module.YoutubeDownloaderApp.add_selected_to_queue(app)
        assert len(app.queue_items) == 1
        assert app.errors, "조용히 넘어가면 사용자는 추가된 줄 안다"
        assert "이미 대기열" in app.errors[0]

    def test_새로_추가되면_안내하지_않는다(self, monkeypatch):
        monkeypatch.setattr(app_module.ctk, "BooleanVar", FakeVar)
        app = self._app(["https://youtu.be/aqz-KE-bpKQ"],
                        "https://www.youtube.com/watch?v=n61ULEU7CO0")
        app_module.YoutubeDownloaderApp.add_selected_to_queue(app)
        assert len(app.queue_items) == 2
        assert app.errors == []

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

        app_module.YoutubeDownloaderApp.update_progress_loop(App())
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

        app_module.YoutubeDownloaderApp.update_progress_loop(App())
        assert not any("경과" in t for t in stats), "중단했는데 변환 경과가 계속 늘면 혼란스럽다"
