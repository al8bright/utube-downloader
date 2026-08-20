"""테스트 공용 스텁.

GUI 창을 띄우지 않고 언바운드 메서드를 돌리기 위한 최소 대역들.
"""
import os
import types

from utube_downloader import app as app_module
from utube_downloader.widgets import ScrollableSearchFrame


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
        self.job_seq = 0

    def after(self, delay, fn, *args):
        job = f"job{self.job_seq}"
        self.job_seq += 1
        self.after_queue.append((job, fn, args))
        return job

    def after_cancel(self, job):
        # 실제 Tk 처럼 지정된 job 만 취소한다.
        # 큐를 통째로 비우면 취소 테스트가 스텁의 동작만 검증하게 된다.
        before = len(self.after_queue)
        self.after_queue[:] = [q for q in self.after_queue if q[0] != job]
        if len(self.after_queue) == before:
            raise ValueError(f"알 수 없는 after id: {job}")

    # 실제 클래스의 메서드를 그대로 빌려 쓴다
    cancel_render = ScrollableSearchFrame.cancel_render
    _render_chunk = ScrollableSearchFrame._render_chunk

    class Row:
        def destroy(self):
            pass

    def _render_row(self, idx, item):
        self.rendered_rows.append(idx)
        self.search_widgets.append(FakeSearchFrame.Row())

    def drain(self):
        """예약된 렌더링을 끝까지 실행한다."""
        while self.after_queue:
            _job, fn, args = self.after_queue.pop(0)
            fn(*args)

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

    is_current_search = app_module.YoutubeDownloaderApp.is_current_search
    finish_search = app_module.YoutubeDownloaderApp.finish_search
    on_search_timeout = app_module.YoutubeDownloaderApp.on_search_timeout

def start_download(app, monkeypatch):
    """start_selected_download 를 실제 스레드 없이 돌린다."""
    captured = {}

    class FakeThread:
        def __init__(self, target=None, args=(), daemon=None):
            captured["args"] = args

        def start(self):
            captured["started"] = True

    monkeypatch.setattr(app_module.threading, "Thread", FakeThread)
    app_module.YoutubeDownloaderApp.start_selected_download(app)
    return captured
