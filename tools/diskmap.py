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
import stat
import threading
import time
from pathlib import Path

from tools import fileguard, trash

MAX_ENTRIES = 250_000
MAX_DEPTH = 60
CACHE_TTL = 90.0
MAX_CACHE = 64
MAX_ERRORS = 25
FILE_ATTRIBUTE_REPARSE_POINT = fileguard.FILE_ATTRIBUTE_REPARSE_POINT


class ScanError(RuntimeError):
    """Папку не удалось посчитать."""


class RemoveError(RuntimeError):
    """Файл не прошёл проверку перед удалением."""


_cache: dict[str, tuple[float, dict]] = {}
_allowed: dict[str, tuple] = {}
_actions_lock = threading.RLock()


def _parents(path: Path) -> tuple:
    try:
        return fileguard.parents(path)
    except fileguard.GuardError as exc:
        raise ScanError(str(exc)) from exc
    except OSError as exc:
        raise ScanError(f"Не получилось прочитать папку: {exc}") from exc


def _identity(info: os.stat_result) -> tuple:
    return fileguard.identity(info)


def files(folder: str) -> dict:
    with _actions_lock:
        _allowed.clear()
        if not folder or not folder.strip():
            raise ScanError("Укажи папку")
        root = Path(os.path.abspath(Path(folder).expanduser()))
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
                        info = Path(entry.path).lstat()
                    except OSError as exc:
                        _note_error(counters, entry.path, str(exc))
                        continue
                    if not stat.S_ISREG(info.st_mode) or _is_link(info):
                        continue
                    listing.append({"name": entry.name, "path": entry.path, "size": info.st_size})
                    allowed[os.path.normcase(entry.path)] = (_identity(info), parents)
            if _parents(root) != parents:
                raise ScanError("Папка изменилась; открой её заново")
        except OSError as exc:
            raise ScanError(f"Не получилось прочитать папку: {exc}") from exc
        listing.sort(key=lambda item: (-item["size"], item["name"].lower()))
        _allowed.update(allowed)
        return {"folder": str(root), "files": listing, "truncated": truncated, "errors": counters["errors"]}


def remove_file(path: str, mode: str, confirmed=False) -> dict:
    with _actions_lock:
        if mode not in ("trash", "delete"):
            raise RemoveError("Выбери перенос в корзину или удаление навсегда")
        if mode == "delete" and confirmed is not True:
            raise RemoveError("Для удаления навсегда нужно явное подтверждение")
        item = Path(os.path.abspath(Path(path).expanduser()))
        key = os.path.normcase(str(item))
        authorized = _allowed.get(key)
        if authorized is None:
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
            _cache.clear()
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
            _allowed.clear()
            _cache.clear()


def last_run() -> dict | None:
    with _actions_lock:
        return trash.last_run("diskmap")


def _note_error(counters: dict, path: str, reason: str) -> None:
    if len(counters["errors"]) < MAX_ERRORS:
        counters["errors"].append({"path": path, "reason": reason})


def _is_link(stat: os.stat_result) -> bool:
    return fileguard.is_link(stat)


def _walk(path: Path, counters: dict, depth: int = 0) -> tuple[int, int]:
    """Суммарный размер и число файлов внутри папки."""
    total = 0
    files = 0
    try:
        entries = list(os.scandir(path))
    except OSError as exc:
        _note_error(counters, str(path), f"папка недоступна: {exc.strerror or exc}")
        return 0, 0

    for entry in entries:
        if counters["entries"] >= MAX_ENTRIES:
            counters["truncated"] = True
            break
        counters["entries"] += 1

        try:
            stat = entry.stat(follow_symlinks=False)
            is_dir = entry.is_dir(follow_symlinks=False)
            is_file = entry.is_file(follow_symlinks=False)
        except OSError:
            _note_error(counters, entry.path, "не удалось прочитать")
            continue

        if is_dir:
            if _is_link(stat):
                counters["links"] += 1
                continue
            if depth >= MAX_DEPTH:
                counters["truncated"] = True
                continue
            child_size, child_files = _walk(Path(entry.path), counters, depth + 1)
            counters["dirs"] += 1
            total += child_size
            files += child_files
        elif is_file:
            total += stat.st_size
            files += 1

    return total, files


def _cached(path: str) -> dict | None:
    hit = _cache.get(path)
    if not hit:
        return None
    stamp, payload = hit
    if time.time() - stamp > CACHE_TTL:
        _cache.pop(path, None)
        return None
    return payload


def _remember(path: str, payload: dict) -> None:
    if len(_cache) >= MAX_CACHE:
        oldest = next(iter(_cache), None)
        if oldest is not None:
            _cache.pop(oldest, None)
    _cache[path] = (time.time(), payload)


def scan(folder: str) -> dict:
    if not folder or not folder.strip():
        raise ScanError("Укажи папку, которую нужно посчитать")

    root = Path(folder).expanduser()
    if not root.exists():
        raise ScanError("Такой папки нет — проверь путь")
    if not root.is_dir():
        raise ScanError("Это файл, а нужна папка")
    root = root.resolve()

    key = str(root).lower()
    cached = _cached(key)
    if cached:
        return cached

    started = time.perf_counter()
    counters = {"entries": 0, "dirs": 0, "files": 0, "links": 0, "truncated": False, "errors": []}

    try:
        children = list(os.scandir(root))
    except OSError as exc:
        raise ScanError(f"Не получилось прочитать папку: {exc.strerror or exc}") from exc

    entries: list[dict] = []
    loose_size = 0
    loose_files = 0

    for entry in children:
        if counters["entries"] >= MAX_ENTRIES:
            counters["truncated"] = True
            break
        counters["entries"] += 1

        try:
            stat = entry.stat(follow_symlinks=False)
            is_dir = entry.is_dir(follow_symlinks=False)
            is_file = entry.is_file(follow_symlinks=False)
        except OSError:
            _note_error(counters, entry.path, "не удалось прочитать")
            continue

        if is_dir:
            if _is_link(stat):
                counters["links"] += 1
                continue
            size, files = _walk(Path(entry.path), counters, depth=1)
            counters["dirs"] += 1
            counters["files"] += files
            entries.append(
                {
                    "name": entry.name,
                    "path": entry.path,
                    "kind": "dir",
                    "size": size,
                    "count": files,
                }
            )
        elif is_file:
            loose_size += stat.st_size
            loose_files += 1
            counters["files"] += 1

    if loose_files:
        entries.append(
            {
                "name": "Файлы в этой папке",
                "path": str(root),
                "kind": "files",
                "size": loose_size,
                "count": loose_files,
            }
        )

    entries.sort(key=lambda item: (-item["size"], item["name"].lower()))
    total = sum(item["size"] for item in entries)

    payload = {
        "folder": str(root),
        "name": root.name or str(root),
        "parent": str(root.parent) if root.parent != root else None,
        "total": total,
        "entries": entries,
        "dirs": counters["dirs"],
        "files": counters["files"],
        "links": counters["links"],
        "errors": counters["errors"],
        "truncated": counters["truncated"],
        "seconds": round(time.perf_counter() - started, 2),
    }
    _remember(key, payload)
    return payload
