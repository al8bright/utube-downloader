import { useState } from "react";
import { api, type FileEntry } from "./api";
import { useApp } from "./ctx";
import { ICONS } from "./icons";
import { FILE_SORTS, type FileSort, filterSortFiles, formatFileDate, formatSize } from "./format";
import { Chip, Ellipsis, Empty, Icon, Modal, Screen } from "./ui";

const SPEC = {
  audio: { title: "음성", word: "음성", exts: ["전체", "MP3", "FLAC"], empty: "받은 음성 파일이 없습니다." },
  video: { title: "영상", word: "영상", exts: [] as string[], empty: "받은 영상 파일이 없습니다." },
};

/** 무손실·영상은 보조 네온, MP3 는 무채색 */
const extBadge = (ext: string) => (ext === "MP3" ? "badge" : "badge s");

export function FilesScreen({ kind }: { kind: "audio" | "video" }) {
  const { data, files, act, refreshFiles } = useApp();
  const spec = SPEC[kind];
  const [query, setQuery] = useState("");
  const [ext, setExt] = useState("전체");
  const [sort, setSort] = useState<FileSort>("recent");
  const [askDelete, setAskDelete] = useState<FileEntry | null>(null);
  const [askAll, setAskAll] = useState(false);
  const [typed, setTyped] = useState("");

  const entries = files?.[kind] ?? [];
  const shown = filterSortFiles(entries, query, ext, sort);
  const total = entries.reduce((n, e) => n + e.size, 0);
  const running = data.batch.running;
  const newSince = files?.session_started_at ?? data.session_started_at;

  let empty = spec.empty;
  if (files && !files.ok) empty = files.error ?? "저장 폴더를 찾을 수 없습니다.";
  else if (files?.error) empty = files.error;
  else if (entries.length) empty = "찾는 조건에 맞는 파일이 없습니다.";

  const deleteOne = async (e: FileEntry) => {
    setAskDelete(null);
    await act(() => api.post("/files/delete", { name: e.name }));
    await refreshFiles();
  };
  const deleteAll = async () => {
    setAskAll(false);
    setTyped("");
    await act(() => api.post("/files/delete-kind", { kind }));
    await refreshFiles();
  };

  return (
    <Screen title={`받은 파일 · ${spec.title}`} tag="LIBRARY"
      summary={entries.length ? `${spec.word} ${entries.length}개 · ${formatSize(total)}` : undefined}
      aside={<button className="btn cyan-ghost" onClick={() => act(() => api.post("/open/folder"))}><Icon d={ICONS.folder} size={14} /> 폴더 열기</button>}
      bar={<>
        <span className="path-note"><span>저장 위치</span><Ellipsis title={files?.dir}>{files?.dir ?? data.settings.save_dir}</Ellipsis></span>
        <span className="spacer" />
        <button className="btn bare danger" disabled={running || !entries.length} title={running ? "받는 중에는 지울 수 없습니다" : undefined}
          onClick={() => setAskAll(true)}>목록 전체 삭제…</button>
      </>}>
      <div className="toolbar">
        <input className="field find" value={query} onChange={(e) => setQuery(e.target.value)}
          placeholder="파일 이름으로 찾기" aria-label="파일 이름으로 찾기" />
        {spec.exts.map((x) => (
          <Chip key={x} active={ext === x} onClick={() => setExt(x)}>
            {x} <span className="n">{x === "전체" ? entries.length : entries.filter((e) => e.ext === x).length}</span>
          </Chip>
        ))}
        <span className="grow" />
        <select className="field" value={sort} onChange={(e) => setSort(e.target.value as FileSort)} aria-label="정렬">
          {Object.entries(FILE_SORTS).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </select>
      </div>

      <div className="cols f-cols col-head" aria-hidden>
        <span>형식</span><span>파일 이름</span><span>크기</span><span>받은 날</span><span />
      </div>
      <div className="list" role="list" aria-label={`${spec.title} 파일`}>
        {shown.length ? shown.map((e) => (
          <div role="listitem" key={e.name} className="row cols f-cols f-row">
            <span><span className={extBadge(e.ext)}>{e.ext}</span></span>
            <span className="name-cell">
              <Ellipsis title={e.name}>{e.name}</Ellipsis>
              {e.mtime >= newSince && <span className="badge ok">새로 받음</span>}
            </span>
            <span className="size">{formatSize(e.size)}</span>
            <span className="date">{formatFileDate(e.mtime)}</span>
            <span className="acts">
              <button className="btn sm cyan-ghost" onClick={() => act(() => api.post("/open/file", { name: e.name }))}>
                <Icon d={ICONS.play} size={11} /> 재생
              </button>
              <button className="btn sm danger" disabled={running} title={running ? "받는 중에는 지울 수 없습니다" : undefined}
                onClick={() => setAskDelete(e)}>삭제</button>
            </span>
          </div>
        )) : <Empty>{empty}</Empty>}
      </div>

      {askDelete && (
        <Modal title="이 파일을 지울까요?" onClose={() => setAskDelete(null)}
          actions={<>
            <button className="btn" data-autofocus onClick={() => setAskDelete(null)}>취소</button>
            <button className="btn danger-solid" onClick={() => deleteOne(askDelete)}>삭제</button>
          </>}>
          <span className="mono">{askDelete.name}</span>
          {"\n\n휴지통을 거치지 않고 바로 지웁니다. 되돌릴 수 없습니다."}
        </Modal>
      )}
      {askAll && (
        <Modal title={`${spec.word} 파일 전체 삭제`} onClose={() => { setAskAll(false); setTyped(""); }}
          actions={<>
            <button className="btn" onClick={() => { setAskAll(false); setTyped(""); }}>취소</button>
            <button className="btn danger-solid" disabled={typed.trim() !== "삭제"} onClick={deleteAll}>모두 삭제</button>
          </>}>
          {`다음 폴더의 ${entries.length}개 ${spec.word} 파일을 영구 삭제합니다.\n${files?.dir ?? ""}\n\n`
            + `이 폴더의 모든 ${spec.word} 파일이 대상입니다. 앱이 받지 않은 파일도 포함됩니다.\n삭제하려면 아래 칸에 '삭제' 를 입력해 주세요.`}
          <input className="field" data-autofocus value={typed} onChange={(e) => setTyped(e.target.value)} aria-label="확인 문구" />
        </Modal>
      )}
    </Screen>
  );
}
