# PyInstaller spec (onedir). 빌드:  uv run pyinstaller packaging/utube-backend.spec
# ffmpeg.exe 는 여기서 넣지 않는다. scripts/build_app.ps1 이 결과 폴더(dist/utube-backend/)에 복사한다.
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hidden = (
    collect_submodules("utube")
    + collect_submodules("uvicorn")
    # yt-dlp 는 추출기·후처리기를 이름으로 불러온다. 정적 분석으로는 다 잡히지 않는다
    + collect_submodules("yt_dlp")
    + collect_submodules("yt_dlp_ejs")
    + ["websockets", "websockets.legacy", "httptools", "h11"]
)
# yt-dlp-ejs: 유튜브 서명 계산에 쓰는 JS 파일이 데이터로 들어 있다
datas = collect_data_files("yt_dlp_ejs") + collect_data_files("certifi")

a = Analysis(
    ["entry.py"],
    pathex=["../src"],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    excludes=["tkinter", "customtkinter", "matplotlib", "IPython", "pytest", "ruff", "PyInstaller"],
    noarchive=False,
)
pyz = PYZ(a.pure)
# console=True: Tauri 가 표준 출력으로 주소를 받는다. 창은 Tauri 가 CREATE_NO_WINDOW 로 숨긴다
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="utube-backend", console=True, upx=False,
          icon="../../app/src-tauri/icons/icon.ico")
coll = COLLECT(exe, a.binaries, a.datas, name="utube-backend", upx=False)
