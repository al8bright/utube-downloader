"""urls 모듈 — 유튜브 링크 해석."""
from utube_downloader import urls


# --------------------------------------------------------------------------
# 재생목록 URL: 항목 1개가 수백 개를 받으면 안 된다
# --------------------------------------------------------------------------
class TestPlaylistDetection:
    def test_재생목록_정보는_재생목록으로_판정한다(self):
        info = {"_type": "playlist", "entries": [{}, {}], "title": "믹스"}
        assert urls.is_playlist_info(info) is True

    def test_단일_영상_정보는_재생목록이_아니다(self):
        assert urls.is_playlist_info({"_type": "url", "title": "곡"}) is False

    def test_타입이_없는_단일_영상도_재생목록이_아니다(self):
        assert urls.is_playlist_info({"title": "곡", "duration": 100}) is False

    def test_None_은_재생목록이_아니다(self):
        assert urls.is_playlist_info(None) is False

# --------------------------------------------------------------------------
# 영상 ID 추출: 링크 형태가 달라도 같은 영상이면 중복으로 잡아야 한다
# --------------------------------------------------------------------------
class TestExtractVideoId:
    def test_표준_watch_링크(self):
        assert urls.extract_video_id("https://www.youtube.com/watch?v=n61ULEU7CO0") == "n61ULEU7CO0"

    def test_단축_링크(self):
        assert urls.extract_video_id("https://youtu.be/n61ULEU7CO0") == "n61ULEU7CO0"

    def test_타임스탬프가_붙어도_같은_ID(self):
        assert urls.extract_video_id("https://youtu.be/n61ULEU7CO0?t=42") == "n61ULEU7CO0"

    def test_재생목록_파라미터가_붙어도_같은_ID(self):
        url = "https://www.youtube.com/watch?v=n61ULEU7CO0&list=PLabc&index=3"
        assert urls.extract_video_id(url) == "n61ULEU7CO0"

    def test_shorts_와_embed(self):
        assert urls.extract_video_id("https://youtube.com/shorts/n61ULEU7CO0") == "n61ULEU7CO0"
        assert urls.extract_video_id("https://www.youtube.com/embed/n61ULEU7CO0") == "n61ULEU7CO0"

    def test_유튜브가_아니면_None(self):
        assert urls.extract_video_id("https://example.com/watch?v=abc") is None

    def test_빈값은_None(self):
        assert urls.extract_video_id("") is None
        assert urls.extract_video_id(None) is None

class TestIsSameVideo:
    def test_형태가_달라도_같은_영상이면_참(self):
        assert urls.is_same_video(
            "https://youtu.be/n61ULEU7CO0?t=42",
            "https://www.youtube.com/watch?v=n61ULEU7CO0&list=PLx",
        ) is True

    def test_다른_영상이면_거짓(self):
        assert urls.is_same_video(
            "https://youtu.be/n61ULEU7CO0", "https://youtu.be/aqz-KE-bpKQ"
        ) is False

    def test_ID를_못뽑으면_문자열_비교로_떨어진다(self):
        assert urls.is_same_video("https://x.com/a", "https://x.com/a") is True
        assert urls.is_same_video("https://x.com/a", "https://x.com/b") is False

# --------------------------------------------------------------------------
# 회귀: 대문자 도메인도 같은 영상으로 잡아야 한다
# --------------------------------------------------------------------------
class TestVideoIdCaseInsensitive:
    def test_대문자_도메인도_ID를_뽑는다(self):
        assert urls.extract_video_id("https://www.YouTube.com/watch?v=n61ULEU7CO0") == "n61ULEU7CO0"
        assert urls.extract_video_id("https://YOUTU.BE/n61ULEU7CO0") == "n61ULEU7CO0"

    def test_대소문자가_달라도_같은_영상으로_본다(self):
        assert urls.is_same_video(
            "https://www.youtube.com/watch?v=n61ULEU7CO0",
            "https://www.YouTube.com/watch?v=n61ULEU7CO0",
        ) is True

    def test_구형_v_경로도_인식한다(self):
        assert urls.extract_video_id("https://www.youtube.com/v/n61ULEU7CO0") == "n61ULEU7CO0"

    def test_영상_ID_자체의_대소문자는_보존한다(self):
        assert urls.extract_video_id("https://youtu.be/AbCdEfGhIjK") == "AbCdEfGhIjK"

# ==========================================================================
# minor 묶음 A: 순수 함수 정밀화
# ==========================================================================
class TestVideoIdStrictness:
    def test_유튜브가_아닌_호스트는_ID를_뽑지_않는다(self):
        assert urls.extract_video_id("https://evil.com/watch?v=n61ULEU7CO0") is None
        assert urls.extract_video_id("https://notyoutube.com/embed/n61ULEU7CO0") is None

    def test_도메인을_포함한_사칭_호스트도_거른다(self):
        assert urls.extract_video_id("https://youtube.com.evil.net/watch?v=n61ULEU7CO0") is None

    def test_서브도메인은_허용한다(self):
        assert urls.extract_video_id("https://m.youtube.com/watch?v=n61ULEU7CO0") == "n61ULEU7CO0"
        assert urls.extract_video_id("https://music.youtube.com/watch?v=n61ULEU7CO0") == "n61ULEU7CO0"

    def test_12자_이상_토큰은_앞_11자로_자르지_않는다(self):
        assert urls.extract_video_id("https://youtu.be/aaaaaaaaaaaaBBB") is None

    def test_양쪽_모두_비어있으면_같은_영상이_아니다(self):
        assert urls.is_same_video("", "") is False
        assert urls.is_same_video(None, None) is False
        assert urls.is_same_video("   ", "") is False
