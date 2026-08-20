"""탭 화면 조립.

각 함수는 app(YoutubeDownloaderApp 인스턴스)을 받아 위젯을 만들어 붙인다.
상태나 동작은 다루지 않는다 — 그건 app 쪽 일이다.
"""
import customtkinter as ctk

from .formatting import SEARCH_INITIAL_TEXT
from .theme import (
    C_ASH, C_BG, C_GIALLO, C_GIALLO_SHADE, C_GRAPHITE, C_PEARL, C_STEEL,
    C_SURFACE, C_SURFACE_DEEP, C_TEXT, C_TEXT_DIM, C_TEXT_MUTED,
    FONT_BODY, FONT_BODY_BOLD, FONT_HEADING, FONT_LABEL, FONT_LABEL_BOLD, FONT_TITLE,
    PAD_L, PAD_M, PAD_S, RADIUS_BUTTON, RADIUS_CARD, tracked,
)
from .widgets import ScrollableFileFrame, ScrollableQueueFrame, ScrollableSearchFrame


def build_widgets(app):
    """전체 화면을 조립한다."""
    build_header(app)
    build_search_tab(app)
    build_queue_tab(app)
    build_audio_tab(app)
    build_video_tab(app)



def build_header(app):
    """상단 타이틀과 탭 뷰를 만든다."""
    # 1. 상단 타이틀
    # 헤드라인은 흰색. 노랑은 주 동작 버튼 하나에만 남겨 둔다.
    title_label = ctk.CTkLabel(
        app,
        text=tracked("YouTube Music Downloader"),
        font=FONT_TITLE,
        text_color=C_PEARL
    )
    title_label.pack(pady=(PAD_L, PAD_M))
    
    # 2. 탭 뷰 초기화
    app.tabview = ctk.CTkTabview(
        app,
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
    app.tabview.pack(fill="both", expand=True, padx=PAD_M, pady=(0, PAD_M))
    
    app.tab_search = app.tabview.add("검색 및 추가")
    app.tab_queue = app.tabview.add("다운로드 대기열")
    app.tab_audio = app.tabview.add("음성 다운로드 목록")
    app.tab_video = app.tabview.add("영상 다운로드 목록")


def build_search_tab(app):
    """검색 및 추가 탭을 만든다."""
    # ----------------------------------------------------
    # 탭 1: 검색 및 추가 구현
    # ----------------------------------------------------
    app.tab_search.grid_columnconfigure(0, weight=1)
    app.tab_search.grid_rowconfigure(1, weight=1)
    
    # 검색어 입력 영역 프레임
    search_bar = ctk.CTkFrame(app.tab_search, fg_color="transparent")
    search_bar.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
    
    app.search_entry = ctk.CTkEntry(
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
    app.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
    app.search_entry.bind("<Return>", lambda event: app.start_search())
    
    app.search_btn = ctk.CTkButton(
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
        command=app.start_search,
        corner_radius=RADIUS_BUTTON
    )
    app.search_btn.pack(side="right", padx=(5, 0))
    
    # 검색 결과 스크롤 프레임
    app.search_scroll = ScrollableSearchFrame(app.tab_search, fg_color="transparent")
    app.search_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
    app.search_scroll.populate_results([])
    
    # 대기열에 추가 버튼 프레임
    search_action_bar = ctk.CTkFrame(app.tab_search, fg_color="transparent")
    search_action_bar.grid(row=2, column=0, sticky="ew", padx=10, pady=(5, 10))
    
    app.add_queue_btn = ctk.CTkButton(
        search_action_bar, 
        text="선택한 항목 다운로드 대기열에 추가", 
        height=38,
        fg_color=C_GIALLO,
        hover_color=C_GIALLO_SHADE,
        text_color=C_SURFACE_DEEP,
        font=FONT_HEADING,
        command=app.add_selected_to_queue,
        corner_radius=RADIUS_BUTTON
    )
    app.add_queue_btn.pack(fill="x")


def build_queue_tab(app):
    """다운로드 대기열 탭을 만든다."""
    # ----------------------------------------------------
    # 탭 2: 다운로드 대기열 구현
    # ----------------------------------------------------
    app.tab_queue.grid_columnconfigure(0, weight=1)
    app.tab_queue.grid_rowconfigure(0, weight=1)
    
    # 대기열 스크롤 프레임
    app.queue_scroll = ScrollableQueueFrame(app.tab_queue, fg_color="transparent")
    app.queue_scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=5)
    app.queue_scroll.populate_queue(app.queue_items, app.delete_queue_item)
    
    # 대기열 하단 제어 및 설정 영역
    queue_ctrl_frame = ctk.CTkFrame(app.tab_queue, fg_color=C_SURFACE, corner_radius=RADIUS_CARD)
    queue_ctrl_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(5, 10))
    
    # 직접 링크 추가 영역
    direct_add_row = ctk.CTkFrame(queue_ctrl_frame, fg_color="transparent")
    direct_add_row.pack(fill="x", padx=15, pady=(10, 5))
    
    ctk.CTkLabel(direct_add_row, text="유튜브 링크 직접 추가:", font=FONT_BODY_BOLD, text_color=C_TEXT_MUTED).pack(side="left", padx=(0, 5))
    
    app.direct_url_entry = ctk.CTkEntry(
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
    app.direct_url_entry.pack(side="left", fill="x", expand=True, padx=5)
    app.direct_url_entry.bind("<Return>", lambda event: app.add_direct_url())
    
    app.direct_add_btn = ctk.CTkButton(
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
        command=app.add_direct_url,
        corner_radius=RADIUS_BUTTON
    )
    app.direct_add_btn.pack(side="right", padx=(5, 0))
    
    # 저장 폴더 지정 영역 추가
    save_dir_row = ctk.CTkFrame(queue_ctrl_frame, fg_color="transparent")
    save_dir_row.pack(fill="x", padx=15, pady=(5, 5))
    
    ctk.CTkLabel(save_dir_row, text="저장 폴더 지정:", font=FONT_BODY_BOLD, text_color=C_TEXT_MUTED).pack(side="left", padx=(0, 5))
    
    app.save_dir_entry = ctk.CTkEntry(
        save_dir_row, 
        textvariable=app.save_dir_var,
        height=30,
        font=FONT_LABEL,
        corner_radius=RADIUS_CARD,
        fg_color=C_SURFACE_DEEP,
        border_color=C_GRAPHITE,
        border_width=1,
        text_color=C_PEARL,
        placeholder_text_color=C_STEEL,
    )
    app.save_dir_entry.pack(side="left", fill="x", expand=True, padx=5)
    
    app.save_dir_btn = ctk.CTkButton(
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
        command=app.browse_save_dir,
        corner_radius=RADIUS_BUTTON
    )
    app.save_dir_btn.pack(side="right", padx=(5, 0))
    
    # 설정 1: 포맷 선택 및 음질
    settings_row = ctk.CTkFrame(queue_ctrl_frame, fg_color="transparent")
    settings_row.pack(fill="x", padx=15, pady=(5, 5))
    
    ctk.CTkLabel(settings_row, text="다운로드 형식:", font=FONT_BODY_BOLD, text_color=C_TEXT_MUTED).pack(side="left", padx=(0, 5))
    
    app.format_var = ctk.StringVar(value="MP3")
    app.format_select = ctk.CTkSegmentedButton(
        settings_row,
        values=["MP3", "FLAC", "MP4"],
        variable=app.format_var,
        command=app.on_format_changed,
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
    app.format_select.pack(side="left", padx=5)
    
    app.quality_label = ctk.CTkLabel(settings_row, text="음질:", font=FONT_BODY_BOLD, text_color=C_TEXT_MUTED)
    app.quality_label.pack(side="left", padx=(15, 5))
    
    app.quality_var = ctk.StringVar(value="320kbps")
    app.quality_select = ctk.CTkOptionMenu(
        settings_row,
        values=["320kbps", "256kbps", "192kbps"],
        variable=app.quality_var,
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
    app.quality_select.pack(side="left", padx=5)
    
    app.clear_completed_btn = ctk.CTkButton(
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
        command=app.clear_completed_queue,
        corner_radius=RADIUS_BUTTON
    )
    app.clear_completed_btn.pack(side="right", padx=(5, 5))

    app.clear_queue_btn = ctk.CTkButton(
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
        command=app.clear_queue,
        corner_radius=RADIUS_BUTTON
    )
    app.clear_queue_btn.pack(side="right", padx=(5, 0))
    
    # 설정 2: 실시간 진행 바
    app.progress_row = ctk.CTkFrame(queue_ctrl_frame, fg_color="transparent")
    app.progress_row.pack(fill="x", padx=15, pady=5)
    
    app.queue_status_lbl = ctk.CTkLabel(app.progress_row, text="대기열 상태: 대기 중", font=FONT_BODY_BOLD, text_color=C_TEXT_MUTED, anchor="w")
    app.queue_status_lbl.pack(fill="x", pady=(2, 2))
    
    # 현재 곡 진행 상황 바
    app.cur_prog_bar = ctk.CTkProgressBar(
        app.progress_row, height=PAD_S, corner_radius=RADIUS_CARD,
        fg_color=C_GRAPHITE, progress_color=C_GIALLO)
    app.cur_prog_bar.set(0.0)
    app.cur_prog_bar.pack(fill="x", pady=2)
    
    app.cur_stats_lbl = ctk.CTkLabel(app.progress_row, text="", font=FONT_LABEL, text_color=C_TEXT_DIM, anchor="e")
    app.cur_stats_lbl.pack(fill="x", pady=(0, 2))
    
    # 전체 대기열 진행 상황 바
    app.overall_status_lbl = ctk.CTkLabel(app.progress_row, text="전체 진행 상황:", font=FONT_LABEL_BOLD, text_color=C_TEXT_MUTED, anchor="w")
    app.overall_status_lbl.pack(fill="x", pady=(2, 2))
    
    app.total_prog_bar = ctk.CTkProgressBar(
        app.progress_row, height=PAD_S, corner_radius=RADIUS_CARD,
        fg_color=C_GRAPHITE, progress_color=C_PEARL)
    app.total_prog_bar.set(0.0)
    app.total_prog_bar.pack(fill="x", pady=2)
    
    # 설정 3: 일괄 다운로드 버튼
    btn_row = ctk.CTkFrame(queue_ctrl_frame, fg_color="transparent")
    btn_row.pack(fill="x", padx=15, pady=(5, 10))
    
    app.download_selected_btn = ctk.CTkButton(
        btn_row, 
        text="선택된 항목 다운로드 시작", 
        height=38,
        fg_color="transparent",
        border_width=1,
        border_color=C_STEEL,
        hover_color=C_GRAPHITE,
        text_color=C_PEARL,
        font=FONT_HEADING,
        command=app.start_selected_download,
        corner_radius=RADIUS_BUTTON
    )
    app.download_selected_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))
    
    app.download_all_btn = ctk.CTkButton(
        btn_row, 
        text="대기열 전체 다운로드 시작",
        text_color=C_SURFACE_DEEP, 
        height=38,
        fg_color=C_GIALLO,
        hover_color=C_GIALLO_SHADE,
        font=FONT_HEADING,
        command=app.start_all_download,
        corner_radius=RADIUS_BUTTON
    )
    app.download_all_btn.pack(side="left", fill="x", expand=True, padx=4)
    
    app.stop_download_btn = ctk.CTkButton(
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
        command=app.request_stop_download,
        corner_radius=RADIUS_BUTTON
    )
    app.stop_download_btn.pack(side="right", fill="x", expand=True, padx=(4, 0))


def build_audio_tab(app):
    """음성 다운로드 목록 탭을 만든다."""
    # ----------------------------------------------------
    # 탭 3: 음성 다운로드 목록 구현
    # ----------------------------------------------------
    app.tab_audio.grid_columnconfigure(0, weight=1)
    app.tab_audio.grid_rowconfigure(1, weight=1)
    
    audio_header = ctk.CTkFrame(app.tab_audio, fg_color="transparent")
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
        command=app.open_download_folder,
        corner_radius=RADIUS_BUTTON
    )
    open_audio_folder_btn.pack(side="right", padx=5)
    
    app.delete_all_audio_btn = ctk.CTkButton(
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
        command=app.delete_all_completed_audio,
        corner_radius=RADIUS_BUTTON
    )
    app.delete_all_audio_btn.pack(side="right", padx=5)
    
    app.scroll_audio_frame = ScrollableFileFrame(app.tab_audio, fg_color="transparent")
    app.scroll_audio_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)


def build_video_tab(app):
    """영상 다운로드 목록 탭을 만든다."""
    # ----------------------------------------------------
    # 탭 4: 영상 다운로드 목록 구현
    # ----------------------------------------------------
    app.tab_video.grid_columnconfigure(0, weight=1)
    app.tab_video.grid_rowconfigure(1, weight=1)
    
    video_header = ctk.CTkFrame(app.tab_video, fg_color="transparent")
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
        command=app.open_download_folder,
        corner_radius=RADIUS_BUTTON
    )
    open_video_folder_btn.pack(side="right", padx=5)
    
    app.delete_all_video_btn = ctk.CTkButton(
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
        command=app.delete_all_completed_video,
        corner_radius=RADIUS_BUTTON
    )
    app.delete_all_video_btn.pack(side="right", padx=5)
    
    app.scroll_video_frame = ScrollableFileFrame(app.tab_video, fg_color="transparent")
    app.scroll_video_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
