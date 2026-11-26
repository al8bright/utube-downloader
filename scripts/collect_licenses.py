"""Collect the licenses of third-party code shipped in the installer.
(Shared file: the four apps use the same content. docs/STRUCTURE.md)

build_app.ps1 (and build_app.sh on a Mac) runs it three times and puts the results in the installer's licenses folder:

    uv export --no-dev --no-hashes --format requirements-txt | uv run python collect_licenses.py python OUT.txt
    python collect_licenses.py cargo app/src-tauri OUT.txt
    python collect_licenses.py npm app OUT.txt

python  Python packages frozen into the backend executable (runtime dependencies only, read from stdin,
        so pytest and PyInstaller are left out), plus the interpreter's own license.
cargo   Rust crates compiled into the app executable: normal dependencies of the app crate
        for the machine that builds (Windows x64, or Apple Silicon for the Mac app). Build scripts
        and dev dependencies are not shipped and are left out.
npm     JavaScript packages in package.json "dependencies" (bundled into the page by Vite).

Each output lists name, version, declared license and source URL, then the full license texts.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LICENSE_NAME = re.compile(r"^(licen[cs]e|copying|notice|copyright)", re.I)
RULE = "-" * 78


def _write(out: str, title: str, rows: list[str], texts: list[tuple[str, str]]) -> None:
    parts = [title, "=" * len(title), "", *rows, ""]
    for label, text in texts:
        parts += ["", RULE, label, RULE, text.rstrip()]
    Path(out).write_text("\n".join(parts) + "\n", encoding="utf-8", newline="\n")


def _license_files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.is_file() and LICENSE_NAME.match(p.name))


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------- python

def _own_name() -> str:
    """The backend's own package (listed by `uv export`, but it is ours, MIT)."""
    import tomllib

    with open(ROOT / "backend" / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["name"].lower()


def _requirement_names(lines: list[str]) -> list[str]:
    names = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith(("#", "-", ".")):
            continue
        name = re.split(r"[\s=<>!~;\[]", line, maxsplit=1)[0]
        if name and name.lower() != _own_name():
            names.append(name)
    return sorted(set(names), key=str.lower)


def _declared(dist: metadata.Distribution) -> str:
    md = dist.metadata
    if md.get("License-Expression"):
        return md["License-Expression"]
    found = [c.split("::")[-1].strip() for c in md.get_all("Classifier") or [] if c.startswith("License ::")]
    lic = (md.get("License") or "").strip()
    if lic and len(lic) < 100:
        found.insert(0, lic)
    return "; ".join(dict.fromkeys(found)) or "see license text"


def collect_python(out: str) -> None:
    rows, texts, skipped = [], [], []
    for name in _requirement_names(sys.stdin.read().splitlines()):
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            # Excluded on this platform by an environment marker (e.g. cffi on CPython).
            # Not installed, so PyInstaller does not bundle it either.
            skipped.append(name)
            continue
        label = f"{dist.metadata['Name']} {dist.version}"
        home = dist.metadata.get("Home-page") or next(
            (u.split(",", 1)[1].strip() for u in dist.metadata.get_all("Project-URL") or [] if "," in u), "")
        rows.append(f"{label}  —  {_declared(dist)}" + (f"\n  {home}" if home else ""))
        for f in dist.files or []:
            if LICENSE_NAME.search(f.name) and f.suffix.lower() in ("", ".txt", ".md", ".rst"):
                try:
                    texts.append((f"{label}: {f}", _read(Path(f.locate()))))
                except OSError:
                    pass
    py_license = Path(sys.base_prefix) / "LICENSE.txt"
    if py_license.is_file():
        rows.append(f"Python {sys.version.split()[0]}  —  PSF-2.0 (interpreter and standard library)")
        texts.append((f"Python {sys.version.split()[0]}: LICENSE.txt", _read(py_license)))
    _write(out, "Python packages bundled in the backend executable", rows, texts)
    if skipped:
        print(f"skipped (not installed on this platform): {', '.join(skipped)}")


# ---------------------------------------------------------------------- cargo

def _host_triple() -> str:
    """The Rust target this machine builds for, e.g. x86_64-pc-windows-msvc or aarch64-apple-darwin."""
    info = subprocess.run(["rustc", "-vV"], capture_output=True, text=True, check=True).stdout
    return next(line.split(":", 1)[1].strip() for line in info.splitlines() if line.startswith("host:"))


def collect_cargo(manifest_dir: str, out: str) -> None:
    raw = subprocess.run(
        ["cargo", "metadata", "--format-version", "1", "--locked", "--filter-platform", _host_triple()],
        cwd=manifest_dir, capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout
    meta = json.loads(raw)
    pkgs = {p["id"]: p for p in meta["packages"]}
    nodes = {n["id"]: n for n in meta["resolve"]["nodes"]}
    root = meta["resolve"]["root"]

    # Walk normal (shipped) dependencies only: dep_kinds kind == null
    seen, stack = set(), [root]
    while stack:
        nid = stack.pop()
        for dep in nodes[nid]["deps"]:
            if any(k["kind"] is None for k in dep["dep_kinds"]) and dep["pkg"] not in seen:
                seen.add(dep["pkg"])
                stack.append(dep["pkg"])

    rows, texts = [], []
    for pid in sorted(seen, key=lambda i: (pkgs[i]["name"], pkgs[i]["version"])):
        p = pkgs[pid]
        label = f"{p['name']} {p['version']}"
        rows.append(f"{label}  —  {p.get('license') or 'see license text'}"
                    + (f"\n  {p['repository']}" if p.get("repository") else ""))
        folder = Path(p["manifest_path"]).parent
        files = _license_files(folder)
        if p.get("license_file"):
            files.append(folder / p["license_file"])
        for f in dict.fromkeys(files):
            if f.is_file():
                texts.append((f"{label}: {f.name}", _read(f)))
    _write(out, "Rust crates compiled into the app executable", rows, texts)


# ---------------------------------------------------------------------- npm

def collect_npm(app_dir: str, out: str) -> None:
    app = Path(app_dir)
    deps = json.loads(_read(app / "package.json")).get("dependencies", {})
    rows, texts = [], []
    for name in sorted(deps):
        folder = app / "node_modules" / name
        pkg = json.loads(_read(folder / "package.json"))
        label = f"{name} {pkg.get('version', '?')}"
        repo = pkg.get("repository")
        repo = repo.get("url") if isinstance(repo, dict) else repo
        rows.append(f"{label}  —  {pkg.get('license') or 'see license text'}" + (f"\n  {repo}" if repo else ""))
        for f in _license_files(folder):
            texts.append((f"{label}: {f.name}", _read(f)))
    _write(out, "JavaScript packages and fonts bundled into the app window", rows, texts)


def main() -> None:
    args = sys.argv[1:]
    if args[:1] == ["python"] and len(args) == 2:
        collect_python(args[1])
    elif args[:1] == ["cargo"] and len(args) == 3:
        collect_cargo(args[1], args[2])
    elif args[:1] == ["npm"] and len(args) == 3:
        collect_npm(args[1], args[2])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
