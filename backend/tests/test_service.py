"""Service: 검색, 대기열, 일괄 다운로드, 받은 파일."""

import os

import pytest
from conftest import entry

from utube.core.service import Aborted, ServiceError

VID_A, VID_B, VID_C = "n61ULEU7CO0", "aqz-KE-bpKQ", "AbCdEfGhIjK"


def url(vid):
    return f"https://www.youtube.com/watch?v={vid}"


def searched(svc, ytdl, *vids):
    ytdl.search_entries = [entry(v, title=f"곡 {v}") for v in vids]
    svc.submit_query("아이유")
    return [r["id"] for r in svc.search.results]


def queued(svc, ytdl, *vids):
    svc.add_results(searched(svc, ytdl, *vids))
    return [i.id for i in svc.items]


# ---------------------------------------------------------------------- 검색
class TestSearch:
    def test_결과를_모으고_끝나면_done(self, svc, ytdl):
        ids = searched(svc, ytdl, VID_A, VID_B)
        assert ids == [VID_A, VID_B]
        assert svc.search.status == "done"

    def test_채널과_중복은_거른다(self, svc, ytdl):
        ytdl.search_entries = [entry(VID_A), {"id": "UCxxxxxxxxxxxxxxxxxxxxxx", "ie_key": "YoutubeTab"}, entry(VID_A)]
        svc.submit_query("x")
        assert [r["id"] for r in svc.search.results] == [VID_A]

    def test_빈_검색어는_거절한다(self, svc):
        with pytest.raises(ServiceError, match="키워드"):
            svc.submit_query("   ")

    def test_링크를_넣으면_검색하지_않고_대기열에_담는다(self, svc):
        out = svc.submit_query(url(VID_A))
        assert "queued" in out
        assert svc.search.status == "idle"
        assert svc.items[0].status == "waiting" and svc.items[0].title == "분석된 곡"

    def test_실패하면_사유와_받은_결과를_남긴다(self, svc, ytdl):
        ytdl.search_entries = [entry(VID_A)]
        ytdl.search_error = RuntimeError("timed out")
        svc.submit_query("x")
        assert svc.search.status == "failed"
        assert "네트워크" in svc.search.error
        assert [r["id"] for r in svc.search.results] == [VID_A]

    def test_새_검색이_시작되면_옛_검색_결과는_버린다(self, svc, ytdl):
        spawned = []
        svc.spawn = lambda fn, *a: spawned.append((fn, a))
        ytdl.search_entries = [entry(VID_A)]
        svc.submit_query("옛 검색")
        svc.submit_query("새 검색")
        old, new = spawned
        old[0](*old[1])  # 늦게 끝난 옛 검색
        assert svc.search.results == [] and svc.search.status == "running"
        new[0](*new[1])
        assert svc.search.query == "새 검색" and svc.search.status == "done"


# ---------------------------------------------------------------------- 담기
class TestAddResults:
    def test_고른_결과만_담는다(self, svc, ytdl):
        searched(svc, ytdl, VID_A, VID_B)
        out = svc.add_results([VID_B])
        assert out["added"] == 1 and out["message"] is None
        assert [i.video_id for i in svc.items] == [VID_B]

    def test_아무것도_고르지_않으면_안내한다(self, svc):
        with pytest.raises(ServiceError, match="1개 이상"):
            svc.add_results([])

    def test_전부_이미_있으면_안내한다(self, svc, ytdl):
        queued(svc, ytdl, VID_A)
        out = svc.add_results([VID_A])
        assert out["added"] == 0 and "모두 이미" in out["message"]

    def test_링크_형태가_달라도_중복으로_잡는다(self, svc, ytdl):
        svc.add_url(f"https://youtu.be/{VID_A}?t=3")
        searched(svc, ytdl, VID_A)
        assert svc.add_results([VID_A])["added"] == 0

    def test_받는_중에_담으면_이번_배치에_없다고_알린다(self, svc, ytdl):
        searched(svc, ytdl, VID_A)
        svc.batch.running = True
        out = svc.add_results([VID_A])
        assert "이번 배치에는 포함되지 않습니다" in out["message"]
        assert svc.batch.added_during == 1


class TestAddUrl:
    def test_같은_링크는_두번_담지_않는다(self, svc):
        svc.add_url(url(VID_A))
        with pytest.raises(ServiceError, match="이미 대기열"):
            svc.add_url(f"https://youtu.be/{VID_A}")

    def test_재생목록은_막고_알린다(self, svc, ytdl):
        pl = "https://www.youtube.com/playlist?list=PL123"
        ytdl.infos[pl] = {"_type": "playlist", "title": "믹스", "entries": [{}, {}, {}]}
        svc.add_url(pl)
        item = svc.items[0]
        assert item.blocked and item.status == "failed" and "영상 3개" in item.error
        assert "재생목록" in svc.notices[-1]["text"]

    def test_분석_실패는_사유를_남긴다(self, svc, ytdl):
        ytdl.infos[url(VID_B)] = RuntimeError("ERROR: Private video")
        svc.add_url(url(VID_B))
        assert svc.items[0].status == "failed" and "비공개" in svc.items[0].error

    def test_분석_중에_지운_항목은_되살리지_않는다(self, svc):
        spawned = []
        svc.spawn = lambda fn, *a: spawned.append((fn, a))
        svc.add_url(url(VID_A))
        svc.clear()
        fn, a = spawned[0]
        fn(*a)
        assert svc.items == []

    def test_스킴이_없으면_https_를_붙인다(self, svc):
        svc.add_url(f"youtu.be/{VID_A}")
        assert svc.items[0].url == f"https://youtu.be/{VID_A}"


# ---------------------------------------------------------------------- 정리
class TestQueueEdits:
    def test_받는_중에는_고칠_수_없다(self, svc, ytdl):
        ids = queued(svc, ytdl, VID_A)
        svc.batch.running = True
        for call in (lambda: svc.remove(ids[0]), svc.clear, svc.clear_finished):
            with pytest.raises(ServiceError):
                call()
        assert len(svc.items) == 1

    def test_완료_항목만_정리한다(self, svc, ytdl):
        queued(svc, ytdl, VID_A, VID_B)
        svc.items[0].status = "finished"
        assert svc.clear_finished() == 1
        assert [i.video_id for i in svc.items] == [VID_B]

    def test_완료_항목이_없으면_안내한다(self, svc, ytdl):
        queued(svc, ytdl, VID_A)
        with pytest.raises(ServiceError, match="완료 상태"):
            svc.clear_finished()

    def test_비우면_지난_결과도_지운다(self, svc, ytdl):
        queued(svc, ytdl, VID_A)
        svc.start(None)
        assert svc.batch.result
        svc.clear()
        assert svc.batch.result is None


# ---------------------------------------------------------------------- 일괄 다운로드
class TestBatch:
    def test_정상_완료(self, svc, ytdl, save_dir):
        queued(svc, ytdl, VID_A, VID_B)
        assert svc.start(None) == {"count": 2}
        assert [i.status for i in svc.items] == ["finished", "finished"]
        r = svc.batch.result
        assert svc.batch.running is False and r["all_ok"] and r["message"] == "완료 2곡"
        assert ytdl.downloads[0][1]["paths"]["home"] == str(save_dir)

    def test_고른_곡만_받는다(self, svc, ytdl):
        ids = queued(svc, ytdl, VID_A, VID_B)
        svc.start([ids[1]])
        assert [i.status for i in svc.items] == ["waiting", "finished"]

    def test_실패는_사유를_남기고_다음_곡으로_간다(self, svc, ytdl):
        queued(svc, ytdl, VID_A, VID_B)
        ytdl.behaviour[url(VID_A)] = RuntimeError("HTTP Error 403: Forbidden")
        svc.start(None)
        a, b = svc.items
        assert a.status == "failed" and "403" in a.error
        assert b.status == "finished"
        assert svc.batch.result["all_ok"] is False and svc.batch.result["progress"] == 0.5

    def test_예기치_못한_예외에도_running_이_풀린다(self, svc, ytdl, monkeypatch):
        queued(svc, ytdl, VID_A)
        monkeypatch.setattr("utube.core.service.build_ydl_opts", lambda *a: (_ for _ in ()).throw(KeyError("x")))
        with pytest.raises(KeyError):
            svc.start(None)
        assert svc.batch.running is False
        assert svc.items[0].status == "stopped", "'다운로드 중' 으로 굳으면 다시 고를 수 없다"

    def test_중단하면_지금_곡은_중단_나머지는_대기로_남는다(self, svc, ytdl, killed):
        queued(svc, ytdl, VID_A, VID_B)

        def stop_midway(hook, opts):
            svc.stop()
            hook({"status": "downloading", "downloaded_bytes": 1, "total_bytes": 10})

        ytdl.behaviour[url(VID_A)] = stop_midway
        svc.start(None)
        a, b = svc.items
        assert a.status == "stopped" and a.error is None, "사용자가 멈춘 것은 실패가 아니다"
        assert b.status == "waiting"
        assert svc.batch.result["stopped"] == 2 and killed, "변환 중인 ffmpeg 도 끊어야 즉시 멈춘다"

    def test_진행_훅은_중단_요청을_예외로_알린다(self, svc, ytdl):
        queued(svc, ytdl, VID_A)
        seen = []

        def check(hook, opts):
            svc.batch.stop_requested = True
            try:
                hook({"status": "downloading"})
            except Aborted:
                seen.append("aborted")
                raise

        ytdl.behaviour[url(VID_A)] = check
        svc.start(None)
        assert seen == ["aborted"]

    def test_MP4_는_두번째_스트림이_끝나야_변환_단계로_넘어간다(self, svc, ytdl, store):
        svc.update_settings({"format": "MP4"})
        queued(svc, ytdl, VID_A)
        stages = []

        def two_streams(hook, opts):
            hook({"status": "finished"})
            stages.append(svc.batch.stage)
            hook({"status": "downloading", "downloaded_bytes": 5, "total_bytes": 10})
            hook({"status": "finished"})
            stages.append(svc.batch.stage)

        ytdl.behaviour[url(VID_A)] = two_streams
        svc.start(None)
        assert stages == ["analyze", "convert"]
        assert svc.batch.result["message"] == "완료 1편"

    def test_차단된_재생목록은_받지_않는다(self, svc, ytdl):
        queued(svc, ytdl, VID_A)
        svc.items[0].blocked, svc.items[0].status = True, "failed"
        with pytest.raises(ServiceError, match="재생목록"):
            svc.start(None)
        assert svc.batch.running is False

    def test_일반_실패는_다시_받을_수_있다(self, svc, ytdl):
        queued(svc, ytdl, VID_A)
        svc.items[0].status, svc.items[0].error = "failed", "예전 사유"
        svc.start(None)
        assert svc.items[0].status == "finished" and svc.items[0].error is None

    def test_분석_중인_곡만_있으면_기다리라고_한다(self, svc):
        svc.spawn = lambda fn, *a: None
        svc.add_url(url(VID_A))
        with pytest.raises(ServiceError, match="분석"):
            svc.start(None)

    def test_저장_폴더가_없으면_시작하지_않는다(self, svc, ytdl, store, tmp_path):
        queued(svc, ytdl, VID_A)
        v = store.get()
        v.save_dir = str(tmp_path / "사라진폴더")
        store.save(v)
        with pytest.raises(ServiceError, match="저장 폴더"):
            svc.start(None)
        assert svc.batch.running is False and ytdl.downloads == []

    def test_이미_받는_중이면_거절한다(self, svc):
        svc.batch.running = True
        with pytest.raises(ServiceError, match="이미"):
            svc.start(None)

    def test_끝나면_임시_폴더를_치우고_받는_중_추가분을_알린다(self, svc, ytdl, save_dir):
        queued(svc, ytdl, VID_A)
        searched(svc, ytdl, VID_B)

        def add_during(hook, opts):
            (save_dir / ".utube_tmp").mkdir()
            svc.add_results([VID_B])
            hook({"status": "finished"})

        ytdl.behaviour[url(VID_A)] = add_during
        svc.start(None)
        assert not (save_dir / ".utube_tmp").exists()
        assert "포함되지 않았습니다" in svc.notices[-1]["text"]
        assert svc.items[1].status == "waiting"

    def test_받는_동안은_형식과_폴더를_바꿀_수_없다(self, svc):
        svc.batch.running = True
        with pytest.raises(ServiceError, match="받는 동안"):
            svc.update_settings({"format": "FLAC"})
        svc.update_settings({"hide_queued": True})  # 화면 설정은 된다
        assert svc.update_settings({"sidebar": "closed"}).sidebar == "closed"
        assert svc.settings.get().sidebar == "closed"  # 다음 실행에도 접힌 채로 연다


# ---------------------------------------------------------------------- 설정·파일
class TestSettingsAndFiles:
    def test_없는_폴더로는_바꾸지_않는다(self, svc, tmp_path):
        with pytest.raises(ServiceError, match="폴더를 찾을 수"):
            svc.update_settings({"save_dir": str(tmp_path / "없음")})

    def test_설정은_파일에_남는다(self, svc, store, tmp_path):
        other = tmp_path / "other"
        other.mkdir()
        svc.update_settings({"save_dir": str(other), "quality": "192"})
        assert store._load().save_dir == str(other) and store._load().quality == "192"

    def test_파일_목록(self, svc, save_dir):
        (save_dir / "a.mp3").write_bytes(b"x")
        (save_dir / "b.mp4").write_bytes(b"x")
        f = svc.files()
        assert f["ok"] and [e["name"] for e in f["audio"]] == ["a.mp3"] and [e["name"] for e in f["video"]] == ["b.mp4"]

    def test_받는_중에는_파일을_지우지_않는다(self, svc, save_dir):
        (save_dir / "a.mp3").write_bytes(b"x")
        svc.batch.running = True
        with pytest.raises(ServiceError, match="진행 중"):
            svc.delete_file("a.mp3")
        assert (save_dir / "a.mp3").exists()

    def test_파일_삭제와_종류별_삭제(self, svc, save_dir):
        for n in ("a.mp3", "b.flac", "c.mp4"):
            (save_dir / n).write_bytes(b"x")
        svc.delete_file("a.mp3")
        assert svc.delete_kind("audio") == {"deleted": 1, "failed": 0, "message": None}
        assert os.listdir(save_dir) == ["c.mp4"]

    def test_폴더_밖은_건드리지_않는다(self, svc, save_dir):
        (save_dir.parent / "outside.mp3").write_bytes(b"x")
        with pytest.raises(ServiceError):
            svc.delete_file("..\\outside.mp3")
        assert (save_dir.parent / "outside.mp3").exists()
