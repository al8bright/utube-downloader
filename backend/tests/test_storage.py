"""저장 폴더와 받은 파일."""

import os

import pytest

from utube.core import storage


class TestResolveSaveDir:
    def test_유효한_폴더는_그대로(self, tmp_path):
        path, ok = storage.resolve_save_dir(str(tmp_path))
        assert ok is True and path == os.path.normpath(str(tmp_path))

    def test_없는_경로는_실패를_알린다(self, tmp_path):
        assert storage.resolve_save_dir(str(tmp_path / "없는폴더"))[1] is False

    def test_파일_경로는_실패를_알린다(self, tmp_path):
        f = tmp_path / "a.mp3"
        f.write_bytes(b"x")
        assert storage.resolve_save_dir(str(f))[1] is False

    def test_빈_문자열은_실패를_알린다(self):
        assert storage.resolve_save_dir("   ") == ("", False)


class TestEscapeAndTemp:
    def test_퍼센트가_이스케이프된다(self):
        assert storage.escape_ydl_path(r"D:\Music%USERNAME%") == r"D:\Music%%USERNAME%%"
        assert storage.escape_ydl_path(r"D:\Music") == r"D:\Music"

    def test_임시폴더_정리는_해당_폴더만_지운다(self, tmp_path):
        keep = tmp_path / "내음악.mp3"
        keep.write_bytes(b"precious")
        tmp = tmp_path / storage.TEMP_DIR_NAME
        tmp.mkdir()
        (tmp / "찌꺼기.webm").write_bytes(b"junk")
        storage.cleanup_temp_dir(str(tmp_path))
        assert keep.exists(), "사용자 파일을 지우면 안 된다"
        assert not tmp.exists()

    def test_임시폴더가_없거나_경로가_비어도_죽지_않는다(self, tmp_path):
        storage.cleanup_temp_dir(str(tmp_path))
        storage.cleanup_temp_dir("")


class TestListFiles:
    def test_음성과_영상을_나누고_나머지는_무시한다(self, tmp_path):
        for name in ("a.mp3", "b.FLAC", "c.mp4", "d.txt", "e.webm"):
            (tmp_path / name).write_bytes(b"xx")
        (tmp_path / "sub.mp3").mkdir()
        found = storage.list_files(str(tmp_path))
        assert sorted(e["name"] for e in found["audio"]) == ["a.mp3", "b.FLAC"]
        assert sorted(e["name"] for e in found["video"]) == ["c.mp4", "e.webm"]
        assert {e["ext"] for e in found["audio"]} == {"MP3", "FLAC"}
        assert found["audio"][0]["size"] == 2


class TestFileInDir:
    def test_폴더_안의_파일만_허용한다(self, tmp_path):
        (tmp_path / "a.mp3").write_bytes(b"x")
        assert storage.file_in_dir(str(tmp_path), "a.mp3") == os.path.join(str(tmp_path), "a.mp3")

    @pytest.mark.parametrize("name", ["..\\a.mp3", "../a.mp3", "C:\\Windows\\a.mp3", "", "..", "sub\\a.mp3"])
    def test_경로가_섞인_이름은_막는다(self, tmp_path, name):
        with pytest.raises(storage.StorageError):
            storage.file_in_dir(str(tmp_path), name)

    def test_음성_영상이_아니면_막는다(self, tmp_path):
        (tmp_path / "settings.json").write_text("{}")
        with pytest.raises(storage.StorageError):
            storage.file_in_dir(str(tmp_path), "settings.json")

    def test_종류별_전체_삭제는_그_종류만(self, tmp_path):
        for name in ("a.mp3", "b.flac", "c.mp4", "keep.txt"):
            (tmp_path / name).write_bytes(b"x")
        deleted, errors = storage.delete_kind(str(tmp_path), "audio")
        assert (deleted, errors) == (2, [])
        assert sorted(os.listdir(tmp_path)) == ["c.mp4", "keep.txt"]


def test_ffmpeg_tree_includes_shim_children_and_skips_others():
    from utube.core.proc import ffmpeg_tree

    procs = [
        (10, 1, "python.exe"),
        (20, 10, "ffmpeg.exe"),    # shim (our child)
        (21, 20, "ffmpeg.exe"),    # real ffmpeg under the shim
        (22, 21, "conhost.exe"),
        (30, 10, "node.exe"),      # our child, not ffmpeg
        (40, 99, "ffmpeg.exe"),    # someone else's ffmpeg
    ]
    got = ffmpeg_tree(procs, 10)
    assert set(got) == {20, 21, 22}
    assert got.index(21) < got.index(20)  # descendants are killed first
