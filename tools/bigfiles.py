"""Большие файлы: самые тяжёлые файлы внутри папки, по убыванию размера.

Папки обходим без ссылок, глубину ограничиваем. Удалять разрешено только то,
что сервер сам показал в последнем списке: путь сверяется с «отпечатком» файла
и всех его папок, поэтому подменить файл между показом и удалением не выйдет.
"""

from __future__ import annotations

import os
import stat
import threading
import time
from pathlib import Path

from tools import fileguard, trash

DEFAULT_MIN_SIZE = 20 * 1024 * 1024
DEFAULT_LIMIT = 100
MAX_LIMIT = 500
MAX_ENTRIES = 400_000
MAX_DEPTH = 40


class ScanError(RuntimeError):
    """Папку не удалось обойти."""


class RemoveError(RuntimeError):
    """Файл не прошёл проверку перед удалением."""


_allowed: dict[str, tuple] = {}
_lock = threading.RLock()


def _is_link(info: os.stat_result) -> bool:
    return fileguard.is_link(info)


def scan(
    folder: str,
    limit: int = DEFAULT_LIMIT,
    min_size: int = DEFAULT_MIN_SIZE,
) -> dict:
    with _lock:
        _allowed.clear()
        if not folder or not folder.strip():
            raise ScanError("Укажи папку, в которой искать большие файлы")
        try:
            root = fileguard.check_safe_folder(folder)
        except fileguard.GuardError as exc:
            raise ScanError(str(exc)) from exc

        limit = max(1, min(MAX_LIMIT, int(limit)))
        min_size = max(0, int(min_size))

        try:
            root_parents = fileguard.parents(root)
        except fileguard.GuardError as exc:
            raise ScanError(str(exc)) from exc
        except OSError as exc:
            raise ScanError(f"Не получилось прочитать папку: {exc}") from exc

        started = time.perf_counter()
        found: list[dict] = []
        scanned = 0
        skipped_links = 0
        errors: list[dict] = []
        truncated = False

        def on_error(exc: OSError) -> None:
            if len(errors) < 25:
                errors.append({"path": getattr(exc, "filename", ""), "reason": exc.strerror or str(exc)})

        for current, dirs, names in os.walk(root, onerror=on_error, followlinks=False):
            depth = len(Path(current).relative_to(root).parts)
            if depth >= MAX_DEPTH:
                dirs[:] = []
                truncated = True
            kept = []
            for name in dirs:
                child = os.path.join(current, name)
                try:
                    info = os.lstat(child)
                except OSError:
                    continue
                if _is_link(info):
                    skipped_links += 1
                    continue
                kept.append(name)
            dirs[:] = kept

            for name in names:
                if scanned >= MAX_ENTRIES:
                    truncated = True
                    break
                scanned += 1
                child = os.path.join(current, name)
                try:
                    info = os.lstat(child)
                except OSError:
                    continue
                if not stat.S_ISREG(info.st_mode) or _is_link(info):
                    continue
                if info.st_size < min_size:
                    continue
                found.append(
                    {
                        "name": name,
                        "path": child,
                        "size": info.st_size,
                        "modified": info.st_mtime,
                        "folder": current,
                    }
                )
            if truncated:
                break

        found.sort(key=lambda item: (-item["size"], item["name"].lower()))
        top = found[:limit]

        for item in top:
            try:
                identity = fileguard.identity(os.lstat(item["path"]))
                folder_parents = fileguard.parents(Path(item["folder"]))
            except (OSError, fileguard.GuardError):
                item["unsafe"] = True
                continue
            _allowed[os.path.normcase(item["path"])] = (identity, folder_parents)
        if truncated:
            errors.append({"path": str(root), "reason": "папка слишком большая, обход остановлен"})

        return {
            "folder": str(root),
            "files": top,
            "matched": len(found),
            "matched_size": sum(item["size"] for item in found),
            "scanned": scanned,
            "min_size": min_size,
            "limit": limit,
            "links": skipped_links,
            "errors": errors,
            "truncated": truncated,
            "seconds": round(time.perf_counter() - started, 2),
        }


def remove(path: str, mode: str, confirmed=False) -> dict:
    with _lock:
        if mode not in ("trash", "delete"):
            raise RemoveError("Выбери перенос в корзину или удаление навсегда")
        if mode == "delete" and confirmed is not True:
            raise RemoveError("Для удаления навсегда нужно явное подтверждение")
        item = Path(os.path.abspath(Path(path).expanduser()))
        key = os.path.normcase(str(item))
        authorized = _allowed.get(key)
        if authorized is None:
            raise RemoveError("Этот файл не из последнего списка; запусти поиск заново")
        try:
            info = item.lstat()
            if (
                not stat.S_ISREG(info.st_mode)
                or _is_link(info)
                or fileguard.identity(info) != authorized[0]
                or fileguard.parents(item.parent) != authorized[1]
            ):
                raise RemoveError("Файл или папка изменились; запусти поиск заново")
        except fileguard.GuardError as exc:
            raise RemoveError(str(exc)) from exc
        except OSError as exc:
            raise RemoveError(f"Файл или папка недоступны: {exc}") from exc

        result = {"removed_count": 0, "removed_size": 0, "errors": [], "run_id": None}
        try:
            if mode == "trash":
                moved = trash.move([str(item)], source="bigfiles", meta={"folder": str(item.parent)})
                result.update({name: moved[name] for name in result if name in moved})
            else:
                item.unlink()
                result.update(removed_count=1, removed_size=info.st_size)
        except (OSError, trash.TrashError) as exc:
            result["errors"].append({"path": str(item), "reason": str(exc)})
        finally:
            _allowed.pop(key, None)
        return result


def undo(run_id: str) -> dict:
    with _lock:
        try:
            _, journal = trash._read(run_id)
            if journal.get("source") != "bigfiles":
                raise RemoveError("Это не перенос больших файлов")
            return trash.undo(run_id)
        except (OSError, trash.TrashError) as exc:
            raise RemoveError(str(exc)) from exc
        finally:
            _allowed.clear()


def last_run() -> dict | None:
    with _lock:
        return trash.last_run("bigfiles")
