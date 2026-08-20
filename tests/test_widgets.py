"""widgets 패키지 — 목록 렌더링."""
import types

from utube_downloader import app as app_module
from utube_downloader.widgets import ScrollableSearchFrame
from .stubs import FakeSearchFrame


class TestProgressiveRender:
    def _results(self, n):
        return [{"title": f"곡{i}", "url": f"u{i}", "duration": "03:00",
                 "uploader": "ch", "thumbnail": None} for i in range(n)]

    def _frame(self, monkeypatch):
        frame = FakeSearchFrame()
        # ctk.BooleanVar 대신 가벼운 대체물을 쓴다 (GUI 없이 돌리기 위함)
        monkeypatch.setattr(app_module.ctk, "BooleanVar", lambda value=False: {"v": value})
        return frame

    def test_데이터는_즉시_전부_채워진다(self, monkeypatch):
        frame = self._frame(monkeypatch)
        ScrollableSearchFrame.populate_results(frame, self._results(100))
        assert len(frame.search_results_data) == 100, "렌더링 전에도 선택 대상 데이터는 전부 있어야 한다"

    def test_첫_호출에_전부_그리지_않는다(self, monkeypatch):
        frame = self._frame(monkeypatch)
        ScrollableSearchFrame.populate_results(frame, self._results(100))
        assert len(frame.rendered_rows) < 100, "한 번에 다 그리면 UI 가 멈춘다"

    def test_끝까지_돌리면_전부_그려진다(self, monkeypatch):
        frame = self._frame(monkeypatch)
        ScrollableSearchFrame.populate_results(frame, self._results(100))
        frame.drain()
        assert frame.rendered_rows == list(range(100))

    def test_빈_결과는_안내만_남긴다(self, monkeypatch):
        frame = self._frame(monkeypatch)

        class FakeLabel:
            def __init__(self, *a, **k):
                self.kwargs = k

            def pack(self, **k):
                pass

        monkeypatch.setattr(app_module.ctk, "CTkLabel", FakeLabel)
        ScrollableSearchFrame.populate_results(frame, [])
        assert frame.search_results_data == []
        assert len(frame.search_widgets) == 1
        assert frame.rendered_rows == []

    def test_새_검색이_들어오면_이전_렌더링을_취소한다(self, monkeypatch):
        frame = self._frame(monkeypatch)
        ScrollableSearchFrame.populate_results(frame, self._results(100))
        assert frame.after_queue, "아직 그릴 것이 남아 있어야 한다"

        class FakeLabel:
            def __init__(self, *a, **k):
                pass

            def pack(self, **k):
                pass

        monkeypatch.setattr(app_module.ctk, "CTkLabel", FakeLabel)
        ScrollableSearchFrame.populate_results(frame, [])
        assert frame.after_queue == [], "이전 렌더링을 취소하지 않으면 옛 결과가 새 화면에 섞인다"

# ==========================================================================
# minor 묶음 D: 렌더링 견고성
# ==========================================================================
class TestRenderRobustness:
    def _results(self, n):
        return [{"title": f"곡{i}", "url": f"u{i}", "duration": "03:00",
                 "uploader": "ch", "thumbnail": None} for i in range(n)]

    def _frame(self, monkeypatch):
        frame = FakeSearchFrame()
        monkeypatch.setattr(app_module.ctk, "BooleanVar", lambda value=False: {"v": value})
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
        ScrollableSearchFrame.populate_results(frame, self._results(10))
        frame.drain()
        assert failed == [3]
        assert len(frame.rendered_rows) == 9, "한 행 실패로 나머지가 사라지면 안 된다"

    def test_데이터가_비워지면_렌더링을_멈춘다(self, monkeypatch):
        """새 검색이 데이터를 지운 뒤 낡은 청크가 돌면 IndexError 가 난다."""
        frame = self._frame(monkeypatch)
        ScrollableSearchFrame.populate_results(frame, self._results(50))
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

        monkeypatch.setattr(app_module.ctk, "CTkLabel", FakeLabel)
        ScrollableSearchFrame.populate_results(
            frame, [], empty_text=app_module.SEARCH_NO_RESULT_TEXT)
        assert texts and "일치하는" in texts[0], "초기 안내와 같으면 결과 없음을 구분할 수 없다"

    def test_검색_성공_경로가_결과없음_문구를_넘긴다(self):
        import inspect
        src = inspect.getsource(app_module.YoutubeDownloaderApp.on_search_success)
        assert "SEARCH_NO_RESULT_TEXT" in src, "empty_text 를 넘기지 않으면 인자가 죽은 코드가 된다"

    def test_렌더링_함수에_한번만_도는_반복문_꼼수가_없다(self):
        import inspect
        src = inspect.getsource(ScrollableSearchFrame._render_row)
        assert "_once" not in src, "for _once in (0,) 는 continue/break 를 넣는 순간 조용히 오작동한다"

class TestSingleDialog:
    def test_show_error_가_기존_창을_재사용한다(self):
        import inspect
        src = inspect.getsource(app_module.YoutubeDownloaderApp.show_error)
        assert "_error_win" in src, "창을 추적하지 않으면 대화상자가 계속 쌓인다"
        assert "merge_error_messages" in src
