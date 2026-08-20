"""유튜브 링크 해석.

링크 형태(단축·타임스탬프·재생목록 파라미터)가 달라도 같은 영상을 알아본다.
"""
import re


# 도메인은 대소문자를 구분하지 않는다. re.I 가 없으면 YouTube.com 같은 링크가
# 중복 검사를 통째로 빠져나가 같은 영상이 두 번 대기열에 들어간다.
# 영상 ID 자체는 대소문자를 구분하므로 캡처 그룹에는 영향이 없다.
# 도메인은 대소문자를 구분하지 않는다. re.I 가 없으면 YouTube.com 같은 링크가
# 중복 검사를 통째로 빠져나가 같은 영상이 두 번 대기열에 들어간다.
# 영상 ID 자체는 대소문자를 구분하므로 캡처 그룹에는 영향이 없다.
#
# 앵커(_HOST)가 없으면 youtube.com.evil.net 같은 사칭 호스트나
# 무관한 사이트의 ?v= 파라미터까지 유튜브 영상으로 오인한다.
# 뒤의 (?![0-9A-Za-z_-]) 는 12자 이상 토큰을 앞 11자로 잘라
# 서로 다른 URL 을 같은 영상으로 착각하는 것을 막는다.
_HOST = r'(?:^|\b)(?:[\w-]+\.)*'


_ID = r'([0-9A-Za-z_-]{11})(?![0-9A-Za-z_-])'


_VIDEO_ID_PATTERNS = (
    re.compile(_HOST + r'(?:youtube\.com|youtube-nocookie\.com)/watch\?(?:.*&)?v=' + _ID, re.I),
    re.compile(_HOST + r'youtu\.be/' + _ID, re.I),
    re.compile(_HOST + r'(?:youtube\.com|youtube-nocookie\.com)/shorts/' + _ID, re.I),
    re.compile(_HOST + r'(?:youtube\.com|youtube-nocookie\.com)/embed/' + _ID, re.I),
    re.compile(_HOST + r'(?:youtube\.com|youtube-nocookie\.com)/live/' + _ID, re.I),
    re.compile(_HOST + r'(?:youtube\.com|youtube-nocookie\.com)/v/' + _ID, re.I),
)


def extract_video_id(url):
    """유튜브 URL 에서 영상 ID 를 뽑는다. 유튜브가 아니면 None."""
    if not url:
        return None
    for pattern in _VIDEO_ID_PATTERNS:
        found = pattern.search(url)
        if found:
            return found.group(1)
    return None


def is_same_video(url_a, url_b):
    """링크 형태(단축/타임스탬프/재생목록 파라미터)가 달라도 같은 영상인지 판정한다."""
    id_a = extract_video_id(url_a)
    id_b = extract_video_id(url_b)
    if id_a and id_b:
        return id_a == id_b
    left = (url_a or '').strip()
    right = (url_b or '').strip()
    if not left or not right:
        # 빈 값끼리 같다고 하면 빈 항목이 서로를 중복으로 막는다
        return False
    return left == right


def is_playlist_info(info):
    """추출 결과가 재생목록/채널인지 판정한다.

    noplaylist 는 watch?v=...&list=... 에서 list 를 떼어낼 뿐,
    순수 재생목록 URL 에는 효력이 없어 항목 1개가 수백 개를 받게 된다.
    """
    if not info:
        return False
    return info.get('_type') in ('playlist', 'multi_video')
