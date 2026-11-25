"""화면에 보일 문자열과 수치. 계산과 문구 생성만 한다."""

from __future__ import annotations

UNKNOWN_TIME = "--:--"


def format_duration(seconds) -> str:
    """초를 mm:ss 또는 hh:mm:ss 로 바꾼다.

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


def format_eta(seconds) -> str:
    """남은 시간(초)을 mm:ss 로. yt-dlp 는 eta 를 float 으로 주기도 한다."""
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return UNKNOWN_TIME
    if total < 0:
        return UNKNOWN_TIME
    mins, secs = divmod(total, 60)
    return f"{mins:02d}:{secs:02d}"


def format_speed(bytes_per_sec) -> str:
    try:
        speed = float(bytes_per_sec)
    except (TypeError, ValueError):
        return ""
    if speed <= 0:
        return ""
    if speed > 1024 * 1024:
        return f"{speed / (1024 * 1024):.2f} MB/s"
    return f"{speed / 1024:.2f} KB/s"


def unit_for(format_type: str) -> str:
    """MP4 는 '곡' 이 아니라 '편' 이다."""
    return "편" if format_type == "MP4" else "곡"


def describe_batch_result(done: int, failed: int, stopped: int, total: int | None = None,
                          unit: str = "곡") -> tuple[str, bool]:
    """배치 결과 문구와 '전부 성공인가' 여부.

    전량 실패인데 '완료' 로 보고하던 문제를 막기 위해 성공 여부를 문구와 함께 돌려준다.
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


def describe_batch_detail(done: int, failed: int, stopped: int) -> str:
    """배치 결과의 보조 설명. 실패가 없으면 사유 안내를 하지 않는다."""
    if failed:
        return "실패한 항목의 사유는 대기열 목록에서 확인할 수 있습니다."
    if stopped:
        return "사용자가 다운로드를 중단했습니다."
    return ""


def batch_progress_value(done: int, failed: int, stopped: int) -> float:
    """전체 진행 바에 채울 값. 성공한 만큼만 채운다. 실패인데 100% 면 진행 바가 거짓말을 한다."""
    total = done + failed + stopped
    if total <= 0:
        return 0.0
    return done / total


def describe_postprocess_stage(format_type: str) -> str:
    """후처리 단계 문구. MP4 는 오디오 변환이 아니라 영상 병합이다."""
    if format_type == "MP4":
        return "영상 병합 중 (FFmpeg)"
    return f"{format_type} 변환 중 (FFmpeg)"


def search_result_from_entry(entry: dict) -> dict | None:
    """검색 결과 한 건을 화면용 사전으로 바꾼다. 영상이 아니면 None.

    유튜브 검색에는 채널·재생목록도 섞여 나온다. 그대로 담으면
    대기열에서 '재생목록은 받을 수 없음' 으로 막히므로 여기서 거른다.
    """
    video_id = entry.get("id") or ""
    ie_key = entry.get("ie_key")
    if (ie_key and ie_key != "Youtube") or len(video_id) != 11:
        return None
    url = entry.get("url") or ""
    if "watch?" not in url and "/shorts/" not in url:
        url = f"https://www.youtube.com/watch?v={video_id}"
    return {
        "id": video_id,
        "title": entry.get("title") or "Unknown Title",
        "url": url,
        "duration": format_duration(entry.get("duration")),
        "uploader": entry.get("uploader") or entry.get("channel") or "Unknown",
        # hqdefault 는 4:3 에 위아래 검은 띠가 든 이미지라 16:9 칸에서 찌그러진다.
        # mqdefault 는 320x180 원본 16:9 라 자르지 않아도 맞고 용량도 작다.
        "thumbnail": f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg",
    }


def thumbnail_for(video_id: str | None) -> str | None:
    return f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg" if video_id else None
