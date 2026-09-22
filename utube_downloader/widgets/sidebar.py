"""왼쪽 메뉴와 진행 요약.

어느 화면에 있든 지금 받는 곡과 전체 진행률이 보이도록 메뉴 아래에 붙박이로 둔다.
대기열 화면에서는 같은 정보가 크게 보이므로 요약을 숨긴다.
"""
import customtkinter as ctk

from ..theme import (
    C_ASH, C_BG, C_GIALLO, C_GRAPHITE, C_PEARL, C_STEEL, C_SURFACE,
    FONT_CAPTION, FONT_LABEL, FONT_LABEL_BOLD, FONT_NAV, FONT_WORDMARK,
    LOGO_SIZE, PAD_M, PAD_S, RADIUS_BUTTON, RADIUS_CARD, SIDEBAR_WIDTH, tracked,
)

# (화면 이름, 아이콘, 표시 이름). None 은 '받은 파일' 구분선 자리다.
NAV_ITEMS = (
    ("search", "⌕", "검색"),
    ("queue", "≡", "대기열"),
    None,
    ("audio", "♪", "음성"),
    ("video", "▶", "영상"),
)


class NavItem(ctk.CTkFrame):
    """메뉴 한 줄. 왼쪽 3px 막대와 배경 밝기로 현재 화면을 표시한다."""

    def __init__(self, master, name, icon, label, on_select):
        super().__init__(master, fg_color=C_SURFACE, corner_radius=0, height=42)
        self.name = name
        self.active = False
        self.pack_propagate(False)

        self.marker = ctk.CTkFrame(self, width=3, fg_color=C_SURFACE, corner_radius=0)
        self.marker.pack(side="left", fill="y")
        self.icon_lbl = ctk.CTkLabel(self, text=icon, width=20, font=FONT_NAV, text_color=C_ASH)
        self.icon_lbl.pack(side="left", padx=(PAD_M - 3, PAD_S))
        self.text_lbl = ctk.CTkLabel(self, text=label, font=FONT_NAV, text_color=C_ASH)
        self.text_lbl.pack(side="left")
        # 받는 중 표시. 노랑 점 하나로, 대기열 메뉴에만 쓴다
        self.live_dot = ctk.CTkFrame(self, width=6, height=6, fg_color=C_GIALLO, corner_radius=0)
        self.count_lbl = ctk.CTkLabel(self, text="", font=FONT_LABEL, text_color=C_STEEL)
        self.count_lbl.pack(side="right", padx=(0, PAD_M + 2))

        for widget in (self, self.icon_lbl, self.text_lbl, self.count_lbl):
            widget.bind("<Button-1>", lambda _e: on_select(self.name))
            widget.bind("<Enter>", lambda _e: self._hover(True))
            widget.bind("<Leave>", lambda _e: self._hover(False))

    def _hover(self, inside):
        if not self.active:
            self.configure(fg_color=C_BG if inside else C_SURFACE)

    def set_active(self, active):
        self.active = active
        bg = C_BG if active else C_SURFACE
        text = C_PEARL if active else C_ASH
        self.configure(fg_color=bg)
        self.marker.configure(fg_color=C_GIALLO if active else bg)
        self.icon_lbl.configure(text_color=text)
        self.text_lbl.configure(text_color=text)
        self.count_lbl.configure(text_color=text if active else C_STEEL)

    def set_count(self, count):
        self.count_lbl.configure(text=str(count) if count else "")

    def set_live(self, live):
        if live:
            self.live_dot.pack(side="left", padx=(PAD_S, 0))
        else:
            self.live_dot.pack_forget()


class Sidebar(ctk.CTkFrame):
    """메뉴와 진행 요약을 담는 왼쪽 기둥."""

    def __init__(self, master, on_select, on_show_queue, on_stop, logo_image=None):
        super().__init__(master, width=SIDEBAR_WIDTH, fg_color=C_SURFACE, corner_radius=0)
        self.pack_propagate(False)
        self.items = {}

        logo = ctk.CTkFrame(self, fg_color="transparent")
        logo.pack(fill="x", padx=18, pady=(20, 22))
        if logo_image is not None:
            ctk.CTkLabel(logo, text="", image=logo_image, width=LOGO_SIZE).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(
            logo, text=tracked("YouTube") + "\n" + tracked("Music DL"),
            font=FONT_WORDMARK, text_color=C_PEARL, justify="left", anchor="w",
        ).pack(side="left")

        for entry in NAV_ITEMS:
            if entry is None:
                ctk.CTkFrame(self, height=1, fg_color=C_GRAPHITE, corner_radius=0).pack(
                    fill="x", padx=18, pady=(10, 6))
                ctk.CTkLabel(self, text="받은 파일", font=FONT_CAPTION, text_color=C_STEEL,
                             anchor="w").pack(fill="x", padx=18, pady=(0, 2))
                continue
            name, icon, label = entry
            item = NavItem(self, name, icon, label, on_select)
            item.pack(fill="x")
            self.items[name] = item

        self._build_progress(on_show_queue, on_stop)

    def _build_progress(self, on_show_queue, on_stop):
        box = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.progress_box = box
        ctk.CTkFrame(box, height=1, fg_color=C_GRAPHITE, corner_radius=0).pack(fill="x")

        inner = ctk.CTkFrame(box, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=(14, 18))

        self.eyebrow_lbl = ctk.CTkLabel(inner, text="", font=FONT_CAPTION, text_color=C_STEEL, anchor="w")
        self.eyebrow_lbl.pack(fill="x")
        self.title_lbl = ctk.CTkLabel(inner, text="", font=FONT_LABEL_BOLD, text_color=C_PEARL,
                                      anchor="w", width=SIDEBAR_WIDTH - 36)
        self.title_lbl.pack(fill="x", pady=(2, 6))

        self.cur_bar = ctk.CTkProgressBar(inner, height=6, corner_radius=RADIUS_CARD,
                                          fg_color=C_GRAPHITE, progress_color=C_GIALLO)
        self.cur_bar.set(0)
        self.cur_bar.pack(fill="x")
        self.cur_lbl = ctk.CTkLabel(inner, text="", font=FONT_CAPTION, text_color=C_ASH, anchor="w")
        self.cur_lbl.pack(fill="x", pady=(2, 6))

        self.total_bar = ctk.CTkProgressBar(inner, height=3, corner_radius=RADIUS_CARD,
                                            fg_color=C_GRAPHITE, progress_color=C_PEARL)
        self.total_bar.set(0)
        self.total_bar.pack(fill="x")
        self.total_lbl = ctk.CTkLabel(inner, text="", font=FONT_CAPTION, text_color=C_ASH, anchor="w")
        self.total_lbl.pack(fill="x", pady=(2, 8))

        buttons = ctk.CTkFrame(inner, fg_color="transparent")
        buttons.pack(fill="x")
        buttons.grid_columnconfigure((0, 1), weight=1, uniform="b")
        common = dict(height=26, fg_color="transparent", border_width=1, border_color=C_STEEL,
                      hover_color=C_GRAPHITE, text_color=C_PEARL, font=FONT_LABEL_BOLD,
                      corner_radius=RADIUS_BUTTON)
        ctk.CTkButton(buttons, text="대기열 보기", command=on_show_queue, **common).grid(
            row=0, column=0, sticky="ew", padx=(0, 3))
        self.stop_btn = ctk.CTkButton(buttons, text="중단", command=on_stop, **common)
        self.stop_btn.grid(row=0, column=1, sticky="ew", padx=(3, 0))

    # ---- 바깥에서 쓰는 동작 ----
    def set_active(self, name):
        for key, item in self.items.items():
            item.set_active(key == name)

    def set_count(self, name, count):
        if name in self.items:
            self.items[name].set_count(count)

    def set_live(self, live):
        self.items["queue"].set_live(live)

    def show_progress(self, visible):
        if visible:
            self.progress_box.pack(side="bottom", fill="x")
        else:
            self.progress_box.pack_forget()

    def update_progress(self, eyebrow, title, cur_value, cur_text, total_value, total_text):
        self.eyebrow_lbl.configure(text=eyebrow)
        # 사이드바 폭에 맞춰 자른다. Tk 라벨은 말줄임을 해 주지 않는다
        self.title_lbl.configure(text=title if len(title) <= 22 else title[:21] + "…")
        self.cur_bar.set(cur_value)
        self.cur_lbl.configure(text=cur_text)
        self.total_bar.set(total_value)
        self.total_lbl.configure(text=total_text)

    def set_stop_enabled(self, enabled):
        self.stop_btn.configure(
            state="normal" if enabled else "disabled",
            border_color=C_STEEL if enabled else C_GRAPHITE,
            text_color=C_PEARL if enabled else C_GRAPHITE,
        )


__all__ = ["Sidebar", "NAV_ITEMS"]
