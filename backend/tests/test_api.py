"""HTTP API: 보안 장치와 주요 경로."""

import pytest
from conftest import entry
from fastapi.testclient import TestClient

from utube.api.server import create_app

TOKEN = "t0ken"


@pytest.fixture
def client(svc):
    with TestClient(create_app(svc, token=TOKEN), headers={"x-utube-token": TOKEN}) as c:
        yield c


class TestGuard:
    def test_토큰이_없으면_거절한다(self, svc):
        with TestClient(create_app(svc, token=TOKEN)) as c:
            assert c.get("/state").status_code == 401
            assert c.get("/health").status_code == 200, "연결 확인은 토큰 없이 된다"

    def test_다른_호스트는_거절한다(self, client):
        assert client.get("/state", headers={"host": "evil.example"}).status_code == 403

    def test_웹소켓도_토큰을_요구한다(self, svc):
        from starlette.websockets import WebSocketDisconnect

        with TestClient(create_app(svc, token=TOKEN)) as c:
            with pytest.raises(WebSocketDisconnect):
                with c.websocket_connect("/events") as ws:
                    ws.receive_json()

    def test_유튜브가_아닌_주소는_열지_않는다(self, client):
        assert client.post("/open/url", json={"url": "file:///C:/Windows/notepad.exe"}).status_code == 400


class TestFlow:
    def test_검색_담기_받기(self, client, ytdl):
        ytdl.search_entries = [entry("n61ULEU7CO0", title="밤편지")]
        assert client.post("/search", json={"query": "아이유"}).json() == {"generation": 1}
        s = client.get("/search").json()
        assert s["status"] == "done" and s["results"][0]["title"] == "밤편지"

        assert client.post("/queue/results", json={"ids": ["n61ULEU7CO0"]}).json()["added"] == 1
        assert client.post("/batch/start", json={}).json() == {"count": 1}
        state = client.get("/state").json()
        assert state["items"][0]["status"] == "finished"
        assert state["batch"]["result"]["message"] == "완료 1곡"

    def test_오류는_한국어_문구와_상태_코드로(self, client):
        r = client.post("/batch/start", json={})
        assert r.status_code == 400 and "1개 이상" in r.json()["detail"]

    def test_이벤트로_상태와_검색을_밀어준다(self, client):
        with client.websocket_connect(f"/events?token={TOKEN}") as ws:
            kinds = {ws.receive_json()["type"], ws.receive_json()["type"]}
        assert kinds == {"state", "search"}

    def test_설정_변경(self, client, tmp_path):
        r = client.put("/settings", json={"format": "FLAC"})
        assert r.status_code == 200 and r.json()["format"] == "FLAC"
        assert client.put("/settings", json={"format": "OGG"}).status_code == 422
        assert client.put("/settings", json={"save_dir": str(tmp_path / "없음")}).status_code == 400
