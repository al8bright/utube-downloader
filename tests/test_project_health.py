"""프로젝트 위생 — 소스 전수 검사.

한 파일이 아니라 패키지 전체를 훑는다.
어느 디렉터리에서 pytest 를 돌려도 같은 파일을 보도록 절대 경로를 쓴다.
"""
import glob
import importlib
import os

import gui_app
from .conftest import PROJECT_ROOT

PACKAGE_SOURCES = sorted(
    glob.glob(os.path.join(PROJECT_ROOT, "utube_downloader", "**", "*.py"), recursive=True)
)
ALL_SOURCES = [os.path.join(PROJECT_ROOT, "gui_app.py")] + PACKAGE_SOURCES


def read_all():
    text = ""
    for path in ALL_SOURCES:
        with open(path, encoding="utf-8") as fh:
            text += fh.read()
    return text


class TestNoDebugPrints:
    def test_소스에_print_가_남아있지_않다(self):
        """--windowed exe 에서는 stdout 이 없어 print 는 흔적조차 남기지 못한다."""
        offenders = []
        for path in ALL_SOURCES:
            with open(path, encoding="utf-8") as fh:
                for i, line in enumerate(fh, 1):
                    if "print(" in line and not line.strip().startswith("#"):
                        offenders.append(f"{os.path.basename(path)}:{i}")
        assert offenders == [], f"print 잔존: {offenders}"


class TestEntryPointExports:
    """gui_app 은 진입점이자 재수출 지점이다. 배치 파일과 테스트가 이 이름을 쓴다."""

    def test_filedialog_가_노출된다(self):
        assert hasattr(gui_app, "filedialog")
        assert hasattr(gui_app.filedialog, "askdirectory")

    def test_messagebox_가_노출된다(self):
        assert hasattr(gui_app, "messagebox")
        assert hasattr(gui_app.messagebox, "askyesno")

    def test_앱_클래스와_주요_심볼이_노출된다(self):
        for name in ("YoutubeDownloaderApp", "LOCKED_WIDGETS", "build_ydl_opts",
                     "extract_video_id", "format_duration", "resolve_save_dir"):
            assert hasattr(gui_app, name), f"{name} 재수출 누락"


class TestPackageImports:
    def test_패키지_모듈이_모두_임포트된다(self):
        """모듈을 나눈 뒤 import 가 빠지면 실행 시점에야 터진다. 미리 잡는다."""
        for name in ("theme", "urls", "storage", "formatting",
                     "winproc", "downloader", "ui", "app", "widgets"):
            importlib.import_module(f"utube_downloader.{name}")


class TestNoUnusedState:
    def test_사용하지_않는_search_results_가_없다(self):
        assert "self.search_results = []" not in read_all(), "실제 검색 상태와 혼동을 준다"
