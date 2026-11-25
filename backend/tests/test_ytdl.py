"""yt-dlp 옵션과 오류 해석."""

import os
import sys

from utube.core import storage, ytdl


def opts(save_dir, fmt="MP3", quality="320"):
    return ytdl.build_ydl_opts(str(save_dir), fmt, quality, hook=None)


class TestBuildYdlOpts:
    def test_파일명에_영상_ID가_들어가_덮어쓰지_않는다(self, tmp_path):
        assert "%(id)s" in opts(tmp_path)["outtmpl"]

    def test_MP3는_음질을_후처리기에_전달한다(self, tmp_path):
        pp = opts(tmp_path, "MP3", "256")["postprocessors"][0]
        assert pp == {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "256"}

    def test_FLAC은_비트레이트를_넣지_않는다(self, tmp_path):
        assert "preferredquality" not in opts(tmp_path, "FLAC")["postprocessors"][0]

    def test_MP4는_추출_대신_mp4로_병합한다(self, tmp_path):
        o = opts(tmp_path, "MP4")
        assert "postprocessors" not in o and o["merge_output_format"] == "mp4"

    def test_모든_형식에서_재생목록을_받지_않는다(self, tmp_path):
        for fmt in ("MP3", "FLAC", "MP4"):
            assert opts(tmp_path, fmt)["noplaylist"] is True

    def test_중간_파일은_전용_임시폴더에_받는다(self, tmp_path):
        o = opts(tmp_path)
        assert o["paths"] == {"home": str(tmp_path), "temp": os.path.join(str(tmp_path), storage.TEMP_DIR_NAME)}

    def test_경로의_퍼센트를_이스케이프한다(self):
        assert "%%USERNAME%%" in ytdl.build_ydl_opts(r"D:\Music%USERNAME%", "MP3", "320", None)["paths"]["home"]

    def test_응답_없는_연결에_시간_제한을_건다(self, tmp_path):
        assert opts(tmp_path)["socket_timeout"] > 0


class TestJsRuntimes:
    def test_설치된_런타임만_켠다(self):
        assert ytdl.detect_js_runtimes(which=lambda n: n in ("node", "bun")) == {"node": {}, "bun": {}}

    def test_옵션에_실린다(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ytdl.shutil, "which", lambda n: n == "node")
        assert opts(tmp_path)["js_runtimes"] == {"node": {}}

    def test_없으면_기본값을_건드리지_않는다(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ytdl.shutil, "which", lambda n: None)
        assert "js_runtimes" not in opts(tmp_path), "빈 설정을 넘기면 yt-dlp 기본값(deno)까지 지워진다"

    def test_함께_넣은_deno_를_경로째_먼저_쓴다(self, monkeypatch, tmp_path):
        (tmp_path / "deno.exe").write_bytes(b"x")
        monkeypatch.setenv("UTUBE_TOOLS_DIR", str(tmp_path))
        monkeypatch.setattr(ytdl.shutil, "which", lambda n: n == "node")
        found = opts(tmp_path)["js_runtimes"]
        assert list(found) == ["deno", "node"]
        assert found["deno"] == {"path": str(tmp_path / "deno.exe")}


class TestBundledFFmpeg:
    def _bundle(self, monkeypatch, tmp_path, present):
        if present:
            (tmp_path / "ffmpeg.exe").write_bytes(b"x")
        monkeypatch.delenv("UTUBE_TOOLS_DIR", raising=False)
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", str(tmp_path / "utube-backend.exe"))

    def test_실행_파일_옆에_있으면_그것을_쓴다(self, monkeypatch, tmp_path):
        self._bundle(monkeypatch, tmp_path, True)
        assert opts(tmp_path)["ffmpeg_location"] == str(tmp_path)

    def test_없으면_PATH_에_맡긴다(self, monkeypatch, tmp_path):
        self._bundle(monkeypatch, tmp_path, False)
        assert "ffmpeg_location" not in opts(tmp_path)

    def test_환경변수로_가리킬_수_있다(self, monkeypatch, tmp_path):
        (tmp_path / "ffmpeg.exe").write_bytes(b"x")
        monkeypatch.setenv("UTUBE_TOOLS_DIR", str(tmp_path))
        assert ytdl.bundled_ffmpeg_dir() == str(tmp_path)

    def test_묶여_있는데_실패하면_설치_안내를_하지_않는다(self, monkeypatch, tmp_path):
        self._bundle(monkeypatch, tmp_path, True)
        msg = ytdl.describe_download_error(Exception("ffprobe/ffmpeg not found"))
        assert "winget" not in msg and "백신" in msg

    def test_개발_실행에서는_설치_안내를_한다(self, monkeypatch, tmp_path):
        self._bundle(monkeypatch, tmp_path, False)
        assert "winget" in ytdl.describe_download_error(Exception("ffprobe/ffmpeg not found"))


class TestErrors:
    def test_403은_구버전_안내(self):
        msg = ytdl.describe_download_error(Exception("ERROR: unable to download video data: HTTP Error 403: Forbidden"))
        assert "403" in msg and "yt-dlp" in msg

    def test_봇_확인_요구(self):
        assert "사람인지" in ytdl.describe_download_error(Exception("ERROR: Sign in to confirm you're not a bot"))

    def test_비공개_영상(self):
        assert "비공개" in ytdl.describe_download_error(Exception("ERROR: Private video"))

    def test_지역_제한은_삭제와_구분한다(self):
        msg = ytdl.describe_download_error(Exception("The uploader has not made this video available in your country"))
        assert "지역" in msg

    def test_모르는_오류는_ERROR_접두어만_뗀다(self):
        assert ytdl.describe_download_error(Exception("ERROR: 이상한 일")) == "이상한 일"
