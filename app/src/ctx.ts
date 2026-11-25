import { createContext, useContext } from "react";
import type { AppData, FilesData, SearchData } from "./api";

export type ScreenName = "search" | "queue" | "audio" | "video";

export interface AppCtx {
  data: AppData;
  search: SearchData;
  files: FilesData | null;
  screen: ScreenName;
  go: (s: ScreenName) => void;
  /** 알림 창. 이미 떠 있으면 내용을 덧붙인다. */
  alert: (text: string) => void;
  /** API 호출을 감싼다: 실패하면 사유를, 응답에 message 가 있으면 그것을 알림으로 띄운다. */
  act: <T>(fn: () => Promise<T>) => Promise<T | undefined>;
  refreshFiles: () => Promise<void>;
}

export const Ctx = createContext<AppCtx | null>(null);

export function useApp(): AppCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("no app context");
  return c;
}
