"""앱 본체.

화면 조립은 ui.py 가, 계산은 formatting/urls/storage 가 맡는다.
여기서는 상태와 스레드, 그리고 생명주기만 다룬다.
"""
import os
import sys
import threading
import time
from tkinter import filedialog, messagebox

import customtkinter as ctk
import yt_dlp

from .downloader import build_ydl_opts, describe_download_error
from .formatting import (
    BR, FILE_SORTS, SEARCH_BATCH, SEARCH_LIMIT, SEARCH_LOADING_TEXT,
    SEARCH_NO_RESULT_TEXT, SEARCH_TIMEOUT_MS, UNKNOWN_TIME,
    batch_progress_value, describe_batch_detail, describe_batch_result,
    describe_postprocess_stage, describe_queue_summary, filter_sort_files,
    format_duration, format_eta, format_size, measure_error_dialog, merge_error_messages,
    search_result_from_entry, summarize_queue,
)
from .storage import cleanup_temp_dir, resolve_save_dir
from .theme import (
    C_ASH, C_BG, C_DANGER, C_GIALLO, C_GRAPHITE, C_PEARL, C_STEEL, C_SUCCESS,
    C_SURFACE_DEEP, C_TEXT_MUTED,
    DIALOG_MIN_HEIGHT, DIALOG_MIN_WIDTH, FONT_BODY, LOCKED_WIDGETS, RADIUS_BUTTON,
    WINDOW_MIN, WINDOW_SIZE,
)
from .ui import build_widgets, chip_text, style_chip
from .urls import extract_video_id, is_playlist_info, is_same_video
from .widgets.queue_list import is_selectable
from .winproc import (
    bind_children_to_process_lifetime, resource_path, terminate_child_ffmpeg,
)

AUDIO_EXTS = ('.mp3', '.flac')
VIDEO_EXTS = ('.mp4', '.mkv', '.webm', '.avi')


class YoutubeDownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # 검색·썸네일·다운로드 스레드가 GIL 을 잡고 있으면 화면 스레드는 Tk 호출마다
        # 전환 주기(기본 5ms)만큼 기다린다. 한 화면에 Tk 호출이 수백 번이라 눈에 띄게 멈춘다.
        sys.setswitchinterval(0.001)

        self.title("YouTube Music Downloader - Batch Queue Edition")
        self.geometry(WINDOW_SIZE)
        self.minsize(*WINDOW_MIN)
        self.configure(fg_color=C_BG)

        # 자식 프로세스(ffmpeg)가 앱보다 오래 살지 못하도록 묶는다
        self._job_handle = bind_children_to_process_lifetime()

        # X 버튼을 눌렀을 때 정리 절차를 거치게 한다
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # 윈도우 타이틀바 아이콘 지정
        try:
            icon_file = resource_path("youtube_icon.ico")
            if os.path.exists(icon_file):
                self.iconbitmap(icon_file)
        except Exception:
            pass


        # 상태 변수들
        self.stop_requested = False
        self.last_error = None
        self.last_batch_tally = None
        self._error_win = None
        self._error_label = None
        self._error_text = ""
        self.stop_message = None
        self.convert_started_at = None
        self.convert_pulse = 0
        self.finished_hook_count = 0
        self.active_format = 'MP3'
        self.pending_added_during_batch = 0
        self.searching = False
        self.search_generation = 0
        self.search_received = 0           # 이번 검색에서 화면에 붙인 결과 수
        self.save_dir_var = ctk.StringVar(value=os.path.normpath(os.getcwd()))
        self.queue_items = []  # 대기열 목록: [{title, url, duration, uploader, check_var, status}]

        # 현재 일괄 다운로드 제어 변수
        self.batch_running = False
        self.current_download_idx = -1
        self.current_download_status = {
            'percent': 0.0,
            'speed': '',
            'eta': '',
            'status': 'idle'
        }
        self.overall_progress = 0.0
        self.batch_position = (0, 0)       # (지금 몇 번째, 모두 몇 곡)

        # 화면 상태
        self.current_screen = None
        self.file_views = {}               # 'audio'/'video' -> 필터·정렬 상태와 위젯
        self.file_entries = {'audio': [], 'video': []}
        self.session_started_at = time.time()  # 이후에 생긴 파일에 '새로 받음' 을 붙인다

        self.create_widgets()
        self.refresh_file_list()
        self.update_queue_list_ui()
        self.update_search_selection()
        self.show_screen("search")

        # 실시간 UI 모니터링 루프 시작
        self.after(100, self.update_progress_loop)

    def create_widgets(self):
        build_widgets(self)

    # ------------------------------------------------------------------
    # 화면 전환
    # ------------------------------------------------------------------
    def show_screen(self, name):
        """사이드바 메뉴로 화면을 바꾼다. 대기열에서는 진행 요약을 숨긴다.

        안 보이는 화면은 배치에서 뺀다. 겹쳐 두기만 하면 창 크기를 바꿀 때
        보이지 않는 화면 넷의 목록까지 전부 다시 배치해 버벅인다.
        """
        for key, frame in self.screens.items():
            if key == name:
                frame.grid()
            else:
                frame.grid_remove()
        self.current_screen = name
        self.sidebar.set_active(name)
        self.sidebar.show_progress(self.batch_running and name != "queue")
        if name in self.file_views:
            # 다른 화면에 있는 동안 받은 파일도 바로 보이게 한다
            self.refresh_file_list()

    def start_search(self):
        # Enter 키(바인딩)는 버튼 비활성화를 우회하므로 플래그로 재진입을 막는다.
        # 막지 않으면 연타 한 번마다 검색 스레드와 썸네일 작업 100건이 쌓인다.
        if self.searching:
            self.show_error(
                "이미 검색이 진행 중입니다."
                + BR + BR
                + "결과가 나온 뒤에 다시 검색해 주세요."
            )
            return

        query = self.search_entry.get().strip()
        if not query:
            self.show_error("검색 키워드를 입력해 주세요.")
            return

        # 유튜브 링크면 검색하지 않고 바로 대기열에 담는다
        if extract_video_id(query):
            if self.add_url_to_queue(query):
                self.search_entry.delete(0, 'end')
                self.show_screen("queue")
            return

        self.searching = True
        self.search_generation += 1
        self.search_received = 0
        generation = self.search_generation
        self.search_btn.configure(state="disabled", text="검색 중...")
        # 결과가 올 때까지 옛 결과를 두면 새 결과와 섞여 보인다
        self.search_scroll.populate_results([], empty_text=SEARCH_LOADING_TEXT)
        self.set_search_progress(None, SEARCH_LOADING_TEXT)

        # 응답이 영영 안 오면 검색이 영구히 막히므로 안전장치를 건다
        self.after(SEARCH_TIMEOUT_MS, self.on_search_timeout, generation)

        # 백그라운드 스레드로 검색 요청
        thread = threading.Thread(
            target=self.search_thread_target, args=(query, generation), daemon=True)
        try:
            thread.start()
        except Exception as exc:
            # 스레드 기동 실패만 다룬다. 그 밖의 오류는 삼키지 않고 드러낸다.
            self.finish_search()
            self.show_error("검색을 시작하지 못했습니다." + BR + BR + str(exc))

    def is_current_search(self, generation):
        """늦게 끝난 옛 검색이 새 검색 결과를 덮어쓰지 못하게 한다."""
        return generation == self.search_generation

    def finish_search(self):
        self.searching = False
        self.search_btn.configure(state="normal", text="검색")
        self.set_search_progress(None, None)

    def set_search_progress(self, value, text):
        """검색창 아래 진행 줄.

        text 가 None 이면 진행 줄을 걷고 안내 문구로 돌아간다.
        value 가 None 이면 첫 결과가 오기 전이라 얼마나 남았는지 모르므로 막대를 좌우로 움직인다.
        """
        bar = self.search_progress_bar
        if text is None:
            bar.stop()
            bar.grid_remove()
            self.search_hint_lbl.configure(text=self.search_hint_text, text_color=C_STEEL)
            return
        self.search_hint_lbl.configure(text=text, text_color=C_ASH)
        if value is None:
            if bar.cget("mode") != "indeterminate":
                bar.configure(mode="indeterminate")
                bar.start()
        else:
            if bar.cget("mode") != "determinate":
                bar.stop()
                bar.configure(mode="determinate")
            bar.set(value)
        bar.grid()

    def on_search_timeout(self, generation):
        """응답이 없는 검색의 잠금을 풀어 준다. 현재 검색일 때만 동작한다."""
        if not self.searching or not self.is_current_search(generation):
            return
        self.finish_search()
        self.show_error(
            "검색 응답이 없어 중단했습니다."
            + BR + BR
            + "네트워크 상태를 확인한 뒤 다시 시도해 주세요."
        )

    def search_thread_target(self, query, generation):
        """결과를 한 페이지(20개)씩 받는 대로 화면에 넘긴다.

        100개를 다 모은 뒤 넘기면 5초 넘게 아무 변화가 없다가 한꺼번에 뜬다.
        process=False 로 받으면 유튜브 페이지를 넘길 때마다 결과가 흘러나온다.
        """
        found = 0
        try:
            ydl_opts = {
                'skip_download': True,
                'extract_flat': True,
                'quiet': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(
                    f"ytsearch{SEARCH_LIMIT}:{query}", download=False, process=False)
                batch = []
                for entry in info.get('entries') or []:
                    if not self.is_current_search(generation):
                        return  # 새 검색이 시작됐다. 남은 페이지는 받지 않는다
                    result = search_result_from_entry(entry)
                    if result is None:
                        continue   # 채널·재생목록
                    batch.append(result)
                    if len(batch) >= SEARCH_BATCH:
                        self.after(0, self.on_search_batch, batch, generation)
                        found += len(batch)
                        batch = []
                if batch:
                    self.after(0, self.on_search_batch, batch, generation)
                    found += len(batch)

            self.after(0, self.on_search_success, found, generation)
        except Exception as e:
            self.after(0, self.on_search_failed, describe_download_error(e), generation)

    def on_search_batch(self, results, generation):
        """받은 한 페이지를 목록 뒤에 붙이고 진행 줄을 채운다."""
        if not self.is_current_search(generation):
            return
        if self.search_received == 0:
            self.search_scroll.populate_results(results)
        else:
            self.search_scroll.append_results(results)
        self.search_received += len(results)
        self.set_search_progress(
            min(self.search_received / SEARCH_LIMIT, 1.0),
            f"찾는 중… {self.search_received}개 받음")
        self.search_count_lbl.configure(text=f"결과 {self.search_received}개")
        self.sidebar.set_count("search", self.search_received)

    def on_search_success(self, found, generation=None):
        """검색이 끝났다. found 는 화면에 넘긴 결과 수다."""
        # 세대가 어긋나도 잠금은 반드시 푼다. 안 그러면 검색이 영구히 막힌다.
        self.finish_search()
        if generation is not None and not self.is_current_search(generation):
            return  # 이미 새 검색이 시작됐다. 옛 결과는 버린다.
        if not found:
            self.search_scroll.populate_results([], empty_text=SEARCH_NO_RESULT_TEXT)
        self.search_count_lbl.configure(text=f"결과 {found}개")
        self.sidebar.set_count("search", found)
        self.update_search_selection()

    def on_search_failed(self, err_msg, generation=None):
        self.finish_search()
        if generation is not None and not self.is_current_search(generation):
            return
        self.show_error("유튜브 검색에 실패했습니다." + BR + BR + str(err_msg))

    def add_selected_to_queue(self):
        added_any = False
        added_count = 0
        for item in self.search_scroll.search_results_data:
            if item['check_var'].get():
                # 링크 형태만 다른 같은 영상도 중복으로 잡는다
                exists = any(is_same_video(q['url'], item['url']) for q in self.queue_items)
                if not exists:
                    added_count += 1
                    self.queue_items.append({
                        'title': item['title'],
                        'url': item['url'],
                        'duration': item['duration'],
                        'uploader': item['uploader'],
                        'check_var': ctk.BooleanVar(value=True),
                        'status': 'waiting'
                    })
                # 검색 목록 체크박스 해제
                item['check_var'].set(False)
                added_any = True

        if not added_any:
            self.show_error("추가할 항목을 1개 이상 선택해 주세요.")
            return

        if not added_count:
            # 선택은 했지만 전부 이미 대기열에 있는 경우.
            # 조용히 탭만 넘기면 사용자는 추가된 줄 안다.
            self.show_error(
                "선택한 항목이 모두 이미 대기열에 있습니다."
                + BR + BR
                + "새로 추가된 곡은 없습니다."
            )

        # 대기열 목록 리빌딩
        self.update_queue_list_ui()

        # 다운로드 중 추가된 항목은 이번 배치에 포함되지 않는다는 사실을 알린다
        if self.batch_running and added_count:
            self.pending_added_during_batch += added_count
            self.show_error(
                f"{added_count}개를 대기열에 담았습니다."
                + BR + BR
                + "지금은 다운로드가 진행 중이라 이번 배치에는 포함되지 않습니다."
                + BR
                + "현재 배치가 끝난 뒤 다시 다운로드를 시작해 주세요."
            )

        # 담은 곡을 바로 확인할 수 있게 대기열 화면으로 넘어간다
        self.show_screen("queue")

    def add_direct_url(self):
        """대기열 화면의 '+ 링크 추가' 입력 줄."""
        url = self.direct_url_entry.get().strip()
        if not url:
            self.show_error("추가할 유튜브 링크를 입력해 주세요.")
            return
        if self.add_url_to_queue(url):
            self.direct_url_entry.delete(0, 'end')

    def add_url_to_queue(self, url):
        """링크 하나를 대기열에 담고 분석을 시작한다. 담았으면 True.

        검색창에 붙여넣은 링크와 '+ 링크 추가' 가 같은 길을 쓴다.
        """
        # 대기열에 이미 존재하는지 검사 (링크 형태가 달라도 같은 영상이면 중복)
        exists = any(is_same_video(q['url'], url) for q in self.queue_items)
        if exists:
            self.show_error("이미 대기열에 존재하는 링크입니다.")
            return False

        # 임시 대기열 항목 생성 및 표시
        new_item = {
            'title': f"링크 분석 중: {url}",
            'url': url,
            'duration': '--:--',
            'uploader': '분석 중...',
            'check_var': ctk.BooleanVar(value=True),
            'status': 'analyzing'
        }
        self.queue_items.append(new_item)
        self.update_queue_list_ui()

        if self.batch_running:
            self.pending_added_during_batch += 1
            self.show_error(
                "대기열에 담았습니다."
                + BR + BR
                + "지금은 다운로드가 진행 중이라 이번 배치에는 포함되지 않습니다."
                + BR
                + "현재 배치가 끝난 뒤 다시 다운로드를 시작해 주세요."
            )

        # 백그라운드 분석 스레드 가동
        thread = threading.Thread(target=self.analyze_direct_url_thread, args=(new_item,), daemon=True)
        thread.start()
        return True

    def analyze_direct_url_thread(self, item):
        url = item['url']
        try:
            ydl_opts = {
                'skip_download': True,
                'extract_flat': True,
                'noplaylist': True,
                'quiet': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            # noplaylist 는 watch?v=...&list=... 만 처리한다.
            # 순수 재생목록/채널 URL 은 항목 1개가 영상 수백 개를 받게 되므로 막는다.
            if is_playlist_info(info):
                count = len(info.get('entries') or [])
                item.update({
                    'title': f"재생목록은 추가할 수 없습니다: {info.get('title', url)}",
                    'uploader': f'영상 {count}개 포함',
                    'status': 'failed',
                    # 이 항목은 재시도 대상이 되면 안 된다. status 만으로는 걸러지지 않는다.
                    'blocked': True,
                    'error': (
                        f"재생목록/채널 링크입니다(영상 {count}개). "
                        "개별 영상 링크를 넣거나 검색 화면에서 곡을 선택해 주세요."
                    ),
                })
                # Tk 변수 쓰기는 메인 스레드에서 한다
                self.after(0, item['check_var'].set, False)
                self.after(0, self.update_queue_list_ui)
                self.after(0, self.show_error,
                           f"재생목록 링크는 추가할 수 없습니다.\n\n"
                           f"'{info.get('title', url)}' 에는 영상 {count}개가 들어 있어\n"
                           f"한 항목으로 받으면 저장 폴더가 통째로 채워집니다.\n\n"
                           f"개별 영상 링크를 넣거나 검색 화면을 이용해 주세요.")
                return

            title = info.get('title', 'Unknown Title')
            uploader = info.get('uploader', 'Unknown')
            duration_str = format_duration(info.get('duration', 0))

            item.update({
                'title': title,
                'duration': duration_str,
                'uploader': uploader,
                'status': 'waiting'
            })
        except Exception as e:
            item.update({
                'title': f"분석 실패: {url}",
                'uploader': '오류 발생',
                'status': 'failed',
                'error': describe_download_error(e),
            })

        # UI 스레드에서 대기열 목록 UI 갱신
        self.after(0, self.update_queue_list_ui)

    def delete_queue_item(self, index):
        if self.batch_running:
            self.show_error("다운로드 중에는 대기열을 수정할 수 없습니다.")
            return
        if 0 <= index < len(self.queue_items):
            self.queue_items.pop(index)
            self.update_queue_list_ui()

    def clear_queue(self):
        if self.batch_running:
            self.show_error("다운로드 중에는 대기열을 비울 수 없습니다.")
            return
        self.queue_items.clear()
        self.update_queue_list_ui()
        self.total_prog_bar.set(0.0)
        # 비운 대기열에 지난 결과가 남아 있으면 무엇의 결과인지 알 수 없다
        self.now_card.grid_remove()

    def clear_completed_queue(self):
        if self.batch_running:
            self.show_error("다운로드 중에는 대기열을 수정할 수 없습니다.")
            return

        new_items = []
        removed_count = 0
        for item in self.queue_items:
            if item.get('status') == 'finished':
                removed_count += 1
            else:
                new_items.append(item)

        if removed_count == 0:
            self.show_error("대기열에 완료(finished) 상태인 항목이 없습니다.")
            return

        self.queue_items = new_items
        self.update_queue_list_ui()

    def on_format_changed(self, value):
        # 음질은 MP3 에만 쓴다. 칸을 숨기지 않고 잠가서 옆 칸이 흔들리지 않게 한다
        self.quality_select.configure(state="normal" if value == "MP3" else "disabled")


    def start_all_download(self):
        # 모든 대기열 항목 활성화(체크) 처리 후 시작
        for item in self.queue_items:
            # 차단된 재생목록 항목까지 다시 체크하면 위 가드가 무력해진다
            item['check_var'].set(not item.get('blocked'))
        self.start_selected_download()

    def request_stop_download(self):
        if not self.batch_running:
            return

        self.stop_requested = True
        # 배경까지 회색으로 바꿔야 '눌리는데 반응 없는 버튼' 으로 보이지 않는다
        self.stop_download_btn.configure(
            state="disabled", border_color=C_GRAPHITE, text_color=C_GRAPHITE)
        sidebar = getattr(self, 'sidebar', None)
        if sidebar is not None:
            sidebar.set_stop_enabled(False)

        # 변환(FFmpeg) 단계에서는 progress_hook 이 불리지 않아 플래그만으로는 멈추지 않는다.
        # 실행 중인 자식 ffmpeg 를 직접 종료해야 즉시 중단된다.
        killed = terminate_child_ffmpeg()
        if killed:
            self.stop_message = "변환을 중단했습니다. 정리하는 중..."
        else:
            self.stop_message = "중단 요청됨. 현재 곡을 정리하는 중..."
        self.queue_status_lbl.configure(text=self.stop_message, text_color=C_DANGER)

    def start_selected_download(self):
        if self.batch_running:
            self.show_error("이미 다운로드 대기열이 실행 중입니다.")
            return

        # blocked 는 재생목록처럼 '받으면 안 되는' 항목이다.
        # status 만 보고 거르면 'failed' 로 남은 재생목록이 재시도 경로로 되살아난다.
        selected_indices = [
            idx for idx, item in enumerate(self.queue_items)
            if item['check_var'].get() and item['status'] != 'finished' and not item.get('blocked')
        ]
        if not selected_indices:
            blocked_count = sum(1 for item in self.queue_items if item.get('blocked'))
            if blocked_count:
                self.show_error(
                    f"받을 수 있는 항목이 없습니다."
                    + BR + BR
                    + f"대기열의 {blocked_count}개는 재생목록/채널 링크라 받을 수 없습니다."
                    + BR
                    + "개별 영상 링크를 넣거나 검색 화면을 이용해 주세요."
                )
            else:
                self.show_error("다운로드할(완료되지 않은) 항목을 1개 이상 체크해 주세요.")
            return

        # 저장 폴더가 유효하지 않으면 다운로드를 시작하지 않는다.
        # 안내만 하고 진행하면 파일이 앱 폴더로 조용히 쌓인다.
        resolved, dir_ok = resolve_save_dir(self.save_dir_var.get())
        if not dir_ok:
            self.show_error(
                "저장 폴더를 찾을 수 없어 다운로드를 시작하지 않았습니다."
                + BR + BR
                + f"입력된 경로: {self.save_dir_var.get().strip() or '(비어 있음)'}"
                + BR + BR
                + f"'폴더 변경' 으로 저장 폴더를 지정한 뒤 다시 시작해 주세요."
                + BR
                + f"(현재 칸에는 {resolved} 를 대신 넣어 두었습니다)"
            )
            self.save_dir_var.set(os.path.normpath(resolved))
            return

        self.stop_requested = False
        self.batch_running = True
        self.set_controls_locked(True)

        # Tk 변수는 메인 스레드에서만 읽는다. 워커 스레드에서 읽으면
        # "main thread is not in main loop" 로 배치가 통째로 죽는다.
        # 다운로드 중에는 이 컨트롤들이 잠기므로 값이 바뀔 일도 없다.
        settings = {
            'format': self.format_var.get(),
            'quality': self.quality_var.get().replace("kbps", ""),
            'save_dir': resolved,
        }

        # 백그라운드 스레드에서 순차 다운로드 시작
        thread = threading.Thread(
            target=self.batch_download_loop,
            args=(selected_indices, settings),
            daemon=True
        )
        try:
            thread.start()
        except Exception as exc:
            # 기동에 실패했는데 잠금과 batch_running 을 그대로 두면 영구 잠금이 된다
            self.batch_running = False
            self.set_controls_locked(False)
            self.show_error(
                "다운로드를 시작하지 못했습니다."
                + BR + BR
                + str(exc)
            )

    def batch_download_loop(self, indices_to_download, settings):
        total_count = len(indices_to_download)
        format_type = settings['format']
        quality = settings['quality']
        save_dir = settings['save_dir']
        self.active_format = format_type

        # 성공/실패/중단 개수를 집계해 완료 보고에 넘긴다
        tally = {'done': 0, 'failed': 0, 'stopped': 0, 'total': total_count}
        self.last_batch_tally = tally

        # try/finally 가 없으면 예외 한 번에 batch_running 이 True 로 고착되어
        # 앱을 재시작하기 전까지 다운로드를 다시 시작할 수 없다.
        try:
            for num, idx in enumerate(indices_to_download):
                if self.stop_requested:
                    # 아직 손대지 않은 나머지 항목도 중단으로 집계한다
                    tally['stopped'] += len(indices_to_download) - num
                    break

                self.current_download_idx = idx
                self.batch_position = (num + 1, total_count)
                item = self.queue_items[idx]

                # 상태값 초기화
                item['status'] = 'downloading'
                item.pop('error', None)
                self.current_download_status = {
                    'percent': 0.0,
                    'speed': '계산 중...',
                    'eta': UNKNOWN_TIME,
                    'status': 'downloading'
                }

                # 전체 작업 대비 진행률 갱신
                self.overall_progress = num / total_count
                self.after(0, self.update_queue_list_ui)

                # 단일 다운로드 수행
                self.last_error = None
                self.finished_hook_count = 0
                self.convert_started_at = None
                success = self.download_single(item['url'], format_type, quality, save_dir)

                if success:
                    item['status'] = 'finished'
                    tally['done'] += 1
                elif self.stop_requested:
                    # 사용자가 직접 멈춘 것은 오류가 아니다
                    item['status'] = 'stopped'
                    tally['stopped'] += 1
                else:
                    item['status'] = 'failed'
                    item['error'] = self.last_error
                    tally['failed'] += 1

                self.overall_progress = (num + 1) / total_count
                self.after(0, self.update_queue_list_ui)
        finally:
            self.batch_running = False
            self.current_download_idx = -1
            # 배치가 끝나면 중간 파일 찌꺼기를 정리한다
            cleanup_temp_dir(save_dir)
            self.after(0, self.on_batch_download_complete)

    def download_single(self, url, format_type, quality, save_dir):
        def progress_hook(d):
            if self.stop_requested:
                raise Exception("Download aborted by user")

            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                downloaded = d.get('downloaded_bytes', 0)
                percent = downloaded / total if total > 0 else 0.0

                speed = d.get('speed')
                if speed:
                    if speed > 1024 * 1024:
                        speed_str = f"{speed / (1024*1024):.2f} MB/s"
                    else:
                        speed_str = f"{speed / 1024:.2f} KB/s"
                else:
                    speed_str = "계산 중..."

                eta = d.get('eta')
                eta_str = format_eta(eta) if eta else "--:--"

                self.current_download_status.update({
                    'percent': percent,
                    'speed': speed_str,
                    'eta': eta_str,
                    'status': 'downloading'
                })
            elif d['status'] == 'finished':
                # MP4 는 영상/음성을 따로 받으므로 이 훅이 두 번 온다.
                # 첫 번째에서 '변환 중' 으로 바꿔버리면 두 번째 다운로드가 시작되며
                # 진행률이 100% -> 0% 로 되감겨 보인다. 마지막 스트림에서만 전환한다.
                self.finished_hook_count += 1
                if self.active_format == 'MP4' and self.finished_hook_count < 2:
                    return

                self.convert_started_at = time.time()
                self.current_download_status.update({
                    'status': 'converting',
                    'percent': 1.0,
                })
                # 백엔드 스레드에서 대기열 리스트 UI 텍스트 갱신을 위해 status 직접 수정
                if self.current_download_idx != -1:
                    self.queue_items[self.current_download_idx]['status'] = 'converting'
                    self.after(0, self.update_queue_list_ui)

        ydl_opts = build_ydl_opts(save_dir, format_type, quality, progress_hook)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            return True
        except Exception as e:
            # print 는 cp949 콘솔에서 스스로 UnicodeEncodeError 를 내고,
            # --windowed 빌드에서는 stdout 이 없어 원인이 완전히 사라진다.
            self.last_error = describe_download_error(e)
            return False

    def update_queue_list_ui(self):
        """대기열이 바뀌면 목록과 그에 딸린 표시(요약·칩·선택·사이드바·검색 표시)를 함께 맞춘다."""
        self.queue_scroll.populate_queue(self.queue_items, self.delete_queue_item)

        unit = "편" if self.format_var.get() == 'MP4' else "곡"
        self.queue_summary_lbl.configure(text=describe_queue_summary(self.queue_items, unit))
        counts = summarize_queue(self.queue_items)
        for bucket, button in self.queue_filter_btns.items():
            button.configure(text=chip_text(bucket, counts[bucket]))
        self.sidebar.set_count("queue", counts["전체"])
        self.update_queue_selection()
        # 담긴 곡은 검색 결과에서 흐리게 바뀌어야 한다
        self.search_scroll.refresh_queued()

    def selectable_queue_items(self):
        return [item for item in self.queue_items if is_selectable(item)]

    def update_queue_selection(self):
        """선택 개수에 맞춰 '선택한 N곡 받기' 와 전체 선택 체크를 고친다."""
        selectable = self.selectable_queue_items()
        checked = sum(1 for item in selectable if item['check_var'].get())
        unit = "편" if self.format_var.get() == 'MP4' else "곡"
        self.queue_sel_lbl.configure(text=f"{checked}{unit} 선택" if selectable else "")
        self.download_selected_btn.configure(
            text=f"선택한 {checked}{unit} 받기" if checked else "선택한 곡 받기")
        self.queue_select_all_var.set(bool(selectable) and checked == len(selectable))

    def toggle_select_all(self):
        value = self.queue_select_all_var.get()
        for item in self.selectable_queue_items():
            item['check_var'].set(value)
        self.update_queue_selection()

    def set_queue_filter(self, bucket):
        self.queue_scroll.bucket = bucket
        for key, button in self.queue_filter_btns.items():
            style_chip(button, key == bucket)
        self.update_queue_list_ui()

    def toggle_link_row(self):
        if self.link_row.winfo_manager():
            self.link_row.grid_remove()
        else:
            self.link_row.grid()
            self.direct_url_entry.focus_set()

    # ------------------------------------------------------------------
    # 검색 결과의 대기열 표시
    # ------------------------------------------------------------------
    def is_in_queue(self, url):
        return any(is_same_video(q['url'], url) for q in self.queue_items)

    def update_search_selection(self):
        count = self.search_scroll.selected_count()
        self.search_sel_lbl.configure(text=f"{count}개 선택" if count else "선택한 곡 없음")

    def on_hide_queued_changed(self):
        self.search_scroll.hide_queued = bool(self.search_hide_queued_var.get())
        self.search_scroll.refresh_queued()

    # ------------------------------------------------------------------
    # '지금 받는 중' 카드
    # ------------------------------------------------------------------
    def set_now_step(self, current):
        """분석 → 다운로드 → 변환 중 현재 단계를 흰 블록으로 채운다."""
        order = ("analyze", "download", "convert")
        reached = order.index(current) if current in order else -1
        for i, key in enumerate(order):
            label = self.now_step_lbls[key]
            base = label.cget("text").replace(" ✓", "").strip()
            if i < reached:
                label.configure(text=f"  {base} ✓  ", fg_color=C_SURFACE_DEEP, text_color=C_ASH)
            elif i == reached:
                label.configure(text=f"  {base}  ", fg_color=C_PEARL, text_color=C_SURFACE_DEEP)
            else:
                label.configure(text=f"  {base}  ", fg_color=C_SURFACE_DEEP, text_color=C_STEEL)

    def show_running_view(self, running):
        """받는 중에는 카드·중단 버튼·잠금 안내를 보이고, 끝나면 시작 버튼으로 돌린다."""
        if running:
            convert = "병합" if self.format_var.get() == 'MP4' else f"{self.format_var.get()} 변환"
            self.now_step_lbls["convert"].configure(text=f"  {convert}  ")
            self.set_now_step("analyze")
            self.now_card.configure(border_color=C_GIALLO)
            self.now_steps_row.pack(fill="x", pady=(6, 8), before=self.cur_prog_bar)
            self.queue_status_lbl.configure(text="받을 준비 중…", text_color=C_PEARL)
            self.cur_prog_bar.set(0.0)
            self.cur_stats_lbl.configure(text="")
            self.now_card.grid()
            self.settings_lock_lbl.pack(side="right")
            self.download_selected_btn.pack_forget()
            self.download_all_btn.pack_forget()
            self.stop_download_btn.pack(side="right", padx=(0, 24))
            self.stop_hint_lbl.pack(side="right", padx=(0, 12))
        else:
            # 결과를 남겨 두되 받는 중이 아님을 노랑 테두리로 구분한다
            self.now_card.configure(border_color=C_GRAPHITE)
            self.now_steps_row.pack_forget()
            self.now_order_lbl.configure(text="")
            self.settings_lock_lbl.pack_forget()
            self.stop_download_btn.pack_forget()
            self.stop_hint_lbl.pack_forget()
            self.download_all_btn.pack(side="right", padx=(0, 24))
            self.download_selected_btn.pack(side="right", padx=(0, 8))
        self.sidebar.set_live(running)
        self.sidebar.set_stop_enabled(running)
        self.sidebar.show_progress(running and self.current_screen != "queue")

    def on_batch_download_complete(self):
        self.set_controls_locked(False)

        # 성공/실패/중단 개수를 사실대로 보고한다.
        # 예전에는 stop_requested 만 보고 분기해서 전량 실패도 초록색 '완료' 로 표시했다.
        tally = getattr(self, 'last_batch_tally', None) or {}
        done = tally.get('done', 0)
        failed = tally.get('failed', 0)
        stopped = tally.get('stopped', 0)
        # MP4 는 '곡' 이 아니라 '편' 이다
        unit = "편" if self.active_format == 'MP4' else "곡"
        message, all_ok = describe_batch_result(
            done, failed, stopped, total=tally.get('total'), unit=unit)

        color = C_SUCCESS if all_ok else (C_DANGER if failed else C_TEXT_MUTED)
        self.queue_status_lbl.configure(text=f"지난 받기 결과: {message}", text_color=color)
        self.cur_prog_bar.set(1.0 if all_ok else 0.0)
        self.cur_stats_lbl.configure(text=describe_batch_detail(done, failed, stopped))
        # 성공한 만큼만 채운다. 실패인데 100% 면 진행 바가 거짓말을 한다
        self.total_prog_bar.set(batch_progress_value(done, failed, stopped))
        self.overall_status_lbl.configure(text=f"전체: {message}")
        self.stop_requested = False
        self.stop_message = None

        if self.pending_added_during_batch:
            count = self.pending_added_during_batch
            self.pending_added_during_batch = 0
            self.show_error(
                f"다운로드 중에 추가된 {count}개 항목은 이번 배치에 포함되지 않았습니다."
                + BR + BR
                + "대기열에 그대로 남아 있으니 '대기 중인 곡 모두 받기' 를 다시 눌러 주세요."
            )

        self.refresh_file_list()

    def update_progress_loop(self):
        # 일괄 다운로드 진행 중 실시간 진행 정보 업데이트
        # 검사와 인덱싱 사이에 워커가 값을 바꿀 수 있으므로 한 번만 읽는다
        idx = self.current_download_idx
        if self.batch_running and 0 <= idx < len(self.queue_items):
            item = self.queue_items[idx]
            status = self.current_download_status['status']

            # 중단 안내 문구가 100ms 뒤 이 루프에 덮여 사라지던 문제를 막는다
            if self.stop_requested and self.stop_message:
                self.queue_status_lbl.configure(text=self.stop_message, text_color=C_DANGER)
            elif status in ('downloading', 'converting'):
                # 단계는 카드의 단계 표시가 보여 주므로 제목에는 곡 이름만 둔다
                title = item['title']
                self.queue_status_lbl.configure(
                    text=title if len(title) <= 48 else title[:47] + "…",
                    text_color=C_PEARL,
                )

            if status == 'downloading':
                self.cur_prog_bar.set(self.current_download_status['percent'])
                self.cur_stats_lbl.configure(
                    text=f"{self.current_download_status['percent']*100:.1f}% · {self.current_download_status['speed']} · 남은 시간 {self.current_download_status['eta']}"
                )
            elif status == 'converting' and not self.stop_requested:
                # 변환 진행률은 알 수 없다. 100% 로 얼려두면 멈춘 것처럼 보이므로
                # 막대를 좌우로 움직여 살아 있음을 보인다.
                # 중단을 요청한 뒤에는 경과 시간을 계속 늘리지 않는다.
                self.convert_pulse = (getattr(self, 'convert_pulse', 0) + 1) % 40
                self.cur_prog_bar.set(0.3 + 0.4 * abs(20 - self.convert_pulse) / 20)
                started = self.convert_started_at
                elapsed = int(time.time() - started) if started else 0
                self.cur_stats_lbl.configure(
                    text=f"{describe_postprocess_stage(self.active_format)} 경과 {elapsed}초"
                    " · 이 단계는 곡 길이에 따라 수 분 걸릴 수 있습니다."
                )

            # 전체 진행률 바 업데이트
            self.total_prog_bar.set(self.overall_progress)
            self.overall_status_lbl.configure(text=f"전체 진행 {self.overall_progress*100:.0f}%")
            self.sync_progress_extras(idx, item, status)

        # 100ms 간격 주기 호출
        self.after(100, self.update_progress_loop)

    def sync_progress_extras(self, idx, item, status):
        """카드의 순서·단계, 목록 한 줄의 %, 사이드바 요약을 같은 값으로 맞춘다."""
        position, total = self.batch_position
        unit = "편" if self.active_format == 'MP4' else "곡"
        self.now_order_lbl.configure(text=f"{position} / {total}{unit}째")

        percent = self.current_download_status.get('percent', 0.0)
        if status == 'converting':
            self.set_now_step("convert")
        elif percent <= 0 and self.current_download_status.get('speed') == '계산 중...':
            # 첫 바이트가 오기 전은 yt-dlp 가 영상 정보를 읽는 단계다
            self.set_now_step("analyze")
        else:
            self.set_now_step("download")

        if status == 'downloading':
            self.queue_scroll.set_row_status_text(idx, f"● 다운로드 중 {percent*100:.0f}%")

        if self.current_screen != "queue":
            self.sidebar.update_progress(
                eyebrow=f"받는 중 · {position} / {total}",
                title=item['title'],
                cur_value=self.cur_prog_bar.get(),
                cur_text=(f"{percent*100:.0f}% · {self.current_download_status.get('speed', '')}"
                          if status == 'downloading' else describe_postprocess_stage(self.active_format)),
                total_value=self.overall_progress,
                total_text=f"전체 {self.overall_progress*100:.0f}%",
            )

    def browse_save_dir(self):
        selected_dir = filedialog.askdirectory(initialdir=self.save_dir_var.get())
        if selected_dir:
            self.save_dir_var.set(os.path.normpath(selected_dir))
            self.refresh_file_list()

    def refresh_file_list(self):
        """저장 폴더를 다시 읽어 음성·영상 목록을 채운다. 크기와 받은 날도 함께 읽는다."""
        save_dir, _dir_ok = resolve_save_dir(self.save_dir_var.get())

        found = {'audio': [], 'video': []}
        try:
            for f in os.listdir(save_dir):
                full_path = os.path.join(save_dir, f)
                if not os.path.isfile(full_path):
                    continue
                lower = f.lower()
                kind = 'audio' if lower.endswith(AUDIO_EXTS) else (
                    'video' if lower.endswith(VIDEO_EXTS) else None)
                if kind is None:
                    continue
                stat = os.stat(full_path)
                found[kind].append({
                    'name': f,
                    'ext': os.path.splitext(f)[1][1:].upper(),
                    'size': stat.st_size,
                    'mtime': stat.st_mtime,
                })
        except Exception as e:
            # --windowed 빌드에는 stdout 이 없어 print 는 흔적조차 남기지 못한다
            self.show_error("파일 목록을 읽지 못했습니다." + BR + BR + str(e))

        self.file_entries = found
        self.file_dir = save_dir
        for kind in ('audio', 'video'):
            self.apply_file_view(kind)

    def apply_file_view(self, kind):
        """찾기 · 형식 칩 · 정렬을 적용해 목록을 다시 그린다. 폴더는 다시 읽지 않는다."""
        view = self.file_views[kind]
        entries = self.file_entries.get(kind, [])
        shown = filter_sort_files(entries, view['filter_entry'].get(), view['ext'], view['sort'])
        save_dir = getattr(self, 'file_dir', None) or resolve_save_dir(self.save_dir_var.get())[0]
        frame = self.scroll_audio_frame if kind == 'audio' else self.scroll_video_frame
        empty = view['empty'] if not entries else "찾는 조건에 맞는 파일이 없습니다."
        frame.populate_files(
            shown,
            lambda fname: self.play_file(os.path.join(save_dir, fname)),
            lambda fname: self.delete_file(os.path.join(save_dir, fname)),
            empty_text=empty,
            new_since=self.session_started_at,
        )

        total_size = sum(e['size'] for e in entries)
        view['count_lbl'].configure(
            text=f"{len(entries)}개 · {format_size(total_size)}" if entries else "")
        for ext, button in view['ext_btns'].items():
            n = len(entries) if ext == "전체" else sum(1 for e in entries if e['ext'] == ext)
            button.configure(text=chip_text(ext, n))
        self.sidebar.set_count(kind, len(entries))

    def set_file_ext(self, kind, ext):
        view = self.file_views[kind]
        view['ext'] = ext
        for key, button in view['ext_btns'].items():
            style_chip(button, key == ext)
        self.apply_file_view(kind)

    def set_file_sort(self, kind, label):
        self.file_views[kind]['sort'] = FILE_SORTS.get(label, "recent")
        self.apply_file_view(kind)

    def play_file(self, fullpath):
        try:
            os.startfile(fullpath)
        except Exception as e:
            self.show_error(f"재생 실패:\n{e}")

    def delete_file(self, fullpath):
        if self.block_if_downloading('파일을 삭제할'):
            return
        filename = os.path.basename(fullpath)
        dialog = ctk.CTkInputDialog(text=f"정말로 '{filename}' 파일을 삭제하시겠습니까?\n삭제하려면 'yes'를 입력해 주세요.", title="파일 삭제 확인")
        response = dialog.get_input()
        if response and response.strip().lower() == 'yes':
            try:
                os.remove(fullpath)
                self.refresh_file_list()
            except Exception as e:
                self.show_error(f"파일 삭제 오류:\n{e}")

    def delete_all_completed_audio(self):
        if self.block_if_downloading('파일을 삭제할'):
            return
        save_dir, _dir_ok = resolve_save_dir(self.save_dir_var.get())
        audio_files = []
        try:
            for f in os.listdir(save_dir):
                if os.path.isfile(os.path.join(save_dir, f)) and f.lower().endswith(('.mp3', '.flac')):
                    audio_files.append(f)
        except Exception as e:
            self.show_error(f"파일 목록 조회 실패:\n{e}")
            return

        if not audio_files:
            self.show_error("삭제할 완료 음성 파일이 없습니다.")
            return

        word_count, word_kind = len(audio_files), "음성"
        dialog = ctk.CTkInputDialog(
            text=f"다음 폴더의 {word_count}개 {word_kind} 파일을 영구 삭제합니다.\n{save_dir}\n\n이 폴더의 모든 {word_kind} 파일이 대상입니다. 앱이 받지 않은 파일도 포함됩니다.\n삭제하려면 'yes' 를 입력해 주세요.",
            title="완료 음성 파일 전체 삭제 확인"
        )
        response = dialog.get_input()
        if response and response.strip().lower() == 'yes':
            deleted_count = 0
            errors = []
            for f in audio_files:
                try:
                    os.remove(os.path.join(save_dir, f))
                    deleted_count += 1
                except Exception as e:
                    errors.append(f"{f}: {e}")
            self.refresh_file_list()
            if errors:
                err_msg = "\n".join(errors[:5])
                if len(errors) > 5:
                    err_msg += f"\n외 {len(errors)-5}개 파일"
                self.show_error(f"{deleted_count}개 파일 삭제 완료 (일부 실패):\n{err_msg}")

    def delete_all_completed_video(self):
        if self.block_if_downloading('파일을 삭제할'):
            return
        save_dir, _dir_ok = resolve_save_dir(self.save_dir_var.get())
        video_files = []
        try:
            for f in os.listdir(save_dir):
                if os.path.isfile(os.path.join(save_dir, f)) and f.lower().endswith(('.mp4', '.mkv', '.webm', '.avi')):
                    video_files.append(f)
        except Exception as e:
            self.show_error(f"파일 목록 조회 실패:\n{e}")
            return

        if not video_files:
            self.show_error("삭제할 완료 영상 파일이 없습니다.")
            return

        word_count, word_kind = len(video_files), "영상"
        dialog = ctk.CTkInputDialog(
            text=f"다음 폴더의 {word_count}개 {word_kind} 파일을 영구 삭제합니다.\n{save_dir}\n\n이 폴더의 모든 {word_kind} 파일이 대상입니다. 앱이 받지 않은 파일도 포함됩니다.\n삭제하려면 'yes' 를 입력해 주세요.",
            title="완료 영상 파일 전체 삭제 확인"
        )
        response = dialog.get_input()
        if response and response.strip().lower() == 'yes':
            deleted_count = 0
            errors = []
            for f in video_files:
                try:
                    os.remove(os.path.join(save_dir, f))
                    deleted_count += 1
                except Exception as e:
                    errors.append(f"{f}: {e}")
            self.refresh_file_list()
            if errors:
                err_msg = "\n".join(errors[:5])
                if len(errors) > 5:
                    err_msg += f"\n외 {len(errors)-5}개 파일"
                self.show_error(f"{deleted_count}개 파일 삭제 완료 (일부 실패):\n{err_msg}")

    def open_download_folder(self):
        save_dir, _dir_ok = resolve_save_dir(self.save_dir_var.get())
        try:
            os.startfile(save_dir)
        except Exception as e:
            self.show_error(f"폴더 열기 실패:\n{e}")

    def block_if_downloading(self, action_text):
        """다운로드 중에 파일을 건드리면 진행 중인 작업이 깨지므로 막는다."""
        if self.batch_running:
            self.show_error(
                f"다운로드가 진행 중입니다."
                + BR + BR
                + f"진행 중에는 {action_text} 수 없습니다. 완료 후 다시 시도해 주세요."
            )
            return True
        return False

    def set_controls_locked(self, locked):
        """다운로드 중 바뀌면 안 되는 컨트롤을 한 곳에서 잠그고 푼다.

        형식/음질을 도중에 바꾸면 화면 설정과 결과물이 어긋나고,
        저장 폴더를 바꾸면 한 배치 결과가 두 폴더로 흩어진다.
        """
        state = "disabled" if locked else "normal"
        for widget_name in LOCKED_WIDGETS:
            widget = getattr(self, widget_name, None)
            if widget is not None:
                try:
                    widget.configure(state=state)
                except Exception:
                    pass

        if locked:
            self.stop_download_btn.configure(
                state="normal", border_color=C_PEARL, text_color=C_PEARL)
        else:
            self.stop_download_btn.configure(
                state="disabled", border_color=C_GRAPHITE, text_color=C_GRAPHITE)

        # 대기열 항목의 체크박스/제거 버튼도 함께 잠근다
        try:
            self.queue_scroll.set_locked(locked)
        except Exception:
            pass

        # 음질은 MP3 일 때만 열려 있어야 한다. 잠금을 풀며 일괄로 열린 것을 되돌린다
        if not locked:
            self.on_format_changed(self.format_var.get())
        self.show_running_view(locked)

    def confirm_exit_during_download(self):
        """다운로드 진행 중 종료를 사용자에게 확인받는다."""
        return messagebox.askyesno(
            "다운로드 진행 중",
            "아직 다운로드가 진행 중입니다.\n\n"
            "지금 종료하면 받고 있던 파일은 완성되지 않은 채 저장 폴더에 남습니다.\n"
            "종료할까요?",
            icon="warning",
            parent=self,
        )

    def on_closing(self):
        """창 닫기(X) 처리. 진행 중이면 확인을 받고 워커를 정리한 뒤 닫는다."""
        if self.batch_running and not self.confirm_exit_during_download():
            return

        # 진행 중인 다운로드에 중단을 알린다
        self.stop_requested = True

        # 변환 중이면 ffmpeg 를 먼저 끊어야 워커의 finally 가 돌아 임시 폴더가 정리된다
        try:
            terminate_child_ffmpeg()
        except Exception:
            pass

        # 썸네일 워커는 non-daemon 이라 정리하지 않으면 창이 닫힌 뒤에도 프로세스가 남는다
        # 각각 따로 감싼다. 앞이 실패해도 뒤가 반드시 실행돼야 프로세스가 남지 않는다.
        try:
            self.search_scroll.cancel_render()
        except Exception:
            pass
        try:
            self.search_scroll.thumb_executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

        self.destroy()

    def show_error(self, message):
        # 이미 알림창이 떠 있으면 새로 만들지 않는다.
        # 새 창을 띄우면 Tk 의 grab 이 넘어가 모달이 무너지고 창이 계속 쌓인다.
        existing = getattr(self, '_error_win', None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    merged = merge_error_messages(self._error_text, message)
                    self._error_text = merged
                    self._error_label.configure(text=merged)
                    width, height = measure_error_dialog(merged)
                    existing.geometry(f"{width}x{height}")
                    existing.lift()
                    existing.focus_force()
                    return
            except Exception:
                pass
        self._error_win = None

        err_win = ctk.CTkToplevel(self)
        err_win.title("알림")
        width, height = measure_error_dialog(message)
        err_win.geometry(f"{width}x{height}")
        err_win.minsize(DIALOG_MIN_WIDTH, DIALOG_MIN_HEIGHT)
        # 잘린 내용을 사용자가 직접 볼 수 있도록 크기 조절을 허용한다
        err_win.resizable(True, True)
        err_win.transient(self)

        # 모달 제어
        err_win.grab_set()

        def close():
            self._error_win = None
            self._error_text = ""
            err_win.destroy()

        err_win.protocol("WM_DELETE_WINDOW", close)

        # 확인 버튼이 항상 보이도록 버튼을 먼저 배치하고 본문이 남은 공간을 쓴다
        ok_btn = ctk.CTkButton(
            err_win,
            text="확인",
            text_color=C_SURFACE_DEEP,
            width=100,
            fg_color=C_GIALLO,
            command=close,
            corner_radius=RADIUS_BUTTON
        )
        ok_btn.pack(side="bottom", pady=(0, 20))

        body = ctk.CTkScrollableFrame(err_win, fg_color="transparent")
        body.pack(side="top", expand=True, fill="both", padx=20, pady=(20, 10))

        label = ctk.CTkLabel(body, text=message, font=FONT_BODY,
                             justify="left", wraplength=width - 90)
        label.pack(expand=True, fill="both")

        # 창을 키우면 글줄도 따라 늘어나야 한다
        def on_resize(event):
            try:
                label.configure(wraplength=max(200, event.width - 90))
            except Exception:
                pass

        err_win.bind("<Configure>", on_resize)

        self._error_win = err_win
        self._error_label = label
        self._error_text = message
