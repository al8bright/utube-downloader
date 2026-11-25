import { useEffect, useMemo, useRef, useState } from "react";
import { api, type SearchResult, type WithMessage } from "./api";
import { useApp } from "./ctx";
import { ICONS } from "./icons";
import { Bar, Check, Empty, Icon, Screen } from "./ui";

const LIMIT = 100; // 백엔드 SEARCH_LIMIT 과 같다
const EMPTY: Set<string> = new Set();
const HINT = "링크를 붙여넣으면 검색하지 않고 바로 대기열에 담습니다.";

export function SearchScreen() {
  const { data, search, act, alert, go } = useApp();
  const [query, setQuery] = useState("");
  // 선택은 검색 세대와 묶는다. 새 검색이 시작되면 옛 선택은 의미가 없다
  const [pick, setPick] = useState<{ gen: number; ids: Set<string> }>({ gen: 0, ids: new Set() });
  const picked = pick.gen === search.generation ? pick.ids : EMPTY;
  const setPicked = (next: Set<string> | ((cur: Set<string>) => Set<string>)) =>
    setPick((cur) => {
      const base = cur.gen === search.generation ? cur.ids : EMPTY;
      return { gen: search.generation, ids: typeof next === "function" ? next(base) : next };
    });
  const failShown = useRef(0);

  useEffect(() => {
    if (search.status === "failed" && failShown.current !== search.generation) {
      failShown.current = search.generation;
      alert(`유튜브 검색에 실패했습니다.\n\n${search.error ?? ""}`);
    }
  }, [search.status, search.generation, search.error, alert]);

  const queuedIds = useMemo(() => new Set(data.items.map((i) => i.video_id).filter(Boolean)), [data.items]);
  const hide = data.settings.hide_queued;
  const rows = hide ? search.results.filter((r) => !queuedIds.has(r.id)) : search.results;
  const running = search.status === "running";
  const pickedCount = [...picked].filter((id) => !queuedIds.has(id)).length;

  const submit = async () => {
    const r = await act(() => api.post<{ generation?: number; queued?: WithMessage & { id: string } }>("/search", { query }));
    if (r?.queued) {
      setQuery("");
      if (r.queued.message) alert(r.queued.message);
      go("queue");
    }
  };

  const add = async () => {
    const ids = [...picked].filter((id) => !queuedIds.has(id));
    const r = await act(() => api.post("/queue/results", { ids }));
    if (r) {
      setPicked(new Set());
      go("queue"); // 담은 곡을 바로 확인할 수 있게 넘어간다
    }
  };

  const toggle = (id: string) => setPicked((cur) => {
    const next = new Set(cur);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });

  let empty = "검색 결과가 없습니다. 키워드를 입력하고 검색해 주세요.";
  if (running) empty = "유튜브에서 찾는 중…";
  else if (search.status === "done" && !search.results.length) empty = "일치하는 영상을 찾지 못했습니다. 다른 키워드로 검색해 보세요.";
  else if (search.results.length && !rows.length) empty = "아직 담지 않은 결과가 없습니다.";

  return (
    <Screen title="검색" tag="SEARCH" summary={search.results.length ? `결과 ${search.results.length}개` : undefined}
      bar={<>
        <span className="bar-count">{pickedCount ? `${pickedCount}개 선택` : "선택한 곡 없음"}</span>
        <span className="bar-hint">형식과 저장 위치는 대기열 화면에서 정합니다</span>
        <span className="spacer" />
        <button className="btn primary lg" disabled={!pickedCount} onClick={add}>대기열에 추가</button>
      </>}>
      <form className="search-bar" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
        <input className="field big grow" value={query} onChange={(e) => setQuery(e.target.value)} autoFocus
          placeholder="키워드로 검색하거나 유튜브 링크를 붙여넣으세요" aria-label="검색어 또는 유튜브 링크" />
        {/* 주 동작(분홍)은 '대기열에 추가' 하나. 검색은 보조 네온으로 둔다 */}
        <button className="btn cyan lg search-go" type="submit">{running ? "다시 검색" : "검색"}</button>
      </form>

      <div className="search-status" aria-live="polite">
        {running && <Bar value={search.results.length ? search.results.length / LIMIT : null} tone="s" label="검색 진행" />}
        <span className="hint">
          {running ? (search.results.length ? `찾는 중… ${search.results.length}개 받음` : "유튜브에서 찾는 중…") : HINT}
        </span>
      </div>

      <div className="toolbar">
        <label className="check-label">
          <Check checked={hide} label="이미 담은 곡 숨기기" onChange={(v) => act(() => api.put("/settings", { hide_queued: v }))} />
          이미 담은 곡 숨기기
        </label>
        {!!rows.length && (
          <button className="btn sm push"
            onClick={() => setPicked(pickedCount ? new Set() : new Set(rows.filter((r) => !queuedIds.has(r.id)).map((r) => r.id)))}>
            {pickedCount ? "선택 해제" : "모두 선택"}
          </button>
        )}
      </div>

      <div className="list" role="list" aria-label="검색 결과">
        {rows.length ? rows.map((r) => (
          <ResultRow key={r.id} r={r} queued={queuedIds.has(r.id)} picked={picked.has(r.id)} onToggle={() => toggle(r.id)} />
        )) : <Empty>{empty}</Empty>}
      </div>
    </Screen>
  );
}

function ResultRow({ r, queued, picked, onToggle }: { r: SearchResult; queued: boolean; picked: boolean; onToggle: () => void }) {
  const { act } = useApp();
  return (
    // 행 어디를 눌러도 체크가 바뀐다. 이미 담은 곡은 고를 수 없다
    <div role="listitem" className={`search-row${picked && !queued ? " picked" : ""}${queued ? " queued" : ""}`}
      onClick={queued ? undefined : onToggle}>
      <Check checked={picked && !queued} disabled={queued} label={r.title} onChange={onToggle} />
      <span className="thumb">
        <img src={r.thumbnail} alt="" loading="lazy" decoding="async" />
        <span className="dur">{r.duration}</span>
      </span>
      <span className="text">
        <span className="title" title={r.title}>{r.title}</span>
        <span className="sub">{r.uploader}</span>
      </span>
      {queued && <span className="badge s">대기열에 있음</span>}
      <button className="btn sm cyan-ghost" title="브라우저에서 미리 듣기"
        onClick={(e) => { e.stopPropagation(); void act(() => api.post("/open/url", { url: r.url })); }}>
        <Icon d={ICONS.play} size={11} /> 재생
      </button>
    </div>
  );
}
