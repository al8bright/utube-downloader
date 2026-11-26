// 백엔드 클라이언트: 연결은 공통 파일 `backend.ts` 가 맡고, 여기서는 이벤트와 응답 형태를 둔다.

import { socket } from "./backend";

export { ApiError, api, connect, inTauri } from "./backend";

/** 상태·검색 변경을 받는다. 끊기면 1초 뒤 다시 붙는다. 돌려준 함수로 닫는다. */
export function events(handlers: { state: (s: AppData) => void; search: (s: SearchData) => void; link: (up: boolean) => void }): () => void {
  return socket("/events", (data) => {
    const e = data as { type: string };
    if (e.type === "state") handlers.state(e as unknown as AppData);
    else if (e.type === "search") handlers.search(e as unknown as SearchData);
  }, handlers.link);
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
