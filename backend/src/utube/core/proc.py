"""하위 프로세스의 수명 관리. (공통 파일: 네 앱이 같은 내용을 쓴다. docs/STRUCTURE.md)

백엔드가 띄운 프로세스(FFmpeg, llama-server 등)는 백엔드가 어떻게 끝나든(정상 종료, 강제 종료,
충돌) 함께 끝나야 한다. 남으면 GPU 메모리·포트·파일을 계속 잡는다.

Windows: KILL_ON_JOB_CLOSE Job Object를 쓴다. 핸들이 닫히면(=이 프로세스가 끝나면) Job 안의
프로세스가 모두 끝난다. 두 가지로 쓴다.
  - bind_self_to_job(): 이 프로세스 자신을 넣는다. 그 뒤에 띄우는 자식은 모두 자동으로 들어간다.
    라이브러리가 FFmpeg를 직접 띄워 핸들을 주지 않을 때(yt-dlp)도 잡힌다. `serve`가 시작할 때 부른다.
  - bind_to_lifetime(proc): 띄운 프로세스 하나를 넣는다. bind_self_to_job이 실패했을 때의 대비책.
macOS: Job Object가 없다. bind_to_lifetime으로 기억해 둔 프로세스를 서버 종료(lifespan), 정상 종료
(atexit), 부모 감시 종료 때 끝낸다. SIGKILL로 죽으면 남으므로, 앱은 먼저 SIGTERM을 보내고 3초 기다린다.
"""

from __future__ import annotations

import atexit
import os
import socket
import subprocess
import sys
import threading
import weakref

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

_job_handle = None
_job_lock = threading.Lock()
_self_bound = False


def _windows_job():
    """KILL_ON_JOB_CLOSE Job을 하나 만들어 돌려준다(한 번만). 실패하면 None."""
    global _job_handle
    with _job_lock:
        if _job_handle is not None:
            return _job_handle
        try:
            import ctypes
            from ctypes import wintypes

            class IO_COUNTERS(ctypes.Structure):
                _fields_ = [(n, ctypes.c_ulonglong) for n in (
                    "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                    "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

            class BASIC(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD),
                ]

            class EXTENDED(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", BASIC), ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            # 64비트에서 HANDLE이 c_int로 잘리지 않도록 시그니처를 적는다
            k32.CreateJobObjectW.restype = wintypes.HANDLE
            k32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
            k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
            k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
            k32.GetCurrentProcess.restype = wintypes.HANDLE
            k32.OpenProcess.restype = wintypes.HANDLE
            k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            k32.CloseHandle.argtypes = [wintypes.HANDLE]

            job = k32.CreateJobObjectW(None, None)
            if not job:
                return None
            info = EXTENDED()
            info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
                k32.CloseHandle(job)
                return None
            # 핸들을 살려 둬야 Job이 유지된다. 프로세스가 끝나면 운영체제가 닫는다
            _job_handle = (k32, job)
            return _job_handle
        except Exception:
            return None


def bind_self_to_job() -> bool:
    """이 프로세스와 앞으로 띄울 자식을 Job에 넣는다. Windows가 아니거나 실패하면 False."""
    global _self_bound
    if sys.platform != "win32":
        return False
    if _self_bound:
        return True
    job = _windows_job()
    if not job:
        return False
    k32, handle = job
    _self_bound = bool(k32.AssignProcessToJobObject(handle, k32.GetCurrentProcess()))
    return _self_bound


_children: weakref.WeakSet[subprocess.Popen] = weakref.WeakSet()
_children_lock = threading.Lock()


def bind_to_lifetime(proc: subprocess.Popen) -> None:
    """proc가 이 프로세스와 함께 끝나게 한다."""
    with _children_lock:
        _children.add(proc)
    if sys.platform != "win32" or _self_bound:
        return  # Windows에서 자신을 이미 묶었으면 자식은 자동으로 Job 안에 있다
    job = _windows_job()
    if not job:
        return
    k32, handle = job
    ph = k32.OpenProcess(0x0100 | 0x0001, False, proc.pid)  # SET_QUOTA | TERMINATE
    if ph:
        k32.AssignProcessToJobObject(handle, ph)
        k32.CloseHandle(ph)


def kill_children() -> None:
    """bind_to_lifetime으로 묶은 프로세스 중 아직 도는 것을 끝낸다."""
    with _children_lock:
        procs = list(_children)
    for p in procs:
        try:
            if p.poll() is None:
                p.kill()
        except OSError:
            pass


atexit.register(kill_children)


def ffmpeg_tree(procs: list[tuple[int, int, str]], root: int) -> list[int]:
    """root가 직접 띄운 ffmpeg와 그 자손 전부를 자손부터 돌려준다. procs는 (pid, 부모 pid, 실행 파일 이름).

    chocolatey처럼 ffmpeg.exe가 진짜 ffmpeg를 다시 띄우는 대리 실행 파일(shim)이면,
    shim만 끊어서는 진짜 ffmpeg가 남아 파일을 계속 쓴다.
    """
    children: dict[int, list[int]] = {}
    for pid, parent, _exe in procs:
        if pid != parent:
            children.setdefault(parent, []).append(pid)
    found: list[int] = []
    stack = [pid for pid, parent, exe in procs if parent == root and exe.startswith("ffmpeg")]
    while stack:
        pid = stack.pop()
        if pid in found or pid == root:
            continue
        found.append(pid)
        stack.extend(children.get(pid, []))
    return found[::-1]


def terminate_child_ffmpeg() -> int:
    """이 프로세스가 띄운 ffmpeg(와 그 자손)를 끝낸다. 끝낸 수를 돌려준다. Windows 전용.

    핸들 없이 띄워진 ffmpeg(yt-dlp 후처리 등)를 멈출 때 쓴다. 프로세스 목록에서 우리 자식 중
    ffmpeg만 찾아 끊으면, 그것을 기다리던 라이브러리가 예외를 내고 정상 경로로 빠져나온다.
    """
    if sys.platform != "win32":
        return 0
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260),
            ]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]

        snapshot = k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
        if not snapshot or snapshot == ctypes.c_void_p(-1).value:
            return 0
        procs: list[tuple[int, int, str]] = []
        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            ok = k32.Process32FirstW(snapshot, ctypes.byref(entry))
            while ok:
                procs.append((entry.th32ProcessID, entry.th32ParentProcessID, entry.szExeFile.lower()))
                ok = k32.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            k32.CloseHandle(snapshot)

        killed = 0
        for pid in ffmpeg_tree(procs, os.getpid()):
            handle = k32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
            if handle:
                if k32.TerminateProcess(handle, 1):
                    killed += 1
                k32.CloseHandle(handle)
        return killed
    except Exception:
        return 0


def exit_when_parent_dies(pid: int) -> None:
    """앱(Tauri)이 끝나면 이 프로세스도 끝낸다.

    개발 실행에서는 Tauri가 `uv`를 띄우고 uv가 파이썬을 띄우므로, Tauri가 uv만 끊으면 파이썬이
    남는다. 부모를 직접 지켜보다 사라지면 자식을 정리하고 스스로 나간다(os._exit는 atexit을 건너뛴다).
    """

    def watch() -> None:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            k = ctypes.WinDLL("kernel32", use_last_error=True)
            k.OpenProcess.restype = wintypes.HANDLE
            h = k.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE. 실패하면 부모가 이미 없다
            if h:
                k.WaitForSingleObject(h, 0xFFFFFFFF)
        else:
            import time

            while True:
                try:
                    os.kill(pid, 0)
                except OSError:
                    break
                time.sleep(1.0)
        kill_children()
        terminate_child_ffmpeg()
        os._exit(0)

    threading.Thread(target=watch, name="parent-watch", daemon=True).start()


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def open_with_shell(target: str) -> None:
    """기본 프로그램으로 연다(파일은 연결된 프로그램, 폴더는 탐색기·Finder, 주소는 브라우저)."""
    if sys.platform == "win32":
        os.startfile(target)  # noqa: S606 - 화면이 고른 파일·폴더·주소만 들어온다
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", target])
