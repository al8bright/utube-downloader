import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { type AppData, api, connect, events, type FilesData, inTauri, type SearchData, type WithMessage } from "./api";
import { type AppCtx, Ctx, type ScreenName, useApp } from "./ctx";
import { FilesScreen } from "./Files";
import { mergeMessages, unitFor } from "./format";
import { QueueScreen } from "./Queue";
import { SearchScreen } from "./Search";
import { ICONS } from "./icons";
import { Bar, Ellipsis, Icon, Logo, Modal } from "./ui";

const VERSION = "2.0.0";

export default function App() {
  const [ready, setReady] = useState<"wait" | "ok" | string>("wait");
  const [data, setData] = useState<AppData | null>(null);
  const [search, setSearch] = useState<SearchData | null>(null);
  const [files, setFiles] = useState<FilesData | null>(null);
  const [screen, setScreen] = useState<ScreenName>("search");
  const [linkUp, setLinkUp] = useState(true);
  const [alertText, setAlertText] = useState("");
  const [askClose, setAskClose] = useState(false);
  const seenNotice = useRef<number | null>(null);
  const running = !!data?.batch.running;
  const runningRef = useRef(false);
  useEffect(() => {
    runningRef.current = running;
  }, [running]);

  const alert = useCallback((text: string) => setAlertText((cur) => mergeMessages(cur, text)), []);
  const act = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    try {
      const r = await fn();
      const m = (r as WithMessage | null)?.message;
      if (m) alert(m);
      return r;
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
      return undefined;
    }
  }, [alert]);
  const refreshFiles = useCallback(async () => {
    try {
      setFiles(await api.get<FilesData>("/files"));
    } catch {
      /* 다음 변경 때 다시 읽는다 */
    }
  }, []);

  useEffect(() => {
    let stop: (() => void) | undefined;
    connect()
      .then(async () => {
        const [d, s] = await Promise.all([api.get<AppData>("/state"), api.get<SearchData>("/search")]);
        setData(d);
        setSearch(s);
        setReady("ok");
        stop = events({ state: setData, search: setSearch, link: setLinkUp });
      })
      .catch((e) => setReady(String(e?.message ?? e)));
    return () => stop?.();
  }, []);

  // 받는 중 추가분, 재생목록 차단처럼 백엔드가 나중에 알리는 것
  useEffect(() => {
    if (!data) return;
    const last = data.notices.at(-1)?.id ?? 0;
    if (seenNotice.current === null) {
      seenNotice.current = last; // 화면을 다시 열었을 때 지난 알림을 또 띄우지 않는다
      return;
    }
    for (const n of data.notices) if (n.id > seenNotice.current) alert(n.text);
    seenNotice.current = Math.max(seenNotice.current, last);
  }, [data, alert]);

  // 저장 폴더가 바뀌었을 수 있으면 다시 읽는다. 음성·영상 화면에 들어올 때도 읽는다(밖에서 지운 파일)
  const filesVersion = data?.files_version;
  useEffect(() => {
    if (filesVersion !== undefined) void refreshFiles();
  }, [filesVersion, refreshFiles]);
  useEffect(() => {
    if (screen === "audio" || screen === "video") void refreshFiles();
  }, [screen, refreshFiles]);

  // 받는 중에 창을 닫으면 확인을 받는다
  useEffect(() => {
    if (!inTauri) return;
    let unlisten: (() => void) | undefined;
    let gone = false;
    import("@tauri-apps/api/window").then(({ getCurrentWindow }) =>
      getCurrentWindow()
        .onCloseRequested((e) => {
          if (runningRef.current) {
            e.preventDefault();
            setAskClose(true);
          }
        })
        .then((u) => (gone ? u() : (unlisten = u))),
    );
    return () => {
      gone = true;
      unlisten?.();
    };
  }, []);

  const closeNow = useCallback(async () => {
    try {
      await api.post("/batch/stop");
    } catch {
      /* 어차피 닫는다. ffmpeg 는 백엔드와 함께 정리된다 */
    }
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    await getCurrentWindow().destroy();
  }, []);

  const ctx: AppCtx | null = useMemo(() => (data && search ? {
    data, search, files, screen, go: setScreen, alert, act, refreshFiles,
  } : null), [data, search, files, screen, alert, act, refreshFiles]);

  if (ready !== "ok" || !ctx) return <Splash text={ready === "wait" || ready === "ok" ? "백엔드를 시작하는 중…" : ready} error={ready !== "wait" && ready !== "ok"} />;

  return (
    <Ctx.Provider value={ctx}>
      <div className="shell">
        <Sidebar />
        <div className="col">
          <main className="main">
            {/* 화면은 모두 붙여 두고 숨긴다. 입력·필터·스크롤 위치가 화면을 오가도 남는다 */}
            <div className="screen-slot" hidden={screen !== "search"}><SearchScreen /></div>
            <div className="screen-slot" hidden={screen !== "queue"}><QueueScreen /></div>
            <div className="screen-slot" hidden={screen !== "audio"}><FilesScreen kind="audio" /></div>
            <div className="screen-slot" hidden={screen !== "video"}><FilesScreen kind="video" /></div>
          </main>
          <div className="foot">
            {/* 대기열 화면에서는 같은 정보가 '지금 받는 중' 카드로 크게 보이므로 숨긴다 */}
            {running && screen !== "queue" && <RunLine />}
            <Monitor linkUp={linkUp} />
          </div>
        </div>
      </div>
      {!linkUp && <div className="offline" role="status">백엔드와 연결이 끊겼습니다. 다시 연결하는 중…</div>}
      {alertText && (
        <Modal title="알림" onClose={() => setAlertText("")}
          actions={<button className="btn primary" onClick={() => setAlertText("")}>확인</button>}>
          {alertText}
        </Modal>
      )}
      {askClose && (
        <Modal title="다운로드 진행 중" onClose={() => setAskClose(false)}
          actions={<>
            <button className="btn" data-autofocus onClick={() => setAskClose(false)}>계속 받기</button>
            <button className="btn danger-solid" onClick={closeNow}>종료</button>
          </>}>
          {"아직 다운로드가 진행 중입니다.\n\n지금 종료하면 받고 있던 곡은 저장되지 않습니다.\n종료할까요?"}
        </Modal>
      )}
    </Ctx.Provider>
  );
}

// ---------------------------------------------------------------------- 사이드바

const NAV: Record<ScreenName, { label: string; icon: string }> = {
  search: { label: "검색", icon: ICONS.search },
  queue: { label: "대기열", icon: ICONS.queue },
  audio: { label: "음성", icon: ICONS.audio },
  video: { label: "영상", icon: ICONS.video },
};

function Sidebar() {
  const { data, search, files, screen, go, act } = useApp();
  // 폭은 이 버튼으로만 바뀐다. 누르자마자 접히고, 설정에 남겨 다음 실행에도 같은 모양으로 연다
  const [shut, setShut] = useState(data.settings.sidebar === "closed");
  const toggle = () => {
    const next = !shut;
    setShut(next);
    void act(() => api.put("/settings", { sidebar: next ? "closed" : "open" }));
  };
  const count: Record<ScreenName, number | undefined> = {
    search: search.results.length || undefined,
    queue: data.items.length || undefined,
    audio: files?.audio.length,
    video: files?.video.length,
  };
  const item = (name: ScreenName) => (
    <button key={name} className="nav-item" aria-current={screen === name ? "page" : undefined} title={NAV[name].label} onClick={() => go(name)}>
      <Icon d={NAV[name].icon} size={shut ? 18 : 16} />
      <span>{NAV[name].label}</span>
      {name === "queue" && data.batch.running && <span className="live" aria-label="받는 중" />}
      {count[name] ? <span className="nav-count">{count[name]}</span> : null}
    </button>
  );
  return (
    <nav className={`side${shut ? " shut" : ""}`} aria-label="주 메뉴">
      <div className="side-top">
        <Logo />
        {!shut && (
          <div className="brand-name">
            <b>MUSIC DL</b>
            <span>YouTube 음악 다운로더</span>
          </div>
        )}
        <button className="side-toggle" onClick={toggle} aria-label={shut ? "사이드바 펼치기" : "사이드바 접기"} aria-expanded={!shut}>
          <svg aria-hidden width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 5h16v14H4zM9 5v14" /><path d={shut ? "M13 10l2 2-2 2" : "M16 10l-2 2 2 2"} />
          </svg>
        </button>
      </div>
      <div className="side-group">
        <span>찾기</span>
        {item("search")}
        {item("queue")}
      </div>
      <div className="side-group">
        <span>{shut ? "파일" : "받은 파일"}</span>
        {item("audio")}
        {item("video")}
      </div>
      <span className="side-ver">V{VERSION}</span>
    </nav>
  );
}

// ---------------------------------------------------------------------- 하단: 받는 중 한 줄

function RunLine() {
  const { data, go, act } = useApp();
  const b = data.batch;
  const current = data.items.find((i) => i.id === b.current_id);
  let stat = "분석 중";
  if (b.stage === "download") stat = `${Math.round(b.percent * 100)}% · ${b.speed} · ${b.eta}`;
  else if (b.stage === "convert") stat = b.format === "MP4" ? "영상 병합 중" : `${b.format} 변환 중`;
  return (
    <div className="runline" aria-label="받는 중">
      <span className="live" aria-hidden />
      <span className="order">{b.position} / {b.total}{unitFor(b.format)}</span>
      <Ellipsis className={`title${b.stop_requested ? " danger" : ""}`} title={current?.title}>
        {b.stop_requested ? (b.stop_message ?? "중단하는 중…") : current?.title ?? "받을 준비 중…"}
      </Ellipsis>
      <Bar value={b.stage === "download" ? b.percent : b.stage === "convert" ? null : 0} tone="p" label="지금 곡 진행률" />
      <span className="stat">{stat}</span>
      <span className="btns">
        <button className="btn sm cyan-ghost" onClick={() => go("queue")}>대기열 보기</button>
        <button className="btn sm danger" disabled={b.stop_requested} onClick={() => act(() => api.post("/batch/stop"))}>중단</button>
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------- 하단: 상태 줄

interface SystemInfo { yt_dlp: string | null; ffmpeg: string | null }

function Monitor({ linkUp }: { linkUp: boolean }) {
  const { data } = useApp();
  const b = data.batch;
  const [sys, setSys] = useState<SystemInfo | null>(null);
  useEffect(() => {
    api.get<SystemInfo>("/system").then(setSys).catch(() => {});
  }, []);

  let svc = "백엔드 연결됨 · 대기 중";
  let tone = "ok";
  if (!linkUp) {
    svc = "백엔드 연결 끊김";
    tone = "err";
  } else if (b.running) svc = b.stop_requested ? "백엔드 연결됨 · 중단하는 중" : "백엔드 연결됨 · 받는 중";

  return (
    <footer className="monitor" aria-label="상태">
      <span className="svc"><span className={`live ${tone}`} aria-hidden />{svc}</span>
      {b.running && (
        <span className="meter">
          <b>QUEUE</b>
          <span className="track" aria-hidden><span style={{ width: `${Math.round(b.overall * 100)}%` }} /></span>
          <span className="val">{Math.round(b.overall * 100)}%</span>
        </span>
      )}
      {sys && (
        <span className="monitor-right">
          <span>yt-dlp {sys.yt_dlp ?? "?"}</span>
          <span className={sys.ffmpeg ? undefined : "danger"}>{sys.ffmpeg ? "FFmpeg 준비됨" : "FFmpeg 없음"}</span>
        </span>
      )}
    </footer>
  );
}

function Splash({ text, error }: { text: string; error?: boolean }) {
  return (
    <div className="splash">
      <Logo size={60} />
      <p className={error ? "err" : undefined}>{text}</p>
    </div>
  );
}
