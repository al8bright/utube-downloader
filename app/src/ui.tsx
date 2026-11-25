import { type ReactNode, useEffect, useRef } from "react";

export function Icon({ d, size = 16, className }: { d: string; size?: number; className?: string }) {
  return (
    <svg aria-hidden width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}
      strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d={d} />
    </svg>
  );
}

/** 꺾쇠(jamak 과 한 계열) + 재생 삼각형 + 채워지는 다운로드 막대. 색은 팔레트와 관계없이 고정이다. */
export function Logo({ size = 30 }: { size?: number }) {
  return (
    <svg className="mark" width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <path className="corner" d="M3 11V3h8M29 21v8h-8" />
      <path className="play" d="M12.5 8.5 L22.5 14.5 L12.5 20.5 Z" />
      <rect className="dl" x="9" y="24" width="14" height="2" />
    </svg>
  );
}

// ------------------------------------------------------------------ 화면 뼈대: 머리글 → 빛나는 패널(도구 → 목록 → 하단 동작 바)

/** eyebrow 는 영문 대문자 이름(자간 있음) + 한글 요약(자간 없음)으로 나눠 받는다. */
export function Screen({ title, tag, summary, aside, children, bar }: {
  title: string; tag: string; summary?: ReactNode; aside?: ReactNode; children: ReactNode; bar: ReactNode;
}) {
  return (
    <section className="screen" aria-label={title}>
      <header className="head">
        <div className="head-title">
          <span className="eyebrow"><span className="tracked">{tag}</span>{summary ? <> · {summary}</> : null}</span>
          <h1>{title}</h1>
        </div>
        {aside && <div className="head-actions">{aside}</div>}
      </header>
      <div className="panel">
        <div className="screen-body">{children}</div>
        <footer className="action-bar">{bar}</footer>
      </div>
    </section>
  );
}

export function Chip({ active, onClick, children, disabled }: {
  active: boolean; onClick: () => void; children: ReactNode; disabled?: boolean;
}) {
  return (
    <button type="button" className="chip" aria-pressed={active} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
}

export function Check({ checked, onChange, disabled, label, indeterminate }: {
  checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; label: string; indeterminate?: boolean;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = !!indeterminate;
  }, [indeterminate]);
  return (
    <input ref={ref} type="checkbox" className="check" checked={checked} disabled={disabled} aria-label={label}
      onChange={(e) => onChange(e.target.checked)} onClick={(e) => e.stopPropagation()} />
  );
}

/** 진행 바. value 가 null 이면 얼마나 남았는지 모르므로 좌우로 움직인다. p 는 지금 곡, s 는 전체 진행이다. */
export function Bar({ value, tone, label, big }: { value: number | null; tone: "p" | "s"; label: string; big?: boolean }) {
  const pct = value === null ? undefined : Math.round(Math.min(1, Math.max(0, value)) * 100);
  return (
    <div className={`bar ${tone}${big ? " big" : ""}${value === null ? " busy" : ""}`} role="progressbar" aria-label={label}
      aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
      <span style={value === null ? undefined : { width: `${pct}%` }} />
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

// ------------------------------------------------------------------ 모달 (앱 안에서만. 브라우저 대화상자는 쓰지 않는다)

export function Modal({ title, children, actions, onClose }: {
  title: string; children: ReactNode; actions: ReactNode; onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.querySelector<HTMLElement>("[data-autofocus], .btn.primary:not(:disabled), button:not(:disabled)")?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="scrim" onMouseDown={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title} ref={ref} onMouseDown={(e) => e.stopPropagation()}>
        <h2>{title}</h2>
        <div className="modal-body">{children}</div>
        <div className="modal-actions">{actions}</div>
      </div>
    </div>
  );
}

/** 글자 수로 자르지 않는다. 말줄임은 CSS(text-overflow)가 맡는다. */
export function Ellipsis({ children, title, className }: { children: ReactNode; title?: string; className?: string }) {
  return <span className={`ellipsis${className ? ` ${className}` : ""}`} title={title}>{children}</span>;
}
