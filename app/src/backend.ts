// 백엔드 연결. (공통 파일: 네 앱이 같은 내용을 쓴다. 앱마다 다른 값은 appInfo.ts. docs/STRUCTURE.md)
// Tauri 안에서는 셸이 백엔드를 띄우고 주소와 토큰을 알려 준다.
// 브라우저(pnpm dev)에서는 VITE_BACKEND_URL 또는 127.0.0.1:<DEV_BACKEND_PORT>의 `<NAME> serve`에 붙는다.

import { DEV_BACKEND_PORT, NAME } from "./appInfo";

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
    base = import.meta.env.VITE_BACKEND_URL ?? `http://127.0.0.1:${DEV_BACKEND_PORT}`;
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
    headers: { "content-type": "application/json", ...(token ? { [`x-${NAME}-token`]: token } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const j = await r.json();
      detail = typeof j.detail === "string" ? j.detail : "요청 값이 올바르지 않습니다.";
    } catch {
      /* statusText를 쓴다 */
    }
    throw new ApiError(r.status, detail);
  }
  return r.json() as Promise<T>;
}

export const api = {
  get: <T,>(p: string) => call<T>("GET", p),
  post: <T,>(p: string, b?: unknown) => call<T>("POST", p, b ?? {}),
  patch: <T,>(p: string, b: unknown) => call<T>("PATCH", p, b),
  put: <T,>(p: string, b: unknown) => call<T>("PUT", p, b),
  del: <T,>(p: string) => call<T>("DELETE", p),
};

/** WebSocket을 연다. 끊기면 1초 뒤 다시 붙는다. 돌려준 함수로 닫는다. link는 붙고 끊길 때 불린다. */
export function socket(path: string, onMessage: (data: unknown) => void, link?: (up: boolean) => void): () => void {
  let closed = false;
  let ws: WebSocket | null = null;
  const open = () => {
    ws = new WebSocket(`${base.replace(/^http/, "ws")}${path}${token ? `?token=${token}` : ""}`);
    ws.onopen = () => link?.(true);
    ws.onmessage = (m) => onMessage(JSON.parse(m.data));
    ws.onclose = () => {
      link?.(false);
      if (!closed) setTimeout(open, 1000);
    };
  };
  open();
  return () => {
    closed = true;
    ws?.close();
  };
}
