"""downloader 모듈 — yt-dlp 옵션과 오류 해석."""
import os

from utube_downloader import downloader, storage


# --------------------------------------------------------------------------
# yt-dlp 옵션: 파일명에 영상 ID가 들어가야 덮어쓰기를 막는다
# --------------------------------------------------------------------------
class TestBuildYdlOpts:
    def test_출력_템플릿에_영상_ID가_포함된다(self, tmp_path):
        opts = downloader.build_ydl_opts(str(tmp_path), "MP3", "320", hook=None)
        assert "%(id)s" in opts["outtmpl"]

    def test_MP3는_음질을_후처리기에_전달한다(self, tmp_path):
        opts = downloader.build_ydl_opts(str(tmp_path), "MP3", "320", hook=None)
        pp = opts["postprocessors"][0]
        assert pp["key"] == "FFmpegExtractAudio"
        assert pp["preferredcodec"] == "mp3"
        assert pp["preferredquality"] == "320"

    def test_MP4는_오디오_추출_후처리기를_쓰지_않는다(self, tmp_path):
        opts = downloader.build_ydl_opts(str(tmp_path), "MP4", "320", hook=None)
        assert "postprocessors" not in opts

    def test_MP4는_병합_컨테이너를_mp4로_고정한다(self, tmp_path):
        opts = downloader.build_ydl_opts(str(tmp_path), "MP4", "320", hook=None)
        assert opts["merge_output_format"] == "mp4"

    def test_모든_포맷에서_재생목록을_비활성화한다(self, tmp_path):
        for fmt in ("MP3", "FLAC", "MP4"):
            assert downloader.build_ydl_opts(str(tmp_path), fmt, "320", hook=None)["noplaylist"] is True

class TestTempDirIsolation:
    def test_중간_파일은_전용_임시폴더에_받는다(self, tmp_path):
        opts = downloader.build_ydl_opts(str(tmp_path), "MP3", "320", hook=None)
        assert "paths" in opts
        assert opts["paths"]["home"] == str(tmp_path)
        assert opts["paths"]["temp"] == os.path.join(str(tmp_path), storage.TEMP_DIR_NAME)

    def test_임시폴더_정리는_해당_폴더만_지운다(self, tmp_path):
        keep = tmp_path / "내음악.mp3"
        keep.write_bytes(b"precious")
        tmp = tmp_path / storage.TEMP_DIR_NAME
        tmp.mkdir()
        (tmp / "찌꺼기.webm").write_bytes(b"junk")

        storage.cleanup_temp_dir(str(tmp_path))

        assert keep.exists(), "사용자 파일을 지우면 안 된다"
        assert not tmp.exists()

    def test_임시폴더가_없어도_예외가_없다(self, tmp_path):
        storage.cleanup_temp_dir(str(tmp_path))

    def test_잘못된_경로에도_죽지_않는다(self):
        storage.cleanup_temp_dir("")

class TestFlacQuality:
    def test_FLAC은_비트레이트_옵션을_넣지_않는다(self, tmp_path):
        """FLAC 은 무손실이라 preferredquality 가 의미 없다."""
        opts = downloader.build_ydl_opts(str(tmp_path), "FLAC", "320", hook=None)
        pp = opts["postprocessors"][0]
        assert "preferredquality" not in pp

    def test_MP3는_비트레이트를_유지한다(self, tmp_path):
        opts = downloader.build_ydl_opts(str(tmp_path), "MP3", "256", hook=None)
        assert opts["postprocessors"][0]["preferredquality"] == "256"


class TestForbiddenError:
    def test_403은_구버전_안내로_바뀐다(self):
        """유튜브가 서명 방식을 바꾸면 낡은 yt-dlp 의 주소가 403 으로 거부된다."""
        msg = downloader.describe_download_error(
            Exception("ERROR: unable to download video data: HTTP Error 403: Forbidden"))
        assert "403" in msg and "yt-dlp" in msg

    def test_봇_확인_요구는_따로_안내한다(self):
        msg = downloader.describe_download_error(
            Exception("ERROR: Sign in to confirm you're not a bot"))
        assert "사람인지" in msg


class TestJsRuntimes:
    """유튜브 서명 계산에 쓰는 JavaScript 런타임 자동 감지."""

    def test_설치된_런타임만_켠다(self):
        found = downloader.detect_js_runtimes(which=lambda name: name in ("node", "bun"))
        assert found == {"node": {}, "bun": {}}

    def test_아무것도_없으면_비어_있다(self):
        assert downloader.detect_js_runtimes(which=lambda name: None) == {}

    def test_옵션에_실린다(self, monkeypatch, tmp_path):
        monkeypatch.setattr(downloader.shutil, "which", lambda name: name == "node")
        opts = downloader.build_ydl_opts(str(tmp_path), "MP3", "320", None)
        assert opts["js_runtimes"] == {"node": {}}

    def test_없으면_기본값을_건드리지_않는다(self, monkeypatch, tmp_path):
        monkeypatch.setattr(downloader.shutil, "which", lambda name: None)
        opts = downloader.build_ydl_opts(str(tmp_path), "MP3", "320", None)
        assert "js_runtimes" not in opts, "빈 설정을 넘기면 yt-dlp 기본값(deno)까지 지워진다"

    def test_검색과_분석도_같은_설정을_쓴다(self):
        """다운로드만 런타임을 쓰면 검색·분석에서 경고가 남고 동작이 달라진다."""
        import inspect
        from utube_downloader import app as app_module
        src = inspect.getsource(app_module)
        assert src.count("js_runtime_opts()") >= 2


class TestBundledFFmpeg:
    """받는 쪽 PC 에 FFmpeg 가 없어도 되도록 exe 에 함께 넣는다."""

    def _fake_bundle(self, monkeypatch, tmp_path, present):
        if present:
            (tmp_path / "ffmpeg.exe").write_bytes(b"x")
        monkeypatch.setattr(downloader, "resource_path",
                            lambda name: str(tmp_path / name))

    def test_묶여_있으면_그_폴더를_쓴다(self, monkeypatch, tmp_path):
        self._fake_bundle(monkeypatch, tmp_path, True)
        opts = downloader.build_ydl_opts(str(tmp_path), "MP3", "320", None)
        assert opts["ffmpeg_location"] == str(tmp_path)

    def test_소스_실행이면_PATH_에_맡긴다(self, monkeypatch, tmp_path):
        self._fake_bundle(monkeypatch, tmp_path, False)
        opts = downloader.build_ydl_opts(str(tmp_path), "MP3", "320", None)
        assert "ffmpeg_location" not in opts

    def test_묶여_있는데_실패하면_설치_안내를_하지_않는다(self, monkeypatch, tmp_path):
        self._fake_bundle(monkeypatch, tmp_path, True)
        msg = downloader.describe_download_error(Exception("ffprobe/ffmpeg not found"))
        assert "winget" not in msg and "백신" in msg

    def test_소스_실행에서는_설치_안내를_한다(self, monkeypatch, tmp_path):
        self._fake_bundle(monkeypatch, tmp_path, False)
        msg = downloader.describe_download_error(Exception("ffprobe/ffmpeg not found"))
        assert "winget" in msg
