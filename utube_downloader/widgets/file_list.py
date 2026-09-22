"""다운로드가 끝난 파일 목록을 보여주는 스크롤 프레임.

형식 · 파일 이름 · 크기 · 받은 날을 열로 나누고,
이번에 앱을 켠 뒤 받은 파일에는 '새로 받음' 을 붙인다.
"""
import customtkinter as ctk

from ..formatting import format_file_date, format_size
from ..theme import (
    C_ASH, C_GRAPHITE, C_PEARL, C_STEEL, C_SURFACE_DEEP, C_TEXT, C_TEXT_DIM,
    EXT_COLORS, FONT_BODY, FONT_CAPTION, FONT_ITEM, FONT_LABEL, FONT_LABEL_BOLD,
    RADIUS_BUTTON, RADIUS_CARD,
)

# 열 폭. 머리글 행(ui.py)과 같은 값을 써야 열이 맞는다
FILE_COLUMNS = (("형식", 58), ("파일 이름", 0), ("크기", 72), ("받은 날", 92), ("", 128))


def configure_columns(frame):
    for col, (_title, width) in enumerate(FILE_COLUMNS):
        if width:
            frame.grid_columnconfigure(col, minsize=width, weight=0)
        else:
            frame.grid_columnconfigure(col, weight=1)


class ScrollableFileFrame(ctk.CTkScrollableFrame):
    """다운로드 완료 목록을 보여주는 스크롤 프레임"""
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.file_items = []

    def populate_files(self, entries, play_callback, delete_callback,
                       empty_text="다운로드된 파일이 없습니다.", new_since=None):
        """entries 는 {'name', 'ext', 'size', 'mtime'} 사전의 목록이다."""
        for item in self.file_items:
            item.destroy()
        self.file_items.clear()

        if not entries:
            label = ctk.CTkLabel(self, text=empty_text, font=FONT_ITEM, text_color=C_TEXT_DIM)
            label.pack(pady=40)
            self.file_items.append(label)
            return

        for entry in entries:
            frame = ctk.CTkFrame(self, fg_color=C_SURFACE_DEEP, corner_radius=RADIUS_CARD, height=46)
            frame.pack(fill="x", pady=2, padx=(0, 6))
            configure_columns(frame)

            ext = entry['ext']
            ctk.CTkLabel(
                frame, text=f" {ext} ", font=FONT_LABEL_BOLD,
                text_color=EXT_COLORS.get(ext, C_TEXT_DIM),
                fg_color=C_SURFACE_DEEP, corner_radius=0,
            ).grid(row=0, column=0, sticky="w", padx=(12, 0), pady=10)

            name_box = ctk.CTkFrame(frame, fg_color="transparent")
            name_box.grid(row=0, column=1, sticky="ew", padx=(4, 8))
            # Tk 라벨은 말줄임을 하지 않아 긴 이름이 옆 열을 밀어낸다
            shown = entry['name'] if len(entry['name']) <= 56 else entry['name'][:55] + "…"
            ctk.CTkLabel(name_box, text=shown, anchor="w", font=FONT_BODY,
                         text_color=C_TEXT).pack(side="left")
            if new_since is not None and entry['mtime'] >= new_since:
                ctk.CTkLabel(name_box, text=" 새로 받음 ", font=FONT_CAPTION,
                             text_color=C_SURFACE_DEEP, fg_color=C_ASH,
                             corner_radius=0).pack(side="left", padx=(8, 0))

            ctk.CTkLabel(frame, text=format_size(entry['size']), font=FONT_LABEL,
                         text_color=C_ASH, anchor="w").grid(row=0, column=2, sticky="w")
            ctk.CTkLabel(frame, text=format_file_date(entry['mtime']), font=FONT_LABEL,
                         text_color=C_ASH, anchor="w").grid(row=0, column=3, sticky="w")

            actions = ctk.CTkFrame(frame, fg_color="transparent")
            actions.grid(row=0, column=4, sticky="e", padx=(0, 12))
            common = dict(height=26, fg_color="transparent", border_width=1, border_color=C_STEEL,
                          hover_color=C_GRAPHITE, text_color=C_PEARL, font=FONT_LABEL_BOLD,
                          corner_radius=RADIUS_BUTTON)
            name = entry['name']
            ctk.CTkButton(actions, text="▶ 재생", width=64,
                          command=lambda fname=name: play_callback(fname), **common).pack(side="left")
            ctk.CTkButton(actions, text="삭제", width=48,
                          command=lambda fname=name: delete_callback(fname), **common).pack(
                side="left", padx=(6, 0))

            self.file_items.append(frame)
