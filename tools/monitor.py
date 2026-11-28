"""Мониторинг ПК: процессы, загрузка процессора, память и место на диске.

Читаем только то, что Windows отдаёт без прав администратора. Ничего не пишем на
диск и никуда не отправляем.

Проценты процессора считаются по разнице двух снимков: время процессора растёт
только пока процесс реально работает, поэтому одной цифры «сейчас» не существует.
Фоновый поток делает снимок раз в секунду, страница забирает готовый.

Закрытие процесса и сворачивание окон требуют проверки сессии Windows, имени
и времени запуска процесса из списка, поскольку PID переиспользуется.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import threading
import time
from ctypes import wintypes

SAMPLE_INTERVAL = 1.2
FIRST_WAIT = 0.35
IDLE_TIMEOUT = 12
MAX_PROCESSES = 400
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_TERMINATE = 0x0001
SYNCHRONIZE = 0x00100000
WAIT_TIMEOUT = 258
SW_MINIMIZE = 6
GA_ROOT = 2
DWMWA_CLOAKED = 14
FILETIME_EPOCH = 11_644_473_600  # секунд между 1601-01-01 и 1970-01-01

# Без этих процессов Windows живёт плохо, а иногда и не живёт вовсе.
PROTECTED_NAMES = {
    "system",
    "system idle process",
    "registry",
    "memory compression",
    "smss.exe",
    "csrss.exe",
    "wininit.exe",
    "winlogon.exe",
    "services.exe",
    "lsass.exe",
    "svchost.exe",
    "fontdrvhost.exe",
    "dwm.exe",
    "explorer.exe",
    "sihost.exe",
    "taskhostw.exe",
    "ctfmon.exe",
    "spoolsv.exe",
    "audiodg.exe",
    "conhost.exe",
}


class MonitorError(RuntimeError):
    """Не удалось получить снимок или выполнить действие над процессом."""


class _MemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


class _MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


_libs_cache: dict | None = None


def _libs() -> dict:
    """Загружаем WinAPI один раз и сразу проверяем, что он вообще есть."""
    global _libs_cache
    if _libs_cache is not None:
        return _libs_cache
    if not hasattr(ctypes, "WinDLL"):
        raise MonitorError("Мониторинг процессов работает только на Windows")

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    dwmapi = ctypes.WinDLL("dwmapi")

    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]
    kernel32.GetSystemTimes.argtypes = [ctypes.POINTER(wintypes.FILETIME)] * 3
    kernel32.GetSystemTimes.restype = wintypes.BOOL
    kernel32.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetTickCount64.restype = ctypes.c_ulonglong
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(_MemoryStatus)]

    psapi.EnumProcesses.argtypes = [
        ctypes.POINTER(wintypes.DWORD),
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    psapi.EnumProcesses.restype = wintypes.BOOL
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_MemoryCounters),
        wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

    enum_callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [enum_callback, wintypes.LPARAM]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
    dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]

    _libs_cache = {"kernel32": kernel32, "psapi": psapi, "user32": user32,
                   "dwmapi": dwmapi, "enum_callback": enum_callback}
    return _libs_cache


def _filetime(value: wintypes.FILETIME) -> float:
    return _filetime_ticks(value) / 10_000_000


def _filetime_ticks(value: wintypes.FILETIME) -> int:
    return value.dwHighDateTime << 32 | value.dwLowDateTime


def _cpu_times(kernel32):
    idle, kernel, user = (wintypes.FILETIME() for _ in range(3))
    if kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        return _filetime_ticks(kernel) + _filetime_ticks(user), _filetime_ticks(idle)
    return None


def _cpu_percent(before, current):
    if before is None or current is None:
        return None
    total = current[0] - before[0]
    idle = current[1] - before[1]
    if total <= 0 or not 0 <= idle <= total:
        return None
    return round((total - idle) / total * 100, 1)


def _percent(delta_seconds: float, span_seconds: float, cores: int) -> float:
    """Доля процессора за промежуток: сколько ядер было занято, в процентах."""
    if span_seconds <= 0.05 or cores <= 0 or delta_seconds <= 0:
        return 0.0
    share = delta_seconds / (span_seconds * cores) * 100
    return round(min(100.0, max(0.0, share)), 1)


def _protected(name: str) -> bool:
    return (name or "").strip().lower() in PROTECTED_NAMES


def _refuse_reason(info: dict, own_pid: int, session: int) -> str:
    """Почему действие над процессом недоступно."""
    if info.get("pid") in (0, 4):
        return "Это системный процесс Windows"
    if info.get("pid") == own_pid:
        return "Это сам хаб — он выключится вместе с сервером"
    if _protected(info.get("name", "")):
        return f"«{info.get('name')}» защищён: без него Windows работает плохо"
    if session <= 0 or info.get("session") != session:
        return "Процесс запущен вне твоей сессии Windows"
    return ""


def _sort_processes(entries: list[dict]) -> list[dict]:
    return sorted(
        entries,
        key=lambda item: (
            -float(item.get("cpu") or 0),
            -int(item.get("memory") or 0),
            (item.get("name") or "").lower(),
        ),
    )


def _pids(libs: dict) -> list[int]:
    size = 4096
    buffer = (wintypes.DWORD * size)()
    needed = wintypes.DWORD()
    if not libs["psapi"].EnumProcesses(buffer, ctypes.sizeof(buffer), ctypes.byref(needed)):
        raise MonitorError("Windows не отдал список процессов")
    count = needed.value // ctypes.sizeof(wintypes.DWORD)
    return [buffer[index] for index in range(count) if buffer[index]]


def _session(libs: dict, pid: int) -> int:
    session = wintypes.DWORD()
    if not libs["kernel32"].ProcessIdToSessionId(pid, ctypes.byref(session)):
        return -1
    return int(session.value)


def _process_info(libs: dict, pid: int, handle=None) -> dict | None:
    """Имя, память и время процессора. None — процесс закрыт или недоступен."""
    kernel32 = libs["kernel32"]
    own_handle = handle is None
    if own_handle:
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(buffer))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
            return None
        name = os.path.basename(buffer.value)
        if not name:
            return None

        created = wintypes.FILETIME()
        exited = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        if not kernel32.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            return None
        counters = _MemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        memory = 0
        if libs["psapi"].GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            memory = int(counters.WorkingSetSize)

        started = _filetime(created)
        return {
            "pid": pid,
            "name": name,
            "session": _session(libs, pid),
            "cpu_seconds": round(_filetime(kernel) + _filetime(user), 4),
            "created": round(started, 3),
            "creation": str(_filetime_ticks(created)),
            "started": round(started - FILETIME_EPOCH, 0) if started else 0,
            "memory": memory,
        }
    finally:
        if own_handle:
            kernel32.CloseHandle(handle)


def _window_owner(libs: dict, window: int) -> int:
    user32 = libs["user32"]
    if not user32.IsWindowVisible(window) or user32.IsIconic(window) or user32.GetAncestor(window, GA_ROOT) != window:
        return 0
    cloaked = wintypes.DWORD()
    if libs["dwmapi"].DwmGetWindowAttribute(window, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) or cloaked.value:
        return 0
    pid = wintypes.DWORD()
    return pid.value if user32.GetWindowThreadProcessId(window, ctypes.byref(pid)) else 0


def _visible_windows(libs: dict) -> dict[int, list[int]]:
    windows = {}

    @libs["enum_callback"]
    def collect(window, _):
        pid = _window_owner(libs, window)
        if pid:
            windows.setdefault(pid, []).append(window)
        return True

    if not libs["user32"].EnumWindows(collect, 0):
        return {}
    return windows


def _process_identity(info: dict) -> tuple[str, float, str]:
    return info["name"], info["created"], info["creation"]


def _memory(libs: dict) -> dict:
    status = _MemoryStatus()
    status.dwLength = ctypes.sizeof(status)
    if not libs["kernel32"].GlobalMemoryStatusEx(ctypes.byref(status)):
        return {"total": 0, "used": 0, "percent": 0}
    total = int(status.ullTotalPhys)
    available = int(status.ullAvailPhys)
    used = max(0, total - available)
    percent = round(used / total * 100, 1) if total else 0
    return {"total": total, "used": used, "percent": percent}


def _disk() -> dict:
    root = os.environ.get("SystemDrive", "C:") + "\\"
    try:
        usage = shutil.disk_usage(root)
    except OSError:
        return {"total": 0, "free": 0, "drive": root}
    return {
        "total": int(usage.total),
        "free": int(usage.free),
        "drive": root,
        "percent": round((usage.total - usage.free) / usage.total * 100, 1) if usage.total else 0,
    }


def _refresh() -> None:
    libs = _libs()
    wall = time.perf_counter()
    cores = os.cpu_count() or 1
    cpu_times = _cpu_times(libs["kernel32"]) if cores <= 64 else None

    entries: list[dict] = []
    current: dict[int, tuple] = {}
    for pid in _pids(libs):
        info = _process_info(libs, pid)
        if info is None:
            continue
        current[pid] = (info["cpu_seconds"], info["creation"])
        entries.append(info)
    windows = _visible_windows(libs)

    with _state["lock"]:
        previous = _state["previous"]
        previous_time = _state["previous_time"]
        span = wall - previous_time if previous_time else 0.0
        total_delta = 0.0
        for entry in entries:
            before = previous.get(entry["pid"])
            if before and before[1] == entry["creation"]:
                delta = max(0.0, entry["cpu_seconds"] - before[0])
                total_delta += delta
                entry["cpu"] = _percent(delta, span, cores)
            else:
                entry["cpu"] = 0.0
            entry.pop("cpu_seconds", None)

        own_pid = os.getpid()
        own_session = _session(libs, own_pid)
        for entry in entries:
            reason = _refuse_reason(entry, own_pid, own_session)
            entry["can_stop"] = not reason
            entry["can_minimize"] = not reason and entry["pid"] in windows
            entry["why_not"] = reason
            entry["own"] = entry["pid"] == own_pid

        entries = _sort_processes(entries)[:MAX_PROCESSES]
        _state["previous"] = current
        _state["previous_time"] = wall
        _state["allowed"] = {
            entry["pid"]: _process_identity(entry) for entry in entries if entry["can_stop"]
        }
        ready = span > 0.05
        cpu_val = _cpu_percent(_state.get("previous_cpu"), cpu_times)
        _state["previous_cpu"] = cpu_times
        if cpu_val is None:
            cpu_val = _percent(total_delta, span, cores) if ready else 0.0
        mem_info = _memory(libs)
        history = _state.get("history", [])
        if ready:
            history.append({"cpu": cpu_val, "memory": mem_info.get("percent", 0.0), "time": time.time()})
            if len(history) > 30:
                history = history[-30:]
            _state["history"] = history

        _state["latest"] = {
            "ready": ready,
            "time": time.time(),
            "seconds": round(span, 2),
            "system": {
                "cpu": cpu_val,
                "cores": cores,
                "memory": mem_info,
                "disk": _disk(),
                "uptime": round(libs["kernel32"].GetTickCount64() / 1000, 0),
                "processes": len(entries),
            },
            "history": list(history),
            "processes": entries,
        }


_state: dict = {
    "lock": threading.RLock(),
    "previous": {},
    "previous_time": 0.0,
    "allowed": {},
    "latest": None,
    "history": [],
    "thread": None,
}


def _loop() -> None:
    while True:
        with _state["lock"]:
            now = time.monotonic()
            if now - _state.get("requested", now) > IDLE_TIMEOUT:
                _state.update(thread=None, latest=None, allowed={}, previous={}, previous_cpu=None,
                              previous_time=0.0, history=[])
                return
        try:
            _refresh()
        except Exception:  # noqa: BLE001 — фоновая нить не должна падать молча в никуда
            with _state["lock"]:
                _state["latest"] = None
        time.sleep(FIRST_WAIT if _state["latest"] is None else SAMPLE_INTERVAL)


def _ensure_sampler() -> None:
    with _state["lock"]:
        _state["requested"] = time.monotonic()
        if _state["thread"] is None:
            thread = threading.Thread(target=_loop, name="hub-monitor", daemon=True)
            _state["thread"] = thread
            thread.start()


def snapshot() -> dict:
    """Последний снимок. Первый запрос ждёт, пока появятся реальные проценты."""
    _ensure_sampler()
    deadline = time.time() + 2.5
    while True:
        with _state["lock"]:
            latest = _state["latest"]
            if latest and latest.get("ready"):
                return latest
        if time.time() >= deadline:
            if latest:
                return latest
            raise MonitorError("Не получилось посмотреть на процессы")
        time.sleep(0.05)


def _allowed_process(pid: int) -> tuple[str, float, str]:
    allowed = _state["allowed"].get(pid)
    if allowed is None:
        raise MonitorError("Процесс недоступен в последнем снимке. Обнови список и попробуй снова.")
    return allowed


def _check_process(libs: dict, pid: int, handle, allowed: tuple[str, float, str]) -> dict:
    info = _process_info(libs, pid, handle)
    if info is None:
        raise MonitorError("Процесс завершился или Windows ограничила доступ")
    if _process_identity(info) != allowed:
        raise MonitorError("Процесс изменился. Обнови список.")
    own_pid = os.getpid()
    reason = _refuse_reason(info, own_pid, _session(libs, own_pid))
    if reason:
        raise MonitorError(reason)
    return info


def terminate(pid: int, expected: tuple[str, float] | tuple[str, float, str] | None = None) -> dict:
    """Закрыть процесс из последнего снимка."""
    with _state["lock"]:
        allowed = _allowed_process(pid)
        if expected is not None and expected != allowed[:len(expected)]:
            raise MonitorError("Процесс изменился. Обнови список.")

        libs = _libs()
        access = PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_TERMINATE | SYNCHRONIZE
        handle = libs["kernel32"].OpenProcess(access, False, pid)
        if not handle:
            raise MonitorError("Windows не разрешил закрыть этот процесс")
        try:
            info = _check_process(libs, pid, handle, allowed)
            if not libs["kernel32"].TerminateProcess(handle, 1):
                raise MonitorError("Процесс не закрылся: Windows отказал")
            libs["kernel32"].WaitForSingleObject(handle, 1500)
        finally:
            libs["kernel32"].CloseHandle(handle)

        _state["allowed"].pop(pid, None)
        return {"stopped": True, "pid": pid, "name": info["name"]}


def minimize(pid: int, name: str, creation: str) -> dict:
    """Запросить сворачивание видимых окон выбранного процесса."""
    with _state["lock"]:
        allowed = _allowed_process(pid)
        if (name, creation) != (allowed[0], allowed[2]):
            raise MonitorError("Процесс изменился. Обнови список.")
        libs = _libs()
        kernel32 = libs["kernel32"]
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid)
        if not handle:
            raise MonitorError("Процесс завершился или Windows ограничила доступ")
        try:
            _check_process(libs, pid, handle, allowed)
            windows = _visible_windows(libs).get(pid, [])
            requested = 0
            for window in windows:
                if _window_owner(libs, window) != pid:
                    continue
                if kernel32.WaitForSingleObject(handle, 0) != WAIT_TIMEOUT:
                    break
                if libs["user32"].ShowWindowAsync(window, SW_MINIMIZE):
                    requested += 1
            if not requested:
                raise MonitorError("Видимых окон сейчас нет или Windows не разрешила их свернуть")
            return {"requested": requested, "pid": pid, "name": name}
        finally:
            kernel32.CloseHandle(handle)
