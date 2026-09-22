"""화면 조립.

왼쪽 사이드바와 오른쪽 화면 4개(검색 · 대기열 · 음성 · 영상)를 만든다.
각 함수는 app(YoutubeDownloaderApp 인스턴스)을 받아 위젯을 만들어 붙인다.
상태나 동작은 다루지 않는다 — 그건 app 쪽 일이다.
"""
import customtkinter as ctk

from .formatting import FILE_SORTS, QUEUE_FILTERS
from .theme import (
    C_ASH, C_BG, C_GIALLO, C_GIALLO_SHADE, C_GRAPHITE, C_PEARL, C_STEEL,
    C_SURFACE, C_SURFACE_DEEP, C_TEXT_MUTED,
    FONT_BODY, FONT_BODY_BOLD, FONT_CAPTION, FONT_FAMILY, FONT_HEADING, FONT_LABEL,
    FONT_LABEL_BOLD, FONT_SCREEN_TITLE, LOGO_SIZE, PAD_L, PAD_M, PAD_S,
    RADIUS_BUTTON, RADIUS_CARD,
)
from .widgets import (
    FILE_COLUMNS, QUEUE_COLUMNS, ScrollableFileFrame, ScrollableQueueFrame,
    ScrollableSearchFrame, Sidebar,
)
from .winproc import resource_path

SCREEN_PADX = PAD_L        # 화면 좌우 여백
ACTION_BAR_HEIGHT = 64     # 화면 맨 아래 동작 바
SCROLLBAR_ALLOWANCE = 22   # 머리글 행이 스크롤 목록의 열과 맞도록 스크롤바 폭만큼 비운다


# --------------------------------------------------------------------------
# 반복되는 부품
# --------------------------------------------------------------------------
def outline_button(parent, text, command, width=0, height=30, font=FONT_LABEL_BOLD):
    """보조 버튼. 면은 투명하고 1px 테두리만 있다."""
    kwargs = dict(
        text=text, command=command, height=height, fg_color="transparent",
        border_width=1, border_color=C_STEEL, hover_color=C_GRAPHITE,
        text_color=C_PEARL, text_color_disabled=C_GRAPHITE, font=font,
        corner_radius=RADIUS_BUTTON,
    )
    if width:
        kwargs['width'] = width
    return ctk.CTkButton(parent, **kwargs)


def primary_button(parent, text, command, height=40, width=180):
    """주 동작 버튼. 노랑은 화면마다 여기 하나에만 쓴다."""
    return ctk.CTkButton(
        parent, text=text, command=command, height=height, width=width,
        fg_color=C_GIALLO, hover_color=C_GIALLO_SHADE, text_color=C_SURFACE_DEEP,
        text_color_disabled=C_GRAPHITE, font=FONT_HEADING, corner_radius=RADIUS_BUTTON,
    )


def text_button(parent, text, command):
    """정리·삭제처럼 되돌리기 어려운 동작. 작게, 주 동작과 떨어뜨려 둔다."""
    return ctk.CTkButton(
        parent, text=text, command=command, width=0, height=28,
        fg_color="transparent", hover_color=C_GRAPHITE, border_width=0,
        text_color=C_ASH, text_color_disabled=C_GRAPHITE,
        font=ctk.CTkFont(family=FONT_FAMILY, size=12, underline=True),
        corner_radius=RADIUS_BUTTON,
    )


def chip_text(label, count=None):
    """칩 글자. CTkButton 은 안쪽 여백이 거의 없어 공백으로 띄운다."""
    return f"  {label}  " if count is None else f"  {label} {count}  "


def chip(parent, text, command):
    """필터 칩. 켜진 칩은 style_chip 으로 테두리와 글자를 밝힌다."""
    return ctk.CTkButton(
        parent, text=chip_text(text), command=command, width=0, height=24,
        fg_color="transparent", hover_color=C_GRAPHITE, border_width=1,
        border_color=C_GRAPHITE, text_color=C_ASH, font=FONT_LABEL,
        corner_radius=RADIUS_BUTTON,
    )


def style_chip(button, active):
    button.configure(border_color=C_PEARL if active else C_GRAPHITE,
                     text_color=C_PEARL if active else C_ASH)


def entry(parent, height=32, font=FONT_LABEL, **kwargs):
    return ctk.CTkEntry(
        parent, height=height, font=font, corner_radius=RADIUS_CARD,
        fg_color=C_SURFACE_DEEP, border_color=C_GRAPHITE, border_width=1,
        text_color=C_PEARL, placeholder_text_color=C_STEEL, **kwargs,
    )


def screen_header(parent, title):
    """화면 제목과 그 옆의 요약 문구. 요약 라벨을 돌려준다."""
    header = ctk.CTkFrame(parent, fg_color="transparent")
    header.grid(row=0, column=0, sticky="ew", padx=SCREEN_PADX, pady=(20, 12))
    ctk.CTkLabel(header, text=title, font=FONT_SCREEN_TITLE, text_color=C_PEARL).pack(side="left")
    summary = ctk.CTkLabel(header, text="", font=FONT_LABEL, text_color=C_ASH)
    summary.pack(side="left", padx=(12, 0), pady=(6, 0))
    return header, summary


def column_header(parent, row, columns):
    """목록 위의 열 이름. 목록 행과 같은 열 폭을 쓴다."""
    head = ctk.CTkFrame(parent, fg_color="transparent")
    head.grid(row=row, column=0, sticky="ew",
              padx=(SCREEN_PADX, SCREEN_PADX + SCROLLBAR_ALLOWANCE), pady=(4, 2))
    for col, (title, width) in enumerate(columns):
        if width:
            head.grid_columnconfigure(col, minsize=width, weight=0)
        else:
            head.grid_columnconfigure(col, weight=1)
        ctk.CTkLabel(head, text=title, font=FONT_CAPTION, text_color=C_STEEL,
                     anchor="w", height=16).grid(row=0, column=col, sticky="w",
                                                 padx=(12 if col == 0 else 4, 0))


def action_bar(parent, row):
    """화면 맨 아래 동작 바. 좌우 여백 없이 창 끝까지 깐다."""
    bar = ctk.CTkFrame(parent, fg_color=C_SURFACE, corner_radius=0, height=ACTION_BAR_HEIGHT)
    bar.grid(row=row, column=0, sticky="ew", pady=(10, 0))
    bar.pack_propagate(False)
    return bar


def load_logo():
    """사이드바 로고. 아이콘 파일 자체가 둥근 모서리라 그대로 줄여 쓴다."""
    try:
        from PIL import Image

        image = Image.open(resource_path("youtube_icon.ico"))
        image.size = max(image.info.get('sizes', [image.size]))
        image = image.convert("RGBA")
        return ctk.CTkImage(light_image=image, dark_image=image, size=(LOGO_SIZE, LOGO_SIZE))
    except Exception:
        return None


# --------------------------------------------------------------------------
# 전체 틀
# --------------------------------------------------------------------------
SCREEN_ORDER = ("search", "queue", "audio", "video")


def build_widgets(app):
    """사이드바와 화면 4개를 조립한다."""
    app.grid_columnconfigure(1, weight=1)
    app.grid_rowconfigure(0, weight=1)

    app.sidebar = Sidebar(
        app,
        on_select=app.show_screen,
        on_show_queue=lambda: app.show_screen("queue"),
        on_stop=app.request_stop_download,
        logo_image=load_logo(),
    )
    app.sidebar.grid(row=0, column=0, sticky="ns")

    content = ctk.CTkFrame(app, fg_color=C_BG, corner_radius=0)
    content.grid(row=0, column=1, sticky="nsew")
    content.grid_rowconfigure(0, weight=1)
    content.grid_columnconfigure(0, weight=1)

    app.screens = {}
    for name in SCREEN_ORDER:
        frame = ctk.CTkFrame(content, fg_color=C_BG, corner_radius=0)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        app.screens[name] = frame

    build_search_screen(app, app.screens["search"])
    build_queue_screen(app, app.screens["queue"])
    build_file_screen(app, app.screens["audio"], "audio")
    build_file_screen(app, app.screens["video"], "video")


# --------------------------------------------------------------------------
# 검색
# --------------------------------------------------------------------------
def build_search_screen(app, screen):
    screen.grid_rowconfigure(4, weight=1)
    _header, app.search_count_lbl = screen_header(screen, "검색")

    search_bar = ctk.CTkFrame(screen, fg_color="transparent")
    search_bar.grid(row=1, column=0, sticky="ew", padx=SCREEN_PADX)
    app.search_entry = entry(
        search_bar, height=40, font=FONT_BODY,
        placeholder_text="키워드로 검색하거나 유튜브 링크를 붙여넣으세요",
    )
    app.search_entry.pack(side="left", fill="x", expand=True, padx=(0, PAD_S))
    app.search_entry.bind("<Return>", lambda event: app.start_search())
    app.search_btn = outline_button(search_bar, "검색", app.start_search, width=96, height=40,
                                    font=FONT_BODY_BOLD)
    app.search_btn.pack(side="right")

    # 안내 문구 자리. 검색 중에는 진행 막대와 '찾는 중… N개' 로 바뀐다
    status = ctk.CTkFrame(screen, fg_color="transparent")
    status.grid(row=2, column=0, sticky="ew", padx=SCREEN_PADX, pady=(6, 6))
    status.grid_columnconfigure(0, weight=1)
    app.search_progress_bar = ctk.CTkProgressBar(
        status, height=3, corner_radius=RADIUS_CARD, fg_color=C_GRAPHITE,
        progress_color=C_GIALLO, mode="determinate")
    app.search_progress_bar.set(0)
    app.search_progress_bar.grid(row=0, column=0, sticky="ew", pady=(0, 4))
    app.search_progress_bar.grid_remove()
    app.search_hint_text = "링크를 붙여넣으면 검색하지 않고 바로 대기열에 담습니다."
    app.search_hint_lbl = ctk.CTkLabel(
        status, text=app.search_hint_text, font=FONT_LABEL, text_color=C_STEEL,
        anchor="w", height=18)
    app.search_hint_lbl.grid(row=1, column=0, sticky="ew")

    options = ctk.CTkFrame(screen, fg_color="transparent")
    options.grid(row=3, column=0, sticky="ew", padx=SCREEN_PADX, pady=(0, 6))
    app.search_hide_queued_var = ctk.BooleanVar(value=False)
    app.search_hide_queued_chk = ctk.CTkCheckBox(
        options, text="이미 담은 곡 숨기기", variable=app.search_hide_queued_var,
        command=app.on_hide_queued_changed, font=FONT_LABEL, text_color=C_ASH,
        corner_radius=RADIUS_CARD, checkbox_width=16, checkbox_height=16, border_width=1,
        fg_color=C_PEARL, hover_color=C_ASH, checkmark_color=C_SURFACE_DEEP, border_color=C_STEEL,
    )
    app.search_hide_queued_chk.pack(side="left")

    app.search_scroll = ScrollableSearchFrame(screen, fg_color="transparent")
    app.search_scroll.grid(row=4, column=0, sticky="nsew", padx=(SCREEN_PADX, SCREEN_PADX - 8))
    app.search_scroll.is_queued = app.is_in_queue
    app.search_scroll.on_change = app.update_search_selection
    app.search_scroll.populate_results([])

    bar = action_bar(screen, 5)
    app.search_sel_lbl = ctk.CTkLabel(bar, text="", font=FONT_BODY_BOLD, text_color=C_PEARL)
    app.search_sel_lbl.pack(side="left", padx=(SCREEN_PADX, 10))
    ctk.CTkLabel(bar, text="형식과 저장 위치는 대기열 화면에서 정합니다", font=FONT_LABEL,
                 text_color=C_STEEL).pack(side="left")
    app.add_queue_btn = primary_button(bar, "대기열에 추가", app.add_selected_to_queue, width=160)
    app.add_queue_btn.pack(side="right", padx=SCREEN_PADX)


# --------------------------------------------------------------------------
# 대기열
# --------------------------------------------------------------------------
def build_queue_screen(app, screen):
    screen.grid_rowconfigure(6, weight=1)
    _header, app.queue_summary_lbl = screen_header(screen, "대기열")
    _build_queue_settings(app, screen)
    _build_now_card(app, screen)
    _build_queue_toolbar(app, screen)
    column_header(screen, 5, QUEUE_COLUMNS)

    app.queue_scroll = ScrollableQueueFrame(screen, fg_color="transparent")
    app.queue_scroll.grid(row=6, column=0, sticky="nsew", padx=(SCREEN_PADX, SCREEN_PADX - 8))
    app.queue_scroll.on_check = app.update_queue_selection
    app.queue_scroll.populate_queue(app.queue_items, app.delete_queue_item)

    _build_queue_actions(app, screen)


def _field(parent, column, title, note=None):
    box = ctk.CTkFrame(parent, fg_color="transparent")
    box.grid(row=0, column=column, sticky="ew", padx=(0, 20) if column < 2 else 0)
    label_row = ctk.CTkFrame(box, fg_color="transparent")
    label_row.pack(fill="x", pady=(0, 6))
    ctk.CTkLabel(label_row, text=title, font=FONT_LABEL_BOLD, text_color=C_ASH,
                 height=16).pack(side="left")
    if note:
        ctk.CTkLabel(label_row, text=note, font=FONT_LABEL, text_color=C_STEEL,
                     height=16).pack(side="left", padx=(6, 0))
    return box, label_row


def _build_queue_settings(app, screen):
    """받는 방법: 형식 · 음질 · 저장 위치. 모든 곡에 한 번에 적용된다."""
    card = ctk.CTkFrame(screen, fg_color=C_SURFACE, corner_radius=RADIUS_CARD)
    card.grid(row=1, column=0, sticky="ew", padx=SCREEN_PADX)
    inner = ctk.CTkFrame(card, fg_color="transparent")
    inner.pack(fill="x", padx=PAD_M, pady=(12, 14))
    inner.grid_columnconfigure(2, weight=1)

    box, _ = _field(inner, 0, "형식")
    app.format_var = ctk.StringVar(value="MP3")
    app.format_select = ctk.CTkSegmentedButton(
        box,
        values=["MP3", "FLAC", "MP4"],
        variable=app.format_var,
        command=app.on_format_changed,
        font=FONT_LABEL_BOLD,
        width=180,
        dynamic_resizing=False,   # 켜 두면 글자 폭으로 줄어 세 칸이 붙어 버린다
        height=30,
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
    app.format_select.pack(anchor="w")

    # 음질 칸은 FLAC·MP4 에서도 자리를 지킨다. 사라졌다 나타나면 옆 칸이 흔들린다
    box, _ = _field(inner, 1, "음질", "MP3만")
    app.quality_var = ctk.StringVar(value="320kbps")
    app.quality_select = ctk.CTkOptionMenu(
        box,
        values=["320kbps", "256kbps", "192kbps"],
        variable=app.quality_var,
        width=110,
        height=30,
        font=FONT_LABEL,
        corner_radius=RADIUS_BUTTON,
        fg_color=C_SURFACE_DEEP,
        button_color=C_GRAPHITE,
        button_hover_color=C_STEEL,
        text_color=C_PEARL,
        text_color_disabled=C_GRAPHITE,
        dropdown_fg_color=C_SURFACE,
        dropdown_hover_color=C_GRAPHITE,
        dropdown_text_color=C_PEARL,
    )
    app.quality_select.pack(anchor="w")

    box, label_row = _field(inner, 2, "저장 위치")
    app.settings_lock_lbl = ctk.CTkLabel(
        label_row, text="받는 동안은 바꿀 수 없습니다", font=FONT_LABEL,
        text_color=C_ASH, height=16)
    path_row = ctk.CTkFrame(box, fg_color="transparent")
    path_row.pack(fill="x")
    app.save_dir_entry = entry(path_row, textvariable=app.save_dir_var)
    app.save_dir_entry.pack(side="left", fill="x", expand=True)
    app.save_dir_btn = outline_button(path_row, "변경", app.browse_save_dir, width=56)
    app.save_dir_btn.pack(side="left", padx=(6, 0))
    app.save_dir_open_btn = outline_button(path_row, "열기", app.open_download_folder, width=56)
    app.save_dir_open_btn.pack(side="left", padx=(6, 0))


def _build_now_card(app, screen):
    """지금 받는 중. 받는 동안과 끝난 직후 결과를 보여 줄 때만 나타난다."""
    app.now_card = ctk.CTkFrame(screen, fg_color=C_SURFACE_DEEP, corner_radius=RADIUS_CARD,
                                border_width=1, border_color=C_GIALLO)
    app.now_card.grid(row=2, column=0, sticky="ew", padx=SCREEN_PADX, pady=(12, 0))
    inner = ctk.CTkFrame(app.now_card, fg_color="transparent")
    inner.pack(fill="x", padx=PAD_M, pady=(12, 14))

    top = ctk.CTkFrame(inner, fg_color="transparent")
    top.pack(fill="x")
    app.queue_status_lbl = ctk.CTkLabel(top, text="", font=FONT_HEADING, text_color=C_PEARL,
                                        anchor="w")
    app.queue_status_lbl.pack(side="left", fill="x", expand=True)
    app.now_order_lbl = ctk.CTkLabel(top, text="", font=FONT_LABEL, text_color=C_ASH)
    app.now_order_lbl.pack(side="right")

    # 단계 표시: 분석 → 다운로드 → 변환. 현재 단계만 흰 블록으로 채운다
    app.now_steps_row = ctk.CTkFrame(inner, fg_color="transparent")
    app.now_steps_row.pack(fill="x", pady=(6, 8))
    app.now_step_lbls = {}
    for key, text in (("analyze", "분석"), ("download", "다운로드"), ("convert", "변환")):
        label = ctk.CTkLabel(app.now_steps_row, text=f"  {text}  ", font=FONT_CAPTION, height=20,
                             fg_color=C_SURFACE_DEEP, text_color=C_STEEL, corner_radius=0)
        label.pack(side="left", padx=(0, 2))
        app.now_step_lbls[key] = label

    app.cur_prog_bar = ctk.CTkProgressBar(
        inner, height=PAD_S, corner_radius=RADIUS_CARD,
        fg_color=C_GRAPHITE, progress_color=C_GIALLO)
    app.cur_prog_bar.set(0.0)
    app.cur_prog_bar.pack(fill="x")
    app.cur_stats_lbl = ctk.CTkLabel(inner, text="", font=FONT_LABEL, text_color=C_ASH, anchor="w")
    app.cur_stats_lbl.pack(fill="x", pady=(2, 8))

    overall = ctk.CTkFrame(inner, fg_color="transparent")
    overall.pack(fill="x")
    app.overall_status_lbl = ctk.CTkLabel(overall, text="", font=FONT_LABEL, text_color=C_ASH,
                                          anchor="w", width=150)
    app.overall_status_lbl.pack(side="left")
    app.total_prog_bar = ctk.CTkProgressBar(
        overall, height=3, corner_radius=RADIUS_CARD,
        fg_color=C_GRAPHITE, progress_color=C_PEARL)
    app.total_prog_bar.set(0.0)
    app.total_prog_bar.pack(side="left", fill="x", expand=True, padx=(10, 0))

    app.now_card.grid_remove()


def _build_queue_toolbar(app, screen):
    """전체 선택 · 필터 칩 · 링크 추가. 링크 입력 줄은 누를 때만 펼친다."""
    bar = ctk.CTkFrame(screen, fg_color="transparent")
    bar.grid(row=3, column=0, sticky="ew", padx=SCREEN_PADX, pady=(14, 4))

    app.queue_select_all_var = ctk.BooleanVar(value=False)
    app.queue_select_all_chk = ctk.CTkCheckBox(
        bar, text="", width=20, variable=app.queue_select_all_var,
        command=app.toggle_select_all, corner_radius=RADIUS_CARD,
        checkbox_width=16, checkbox_height=16, border_width=1,
        fg_color=C_PEARL, hover_color=C_ASH, checkmark_color=C_SURFACE_DEEP, border_color=C_STEEL,
    )
    app.queue_select_all_chk.pack(side="left", padx=(12, 6))
    app.queue_sel_lbl = ctk.CTkLabel(bar, text="", font=FONT_LABEL, text_color=C_ASH)
    app.queue_sel_lbl.pack(side="left")

    app.link_toggle_btn = outline_button(bar, "+ 링크 추가", app.toggle_link_row, height=26)
    app.link_toggle_btn.pack(side="right", padx=(8, 0))

    app.queue_filter_btns = {}
    for bucket in reversed(QUEUE_FILTERS):
        button = chip(bar, bucket, lambda b=bucket: app.set_queue_filter(b))
        button.pack(side="right", padx=(6, 0))
        app.queue_filter_btns[bucket] = button
    style_chip(app.queue_filter_btns["전체"], True)

    app.link_row = ctk.CTkFrame(screen, fg_color="transparent")
    app.link_row.grid(row=4, column=0, sticky="ew", padx=SCREEN_PADX, pady=(4, 2))
    app.direct_url_entry = entry(app.link_row, placeholder_text="https://www.youtube.com/watch?v=...")
    app.direct_url_entry.pack(side="left", fill="x", expand=True)
    app.direct_url_entry.bind("<Return>", lambda event: app.add_direct_url())
    app.direct_add_btn = outline_button(app.link_row, "대기열에 추가", app.add_direct_url, width=96)
    app.direct_add_btn.pack(side="left", padx=(6, 0))
    outline_button(app.link_row, "닫기", app.toggle_link_row, width=48).pack(side="left", padx=(6, 0))
    app.link_row.grid_remove()


def _build_queue_actions(app, screen):
    """실행 버튼은 여기 한 곳에만 둔다. 받는 중에는 중단 하나만 보인다."""
    bar = action_bar(screen, 7)
    app.clear_completed_btn = text_button(bar, "완료 항목 정리", app.clear_completed_queue)
    app.clear_completed_btn.pack(side="left", padx=(SCREEN_PADX - 6, 0))
    app.clear_queue_btn = text_button(bar, "대기열 비우기", app.clear_queue)
    app.clear_queue_btn.pack(side="left", padx=(4, 0))

    app.download_all_btn = primary_button(bar, "대기 중인 곡 모두 받기", app.start_all_download, width=200)
    app.download_all_btn.pack(side="right", padx=(0, SCREEN_PADX))
    app.download_selected_btn = outline_button(bar, "선택한 곡 받기", app.start_selected_download,
                                               width=160, height=40, font=FONT_HEADING)
    app.download_selected_btn.pack(side="right", padx=(0, 8))

    app.stop_download_btn = ctk.CTkButton(
        bar,
        text="다운로드 중단",
        text_color=C_PEARL,
        width=140,
        height=40,
        fg_color="transparent",
        border_width=1,
        border_color=C_STEEL,
        hover_color=C_GRAPHITE,
        state="disabled",
        font=FONT_HEADING,
        command=app.request_stop_download,
        corner_radius=RADIUS_BUTTON
    )
    app.stop_hint_lbl = ctk.CTkLabel(
        bar, text="중단하면 지금 곡까지만 멈추고 나머지는 대기 중으로 남습니다",
        font=FONT_LABEL, text_color=C_STEEL)


# --------------------------------------------------------------------------
# 음성 · 영상
# --------------------------------------------------------------------------
FILE_SCREENS = {
    "audio": {"title": "음성", "exts": ("전체", "MP3", "FLAC"),
              "empty": "받은 음성 파일이 없습니다."},
    "video": {"title": "영상", "exts": (),
              "empty": "받은 영상 파일이 없습니다."},
}


def build_file_screen(app, screen, kind):
    spec = FILE_SCREENS[kind]
    screen.grid_rowconfigure(3, weight=1)
    header, count_lbl = screen_header(screen, spec["title"])
    outline_button(header, "폴더 열기", app.open_download_folder, height=30).pack(side="right")

    tools = ctk.CTkFrame(screen, fg_color="transparent")
    tools.grid(row=1, column=0, sticky="ew", padx=SCREEN_PADX, pady=(0, 6))
    filter_entry = entry(tools, width=240, placeholder_text="파일 이름으로 찾기")
    filter_entry.pack(side="left")
    filter_entry.bind("<KeyRelease>", lambda _e: app.apply_file_view(kind))

    ext_btns = {}
    for ext in spec["exts"]:
        button = chip(tools, ext, lambda e=ext: app.set_file_ext(kind, e))
        button.pack(side="left", padx=(6, 0))
        ext_btns[ext] = button
    if ext_btns:
        style_chip(ext_btns["전체"], True)

    sort_select = ctk.CTkOptionMenu(
        tools, values=list(FILE_SORTS), width=130, height=30, font=FONT_LABEL,
        corner_radius=RADIUS_BUTTON, fg_color=C_SURFACE_DEEP, button_color=C_GRAPHITE,
        button_hover_color=C_STEEL, text_color=C_PEARL, dropdown_fg_color=C_SURFACE,
        dropdown_hover_color=C_GRAPHITE, dropdown_text_color=C_PEARL,
        command=lambda value: app.set_file_sort(kind, value),
    )
    sort_select.pack(side="right")

    column_header(screen, 2, FILE_COLUMNS)
    scroll = ScrollableFileFrame(screen, fg_color="transparent")
    scroll.grid(row=3, column=0, sticky="nsew", padx=(SCREEN_PADX, SCREEN_PADX - 8))

    bar = action_bar(screen, 4)
    ctk.CTkLabel(bar, text="저장 위치", font=FONT_LABEL, text_color=C_STEEL).pack(
        side="left", padx=(SCREEN_PADX, 8))
    path_lbl = ctk.CTkLabel(bar, textvariable=app.save_dir_var, font=FONT_LABEL,
                            text_color=C_TEXT_MUTED)
    path_lbl.pack(side="left")

    if kind == "audio":
        app.delete_all_audio_btn = text_button(bar, "목록 전체 삭제…", app.delete_all_completed_audio)
        app.delete_all_audio_btn.pack(side="right", padx=(0, SCREEN_PADX - 6))
        app.scroll_audio_frame = scroll
    else:
        app.delete_all_video_btn = text_button(bar, "목록 전체 삭제…", app.delete_all_completed_video)
        app.delete_all_video_btn.pack(side="right", padx=(0, SCREEN_PADX - 6))
        app.scroll_video_frame = scroll

    app.file_views[kind] = {
        "count_lbl": count_lbl, "filter_entry": filter_entry, "ext_btns": ext_btns,
        "sort_select": sort_select, "ext": "전체", "sort": "recent",
        "empty": spec["empty"],
    }
