"""storage 모듈 — 저장 경로와 임시 폴더."""
import os

from utube_downloader import downloader, storage


# --------------------------------------------------------------------------
# 저장 경로: 조용한 cwd 폴백이 아니라 유효성을 알려줘야 한다
# --------------------------------------------------------------------------
class TestResolveSaveDir:
    def test_유효한_폴더는_그대로_반환한다(self, tmp_path):
        path, ok = storage.resolve_save_dir(str(tmp_path))
        assert ok is True
        assert os.path.normpath(path) == os.path.normpath(str(tmp_path))

    def test_존재하지_않는_경로는_실패를_알린다(self, tmp_path):
        missing = str(tmp_path / "없는폴더")
        path, ok = storage.resolve_save_dir(missing)
        assert ok is False
        assert os.path.normpath(path) == os.path.normpath(os.getcwd())

    def test_폴더가_아닌_파일경로는_실패를_알린다(self, tmp_path):
        f = tmp_path / "a.mp3"
        f.write_bytes(b"x")
        path, ok = storage.resolve_save_dir(str(f))
        assert ok is False

    def test_빈_문자열은_실패를_알린다(self):
        path, ok = storage.resolve_save_dir("   ")
        assert ok is False

# --------------------------------------------------------------------------
# 저장 경로의 %VAR% 가 환경변수로 치환되면 안 된다
# --------------------------------------------------------------------------
class TestPathEscaping:
    def test_퍼센트가_이스케이프된다(self):
        assert storage.escape_ydl_path(r"D:\Music%USERNAME%") == r"D:\Music%%USERNAME%%"

    def test_퍼센트가_없으면_그대로(self):
        assert storage.escape_ydl_path(r"D:\Music") == r"D:\Music"

    def test_옵션의_paths가_이스케이프된_경로를_쓴다(self):
        opts = downloader.build_ydl_opts(r"D:\Music%USERNAME%", "MP3", "320", hook=None)
        assert "%%USERNAME%%" in opts["paths"]["home"]
