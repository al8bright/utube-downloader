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

            def place(self, **k):
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

            def place(self, **k):
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

            def place(self, **k):
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


# ==========================================================================
# 검색 결과를 받는 대로 이어 붙이기
# ==========================================================================
class TestAppendResults:
    def _results(self, start, n):
        return [{"title": f"곡{i}", "url": f"u{i}", "duration": "03:00",
                 "uploader": "ch", "thumbnail": None} for i in range(start, start + n)]

    def _frame(self, monkeypatch):
        monkeypatch.setattr(app_module.ctk, "BooleanVar", lambda value=False: {"v": value})
        return FakeSearchFrame()

    def test_이어_붙인_결과도_끝까지_그려진다(self, monkeypatch):
        frame = self._frame(monkeypatch)
        frame.populate_results(self._results(0, 20))
        frame.drain()
        frame.append_results(self._results(20, 20))
        frame.drain()
        assert frame.rendered_rows == list(range(40)), "앞서 그린 행은 다시 그리지 않고 뒤만 붙인다"
        assert len(frame.search_results_data) == 40

    def test_그리는_도중에_붙여도_중복_없이_이어진다(self, monkeypatch):
        frame = self._frame(monkeypatch)
        frame.populate_results(self._results(0, 20))
        frame.append_results(self._results(20, 20))   # 첫 페이지를 아직 다 못 그린 상태
        frame.drain()
        assert frame.rendered_rows == list(range(40))

    def test_비어_있으면_처음부터_채운다(self, monkeypatch):
        frame = self._frame(monkeypatch)
        frame.append_results(self._results(0, 5))
        frame.drain()
        assert frame.rendered_rows == list(range(5))


class TestThumbnailFit:
    def test_4대3_이미지도_찌그러지지_않고_16대9로_잘린다(self):
        from PIL import Image
        from utube_downloader.widgets.search_list import THUMB_SIZE, fit_thumbnail

        # 4:3 에 위아래 검은 띠가 든 옛 hqdefault 모양
        image = Image.new("RGB", (480, 360), "black")
        image.paste(Image.new("RGB", (480, 270), "white"), (0, 45))
        fitted = fit_thumbnail(image, THUMB_SIZE)
        assert fitted.size == THUMB_SIZE
        assert fitted.getpixel((THUMB_SIZE[0] // 2, THUMB_SIZE[1] // 2)) == (255, 255, 255)


class TestTitleClip:
    def test_짧은_제목은_그대로(self):
        from utube_downloader.widgets.search_list import clip_to_lines
        assert clip_to_lines("IU 'Holssi' Live Clip", 400, 12) == "IU 'Holssi' Live Clip"

    def test_긴_제목은_두_줄_분량에서_자른다(self):
        from utube_downloader.widgets.search_list import char_units, clip_to_lines
        title = "좋아하는 걸 한 줄 알았는데 잘하는 걸 했구나 " * 6
        clipped = clip_to_lines(title, 300, 12)
        assert clipped.endswith("…")
        units = sum(char_units(ch) for ch in clipped[:-1])
        assert units * 12 <= 2 * 300, "두 줄을 넘으면 아래 행을 덮는다"

    def test_라틴_문자는_한글보다_좁게_센다(self):
        from utube_downloader.widgets.search_list import char_units
        assert char_units("a") < char_units("가")
