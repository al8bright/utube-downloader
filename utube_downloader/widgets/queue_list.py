"""다운로드 대기열 목록.

다운로드 중에는 체크박스와 제거 버튼을 잠가, 눌러도 무시되는 상황을 없앤다.
"""
import customtkinter as ctk

from ..theme import (
    C_ASH, C_DANGER, C_GRAPHITE, C_PEARL, C_STEEL, C_SUCCESS, C_SURFACE_DEEP,
    C_TEXT, C_TEXT_DIM, C_TEXT_MUTED, C_WARNING,
    FONT_BODY_BOLD, FONT_ITEM, FONT_LABEL, FONT_LABEL_BOLD, RADIUS_CARD,
)


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
