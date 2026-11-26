import { useEffect, useRef, useState } from "react";
import { api, type Batch, type Format, type Item, inTauri, type Quality } from "./api";
import { useApp } from "./ctx";
import { ICONS } from "./icons";
import {
  describeQueueStatus, describeQueueSummary, isSelectable, QUEUE_FILTERS, type QueueFilter, queueBucket, summarizeQueue, unitFor,
} from "./format";
import { Bar, Check, Chip, Ellipsis, Empty, eyebrow, Icon, Screen } from "./ui";

const FORMATS: Format[] = ["MP3", "FLAC", "MP4"];
const QUALITIES: Quality[] = ["320", "256", "192"];

/** 상태 → 배지 색. 진행 중은 주 네온, 완료·문제·막힘은 상태색, 대기·중단은 무채색. */
const BADGE: Record<string, string> = {
  waiting: "badge", stopped: "badge", busy: "badge run", downloading: "badge p",
  finished: "badge ok", failed: "badge err", blocked: "badge warn",
};

export function QueueScreen() {
  const { data, act } = useApp();
  const { items, batch: b, settings } = data;
  const running = b.running;
  const unit = unitFor(running ? b.format : settings.format);

  // 고른 곡. 새로 담긴 곡은 처음부터 골라 둔다
  const [sel, setSel] = useState<Set<string>>(new Set());
  const known = useRef<Set<string>>(new Set());
  useEffect(() => {
    const ids = new Set(items.map((i) => i.id));
    const fresh = items.filter((i) => !known.current.has(i.id)).map((i) => i.id);
    known.current = ids;
    setSel((cur) => new Set([...[...cur].filter((id) => ids.has(id)), ...fresh]));
  }, [items]);

  const [bucket, setBucket] = useState<QueueFilter>("전체");
  const [linkOpen, setLinkOpen] = useState(false);
  const [link, setLink] = useState("");

  const selectable = items.filter(isSelectable);
  const picked = selectable.filter((i) => sel.has(i.id));
  const counts = summarizeQueue(items);
  const shown = items.map((item, idx) => ({ item, idx })).filter(({ item }) => bucket === "전체" || queueBucket(item) === bucket);

  const toggleAll = (on: boolean) => setSel(on ? new Set(selectable.map((i) => i.id)) : new Set());
  const toggle = (id: string, on: boolean) => setSel((cur) => {
    const next = new Set(cur);
    if (on) next.add(id);
    else next.delete(id);
    return next;
  });

  const addLink = async () => {
    const r = await act(() => api.post("/queue/url", { url: link }));
    if (r) setLink("");
  };

  return (
    <Screen title="대기열" eyebrow={eyebrow("QUEUE", `${describeQueueSummary(items, unit)}${running ? " · 받는 중" : ""}`)}
      bar={running ? <>
        <span className="spacer" />
        <span className="bar-hint">중단하면 지금 곡까지만 멈추고 나머지는 대기 중으로 남습니다</span>
        <button className="btn lg danger" disabled={b.stop_requested} onClick={() => act(() => api.post("/batch/stop"))}>
          {b.stop_requested ? "중단하는 중…" : "다운로드 중단"}
        </button>
      </> : <>
        <button className="btn bare" onClick={() => act(() => api.post("/queue/clear-finished"))}>완료 항목 정리</button>
        <button className="btn bare danger" onClick={() => act(() => api.post("/queue/clear"))}>대기열 비우기</button>
        <span className="spacer" />
        <button className="btn lg" disabled={!picked.length}
          onClick={() => act(() => api.post("/batch/start", { ids: picked.map((i) => i.id) }))}>
          {picked.length ? `선택한 ${picked.length}${unit} 받기` : "선택한 곡 받기"}
        </button>
        <button className="btn primary lg" onClick={() => { toggleAll(true); void act(() => api.post("/batch/start", {})); }}>
          {unit === "편" ? "대기 중인 영상 모두 받기" : "대기 중인 곡 모두 받기"}
        </button>
      </>}>
      <div className="queue-top">
        {(running || b.result) && <NowCard b={b} items={items} />}
        <SettingsCard locked={running} />
      </div>

      <div className="queue-tools">
        <Check checked={!!selectable.length && picked.length === selectable.length}
          indeterminate={!!picked.length && picked.length < selectable.length}
          disabled={running || !selectable.length} label="받을 수 있는 곡 모두 고르기" onChange={toggleAll} />
        <span className="sel">{selectable.length ? `${picked.length}${unit} 선택` : ""}</span>
        <span className="grow" />
        {QUEUE_FILTERS.map((f) => (
          <Chip key={f} active={bucket === f} onClick={() => setBucket(f)}>{f} <span className="n">{counts[f]}</span></Chip>
        ))}
        <button className="btn sm cyan-ghost" aria-expanded={linkOpen} onClick={() => setLinkOpen((v) => !v)}>
          <Icon d={ICONS.link} size={13} /> 링크 추가
        </button>
      </div>
      {linkOpen && (
        <form className="link-row" onSubmit={(e) => { e.preventDefault(); void addLink(); }}>
          <input className="field" autoFocus value={link} onChange={(e) => setLink(e.target.value)}
            placeholder="https://www.youtube.com/watch?v=..." aria-label="유튜브 링크" />
          <button className="btn cyan" type="submit">대기열에 추가</button>
          <button className="btn" type="button" onClick={() => setLinkOpen(false)}>닫기</button>
        </form>
      )}

      <div className="cols q-cols col-head" aria-hidden>
        <span /><span>#</span><span>제목</span><span>길이</span><span>상태</span><span />
      </div>
      <div className="list" role="list" aria-label="대기열">
        {shown.length ? shown.map(({ item, idx }) => (
          <QueueRow key={item.id} item={item} num={idx + 1} current={item.id === b.current_id} locked={running}
            checked={sel.has(item.id)} onCheck={(on) => toggle(item.id, on)} />
        )) : <Empty>{items.length ? "이 분류에 해당하는 곡이 없습니다." : "대기열이 비어 있습니다. 검색 화면에서 곡을 골라 담아 주세요."}</Empty>}
      </div>
    </Screen>
  );
}

function QueueRow({ item, num, current, locked, checked, onCheck }: {
  item: Item; num: number; current: boolean; locked: boolean; checked: boolean; onCheck: (on: boolean) => void;
}) {
  const { act } = useApp();
  const s = describeQueueStatus(item);
  const can = isSelectable(item);
  return (
    <div role="listitem" className={`row cols q-cols q-row${current ? " current" : ""}${item.status === "finished" ? " finished" : ""}`}>
      <Check checked={can && checked} disabled={!can || locked} label={item.title} onChange={onCheck} />
      <span className="num">{num}</span>
      <span className="cell">
        <Ellipsis className="title" title={item.title}>{item.title}</Ellipsis>
        <Ellipsis className="sub">{item.uploader}</Ellipsis>
      </span>
      <span className="len">{item.duration}</span>
      <span className="status">
        <span className={BADGE[s.tone] ?? "badge"}>{s.label}</span>
        {s.reason && <span className="reason">{s.reason}</span>}
      </span>
      <button className="btn icon" disabled={locked} aria-label={`${item.title} 대기열에서 빼기`}
        onClick={() => act(() => api.del(`/queue/${item.id}`))}>
        <Icon d={ICONS.x} size={14} />
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------- 받는 방법

function SettingsCard({ locked }: { locked: boolean }) {
  const { data, act } = useApp();
  const s = data.settings;
  const [draft, setDraft] = useState<string | null>(null);
  const dir = draft ?? s.save_dir;

  const put = (patch: object) => act(() => api.put("/settings", patch));
  const commitDir = async (value: string) => {
    if (value.trim() && value !== s.save_dir) await put({ save_dir: value });
    setDraft(null);
  };
  const browse = async () => {
    if (!inTauri) return;
    const { open } = await import("@tauri-apps/plugin-dialog");
    const picked = await open({ directory: true, defaultPath: s.save_dir || undefined, title: "저장 폴더 고르기" });
    if (typeof picked === "string") await commitDir(picked);
  };

  return (
    <section className="card settings" aria-label="받는 방법">
      <div className="card-head">
        <h2>받는 방법</h2>
        {locked && <span className="badge"><Icon d={ICONS.lock} size={11} /> 받는 동안 잠김</span>}
      </div>
      <div className="settings-row">
        <div className="setting">
          형식
          <div className="seg" role="group" aria-label="형식">
            {FORMATS.map((f) => (
              <button key={f} aria-pressed={s.format === f} disabled={locked} onClick={() => s.format !== f && put({ format: f })}>{f}</button>
            ))}
          </div>
        </div>
        {/* FLAC·MP4 에서도 칸을 숨기지 않고 잠근다. 사라지면 옆 칸이 흔들린다 */}
        <label className="setting">
          음질 (MP3만)
          <select className="field" value={s.quality} disabled={locked || s.format !== "MP3"}
            onChange={(e) => put({ quality: e.target.value })}>
            {QUALITIES.map((q) => <option key={q} value={q}>{q}kbps</option>)}
          </select>
        </label>
      </div>
      <div className="setting path">
        저장 위치
        <div className="path-row">
          <input className="field path" value={dir} disabled={locked} aria-label="저장 위치" spellCheck={false}
            onChange={(e) => setDraft(e.target.value)} onBlur={() => commitDir(dir)}
            onKeyDown={(e) => e.key === "Enter" && commitDir(dir)} />
          {inTauri && <button className="btn" disabled={locked} onClick={browse}>변경</button>}
          <button className="btn cyan-ghost" onClick={() => act(() => api.post("/open/folder"))}>열기</button>
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------- 지금 받는 중

const STEPS = ["analyze", "download", "convert"] as const;

function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(t);
  }, [active]);
  return now;
}

function NowCard({ b, items }: { b: Batch; items: Item[] }) {
  const now = useNow(b.running && b.stage === "convert");
  const unit = unitFor(b.format);
  const current = items.find((i) => i.id === b.current_id);
  const convertLabel = b.format === "MP4" ? "영상 병합" : `${b.format} 변환`;

  if (!b.running && b.result) {
    const r = b.result;
    const tone = r.all_ok ? "badge ok" : r.failed ? "badge err" : "badge";
    return (
      <section className="card now done" aria-label="지난 받기 결과">
        <div className="card-head">
          <span className="eyebrow"><span className="tracked">LAST RUN</span></span>
          <span className={tone}>{r.all_ok ? "모두 받음" : r.failed ? `실패 ${r.failed}` : "일부만 받음"}</span>
        </div>
        <h2>{r.message}</h2>
        {r.detail && <div className="detail">{r.detail}</div>}
        <div className="overall">
          <span>전체</span>
          <Bar value={r.progress} tone="s" label="지난 받기 전체 진행률" />
          <span className="mono">{r.done} / {r.total}{unit}</span>
        </div>
      </section>
    );
  }

  const reached = b.stage ? STEPS.indexOf(b.stage) : -1;
  const elapsed = b.convert_started_at ? Math.max(0, Math.floor(now - b.convert_started_at)) : 0;
  const pct = b.stage === "download" ? Math.round(b.percent * 100) : b.stage === "convert" ? 100 : 0;
  const title = b.stop_requested ? (b.stop_message ?? "중단하는 중…") : current?.title ?? "받을 준비 중…";

  const detail = (k: (typeof STEPS)[number]): string => {
    if (k === "download" && b.stage === "download") return `${(b.percent * 100).toFixed(1)}% · ${b.speed} · 남은 시간 ${b.eta}`;
    // 변환 진행률은 알 수 없다. 멈춘 것처럼 보이지 않게 경과 시간을 보인다
    if (k === "convert" && b.stage === "convert" && !b.stop_requested) return `FFmpeg · 경과 ${elapsed}초 · 곡 길이에 따라 수 분 걸릴 수 있습니다`;
    return "";
  };

  return (
    <section className="card now" aria-label="지금 받는 중" aria-live="polite">
      <div className="now-top">
        <div className="who">
          <span className="eyebrow"><span className="tracked">NOW</span> · {b.position} / {b.total}{unit}째</span>
          <h2 className={b.stop_requested ? "danger" : undefined}><Ellipsis title={current?.title}>{title}</Ellipsis></h2>
          {current?.uploader && <Ellipsis className="sub">{current.uploader}</Ellipsis>}
        </div>
        <div className="big-pct"><b>{pct}%</b><span>지금 곡</span></div>
      </div>
      <ol className="steps">
        {STEPS.map((k, i) => {
          const state = i < reached ? "done" : i === reached ? "run" : "wait";
          const d = detail(k);
          return (
            <li key={k} className={state}>
              <span className="step-no">{state === "done" ? "✓" : i + 1}</span>
              <div className="step-body">
                <div className="step-top">
                  <b>{k === "analyze" ? "분석" : k === "download" ? "다운로드" : convertLabel}</b>
                  <span className="step-state">{state === "done" ? "완료" : state === "run" ? "진행 중" : "대기"}</span>
                </div>
                {state === "run" && k !== "analyze" && (
                  <Bar value={k === "download" ? b.percent : b.stop_requested ? 0 : null} tone="p" big label="지금 곡 진행률" />
                )}
                {d && <span className="step-detail">{d}</span>}
              </div>
            </li>
          );
        })}
      </ol>
      <div className="overall">
        <span>전체</span>
        <Bar value={b.overall} tone="s" label="전체 진행률" />
        <span className="mono">{Math.round(b.overall * 100)}%</span>
      </div>
    </section>
  );
}
