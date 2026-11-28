"""WinGet inventory and confirmed package operations for the Windows desktop."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Lock
from time import time
from unicodedata import combining, east_asian_width

from tools import paths
from tools.i18n import tr

_operation_lock = Lock()
_escape = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_safe_id = re.compile(r"[A-Za-z0-9_.+{}\\][A-Za-z0-9_.+{}\\-]{0,255}\Z")
_version = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+~:-]{0,127}\Z")
_no_matches = {0x8A150014}  # APPINSTALLER_CLI_ERROR_NO_APPLICATIONS_FOUND


class PackageError(RuntimeError):
    pass


@dataclass(frozen=True)
class Package:
    name: str
    id: str
    version: str
    available: str = ""
    source: str = ""


def _executable():
    root = os.environ.get("LOCALAPPDATA")
    if not root or os.name != "nt":
        raise PackageError(tr("WinGet requires Windows App Installer.", "Для WinGet нужен «Установщик приложений» Windows."))
    return str(Path(root) / "Microsoft/WindowsApps/winget.exe")


def _make_args(command, *args):
    return [_executable(), command, *args, "--disable-interactivity", "--output-locale", "en-US"]


def _spawn_error():
    return PackageError(tr("WinGet is unavailable. Check App Installer in Windows.",
                           "WinGet недоступен. Проверь «Установщик приложений» в Windows."))


def _read(command, *args):
    try:
        return subprocess.run(_make_args(command, *args), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              timeout=40, creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired as exc:
        raise PackageError(tr("WinGet did not respond in time.", "WinGet не ответил вовремя.")) from exc
    except OSError as exc:
        raise _spawn_error() from exc


def _columns(line, fields):
    values = [[] for _ in fields]
    column = cell = 0
    for character in line:
        while column + 1 < len(fields) and cell >= fields[column + 1].start():
            column += 1
        values[column].append(character)
        cell += 0 if combining(character) else 2 if east_asian_width(character) in ("F", "W") else 1
    return ["".join(value).strip() for value in values]


def _table(text):
    lines = [_escape.sub("", line).strip("\ufeff") for line in text.splitlines()]
    for index, line in enumerate(lines[:-1]):
        fields = list(re.finditer(r"\S+", line))
        names = [field[0] for field in fields]
        if names[:3] != ["Name", "Id", "Version"] or not re.fullmatch(r"\s*-{3,}\s*", lines[index + 1]):
            continue
        rows = []
        for data in lines[index + 2:]:
            if not data.strip():
                break
            values = _columns(data, fields)
            if not all(values[:3]):
                continue
            item = dict(zip(names, values))
            rows.append(Package(item["Name"], item["Id"], item["Version"],
                                item.get("Available", ""), item.get("Source", "")))
        return rows
    raise PackageError(tr("WinGet returned an unrecognized list.", "WinGet вернул список в неизвестном формате."))


def packages(query=""):
    query = query.strip()
    if query and (len(query) > 120 or query.startswith("-") or any(ord(char) < 32 for char in query)):
        raise PackageError(tr("Enter a package name or ID.", "Введи имя или ID пакета."))
    result = (_read("search", "--query", query, "--source", "winget", "--count", "100") if query else
              _read("list", "--source", "winget"))
    code = result.returncode & 0xFFFFFFFF
    if code in _no_matches:
        return []
    if code:
        raise PackageError(tr(f"WinGet couldn't load packages (0x{code:08X}).",
                              f"WinGet не смог загрузить пакеты (0x{code:08X})."))
    rows = _table(result.stdout.decode("utf-8-sig", errors="replace"))
    return [replace(item, source="winget") if not item.source and (query or item.available) else item for item in rows]


def can_run(operation, package):
    if not package or not _safe_id.fullmatch(package.id):
        return False
    if operation == "uninstall":
        return True
    target = package.available if operation == "upgrade" else package.version
    return (operation in ("install", "upgrade") and package.source == "winget" and
            target.casefold() != "unknown" and bool(_version.fullmatch(target)))


def history():
    try:
        records = json.loads((paths.DATA_DIR / "app-history.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return []
    if not isinstance(records, list):
        return []
    return [record for record in records[-100:] if isinstance(record, dict) and
            isinstance(record.get("package"), str) and record.get("action") in ("install", "upgrade", "uninstall") and
            type(record.get("time")) is int and 0 < record["time"] < 32_503_680_000 and
            type(record.get("code")) is int and 0 <= record["code"] <= 0xFFFFFFFF]


def _record(action, package, code):
    paths.DATA_DIR.mkdir(parents=True, exist_ok=True)
    staged = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=paths.DATA_DIR,
                                         prefix="app-history-", suffix=".tmp", delete=False)
    temp = Path(staged.name)
    try:
        with staged:
            entries = history() + [{"action": action, "package": package.id, "time": int(time()), "code": code}]
            json.dump(entries[-100:], staged)
            staged.flush()
            os.fsync(staged.fileno())
        temp.replace(paths.DATA_DIR / "app-history.json")
    finally:
        temp.unlink(missing_ok=True)


def run(operation, package, progress):
    if not can_run(operation, package):
        raise PackageError(tr("This package has no supported WinGet action.", "Это действие WinGet недоступно для пакета."))
    if not _operation_lock.acquire(blocking=False):
        raise PackageError(tr("A package operation is already running.", "Уже выполняется операция с пакетом."))
    try:
        args = ["--id", package.id, "--exact"]
        if operation != "uninstall":
            args.extend(("--source", "winget", "--version", package.available if operation == "upgrade" else package.version))
        try:
            with subprocess.Popen(_make_args(operation, *args), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  creationflags=subprocess.CREATE_NO_WINDOW) as process:
                seen = None
                while chunk := process.stdout.read1(4096):
                    updates = re.findall(rb"(?<!\d)(\d{1,3})%", chunk)
                    if updates:
                        percent = min(int(updates[-1]), 100)
                        if percent != seen:
                            progress(percent)
                            seen = percent
                code = process.wait() & 0xFFFFFFFF
        except OSError as exc:
            raise _spawn_error() from exc
        try:
            _record(operation, package, code)
        except OSError:
            return code, False
        return code, True
    finally:
        _operation_lock.release()
