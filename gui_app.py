import os
import sys
import threading
import urllib.request
import webbrowser
from io import BytesIO
import customtkinter as ctk
from PIL import Image, ImageTk
import yt_dlp

# 시스템 인코딩 및 테마 설정
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

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
            label = ctk.CTkLabel(self, text=empty_text, font=("Malgun Gothic", 13), text_color="#888888")
            label.pack(pady=20)
            self.file_items.append(label)
            return
            
        for f in files:
            frame = ctk.CTkFrame(self, fg_color="#1E1E2E", corner_radius=6)
            frame.pack(fill="x", pady=4, padx=5)
            
            ext = os.path.splitext(f)[1].upper()
            if ext == ".MP3":
                ext_color = "#3A86FF"
            elif ext == ".FLAC":
                ext_color = "#06D6A0"
            elif ext == ".MP4":
                ext_color = "#F77F00"
            else:
                ext_color = "#888888"
            ext_label = ctk.CTkLabel(frame, text=ext.replace(".", ""), font=("Malgun Gothic", 11, "bold"), text_color=ext_color, width=45)
            ext_label.pack(side="left", padx=(10, 5), pady=8)
            
            file_label = ctk.CTkLabel(frame, text=f, anchor="w", font=("Malgun Gothic", 12), text_color="#E0E0E6")
            file_label.pack(side="left", fill="x", expand=True, padx=5)
            
            play_btn = ctk.CTkButton(
                frame, 
                text="재생", 
                width=50, 
                height=26,
                fg_color="#3A86FF",
                hover_color="#2563EB",
                font=("Malgun Gothic", 11, "bold"),
                command=lambda fname=f: play_callback(fname)
            )
            play_btn.pack(side="right", padx=5)
            
            del_btn = ctk.CTkButton(
                frame, 
                text="삭제", 
                width=50, 
                height=26,
                fg_color="#FF007F",
                hover_color="#CC0066",
                font=("Malgun Gothic", 11, "bold"),
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
                    label_widget.configure(text="No Image", text_color="#666666")
            label_widget.after(0, set_fail)

    def populate_results(self, results):
        for widget in self.search_widgets:
            widget.destroy()
        self.search_widgets.clear()
        self.search_results_data.clear()
        
        if not results:
            label = ctk.CTkLabel(self, text="검색 결과가 없습니다. 키워드를 입력하고 검색해 주세요.", font=("Malgun Gothic", 13), text_color="#888888")
            label.pack(pady=40)
            self.search_widgets.append(label)
            return
            
        for idx, item in enumerate(results):
            frame = ctk.CTkFrame(self, fg_color="#1E1E2E", corner_radius=6)
            frame.pack(fill="x", pady=4, padx=5)
            
            # 체크박스 변수 생성
            check_var = ctk.BooleanVar(value=False)
            chk = ctk.CTkCheckBox(frame, text="", variable=check_var, width=20)
            chk.pack(side="left", padx=(10, 5), pady=10)
            
            # 썸네일 이미지 라벨 (플레이스홀더 상태로 선설정)
            thumbnail_lbl = ctk.CTkLabel(
                frame, 
                text="로딩 중...", 
                width=80, 
                height=45, 
                fg_color="#141421", 
                font=("Malgun Gothic", 10), 
                text_color="#888888"
            )
            thumbnail_lbl.pack(side="left", padx=5, pady=5)
            
            # 제목 및 정보 텍스트 결합 프레임
            info_frame = ctk.CTkFrame(frame, fg_color="transparent")
            info_frame.pack(side="left", fill="x", expand=True, padx=10, pady=5)
            
            title_lbl = ctk.CTkLabel(
                info_frame, 
                text=item['title'], 
                anchor="w", 
                font=("Malgun Gothic", 12, "bold"), 
                text_color="#E0E0E6",
                justify="left"
            )
            title_lbl.pack(fill="x", anchor="w")
            
            sub_lbl = ctk.CTkLabel(
                info_frame, 
                text=f"채널: {item['uploader']} | 길이: {item['duration']}", 
                anchor="w", 
                font=("Malgun Gothic", 11), 
                text_color="#888888"
            )
            sub_lbl.pack(fill="x", anchor="w")
            
            # 바로 재생 버튼
            play_btn = ctk.CTkButton(
                frame,
                text="▶ 재생",
                width=60,
                height=26,
                fg_color="#3A86FF",
                hover_color="#2563EB",
                font=("Malgun Gothic", 11, "bold"),
                command=lambda url=item['url']: webbrowser.open(url)
            )
            play_btn.pack(side="right", padx=(5, 10), pady=10)
            
            # 비동기 썸네일 다운로드 시작
            thumb_url = item.get('thumbnail')
            thread = threading.Thread(
                target=self.load_thumbnail_async, 
                args=(thumb_url, thumbnail_lbl), 
                daemon=True
            )
            thread.start()
            
            # 검색결과 데이터 수집
            self.search_results_data.append({
                'title': item['title'],
                'url': item['url'],
                'duration': item['duration'],
                'uploader': item['uploader'],
                'check_var': check_var
            })
            
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
        
    def populate_queue(self, queue_items, delete_callback):
        for widget in self.queue_widgets:
            widget.destroy()
        self.queue_widgets.clear()
        
        if not queue_items:
            label = ctk.CTkLabel(self, text="대기열이 비어 있습니다. '검색 및 추가' 탭에서 노래를 추가해 주세요.", font=("Malgun Gothic", 13), text_color="#888888")
            label.pack(pady=40)
            self.queue_widgets.append(label)
            return
            
        for idx, item in enumerate(queue_items):
            frame = ctk.CTkFrame(self, fg_color="#1E1E2E", corner_radius=6)
            frame.pack(fill="x", pady=4, padx=5)
            
            # 체크박스 연결
            chk = ctk.CTkCheckBox(frame, text="", variable=item['check_var'], width=20)
            chk.pack(side="left", padx=(10, 5), pady=10)
            
            # 정보 텍스트 프레임
            info_frame = ctk.CTkFrame(frame, fg_color="transparent")
            info_frame.pack(side="left", fill="x", expand=True, padx=5, pady=5)
            
            title_lbl = ctk.CTkLabel(
                info_frame, 
                text=item['title'], 
                anchor="w", 
                font=("Malgun Gothic", 12, "bold"), 
                text_color="#E0E0E6",
                justify="left"
            )
            title_lbl.pack(fill="x", anchor="w")
            
            # 상태에 따른 텍스트 컬러 지정
            status = item['status']
            status_text = "대기 중"
            status_color = "#888888"
            
            if status == 'downloading':
                status_text = "다운로드 중..."
                status_color = "#3A86FF"
            elif status == 'converting':
                status_text = "음원 변환 중..."
                status_color = "#F77F00"
            elif status == 'finished':
                status_text = "완료"
                status_color = "#06D6A0"
            elif status == 'failed':
                status_text = "실패"
                status_color = "#FF007F"
                
            sub_lbl = ctk.CTkLabel(
                info_frame, 
                text=f"채널: {item['uploader']} | 길이: {item['duration']} | 상태: {status_text}", 
                anchor="w", 
                font=("Malgun Gothic", 11), 
                text_color=status_color
            )
            sub_lbl.pack(fill="x", anchor="w")
            
            # 대기열 삭제 버튼
            del_btn = ctk.CTkButton(
                frame, 
                text="제거", 
                width=50, 
                height=26,
                fg_color="#343A40",
                hover_color="#495057",
                font=("Malgun Gothic", 11, "bold"),
                command=lambda index=idx: delete_callback(index)
            )
            del_btn.pack(side="right", padx=(5, 10))
            
            self.queue_widgets.append(frame)


class YoutubeDownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("YouTube Music Downloader - Batch Queue Edition")
        self.geometry("800x700")
        self.minsize(750, 650)
        
        # 윈도우 타이틀바 아이콘 지정
        try:
            if os.path.exists("youtube_icon.ico"):
                self.iconbitmap("youtube_icon.ico")
        except Exception:
            pass

        
        # 상태 변수들
        self.stop_requested = False
        self.save_dir_var = ctk.StringVar(value=os.path.normpath(os.getcwd()))
        self.queue_items = []  # 대기열 목록: [{title, url, duration, uploader, check_var, status}]
        self.search_results = []
        
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
        title_label = ctk.CTkLabel(
            self, 
            text="YouTube Music Downloader", 
            font=("Malgun Gothic", 22, "bold"),
            text_color="#3A86FF"
        )
        title_label.pack(pady=(15, 10))
        
        # 2. 탭 뷰 초기화
        self.tabview = ctk.CTkTabview(self, segmented_button_selected_color="#3A86FF")
        self.tabview.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
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
            height=35,
            font=("Malgun Gothic", 12)
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.search_entry.bind("<Return>", lambda event: self.start_search())
        
        self.search_btn = ctk.CTkButton(
            search_bar, 
            text="유튜브 검색", 
            width=100, 
            height=35,
            fg_color="#3A86FF",
            hover_color="#2563EB",
            font=("Malgun Gothic", 12, "bold"),
            command=self.start_search
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
            fg_color="#06D6A0",
            hover_color="#05B386",
            text_color="#1E1E2E",
            font=("Malgun Gothic", 13, "bold"),
            command=self.add_selected_to_queue
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
        queue_ctrl_frame = ctk.CTkFrame(self.tab_queue, fg_color="#1E1E2E", corner_radius=8)
        queue_ctrl_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(5, 10))
        
        # 직접 링크 추가 영역
        direct_add_row = ctk.CTkFrame(queue_ctrl_frame, fg_color="transparent")
        direct_add_row.pack(fill="x", padx=15, pady=(10, 5))
        
        ctk.CTkLabel(direct_add_row, text="유튜브 링크 직접 추가:", font=("Malgun Gothic", 12, "bold"), text_color="#A0A0B0").pack(side="left", padx=(0, 5))
        
        self.direct_url_entry = ctk.CTkEntry(
            direct_add_row, 
            placeholder_text="https://www.youtube.com/watch?v=...", 
            height=30,
            font=("Malgun Gothic", 11)
        )
        self.direct_url_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.direct_url_entry.bind("<Return>", lambda event: self.add_direct_url())
        
        direct_add_btn = ctk.CTkButton(
            direct_add_row, 
            text="대기열 추가", 
            width=90, 
            height=30,
            fg_color="#3A86FF",
            hover_color="#2563EB",
            font=("Malgun Gothic", 11, "bold"),
            command=self.add_direct_url
        )
        direct_add_btn.pack(side="right", padx=(5, 0))
        
        # 저장 폴더 지정 영역 추가
        save_dir_row = ctk.CTkFrame(queue_ctrl_frame, fg_color="transparent")
        save_dir_row.pack(fill="x", padx=15, pady=(5, 5))
        
        ctk.CTkLabel(save_dir_row, text="저장 폴더 지정:", font=("Malgun Gothic", 12, "bold"), text_color="#A0A0B0").pack(side="left", padx=(0, 5))
        
        self.save_dir_entry = ctk.CTkEntry(
            save_dir_row, 
            textvariable=self.save_dir_var,
            height=30,
            font=("Malgun Gothic", 11)
        )
        self.save_dir_entry.pack(side="left", fill="x", expand=True, padx=5)
        
        save_dir_btn = ctk.CTkButton(
            save_dir_row, 
            text="폴더 변경", 
            width=90, 
            height=30,
            fg_color="#4F5D75",
            hover_color="#3D4A5E",
            font=("Malgun Gothic", 11, "bold"),
            command=self.browse_save_dir
        )
        save_dir_btn.pack(side="right", padx=(5, 0))
        
        # 설정 1: 포맷 선택 및 음질
        settings_row = ctk.CTkFrame(queue_ctrl_frame, fg_color="transparent")
        settings_row.pack(fill="x", padx=15, pady=(5, 5))
        
        ctk.CTkLabel(settings_row, text="다운로드 형식:", font=("Malgun Gothic", 12, "bold"), text_color="#A0A0B0").pack(side="left", padx=(0, 5))
        
        self.format_var = ctk.StringVar(value="MP3")
        self.format_select = ctk.CTkSegmentedButton(
            settings_row, 
            values=["MP3", "FLAC", "MP4"], 
            variable=self.format_var,
            command=self.on_format_changed,
            font=("Malgun Gothic", 11, "bold")
        )
        self.format_select.pack(side="left", padx=5)
        
        self.quality_label = ctk.CTkLabel(settings_row, text="음질:", font=("Malgun Gothic", 12, "bold"), text_color="#A0A0B0")
        self.quality_label.pack(side="left", padx=(15, 5))
        
        self.quality_var = ctk.StringVar(value="320kbps")
        self.quality_select = ctk.CTkOptionMenu(
            settings_row, 
            values=["320kbps", "256kbps", "192kbps"], 
            variable=self.quality_var,
            width=100,
            font=("Malgun Gothic", 11)
        )
        self.quality_select.pack(side="left", padx=5)
        
        self.clear_completed_btn = ctk.CTkButton(
            settings_row, 
            text="완료 항목 제거", 
            width=100, 
            height=28,
            fg_color="#343A40",
            hover_color="#495057",
            font=("Malgun Gothic", 11, "bold"),
            command=self.clear_completed_queue
        )
        self.clear_completed_btn.pack(side="right", padx=(5, 5))

        clear_queue_btn = ctk.CTkButton(
            settings_row, 
            text="대기열 비우기", 
            width=90, 
            height=28,
            fg_color="#343A40",
            hover_color="#495057",
            font=("Malgun Gothic", 11, "bold"),
            command=self.clear_queue
        )
        clear_queue_btn.pack(side="right", padx=(5, 0))
        
        # 설정 2: 실시간 진행 바
        self.progress_row = ctk.CTkFrame(queue_ctrl_frame, fg_color="transparent")
        self.progress_row.pack(fill="x", padx=15, pady=5)
        
        self.queue_status_lbl = ctk.CTkLabel(self.progress_row, text="대기열 상태: 대기 중", font=("Malgun Gothic", 12, "bold"), text_color="#A0A0B0", anchor="w")
        self.queue_status_lbl.pack(fill="x", pady=(2, 2))
        
        # 현재 곡 진행 상황 바
        self.cur_prog_bar = ctk.CTkProgressBar(self.progress_row, height=8, progress_color="#3A86FF")
        self.cur_prog_bar.set(0.0)
        self.cur_prog_bar.pack(fill="x", pady=2)
        
        self.cur_stats_lbl = ctk.CTkLabel(self.progress_row, text="", font=("Malgun Gothic", 11), text_color="#888888", anchor="e")
        self.cur_stats_lbl.pack(fill="x", pady=(0, 2))
        
        # 전체 대기열 진행 상황 바
        self.overall_status_lbl = ctk.CTkLabel(self.progress_row, text="전체 진행 상황:", font=("Malgun Gothic", 11, "bold"), text_color="#A0A0B0", anchor="w")
        self.overall_status_lbl.pack(fill="x", pady=(2, 2))
        
        self.total_prog_bar = ctk.CTkProgressBar(self.progress_row, height=8, progress_color="#06D6A0")
        self.total_prog_bar.set(0.0)
        self.total_prog_bar.pack(fill="x", pady=2)
        
        # 설정 3: 일괄 다운로드 버튼
        btn_row = ctk.CTkFrame(queue_ctrl_frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=15, pady=(5, 10))
        
        self.download_selected_btn = ctk.CTkButton(
            btn_row, 
            text="선택된 항목 다운로드 시작", 
            height=38,
            fg_color="#06D6A0",
            hover_color="#05B386",
            text_color="#1E1E2E",
            font=("Malgun Gothic", 13, "bold"),
            command=self.start_selected_download
        )
        self.download_selected_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))
        
        self.download_all_btn = ctk.CTkButton(
            btn_row, 
            text="대기열 전체 다운로드 시작", 
            height=38,
            fg_color="#3A86FF",
            hover_color="#2563EB",
            font=("Malgun Gothic", 13, "bold"),
            command=self.start_all_download
        )
        self.download_all_btn.pack(side="left", fill="x", expand=True, padx=4)
        
        self.stop_download_btn = ctk.CTkButton(
            btn_row,
            text="다운로드 중단",
            height=38,
            fg_color="#4F5D75",
            hover_color="#3D4A5E",
            state="disabled",
            font=("Malgun Gothic", 13, "bold"),
            command=self.request_stop_download
        )
        self.stop_download_btn.pack(side="right", fill="x", expand=True, padx=(4, 0))
        
        # ----------------------------------------------------
        # 탭 3: 음성 다운로드 목록 구현
        # ----------------------------------------------------
        self.tab_audio.grid_columnconfigure(0, weight=1)
        self.tab_audio.grid_rowconfigure(1, weight=1)
        
        audio_header = ctk.CTkFrame(self.tab_audio, fg_color="transparent")
        audio_header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        
        audio_title = ctk.CTkLabel(audio_header, text="음성 다운로드 완료 목록", font=("Malgun Gothic", 13, "bold"), text_color="#A0A0B0")
        audio_title.pack(side="left", padx=5, pady=5)
        
        open_audio_folder_btn = ctk.CTkButton(
            audio_header, 
            text="폴더 열기", 
            width=80, 
            height=26,
            fg_color="#4F46E5",
            hover_color="#4338CA",
            font=("Malgun Gothic", 11, "bold"),
            command=self.open_download_folder
        )
        open_audio_folder_btn.pack(side="right", padx=5)
        
        delete_all_audio_btn = ctk.CTkButton(
            audio_header, 
            text="목록 전체 삭제", 
            width=100, 
            height=26,
            fg_color="#FF007F",
            hover_color="#CC0066",
            font=("Malgun Gothic", 11, "bold"),
            command=self.delete_all_completed_audio
        )
        delete_all_audio_btn.pack(side="right", padx=5)
        
        self.scroll_audio_frame = ScrollableFileFrame(self.tab_audio, fg_color="transparent")
        self.scroll_audio_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        
        # ----------------------------------------------------
        # 탭 4: 영상 다운로드 목록 구현
        # ----------------------------------------------------
        self.tab_video.grid_columnconfigure(0, weight=1)
        self.tab_video.grid_rowconfigure(1, weight=1)
        
        video_header = ctk.CTkFrame(self.tab_video, fg_color="transparent")
        video_header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        
        video_title = ctk.CTkLabel(video_header, text="영상 다운로드 완료 목록", font=("Malgun Gothic", 13, "bold"), text_color="#A0A0B0")
        video_title.pack(side="left", padx=5, pady=5)
        
        open_video_folder_btn = ctk.CTkButton(
            video_header, 
            text="폴더 열기", 
            width=80, 
            height=26,
            fg_color="#4F46E5",
            hover_color="#4338CA",
            font=("Malgun Gothic", 11, "bold"),
            command=self.open_download_folder
        )
        open_video_folder_btn.pack(side="right", padx=5)
        
        delete_all_video_btn = ctk.CTkButton(
            video_header, 
            text="목록 전체 삭제", 
            width=100, 
            height=26,
            fg_color="#FF007F",
            hover_color="#CC0066",
            font=("Malgun Gothic", 11, "bold"),
            command=self.delete_all_completed_video
        )
        delete_all_video_btn.pack(side="right", padx=5)
        
        self.scroll_video_frame = ScrollableFileFrame(self.tab_video, fg_color="transparent")
        self.scroll_video_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        
    def start_search(self):
        query = self.search_entry.get().strip()
        if not query:
            self.show_error("검색 키워드를 입력해 주세요.")
            return
            
        self.search_btn.configure(state="disabled", text="검색 중...")
        
        # 백그라운드 스레드로 검색 요청
        thread = threading.Thread(target=self.search_thread_target, args=(query,), daemon=True)
        thread.start()
        
    def search_thread_target(self, query):
        try:
            # yt-dlp를 이용해 동영상을 다운로드 받지 않고 검색만 수행
            ydl_opts = {
                'skip_download': True,
                'extract_flat': True,
                'quiet': True,
            }
            # 검색어 10개 추출
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch10:{query}", download=False)
                entries = info.get('entries', [])
                
            results = []
            for entry in entries:
                duration_sec = entry.get('duration', 0)
                mins, secs = divmod(duration_sec, 60)
                hours, mins = divmod(mins, 60)
                duration_str = f"{hours:02d}:{mins:02d}:{secs:02d}" if hours > 0 else f"{mins:02d}:{secs:02d}"
                
                results.append({
                    'title': entry.get('title', 'Unknown Title'),
                    'url': entry.get('url', f"https://www.youtube.com/watch?v={entry.get('id')}"),
                    'duration': duration_str,
                    'uploader': entry.get('uploader', 'Unknown'),
                    'thumbnail': entry.get('thumbnail') or (f"https://img.youtube.com/vi/{entry.get('id')}/hqdefault.jpg" if entry.get('id') else None)
                })
                
            self.after(0, self.on_search_success, results)
        except Exception as e:
            self.after(0, self.on_search_failed, str(e))
            
    def on_search_success(self, results):
        self.search_btn.configure(state="normal", text="유튜브 검색")
        self.search_scroll.populate_results(results)
        
    def on_search_failed(self, err_msg):
        self.search_btn.configure(state="normal", text="유튜브 검색")
        self.show_error(f"유튜브 검색 실패:\n{err_msg}")
        
    def add_selected_to_queue(self):
        added_any = False
        for item in self.search_scroll.search_results_data:
            if item['check_var'].get():
                exists = any(q['url'] == item['url'] for q in self.queue_items)
                if not exists:
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
            
        # 대기열 목록 리빌딩
        self.queue_scroll.populate_queue(self.queue_items, self.delete_queue_item)
        
        # 탭 뷰를 다운로드 대기열 탭으로 포커스 이동
        self.tabview.set("다운로드 대기열")
        
    def add_direct_url(self):
        url = self.direct_url_entry.get().strip()
        if not url:
            self.show_error("추가할 유튜브 링크를 입력해 주세요.")
            return
            
        # 대기열에 이미 존재하는지 검사
        exists = any(q['url'] == url for q in self.queue_items)
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
                
            title = info.get('title', 'Unknown Title')
            duration_sec = info.get('duration', 0)
            uploader = info.get('uploader', 'Unknown')
            
            mins, secs = divmod(duration_sec, 60)
            hours, mins = divmod(mins, 60)
            duration_str = f"{hours:02d}:{mins:02d}:{secs:02d}" if hours > 0 else f"{mins:02d}:{secs:02d}"
            
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
                'status': 'failed'
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
            item['check_var'].set(True)
        self.start_selected_download()
        
    def request_stop_download(self):
        if self.batch_running:
            self.stop_requested = True
            self.queue_status_lbl.configure(text="대기열 상태: 중단 요청 중...", text_color="#FF007F")
            self.stop_download_btn.configure(state="disabled")

    def start_selected_download(self):
        if self.batch_running:
            self.show_error("이미 다운로드 대기열이 실행 중입니다.")
            return
            
        selected_indices = [idx for idx, item in enumerate(self.queue_items) if item['check_var'].get() and item['status'] != 'finished']
        if not selected_indices:
            self.show_error("다운로드할(완료되지 않은) 항목을 1개 이상 체크해 주세요.")
            return
            
        self.stop_requested = False
        self.batch_running = True
        self.download_selected_btn.configure(state="disabled")
        self.download_all_btn.configure(state="disabled")
        self.add_queue_btn.configure(state="disabled")
        self.stop_download_btn.configure(state="normal", fg_color="#FF007F", hover_color="#CC0066")
        
        # 백그라운드 스레드에서 순차 다운로드 시작
        thread = threading.Thread(
            target=self.batch_download_loop, 
            args=(selected_indices,), 
            daemon=True
        )
        thread.start()
        
    def batch_download_loop(self, indices_to_download):
        total_count = len(indices_to_download)
        format_type = self.format_var.get()
        quality_str = self.quality_var.get()
        quality = quality_str.replace("kbps", "")
        
        for num, idx in enumerate(indices_to_download):
            if self.stop_requested:
                break
                
            self.current_download_idx = idx
            item = self.queue_items[idx]
            
            # 상태값 초기화
            item['status'] = 'downloading'
            self.current_download_status = {
                'percent': 0.0,
                'speed': '계산 중...',
                'eta': '--:--',
                'status': 'downloading'
            }
            
            # 전체 작업 대비 진행률 갱신
            self.overall_progress = num / total_count
            self.after(0, self.update_queue_list_ui)
            
            # 단일 다운로드 수행
            success = self.download_single(item['url'], format_type, quality)
            
            if success:
                item['status'] = 'finished'
            else:
                item['status'] = 'failed'
                
            self.overall_progress = (num + 1) / total_count
            self.after(0, self.update_queue_list_ui)
            
        self.batch_running = False
        self.current_download_idx = -1
        self.after(0, self.on_batch_download_complete)
        
    def download_single(self, url, format_type, quality):
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
                if eta:
                    mins, secs = divmod(eta, 60)
                    eta_str = f"{mins:02d}:{secs:02d}"
                else:
                    eta_str = "--:--"
                    
                self.current_download_status.update({
                    'percent': percent,
                    'speed': speed_str,
                    'eta': eta_str,
                    'status': 'downloading'
                })
            elif d['status'] == 'finished':
                self.current_download_status.update({
                    'status': 'converting',
                    'percent': 1.0,
                })
                # 백엔드 스레드에서 대기열 리스트 UI 텍스트 갱신을 위해 status 직접 수정
                if self.current_download_idx != -1:
                    self.queue_items[self.current_download_idx]['status'] = 'converting'
                    self.after(0, self.update_queue_list_ui)
                    
        save_dir = self.save_dir_var.get().strip()
        if not save_dir or not os.path.exists(save_dir):
            save_dir = os.getcwd()

        if format_type == 'MP4':
            ydl_opts = {
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'outtmpl': os.path.join(save_dir, '%(title)s.%(ext)s'),
                'progress_hooks': [progress_hook],
                'noplaylist': True,
                'quiet': True,
            }
        else:
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(save_dir, '%(title)s.%(ext)s'),
                'progress_hooks': [progress_hook],
                'noplaylist': True,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': format_type.lower(),
                    'preferredquality': quality if format_type == 'MP3' else '0',
                }],
                'quiet': True,
            }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            return True
        except Exception as e:
            print(f"Download error for {url}: {e}")
            return False
            
    def update_queue_list_ui(self):
        # 대기열 리스트 프레임 리빌드
        self.queue_scroll.populate_queue(self.queue_items, self.delete_queue_item)
        
    def on_batch_download_complete(self):
        self.download_selected_btn.configure(state="normal")
        self.download_all_btn.configure(state="normal")
        self.add_queue_btn.configure(state="normal")
        self.stop_download_btn.configure(state="disabled", fg_color="#4F5D75")
        
        if self.stop_requested:
            self.queue_status_lbl.configure(text="다운로드 중단됨!", text_color="#FF007F")
            self.cur_prog_bar.set(0.0)
            self.cur_stats_lbl.configure(text="사용자가 다운로드를 중단했습니다.")
            self.stop_requested = False
        else:
            self.queue_status_lbl.configure(text="대기열 완료!", text_color="#06D6A0")
            self.cur_prog_bar.set(1.0)
            self.cur_stats_lbl.configure(text="")
            self.total_prog_bar.set(1.0)
            self.overall_status_lbl.configure(text="전체 진행 상황: 일괄 다운로드 완료!")
        
        self.refresh_file_list()
        
    def update_progress_loop(self):
        # 일괄 다운로드 진행 중 실시간 진행 정보 업데이트
        if self.batch_running and self.current_download_idx != -1:
            item = self.queue_items[self.current_download_idx]
            status = self.current_download_status['status']
            
            if status == 'downloading':
                self.queue_status_lbl.configure(
                    text=f"현재 다운로드 중: {item['title'][:40]}...", 
                    text_color="#3A86FF"
                )
                self.cur_prog_bar.set(self.current_download_status['percent'])
                self.cur_stats_lbl.configure(
                    text=f"{self.current_download_status['percent']*100:.1f}% | 속도: {self.current_download_status['speed']} | 남은 시간: {self.current_download_status['eta']}"
                )
                
            elif status == 'converting':
                self.queue_status_lbl.configure(
                    text=f"오디오 음질 변환 중: {item['title'][:40]}...", 
                    text_color="#F77F00"
                )
                self.cur_prog_bar.set(1.0)
                self.cur_stats_lbl.configure(text="변환 작업 진행 중 (FFmpeg)...")
                
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
        save_dir = self.save_dir_var.get().strip()
        if not save_dir or not os.path.exists(save_dir):
            save_dir = os.getcwd()
            
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
            print(f"File list reload failed: {e}")
            
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
        save_dir = self.save_dir_var.get().strip()
        if not save_dir or not os.path.exists(save_dir):
            save_dir = os.getcwd()
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
            
        dialog = ctk.CTkInputDialog(
            text=f"정말로 지정된 폴더의 모든 완료 음성 파일({len(audio_files)}개)을 영구 삭제하시겠습니까?\n삭제하려면 'yes'를 입력해 주세요.", 
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
        save_dir = self.save_dir_var.get().strip()
        if not save_dir or not os.path.exists(save_dir):
            save_dir = os.getcwd()
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
            
        dialog = ctk.CTkInputDialog(
            text=f"정말로 지정된 폴더의 모든 완료 영상 파일({len(video_files)}개)을 영구 삭제하시겠습니까?\n삭제하려면 'yes'를 입력해 주세요.", 
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
        save_dir = self.save_dir_var.get().strip()
        if not save_dir or not os.path.exists(save_dir):
            save_dir = os.getcwd()
        try:
            os.startfile(save_dir)
        except Exception as e:
            self.show_error(f"폴더 열기 실패:\n{e}")
            
    def show_error(self, message):
        err_win = ctk.CTkToplevel(self)
        err_win.title("알림")
        err_win.geometry("380x180")
        err_win.resizable(False, False)
        
        # 모달 제어
        err_win.grab_set()
        
        label = ctk.CTkLabel(err_win, text=message, font=("Malgun Gothic", 12), justify="left", wraplength=340)
        label.pack(expand=True, fill="both", padx=20, pady=20)
        
        ok_btn = ctk.CTkButton(
            err_win, 
            text="확인", 
            width=100, 
            fg_color="#3A86FF",
            command=err_win.destroy
        )
        ok_btn.pack(pady=(0, 20))

if __name__ == "__main__":
    app = YoutubeDownloaderApp()
    app.mainloop()
