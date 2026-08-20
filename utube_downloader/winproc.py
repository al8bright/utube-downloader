"""Windows 프로세스·리소스 처리.

이 앱이 띄운 ffmpeg 자식 프로세스의 수명을 다룬다.
Windows 는 부모가 죽어도 자식을 종료하지 않으므로 명시적으로 묶고 끊어야 한다.
"""
import os
import sys


def terminate_child_ffmpeg():
    """이 프로세스가 띄운 ffmpeg 자식 프로세스를 종료한다.

    yt-dlp 는 후처리에서 ffmpeg 를 블로킹 실행하고 핸들을 밖으로 내주지 않아,
    변환 구간에서는 progress_hook 이 호출되지 않아 중단 플래그가 먹히지 않는다.
    라이브러리 내부를 몽키패치하는 대신, 프로세스 스냅샷에서 우리 자식 중
    ffmpeg 만 찾아 종료한다. 종료되면 yt-dlp 가 예외를 내고 정상 경로로 빠져나온다.

    종료시킨 프로세스 수를 돌려준다.
    """
    if sys.platform != 'win32':
        return 0
    try:
        import ctypes
        from ctypes import wintypes

        TH32CS_SNAPPROCESS = 0x00000002
        PROCESS_TERMINATE = 0x0001
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ('dwSize', wintypes.DWORD),
                ('cntUsage', wintypes.DWORD),
                ('th32ProcessID', wintypes.DWORD),
                ('th32DefaultHeapID', ctypes.POINTER(ctypes.c_ulong)),
                ('th32ModuleID', wintypes.DWORD),
                ('cntThreads', wintypes.DWORD),
                ('th32ParentProcessID', wintypes.DWORD),
                ('pcPriClassBase', ctypes.c_long),
                ('dwFlags', wintypes.DWORD),
                ('szExeFile', wintypes.WCHAR * 260),
            ]

        k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]

        snapshot = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if not snapshot or snapshot == INVALID_HANDLE_VALUE:
            return 0

        my_pid = os.getpid()
        targets = []
        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            ok = k32.Process32FirstW(snapshot, ctypes.byref(entry))
            while ok:
                if (entry.th32ParentProcessID == my_pid
                        and entry.szExeFile.lower().startswith('ffmpeg')):
                    targets.append(entry.th32ProcessID)
                entry = PROCESSENTRY32W()
                entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
                ok = k32.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            k32.CloseHandle(snapshot)

        killed = 0
        for pid in targets:
            handle = k32.OpenProcess(PROCESS_TERMINATE, False, pid)
            if handle:
                if k32.TerminateProcess(handle, 1):
                    killed += 1
                k32.CloseHandle(handle)
        return killed
    except Exception:
        return 0


def bind_children_to_process_lifetime():
    """자식 프로세스(ffmpeg)가 이 프로세스보다 오래 살지 못하게 묶는다.

    Windows 는 부모가 죽어도 자식을 종료하지 않고, yt-dlp 의 Popen 은
    Job Object 도 creationflags 도 지정하지 않는다. 그래서 변환 중 창을 닫으면
    ffmpeg.exe 가 고아로 남아 계속 돈다. JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE 로
    현재 프로세스를 Job 에 넣어두면 어떤 경로로 종료되든 자식이 함께 정리된다.
    """
    if sys.platform != 'win32':
        return None
    try:
        import ctypes
        from ctypes import wintypes

        JobObjectExtendedLimitInformation = 9
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in (
                'ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
                'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ('PerProcessUserTimeLimit', ctypes.c_int64),
                ('PerJobUserTimeLimit', ctypes.c_int64),
                ('LimitFlags', wintypes.DWORD),
                ('MinimumWorkingSetSize', ctypes.c_size_t),
                ('MaximumWorkingSetSize', ctypes.c_size_t),
                ('ActiveProcessLimit', wintypes.DWORD),
                ('Affinity', ctypes.POINTER(ctypes.c_ulong)),
                ('PriorityClass', wintypes.DWORD),
                ('SchedulingClass', wintypes.DWORD),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ('BasicLimitInformation', JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ('IoInfo', IO_COUNTERS),
                ('ProcessMemoryLimit', ctypes.c_size_t),
                ('JobMemoryLimit', ctypes.c_size_t),
                ('PeakProcessMemoryUsed', ctypes.c_size_t),
                ('PeakJobMemoryUsed', ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        # 64비트에서 HANDLE 이 c_int 로 잘리지 않도록 시그니처를 명시한다
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
                job, JobObjectExtendedLimitInformation,
                ctypes.byref(info), ctypes.sizeof(info)):
            kernel32.CloseHandle(job)
            return None

        if not kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess()):
            kernel32.CloseHandle(job)
            return None

        # 핸들을 살려둬야 Job 이 유지된다. 프로세스 종료 시 닫히며 자식이 정리된다.
        return job
    except Exception:
        return None


def resource_path(relative_path):
    """PyInstaller 번들과 일반 실행 양쪽에서 리소스 절대 경로를 반환한다."""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)
