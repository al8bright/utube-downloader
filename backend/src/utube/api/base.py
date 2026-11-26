"""로컬 API 서버의 뼈대. (공통 파일: 네 앱이 같은 내용을 쓴다. docs/STRUCTURE.md)

보안
  - 127.0.0.1에만 묶는다.
  - Host 헤더가 127.0.0.1/localhost가 아니면 거절한다(DNS 리바인딩 차단).
  - `<ENV>_TOKEN`이 있으면(Tauri가 실행마다 임의 값을 넘긴다) 모든 요청이 같은 값을
    `X-<Name>-Token` 헤더로, WebSocket은 `?token=`으로 보내야 한다. `/health`만 예외다.
앱마다 다른 값(이름, 포트)은 `app_info.py`에서 읽는다.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .. import __version__, app_info

ALLOWED_HOSTS = {"127.0.0.1", "localhost", "testserver"}
TOKEN_HEADER = f"x-{app_info.NAME}-token"


def allowed_origins() -> list[str]:
    return [
        f"http://localhost:{app_info.VITE_PORT}", f"http://127.0.0.1:{app_info.VITE_PORT}",  # Vite 개발 서버
        "tauri://localhost", "http://tauri.localhost", "https://tauri.localhost",  # Tauri 웹뷰
    ]


def env_token(token: str | None = None) -> str | None:
    """create_app(token=...)에 넘긴 값, 없으면 환경 변수. 빈 문자열은 토큰 검사를 끈다(테스트)."""
    return token if token is not None else os.environ.get(f"{app_info.ENV}_TOKEN") or None


def secure(app: FastAPI, token: str | None) -> None:
    """CORS, Host·토큰 검사, `/health`를 붙인다. create_app이 앱을 만든 직후에 부른다."""
    app.add_middleware(CORSMiddleware, allow_origins=allowed_origins(), allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def guard(request: Request, call_next):
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
        if host not in ALLOWED_HOSTS:
            return JSONResponse({"detail": "forbidden host"}, status_code=403)
        if token and request.method != "OPTIONS" and request.url.path != "/health":
            if request.headers.get(TOKEN_HEADER) != token:
                return JSONResponse({"detail": "bad token"}, status_code=401)
        return await call_next(request)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": __version__}


async def ws_allowed(ws: WebSocket, token: str | None) -> bool:
    """WebSocket은 미들웨어를 거치지 않으므로 직접 본다. 틀리면 4401로 닫고 False."""
    host = (ws.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
    if host not in ALLOWED_HOSTS or (token and ws.query_params.get("token") != token):
        await ws.close(code=4401)
        return False
    return True


def add_serve_command(sub) -> None:
    """argparse 하위 명령 `serve`를 붙인다."""
    s = sub.add_parser("serve", help="run the local API server")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=app_info.PORT, help="0 picks a free port")
    s.add_argument("--parent-pid", type=int, help="exit when this process exits (Tauri)")
    s.set_defaults(fn=lambda a: serve(a.host, a.port, a.parent_pid) or 0)


def serve(host: str = "127.0.0.1", port: int = app_info.PORT, parent_pid: int | None = None,
          create_app: Callable[[], FastAPI] | None = None) -> None:
    """서버를 띄운다. 준비되면 `<ENV>_LISTENING <주소>` 한 줄을 표준 출력에 쓴다(Tauri가 읽는다)."""
    import uvicorn

    from ..core.proc import bind_self_to_job, exit_when_parent_dies, free_port

    if host not in ("127.0.0.1", "localhost"):
        raise SystemExit("refusing to bind to a non-loopback address")
    if create_app is None:
        from .server import create_app
    # 앱이 어떻게 끝나든(강제 종료 포함) 이 프로세스가 띄운 프로세스가 남지 않게 한다
    bind_self_to_job()
    if parent_pid:
        exit_when_parent_dies(parent_pid)
    if port == 0:
        port = free_port()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"{app_info.ENV}_LISTENING http://{host}:{port}", flush=True)
    # SIGTERM(macOS 앱 종료)을 받으면 열린 WebSocket을 2초까지만 기다린다. 앱은 3초 뒤 강제 종료한다
    uvicorn.run(create_app(), host=host, port=port, log_level="warning", timeout_graceful_shutdown=2)
