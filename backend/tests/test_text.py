"""표시 문자열과 수치."""

from utube.core import text


class TestDuration:
    def test_정상_초를_분초로_변환한다(self):
        assert text.format_duration(125) == "02:05"

    def test_한시간_이상은_시분초로_변환한다(self):
        assert text.format_duration(3725) == "01:02:05"

    def test_라이브방송의_None_은_기본값(self):
        assert text.format_duration(None) == text.UNKNOWN_TIME

    def test_float_초도_변환한다(self):
        assert text.format_duration(125.7) == "02:05"

    def test_문자열이나_음수에도_죽지_않는다(self):
        assert text.format_duration("abc") == text.UNKNOWN_TIME
        assert text.format_duration(-1) == text.UNKNOWN_TIME


class TestEtaSpeed:
    def test_eta(self):
        assert text.format_eta(75) == "01:15"
        assert text.format_eta(75.9) == "01:15"
        assert text.format_eta(None) == text.UNKNOWN_TIME

    def test_속도(self):
        assert text.format_speed(2048) == "2.00 KB/s"
        assert text.format_speed(3 * 1024 * 1024) == "3.00 MB/s"
        assert text.format_speed(None) == ""
        assert text.format_speed(0) == ""


class TestBatchResult:
    def test_전부_성공(self):
        assert text.describe_batch_result(3, 0, 0) == ("완료 3곡", True)

    def test_전부_실패면_성공으로_보고하지_않는다(self):
        msg, ok = text.describe_batch_result(0, 2, 0)
        assert ok is False and "실패 2곡" in msg

    def test_일부_실패도_성공이_아니다(self):
        assert text.describe_batch_result(2, 1, 0)[1] is False

    def test_중단이_섞이면_중단을_알린다(self):
        msg, ok = text.describe_batch_result(1, 0, 2)
        assert "중단 2곡" in msg and ok is False

    def test_아무것도_안했으면_성공이_아니다(self):
        assert text.describe_batch_result(0, 0, 0) == ("처리한 항목이 없습니다.", False)

    def test_예외로_일부만_처리되면_성공이_아니다(self):
        assert text.describe_batch_result(2, 0, 0, total=3)[1] is False

    def test_단위를_바꿀_수_있다(self):
        assert text.describe_batch_result(2, 0, 0, unit="편")[0] == "완료 2편"
        assert text.unit_for("MP4") == "편" and text.unit_for("MP3") == "곡"

    def test_보조_설명(self):
        assert "사유" in text.describe_batch_detail(1, 1, 0)
        assert "중단" in text.describe_batch_detail(1, 0, 1)
        assert text.describe_batch_detail(1, 0, 0) == ""

    def test_진행바는_성공한_만큼만_채운다(self):
        assert text.batch_progress_value(0, 3, 0) == 0.0
        assert text.batch_progress_value(3, 0, 0) == 1.0
        assert text.batch_progress_value(1, 1, 0) == 0.5
        assert text.batch_progress_value(0, 0, 0) == 0.0


class TestPostprocess:
    def test_MP4_는_병합(self):
        assert "병합" in text.describe_postprocess_stage("MP4")

    def test_음성은_변환(self):
        assert "MP3 변환" in text.describe_postprocess_stage("MP3")
        assert "FLAC 변환" in text.describe_postprocess_stage("FLAC")


class TestSearchResult:
    def test_영상은_화면용_사전으로_바뀐다(self):
        r = text.search_result_from_entry({"id": "n61ULEU7CO0", "ie_key": "Youtube", "title": "곡",
                                           "url": "https://www.youtube.com/watch?v=n61ULEU7CO0",
                                           "duration": 61, "channel": "채널"})
        assert r == {"id": "n61ULEU7CO0", "title": "곡", "url": "https://www.youtube.com/watch?v=n61ULEU7CO0",
                     "duration": "01:01", "uploader": "채널",
                     "thumbnail": "https://i.ytimg.com/vi/n61ULEU7CO0/mqdefault.jpg"}

    def test_채널과_재생목록은_거른다(self):
        assert text.search_result_from_entry({"id": "UC" + "x" * 22, "ie_key": "YoutubeTab"}) is None
        assert text.search_result_from_entry({"id": "PLabc", "ie_key": "Youtube"}) is None

    def test_링크가_없으면_영상_ID로_만든다(self):
        r = text.search_result_from_entry({"id": "n61ULEU7CO0", "url": "n61ULEU7CO0"})
        assert r["url"] == "https://www.youtube.com/watch?v=n61ULEU7CO0"
