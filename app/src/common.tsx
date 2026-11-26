// 네 앱이 같이 쓰는 화면 부품. (공통 파일: 네 앱이 같은 내용을 쓴다. 모양은 base.css. docs/STRUCTURE.md)
// 앱 고유 부품(로고, 아이콘 모음, 앱 전용 부품)은 ui.tsx에 두고, ui.tsx가 이 파일을 다시 내보낸다.

import { type ReactNode, useEffect, useRef, useState } from "react";

/** 선 아이콘 하나(24×24 path). 굵기는 --icon-stroke 토큰, width를 주면 그 값. 색은 글자 색을 따른다. */
export function Icon({ d, size = 16, stroke, width, className }: {
  d: string; size?: number; stroke?: string; width?: number; className?: string;
}) {
  return (
    <svg aria-hidden width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={stroke ?? "currentColor"}
      strokeLinecap="round" strokeLinejoin="round" className={`ic${className ? ` ${className}` : ""}`}
      style={width === undefined ? undefined : { strokeWidth: width }}>
      <path d={d} />
    </svg>
  );
}

const INFO = "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18M12 8h.01M11 12h1v5h1";
const ALERT = "M12 3 2 20h20zM12 10v4M12 17h.01";

/** 자간은 라틴 대문자에만 준다: "REVIEW · 21:37 완료" → 자간 있는 "REVIEW" + 나머지. */
export function tracked(text: string): ReactNode {
  const parts = text.split(/([A-Z][A-Z0-9]*(?: [A-Z][A-Z0-9]*)*)/);
  return parts.map((p, i) => (i % 2 ? <span className="tracked" key={i}>{p}</span> : p));
}

function Head({ eyebrow, title, actions }: { eyebrow: ReactNode; title: ReactNode; actions?: ReactNode }) {
  return (
    <header className="head">
      <div className="head-title">
        <span className="eyebrow">{typeof eyebrow === "string" ? tracked(eyebrow) : eyebrow}</span>
        <h1>{title}</h1>
      </div>
      {actions && <div className="head-actions">{actions}</div>}
    </header>
  );
}

/** 화면 뼈대 ①: 머리글 + 통째로 스크롤되는 패널. 설정·검수처럼 내용이 긴 화면. */
export function Page({ eyebrow, title, actions, children, wide, label = "본문" }: {
  eyebrow: ReactNode; title: ReactNode; actions?: ReactNode; children: ReactNode; wide?: boolean; label?: string;
}) {
  return (
    <>
      <Head eyebrow={eyebrow} title={title} actions={actions} />
      <div className="panel" role="region" aria-label={label} tabIndex={0}>
        <div className={`inner${wide ? " wide" : ""}`}>{children}</div>
      </div>
    </>
  );
}

/** 화면 뼈대 ②: 머리글 + 패널(도구 → 목록(.list)만 스크롤 → 하단 동작 바). 대기열·파일 목록처럼 항목이 많은 화면. */
export function Screen({ eyebrow, title, actions, children, bar }: {
  eyebrow: ReactNode; title: string; actions?: ReactNode; children: ReactNode; bar: ReactNode;
}) {
  return (
    <section className="screen" aria-label={title}>
      <Head eyebrow={eyebrow} title={title} actions={actions} />
      <div className="panel">
        <div className="screen-body">{children}</div>
        <footer className="action-bar">{bar}</footer>
      </div>
    </section>
  );
}

export function Chip({ active, onClick, children, disabled, className }: {
  active: boolean; onClick: () => void; children: ReactNode; disabled?: boolean; className?: string;
}) {
  return (
    <button type="button" className={`chip${className ? ` ${className}` : ""}`} aria-pressed={active} onClick={onClick} disabled={disabled}>
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
    <input ref={ref} type="checkbox" className="checkbox" checked={checked} disabled={disabled} aria-label={label}
      onChange={(e) => onChange(e.target.checked)} onClick={(e) => e.stopPropagation()} />
  );
}

/** 진행 바. value가 null이면 얼마나 남았는지 모르므로 좌우로 움직인다. tone "s"는 보조 네온. */
export function Bar({ value, tone, label, big }: { value: number | null; tone?: "p" | "s"; label?: string; big?: boolean }) {
  const pct = value === null ? undefined : Math.round(Math.min(1, Math.max(0, value)) * 100);
  return (
    <span className={`bar${tone === "s" ? " s" : ""}${big ? " big" : ""}${value === null ? " busy" : ""}`}
      {...(label ? { role: "progressbar", "aria-label": label, "aria-valuemin": 0, "aria-valuemax": 100, "aria-valuenow": pct } : { "aria-hidden": true })}>
      <span style={value === null ? undefined : { width: `${Math.min(1, Math.max(0, value)) * 100}%` }} />
    </span>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

/** 안내 한 줄. tone이 없으면 정보(보조 네온), warn·err는 상태 색. */
export function Note({ tone, children }: { tone?: "warn" | "err"; children: ReactNode }) {
  return (
    <div role="note" className={`note${tone ? ` ${tone}` : ""}`}>
      <Icon d={tone ? ALERT : INFO} size={15} />
      <span className="grow">{children}</span>
    </div>
  );
}

/** 글자 수로 자르지 않는다. 말줄임은 CSS(text-overflow)가 맡는다. */
export function Ellipsis({ children, title, className }: { children: ReactNode; title?: string; className?: string }) {
  return <span className={`ellipsis${className ? ` ${className}` : ""}`} title={title}>{children}</span>;
}

/** 앱 안 확인 창. Esc·바깥 누르기로 닫힌다. 처음 초점: data-autofocus → 주 동작 → 첫 버튼. */
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

/** 잠깐 떴다 사라지는 알림. [놓을 자리, 띄우는 함수]를 돌려준다. */
export function useToast(): [ReactNode, (text: string, bad?: boolean) => void] {
  const [t, setT] = useState<{ text: string; bad: boolean } | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const show = (text: string, bad = false) => {
    setT({ text, bad });
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setT(null), 3000);
  };
  const node = t ? <div className={`toast${t.bad ? " err" : ""}`} role="status">{t.text}</div> : null;
  return [node, show];
}
