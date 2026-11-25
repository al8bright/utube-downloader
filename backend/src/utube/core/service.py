"""앱 상태와 작업: 검색, 대기열, 일괄 다운로드, 받은 파일.

화면(웹뷰)은 이 상태의 사본만 받아 그린다. 상태를 바꿀 때마다 version 을 올리고,
API 의 WebSocket 이 바뀐 것을 화면에 밀어 준다. 모든 변경은 lock 안에서 한다.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from utube.config import Settings, SettingsStore
from utube.core import storage
from utube.core.proc import terminate_child_ffmpeg
from utube.core.text import (
    UNKNOWN_TIME,
    batch_progress_value,
    describe_batch_detail,
    describe_batch_result,
    format_duration,
    format_eta,
    format_speed,
    search_result_from_entry,
    thumbnail_for,
    unit_for,
)
from utube.core.urls import extract_video_id, is_playlist_info, is_same_video, looks_like_url
from utube.core.ytdl import YtDlp, build_ydl_opts, describe_download_error

SEARCH_LIMIT = 100  # 한 번에 찾는 최대 개수
SEARCH_BATCH = 20   # 이만큼 모이면 바로 화면에 붙인다 (유튜브 한 페이지 분량)
NOTICE_KEEP = 20

SELECTABLE = ("waiting", "stopped", "failed")


class ServiceError(Exception):
    """사용자에게 그대로 보여 줄 문구. status 는 HTTP 상태 코드로 쓴다."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


class Aborted(Exception):
    pass


@dataclass
class Item:
    url: str
    title: str
    uploader: str = ""
    duration: str = UNKNOWN_TIME
    thumbnail: str | None = None
    video_id: str | None = None
    # analyzing | waiting | downloading | converting | finished | failed | stopped
    status: str = "waiting"
    blocked: bool = False  # 재생목록처럼 '받으면 안 되는' 항목. status 만으로는 걸러지지 않는다
    error: str | None = None
    percent: float = 0.0
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def selectable(self) -> bool:
        return not self.blocked and self.status in SELECTABLE


@dataclass
class Batch:
    running: bool = False
    stop_requested: bool = False
    stop_message: str | None = None
    format: str = "MP3"
    quality: str = "320"
    save_dir: str = ""
    current_id: str | None = None
    position: int = 0
    total: int = 0
    stage: str | None = None  # analyze | download | convert
    percent: float = 0.0
    speed: str = ""
    eta: str = ""
    convert_started_at: float | None = None
    overall: float = 0.0
    result: dict | None = None  # 끝난 뒤 '지난 받기 결과'
    added_during: int = 0
    finished_hooks: int = 0


@dataclass
class Search:
    generation: int = 0
    query: str = ""
    status: str = "idle"  # idle | running | done | failed
    results: list[dict] = field(default_factory=list)
    error: str | None = None


def _spawn_thread(fn: Callable, *args: Any) -> None:
    threading.Thread(target=fn, args=args, daemon=True).start()


class Service:
    def __init__(self, ytdl: Any = None, settings: SettingsStore | None = None,
                 spawn: Callable[..., None] | None = None, kill_ffmpeg: Callable[[], int] | None = None) -> None:
        self.ytdl = ytdl or YtDlp()
        self.settings = settings or SettingsStore()
        self.spawn = spawn or _spawn_thread
        self.kill_ffmpeg = kill_ffmpeg or terminate_child_ffmpeg
        self.lock = threading.RLock()
        self.items: list[Item] = []
        self.batch = Batch()
        self.search = Search()
        self.notices: list[dict] = []
        self._notice_id = 0
        self.version = 0          # 대기열·배치·설정·알림이 바뀌면 올린다
        self.search_version = 0   # 검색 결과가 바뀌면 올린다
        self.files_version = 0    # 저장 폴더 내용이 바뀌었을 수 있으면 올린다
        self.session_started_at = time.time()  # 이후에 생긴 파일에 '새로 받음' 을 붙인다

    # ------------------------------------------------------------------ 공통
    def _touch(self) -> None:
        self.version += 1

    def _notice(self, text: str, tone: str = "info") -> None:
        self._notice_id += 1
        self.notices.append({"id": self._notice_id, "text": text, "tone": tone})
        del self.notices[:-NOTICE_KEEP]

    def _find(self, item_id: str) -> Item | None:
        return next((i for i in self.items if i.id == item_id), None)

    def _in_queue(self, url: str) -> bool:
        return any(is_same_video(q.url, url) for q in self.items)

    def _guard_idle(self, message: str = "다운로드 중에는 대기열을 수정할 수 없습니다.") -> None:
        if self.batch.running:
            raise ServiceError(message, 409)

    def _during_batch_message(self, count: int) -> str:
        return (f"{count}개를 대기열에 담았습니다.\n\n"
                "지금은 다운로드가 진행 중이라 이번 배치에는 포함되지 않습니다.\n"
                "현재 배치가 끝난 뒤 다시 다운로드를 시작해 주세요.")

    def snapshot(self) -> dict:
        with self.lock:
            b = asdict(self.batch)
            b.pop("finished_hooks")
            return {
                "version": self.version,
                "search_version": self.search_version,
                "files_version": self.files_version,
                "session_started_at": self.session_started_at,
                "items": [asdict(i) for i in self.items],
                "batch": b,
                "settings": self.settings.get().model_dump(),
                "notices": list(self.notices),
            }

    def search_snapshot(self) -> dict:
        with self.lock:
            s = self.search
            return {"version": self.search_version, "generation": s.generation, "query": s.query,
                    "status": s.status, "results": list(s.results), "error": s.error}

    # ------------------------------------------------------------------ 설정
    def update_settings(self, patch: dict) -> Settings:
        with self.lock:
            current = self.settings.get()
            touches_batch = any(k in patch and patch[k] != getattr(current, k) for k in ("save_dir", "format", "quality"))
            if touches_batch and self.batch.running:
                # 형식을 도중에 바꾸면 결과물이 어긋나고, 폴더를 바꾸면 한 배치가 두 폴더로 흩어진다
                raise ServiceError("받는 동안은 형식·음질·저장 위치를 바꿀 수 없습니다.", 409)
            merged = current.model_dump() | patch
            if "save_dir" in patch:
                path, ok = storage.resolve_save_dir(patch["save_dir"])
                if not ok:
                    raise ServiceError(f"폴더를 찾을 수 없습니다: {patch['save_dir'] or '(비어 있음)'}")
                merged["save_dir"] = path
            value = Settings.model_validate(merged)
            self.settings.save(value)
            if value.save_dir != current.save_dir:
                self.files_version += 1
            self._touch()
            return value

    # ------------------------------------------------------------------ 검색
    def submit_query(self, query: str) -> dict:
        """검색창 입력. 유튜브 링크면 검색하지 않고 바로 대기열에 담는다."""
        query = (query or "").strip()
        if not query:
            raise ServiceError("검색 키워드를 입력해 주세요.")
        if extract_video_id(query) or looks_like_url(query):
            return {"queued": self.add_url(query)}
        with self.lock:
            # 새 검색은 옛 검색을 대신한다. 늦게 끝난 옛 검색은 generation 이 달라 결과를 버린다
            self.search = Search(generation=self.search.generation + 1, query=query, status="running")
            self.search_version += 1
            gen = self.search.generation
        self.spawn(self._search_worker, query, gen)
        return {"generation": gen}

    def _search_worker(self, query: str, gen: int) -> None:
        pending: list[dict] = []

        def flush() -> bool:
            with self.lock:
                if self.search.generation != gen:
                    return False
                self.search.results.extend(pending)
                self.search_version += 1
            pending.clear()
            return True

        try:
            seen: set[str] = set()
            for entry in self.ytdl.search(query, SEARCH_LIMIT):
                if self.search.generation != gen:
                    return  # 새 검색이 시작됐다. 남은 페이지는 받지 않는다
                result = search_result_from_entry(entry)
                if result is None or result["id"] in seen:
                    continue  # 채널·재생목록, 중복
                seen.add(result["id"])
                pending.append(result)
                if len(pending) >= SEARCH_BATCH and not flush():
                    return
            if pending and not flush():
                return
            with self.lock:
                if self.search.generation == gen:
                    self.search.status = "done"
                    self.search_version += 1
        except Exception as e:  # noqa: BLE001 - 어떤 실패든 화면에 사유를 남긴다
            with self.lock:
                if self.search.generation == gen:
                    self.search.results.extend(pending)
                    self.search.status = "failed"
                    self.search.error = describe_download_error(e)
                    self.search_version += 1

    # ------------------------------------------------------------------ 대기열에 담기
    def add_results(self, ids: list[str]) -> dict:
        """검색 결과에서 고른 영상(ID)을 담는다. 링크 형태만 다른 같은 영상도 중복으로 잡는다."""
        if not ids:
            raise ServiceError("추가할 항목을 1개 이상 선택해 주세요.")
        with self.lock:
            wanted = set(ids)
            picked = [r for r in self.search.results if r["id"] in wanted]
            if not picked:
                raise ServiceError("선택한 항목을 검색 결과에서 찾지 못했습니다. 다시 검색해 주세요.")
            added = 0
            for r in picked:
                if self._in_queue(r["url"]):
                    continue
                self.items.append(Item(url=r["url"], title=r["title"], uploader=r["uploader"],
                                       duration=r["duration"], thumbnail=r["thumbnail"], video_id=r["id"]))
                added += 1
            message = None
            if not added:
                # 선택은 했지만 전부 이미 있는 경우. 조용히 넘기면 사용자는 추가된 줄 안다
                message = "선택한 항목이 모두 이미 대기열에 있습니다.\n\n새로 추가된 곡은 없습니다."
            elif self.batch.running:
                self.batch.added_during += added
                message = self._during_batch_message(added)
            self._touch()
            return {"added": added, "duplicates": len(picked) - added, "message": message}

    def add_url(self, url: str) -> dict:
        """링크 하나를 담고 분석을 시작한다. 검색창과 '+ 링크 추가' 가 같은 길을 쓴다."""
        url = (url or "").strip()
        if not url:
            raise ServiceError("추가할 유튜브 링크를 입력해 주세요.")
        if not url.lower().startswith(("http://", "https://")):
            url = "https://" + url
        with self.lock:
            if self._in_queue(url):
                raise ServiceError("이미 대기열에 존재하는 링크입니다.", 409)
            vid = extract_video_id(url)
            item = Item(url=url, title=f"링크 분석 중: {url}", uploader="분석 중...", status="analyzing",
                        video_id=vid, thumbnail=thumbnail_for(vid))
            self.items.append(item)
            message = None
            if self.batch.running:
                self.batch.added_during += 1
                message = self._during_batch_message(1)
            self._touch()
        self.spawn(self._analyze_worker, item.id, url)
        return {"id": item.id, "message": message}

    def _analyze_worker(self, item_id: str, url: str) -> None:
        try:
            info = self.ytdl.analyze(url)
        except Exception as e:  # noqa: BLE001
            with self.lock:
                item = self._find(item_id)
                if item and item.status == "analyzing":
                    item.title, item.uploader = f"분석 실패: {url}", "오류 발생"
                    item.status, item.error = "failed", describe_download_error(e)
                    self._touch()
            return

        with self.lock:
            item = self._find(item_id)
            if item is None or item.status != "analyzing":
                return  # 그사이 대기열에서 지웠다
            if is_playlist_info(info):
                # 순수 재생목록/채널 링크는 항목 하나가 영상 수백 개를 받게 되므로 막는다
                count = len(info.get("entries") or [])
                title = info.get("title") or url
                item.title = f"재생목록은 추가할 수 없습니다: {title}"
                item.uploader = f"영상 {count}개 포함"
                item.status, item.blocked = "failed", True
                item.error = (f"재생목록/채널 링크입니다(영상 {count}개). "
                              "개별 영상 링크를 넣거나 검색 화면에서 곡을 선택해 주세요.")
                self._notice(f"재생목록 링크는 추가할 수 없습니다.\n\n'{title}' 에는 영상 {count}개가 들어 있어\n"
                             "한 항목으로 받으면 저장 폴더가 통째로 채워집니다.\n\n"
                             "개별 영상 링크를 넣거나 검색 화면을 이용해 주세요.", "warn")
            else:
                vid = info.get("id") if len(info.get("id") or "") == 11 else item.video_id
                item.video_id = vid
                item.title = info.get("title") or "Unknown Title"
                item.uploader = info.get("uploader") or info.get("channel") or "Unknown"
                item.duration = format_duration(info.get("duration"))
                item.thumbnail = thumbnail_for(vid) or info.get("thumbnail")
                item.status = "waiting"
            self._touch()

    # ------------------------------------------------------------------ 대기열 정리
    def remove(self, item_id: str) -> None:
        with self.lock:
            self._guard_idle()
            item = self._find(item_id)
            if item is None:
                raise ServiceError("대기열에 없는 항목입니다.", 404)
            self.items.remove(item)
            self._touch()

    def clear(self) -> None:
        with self.lock:
            self._guard_idle("다운로드 중에는 대기열을 비울 수 없습니다.")
            self.items.clear()
            # 비운 대기열에 지난 결과가 남아 있으면 무엇의 결과인지 알 수 없다
            self.batch.result = None
            self._touch()

    def clear_finished(self) -> int:
        with self.lock:
            self._guard_idle()
            before = len(self.items)
            self.items = [i for i in self.items if i.status != "finished"]
            removed = before - len(self.items)
            if not removed:
                raise ServiceError("대기열에 완료 상태인 항목이 없습니다.")
            self._touch()
            return removed

    # ------------------------------------------------------------------ 일괄 다운로드
    def start(self, ids: list[str] | None) -> dict:
        """ids 가 None 이면 받을 수 있는 곡 전부를 받는다."""
        with self.lock:
            if self.batch.running:
                raise ServiceError("이미 다운로드 대기열이 실행 중입니다.", 409)
            wanted = None if ids is None else set(ids)
            picked = [i for i in self.items if i.selectable() and (wanted is None or i.id in wanted)]
            if not picked:
                blocked = sum(1 for i in self.items if i.blocked)
                analyzing = sum(1 for i in self.items if i.status == "analyzing")
                if blocked and wanted is None:
                    raise ServiceError(f"받을 수 있는 항목이 없습니다.\n\n대기열의 {blocked}개는 재생목록/채널 링크라 받을 수 없습니다.\n"
                                       "개별 영상 링크를 넣거나 검색 화면을 이용해 주세요.")
                if analyzing:
                    raise ServiceError("아직 링크를 분석하는 중입니다. 분석이 끝난 뒤 다시 시작해 주세요.")
                raise ServiceError("다운로드할(완료되지 않은) 항목을 1개 이상 선택해 주세요.")

            settings = self.settings.get()
            save_dir, ok = storage.resolve_save_dir(settings.save_dir)
            if not ok:
                # 안내만 하고 진행하면 파일이 엉뚱한 폴더로 조용히 쌓인다
                raise ServiceError("저장 폴더를 찾을 수 없어 다운로드를 시작하지 않았습니다.\n\n"
                                   f"지정된 경로: {settings.save_dir or '(비어 있음)'}\n\n"
                                   "'변경' 으로 저장 폴더를 지정한 뒤 다시 시작해 주세요.")
            self.batch = Batch(running=True, format=settings.format, quality=settings.quality,
                               save_dir=save_dir, total=len(picked))
            for i in picked:
                i.error = None
            order = [i.id for i in picked]
            self._touch()
        self.spawn(self._batch_worker, order)
        return {"count": len(order)}

    def stop(self) -> bool:
        with self.lock:
            if not self.batch.running:
                return False
            self.batch.stop_requested = True
            self._touch()
        # 변환(FFmpeg) 단계에서는 progress_hook 이 불리지 않아 플래그만으로는 멈추지 않는다.
        # 실행 중인 자식 ffmpeg 를 직접 끊어야 즉시 멈춘다.
        killed = self.kill_ffmpeg()
        with self.lock:
            self.batch.stop_message = ("변환을 중단했습니다. 정리하는 중..." if killed
                                       else "중단 요청됨. 현재 곡을 정리하는 중...")
            self._touch()
        return True

    def _batch_worker(self, order: list[str]) -> None:
        b = self.batch
        tally = {"done": 0, "failed": 0, "stopped": 0}
        total = len(order)
        # try/finally 가 없으면 예외 한 번에 running 이 True 로 굳어 다시 시작할 수 없다
        try:
            for num, item_id in enumerate(order):
                with self.lock:
                    if b.stop_requested:
                        # 아직 손대지 않은 나머지는 집계에서만 중단으로 센다.
                        # 상태는 '대기 중' 그대로 둬야 다음에 '모두 받기' 로 이어 받을 수 있다
                        tally["stopped"] += total - num
                        break
                    item = self._find(item_id)
                    if item is None:
                        tally["stopped"] += 1
                        continue
                    item.status, item.percent, item.error = "downloading", 0.0, None
                    b.current_id, b.position = item_id, num + 1
                    b.stage, b.percent, b.speed, b.eta = "analyze", 0.0, "", UNKNOWN_TIME
                    b.convert_started_at, b.finished_hooks = None, 0
                    b.overall = num / total
                    url = item.url
                    self._touch()

                error = self._download_one(item, url)

                with self.lock:
                    if error is None:
                        item.status, item.percent = "finished", 1.0
                        tally["done"] += 1
                        self.files_version += 1
                    elif b.stop_requested:
                        item.status = "stopped"  # 사용자가 직접 멈춘 것은 오류가 아니다
                        tally["stopped"] += 1
                    else:
                        item.status, item.error = "failed", error
                        tally["failed"] += 1
                    b.overall = (num + 1) / total
                    self._touch()
        finally:
            # 배치가 끝나면 중간 파일 찌꺼기를 정리한다
            storage.cleanup_temp_dir(b.save_dir)
            with self.lock:
                unit = unit_for(b.format)
                message, all_ok = describe_batch_result(tally["done"], tally["failed"], tally["stopped"],
                                                        total=total, unit=unit)
                b.result = {
                    "message": message, "all_ok": all_ok,
                    "detail": describe_batch_detail(tally["done"], tally["failed"], tally["stopped"]),
                    "progress": batch_progress_value(tally["done"], tally["failed"], tally["stopped"]),
                    **tally, "total": total,
                }
                if b.added_during:
                    self._notice(f"다운로드 중에 추가된 {b.added_during}개 항목은 이번 배치에 포함되지 않았습니다.\n\n"
                                 "대기열에 그대로 남아 있으니 '대기 중인 곡 모두 받기' 를 다시 눌러 주세요.")
                    b.added_during = 0
                # 받는 도중 앱이 강제로 멈춘 항목이 '다운로드 중' 으로 남지 않게 한다
                for it in self.items:
                    if it.status in ("downloading", "converting"):
                        it.status = "stopped"
                b.running, b.stop_requested, b.stop_message = False, False, None
                b.current_id, b.stage = None, None
                self.files_version += 1
                self._touch()

    def _download_one(self, item: Item, url: str) -> str | None:
        """한 곡을 받는다. 성공이면 None, 실패면 사유."""
        b = self.batch

        def hook(d: dict) -> None:
            if b.stop_requested:
                raise Aborted("Download aborted by user")
            with self.lock:
                if d.get("status") == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    done = d.get("downloaded_bytes") or 0
                    pct = min(done / total, 1.0) if total > 0 else 0.0
                    b.stage = "download"
                    b.percent = item.percent = pct
                    b.speed = format_speed(d.get("speed")) or "계산 중..."
                    b.eta = format_eta(d.get("eta")) if d.get("eta") is not None else UNKNOWN_TIME
                    self._touch()
                elif d.get("status") == "finished":
                    # MP4 는 영상/음성을 따로 받아 이 훅이 두 번 온다. 첫 번째에서 '변환' 으로 바꾸면
                    # 두 번째 다운로드가 시작되며 진행률이 100% -> 0% 로 되감겨 보인다
                    b.finished_hooks += 1
                    if b.format == "MP4" and b.finished_hooks < 2:
                        return
                    b.stage, b.percent = "convert", 1.0
                    b.convert_started_at = time.time()
                    item.status = "converting"
                    self._touch()

        opts = build_ydl_opts(b.save_dir, b.format, b.quality, hook)
        try:
            self.ytdl.download(url, opts)
            return None
        except BaseException as e:  # noqa: BLE001 - yt-dlp 는 KeyboardInterrupt 류도 감싸 던진다
            if isinstance(e, (SystemExit, KeyboardInterrupt)):
                raise
            return describe_download_error(e)

    # ------------------------------------------------------------------ 받은 파일
    def files(self) -> dict:
        settings = self.settings.get()
        save_dir, ok = storage.resolve_save_dir(settings.save_dir)
        out = {"dir": save_dir, "ok": ok, "audio": [], "video": [], "error": None,
               "session_started_at": self.session_started_at, "version": self.files_version}
        if not ok:
            out["error"] = f"저장 폴더를 찾을 수 없습니다: {settings.save_dir or '(비어 있음)'}"
            return out
        try:
            out.update(storage.list_files(save_dir))
        except OSError as e:
            out["error"] = f"파일 목록을 읽지 못했습니다.\n\n{e.strerror or e}"
        return out

    def _guard_files(self) -> str:
        if self.batch.running:
            raise ServiceError("다운로드가 진행 중입니다.\n\n진행 중에는 파일을 삭제할 수 없습니다. 완료 후 다시 시도해 주세요.", 409)
        save_dir, ok = storage.resolve_save_dir(self.settings.get().save_dir)
        if not ok:
            raise ServiceError("저장 폴더를 찾을 수 없습니다.")
        return save_dir

    def file_path(self, name: str) -> str:
        save_dir, ok = storage.resolve_save_dir(self.settings.get().save_dir)
        if not ok:
            raise ServiceError("저장 폴더를 찾을 수 없습니다.")
        try:
            return storage.file_in_dir(save_dir, name)
        except storage.StorageError as e:
            raise ServiceError(str(e), 404) from e

    def delete_file(self, name: str) -> None:
        with self.lock:
            save_dir = self._guard_files()
            try:
                path = storage.file_in_dir(save_dir, name)
            except storage.StorageError as e:
                raise ServiceError(str(e), 404) from e
            try:
                os.remove(path)
            except OSError as e:
                raise ServiceError(f"파일을 삭제하지 못했습니다.\n\n{e.strerror or e}") from e
            self.files_version += 1
            self._touch()

    def delete_kind(self, kind: str) -> dict:
        with self.lock:
            save_dir = self._guard_files()
            try:
                deleted, errors = storage.delete_kind(save_dir, kind)
            except storage.StorageError as e:
                raise ServiceError(str(e)) from e
            self.files_version += 1
            self._touch()
            message = None
            if errors:
                listed = "\n".join(errors[:5]) + (f"\n외 {len(errors) - 5}개 파일" if len(errors) > 5 else "")
                message = f"{deleted}개 파일 삭제 완료 (일부 실패):\n{listed}"
            return {"deleted": deleted, "failed": len(errors), "message": message}

    # ------------------------------------------------------------------ 시작·종료
    def startup_cleanup(self) -> None:
        """지난번에 강제 종료돼 남은 임시 폴더를 치운다."""
        storage.cleanup_temp_dir(self.settings.get().save_dir)

    def shutdown(self) -> None:
        with self.lock:
            self.batch.stop_requested = True
        self.kill_ffmpeg()
