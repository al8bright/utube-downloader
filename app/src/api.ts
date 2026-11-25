// 백엔드 클라이언트. Tauri 안에서는 셸이 백엔드를 띄우고 주소와 토큰을 알려 준다.
// 브라우저(pnpm dev)에서는 VITE_UTUBE_URL 또는 127.0.0.1:8766 의 `utube serve` 에 붙는다.

export const inTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

let base = "";
let token = "";

export async function connect(): Promise<void> {
  if (inTauri) {
    const { invoke } = await import("@tauri-apps/api/core");
    const info = await invoke<{ url: string; token: string }>("backend_info");
    base = info.url;
    token = info.token;
  } else {
    base = import.meta.env.VITE_UTUBE_URL ?? "http://127.0.0.1:8766";
  }
  for (let i = 0; i < 150; i++) {
    try {
      const r = await fetch(`${base}/health`);
      if (r.ok) return;
    } catch {
      /* 아직 뜨지 않았다 */
    }
    await new Promise((res) => setTimeout(res, 200));
  }
  throw new Error(`백엔드(${base})에 연결하지 못했습니다.`);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${base}${path}`, {
    method,
    headers: { "content-type": "application/json", ...(token ? { "x-utube-token": token } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const j = await r.json();
      detail = typeof j.detail === "string" ? j.detail : "요청 값이 올바르지 않습니다.";
    } catch {
      /* statusText 를 쓴다 */
    }
    throw new ApiError(r.status, detail);
  }
  return r.json() as Promise<T>;
}

export const api = {
  get: <T,>(p: string) => call<T>("GET", p),
  post: <T,>(p: string, b?: unknown) => call<T>("POST", p, b ?? {}),
  put: <T,>(p: string, b: unknown) => call<T>("PUT", p, b),
  del: <T,>(p: string) => call<T>("DELETE", p),
};

/** 상태·검색 변경을 받는다. 끊기면 1초 뒤 다시 붙는다. 돌려준 함수로 닫는다. */
export function events(handlers: { state: (s: AppData) => void; search: (s: SearchData) => void; link: (up: boolean) => void }): () => void {
  let closed = false;
  let ws: WebSocket | null = null;
  const open = () => {
    ws = new WebSocket(`${base.replace(/^http/, "ws")}/events${token ? `?token=${token}` : ""}`);
    ws.onopen = () => handlers.link(true);
    ws.onmessage = (m) => {
      const e = JSON.parse(m.data);
      if (e.type === "state") handlers.state(e);
      else if (e.type === "search") handlers.search(e);
    };
    ws.onclose = () => {
      handlers.link(false);
      if (!closed) setTimeout(open, 1000);
    };
  };
  open();
  return () => {
    closed = true;
    ws?.close();
  };
}

// ---------------------------------------------------------------------- 형태

export type Format = "MP3" | "FLAC" | "MP4";
export type Quality = "320" | "256" | "192";
export type Status = "analyzing" | "waiting" | "downloading" | "converting" | "finished" | "failed" | "stopped";

export interface Item {
  id: string;
  url: string;
  title: string;
  uploader: string;
  duration: string;
  thumbnail: string | null;
  video_id: string | null;
  status: Status;
  blocked: boolean;
  error: string | null;
  percent: number;
}

export interface BatchResult {
  message: string;
  all_ok: boolean;
  detail: string;
  progress: number;
  done: number;
  failed: number;
  stopped: number;
  total: number;
}

export interface Batch {
  running: boolean;
  stop_requested: boolean;
  stop_message: string | null;
  format: Format;
  quality: Quality;
  save_dir: string;
  current_id: string | null;
  position: number;
  total: number;
  stage: "analyze" | "download" | "convert" | null;
  percent: number;
  speed: string;
  eta: string;
  convert_started_at: number | null;
  overall: number;
  result: BatchResult | null;
  added_during: number;
}

export interface Settings {
  save_dir: string;
  format: Format;
  quality: Quality;
  hide_queued: boolean;
  sidebar: "open" | "closed";
}

export interface Notice {
  id: number;
  text: string;
  tone: "info" | "warn";
}

export interface AppData {
  version: number;
  search_version: number;
  files_version: number;
  session_started_at: number;
  items: Item[];
  batch: Batch;
  settings: Settings;
  notices: Notice[];
}

export interface SearchResult {
  id: string;
  title: string;
  url: string;
  duration: string;
  uploader: string;
  thumbnail: string;
}

export interface SearchData {
  version: number;
  generation: number;
  query: string;
  status: "idle" | "running" | "done" | "failed";
  results: SearchResult[];
  error: string | null;
}

export interface FileEntry {
  name: string;
  ext: string;
  size: number;
  mtime: number;
}

export interface FilesData {
  dir: string;
  ok: boolean;
  audio: FileEntry[];
  video: FileEntry[];
  error: string | null;
  session_started_at: number;
  version: number;
}

/** 응답에 사용자에게 보여 줄 안내가 실려 오는 동작들 */
export interface WithMessage {
  message?: string | null;
}
