"""다운로드 대기열 목록.

곡마다 제목·채널 / 길이 / 상태를 열로 나누고, 실패 사유는 상태 밑에 적는다.
다운로드 중에는 체크박스와 제거 버튼을 잠가, 눌러도 무시되는 상황을 없앤다.
"""
import customtkinter as ctk

from ..formatting import describe_queue_status, display_text, filter_queue_indices
from ..theme import (
    C_ASH, C_DANGER, C_GRAPHITE, C_PEARL, C_STEEL, C_SUCCESS, C_SURFACE_DEEP,
    C_TEXT, C_TEXT_DIM, C_TEXT_MUTED, C_WARNING,
    FONT_BODY_BOLD, FONT_CAPTION, FONT_ITEM, FONT_LABEL, RADIUS_BUTTON, RADIUS_CARD,
)

# 열 폭. 머리글 행(ui.py)과 같은 값을 써야 열이 맞는다
QUEUE_COLUMNS = (("", 24), ("#", 28), ("제목", 0), ("길이", 56), ("상태", 196), ("", 34))


def queue_status_color(item):
    status = item.get('status')
    if item.get('blocked'):
        return C_STEEL
    return {
        'downloading': C_PEARL,
        'finished': C_SUCCESS,
        'stopped': C_TEXT_MUTED,
        'failed': C_DANGER,
        'analyzing': C_WARNING,
        'converting': C_WARNING,
    }.get(status, C_TEXT_DIM)


def is_selectable(item):
    """받기 대상으로 고를 수 있는 항목. 완료·차단·진행 중인 곡은 고를 수 없다."""
    if item.get('blocked'):
        return False
    return item.get('status') in ('waiting', 'stopped', 'failed')


def configure_columns(frame):
    for col, (_title, width) in enumerate(QUEUE_COLUMNS):
        if width:
            frame.grid_columnconfigure(col, minsize=width, weight=0)
        else:
            frame.grid_columnconfigure(col, weight=1)


class ScrollableQueueFrame(ctk.CTkScrollableFrame):
    """다운로드 대기열 목록을 보여주는 스크롤 프레임"""
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.queue_widgets = []
        self.row_controls = []   # 다운로드 중 잠글 체크박스·제거 버튼
        self.status_labels = {}  # 원래 인덱스 -> 상태 라벨. 진행률 글자만 바꿀 때 쓴다
        self.locked = False
        self.bucket = "전체"     # 필터 칩
        self.on_check = None     # 체크가 바뀌면 선택 개수를 다시 센다

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

    def set_row_status_text(self, index, text):
        """다시 그리지 않고 한 줄의 상태 글자만 바꾼다 (진행률 %)."""
        label = self.status_labels.get(index)
        try:
            if label is not None and label.winfo_exists():
                label.configure(text=text)
        except Exception:
            pass

    def _notify_check(self):
        if self.on_check:
            self.on_check()

    def populate_queue(self, queue_items, delete_callback):
        for widget in self.queue_widgets:
            widget.destroy()
        self.queue_widgets.clear()
        self.row_controls.clear()
        self.status_labels.clear()

        if not queue_items:
            self._empty("대기열이 비어 있습니다. 검색 화면에서 곡을 담거나 링크를 추가해 주세요.")
            return

        indices = filter_queue_indices(queue_items, self.bucket)
        if not indices:
            self._empty(f"'{self.bucket}' 에 해당하는 곡이 없습니다.")
            return

        for idx in indices:
            self._render_row(idx, queue_items[idx], delete_callback)

        # 목록을 다시 그려도 다운로드 중이면 잠금 상태를 유지한다
        if self.locked:
            self.set_locked(True)

    def _empty(self, text):
        label = ctk.CTkLabel(self, text=text, font=FONT_ITEM, text_color=C_TEXT_DIM)
        label.pack(pady=40)
        self.queue_widgets.append(label)

    def _render_row(self, idx, item, delete_callback):
        status = item.get('status')
        current = status in ('downloading', 'converting')
        frame = ctk.CTkFrame(
            self, fg_color=C_SURFACE_DEEP, corner_radius=RADIUS_CARD,
            border_width=1 if current else 0, border_color=C_GRAPHITE)
        frame.pack(fill="x", pady=2, padx=(0, 6))
        configure_columns(frame)

        selectable = is_selectable(item)
        chk = ctk.CTkCheckBox(
            frame, text="", variable=item['check_var'], width=20,
            corner_radius=RADIUS_CARD, checkbox_width=16, checkbox_height=16,
            fg_color=C_PEARL, hover_color=C_ASH, checkmark_color=C_SURFACE_DEEP,
            border_color=C_STEEL if selectable else C_GRAPHITE, border_width=1,
            command=self._notify_check)
        chk.grid(row=0, column=0, padx=(12, 0), pady=10)
        if selectable:
            self.row_controls.append(chk)
        else:
            chk.configure(state="disabled")

        ctk.CTkLabel(frame, text=str(idx + 1), font=FONT_LABEL, text_color=C_STEEL,
                     anchor="w").grid(row=0, column=1, sticky="w", padx=(6, 0))

        info = ctk.CTkFrame(frame, fg_color="transparent")
        info.grid(row=0, column=2, sticky="ew", padx=(6, 8), pady=7)
        done = status == 'finished'
        ctk.CTkLabel(
            info, text=display_text(item['title']), anchor="w", justify="left",
            font=FONT_LABEL if done else FONT_BODY_BOLD,
            text_color=C_TEXT_MUTED if done or item.get('blocked') else C_TEXT,
        ).pack(fill="x", anchor="w")
        ctk.CTkLabel(info, text=display_text(item.get('uploader', '')), anchor="w", font=FONT_LABEL,
                     text_color=C_ASH).pack(fill="x", anchor="w")

        ctk.CTkLabel(frame, text=item.get('duration', ''), font=FONT_LABEL, text_color=C_ASH,
                     anchor="w").grid(row=0, column=3, sticky="w")

        label, reason = describe_queue_status(item)
        status_box = ctk.CTkFrame(frame, fg_color="transparent")
        status_box.grid(row=0, column=4, sticky="ew", padx=(0, 6))
        status_lbl = ctk.CTkLabel(status_box, text="● " + label, font=FONT_LABEL,
                                  text_color=queue_status_color(item), anchor="w")
        status_lbl.pack(fill="x")
        self.status_labels[idx] = status_lbl
        if reason:
            ctk.CTkLabel(status_box, text=reason, font=FONT_CAPTION, text_color=C_STEEL,
                         anchor="w", justify="left", wraplength=190).pack(fill="x")

        del_btn = ctk.CTkButton(
            frame, text="✕", width=26, height=26,
            fg_color="transparent", border_width=1, border_color=C_GRAPHITE,
            hover_color=C_GRAPHITE, text_color=C_ASH, font=FONT_LABEL,
            corner_radius=RADIUS_BUTTON,
            command=lambda index=idx: delete_callback(index))
        del_btn.grid(row=0, column=5, padx=(0, 10))
        self.row_controls.append(del_btn)

        self.queue_widgets.append(frame)
