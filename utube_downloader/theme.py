"""디자인 토큰 — 쓰임과 규칙은 DESIGN.md 참고.

색·서체·간격을 여기서만 정의한다. 위젯 코드에는 리터럴을 두지 않는다.
"""
import customtkinter as ctk

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


# 브랜드 유일색
C_GIALLO = "#ffc000"           # Giallo Vivo — 주 동작 버튼, 현재 곡 진행 바, 받는 중 표시


C_GIALLO_SHADE = "#917300"     # Giallo Ombra — 노랑 버튼 호버, 실패 표시


# 표면 (밝기 대비만으로 층을 만든다)
C_BG = "#202020"               # Carbony Black — 기본 무대


C_SURFACE = "#181818"          # Carbon Deep — 사이드바, 설정 카드, 하단 동작 바


C_SURFACE_DEEP = "#000000"     # Pure Black — 목록 행, 입력창, 노랑 위 글자


C_PEARL = "#ffffff"            # Pearl White


# 중립 램프
C_GRAPHITE = "#494949"         # 구분, 비활성, 호버


C_STEEL = "#7d7d7d"            # 보조 텍스트


C_ASH = "#969696"              # 흐린 텍스트


# ---- 역할 별칭 (위젯 코드는 이 이름만 쓴다) ----
C_SUCCESS = C_PEARL            # 완료 상태 = 색이 아니라 밝기로


C_DANGER = C_GIALLO_SHADE      # 실패 마커 (브랜드 팔레트 안에서)


C_WARNING = C_STEEL            # 진행 중 = 차분한 중립


C_TEXT = C_PEARL


C_TEXT_MUTED = C_ASH


C_TEXT_DIM = C_STEEL


C_TEXT_FAINT = C_GRAPHITE


# 서체
# LamboType 은 배포 불가라 Windows 기본 탑재 Bahnschrift(DIN 계열)로 대체한다.
# 한글은 Bahnschrift 에 글리프가 없어 시스템 폰트로 자동 폴백되므로,
# 한글이 들어가는 본문에는 맑은 고딕을 그대로 쓴다.
FONT_FAMILY = "Malgun Gothic"


FONT_DISPLAY_FAMILY = "Bahnschrift SemiBold Condensed"


FONT_HEADING = (FONT_FAMILY, 13, "bold")


FONT_BODY_BOLD = (FONT_FAMILY, 12, "bold")


FONT_BODY = (FONT_FAMILY, 12)


FONT_LABEL_BOLD = (FONT_FAMILY, 11, "bold")


FONT_LABEL = (FONT_FAMILY, 11)


FONT_ITEM = (FONT_FAMILY, 13)


FONT_CAPTION = (FONT_FAMILY, 10)


FONT_SCREEN_TITLE = (FONT_FAMILY, 20, "bold")   # 화면 제목 (검색 · 대기열 · 음성 · 영상)


FONT_NAV = (FONT_FAMILY, 13, "bold")            # 사이드바 메뉴


FONT_WORDMARK = (FONT_DISPLAY_FAMILY, 18)       # 사이드바 로고 옆 영문 이름


# 파일 형식 태그. MP3 까지 노랑이면 목록 전체에 강조색이 깔리므로 무채색으로 구분한다
EXT_COLORS = {"MP3": C_ASH, "FLAC": C_PEARL, "MP4": C_STEEL}


# 하드 엣지 — 반경 0 은 이 디자인의 비타협 항목이다
RADIUS_CARD = 0


RADIUS_BUTTON = 0


# 8px 그리드
PAD_S = 8


PAD_M = 16


PAD_L = 24


# 창과 사이드바
WINDOW_SIZE = "1000x840"


WINDOW_MIN = (920, 680)


SIDEBAR_WIDTH = 212


LOGO_SIZE = 30       # 사이드바 로고. 아이콘 파일 자체가 둥근 모서리다


def tracked(text):
    """Latin 대문자에 자간을 흉내 낸다.

    LamboType 의 0.023em 트래킹은 Tk 로 표현할 수 없어,
    영문 제목에 한해 글자 사이에 얇은 공백을 넣어 '설계된' 리듬을 낸다.
    한글에는 쓰지 않는다 (가독성이 크게 떨어진다).
    """
    return " ".join((text or "").upper())


DIALOG_MIN_WIDTH = 380


DIALOG_MAX_WIDTH = 620


DIALOG_MIN_HEIGHT = 180


DIALOG_MAX_HEIGHT = 560


DIALOG_CHAR_PX = 14      # Malgun Gothic 12pt 한글 한 글자의 대략적인 폭


DIALOG_LINE_PX = 22      # 한 줄 높이


DIALOG_CHROME_PX = 130   # 여백 + '확인' 버튼


# 다운로드 중 잠글 위젯들. 상수로 두어야 이름 오타를 테스트로 잡을 수 있다.
# 검색과 대기열에 담기는 잠그지 않는다. 받는 동안 다음 곡을 고를 수 있어야
# 사이드바 구성의 의미가 있고, 담은 곡은 이번 배치에 끼지 않는다고 따로 안내한다.
LOCKED_WIDGETS = (
    'download_selected_btn', 'download_all_btn',
    'format_select', 'quality_select', 'save_dir_entry', 'save_dir_btn',
    'clear_queue_btn', 'clear_completed_btn', 'queue_select_all_chk',
    'delete_all_audio_btn', 'delete_all_video_btn',
)
