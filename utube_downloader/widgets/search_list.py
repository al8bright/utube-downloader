"""유튜브 검색 결과 목록.

결과 100건을 한 번에 그리면 화면이 멈추므로 조각내어 그린다.
"""
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import customtkinter as ctk
from PIL import Image

from ..formatting import SEARCH_INITIAL_TEXT
from ..theme import (
    C_ASH, C_GRAPHITE, C_PEARL, C_STEEL, C_SURFACE_DEEP,
    C_TEXT, C_TEXT_DIM, C_TEXT_FAINT,
    FONT_BODY_BOLD, FONT_CAPTION, FONT_ITEM, FONT_LABEL, FONT_LABEL_BOLD, RADIUS_CARD,
)


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
