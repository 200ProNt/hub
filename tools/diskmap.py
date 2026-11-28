"""Карта диска: сколько места занимает каждая папка.

Считаем реальные размеры файлов (не «на диске», а суммарный размер байтов),
без символических ссылок и junction-точек, чтобы не бегать по кругу и не
считать одно и то же дважды.

Для одной папки отдаём её ближайшие папки по отдельности и все файлы из корня
одной строкой «Файлы в этой папке» — иначе на диаграмме будет каша из сотен
мелких секторов.
"""

from __future__ import annotations

import os
from contextlib import closing
from dataclasses import dataclass
import stat
import threading
import time
from pathlib import Path
from uuid import uuid4

from tools import fileguard, trash

MAX_ENTRIES = 250_000
MAX_DEPTH = 60
CACHE_TTL = 90.0
MAX_CACHE = 64
MAX_ERRORS = 25
FILE_PAGE_SIZE = 100
FILE_ATTRIBUTE_REPARSE_POINT = fileguard.FILE_ATTRIBUTE_REPARSE_POINT
PROTECTED_NAMES = ("$recycle.bin", "system volume information")
PROTECTED_TOP_NAMES = ("windows", "program files", "program files (x86)", "programdata")


class ScanError(RuntimeError):
    """Папку не удалось посчитать."""


class RemoveError(RuntimeError):
    """Файл не прошёл проверку перед удалением."""


@dataclass
class FileListing:
    token: str
    root: Path
    parents: tuple
    files: list[dict]
    truncated: bool


_cache: dict[str, tuple[float, dict]] = {}
_allowed: dict[str, tuple] = {}
_file_listing: FileListing | None = None
_actions_lock = threading.RLock()
_cache_lock = threading.Lock()
_cache_generation = 0


def _parents(path: Path) -> tuple:
    try:
        return fileguard.parents(path)
    except fileguard.GuardError as exc:
        raise ScanError(str(exc)) from exc
    except OSError as exc:
        raise ScanError(f"Не получилось прочитать папку: {exc}") from exc


def _identity(info: os.stat_result) -> tuple:
    return fileguard.identity(info)


def close_file_listing() -> None:
    global _file_listing
    with _actions_lock:
        _file_listing = None
        _allowed.clear()


def files(folder: str, *, paged: bool = False) -> dict:
    global _file_listing
    with _actions_lock:
        _file_listing = None
        _allowed.clear()
        if not folder or not folder.strip():
            raise ScanError("Укажи папку")
        if _drive_root(Path(os.path.abspath(Path(folder).expanduser()))):
            raise ScanError("Корень диска доступен только для расчёта размеров")
        try:
            root = fileguard.check_safe_folder(folder)
        except fileguard.GuardError as exc:
            raise ScanError(str(exc)) from exc
        try:
            parents = _parents(root)
            counters = {"errors": []}
            listing = []
            allowed = {}
            truncated = False
            with os.scandir(root) as children:
                for number, entry in enumerate(children):
                    if number >= MAX_ENTRIES:
                        truncated = True
                        break
                    try:
                        info = entry.stat(follow_symlinks=False) if paged else os.lstat(entry.path)
                    except OSError as exc:
                        _note_error(counters, entry.path, str(exc))
                        continue
                    if not stat.S_ISREG(info.st_mode) or _is_link(info):
                        continue
                    listing.append({"name": entry.name, "path": entry.path, "size": info.st_size})
                    if not paged:
                        allowed[os.path.normcase(entry.path)] = (_identity(info), parents)
            if not paged and _parents(root) != parents:
                raise ScanError("Папка изменилась; открой её заново")
        except OSError as exc:
            raise ScanError(f"Не получилось прочитать папку: {exc}") from exc
        listing.sort(key=lambda item: (-item["size"], item["name"].lower()))
        if paged:
            _file_listing = FileListing(uuid4().hex, root, parents, listing, truncated)
            return file_page(_file_listing.token, 0, counters)
        _allowed.update(allowed)
        return {"folder": str(root), "files": listing, "truncated": truncated, "errors": counters["errors"]}


def file_page(token: str, offset: int, counters=None) -> dict:
    with _actions_lock:
        listing = _file_listing
        if listing is None or listing.token != token:
            raise ScanError("Список файлов устарел; открой его заново")
        if type(offset) is not int or not 0 <= offset <= len(listing.files) or offset % FILE_PAGE_SIZE:
            raise ScanError("Неверная страница списка файлов")
        counters = {"errors": []} if counters is None else counters
        rows, allowed = [], {}
        end = offset + FILE_PAGE_SIZE
        try:
            if _parents(listing.root) != listing.parents:
                raise ScanError("Папка изменилась; открой её заново")
            for item in listing.files[offset:end]:
                path = item["path"]
                try:
                    # The directory index provides ordering. Only lstat can authorize actions.
                    info = os.lstat(path)
                except OSError as exc:
                    _note_error(counters, path, str(exc))
                    continue
                key = os.path.normcase(path)
                identity = (_identity(info), listing.parents)
                if (not stat.S_ISREG(info.st_mode) or _is_link(info) or info.st_size != item["size"]
                        or _allowed.get(key, identity) != identity):
                    _note_error(counters, path, "Файл изменился; открой список заново")
                    continue
                rows.append(item)
                allowed[key] = identity
            if _parents(listing.root) != listing.parents:
                raise ScanError("Папка изменилась; открой её заново")
        except ScanError:
            close_file_listing()
            raise
        _allowed.update(allowed)
        return {
            "folder": str(listing.root), "files": rows, "count": len(listing.files),
            "listing": listing.token, "next_offset": end if end < len(listing.files) else None,
            "truncated": listing.truncated, "errors": counters["errors"],
        }


def remove_file(path: str, mode: str, confirmed=False, *, listing=None) -> dict:
    with _actions_lock:
        if mode not in ("trash", "delete"):
            raise RemoveError("Выбери перенос в корзину или удаление навсегда")
        if mode == "delete" and confirmed is not True:
            raise RemoveError("Для удаления навсегда нужно явное подтверждение")
        item = Path(os.path.abspath(Path(path).expanduser()))
        key = os.path.normcase(str(item))
        authorized = _allowed.get(key)
        if authorized is None or listing != (_file_listing.token if _file_listing is not None else None):
            raise RemoveError("Этот файл не из последнего списка; открой папку заново")
        try:
            info = item.lstat()
            if (not stat.S_ISREG(info.st_mode) or _is_link(info)
                    or _identity(info) != authorized[0] or _parents(item.parent) != authorized[1]):
                raise RemoveError("Файл или папка изменились; открой список заново")
        except (OSError, ScanError) as exc:
            raise RemoveError(f"Файл или папка недоступны: {exc}") from exc
        result = {"removed_count": 0, "removed_size": 0, "errors": [], "run_id": None}
        try:
            if mode == "trash":
                moved = trash.move([str(item)], source="diskmap", meta={"folder": str(item.parent)})
                result.update({name: moved[name] for name in result if name in moved})
            else:
                item.unlink()
                result.update(removed_count=1, removed_size=info.st_size)
        except (OSError, trash.TrashError) as exc:
            result["errors"].append({"path": str(item), "reason": str(exc)})
        finally:
            _allowed.pop(key, None)
            _invalidate_cache()
        return result


def undo(run_id: str) -> dict:
    with _actions_lock:
        try:
            _, journal = trash._read(run_id)
            if journal.get("source") != "diskmap":
                raise RemoveError("Это не перенос карты диска")
            return trash.undo(run_id)
        except (OSError, trash.TrashError) as exc:
            raise RemoveError(str(exc)) from exc
        finally:
            close_file_listing()
            _invalidate_cache()


def last_run() -> dict | None:
    with _actions_lock:
        return trash.last_run("diskmap")


def _note_error(counters: dict, path: str, reason: str) -> None:
    counters["error_count"] = counters.get("error_count", 0) + 1
    if len(counters["errors"]) < MAX_ERRORS:
        counters["errors"].append({"path": path, "reason": reason})


def _is_link(stat: os.stat_result) -> bool:
    return fileguard.is_link(stat)


def _children(path, counters, control=None, *, root=False):
    """Stream entries and stop the whole traversal once the cap is exceeded."""
    if control is not None:
        control.check()
    if counters["entry_limit"]:
        return
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                if control is not None:
                    control.check()
                if counters["entries"] == MAX_ENTRIES:
                    counters["entry_limit"] = counters["truncated"] = True
                    return
                counters["entries"] += 1
                if control is not None and counters["entries"] % 64 == 0:
                    control.report(counters["entries"], counters["files"], counters["bytes"])
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError as exc:
                    _note_error(counters, entry.path, str(exc))
                    continue
                if stat.S_ISLNK(info.st_mode) or _is_link(info):
                    counters["links"] += 1
                    continue
                yield entry, info
                if counters["entry_limit"]:
                    return
    except OSError as exc:
        if root:
            raise ScanError(f"Не получилось прочитать папку: {exc}") from exc
        _note_error(counters, str(path), f"папка недоступна: {exc.strerror or exc}")


def _walk(path, counters, control, protected, depth=1):
    """Aggregate one branch and close its iterator on cancellation."""
    if control is not None:
        control.check()
    # Windows directory entries may still describe a directory replaced by a junction.
    try:
        info = os.lstat(path)
    except OSError as exc:
        _note_error(counters, path, f"папка недоступна: {exc.strerror or exc}")
        return 0, 0
    if stat.S_ISLNK(info.st_mode) or _is_link(info):
        counters["links"] += 1
        return 0, 0
    if not stat.S_ISDIR(info.st_mode):
        _note_error(counters, path, "Папка изменилась во время обхода")
        return 0, 0

    total = files = 0
    with closing(_children(path, counters, control)) as children:
        for entry, info in children:
            if stat.S_ISDIR(info.st_mode):
                if protected is not None and _protected(entry, protected):
                    _note_error(counters, entry.path, "Системная папка пропущена")
                    continue
                if depth >= MAX_DEPTH:
                    counters["truncated"] = True
                    continue
                counters["dirs"] += 1
                size, count = _walk(entry.path, counters, control, protected, depth + 1)
                total += size
                files += count
            elif stat.S_ISREG(info.st_mode):
                counters["files"] += 1
                counters["bytes"] += info.st_size
                total += info.st_size
                files += 1
    return total, files


def _invalidate_cache():
    global _cache_generation
    with _cache_lock:
        _cache_generation += 1
        _cache.clear()


def _drive_root(path):
    return os.name == "nt" and str(path) == path.anchor and len(path.drive) == 2


def _volume_root(path):
    if not _drive_root(path):
        return False
    from ctypes import windll, wintypes

    drive_type = windll.kernel32.GetDriveTypeW
    drive_type.argtypes = (wintypes.LPCWSTR,)
    drive_type.restype = wintypes.UINT
    return drive_type(str(path)) in (2, 3)  # Local removable and fixed volumes.


def _protected(entry, directories, *, top=False):
    name = entry.name.casefold()
    if name in PROTECTED_NAMES:
        return True
    if top and name in PROTECTED_TOP_NAMES:
        return True
    return os.path.normcase(entry.path) in directories


def _prepare_scan(folder, allow_volume_root, control):
    if not folder or not folder.strip():
        raise ScanError("Укажи папку, которую нужно посчитать")
    if control is not None:
        control.check()
    candidate = Path(os.path.abspath(Path(folder).expanduser()))
    volume = allow_volume_root and _volume_root(candidate)
    if not volume and _drive_root(candidate):
        raise ScanError("Системная папка защищена: корень диска можно посчитать в локальной карте диска")
    try:
        root = candidate if volume else fileguard.check_safe_folder(folder)
        if volume:
            _parents(root)
            resolved = root.resolve(strict=True)
            if not _drive_root(resolved):
                fileguard.check_safe_folder(resolved)
    except fileguard.GuardError as exc:
        raise ScanError(str(exc)) from exc
    except OSError as exc:
        raise ScanError(f"Не получилось прочитать папку: {exc}") from exc
    protected = None
    if volume:
        protected = {os.path.normcase(str(root / path.relative_to(resolved)))
                     for path in fileguard.get_system_directories() if path.is_relative_to(resolved)}
    return root, protected


def _scan_payload(root, protected, started, entries, loose_size, loose_files, counters, control):
    if loose_files:
        entries.append({
            "name": "Файлы в этой папке", "path": str(root), "kind": "files",
            "size": loose_size, "count": loose_files,
        })
    if control is not None:
        control.check()
    entries.sort(key=lambda item: (-item["size"], item["name"].lower()))
    payload = {
        "folder": str(root),
        "name": root.name or str(root),
        "parent": str(root.parent) if root.parent != root else None,
        "total": sum(item["size"] for item in entries),
        "entries": entries,
        "dirs": counters["dirs"],
        "files": counters["files"],
        "links": counters["links"],
        "errors": counters["errors"],
        "error_count": counters.get("error_count", 0),
        "truncated": counters["truncated"],
        "seconds": round(time.monotonic() - started, 2),
    }
    if protected is not None:
        payload["read_only_root"] = True
    if control is not None:
        control.check()
        control.report(counters["entries"], counters["files"], counters["bytes"])
    return payload


def scan(folder: str, *, use_cache=False, allow_volume_root=False, control=None) -> dict:
    global _cache_generation
    root, protected = _prepare_scan(folder, allow_volume_root, control)
    volume = protected is not None

    key = os.path.normcase(str(root))
    started = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if use_cache and not volume and control is None and hit and started - hit[0] <= CACHE_TTL:
            return hit[1]
        if not use_cache:
            _cache_generation += 1
        generation = _cache_generation
        _cache.pop(key, None)

    counters = {"entries": 0, "dirs": 0, "files": 0, "bytes": 0, "links": 0,
                "entry_limit": False, "truncated": False, "errors": []}
    entries = []
    loose_size = loose_files = 0

    with closing(_children(root, counters, control, root=True)) as children:
        for entry, info in children:
            if stat.S_ISDIR(info.st_mode):
                if protected is not None and _protected(entry, protected, top=True):
                    _note_error(counters, entry.path, "Системная папка пропущена")
                    continue
                counters["dirs"] += 1
                size, count = _walk(entry.path, counters, control, protected)
                entries.append({"name": entry.name, "path": entry.path, "kind": "dir",
                                "size": size, "count": count})
            elif stat.S_ISREG(info.st_mode):
                loose_size += info.st_size
                loose_files += 1
                counters["files"] += 1
                counters["bytes"] += info.st_size

    payload = _scan_payload(root, protected, started, entries, loose_size, loose_files, counters, control)
    if use_cache and not volume and control is None and not payload["errors"] and not payload["truncated"]:
        with _cache_lock:
            current = _cache.get(key)
            if generation == _cache_generation and (current is None or current[0] < started):
                if len(_cache) >= MAX_CACHE:
                    _cache.pop(next(iter(_cache)))
                _cache[key] = (started, payload)
    return payload
