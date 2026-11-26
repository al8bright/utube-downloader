"""웹 화면(Tauri 웹뷰)이 쓰는 로컬 HTTP/WebSocket API.

보안(127.0.0.1 전용, Host 검사, 실행마다 바뀌는 토큰)은 공통 파일 `api/base.py` 가 맡는다.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from utube import __version__
from utube.api import base
from utube.config import Format, Quality, Sidebar
from utube.core.proc import open_with_shell
from utube.core.service import Service, ServiceError
from utube.core.storage import resolve_save_dir
from utube.core.urls import is_openable
from utube.core.ytdl import detect_js_runtimes, ffmpeg_path, ytdlp_version

PUSH_INTERVAL = 0.1  # 초. 진행률은 이보다 자주 바뀌어도 화면에는 이 간격으로 보낸다


class QueryBody(BaseModel):
    query: str


class IdsBody(BaseModel):
    ids: list[str]


class StartBody(BaseModel):
    ids: list[str] | None = None  # None 이면 받을 수 있는 곡 전부


class UrlBody(BaseModel):
    url: str


class NameBody(BaseModel):
    name: str


class KindBody(BaseModel):
    kind: Literal["audio", "video"]


class SettingsPatch(BaseModel):
    save_dir: str | None = None
    format: Format | None = None
    quality: Quality | None = None
    hide_queued: bool | None = None
    sidebar: Sidebar | None = None


def create_app(service: Service | None = None, token: str | None = None) -> FastAPI:
    token = base.env_token(token)
    svc = service or Service()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await asyncio.to_thread(svc.startup_cleanup)
        yield
        svc.shutdown()

    app = FastAPI(title="utube", version=__version__, lifespan=lifespan)
    app.state.service = svc
    base.secure(app, token)

    @app.exception_handler(ServiceError)
    async def service_error(_request: Request, exc: ServiceError):
        return JSONResponse({"detail": str(exc)}, status_code=exc.status)

    # -------------------------------------------------------------- 상태
    @app.get("/system")
    def system():
        return {"version": __version__, "yt_dlp": ytdlp_version(), "ffmpeg": ffmpeg_path(),
                "js_runtimes": list(detect_js_runtimes())}

    @app.get("/state")
    def state():
        return svc.snapshot()

    @app.websocket("/events")
    async def events(ws: WebSocket):
        if not await base.ws_allowed(ws, token):
            return
        await ws.accept()
        sent_state = sent_search = -1
        try:
            while True:
                # 버전만 보고 바뀐 것만 보낸다. 진행률이 초당 수십 번 바뀌어도 화면에는 10번까지만 간다
                if svc.version != sent_state:
                    snap = svc.snapshot()
                    await ws.send_json({"type": "state", **snap})
                    sent_state = snap["version"]
                if svc.search_version != sent_search:
                    s = svc.search_snapshot()
                    await ws.send_json({"type": "search", **s})
                    sent_search = s["version"]
                await asyncio.sleep(PUSH_INTERVAL)
        except (WebSocketDisconnect, RuntimeError):
            pass

    # -------------------------------------------------------------- 검색
    @app.get("/search")
    def get_search():
        return svc.search_snapshot()

    @app.post("/search")
    def post_search(body: QueryBody):
        return svc.submit_query(body.query)

    # -------------------------------------------------------------- 대기열
    @app.post("/queue/results")
    def add_results(body: IdsBody):
        return svc.add_results(body.ids)

    @app.post("/queue/url")
    def add_url(body: UrlBody):
        return svc.add_url(body.url)

    @app.delete("/queue/{item_id}")
    def remove_item(item_id: str):
        svc.remove(item_id)
        return {"ok": True}

    @app.post("/queue/clear")
    def clear_queue():
        svc.clear()
        return {"ok": True}

    @app.post("/queue/clear-finished")
    def clear_finished():
        return {"removed": svc.clear_finished()}

    @app.post("/batch/start")
    def start_batch(body: StartBody):
        return svc.start(body.ids)

    @app.post("/batch/stop")
    def stop_batch():
        return {"ok": svc.stop()}

    # -------------------------------------------------------------- 설정
    @app.put("/settings")
    def put_settings(body: SettingsPatch):
        return svc.update_settings(body.model_dump(exclude_none=True))

    # -------------------------------------------------------------- 받은 파일
    @app.get("/files")
    def files():
        return svc.files()

    @app.post("/files/delete")
    def delete_file(body: NameBody):
        svc.delete_file(body.name)
        return {"ok": True}

    @app.post("/files/delete-kind")
    def delete_kind(body: KindBody):
        return svc.delete_kind(body.kind)

    # -------------------------------------------------------------- 열기
    def _open(target: str) -> dict:
        try:
            open_with_shell(target)
        except OSError as e:
            raise HTTPException(500, f"열지 못했습니다.\n\n{e.strerror or e}") from e
        return {"ok": True}

    @app.post("/open/file")
    def open_file(body: NameBody):
        return _open(svc.file_path(body.name))

    @app.post("/open/folder")
    def open_folder():
        save_dir, ok = resolve_save_dir(svc.settings.get().save_dir)
        if not ok:
            raise HTTPException(404, "저장 폴더를 찾을 수 없습니다.")
        return _open(save_dir)

    @app.post("/open/url")
    def open_url(body: UrlBody):
        if not is_openable(body.url):
            raise HTTPException(400, "유튜브 주소만 열 수 있습니다.")
        return _open(body.url.strip())

    return app
