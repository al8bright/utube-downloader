// 이 앱의 부품. 공통 부품(Icon, Screen, Modal …)은 common.tsx에 있고 여기서 다시 내보낸다.
import type { ReactNode } from "react";

export * from "./common";

/** 꺾쇠(jamak과 한 계열) + 재생 삼각형 + 채워지는 다운로드 막대. 색은 팔레트와 관계없이 고정이다. */
export function Logo({ size = 30 }: { size?: number }) {
  return (
    <svg className="mark" width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <path className="corner" d="M3 11V3h8M29 21v8h-8" />
      <path className="play" d="M12.5 8.5 L22.5 14.5 L12.5 20.5 Z" />
      <rect className="dl" x="9" y="24" width="14" height="2" />
    </svg>
  );
}

/** 머리글 위 작은 줄: 영문 대문자 이름(자간 있음) + 한글 요약(자간 없음). */
export function eyebrow(tag: string, summary?: ReactNode): ReactNode {
  return <><span className="tracked">{tag}</span>{summary ? <> · {summary}</> : null}</>;
}
