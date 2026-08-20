import os
import sys
import re
import shutil
import threading
import time
import urllib.request
import webbrowser
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import yt_dlp

# 패키지로 옮긴 모듈들. gui_app 이름으로 참조하던 곳(테스트·배치 파일)이
# 그대로 동작하도록 재수출한다.
from utube_downloader.theme import *  # noqa: F401,F403
from utube_downloader.theme import tracked, LOCKED_WIDGETS  # noqa: F401
from utube_downloader.urls import (  # noqa: F401
    extract_video_id, is_same_video, is_playlist_info,
)
from utube_downloader.storage import (  # noqa: F401
    TEMP_DIR_NAME, resolve_save_dir, escape_ydl_path, cleanup_temp_dir,
)
from utube_downloader.winproc import (  # noqa: F401
    terminate_child_ffmpeg, bind_children_to_process_lifetime, resource_path,
)
from utube_downloader.downloader import (  # noqa: F401
    describe_download_error, build_ydl_opts,
)
from utube_downloader.formatting import (  # noqa: F401
    UNKNOWN_TIME, BR, SEARCH_TIMEOUT_MS, SEARCH_INITIAL_TEXT, SEARCH_NO_RESULT_TEXT,
    format_duration, format_eta, describe_batch_result, describe_batch_detail,
    batch_progress_value, describe_postprocess_stage, measure_error_dialog,
    merge_error_messages,
)









































# ---------------------------------------------------------------------------
# 디자인 토큰 — design.md (Lamborghini.com 스타일 레퍼런스)
# "쇼룸 블랙 위에 스포트라이트를 받는 노란 차 한 대"
#
# 규칙 세 가지를 지킨다.
#   1) 노랑(Giallo Vivo)은 화면당 단 하나. 그 화면의 주 동작에만 쓴다.
#   2) 모서리 반경은 전부 0. 하드 엣지가 이 브랜드의 뼈대다.
#   3) 구분은 그림자나 테두리가 아니라 면 색 대비와 여백으로 한다.
# ---------------------------------------------------------------------------

















# 시스템 인코딩 및 테마 설정

class ScrollableFileFrame(ctk.CTkScrollableFrame):
    """다운로드 완료 목록을 보여주는 스크롤 프레임"""
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.file_items = []
        
    def populate_files(self, files, play_callback, delete_callback, empty_text="다운로드된 파일이 없습니다."):
        for item in self.file_items:
            item.destroy()
        self.file_items.clear()
        
        if not files:
            label = ctk.CTkLabel(self, text=empty_text, font=FONT_ITEM, text_color=C_TEXT_DIM)
            label.pack(pady=20)
            self.file_items.append(label)
            return
            
        for f in files:
            frame = ctk.CTkFrame(self, fg_color=C_SURFACE_DEEP, corner_radius=RADIUS_CARD)
            frame.pack(fill="x", pady=4, padx=5)
            
            ext = os.path.splitext(f)[1].upper()
            if ext == ".MP3":
                ext_color = C_ACCENT
            elif ext == ".FLAC":
                ext_color = C_SUCCESS
            elif ext == ".MP4":
                ext_color = C_WARNING
            else:
                ext_color = C_TEXT_DIM
            ext_label = ctk.CTkLabel(frame, text=ext.replace(".", ""), font=FONT_LABEL_BOLD, text_color=ext_color, width=45)
            ext_label.pack(side="left", padx=(10, 5), pady=8)
            
            file_label = ctk.CTkLabel(frame, text=f, anchor="w", font=FONT_BODY, text_color=C_TEXT)
            file_label.pack(side="left", fill="x", expand=True, padx=5)
            
            play_btn = ctk.CTkButton(
                frame, 
                text="재생",
            text_color=C_PEARL, 
                width=50, 
                height=26,
                fg_color="transparent",
            border_width=1,
            border_color=C_STEEL,
                hover_color=C_GRAPHITE,
                font=FONT_LABEL_BOLD,
                command=lambda fname=f: play_callback(fname)
            )
            play_btn.pack(side="right", padx=5)
            
            del_btn = ctk.CTkButton(
                frame, 
                text="삭제",
            text_color=C_PEARL, 
                width=50, 
                height=26,
                fg_color="transparent",
            border_width=1,
            border_color=C_STEEL,
                hover_color=C_GRAPHITE,
                font=FONT_LABEL_BOLD,
                command=lambda fname=f: delete_callback(fname)
            )
            del_btn.pack(side="right", padx=(0, 10))
            
            self.file_items.append(frame)


class ScrollableSearchFrame(ctk.CTkScrollableFrame):
    """유튜브 검색 결과를 보여주는 스크롤 프레임"""
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.search_widgets = []
        self.search_results_data = [] # 검색결과 저장용
        self.render_job = None        # 점진 렌더링 예약 핸들
        self.thumb_executor = ThreadPoolExecutor(max_workers=8) # 썸네일 동시 다운로드 풀 제한 (100개 검색 대비 부하 관리)
        
    def load_thumbnail_async(self, thumb_url, label_widget):
        try:
            if not thumb_url:
                raise Exception("No thumbnail URL")
            req = urllib.request.Request(
                thumb_url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                data = response.read()
            img = Image.open(BytesIO(data))
            img = img.resize((80, 45), Image.Resampling.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(80, 45))
            
            def set_img():
                if label_widget.winfo_exists():
                    label_widget.configure(text="", image=ctk_img)
                    label_widget.image = ctk_img
            label_widget.after(0, set_img)
        except Exception:
            def set_fail():
                if label_widget.winfo_exists():
                    label_widget.configure(text="No Image", text_color=C_TEXT_FAINT)
            label_widget.after(0, set_fail)

    def cancel_render(self):
        """진행 중인 점진 렌더링을 취소한다. 새 검색이 들어오면 반드시 호출해야 한다."""
        if self.render_job is not None:
            try:
                self.after_cancel(self.render_job)
            except Exception:
                pass
            self.render_job = None

    def populate_results(self, results, empty_text=SEARCH_INITIAL_TEXT):
        self.cancel_render()
        for widget in self.search_widgets:
            widget.destroy()
        self.search_widgets.clear()
        self.search_results_data.clear()

        if not results:
            label = ctk.CTkLabel(self, text=empty_text, font=FONT_ITEM, text_color=C_TEXT_DIM)
            label.pack(pady=40)
            self.search_widgets.append(label)
            return

        # 데이터는 즉시 전부 채운다. 위젯만 나눠 그린다.
        # 그러지 않으면 렌더링이 끝나기 전에 '선택 항목 추가' 를 누른 곡이 누락된다.
        for item in results:
            self.search_results_data.append({
                'title': item['title'],
                'url': item['url'],
                'duration': item['duration'],
                'uploader': item['uploader'],
                'check_var': ctk.BooleanVar(value=False),
            })

        # 100건을 한 번에 그리면 위젯 700개를 동기 생성해 UI 가 수 초간 멈춘다.
        # 한 번에 조금씩 그려 이벤트 루프에 숨 쉴 틈을 준다.
        self._render_chunk(results, 0)

    def _render_chunk(self, results, start, chunk_size=8):
        self.render_job = None

        # 새 검색이 데이터를 비운 뒤 낡은 청크가 돌면 인덱스가 어긋난다.
        # 취소가 한 박자 늦을 수 있으므로 여기서도 확인한다.
        if len(self.search_results_data) != len(results):
            return

        for idx, item in enumerate(results[start:start + chunk_size], start=start):
            try:
                self._render_row(idx, item)
            except Exception:
                # 한 행의 실패로 나머지 결과가 통째로 사라지면 안 된다
                pass

        next_start = start + chunk_size
        if next_start < len(results):
            self.render_job = self.after(1, self._render_chunk, results, next_start, chunk_size)

    def _render_row(self, idx, item):
        frame = ctk.CTkFrame(self, fg_color=C_SURFACE_DEEP, corner_radius=RADIUS_CARD)
        frame.pack(fill="x", pady=4, padx=5)
            
        # populate_results 에서 미리 만들어 둔 체크 변수를 재사용한다
        check_var = self.search_results_data[idx]['check_var']
        chk = ctk.CTkCheckBox(
            frame, text="", variable=check_var, width=20,
            corner_radius=RADIUS_CARD, checkbox_width=18, checkbox_height=18,
            fg_color=C_PEARL, hover_color=C_ASH, checkmark_color=C_SURFACE_DEEP,
            border_color=C_STEEL, border_width=1)
        chk.pack(side="left", padx=(10, 5), pady=10)
            
        # 썸네일 이미지 라벨 (플레이스홀더 상태로 선설정)
        thumbnail_lbl = ctk.CTkLabel(
            frame, 
            text="로딩 중...", 
            width=80, 
            height=45, 
            fg_color=C_SURFACE_DEEP, 
            font=FONT_CAPTION, 
            text_color=C_TEXT_DIM
        )
        thumbnail_lbl.pack(side="left", padx=5, pady=5)
            
        # 바로 재생 버튼 (우측 고정 점유를 위해 info_frame보다 먼저 pack)
        play_btn = ctk.CTkButton(
            frame,
            text="▶ 재생",
            text_color=C_PEARL,
            width=60,
            height=26,
            fg_color="transparent",
            border_width=1,
            border_color=C_STEEL,
            hover_color=C_GRAPHITE,
            font=FONT_LABEL_BOLD,
            command=lambda url=item['url']: webbrowser.open(url)
        )
        play_btn.pack(side="right", padx=(5, 10), pady=10)
            
        # 제목 및 정보 텍스트 결합 프레임 (남은 공간을 유동적으로 사용)
        info_frame = ctk.CTkFrame(frame, fg_color="transparent")
        info_frame.pack(side="left", fill="x", expand=True, padx=10, pady=5)
            
        title_lbl = ctk.CTkLabel(
            info_frame, 
            text=item['title'], 
            anchor="w", 
            font=FONT_BODY_BOLD, 
            text_color=C_TEXT,
            justify="left",
            wraplength=420  # 제목이 너무 길 경우 겹치지 않고 줄바꿈되도록 wraplength 지정
        )
        title_lbl.pack(fill="x", anchor="w")
            
        sub_lbl = ctk.CTkLabel(
            info_frame, 
            text=f"채널: {item['uploader']} | 길이: {item['duration']}", 
            anchor="w", 
            font=FONT_LABEL, 
            text_color=C_TEXT_DIM
        )
        sub_lbl.pack(fill="x", anchor="w")
            
        # 비동기 썸네일 다운로드 시작 (ThreadPoolExecutor로 부하 분산)
        thumb_url = item.get('thumbnail')
        self.thumb_executor.submit(
            self.load_thumbnail_async, 
            thumb_url, 
            thumbnail_lbl
        )
            
        # 검색결과 데이터 수집
        self.search_widgets.append(frame)

    def get_selected_items(self):
        selected = []
        for item in self.search_results_data:
            if item['check_var'].get():
                selected.append({
                    'title': item['title'],
                    'url': item['url'],
                    'duration': item['duration'],
                    'uploader': item['uploader']
                })
        return selected


class ScrollableQueueFrame(ctk.CTkScrollableFrame):
    """다운로드 대기열 목록을 보여주는 스크롤 프레임"""
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.queue_widgets = []
        self.row_controls = []   # 다운로드 중 잠글 체크박스·제거 버튼
        self.locked = False

    def set_locked(self, locked):
        """다운로드 중에는 체크박스와 제거 버튼을 눌리지 않게 한다.

        예전에는 눌러도 조용히 무시돼, 사용자가 취소했다고 믿은 곡이 그대로 받아졌다.
        """
        self.locked = locked
        state = "disabled" if locked else "normal"
        for widget in self.row_controls:
            try:
                if widget.winfo_exists():
                    widget.configure(state=state)
            except Exception:
                pass
        
    def populate_queue(self, queue_items, delete_callback):
        for widget in self.queue_widgets:
            widget.destroy()
        self.queue_widgets.clear()
        self.row_controls.clear()
        
        if not queue_items:
            label = ctk.CTkLabel(self, text="대기열이 비어 있습니다. '검색 및 추가' 탭에서 노래를 추가해 주세요.", font=FONT_ITEM, text_color=C_TEXT_DIM)
            label.pack(pady=40)
            self.queue_widgets.append(label)
            return
            
        for idx, item in enumerate(queue_items):
            frame = ctk.CTkFrame(self, fg_color=C_SURFACE_DEEP, corner_radius=RADIUS_CARD)
            frame.pack(fill="x", pady=4, padx=5)
            
            # 체크박스 연결
            chk = ctk.CTkCheckBox(
            frame, text="", variable=item['check_var'], width=20,
            corner_radius=RADIUS_CARD, checkbox_width=18, checkbox_height=18,
            fg_color=C_PEARL, hover_color=C_ASH, checkmark_color=C_SURFACE_DEEP,
            border_color=C_STEEL, border_width=1)
            chk.pack(side="left", padx=(10, 5), pady=10)
            self.row_controls.append(chk)
            
            # 정보 텍스트 프레임
            info_frame = ctk.CTkFrame(frame, fg_color="transparent")
            info_frame.pack(side="left", fill="x", expand=True, padx=5, pady=5)
            
            title_lbl = ctk.CTkLabel(
                info_frame, 
                text=item['title'], 
                anchor="w", 
                font=FONT_BODY_BOLD, 
                text_color=C_TEXT,
                justify="left"
            )
            title_lbl.pack(fill="x", anchor="w")
            
            # 상태에 따른 텍스트 컬러 지정
            status = item['status']
            status_text = "대기 중"
            status_color = C_TEXT_DIM
            
            if status == 'analyzing':
                status_text = "분석 중..."
                status_color = C_WARNING
            elif status == 'downloading':
                status_text = "다운로드 중..."
                status_color = C_PEARL
            elif status == 'converting':
                status_text = "음원 변환 중..."
                status_color = C_WARNING
            elif status == 'finished':
                status_text = "완료"
                status_color = C_SUCCESS
            elif status == 'stopped':
                status_text = "사용자 중단"
                status_color = C_TEXT_MUTED
            elif status == 'failed':
                # 실패 사유를 함께 보여줘야 사용자가 조치할 수 있다
                reason = item.get('error')
                status_text = f"실패 - {reason}" if reason else "실패"
                status_color = C_DANGER
                
            sub_lbl = ctk.CTkLabel(
                info_frame, 
                text=f"채널: {item['uploader']} | 길이: {item['duration']} | 상태: {status_text}", 
                anchor="w", 
                font=FONT_LABEL, 
                text_color=status_color
            )
            sub_lbl.pack(fill="x", anchor="w")
            
            # 대기열 삭제 버튼
            del_btn = ctk.CTkButton(
                frame, 
                text="제거",
            text_color=C_PEARL, 
                width=50, 
                height=26,
                fg_color="transparent",
            border_width=1,
            border_color=C_STEEL,
                hover_color=C_GRAPHITE,
                font=FONT_LABEL_BOLD,
                command=lambda index=idx: delete_callback(index)
            )
            del_btn.pack(side="right", padx=(5, 10))
            self.row_controls.append(del_btn)
            
            self.queue_widgets.append(frame)

        # 목록을 다시 그려도 다운로드 중이면 잠금 상태를 유지한다
        if self.locked:
            self.set_locked(True)


class YoutubeDownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("YouTube Music Downloader - Batch Queue Edition")
        self.geometry("800x700")
        self.minsize(750, 650)
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
        
        self.create_widgets()
        self.refresh_file_list()
        
        # 실시간 UI 모니터링 루프 시작
        self.after(100, self.update_progress_loop)
        
    def create_widgets(self):
        # 1. 상단 타이틀
        # 헤드라인은 흰색. 노랑은 주 동작 버튼 하나에만 남겨 둔다.
        title_label = ctk.CTkLabel(
            self,
            text=tracked("YouTube Music Downloader"),
            font=FONT_TITLE,
            text_color=C_PEARL
        )
        title_label.pack(pady=(PAD_L, PAD_M))
        
        # 2. 탭 뷰 초기화
        self.tabview = ctk.CTkTabview(
            self,
            corner_radius=RADIUS_CARD,
            fg_color=C_SURFACE,
            segmented_button_fg_color=C_BG,
            # CTkTabview 는 글자색을 하나만 받는다.
            # 선택 탭을 흰 블록으로 두면 비선택 탭 글자가 묻히므로,
            # 글자는 전부 흰색으로 두고 선택은 밝은 면으로 구분한다.
            segmented_button_selected_color=C_GRAPHITE,
            segmented_button_selected_hover_color=C_GRAPHITE,
            segmented_button_unselected_color=C_BG,
            segmented_button_unselected_hover_color=C_SURFACE,
            text_color=C_PEARL,
        )
        self.tabview.pack(fill="both", expand=True, padx=PAD_M, pady=(0, PAD_M))
        
        self.tab_search = self.tabview.add("검색 및 추가")
        self.tab_queue = self.tabview.add("다운로드 대기열")
        self.tab_audio = self.tabview.add("음성 다운로드 목록")
        self.tab_video = self.tabview.add("영상 다운로드 목록")
        
        # ----------------------------------------------------
        # 탭 1: 검색 및 추가 구현
        # ----------------------------------------------------
        self.tab_search.grid_columnconfigure(0, weight=1)
        self.tab_search.grid_rowconfigure(1, weight=1)
        
        # 검색어 입력 영역 프레임
        search_bar = ctk.CTkFrame(self.tab_search, fg_color="transparent")
        search_bar.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        
        self.search_entry = ctk.CTkEntry(
            search_bar,
            placeholder_text="유튜브 검색 키워드를 입력하세요... (예: 아이유 히트곡)",
            height=36,
            font=FONT_BODY,
            corner_radius=RADIUS_CARD,
            fg_color=C_SURFACE_DEEP,
            border_color=C_GRAPHITE,
            border_width=1,
            text_color=C_PEARL,
            placeholder_text_color=C_STEEL,
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.search_entry.bind("<Return>", lambda event: self.start_search())
        
        self.search_btn = ctk.CTkButton(
            search_bar, 
            text="유튜브 검색",
            text_color=C_PEARL, 
            width=100, 
            height=35,
            fg_color="transparent",
            border_width=1,
            border_color=C_STEEL,
            hover_color=C_GRAPHITE,
            font=FONT_BODY_BOLD,
            command=self.start_search,
            corner_radius=RADIUS_BUTTON
        )
        self.search_btn.pack(side="right", padx=(5, 0))
        
        # 검색 결과 스크롤 프레임
        self.search_scroll = ScrollableSearchFrame(self.tab_search, fg_color="transparent")
        self.search_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        self.search_scroll.populate_results([])
        
        # 대기열에 추가 버튼 프레임
        search_action_bar = ctk.CTkFrame(self.tab_search, fg_color="transparent")
        search_action_bar.grid(row=2, column=0, sticky="ew", padx=10, pady=(5, 10))
        
        self.add_queue_btn = ctk.CTkButton(
            search_action_bar, 
            text="선택한 항목 다운로드 대기열에 추가", 
            height=38,
            fg_color=C_GIALLO,
            hover_color=C_GIALLO_SHADE,
            text_color=C_SURFACE_DEEP,
            font=FONT_HEADING,
            command=self.add_selected_to_queue,
            corner_radius=RADIUS_BUTTON
        )
        self.add_queue_btn.pack(fill="x")
        
        # ----------------------------------------------------
        # 탭 2: 다운로드 대기열 구현
        # ----------------------------------------------------
        self.tab_queue.grid_columnconfigure(0, weight=1)
        self.tab_queue.grid_rowconfigure(0, weight=1)
        
        # 대기열 스크롤 프레임
        self.queue_scroll = ScrollableQueueFrame(self.tab_queue, fg_color="transparent")
        self.queue_scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=5)
        self.queue_scroll.populate_queue(self.queue_items, self.delete_queue_item)
        
        # 대기열 하단 제어 및 설정 영역
        queue_ctrl_frame = ctk.CTkFrame(self.tab_queue, fg_color=C_SURFACE, corner_radius=RADIUS_CARD)
        queue_ctrl_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(5, 10))
        
        # 직접 링크 추가 영역
        direct_add_row = ctk.CTkFrame(queue_ctrl_frame, fg_color="transparent")
        direct_add_row.pack(fill="x", padx=15, pady=(10, 5))
        
        ctk.CTkLabel(direct_add_row, text="유튜브 링크 직접 추가:", font=FONT_BODY_BOLD, text_color=C_TEXT_MUTED).pack(side="left", padx=(0, 5))
        
        self.direct_url_entry = ctk.CTkEntry(
            direct_add_row, 
            placeholder_text="https://www.youtube.com/watch?v=...", 
            height=30,
            font=FONT_LABEL,
            corner_radius=RADIUS_CARD,
            fg_color=C_SURFACE_DEEP,
            border_color=C_GRAPHITE,
            border_width=1,
            text_color=C_PEARL,
            placeholder_text_color=C_STEEL,
        )
        self.direct_url_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.direct_url_entry.bind("<Return>", lambda event: self.add_direct_url())
        
        self.direct_add_btn = ctk.CTkButton(
            direct_add_row, 
            text="대기열 추가",
            text_color=C_PEARL, 
            width=90, 
            height=30,
            fg_color="transparent",
            border_width=1,
            border_color=C_STEEL,
            hover_color=C_GRAPHITE,
            font=FONT_LABEL_BOLD,
            command=self.add_direct_url,
            corner_radius=RADIUS_BUTTON
        )
        self.direct_add_btn.pack(side="right", padx=(5, 0))
        
        # 저장 폴더 지정 영역 추가
        save_dir_row = ctk.CTkFrame(queue_ctrl_frame, fg_color="transparent")
        save_dir_row.pack(fill="x", padx=15, pady=(5, 5))
        
        ctk.CTkLabel(save_dir_row, text="저장 폴더 지정:", font=FONT_BODY_BOLD, text_color=C_TEXT_MUTED).pack(side="left", padx=(0, 5))
        
        self.save_dir_entry = ctk.CTkEntry(
            save_dir_row, 
            textvariable=self.save_dir_var,
            height=30,
            font=FONT_LABEL,
            corner_radius=RADIUS_CARD,
            fg_color=C_SURFACE_DEEP,
            border_color=C_GRAPHITE,
            border_width=1,
            text_color=C_PEARL,
            placeholder_text_color=C_STEEL,
        )
        self.save_dir_entry.pack(side="left", fill="x", expand=True, padx=5)
        
        self.save_dir_btn = ctk.CTkButton(
            save_dir_row, 
            text="폴더 변경",
            text_color=C_PEARL, 
            width=90, 
            height=30,
            fg_color="transparent",
            border_width=1,
            border_color=C_STEEL,
            hover_color=C_GRAPHITE,
            font=FONT_LABEL_BOLD,
            command=self.browse_save_dir,
            corner_radius=RADIUS_BUTTON
        )
        self.save_dir_btn.pack(side="right", padx=(5, 0))
        
        # 설정 1: 포맷 선택 및 음질
        settings_row = ctk.CTkFrame(queue_ctrl_frame, fg_color="transparent")
        settings_row.pack(fill="x", padx=15, pady=(5, 5))
        
        ctk.CTkLabel(settings_row, text="다운로드 형식:", font=FONT_BODY_BOLD, text_color=C_TEXT_MUTED).pack(side="left", padx=(0, 5))
        
        self.format_var = ctk.StringVar(value="MP3")
        self.format_select = ctk.CTkSegmentedButton(
            settings_row,
            values=["MP3", "FLAC", "MP4"],
            variable=self.format_var,
            command=self.on_format_changed,
            font=FONT_LABEL_BOLD,
            corner_radius=RADIUS_BUTTON,
            fg_color=C_SURFACE_DEEP,
            # 글자색을 하나만 받으므로, 선택 상태는 면 밝기로 확실히 벌린다
            selected_color=C_STEEL,
            selected_hover_color=C_STEEL,
            unselected_color=C_SURFACE_DEEP,
            unselected_hover_color=C_GRAPHITE,
            text_color=C_PEARL,
            border_width=0,
        )
        self.format_select.pack(side="left", padx=5)
        
        self.quality_label = ctk.CTkLabel(settings_row, text="음질:", font=FONT_BODY_BOLD, text_color=C_TEXT_MUTED)
        self.quality_label.pack(side="left", padx=(15, 5))
        
        self.quality_var = ctk.StringVar(value="320kbps")
        self.quality_select = ctk.CTkOptionMenu(
            settings_row,
            values=["320kbps", "256kbps", "192kbps"],
            variable=self.quality_var,
            width=100,
            font=FONT_LABEL,
            corner_radius=RADIUS_BUTTON,
            fg_color=C_SURFACE_DEEP,
            button_color=C_GRAPHITE,
            button_hover_color=C_STEEL,
            text_color=C_PEARL,
            dropdown_fg_color=C_SURFACE,
            dropdown_hover_color=C_GRAPHITE,
            dropdown_text_color=C_PEARL,
        )
        self.quality_select.pack(side="left", padx=5)
        
        self.clear_completed_btn = ctk.CTkButton(
            settings_row, 
            text="완료 항목 제거",
            text_color=C_PEARL, 
            width=100, 
            height=28,
            fg_color="transparent",
            border_width=1,
            border_color=C_STEEL,
            hover_color=C_GRAPHITE,
            font=FONT_LABEL_BOLD,
            command=self.clear_completed_queue,
            corner_radius=RADIUS_BUTTON
        )
        self.clear_completed_btn.pack(side="right", padx=(5, 5))

        self.clear_queue_btn = ctk.CTkButton(
            settings_row, 
            text="대기열 비우기",
            text_color=C_PEARL, 
            width=90, 
            height=28,
            fg_color="transparent",
            border_width=1,
            border_color=C_STEEL,
            hover_color=C_GRAPHITE,
            font=FONT_LABEL_BOLD,
            command=self.clear_queue,
            corner_radius=RADIUS_BUTTON
        )
        self.clear_queue_btn.pack(side="right", padx=(5, 0))
        
        # 설정 2: 실시간 진행 바
        self.progress_row = ctk.CTkFrame(queue_ctrl_frame, fg_color="transparent")
        self.progress_row.pack(fill="x", padx=15, pady=5)
        
        self.queue_status_lbl = ctk.CTkLabel(self.progress_row, text="대기열 상태: 대기 중", font=FONT_BODY_BOLD, text_color=C_TEXT_MUTED, anchor="w")
        self.queue_status_lbl.pack(fill="x", pady=(2, 2))
        
        # 현재 곡 진행 상황 바
        self.cur_prog_bar = ctk.CTkProgressBar(
            self.progress_row, height=PAD_S, corner_radius=RADIUS_CARD,
            fg_color=C_GRAPHITE, progress_color=C_GIALLO)
        self.cur_prog_bar.set(0.0)
        self.cur_prog_bar.pack(fill="x", pady=2)
        
        self.cur_stats_lbl = ctk.CTkLabel(self.progress_row, text="", font=FONT_LABEL, text_color=C_TEXT_DIM, anchor="e")
        self.cur_stats_lbl.pack(fill="x", pady=(0, 2))
        
        # 전체 대기열 진행 상황 바
        self.overall_status_lbl = ctk.CTkLabel(self.progress_row, text="전체 진행 상황:", font=FONT_LABEL_BOLD, text_color=C_TEXT_MUTED, anchor="w")
        self.overall_status_lbl.pack(fill="x", pady=(2, 2))
        
        self.total_prog_bar = ctk.CTkProgressBar(
            self.progress_row, height=PAD_S, corner_radius=RADIUS_CARD,
            fg_color=C_GRAPHITE, progress_color=C_PEARL)
        self.total_prog_bar.set(0.0)
        self.total_prog_bar.pack(fill="x", pady=2)
        
        # 설정 3: 일괄 다운로드 버튼
        btn_row = ctk.CTkFrame(queue_ctrl_frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=15, pady=(5, 10))
        
        self.download_selected_btn = ctk.CTkButton(
            btn_row, 
            text="선택된 항목 다운로드 시작", 
            height=38,
            fg_color="transparent",
            border_width=1,
            border_color=C_STEEL,
            hover_color=C_GRAPHITE,
            text_color=C_PEARL,
            font=FONT_HEADING,
            command=self.start_selected_download,
            corner_radius=RADIUS_BUTTON
        )
        self.download_selected_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))
        
        self.download_all_btn = ctk.CTkButton(
            btn_row, 
            text="대기열 전체 다운로드 시작",
            text_color=C_SURFACE_DEEP, 
            height=38,
            fg_color=C_GIALLO,
            hover_color=C_GIALLO_SHADE,
            font=FONT_HEADING,
            command=self.start_all_download,
            corner_radius=RADIUS_BUTTON
        )
        self.download_all_btn.pack(side="left", fill="x", expand=True, padx=4)
        
        self.stop_download_btn = ctk.CTkButton(
            btn_row,
            text="다운로드 중단",
            text_color=C_PEARL,
            height=38,
            fg_color="transparent",
            border_width=1,
            border_color=C_STEEL,
            hover_color=C_GRAPHITE,
            state="disabled",
            font=FONT_HEADING,
            command=self.request_stop_download,
            corner_radius=RADIUS_BUTTON
        )
        self.stop_download_btn.pack(side="right", fill="x", expand=True, padx=(4, 0))
        
        # ----------------------------------------------------
        # 탭 3: 음성 다운로드 목록 구현
        # ----------------------------------------------------
        self.tab_audio.grid_columnconfigure(0, weight=1)
        self.tab_audio.grid_rowconfigure(1, weight=1)
        
        audio_header = ctk.CTkFrame(self.tab_audio, fg_color="transparent")
        audio_header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        
        audio_title = ctk.CTkLabel(audio_header, text="음성 다운로드 완료 목록", font=FONT_HEADING, text_color=C_TEXT_MUTED)
        audio_title.pack(side="left", padx=5, pady=5)
        
        open_audio_folder_btn = ctk.CTkButton(
            audio_header, 
            text="폴더 열기",
            text_color=C_PEARL, 
            width=80, 
            height=26,
            fg_color="transparent",
            border_width=1,
            border_color=C_STEEL,
            hover_color=C_GRAPHITE,
            font=FONT_LABEL_BOLD,
            command=self.open_download_folder,
            corner_radius=RADIUS_BUTTON
        )
        open_audio_folder_btn.pack(side="right", padx=5)
        
        self.delete_all_audio_btn = ctk.CTkButton(
            audio_header, 
            text="목록 전체 삭제",
            text_color=C_PEARL, 
            width=100, 
            height=26,
            fg_color="transparent",
            border_width=1,
            border_color=C_STEEL,
            hover_color=C_GRAPHITE,
            font=FONT_LABEL_BOLD,
            command=self.delete_all_completed_audio,
            corner_radius=RADIUS_BUTTON
        )
        self.delete_all_audio_btn.pack(side="right", padx=5)
        
        self.scroll_audio_frame = ScrollableFileFrame(self.tab_audio, fg_color="transparent")
        self.scroll_audio_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        
        # ----------------------------------------------------
        # 탭 4: 영상 다운로드 목록 구현
        # ----------------------------------------------------
        self.tab_video.grid_columnconfigure(0, weight=1)
        self.tab_video.grid_rowconfigure(1, weight=1)
        
        video_header = ctk.CTkFrame(self.tab_video, fg_color="transparent")
        video_header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        
        video_title = ctk.CTkLabel(video_header, text="영상 다운로드 완료 목록", font=FONT_HEADING, text_color=C_TEXT_MUTED)
        video_title.pack(side="left", padx=5, pady=5)
        
        open_video_folder_btn = ctk.CTkButton(
            video_header, 
            text="폴더 열기", 
            width=80, 
            height=26,
            fg_color="transparent",
            border_width=1,
            border_color=C_STEEL,
            hover_color=C_GRAPHITE,
            text_color=C_PEARL,
            font=FONT_LABEL_BOLD,
            command=self.open_download_folder,
            corner_radius=RADIUS_BUTTON
        )
        open_video_folder_btn.pack(side="right", padx=5)
        
        self.delete_all_video_btn = ctk.CTkButton(
            video_header, 
            text="목록 전체 삭제", 
            width=100, 
            height=26,
            fg_color="transparent",
            border_width=1,
            border_color=C_STEEL,
            hover_color=C_GRAPHITE,
            text_color=C_PEARL,
            font=FONT_LABEL_BOLD,
            command=self.delete_all_completed_video,
            corner_radius=RADIUS_BUTTON
        )
        self.delete_all_video_btn.pack(side="right", padx=5)
        
        self.scroll_video_frame = ScrollableFileFrame(self.tab_video, fg_color="transparent")
        self.scroll_video_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        
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

        self.searching = True
        self.search_generation += 1
        generation = self.search_generation
        self.search_btn.configure(state="disabled", text="검색 중...")

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
        self.search_btn.configure(state="normal", text="유튜브 검색")

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
        try:
            # yt-dlp를 이용해 동영상을 다운로드 받지 않고 검색만 수행
            ydl_opts = {
                'skip_download': True,
                'extract_flat': True,
                'quiet': True,
            }
            # 검색어 100개 추출 (flat extraction으로 빠른 메타데이터 리스트 수집)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch100:{query}", download=False)
                entries = info.get('entries', [])
                
            results = []
            for entry in entries:
                duration_str = format_duration(entry.get('duration', 0))
                
                results.append({
                    'title': entry.get('title', 'Unknown Title'),
                    'url': entry.get('url', f"https://www.youtube.com/watch?v={entry.get('id')}"),
                    'duration': duration_str,
                    'uploader': entry.get('uploader', 'Unknown'),
                    'thumbnail': entry.get('thumbnail') or (f"https://img.youtube.com/vi/{entry.get('id')}/hqdefault.jpg" if entry.get('id') else None)
                })
                
            self.after(0, self.on_search_success, results, generation)
        except Exception as e:
            self.after(0, self.on_search_failed, describe_download_error(e), generation)

    def on_search_success(self, results, generation=None):
        # 세대가 어긋나도 잠금은 반드시 푼다. 안 그러면 검색이 영구히 막힌다.
        self.finish_search()
        if generation is not None and not self.is_current_search(generation):
            return  # 이미 새 검색이 시작됐다. 옛 결과는 버린다.
        self.search_scroll.populate_results(results, empty_text=SEARCH_NO_RESULT_TEXT)
        
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

        # 탭 뷰를 다운로드 대기열 탭으로 포커스 이동
        self.tabview.set("다운로드 대기열")
        
    def add_direct_url(self):
        url = self.direct_url_entry.get().strip()
        if not url:
            self.show_error("추가할 유튜브 링크를 입력해 주세요.")
            return
            
        # 대기열에 이미 존재하는지 검사 (링크 형태가 달라도 같은 영상이면 중복)
        exists = any(is_same_video(q['url'], url) for q in self.queue_items)
        if exists:
            self.show_error("이미 대기열에 존재하는 링크입니다.")
            return
            
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
        self.queue_scroll.populate_queue(self.queue_items, self.delete_queue_item)
        self.direct_url_entry.delete(0, 'end')
        
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
                        "개별 영상 링크를 넣거나 검색 탭에서 곡을 선택해 주세요."
                    ),
                })
                # Tk 변수 쓰기는 메인 스레드에서 한다
                self.after(0, item['check_var'].set, False)
                self.after(0, self.update_queue_list_ui)
                self.after(0, self.show_error,
                           f"재생목록 링크는 추가할 수 없습니다.\n\n"
                           f"'{info.get('title', url)}' 에는 영상 {count}개가 들어 있어\n"
                           f"한 항목으로 받으면 저장 폴더가 통째로 채워집니다.\n\n"
                           f"개별 영상 링크를 넣거나 검색 탭을 이용해 주세요.")
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
            self.queue_scroll.populate_queue(self.queue_items, self.delete_queue_item)
            
    def clear_queue(self):
        if self.batch_running:
            self.show_error("다운로드 중에는 대기열을 비울 수 없습니다.")
            return
        self.queue_items.clear()
        self.queue_scroll.populate_queue(self.queue_items, self.delete_queue_item)
        self.total_prog_bar.set(0.0)

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
        if value in ("FLAC", "MP4"):
            self.quality_label.pack_forget()
            self.quality_select.pack_forget()
        else:
            self.quality_label.pack(side="left", padx=(15, 5))
            self.quality_select.pack(side="left", padx=5)
            
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

        # 변환(FFmpeg) 단계에서는 progress_hook 이 불리지 않아 플래그만으로는 멈추지 않는다.
        # 실행 중인 자식 ffmpeg 를 직접 종료해야 즉시 중단된다.
        killed = terminate_child_ffmpeg()
        if killed:
            self.stop_message = "변환을 중단했습니다. 정리하는 중..."
        else:
            self.stop_message = "중단 요청됨. 현재 곡을 정리하는 중..."
        self.queue_status_lbl.configure(text=f"대기열 상태: {self.stop_message}", text_color=C_DANGER)

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
                    + "개별 영상 링크를 넣거나 검색 탭을 이용해 주세요."
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
        # 대기열 리스트 프레임 리빌드
        self.queue_scroll.populate_queue(self.queue_items, self.delete_queue_item)
        
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
        self.queue_status_lbl.configure(text=f"대기열 결과: {message}", text_color=color)
        self.cur_prog_bar.set(1.0 if all_ok else 0.0)
        self.cur_stats_lbl.configure(text=describe_batch_detail(done, failed, stopped))
        # 성공한 만큼만 채운다. 실패인데 100% 면 진행 바가 거짓말을 한다
        self.total_prog_bar.set(batch_progress_value(done, failed, stopped))
        self.overall_status_lbl.configure(text=f"전체 진행 상황: {message}")
        self.stop_requested = False
        self.stop_message = None

        if self.pending_added_during_batch:
            count = self.pending_added_during_batch
            self.pending_added_during_batch = 0
            self.show_error(
                f"다운로드 중에 추가된 {count}개 항목은 이번 배치에 포함되지 않았습니다."
                + BR + BR
                + "대기열에 그대로 남아 있으니 '선택 항목 다운로드' 를 다시 눌러 주세요."
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
                self.queue_status_lbl.configure(
                    text=f"대기열 상태: {self.stop_message}", text_color=C_DANGER)
            elif status == 'downloading':
                self.queue_status_lbl.configure(
                    text=f"현재 다운로드 중: {item['title'][:40]}...",
                    text_color=C_ACCENT
                )
            elif status == 'converting':
                # MP4 는 오디오 변환이 아니라 영상 병합이다
                stage = describe_postprocess_stage(self.active_format)
                self.queue_status_lbl.configure(
                    text=f"{stage} {item['title'][:34]}...",
                    text_color=C_WARNING
                )

            if status == 'downloading':
                self.cur_prog_bar.set(self.current_download_status['percent'])
                self.cur_stats_lbl.configure(
                    text=f"{self.current_download_status['percent']*100:.1f}% | 속도: {self.current_download_status['speed']} | 남은 시간: {self.current_download_status['eta']}"
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
            self.overall_status_lbl.configure(text=f"전체 대기열 진행 상황: {self.overall_progress*100:.1f}% 완료")

        # 100ms 간격 주기 호출
        self.after(100, self.update_progress_loop)

    def browse_save_dir(self):
        selected_dir = filedialog.askdirectory(initialdir=self.save_dir_var.get())
        if selected_dir:
            self.save_dir_var.set(os.path.normpath(selected_dir))
            self.refresh_file_list()

    def refresh_file_list(self):
        save_dir, _dir_ok = resolve_save_dir(self.save_dir_var.get())
            
        audio_files = []
        video_files = []
        try:
            for f in os.listdir(save_dir):
                full_path = os.path.join(save_dir, f)
                if os.path.isfile(full_path):
                    if f.lower().endswith(('.mp3', '.flac')):
                        audio_files.append(f)
                    elif f.lower().endswith(('.mp4', '.mkv', '.webm', '.avi')):
                        video_files.append(f)
            audio_files.sort()
            video_files.sort()
        except Exception as e:
            # --windowed 빌드에는 stdout 이 없어 print 는 흔적조차 남기지 못한다
            self.show_error("파일 목록을 읽지 못했습니다." + BR + BR + str(e))
            
        self.scroll_audio_frame.populate_files(
            audio_files, 
            lambda fname: self.play_file(os.path.join(save_dir, fname)), 
            lambda fname: self.delete_file(os.path.join(save_dir, fname)),
            empty_text="다운로드된 음성 파일이 없습니다."
        )
        
        self.scroll_video_frame.populate_files(
            video_files, 
            lambda fname: self.play_file(os.path.join(save_dir, fname)), 
            lambda fname: self.delete_file(os.path.join(save_dir, fname)),
            empty_text="다운로드된 영상 파일이 없습니다."
        )
        
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
        


if __name__ == "__main__":
    app = YoutubeDownloaderApp()
    app.mainloop()
