"""YouTube Music Downloader 진입점.

실제 구현은 utube_downloader 패키지에 있다.
이 파일은 실행 진입점이자, 기존 이름으로 참조하던 곳
(테스트·배치 파일·빌드 스크립트)을 위한 재수출 지점이다.
"""
from utube_downloader.app import YoutubeDownloaderApp  # noqa: F401
from utube_downloader.downloader import (  # noqa: F401
    build_ydl_opts, describe_download_error,
)
from utube_downloader.formatting import (  # noqa: F401
    BR, SEARCH_INITIAL_TEXT, SEARCH_NO_RESULT_TEXT, SEARCH_TIMEOUT_MS, UNKNOWN_TIME,
    batch_progress_value, describe_batch_detail, describe_batch_result,
    describe_postprocess_stage, format_duration, format_eta,
    measure_error_dialog, merge_error_messages,
)
from utube_downloader.storage import (  # noqa: F401
    TEMP_DIR_NAME, cleanup_temp_dir, escape_ydl_path, resolve_save_dir,
)
from utube_downloader.theme import *  # noqa: F401,F403
from utube_downloader.theme import LOCKED_WIDGETS, tracked  # noqa: F401
from utube_downloader.ui import build_widgets  # noqa: F401
from utube_downloader.urls import (  # noqa: F401
    extract_video_id, is_playlist_info, is_same_video,
)
from utube_downloader.widgets import (  # noqa: F401
    ScrollableFileFrame, ScrollableQueueFrame, ScrollableSearchFrame,
)
from utube_downloader.winproc import (  # noqa: F401
    bind_children_to_process_lifetime, resource_path, terminate_child_ffmpeg,
)

# 테스트가 gui_app.ctk / gui_app.threading / gui_app.filedialog 를 monkeypatch 한다.
import threading  # noqa: E402,F401
from tkinter import filedialog, messagebox  # noqa: E402,F401

import customtkinter as ctk  # noqa: E402,F401


def main():
    app = YoutubeDownloaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
