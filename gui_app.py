import os
import sys
import re
import shutil
import threading
import urllib.request
import webbrowser
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import yt_dlp


def format_duration(seconds):
    """초를 mm:ss 또는 hh:mm:ss 문자열로 변환한다.

    라이브 방송은 duration 이 None 이고 일부 항목은 float 으로 오므로,
    변환할 수 없는 값은 예외 대신 기본 표시를 돌려준다.
    """
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return UNKNOWN_TIME
    if total < 0:
        return UNKNOWN_TIME
    mins, secs = divmod(total, 60)
    hours, mins = divmod(mins, 60)
    return f"{hours:02d}:{mins:02d}:{secs:02d}" if hours > 0 else f"{mins:02d}:{secs:02d}"


def format_eta(seconds):
    """남은 시간(초)을 mm:ss 문자열로 변환한다.

    yt-dlp 는 eta 를 float 으로 주기도 한다. 표시용 값 하나 때문에
    다운로드 전체가 실패로 처리되지 않도록 방어한다.
    """
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return UNKNOWN_TIME
    if total < 0:
        return UNKNOWN_TIME
    mins, secs = divmod(total, 60)
    return f"{mins:02d}:{secs:02d}"


def resolve_save_dir(raw_dir):
    """저장 폴더 경로를 검증한다. (사용할 경로, 유효여부) 를 돌려준다.

    폴더가 아닌 경로(파일, 끊긴 네트워크 드라이브)를 그대로 통과시키면
    다운로드와 일괄 삭제가 엉뚱한 폴더에서 일어나므로 isdir 로 확인한다.
    """
    save_dir = (raw_dir or '').strip()
    if not save_dir or not os.path.isdir(save_dir):
        return os.getcwd(), False
    return save_dir, True


_VIDEO_ID_PATTERNS = (
    re.compile(r'(?:youtube\.com|youtube-nocookie\.com)/watch\?(?:.*&)?v=([\w-]{11})'),
    re.compile(r'youtu\.be/([\w-]{11})'),
    re.compile(r'(?:youtube\.com|youtube-nocookie\.com)/shorts/([\w-]{11})'),
    re.compile(r'(?:youtube\.com|youtube-nocookie\.com)/embed/([\w-]{11})'),
    re.compile(r'(?:youtube\.com|youtube-nocookie\.com)/live/([\w-]{11})'),
)


def extract_video_id(url):
    """유튜브 URL 에서 영상 ID 를 뽑는다. 유튜브가 아니면 None."""
    if not url:
        return None
    for pattern in _VIDEO_ID_PATTERNS:
        found = pattern.search(url)
        if found:
            return found.group(1)
    return None


def is_same_video(url_a, url_b):
    """링크 형태(단축/타임스탬프/재생목록 파라미터)가 달라도 같은 영상인지 판정한다."""
    id_a = extract_video_id(url_a)
    id_b = extract_video_id(url_b)
    if id_a and id_b:
        return id_a == id_b
    return (url_a or '').strip() == (url_b or '').strip()


def escape_ydl_path(path):
    """yt-dlp 가 경로의 %VAR% 를 환경변수로 확장하지 못하도록 % 를 이스케이프한다."""
    return (path or '').replace('%', '%%')


def describe_batch_result(done, failed, stopped):
    """배치 결과 문구와 '전부 성공인가' 여부를 돌려준다.

    전량 실패인데 초록색 '완료' 로 보고하던 문제를 막기 위해,
    성공 여부를 문구와 함께 명시적으로 돌려준다.
    """
    parts = []
    if done:
        parts.append(f"완료 {done}곡")
    if failed:
        parts.append(f"실패 {failed}곡")
    if stopped:
        parts.append(f"중단 {stopped}곡")

    if not parts:
        return "처리한 항목이 없습니다.", False
    all_ok = bool(done) and not failed and not stopped
    return " · ".join(parts), all_ok


def describe_postprocess_stage(format_type):
    """후처리 단계 문구. MP4 는 오디오 변환이 아니라 영상 병합이다."""
    if format_type == 'MP4':
        return "영상 병합 중 (FFmpeg)..."
    return "음원 변환 중 (FFmpeg)..."


def cleanup_temp_dir(save_dir):
    """앱이 만든 임시 폴더만 지운다. 사용자 파일에는 손대지 않는다."""
    if not save_dir:
        return
    temp_dir = os.path.join(save_dir, TEMP_DIR_NAME)
    if not os.path.isdir(temp_dir):
        return
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass


def bind_children_to_process_lifetime():
    """자식 프로세스(ffmpeg)가 이 프로세스보다 오래 살지 못하게 묶는다.

    Windows 는 부모가 죽어도 자식을 종료하지 않고, yt-dlp 의 Popen 은
    Job Object 도 creationflags 도 지정하지 않는다. 그래서 변환 중 창을 닫으면
    ffmpeg.exe 가 고아로 남아 계속 돈다. JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE 로
    현재 프로세스를 Job 에 넣어두면 어떤 경로로 종료되든 자식이 함께 정리된다.
    """
    if sys.platform != 'win32':
        return None
    try:
        import ctypes
        from ctypes import wintypes

        JobObjectExtendedLimitInformation = 9
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in (
                'ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
                'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ('PerProcessUserTimeLimit', ctypes.c_int64),
                ('PerJobUserTimeLimit', ctypes.c_int64),
                ('LimitFlags', wintypes.DWORD),
                ('MinimumWorkingSetSize', ctypes.c_size_t),
                ('MaximumWorkingSetSize', ctypes.c_size_t),
                ('ActiveProcessLimit', wintypes.DWORD),
                ('Affinity', ctypes.POINTER(ctypes.c_ulong)),
                ('PriorityClass', wintypes.DWORD),
                ('SchedulingClass', wintypes.DWORD),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ('BasicLimitInformation', JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ('IoInfo', IO_COUNTERS),
                ('ProcessMemoryLimit', ctypes.c_size_t),
                ('JobMemoryLimit', ctypes.c_size_t),
                ('PeakProcessMemoryUsed', ctypes.c_size_t),
                ('PeakJobMemoryUsed', ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        # 64비트에서 HANDLE 이 c_int 로 잘리지 않도록 시그니처를 명시한다
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
                job, JobObjectExtendedLimitInformation,
                ctypes.byref(info), ctypes.sizeof(info)):
            kernel32.CloseHandle(job)
            return None

        if not kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess()):
            kernel32.CloseHandle(job)
            return None

        # 핸들을 살려둬야 Job 이 유지된다. 프로세스 종료 시 닫히며 자식이 정리된다.
        return job
    except Exception:
        return None


def describe_download_error(exc):
    """yt-dlp 예외를 사용자가 조치할 수 있는 한국어 문구로 바꾼다."""
    raw = str(exc)
    low = raw.lower()
    if 'ffmpeg' in low or 'ffprobe' in low:
        return "FFmpeg 를 찾을 수 없습니다. winget install Gyan.FFmpeg 로 설치한 뒤 다시 시도해 주세요."
    if 'private video' in low:
        return "비공개 영상이라 다운로드할 수 없습니다."
    if 'age' in low and 'restrict' in low:
        return "연령 제한 영상이라 다운로드할 수 없습니다."
    if 'unavailable' in low or 'removed' in low:
        return "삭제되었거나 이용할 수 없는 영상입니다."
    if 'not available in your country' in low or 'geo' in low and 'block' in low:
        return "지역 제한으로 차단된 영상입니다."
    if 'no space' in low or 'disk' in low and 'full' in low:
        return "저장 공간이 부족합니다."
    if 'urlopen' in low or 'timed out' in low or 'connection' in low:
        return "네트워크 연결에 실패했습니다. 인터넷 상태를 확인해 주세요."
    return raw.strip() or "알 수 없는 오류가 발생했습니다."


def is_playlist_info(info):
    """추출 결과가 재생목록/채널인지 판정한다.

    noplaylist 는 watch?v=...&list=... 에서 list 를 떼어낼 뿐,
    순수 재생목록 URL 에는 효력이 없어 항목 1개가 수백 개를 받게 된다.
    """
    if not info:
        return False
    return info.get('_type') in ('playlist', 'multi_video')


def build_ydl_opts(save_dir, format_type, quality, hook):
    """포맷에 맞는 yt-dlp 옵션을 만든다."""
    opts = {
        # 영상 ID 를 붙여야 제목이 같은 다른 영상이 기존 파일을 덮어쓰지 않는다
        'outtmpl': '%(title)s [%(id)s].%(ext)s',
        # 중간 파일(.part/.webm)을 전용 폴더에 두어 저장 폴더가 더럽혀지지 않게 한다
        'paths': {
            # % 를 이스케이프하지 않으면 폴더 이름의 %VAR% 가 환경변수로 치환된다
            'home': escape_ydl_path(save_dir),
            'temp': escape_ydl_path(os.path.join(save_dir, TEMP_DIR_NAME)),
        },
        'noplaylist': True,
        'quiet': True,
    }
    if hook is not None:
        opts['progress_hooks'] = [hook]

    if format_type == 'MP4':
        opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        opts['merge_output_format'] = 'mp4'
    else:
        opts['format'] = 'bestaudio/best'
        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': format_type.lower(),
            'preferredquality': quality if format_type == 'MP3' else '0',
        }]
    return opts


def resource_path(relative_path):
    """PyInstaller 번들과 일반 실행 양쪽에서 리소스 절대 경로를 반환한다."""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

UNKNOWN_TIME = "--:--"
TEMP_DIR_NAME = ".utube_tmp"  # 변환 전 중간 파일을 격리하는 폴더
BR = chr(10)  # 대화상자 줄바꿈

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
            
            # 바로 재생 버튼 (우측 고정 점유를 위해 info_frame보다 먼저 pack)
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
            
            # 제목 및 정보 텍스트 결합 프레임 (남은 공간을 유동적으로 사용)
            info_frame = ctk.CTkFrame(frame, fg_color="transparent")
            info_frame.pack(side="left", fill="x", expand=True, padx=10, pady=5)
            
            title_lbl = ctk.CTkLabel(
                info_frame, 
                text=item['title'], 
                anchor="w", 
                font=("Malgun Gothic", 12, "bold"), 
                text_color="#E0E0E6",
                justify="left",
                wraplength=420  # 제목이 너무 길 경우 겹치지 않고 줄바꿈되도록 wraplength 지정
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
            
            # 비동기 썸네일 다운로드 시작 (ThreadPoolExecutor로 부하 분산)
            thumb_url = item.get('thumbnail')
            self.thumb_executor.submit(
                self.load_thumbnail_async, 
                thumb_url, 
                thumbnail_lbl
            )
            
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
            self.row_controls.append(chk)
            
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
            
            if status == 'analyzing':
                status_text = "분석 중..."
                status_color = "#F77F00"
            elif status == 'downloading':
                status_text = "다운로드 중..."
                status_color = "#3A86FF"
            elif status == 'converting':
                status_text = "음원 변환 중..."
                status_color = "#F77F00"
            elif status == 'finished':
                status_text = "완료"
                status_color = "#06D6A0"
            elif status == 'stopped':
                status_text = "사용자 중단"
                status_color = "#A0A0B0"
            elif status == 'failed':
                # 실패 사유를 함께 보여줘야 사용자가 조치할 수 있다
                reason = item.get('error')
                status_text = f"실패 - {reason}" if reason else "실패"
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
        self.pending_added_during_batch = 0
        self.searching = False
        self.search_generation = 0
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
        
        self.direct_add_btn = ctk.CTkButton(
            direct_add_row, 
            text="대기열 추가", 
            width=90, 
            height=30,
            fg_color="#3A86FF",
            hover_color="#2563EB",
            font=("Malgun Gothic", 11, "bold"),
            command=self.add_direct_url
        )
        self.direct_add_btn.pack(side="right", padx=(5, 0))
        
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
        
        self.save_dir_btn = ctk.CTkButton(
            save_dir_row, 
            text="폴더 변경", 
            width=90, 
            height=30,
            fg_color="#4F5D75",
            hover_color="#3D4A5E",
            font=("Malgun Gothic", 11, "bold"),
            command=self.browse_save_dir
        )
        self.save_dir_btn.pack(side="right", padx=(5, 0))
        
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

        self.clear_queue_btn = ctk.CTkButton(
            settings_row, 
            text="대기열 비우기", 
            width=90, 
            height=28,
            fg_color="#343A40",
            hover_color="#495057",
            font=("Malgun Gothic", 11, "bold"),
            command=self.clear_queue
        )
        self.clear_queue_btn.pack(side="right", padx=(5, 0))
        
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
        
        self.delete_all_audio_btn = ctk.CTkButton(
            audio_header, 
            text="목록 전체 삭제", 
            width=100, 
            height=26,
            fg_color="#FF007F",
            hover_color="#CC0066",
            font=("Malgun Gothic", 11, "bold"),
            command=self.delete_all_completed_audio
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
        
        self.delete_all_video_btn = ctk.CTkButton(
            video_header, 
            text="목록 전체 삭제", 
            width=100, 
            height=26,
            fg_color="#FF007F",
            hover_color="#CC0066",
            font=("Malgun Gothic", 11, "bold"),
            command=self.delete_all_completed_video
        )
        self.delete_all_video_btn.pack(side="right", padx=5)
        
        self.scroll_video_frame = ScrollableFileFrame(self.tab_video, fg_color="transparent")
        self.scroll_video_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        
    def start_search(self):
        # Enter 키(바인딩)는 버튼 비활성화를 우회하므로 플래그로 재진입을 막는다.
        # 막지 않으면 연타 한 번마다 검색 스레드와 썸네일 작업 100건이 쌓인다.
        if self.searching:
            return

        query = self.search_entry.get().strip()
        if not query:
            self.show_error("검색 키워드를 입력해 주세요.")
            return

        self.searching = True
        self.search_generation += 1
        generation = self.search_generation
        self.search_btn.configure(state="disabled", text="검색 중...")

        # 백그라운드 스레드로 검색 요청
        thread = threading.Thread(
            target=self.search_thread_target, args=(query, generation), daemon=True)
        thread.start()

    def is_current_search(self, generation):
        """늦게 끝난 옛 검색이 새 검색 결과를 덮어쓰지 못하게 한다."""
        return generation == self.search_generation

    def finish_search(self):
        self.searching = False
        self.search_btn.configure(state="normal", text="유튜브 검색")

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
        if generation is not None and not self.is_current_search(generation):
            return  # 이미 새 검색이 시작됐다. 옛 결과는 버린다.
        self.finish_search()
        self.search_scroll.populate_results(results)
        
    def on_search_failed(self, err_msg, generation=None):
        if generation is not None and not self.is_current_search(generation):
            return
        self.finish_search()
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
                    'error': (
                        f"재생목록/채널 링크입니다(영상 {count}개). "
                        "개별 영상 링크를 넣거나 검색 탭에서 곡을 선택해 주세요."
                    ),
                })
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
            
        # 저장 폴더가 유효하지 않으면 조용히 cwd 로 새는 대신 먼저 알린다
        resolved, dir_ok = resolve_save_dir(self.save_dir_var.get())
        if not dir_ok:
            self.show_error(
                "저장 폴더를 찾을 수 없습니다."
                + BR + BR
                + f"입력된 경로: {self.save_dir_var.get().strip() or '(비어 있음)'}"
                + BR
                + f"대신 사용할 폴더: {resolved}"
                + BR + BR
                + "폴더를 다시 지정해 주세요."
            )
            self.save_dir_var.set(os.path.normpath(resolved))

        self.stop_requested = False
        self.batch_running = True
        self.set_controls_locked(True)
        
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
        
        # 성공/실패/중단 개수를 집계해 완료 보고에 넘긴다
        tally = {'done': 0, 'failed': 0, 'stopped': 0}
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
                success = self.download_single(item['url'], format_type, quality)

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
            cleanup_temp_dir(resolve_save_dir(self.save_dir_var.get())[0])
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
                eta_str = format_eta(eta) if eta else "--:--"
                    
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
                    
        save_dir, _dir_ok = resolve_save_dir(self.save_dir_var.get())

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
        tally = getattr(self, 'last_batch_tally', None) or {'done': 0, 'failed': 0, 'stopped': 0}
        message, all_ok = describe_batch_result(
            tally.get('done', 0), tally.get('failed', 0), tally.get('stopped', 0))

        color = "#06D6A0" if all_ok else ("#FF007F" if tally.get('failed') else "#A0A0B0")
        self.queue_status_lbl.configure(text=f"대기열 결과: {message}", text_color=color)
        self.cur_prog_bar.set(1.0 if all_ok else 0.0)
        self.cur_stats_lbl.configure(
            text="" if all_ok else "실패한 항목의 사유는 대기열 목록에서 확인할 수 있습니다.")
        self.total_prog_bar.set(1.0)
        self.overall_status_lbl.configure(text=f"전체 진행 상황: {message}")
        self.stop_requested = False

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
        for widget_name in (
            'download_selected_btn', 'download_all_btn', 'add_queue_btn',
            'format_select', 'quality_select', 'save_dir_entry',
            'save_dir_btn', 'direct_add_btn', 'clear_queue_btn',
            'clear_completed_btn', 'delete_all_audio_btn', 'delete_all_video_btn',
        ):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                try:
                    widget.configure(state=state)
                except Exception:
                    pass

        if locked:
            self.stop_download_btn.configure(
                state="normal", fg_color="#FF007F", hover_color="#CC0066")
        else:
            self.stop_download_btn.configure(state="disabled", fg_color="#4F5D75")

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

        # 썸네일 워커는 non-daemon 이라 정리하지 않으면 창이 닫힌 뒤에도 프로세스가 남는다
        try:
            self.search_scroll.thumb_executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

        self.destroy()

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
