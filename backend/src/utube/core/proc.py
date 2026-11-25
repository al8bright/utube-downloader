"""Windows 프로세스 처리.

이 백엔드가 띄운 ffmpeg 자식 프로세스의 수명을 다룬다.
Windows 는 부모가 죽어도 자식을 종료하지 않으므로 명시적으로 묶고 끊어야 한다.
"""

from __future__ import annotations

import os
import socket
import sys
import threading

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

_job_handle = None


def bind_self_to_job() -> bool:
    """이 프로세스와 앞으로 띄울 자식(ffmpeg)을 KILL_ON_JOB_CLOSE Job 에 넣는다.

    yt-dlp 는 ffmpeg 를 직접 띄우고 핸들을 내주지 않으므로 자식을 하나씩 묶을 수 없다.
    자기 자신을 Job 에 넣어 두면 앱이 어떤 식으로 끝나든(종료, 강제 종료, 충돌)
    핸들이 닫히며 ffmpeg 도 함께 정리된다.
    """
    global _job_handle
    if sys.platform != "win32" or _job_handle is not None:
        return _job_handle is not None
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
        # 64비트에서 HANDLE 이 c_int 로 잘리지 않도록 시그니처를 명시한다
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.CloseHandle.argtypes = [wintypes.HANDLE]

        job = k32.CreateJobObjectW(None, None)
        if not job:
            return False
        info = EXTENDED()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
            k32.CloseHandle(job)
            return False
        if not k32.AssignProcessToJobObject(job, k32.GetCurrentProcess()):
            k32.CloseHandle(job)
            return False
        # 핸들을 살려 둬야 Job 이 유지된다. 프로세스가 끝나면 닫히며 자식이 정리된다
        _job_handle = job
        return True
    except Exception:
        return False


def ffmpeg_tree(procs: list[tuple[int, int, str]], root: int) -> list[int]:
    """root 가 직접 띄운 ffmpeg 와 그 ffmpeg 의 자손 전부를 자손부터 돌려준다.

    chocolatey 처럼 ffmpeg.exe 가 진짜 ffmpeg 를 다시 띄우는 대리 실행 파일(shim)이면,
    shim 만 끊어서는 진짜 ffmpeg 가 남아 파일을 계속 쓴다.
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
    """이 프로세스가 띄운 ffmpeg 자식 프로세스를 종료한다. 종료한 수를 돌려준다.

    yt-dlp 는 후처리에서 ffmpeg 를 블로킹 실행하고, 그동안 progress_hook 이 불리지 않아
    중단 플래그가 먹히지 않는다. 프로세스 스냅샷에서 우리 자식 중 ffmpeg 만 찾아 끊으면
    yt-dlp 가 예외를 내고 정상 경로로 빠져나온다.
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
        my_pid = os.getpid()
        procs: list[tuple[int, int, str]] = []  # (pid, parent, exe)
        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            ok = k32.Process32FirstW(snapshot, ctypes.byref(entry))
            while ok:
                procs.append((entry.th32ProcessID, entry.th32ParentProcessID, entry.szExeFile.lower()))
                ok = k32.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            k32.CloseHandle(snapshot)
        targets = ffmpeg_tree(procs, my_pid)

        killed = 0
        for pid in targets:
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

    개발 실행에서는 Tauri 가 `uv` 를 띄우고 uv 가 파이썬을 띄우므로, Tauri 가 uv 만 끊으면
    파이썬은 남는다. 부모를 직접 지켜보다 사라지면 스스로 나간다.
    """

    def watch() -> None:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            k = ctypes.WinDLL("kernel32", use_last_error=True)
            k.OpenProcess.restype = wintypes.HANDLE
            h = k.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
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
        terminate_child_ffmpeg()
        os._exit(0)

    threading.Thread(target=watch, name="parent-watch", daemon=True).start()


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def open_with_shell(target: str) -> None:
    """기본 프로그램으로 연다(파일은 재생기, 폴더는 탐색기, 주소는 브라우저)."""
    if sys.platform == "win32":
        os.startfile(target)  # noqa: S606 - 화면이 고른 파일·폴더·유튜브 주소만 들어온다
    else:
        import subprocess

        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", target])
