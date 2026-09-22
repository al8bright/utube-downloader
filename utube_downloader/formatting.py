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


# --------------------------------------------------------------------------
# 대기열 요약·필터
# --------------------------------------------------------------------------
QUEUE_FILTERS = ("전체", "대기", "완료", "문제")


def queue_bucket(item):
    """대기열 항목을 필터 칩 분류로 나눈다.

    중단된 곡은 다시 받을 수 있으므로 '대기' 로 센다.
    재생목록처럼 막힌 항목은 status 가 failed 가 아니어도 '문제' 다.
    """
    status = item.get('status')
    if item.get('blocked') or status == 'failed':
        return "문제"
    if status == 'finished':
        return "완료"
    if status in ('waiting', 'stopped'):
        return "대기"
    return "진행"


def summarize_queue(items):
    """분류별 개수. 없는 분류도 0 으로 담아 화면이 키를 찾다 죽지 않게 한다."""
    counts = {"대기": 0, "진행": 0, "완료": 0, "문제": 0}
    for item in items:
        counts[queue_bucket(item)] += 1
    counts["전체"] = len(items)
    return counts


def describe_queue_summary(items, unit="곡"):
    """제목 옆 요약 문구. 0 인 분류는 적지 않는다."""
    counts = summarize_queue(items)
    if not counts["전체"]:
        return "비어 있음"
    parts = [f"{counts['전체']}{unit}"]
    for key, label in (("대기", "대기"), ("진행", "받는 중"), ("완료", "완료"), ("문제", "문제")):
        if counts[key]:
            parts.append(f"{label} {counts[key]}")
    return " · ".join(parts)


def filter_queue_indices(items, bucket):
    """필터 칩에 해당하는 항목의 원래 인덱스. 제거 버튼이 원래 인덱스를 써야 한다."""
    if bucket in (None, "전체"):
        return list(range(len(items)))
    return [i for i, item in enumerate(items) if queue_bucket(item) == bucket]


def describe_queue_status(item):
    """대기열 항목의 상태 문구와 보조 사유. (문구, 사유 또는 None)"""
    status = item.get('status')
    if item.get('blocked'):
        return "받지 않음", item.get('error')
    if status == 'failed':
        return "실패", item.get('error')
    return {
        'waiting': "대기 중",
        'analyzing': "분석 중…",
        'downloading': "다운로드 중",
        'converting': "변환 중…",
        'finished': "완료",
        'stopped': "사용자 중단",
    }.get(status, "대기 중"), None


# --------------------------------------------------------------------------
# 받은 파일 목록
# --------------------------------------------------------------------------
FILE_SORTS = {"최근 받은 순": "recent", "이름 순": "name", "크기 순": "size"}


def format_size(num_bytes):
    """파일 크기를 짧게. 100 이상이면 소수점을 버려 열 폭을 일정하게 한다."""
    try:
        size = float(num_bytes)
    except (TypeError, ValueError):
        return "-"
    if size < 0:
        return "-"
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            if unit == "B":
                return f"{int(size)}B"
            return f"{size:.0f}{unit}" if size >= 100 else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.0f}GB" if size >= 100 else f"{size:.1f}GB"


def format_file_date(timestamp, now=None):
    """받은 날 표시. 오늘·어제는 시각까지, 올해는 월·일, 그 전은 연도까지."""
    import datetime

    try:
        when = datetime.datetime.fromtimestamp(float(timestamp))
    except (TypeError, ValueError, OverflowError, OSError):
        return "-"
    now = now or datetime.datetime.now()
    days = (now.date() - when.date()).days
    if days == 0:
        return f"오늘 {when:%H:%M}"
    if days == 1:
        return f"어제 {when:%H:%M}"
    if when.year == now.year:
        return f"{when.month}월 {when.day}일"
    return f"{when.year}. {when.month}. {when.day}."


def filter_sort_files(entries, query="", ext=None, sort="recent"):
    """파일 목록을 이름·형식으로 거르고 정렬한다.

    entries 는 {'name', 'ext', 'size', 'mtime'} 사전의 목록이다.
    ext 는 'MP3' 처럼 대문자이고, None 이나 '전체' 면 거르지 않는다.
    """
    needle = (query or "").strip().lower()
    picked = [
        e for e in entries
        if (not needle or needle in e['name'].lower())
        and (ext in (None, "전체") or e['ext'] == ext)
    ]
    if sort == "name":
        picked.sort(key=lambda e: e['name'].lower())
    elif sort == "size":
        picked.sort(key=lambda e: e['size'], reverse=True)
    else:
        picked.sort(key=lambda e: e['mtime'], reverse=True)
    return picked


# --------------------------------------------------------------------------
# 검색 결과
# --------------------------------------------------------------------------
SEARCH_LIMIT = 100        # 한 번에 찾는 최대 개수
SEARCH_BATCH = 20         # 이만큼 모이면 바로 화면에 붙인다 (유튜브 한 페이지 분량)


SEARCH_LOADING_TEXT = "유튜브에서 찾는 중…"


def search_result_from_entry(entry):
    """검색 결과 한 건을 화면용 사전으로 바꾼다. 영상이 아니면 None.

    유튜브 검색에는 채널·재생목록도 섞여 나온다. 그대로 담으면
    대기열에서 '재생목록은 받을 수 없음' 으로 막히므로 여기서 거른다.
    """
    video_id = entry.get('id') or ''
    ie_key = entry.get('ie_key')
    if (ie_key and ie_key != 'Youtube') or len(video_id) != 11:
        return None
    url = entry.get('url') or ''
    if 'watch?' not in url and '/shorts/' not in url:
        url = f"https://www.youtube.com/watch?v={video_id}"
    return {
        'title': entry.get('title') or 'Unknown Title',
        'url': url,
        'duration': format_duration(entry.get('duration')),
        'uploader': entry.get('uploader') or entry.get('channel') or 'Unknown',
        # hqdefault 는 4:3 에 위아래 검은 띠가 든 이미지라 16:9 칸에서 찌그러진다.
        # mqdefault 는 320x180 원본 16:9 라 자르지 않아도 맞고 용량도 작다.
        'thumbnail': f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg",
    }


def display_text(text):
    """화면에 그릴 글자만 남긴다. 데이터(파일 이름·링크)는 바꾸지 않는다.

    Tk 8.6 은 이모지를 그리지 못해 빈 네모로 나오고, 맑은 고딕에 없는 글자를 처음 만나면
    시스템 글꼴을 전부 뒤져 제목 하나에 0.3초씩 멈췄다.
    - '𝑷𝒍𝒂𝒚' 같은 장식용 수학 글자는 NFKC 로 'Play' 가 된다
    - 이모지처럼 기본 다국어 평면(U+FFFF) 밖의 글자와 이모지 결합 문자는 뺀다
    """
    import unicodedata

    if not text:
        return text or ""
    normalized = unicodedata.normalize("NFKC", text)
    kept = "".join(
        ch for ch in normalized
        if ord(ch) <= 0xFFFF and ch not in "\u200d\ufe0e\ufe0f"
    )
    # 이모지를 빼고 남은 겹빈칸을 하나로
    return " ".join(kept.split())
