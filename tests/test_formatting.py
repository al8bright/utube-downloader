"""formatting 모듈 — 표시 문자열과 수치 계산."""
from utube_downloader import formatting as fmt


# --------------------------------------------------------------------------
# 시간 포맷: 라이브 방송(None)과 float 값에서 예외가 나면 안 된다
# --------------------------------------------------------------------------
class TestFormatDuration:
    def test_정상_초를_분초로_변환한다(self):
        assert fmt.format_duration(215) == "03:35"

    def test_한시간_이상은_시분초로_변환한다(self):
        assert fmt.format_duration(3725) == "01:02:05"

    def test_라이브방송의_None_은_예외없이_기본값을_준다(self):
        assert fmt.format_duration(None) == "--:--"

    def test_float_초도_예외없이_변환한다(self):
        assert fmt.format_duration(215.0) == "03:35"

    def test_문자열이_들어와도_죽지_않는다(self):
        assert fmt.format_duration("bad") == "--:--"

class TestFormatEta:
    def test_정상_eta를_변환한다(self):
        assert fmt.format_eta(93) == "01:33"

    def test_float_eta도_예외없이_변환한다(self):
        assert fmt.format_eta(93.4) == "01:33"

    def test_None_은_기본값을_준다(self):
        assert fmt.format_eta(None) == "--:--"

# --------------------------------------------------------------------------
# 배치 결과 보고: 전량 실패를 성공으로 보고하면 안 된다
# --------------------------------------------------------------------------
class TestBatchResultMessage:
    def test_전부_성공(self):
        text, ok = fmt.describe_batch_result(3, 0, 0)
        assert ok is True
        assert "3" in text

    def test_전부_실패면_성공으로_보고하지_않는다(self):
        text, ok = fmt.describe_batch_result(0, 3, 0)
        assert ok is False, "전량 실패인데 성공색으로 표시하면 안 된다"
        assert "실패" in text

    def test_일부_실패도_성공이_아니다(self):
        text, ok = fmt.describe_batch_result(2, 1, 0)
        assert ok is False
        assert "2" in text and "1" in text

    def test_중단이_섞이면_중단을_알린다(self):
        text, ok = fmt.describe_batch_result(1, 0, 2)
        assert "중단" in text

    def test_아무것도_안했으면_성공이_아니다(self):
        text, ok = fmt.describe_batch_result(0, 0, 0)
        assert ok is False

class TestBatchResultDetail:
    def test_예외로_일부만_처리되면_성공이_아니다(self):
        text, ok = fmt.describe_batch_result(2, 0, 0, total=5)
        assert ok is False, "5곡 중 2곡만 처리됐는데 전부 성공으로 보고하면 안 된다"

    def test_전부_처리하고_전부_성공하면_성공이다(self):
        text, ok = fmt.describe_batch_result(5, 0, 0, total=5)
        assert ok is True

    def test_단위를_바꿀_수_있다(self):
        text, _ = fmt.describe_batch_result(2, 0, 0, unit="편")
        assert "2편" in text

    def test_기본_단위는_곡이다(self):
        text, _ = fmt.describe_batch_result(2, 0, 0)
        assert "2곡" in text

class TestBatchDetailMessage:
    def test_실패가_있을_때만_사유_안내를_한다(self):
        assert "사유" in fmt.describe_batch_detail(1, 1, 0)

    def test_중단만_있으면_사유_안내를_하지_않는다(self):
        detail = fmt.describe_batch_detail(1, 0, 2)
        assert "사유" not in detail
        assert "중단" in detail

    def test_전부_성공이면_안내가_없다(self):
        assert fmt.describe_batch_detail(3, 0, 0) == ""

class TestBatchProgress:
    def test_전량_실패면_진행바를_채우지_않는다(self):
        assert fmt.batch_progress_value(0, 3, 0) == 0.0

    def test_전부_성공이면_가득_채운다(self):
        assert fmt.batch_progress_value(3, 0, 0) == 1.0

    def test_일부_성공은_비율만큼만_채운다(self):
        assert fmt.batch_progress_value(1, 1, 0) == 0.5

    def test_아무것도_없으면_0이다(self):
        assert fmt.batch_progress_value(0, 0, 0) == 0.0

# --------------------------------------------------------------------------
# 진행 단계 문구: MP4 인데 '음원 변환 중' 이라고 하면 안 된다
# --------------------------------------------------------------------------
class TestStageText:
    def test_MP4_후처리는_병합으로_표기한다(self):
        assert "병합" in fmt.describe_postprocess_stage("MP4")

    def test_MP3_후처리는_음원_변환으로_표기한다(self):
        assert "변환" in fmt.describe_postprocess_stage("MP3")

    def test_FLAC도_변환으로_표기한다(self):
        assert "변환" in fmt.describe_postprocess_stage("FLAC")

# ==========================================================================
# minor 묶음 G: 오류 대화상자
# ==========================================================================
class TestErrorMessageMerge:
    def test_새_메시지를_아래에_덧붙인다(self):
        merged = fmt.merge_error_messages("첫 번째", "두 번째")
        assert "첫 번째" in merged and "두 번째" in merged

    def test_같은_메시지는_중복해서_쌓지_않는다(self):
        merged = fmt.merge_error_messages("같은 말", "같은 말")
        assert merged.count("같은 말") == 1

    def test_기존이_비어있으면_새_메시지만_남는다(self):
        assert fmt.merge_error_messages("", "새 메시지") == "새 메시지"

class TestDialogWidth:
    def test_긴_한_줄은_창을_넓힌다(self):
        narrow, _ = fmt.measure_error_dialog("짧다")
        wide, _ = fmt.measure_error_dialog("가" * 120)
        assert wide >= narrow

    def test_너비는_상한을_넘지_않는다(self):
        width, _ = fmt.measure_error_dialog("가" * 5000)
        assert width <= fmt.DIALOG_MAX_WIDTH

    def test_높이는_상한을_넘지_않는다(self):
        _, height = fmt.measure_error_dialog("줄" + chr(10) * 500)
        assert height <= fmt.DIALOG_MAX_HEIGHT

    def test_최소_크기를_보장한다(self):
        width, height = fmt.measure_error_dialog("")
        assert width >= fmt.DIALOG_MIN_WIDTH
        assert height >= fmt.DIALOG_MIN_HEIGHT


# ==========================================================================
# 사이드바 개편: 대기열 요약·필터
# ==========================================================================
class TestQueueSummary:
    ITEMS = [
        {"status": "finished"},
        {"status": "waiting"},
        {"status": "stopped"},
        {"status": "downloading"},
        {"status": "failed", "error": "연령 제한"},
        {"status": "failed", "blocked": True, "error": "재생목록"},
    ]

    def test_중단된_곡은_다시_받을_수_있어_대기로_센다(self):
        assert fmt.queue_bucket({"status": "stopped"}) == "대기"

    def test_차단된_항목은_문제로_센다(self):
        assert fmt.queue_bucket({"status": "waiting", "blocked": True}) == "문제"

    def test_분류별_개수(self):
        counts = fmt.summarize_queue(self.ITEMS)
        assert counts == {"전체": 6, "대기": 2, "진행": 1, "완료": 1, "문제": 2}

    def test_요약_문구는_0인_분류를_뺀다(self):
        text = fmt.describe_queue_summary([{"status": "waiting"}, {"status": "finished"}])
        assert text == "2곡 · 대기 1 · 완료 1"

    def test_빈_대기열(self):
        assert fmt.describe_queue_summary([]) == "비어 있음"

    def test_필터는_원래_인덱스를_돌려준다(self):
        assert fmt.filter_queue_indices(self.ITEMS, "문제") == [4, 5]
        assert fmt.filter_queue_indices(self.ITEMS, "전체") == list(range(6))

    def test_실패_사유를_함께_돌려준다(self):
        assert fmt.describe_queue_status(self.ITEMS[4]) == ("실패", "연령 제한")
        assert fmt.describe_queue_status(self.ITEMS[5]) == ("받지 않음", "재생목록")
        assert fmt.describe_queue_status({"status": "waiting"}) == ("대기 중", None)


class TestFileList:
    def test_크기_표시(self):
        assert fmt.format_size(500) == "500B"
        assert fmt.format_size(9.8 * 1024 * 1024) == "9.8MB"
        assert fmt.format_size(212 * 1024 * 1024) == "212MB"
        assert fmt.format_size(None) == "-"

    def test_날짜_표시(self):
        import datetime
        now = datetime.datetime(2026, 9, 23, 12, 0)
        ts = lambda *a: datetime.datetime(*a).timestamp()
        assert fmt.format_file_date(ts(2026, 9, 23, 9, 5), now) == "오늘 09:05"
        assert fmt.format_file_date(ts(2026, 9, 22, 21, 40), now) == "어제 21:40"
        assert fmt.format_file_date(ts(2026, 3, 1, 0, 0), now) == "3월 1일"
        assert fmt.format_file_date(ts(2025, 12, 31, 0, 0), now) == "2025. 12. 31."
        assert fmt.format_file_date("x", now) == "-"

    ENTRIES = [
        {"name": "b 노래.mp3", "ext": "MP3", "size": 10, "mtime": 3},
        {"name": "A 노래.flac", "ext": "FLAC", "size": 30, "mtime": 1},
        {"name": "c 다른곡.mp3", "ext": "MP3", "size": 20, "mtime": 2},
    ]

    def names(self, entries):
        return [e["name"] for e in entries]

    def test_기본은_최근_받은_순(self):
        assert self.names(fmt.filter_sort_files(self.ENTRIES)) == ["b 노래.mp3", "c 다른곡.mp3", "A 노래.flac"]

    def test_이름_크기_정렬(self):
        assert self.names(fmt.filter_sort_files(self.ENTRIES, sort="name"))[0] == "A 노래.flac"
        assert self.names(fmt.filter_sort_files(self.ENTRIES, sort="size"))[0] == "A 노래.flac"

    def test_이름과_형식으로_거른다(self):
        assert self.names(fmt.filter_sort_files(self.ENTRIES, query="노래")) == ["b 노래.mp3", "A 노래.flac"]
        assert self.names(fmt.filter_sort_files(self.ENTRIES, ext="FLAC")) == ["A 노래.flac"]
        assert len(fmt.filter_sort_files(self.ENTRIES, ext="전체")) == 3


class TestSearchResultFromEntry:
    def test_영상은_화면용_사전으로_바뀐다(self):
        r = fmt.search_result_from_entry({
            "ie_key": "Youtube", "id": "V2Mzp7ewg9M", "title": "곡",
            "url": "https://www.youtube.com/watch?v=V2Mzp7ewg9M", "duration": 220,
            "channel": "채널"})
        assert r["duration"] == "03:40"
        assert r["uploader"] == "채널"
        assert r["thumbnail"].endswith("/V2Mzp7ewg9M/mqdefault.jpg"), "4:3 썸네일은 16:9 칸에서 찌그러진다"

    def test_채널과_재생목록은_거른다(self):
        assert fmt.search_result_from_entry(
            {"ie_key": "YoutubeTab", "id": "UC3SyT4_WLHzN7JmHQwKQZww", "title": "채널"}) is None
        assert fmt.search_result_from_entry({"id": "PLabc", "title": "목록"}) is None

    def test_링크가_없으면_영상_ID로_만든다(self):
        r = fmt.search_result_from_entry({"id": "V2Mzp7ewg9M", "url": "V2Mzp7ewg9M"})
        assert r["url"] == "https://www.youtube.com/watch?v=V2Mzp7ewg9M"
        assert r["duration"] == fmt.UNKNOWN_TIME


class TestDisplayText:
    def test_장식용_수학_글자는_보통_글자로(self):
        assert fmt.display_text("𝑷𝒍𝒂𝒚𝒍𝒊𝒔𝒕 아이유") == "Playlist 아이유"

    def test_이모지와_결합_문자는_뺀다(self):
        assert fmt.display_text("[IU TV] 소울메이트👯\u200d♀️") == "[IU TV] 소울메이트♀"
        assert fmt.display_text("속보📢 전세계 💘아이유") == "속보 전세계 아이유"

    def test_보통_제목은_그대로(self):
        title = "IU '이 별로부터(Unknown Planet)' MV [가사/Lyrics] ♥"
        assert fmt.display_text(title) == title
