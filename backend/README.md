# utube 백엔드

YouTube Music Downloader 의 Python 백엔드입니다. 검색·대기열·일괄 다운로드·받은 파일 관리를
로컬 HTTP/WebSocket API 로 내보내고, Tauri 앱이 이 프로세스를 띄워 씁니다.

```powershell
uv sync
uv run pytest -q
uv run utube doctor          # yt-dlp, FFmpeg, JS 런타임 확인
uv run utube serve           # http://127.0.0.1:8766 (브라우저 개발용)
```

| 모듈 | 하는 일 |
| :--- | :--- |
| `core/service.py` | 앱 상태와 작업: 검색, 대기열, 일괄 다운로드, 받은 파일 |
| `core/ytdl.py` | yt-dlp 옵션, 검색·분석·다운로드 호출, 오류를 한국어로 |
| `core/storage.py` | 저장 폴더, 임시 폴더, 파일 목록·삭제 |
| `core/urls.py` · `core/text.py` | 링크 해석, 표시 문자열 |
| `core/proc.py` | ffmpeg 자식 프로세스 정리, 부모(Tauri) 감시 |
| `api/server.py` | FastAPI 경로와 WebSocket `/events` |
