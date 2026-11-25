// 화면에 보일 문자열과 분류. 위젯을 만들지 않는다.
import type { FileEntry, Format, Item } from "./api";

export const unitFor = (f: Format) => (f === "MP4" ? "편" : "곡");

// ---------------------------------------------------------------------- 대기열

export const QUEUE_FILTERS = ["전체", "대기", "완료", "문제"] as const;
export type QueueFilter = (typeof QUEUE_FILTERS)[number];
type Bucket = "대기" | "진행" | "완료" | "문제";

/** 중단된 곡은 다시 받을 수 있어 '대기' 로 센다. 막힌 항목은 '문제' 다. */
export function queueBucket(item: Item): Bucket {
  if (item.blocked || item.status === "failed") return "문제";
  if (item.status === "finished") return "완료";
  if (item.status === "waiting" || item.status === "stopped") return "대기";
  return "진행";
}

export function summarizeQueue(items: Item[]): Record<Bucket | "전체", number> {
  const c = { 대기: 0, 진행: 0, 완료: 0, 문제: 0, 전체: items.length };
  for (const i of items) c[queueBucket(i)]++;
  return c;
}

/** 제목 옆 요약. 0 인 분류는 적지 않는다. */
export function describeQueueSummary(items: Item[], unit: string): string {
  const c = summarizeQueue(items);
  if (!c.전체) return "비어 있음";
  const parts = [`${c.전체}${unit}`];
  for (const [k, label] of [["대기", "대기"], ["진행", "받는 중"], ["완료", "완료"], ["문제", "문제"]] as const) {
    if (c[k]) parts.push(`${label} ${c[k]}`);
  }
  return parts.join(" · ");
}

/** 받기 대상으로 고를 수 있는 항목. 완료·차단·진행 중인 곡은 고를 수 없다. */
export const isSelectable = (i: Item) => !i.blocked && (i.status === "waiting" || i.status === "stopped" || i.status === "failed");

export function describeQueueStatus(i: Item): { label: string; reason: string | null; tone: string } {
  if (i.blocked) return { label: "받지 않음", reason: i.error, tone: "blocked" };
  switch (i.status) {
    case "failed": return { label: "실패", reason: i.error, tone: "failed" };
    case "analyzing": return { label: "분석 중…", reason: null, tone: "busy" };
    case "downloading": return { label: `다운로드 중 ${Math.round(i.percent * 100)}%`, reason: null, tone: "downloading" };
    case "converting": return { label: "변환 중…", reason: null, tone: "busy" };
    case "finished": return { label: "완료", reason: null, tone: "finished" };
    case "stopped": return { label: "사용자 중단", reason: null, tone: "stopped" };
    default: return { label: "대기 중", reason: null, tone: "waiting" };
  }
}

// ---------------------------------------------------------------------- 받은 파일

export const FILE_SORTS = { recent: "최근 받은 순", name: "이름 순", size: "크기 순" } as const;
export type FileSort = keyof typeof FILE_SORTS;

/** 100 이상이면 소수점을 버려 열 폭을 일정하게 한다. */
export function formatSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "-";
  let size = bytes;
  for (const unit of ["B", "KB", "MB"]) {
    if (size < 1024) {
      if (unit === "B") return `${Math.trunc(size)}B`;
      return size >= 100 ? `${size.toFixed(0)}${unit}` : `${size.toFixed(1)}${unit}`;
    }
    size /= 1024;
  }
  return size >= 100 ? `${size.toFixed(0)}GB` : `${size.toFixed(1)}GB`;
}

const pad = (n: number) => String(n).padStart(2, "0");

/** 오늘·어제는 시각까지, 올해는 월·일, 그 전은 연도까지. */
export function formatFileDate(mtime: number, now = new Date()): string {
  const when = new Date(mtime * 1000);
  if (Number.isNaN(when.getTime())) return "-";
  const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((day(now) - day(when)) / 86_400_000);
  const hm = `${pad(when.getHours())}:${pad(when.getMinutes())}`;
  if (days === 0) return `오늘 ${hm}`;
  if (days === 1) return `어제 ${hm}`;
  if (when.getFullYear() === now.getFullYear()) return `${when.getMonth() + 1}월 ${when.getDate()}일`;
  return `${when.getFullYear()}. ${when.getMonth() + 1}. ${when.getDate()}.`;
}

export function filterSortFiles(entries: FileEntry[], query: string, ext: string, sort: FileSort): FileEntry[] {
  const needle = query.trim().toLowerCase();
  const picked = entries.filter((e) => (!needle || e.name.toLowerCase().includes(needle)) && (ext === "전체" || e.ext === ext));
  if (sort === "name") picked.sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase(), "ko"));
  else if (sort === "size") picked.sort((a, b) => b.size - a.size);
  else picked.sort((a, b) => b.mtime - a.mtime);
  return picked;
}

/** 열린 알림에 새 문구를 덧붙인다. 같은 문구는 다시 쌓지 않는다. */
export function mergeMessages(existing: string, next: string): string {
  const a = existing.trim();
  const b = next.trim();
  if (!a) return b;
  if (!b || a.includes(b)) return a;
  return `${a}\n\n${"-".repeat(20)}\n\n${b}`;
}
