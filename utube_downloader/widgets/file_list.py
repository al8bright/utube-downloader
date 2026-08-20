"""다운로드가 끝난 파일 목록을 보여주는 스크롤 프레임."""
import os

import customtkinter as ctk

from ..theme import (
    C_ACCENT, C_GRAPHITE, C_PEARL, C_STEEL, C_SUCCESS, C_SURFACE_DEEP,
    C_TEXT, C_TEXT_DIM, C_WARNING,
    FONT_BODY, FONT_ITEM, FONT_LABEL_BOLD, RADIUS_CARD,
)


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
