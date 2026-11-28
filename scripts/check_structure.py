"""네 앱(jamak, utube, videoconverter, audioconverter)이 같은 구조인지 확인한다.
(공통 파일: 네 앱이 같은 내용을 쓴다. 기준 문서는 jamak_converter/docs/STRUCTURE.md)

    python scripts/check_structure.py              이 저장소 확인 + 옆 폴더의 다른 앱과 공통 파일 비교
    python scripts/check_structure.py --diff       다른 곳을 diff로 보여 준다
    python scripts/check_structure.py --copy-from jamak_converter
                                                   그 폴더의 공통 파일을 이 저장소로 복사한다(이름은 바꿔서)

확인하는 것
  1. 있어야 하는 파일이 있는지
  2. 앱 이름·포트가 app_info.py, app_info.rs, appInfo.ts, tauri.conf.json에서 서로 맞는지
  3. 공통 파일이 옆 폴더의 다른 앱과 같은지(폴더 이름이 아니라 백엔드 패키지 이름으로 찾는다). 줄 끝(CRLF/LF)은 무시하고, 앱 이름이 든 파일(NAMED)은
     이름을 바꿔 비교한다
문제가 있으면 종료 코드 1. 표준 라이브러리만 쓴다.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 백엔드 패키지 이름(backend/src/<패키지>). 새 앱을 만들면 여기에 더한다(네 저장소 모두).
# 옆 폴더는 이름이 아니라 이 패키지로 알아본다 — clone한 폴더 이름은 PC마다 다를 수 있다
# (예: youtube_down, utube-downloader)
APPS = {"jamak", "utube", "videoconverter", "audioconverter"}

# 네 앱이 같은 내용을 쓰는 파일. {pkg}는 백엔드 패키지 이름
SHARED = [
    ".gitattributes",
    ".github/workflows/ci.yml",
    "LICENSE",
    "scripts/check_structure.py",
    "scripts/collect_licenses.py",
    "backend/packaging/entry.py",
    "backend/src/{pkg}/api/base.py",
    "backend/src/{pkg}/core/proc.py",
    "backend/tests/test_common.py",
    "app/.gitignore",
    "app/.oxlintrc.json",
    "app/tsconfig.json",
    "app/tsconfig.app.json",
    "app/tsconfig.node.json",
    "app/vite.config.ts",
    "app/src/backend.ts",
    "app/src/common.tsx",
    "app/src/base.css",
    "app/src-tauri/.gitignore",
    "app/src-tauri/build.rs",
    "app/src-tauri/src/lib.rs",
    "app/src-tauri/src/main.rs",
]

# 공통 파일 중 앱 이름이 들어 있는 것. 이름만 바꿔(jamak -> utube) 비교·복사한다.
# 나머지 공통 파일에는 앱 이름을 쓰지 않는다(이름은 app_info에서 읽는다)
NAMED = {"backend/packaging/entry.py"}

# 앱마다 내용은 다르지만 있어야 하는 파일
REQUIRED = [
    "README.md",
    "DESIGN.md",
    "THIRD_PARTY_NOTICES.md",
    ".gitignore",
    "scripts/build_app.ps1",
    "backend/pyproject.toml",
    "backend/uv.lock",
    "backend/packaging/{pkg}-backend.spec",
    "backend/src/{pkg}/__init__.py",
    "backend/src/{pkg}/app_info.py",
    "backend/src/{pkg}/cli.py",
    "backend/src/{pkg}/config.py",
    "backend/src/{pkg}/api/server.py",
    "backend/tests/conftest.py",
    "app/package.json",
    "app/pnpm-lock.yaml",
    "app/index.html",
    "app/src/main.tsx",
    "app/src/App.tsx",
    "app/src/api.ts",
    "app/src/appInfo.ts",
    "app/src/ctx.ts",
    "app/src/ui.tsx",
    "app/src/index.css",
    "app/src-tauri/Cargo.toml",
    "app/src-tauri/Cargo.lock",
    "app/src-tauri/tauri.conf.json",
    "app/src-tauri/capabilities/default.json",
    "app/src-tauri/src/app_info.rs",
]


def read(p: Path) -> str:
    """줄 끝은 LF로 맞춰 읽는다(Windows 체크아웃은 CRLF일 수 있다)."""
    return p.read_text(encoding="utf-8").replace("\r\n", "\n")


def own_pkg(root: Path) -> str | None:
    found = [p.parent.name for p in (root / "backend" / "src").glob("*/app_info.py")]
    return found[0] if len(found) == 1 else None


def normalize(text: str, pkg: str) -> str:
    """줄 끝과 앱 이름을 지운다. jamak -> {pkg}, JAMAK -> {PKG}, Jamak -> {Pkg}."""
    text = text.replace("\r\n", "\n")
    for name, token in ((pkg, "{pkg}"), (pkg.upper(), "{PKG}"), (pkg.capitalize(), "{Pkg}")):
        text = re.sub(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", token, text)
    return text


def denormalize(text: str, pkg: str) -> str:
    return text.replace("{pkg}", pkg).replace("{PKG}", pkg.upper()).replace("{Pkg}", pkg.capitalize())


def read_values(root: Path, pkg: str) -> dict[str, dict[str, object]]:
    """각 파일에 적힌 이름·포트."""
    out: dict[str, dict[str, object]] = {}

    def grab(rel: str, patterns: dict[str, str]) -> None:
        p = root / rel
        if not p.exists():
            return
        text = p.read_text(encoding="utf-8")
        vals: dict[str, object] = {}
        for key, pat in patterns.items():
            m = re.search(pat, text, re.M)
            if m:
                v = m.group(1)
                vals[key] = int(v) if v.isdigit() else v
        out[rel] = vals

    grab(f"backend/src/{pkg}/app_info.py", {
        "name": r'^NAME = "([^"]+)"', "env": r'^ENV = "([^"]+)"', "port": r"^PORT = (\d+)", "vite": r"^VITE_PORT = (\d+)"})
    grab("app/src/appInfo.ts", {
        "name": r'export const NAME = "([^"]+)"', "port": r"export const DEV_BACKEND_PORT = (\d+)",
        "vite": r"export const VITE_PORT = (\d+)"})
    grab("app/src-tauri/src/app_info.rs", {
        "env": r'pub const ENV: &str = "([^"]+)"', "name": r'pub const CLI: &str = "([^"]+)"'})
    conf = root / "app/src-tauri/tauri.conf.json"
    if conf.exists():
        c = json.loads(conf.read_text(encoding="utf-8"))
        m = re.search(r":(\d+)", c.get("build", {}).get("devUrl", ""))
        res = " ".join(c.get("bundle", {}).get("resources", {}) or {})
        r = re.search(r"backend/dist/([^/]+)-backend/", res)
        out["app/src-tauri/tauri.conf.json"] = {
            **({"vite": int(m.group(1))} if m else {}), **({"name": r.group(1)} if r else {})}
    return out


def check_values(root: Path, pkg: str) -> list[str]:
    problems = []
    values = read_values(root, pkg)
    want = {"name": pkg, "env": pkg.upper()}
    first = values.get(f"backend/src/{pkg}/app_info.py", {})
    want.update({k: first[k] for k in ("port", "vite") if k in first})
    for rel, vals in values.items():
        for key, v in vals.items():
            if key in want and v != want[key]:
                problems.append(f"{rel}: {key} = {v!r}, app_info.py와 다름({want[key]!r})")
    return problems


def siblings(pkg: str) -> dict[str, tuple[Path, str]]:
    """옆 폴더에 있고 이 구조로 바뀐 다른 앱. 키는 실제 폴더 이름이다."""
    out = {}
    for p in sorted(ROOT.parent.iterdir()):
        if p == ROOT or not (p / "app" / "src-tauri").is_dir():
            continue
        other = own_pkg(p)
        if other in APPS and other != pkg:
            out[p.name] = (p, other)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--diff", action="store_true", help="다른 곳을 diff로 보여 준다")
    ap.add_argument("--copy-from", metavar="FOLDER", help="이 저장소의 공통 파일을 FOLDER의 것으로 바꾼다")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    pkg = own_pkg(ROOT)
    if not pkg:
        print(f"backend/src/<패키지>/app_info.py를 찾지 못했습니다: {ROOT}")
        return 1
    others = siblings(pkg)

    if args.copy_from:
        if args.copy_from not in others:
            print(f"{args.copy_from}: 옆 폴더에 이 구조로 된 저장소가 없습니다. 있는 것: {', '.join(others) or '없음'}")
            return 1
        src, src_pkg = others[args.copy_from]
        for rel in SHARED:
            a = src / rel.format(pkg=src_pkg)
            if not a.exists():
                print(f"  건너뜀(원본 없음) {rel}")
                continue
            b = ROOT / rel.format(pkg=pkg)
            b.parent.mkdir(parents=True, exist_ok=True)
            text = read(a)
            if rel in NAMED:
                text = denormalize(normalize(text, src_pkg), pkg)
            if b.exists() and read(b) == text:
                continue
            b.write_text(text, encoding="utf-8", newline="\n")
            print(f"  복사 {rel.format(pkg=pkg)}")
        return 0

    bad = 0
    print(f"{ROOT.name} (패키지 {pkg})")
    missing = [r.format(pkg=pkg) for r in REQUIRED + SHARED if not (ROOT / r.format(pkg=pkg)).exists()]
    for r in missing:
        print(f"  없음    {r}")
    for p in check_values(ROOT, pkg):
        print(f"  안 맞음  {p}")
    bad += len(missing) + len(check_values(ROOT, pkg))

    if not others:
        print("  비교할 저장소가 옆 폴더에 없습니다.")
    for folder, (other_root, other_pkg) in others.items():
        diffs = []
        for rel in SHARED:
            a, b = ROOT / rel.format(pkg=pkg), other_root / rel.format(pkg=other_pkg)
            if not a.exists() or not b.exists():
                continue  # 없는 파일은 각 저장소가 따로 알린다
            x, y = read(a), read(b)
            if rel in NAMED:
                x, y = normalize(x, pkg), normalize(y, other_pkg)
            x, y = x.splitlines(), y.splitlines()
            if x != y:
                d = list(difflib.unified_diff(x, y, f"{ROOT.name}/{rel}", f"{folder}/{rel}", lineterm="", n=1))
                diffs.append((rel, sum(1 for line in d if line[:1] in "+-" and line[:3] not in ("+++", "---")), d))
        print(f"\n{folder}와 공통 파일 {len(SHARED)}개 비교: {'모두 같음' if not diffs else f'{len(diffs)}개 다름'}")
        for rel, n, d in diffs:
            print(f"  다름    {rel} ({n}줄)")
            if args.diff:
                print("\n".join("    " + line for line in d))
        bad += len(diffs)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
