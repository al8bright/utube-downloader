"""공통 파일(api/base.py, core/proc.py)의 테스트. (공통 파일: 네 앱이 같은 내용을 쓴다. docs/STRUCTURE.md)

패키지 이름은 src 아래에서 app_info.py가 있는 폴더로 찾는다.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

SRC = Path(__file__).resolve().parents[1] / "src"
PKG = next(p.name for p in SRC.iterdir() if (p / "app_info.py").exists())
app_info = importlib.import_module(f"{PKG}.app_info")
base = importlib.import_module(f"{PKG}.api.base")
proc = importlib.import_module(f"{PKG}.core.proc")


def small_app(token: str | None) -> FastAPI:
    app = FastAPI()
    base.secure(app, token)

    @app.get("/ping")
    def ping():
        return {"pong": True}

    @app.websocket("/ws")
    async def ws(sock: WebSocket):
        if not await base.ws_allowed(sock, token):
            return
        await sock.accept()
        await sock.send_json({"hello": True})
        await sock.close()

    return app


def test_app_info_values():
    assert app_info.NAME == PKG and app_info.ENV == PKG.upper()
    assert 1024 < app_info.PORT < 65536 and 1024 < app_info.VITE_PORT < 65536


def test_health_is_open_and_the_rest_needs_the_token():
    c = TestClient(small_app("s3cret"))
    assert c.get("/health").json()["status"] == "ok"
    assert c.get("/ping").status_code == 401
    assert c.get("/ping", headers={base.TOKEN_HEADER: "wrong"}).status_code == 401
    assert c.get("/ping", headers={base.TOKEN_HEADER: "s3cret"}).json() == {"pong": True}


def test_foreign_host_is_refused():
    c = TestClient(small_app(None))
    assert c.get("/ping").status_code == 200
    assert c.get("/ping", headers={"host": "evil.example"}).status_code == 403
    assert c.get("/ping", headers={"host": "127.0.0.1:8000"}).status_code == 200


def test_cors_allows_only_the_app_and_the_dev_server():
    c = TestClient(small_app(None))
    dev = f"http://localhost:{app_info.VITE_PORT}"
    ok = c.options("/ping", headers={"origin": dev, "access-control-request-method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == dev
    bad = c.options("/ping", headers={"origin": "https://evil.example", "access-control-request-method": "GET"})
    assert "access-control-allow-origin" not in bad.headers


def test_websocket_needs_the_token():
    c = TestClient(small_app("s3cret"))
    with c.websocket_connect("/ws?token=s3cret") as ws:
        assert ws.receive_json() == {"hello": True}
    with pytest.raises(WebSocketDisconnect) as e, c.websocket_connect("/ws?token=wrong") as ws:
        ws.receive_json()
    assert e.value.code == 4401


def test_env_token(monkeypatch):
    monkeypatch.setenv(f"{app_info.ENV}_TOKEN", "from-env")
    assert base.env_token() == "from-env"
    assert base.env_token("given") == "given"
    assert base.env_token("") == ""  # tests turn the check off this way


def test_serve_refuses_other_addresses():
    with pytest.raises(SystemExit):
        base.serve(host="0.0.0.0", create_app=FastAPI)


def test_serve_command_defaults():
    import argparse

    p = argparse.ArgumentParser()
    base.add_serve_command(p.add_subparsers(dest="cmd"))
    a = p.parse_args(["serve"])
    assert (a.host, a.port, a.parent_pid) == ("127.0.0.1", app_info.PORT, None)
    assert p.parse_args(["serve", "--port", "0", "--parent-pid", "42"]).parent_pid == 42


def test_ffmpeg_tree_takes_shims_and_their_children():
    procs = [
        (10, 1, "python.exe"),  # us
        (20, 10, "ffmpeg.exe"),  # shim we started
        (21, 20, "ffmpeg.exe"),  # the real ffmpeg the shim started
        (22, 21, "conhost.exe"),
        (30, 10, "llama-server.exe"),  # not ffmpeg: left alone
        (40, 99, "ffmpeg.exe"),  # someone else's
    ]
    got = proc.ffmpeg_tree(procs, 10)
    assert set(got) == {20, 21, 22} and got.index(22) < got.index(21) < got.index(20)


def test_bound_child_is_killed_by_kill_children():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        proc.bind_to_lifetime(child)
        proc.kill_children()
        t = time.time()
        while child.poll() is None and time.time() - t < 5:
            time.sleep(0.05)
        assert child.poll() is not None
    finally:
        if child.poll() is None:
            child.kill()
        child.wait()


def _alive(pid: int) -> bool:
    """Windows: 프로세스가 아직 도는지(os.kill(pid, 0)은 Windows에서 프로세스를 끝내 버린다)."""
    import ctypes

    k32 = ctypes.WinDLL("kernel32")
    k32.OpenProcess.restype = ctypes.c_void_p
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong()
    k32.GetExitCodeProcess(ctypes.c_void_p(h), ctypes.byref(code))
    k32.CloseHandle(ctypes.c_void_p(h))
    return code.value == 259  # STILL_ACTIVE


@pytest.mark.skipif(sys.platform != "win32", reason="Job Object is Windows only")
def test_children_die_with_a_bound_parent():
    """bind_self_to_job를 부른 프로세스가 강제로 죽으면 그 자식도 함께 끝난다."""
    code = (
        "import subprocess, sys, time\n"
        f"sys.path.insert(0, {str(SRC)!r})\n"
        f"from {PKG}.core import proc\n"
        "assert proc.bind_self_to_job()\n"
        "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "print(c.pid, flush=True)\n"
        "time.sleep(60)\n"
    )
    parent = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    child = None
    try:
        child = int(parent.stdout.readline())
        assert _alive(child)
        parent.kill()
        parent.wait()
        t = time.time()
        while _alive(child) and time.time() - t < 5:
            time.sleep(0.05)
        assert not _alive(child)
    finally:
        if parent.poll() is None:
            parent.kill()
        if child and _alive(child):
            subprocess.run(["taskkill", "/F", "/PID", str(child)], capture_output=True)
