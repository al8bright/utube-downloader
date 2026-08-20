"""디자인 토큰 — DESIGN.md (Lamborghini.com 스타일 레퍼런스).

색·서체·간격을 여기서만 정의한다. 위젯 코드에는 리터럴을 두지 않는다.
"""
import customtkinter as ctk

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


# 브랜드 유일색
C_GIALLO = "#ffc000"           # Giallo Vivo — 주 동작 버튼, 진행 바


C_GIALLO_SHADE = "#917300"     # Giallo Ombra — 호버, 목록 마커


# 표면 (밝기 대비만으로 층을 만든다)
C_BG = "#202020"               # Carbony Black — 기본 무대


C_SURFACE = "#181818"          # Carbon Deep — 카드, 행, 보조 버튼


C_SURFACE_DEEP = "#000000"     # Pure Black — 노랑 위 텍스트, 가장 깊은 면


C_PEARL = "#ffffff"            # Pearl White


# 중립 램프
C_GRAPHITE = "#494949"         # 구분, 비활성, 호버


C_STEEL = "#7d7d7d"            # 보조 텍스트


C_ASH = "#969696"              # 흐린 텍스트


# ---- 역할 별칭 (위젯 코드는 이 이름만 쓴다) ----
C_ACCENT = C_GIALLO


C_ACCENT_HOVER = C_GIALLO_SHADE


C_SUCCESS = C_PEARL            # 완료 상태 = 색이 아니라 밝기로


C_SUCCESS_HOVER = C_ASH


C_DANGER = C_GIALLO_SHADE      # 실패 마커 (브랜드 팔레트 안에서)


C_DANGER_HOVER = C_GIALLO_SHADE


C_WARNING = C_STEEL            # 진행 중 = 차분한 중립


C_INFO = C_SURFACE             # 보조 버튼 = 면 대비로만


C_INFO_HOVER = C_GRAPHITE


C_SURFACE_MUTED = C_SURFACE


C_SURFACE_MUTED_HOVER = C_GRAPHITE


C_DISABLED = C_GRAPHITE


C_HOVER_NEUTRAL = C_GRAPHITE


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


FONT_TITLE = (FONT_DISPLAY_FAMILY, 34)


FONT_HEADING = (FONT_FAMILY, 13, "bold")


FONT_BODY_BOLD = (FONT_FAMILY, 12, "bold")


FONT_BODY = (FONT_FAMILY, 12)


FONT_LABEL_BOLD = (FONT_FAMILY, 11, "bold")


FONT_LABEL = (FONT_FAMILY, 11)


FONT_ITEM = (FONT_FAMILY, 13)


FONT_CAPTION = (FONT_FAMILY, 10)


# 하드 엣지 — 반경 0 은 이 디자인의 비타협 항목이다
RADIUS_CARD = 0


RADIUS_BUTTON = 0


# 8px 그리드
PAD_S = 8


PAD_M = 16


PAD_L = 24


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
LOCKED_WIDGETS = (
    'download_selected_btn', 'download_all_btn', 'add_queue_btn',
    'format_select', 'quality_select', 'save_dir_entry',
    'save_dir_btn', 'direct_add_btn', 'clear_queue_btn',
    'clear_completed_btn', 'delete_all_audio_btn', 'delete_all_video_btn',
    'direct_url_entry', 'search_entry',
)
