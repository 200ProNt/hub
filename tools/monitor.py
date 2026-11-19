"""Мониторинг ПК: процессы, загрузка процессора, память и место на диске.

Читаем только то, что Windows отдаёт без прав администратора. Ничего не пишем на
диск и никуда не отправляем.

Проценты процессора считаются по разнице двух снимков: время процессора растёт
только пока процесс реально работает, поэтому одной цифры «сейчас» не существует.
Фоновый поток делает снимок раз в секунду, страница забирает готовый.

Закрывать процессы можно, но осторожно: только свои (та же сессия Windows), только
не системные и только если процесс с момента списка не подменился. Перед закрытием
сверяется время запуска — PID переиспользуется, и по одному номеру можно случайно
попасть в чужой процесс.
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
MAX_PROCESSES = 400
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_TERMINATE = 0x0001
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
    """Снимок или закрытие процесса не получились."""


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
    kernel32.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetTickCount64.restype = ctypes.c_ulonglong
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
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

    _libs_cache = {"kernel32": kernel32, "psapi": psapi}
    return _libs_cache


def _filetime(value: wintypes.FILETIME) -> float:
    return (value.dwHighDateTime << 32 | value.dwLowDateTime) / 10_000_000


def _percent(delta_seconds: float, span_seconds: float, cores: int) -> float:
    """Доля процессора за промежуток: сколько ядер было занято, в процентах."""
    if span_seconds <= 0.05 or cores <= 0 or delta_seconds <= 0:
        return 0.0
    share = delta_seconds / (span_seconds * cores) * 100
    return round(min(100.0, max(0.0, share)), 1)


def _protected(name: str) -> bool:
    return (name or "").strip().lower() in PROTECTED_NAMES


def _refuse_reason(info: dict, own_pid: int, session: int) -> str:
    """Почему процесс нельзя закрыть. Пустая строка — можно."""
    if info.get("pid") in (0, 4):
        return "Это системный процесс Windows"
    if info.get("pid") == own_pid:
        return "Это сам хаб — он выключится вместе с сервером"
    if _protected(info.get("name", "")):
        return f"«{info.get('name')}» защищён: без него Windows работает плохо"
    if info.get("session") != session:
        return "Это процесс системы, а не твой — его не трогаем"
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


def _process_info(libs: dict, pid: int) -> dict | None:
    """Имя, память и время процессора. None — процесс закрыт или недоступен."""
    kernel32 = libs["kernel32"]
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
        kernel32.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        )
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
            "started": round(started - FILETIME_EPOCH, 0) if started else 0,
            "memory": memory,
        }
    finally:
        kernel32.CloseHandle(handle)


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

    entries: list[dict] = []
    current: dict[int, tuple] = {}
    for pid in _pids(libs):
        info = _process_info(libs, pid)
        if info is None:
            continue
        current[pid] = (info["cpu_seconds"], info["created"])
        entries.append(info)

    with _state["lock"]:
        previous = _state["previous"]
        previous_time = _state["previous_time"]
        span = wall - previous_time if previous_time else 0.0
        total_delta = 0.0
        for entry in entries:
            before = previous.get(entry["pid"])
            if before and before[1] == entry["created"]:
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
            entry["why_not"] = reason
            entry["own"] = entry["pid"] == own_pid

        entries = _sort_processes(entries)[:MAX_PROCESSES]
        _state["previous"] = current
        _state["previous_time"] = wall
        _state["allowed"] = {
            entry["pid"]: (entry["name"], entry["created"]) for entry in entries if entry["can_stop"]
        }
        ready = span > 0.05
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
        try:
            _refresh()
        except Exception:  # noqa: BLE001 — фоновая нить не должна падать молча в никуда
            with _state["lock"]:
                _state["latest"] = None
        time.sleep(FIRST_WAIT if _state["latest"] is None else SAMPLE_INTERVAL)


def _ensure_sampler() -> None:
    with _state["lock"]:
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


def terminate(pid: int) -> dict:
    """Закрыть процесс из последнего снимка."""
    with _state["lock"]:
        allowed = _state["allowed"].get(pid)
        if allowed is None:
            raise MonitorError("Этого процесса нет в последнем списке — обнови и попробуй снова")

        libs = _libs()
        info = _process_info(libs, pid)
        if info is None:
            raise MonitorError("Процесс уже завершился")
        if (info["name"], info["created"]) != allowed:
            raise MonitorError("Процесс изменился; список обновится сам")

        reason = _refuse_reason(info, os.getpid(), _session(libs, os.getpid()))
        if reason:
            raise MonitorError(reason)

        handle = libs["kernel32"].OpenProcess(PROCESS_TERMINATE, False, pid)
        if not handle:
            raise MonitorError("Windows не разрешил закрыть этот процесс")
        try:
            if not libs["kernel32"].TerminateProcess(handle, 1):
                raise MonitorError("Процесс не закрылся: Windows отказал")
            libs["kernel32"].WaitForSingleObject(handle, 1500)
        finally:
            libs["kernel32"].CloseHandle(handle)

        _state["allowed"].pop(pid, None)
        return {"stopped": True, "pid": pid, "name": info["name"]}
