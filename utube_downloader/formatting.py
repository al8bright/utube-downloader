"""화면에 보일 문자열과 수치를 만든다.

계산과 문구 생성만 한다. 위젯을 만들거나 건드리지 않는다.
"""
from .theme import (
    DIALOG_CHAR_PX, DIALOG_CHROME_PX, DIALOG_LINE_PX,
    DIALOG_MAX_HEIGHT, DIALOG_MAX_WIDTH, DIALOG_MIN_HEIGHT, DIALOG_MIN_WIDTH,
)


def format_duration(seconds):
    """초를 mm:ss 또는 hh:mm:ss 문자열로 변환한다.

    라이브 방송은 duration 이 None 이고 일부 항목은 float 으로 오므로,
    변환할 수 없는 값은 예외 대신 기본 표시를 돌려준다.
    """
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return UNKNOWN_TIME
    if total < 0:
        return UNKNOWN_TIME
    mins, secs = divmod(total, 60)
    hours, mins = divmod(mins, 60)
    return f"{hours:02d}:{mins:02d}:{secs:02d}" if hours > 0 else f"{mins:02d}:{secs:02d}"


def format_eta(seconds):
    """남은 시간(초)을 mm:ss 문자열로 변환한다.

    yt-dlp 는 eta 를 float 으로 주기도 한다. 표시용 값 하나 때문에
    다운로드 전체가 실패로 처리되지 않도록 방어한다.
    """
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return UNKNOWN_TIME
    if total < 0:
        return UNKNOWN_TIME
    mins, secs = divmod(total, 60)
    return f"{mins:02d}:{secs:02d}"


def describe_batch_result(done, failed, stopped, total=None, unit="곡"):
    """배치 결과 문구와 '전부 성공인가' 여부를 돌려준다.

    전량 실패인데 초록색 '완료' 로 보고하던 문제를 막기 위해,
    성공 여부를 문구와 함께 명시적으로 돌려준다.
    """
    parts = []
    if done:
        parts.append(f"완료 {done}{unit}")
    if failed:
        parts.append(f"실패 {failed}{unit}")
    if stopped:
        parts.append(f"중단 {stopped}{unit}")

    if not parts:
        return "처리한 항목이 없습니다.", False

    all_ok = bool(done) and not failed and not stopped
    if total is not None and done != total:
        # 예외로 루프가 중간에 끊기면 집계가 total 에 못 미친다.
        # 그때 성공으로 보고하면 사용자가 받지 못한 곡을 받았다고 믿는다.
        all_ok = False
    return " · ".join(parts), all_ok


def describe_batch_detail(done, failed, stopped):
    """배치 결과의 보조 설명. 실패가 없으면 사유 안내를 하지 않는다."""
    if failed:
        return "실패한 항목의 사유는 대기열 목록에서 확인할 수 있습니다."
    if stopped:
        return "사용자가 다운로드를 중단했습니다."
    return ""


def batch_progress_value(done, failed, stopped):
    """전체 진행 바에 채울 값. 성공한 만큼만 채운다.

    실패·중단인데 100% 로 채우면 진행 바 자체가 거짓 보고가 된다.
    """
    total = done + failed + stopped
    if total <= 0:
        return 0.0
    return done / total


def measure_error_dialog(message):
    """메시지 길이에 맞는 알림창 크기를 계산한다. (너비, 높이)

    고정 380x180 이면 실패 사유처럼 긴 문구에서 본문이 잘리고
    '확인' 버튼이 창 밖으로 밀려 사용자가 창을 닫지 못한다.
    """
    text = message or ""
    raw_lines = text.split(chr(10))
    longest = max((len(line) for line in raw_lines), default=0)

    # 가장 긴 줄에 맞춰 너비를 잡되 상한을 둔다
    width = min(DIALOG_MAX_WIDTH, max(DIALOG_MIN_WIDTH, longest * DIALOG_CHAR_PX + 80))

    per_line = max(1, (width - 80) // DIALOG_CHAR_PX)
    lines = sum(max(1, -(-len(line) // per_line)) for line in raw_lines)
    height = DIALOG_CHROME_PX + lines * DIALOG_LINE_PX
    return width, max(DIALOG_MIN_HEIGHT, min(height, DIALOG_MAX_HEIGHT))


def merge_error_messages(existing, new_message):
    """이미 떠 있는 알림창에 새 메시지를 덧붙인다.

    알림창을 새로 띄우면 Tk 의 grab 이 앞 창에서 넘어가 모달이 무너지고
    창이 계속 쌓인다. 하나만 유지하고 내용을 합친다.
    """
    old = (existing or "").strip()
    new = (new_message or "").strip()
    if not old:
        return new
    if not new or new in old:
        return old
    return old + BR + BR + ("-" * 20) + BR + BR + new


def describe_postprocess_stage(format_type):
    """후처리 단계 문구. MP4 는 오디오 변환이 아니라 영상 병합이다."""
    if format_type == 'MP4':
        return "영상 병합 중 (FFmpeg)..."
    return "음원 변환 중 (FFmpeg)..."


UNKNOWN_TIME = "--:--"


BR = chr(10)  # 대화상자 줄바꿈


SEARCH_TIMEOUT_MS = 60000  # 응답이 이 시간을 넘기면 검색 잠금을 풀어 준다


SEARCH_INITIAL_TEXT = "검색 결과가 없습니다. 키워드를 입력하고 검색해 주세요."


SEARCH_NO_RESULT_TEXT = "일치하는 영상을 찾지 못했습니다. 다른 키워드로 검색해 보세요."
