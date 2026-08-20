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
