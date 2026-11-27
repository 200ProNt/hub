"""Run the read-only Disk Map worker and translate protocol v1 to Hub's result."""

import ctypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from queue import Empty, SimpleQueue
from threading import Thread

from tools import diskmap

PROTOCOL = 1
IDLE_TIMEOUT = 30


class WorkerError(RuntimeError):
    pass


def executable():
    root = Path(__file__).resolve().parents[1]
    if getattr(sys, "frozen", False):
        return root / "bin" / "hub-diskmap-worker.exe"
    return root / "rust" / "diskmap-worker" / "target" / "release" / "hub-diskmap-worker.exe"


def _exchange(process, request, messages):
    try:
        with process.stdin as pipe:
            pipe.write(request)
        with process.stdout as pipe:
            for line in pipe:
                messages.put(json.loads(line))
    except (OSError, ValueError) as exc:
        messages.put(WorkerError(f"Некорректный ответ Rust Worker: {exc}"))
    finally:
        messages.put(None)


def _events(path, request, control, metrics, sample_process):
    startup = time.perf_counter()
    try:
        process = subprocess.Popen(
            [str(path)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except OSError as exc:
        raise WorkerError(f"Не удалось запустить Rust Worker: {exc}") from exc

    messages = SimpleQueue()
    reader = Thread(target=_exchange, args=(process, request, messages), daemon=True, name="diskmap-worker-io")
    terminal = None
    ready = False
    deadline = time.monotonic() + IDLE_TIMEOUT
    try:
        reader.start()
        while True:
            if control is not None:
                control.check()
            if time.monotonic() > deadline:
                raise WorkerError("Rust Worker перестал отвечать")
            try:
                event = messages.get(timeout=.025)
            except Empty:
                continue
            if event is None:
                break
            if isinstance(event, WorkerError):
                raise event
            if not isinstance(event, dict) or terminal is not None:
                raise WorkerError("Некорректная последовательность ответов Rust Worker")
            name = event.get("event")
            if not ready:
                if name != "ready" or event.get("protocol") != PROTOCOL:
                    raise WorkerError("Несовместимая версия Rust Worker")
                ready = True
                if metrics is not None:
                    metrics["worker_start_ms"] = (time.perf_counter() - startup) * 1000
            elif name == "progress":
                if control is not None:
                    control.report(event["entries"], event["files"], event["bytes"])
            elif name in ("result", "scan_error"):
                terminal = event
            else:
                raise WorkerError("Неизвестный ответ Rust Worker")
            deadline = time.monotonic() + IDLE_TIMEOUT
        if process.wait(timeout=2) or terminal is None:
            raise WorkerError(f"Rust Worker завершился без результата (код {process.returncode})")
        if sample_process is not None:
            sample_process(process)
        if control is not None:
            control.check()
        return terminal
    except subprocess.TimeoutExpired as exc:
        raise WorkerError("Rust Worker не завершился после расчёта") from exc
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        if reader.ident is not None:
            reader.join()


def _detail(error):
    code = error.get("os_error")
    if os.name == "nt" and isinstance(code, int):
        return ctypes.WinError(code).strerror
    return error["detail"]


def _payload(root, protected, started, result, control):
    entries = []
    for branch in result["branches"]:
        name = branch["name"]
        if not isinstance(name, str) or not name or name in (".", "..") or Path(name).name != name:
            raise WorkerError("Rust Worker вернул недопустимое имя папки")
        totals = branch["totals"]
        entries.append({"name": name, "path": str(root / name), "kind": "dir",
                        "size": totals["bytes"], "count": totals["files"]})
    errors = []
    for error in result["errors"]:
        relative = Path(error["path"])
        if relative.anchor or ".." in relative.parts:
            raise WorkerError("Rust Worker вернул недопустимый путь ошибки")
        kind = error["reason"]
        if kind == "protected":
            reason = "Системная папка пропущена"
        elif kind == "changed":
            reason = "Папка изменилась во время обхода"
        elif kind == "folder":
            reason = f"папка недоступна: {_detail(error)}"
        else:
            reason = _detail(error)
        errors.append({"path": str(root / relative), "reason": reason})
    counters = {**result, **result["totals"], "errors": errors}
    loose = result["loose"]
    payload = diskmap._scan_payload(root, protected, started, entries, loose["bytes"], loose["files"], counters, control)
    if payload["total"] != counters["bytes"] or sum(item["count"] for item in entries) != counters["files"]:
        raise WorkerError("Rust Worker вернул несовместимые итоги обхода")
    return payload


def scan(folder, *, control=None, allow_volume_root=False, worker=None, metrics=None, sample_process=None):
    root, protected = diskmap._prepare_scan(folder, allow_volume_root, control)
    started = time.monotonic()
    request = json.dumps({
        "protocol": PROTOCOL, "root": str(root), "max_entries": diskmap.MAX_ENTRIES,
        "max_depth": diskmap.MAX_DEPTH, "max_errors": diskmap.MAX_ERRORS,
        "protected_paths": sorted(protected or ()),
        "protected_names": diskmap.PROTECTED_NAMES if protected is not None else (),
        "protected_top_names": diskmap.PROTECTED_TOP_NAMES if protected is not None else (),
    }, ensure_ascii=True).encode() + b"\n"
    try:
        answer = _events(worker or executable(), request, control, metrics, sample_process)
        if answer["event"] == "scan_error":
            raise diskmap.ScanError(f"Не получилось прочитать папку: {_detail(answer)}")
        return _payload(root, protected, started, answer["scan"], control)
    except (KeyError, TypeError, ValueError) as exc:
        raise WorkerError("Rust Worker вернул повреждённый ответ") from exc
