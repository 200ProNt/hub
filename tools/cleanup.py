"""Уборка: старые файлы, мусорные остатки и пустые папки.

Ничего не удаляется молча: сервер сначала показывает список, а потом принимает
только те пути, которые сам же и показал. Основной путь — корзина хаба, из
которой всё возвращается одной кнопкой. Удаление навсегда требует отдельного
подтверждения от пользователя.
"""

from __future__ import annotations

import json
import os
import stat
import threading
import time
from pathlib import Path

from tools import paths

from tools import fileguard, trash

DEFAULT_AGE_DAYS = 365
MAX_AGE_DAYS = 3650
MAX_ENTRIES = 200_000
MAX_DEPTH = 40

JUNK_SUFFIXES = {
    ".tmp", ".temp", ".bak", ".old", ".orig", ".part", ".partial",
    ".crdownload", ".download", ".dmp", ".chk", ".cache", ".log.old",
}
JUNK_NAMES = {"thumbs.db", "ehthumbs.db", ".ds_store"}

DEFAULT_JUNK_SUFFIXES = set(JUNK_SUFFIXES)
DEFAULT_JUNK_NAMES = set(JUNK_NAMES)


def _rules_file() -> Path:
    override = os.environ.get("HUB_CLEANUP_RULES_FILE")
    if override:
        return Path(override)
    return paths.DATA_DIR / "cleanup_rules.json"


def get_rules() -> dict:
    return {
        "suffixes": sorted(list(JUNK_SUFFIXES)),
        "names": sorted(list(JUNK_NAMES)),
    }


def load_rules() -> dict:
    rf = _rules_file()
    if rf.exists():
        try:
            raw = json.loads(rf.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                suffixes = set(raw.get("suffixes", []))
                names = set(raw.get("names", []))
                if suffixes:
                    JUNK_SUFFIXES.clear()
                    JUNK_SUFFIXES.update(suffixes)
                if names:
                    JUNK_NAMES.clear()
                    JUNK_NAMES.update(names)
                return get_rules()
        except Exception:
            pass
    return get_rules()


def save_rules(rules: dict) -> dict:
    if isinstance(rules, dict):
        new_suffixes = {
            (s.lower().strip() if s.strip().startswith(".") else f".{s.lower().strip()}")
            for s in rules.get("suffixes", [])
            if s and s.strip()
        }
        new_names = {n.lower().strip() for n in rules.get("names", []) if n and n.strip()}
        if new_suffixes:
            JUNK_SUFFIXES.clear()
            JUNK_SUFFIXES.update(new_suffixes)
        if new_names:
            JUNK_NAMES.clear()
            JUNK_NAMES.update(new_names)
        rf = _rules_file()
        try:
            rf.parent.mkdir(parents=True, exist_ok=True)
            rf.write_text(json.dumps(get_rules(), ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
    return get_rules()


def reset_rules() -> dict:
    rf = _rules_file()
    if rf.exists():
        try:
            rf.unlink()
        except OSError:
            pass
    JUNK_SUFFIXES.clear()
    JUNK_SUFFIXES.update(DEFAULT_JUNK_SUFFIXES)
    JUNK_NAMES.clear()
    JUNK_NAMES.update(DEFAULT_JUNK_NAMES)
    return get_rules()


load_rules()


class ScanError(RuntimeError):
    """Папку не удалось обойти."""


class RemoveError(RuntimeError):
    """Путь не прошёл проверку перед удалением."""


_allowed: dict[str, tuple] = {}
_lock = threading.RLock()


def _is_link(info: os.stat_result) -> bool:
    return fileguard.is_link(info)


def _has_children(path: Path) -> bool:
    try:
        with os.scandir(path) as entries:
            return next(entries, None) is not None
    except OSError:
        return False


def _junk(name: str) -> bool:
    lower = name.lower()
    if lower in JUNK_NAMES:
        return True
    if lower.startswith("~$"):
        return True
    return Path(lower).suffix in JUNK_SUFFIXES


def scan(folder: str, age_days: int = DEFAULT_AGE_DAYS, include_junk: bool = True) -> dict:
    with _lock:
        _allowed.clear()
        if not folder or not folder.strip():
            raise ScanError("Укажи папку для уборки")
        try:
            root = fileguard.check_safe_folder(folder)
        except fileguard.GuardError as exc:
            raise ScanError(str(exc)) from exc

        try:
            age_days = int(age_days)
        except (TypeError, ValueError):
            age_days = DEFAULT_AGE_DAYS
        age_days = max(0, min(MAX_AGE_DAYS, age_days))
        cutoff = time.time() - age_days * 86_400

        try:
            root_parents = fileguard.parents(root)
        except fileguard.GuardError as exc:
            raise ScanError(str(exc)) from exc
        except OSError as exc:
            raise ScanError(f"Не получилось прочитать папку: {exc}") from exc

        started = time.perf_counter()
        old: list[dict] = []
        junk: list[dict] = []
        empty: list[dict] = []
        errors: list[dict] = []
        seen = 0
        links = 0
        truncated = False

        def on_error(exc: OSError) -> None:
            if len(errors) < 25:
                errors.append({"path": getattr(exc, "filename", "") or str(root), "reason": exc.strerror or str(exc)})

        for current, dirs, names in os.walk(root, topdown=False, onerror=on_error, followlinks=False):
            current_path = Path(current)
            depth = len(current_path.relative_to(root).parts)
            kept = []
            for name in dirs:
                child = os.path.join(current, name)
                try:
                    info = os.lstat(child)
                except OSError:
                    continue
                if _is_link(info):
                    links += 1
                    continue
                kept.append(name)

            for name in kept:
                child = Path(current) / name
                try:
                    info = child.lstat()
                    has_children = _has_children(child)
                except OSError:
                    continue
                if has_children:
                    continue
                entry = {
                    "name": name,
                    "path": str(child),
                    "size": 0,
                    "kind": "dir",
                }
                try:
                    _allowed[os.path.normcase(str(child))] = (
                        fileguard.identity(info),
                        root_parents if current_path == root else fileguard.parents(current_path),
                    )
                except (OSError, fileguard.GuardError):
                    entry["unsafe"] = True
                    continue
                empty.append(entry)

            for name in names:
                if seen >= MAX_ENTRIES:
                    truncated = True
                    break
                seen += 1
                child = Path(current) / name
                try:
                    info = child.lstat()
                except OSError:
                    continue
                if not stat.S_ISREG(info.st_mode) or _is_link(info):
                    continue
                is_junk = include_junk and _junk(name)
                is_old = info.st_mtime < cutoff
                if not is_junk and not is_old:
                    continue
                entry = {
                    "name": name,
                    "path": str(child),
                    "size": info.st_size,
                    "modified": info.st_mtime,
                    "kind": "file",
                    "reason": "junk" if is_junk else "old",
                }
                try:
                    _allowed[os.path.normcase(str(child))] = (
                        fileguard.identity(info),
                        root_parents if current_path == root else fileguard.parents(current_path),
                    )
                except (OSError, fileguard.GuardError):
                    entry["unsafe"] = True
                    if is_junk:
                        junk.append(entry)
                    else:
                        old.append(entry)
                    continue
                if is_junk:
                    junk.append(entry)
                else:
                    old.append(entry)
            if truncated:
                break

        old.sort(key=lambda item: (-item["size"], item["name"].lower()))
        junk.sort(key=lambda item: (-item["size"], item["name"].lower()))
        empty.sort(key=lambda item: item["path"].lower())

        if truncated:
            errors.append({"path": str(root), "reason": "папка слишком большая, обход остановлен"})

        safe_old = sum(item["size"] for item in old if not item.get("unsafe"))
        safe_junk = sum(item["size"] for item in junk if not item.get("unsafe"))
        return {
            "folder": str(root),
            "age_days": age_days,
            "old": old,
            "junk": junk,
            "empty": empty,
            "old_size": safe_old,
            "junk_size": safe_junk,
            "empty_size": 0,
            "scanned": seen,
            "links": links,
            "errors": errors,
            "truncated": truncated,
            "seconds": round(time.perf_counter() - started, 2),
        }


def remove(paths: list[str], mode: str = "trash", confirmed=False, folder: str = "") -> dict:
    """Убрать выбранные пути: в корзину (по умолчанию) или насовсем."""
    with _lock:
        if mode not in ("trash", "delete"):
            raise RemoveError("Выбери перенос в корзину или удаление навсегда")
        if mode == "delete" and confirmed is not True:
            raise RemoveError("Для удаления навсегда нужно явное подтверждение")
        if not isinstance(paths, list) or not paths:
            raise RemoveError("Ничего не выбрано")

        result = {"removed_count": 0, "removed_size": 0, "errors": [], "run_id": None, "deleted": []}
        files: list[Path] = []
        dirs: list[Path] = []

        for raw in dict.fromkeys(str(item) for item in paths):
            item = Path(os.path.abspath(Path(raw).expanduser()))
            key = os.path.normcase(str(item))
            authorized = _allowed.get(key)
            if authorized is None:
                result["errors"].append({"path": str(item), "reason": "путь не из последнего списка; открой папку заново"})
                continue
            try:
                info = item.lstat()
                parents = fileguard.parents(item.parent)
            except fileguard.GuardError as exc:
                result["errors"].append({"path": str(item), "reason": str(exc)})
                _allowed.pop(key, None)
                continue
            except OSError as exc:
                result["errors"].append({"path": str(item), "reason": f"путь недоступен: {exc}"})
                _allowed.pop(key, None)
                continue

            if _is_link(info) or fileguard.identity(info) != authorized[0] or parents != authorized[1]:
                result["errors"].append({"path": str(item), "reason": "путь изменился; открой папку заново"})
                _allowed.pop(key, None)
                continue

            if stat.S_ISDIR(info.st_mode):
                try:
                    has_children = _has_children(item)
                except OSError as exc:
                    result["errors"].append({"path": str(item), "reason": f"папка недоступна: {exc}"})
                    continue
                if has_children:
                    result["errors"].append({"path": str(item), "reason": "папка уже не пустая"})
                    continue
                dirs.append(item)
            elif stat.S_ISREG(info.st_mode):
                files.append(item)
            else:
                result["errors"].append({"path": str(item), "reason": "это не файл и не папка"})

        if mode == "trash":
            if files or dirs:
                try:
                    moved = trash.move(
                        [str(item) for item in files + dirs],
                        source="cleanup",
                        meta={"folder": folder or None},
                    )
                except (OSError, trash.TrashError) as exc:
                    result["errors"].append({"path": "", "reason": str(exc)})
                    return result
                result["run_id"] = moved["run_id"]
                result["removed_count"] = moved["removed_count"]
                result["removed_size"] = moved["removed_size"]
                result["errors"].extend(moved["errors"])
            return result

        freed = 0
        removed = 0
        # Папки удаляем первыми и без рекурсии: rmdir сам откажется, если внутри что-то есть.
        for item in dirs + files:
            try:
                if item.is_dir() and not item.is_symlink():
                    item.rmdir()
                else:
                    freed += item.stat().st_size
                    item.unlink()
                removed += 1
                result["deleted"].append(str(item))
            except OSError as exc:
                result["errors"].append({"path": str(item), "reason": exc.strerror or str(exc)})
            finally:
                _allowed.pop(os.path.normcase(str(item)), None)

        result["removed_count"] = removed
        result["removed_size"] = freed
        return result


def undo(run_id: str) -> dict:
    with _lock:
        try:
            _, journal = trash._read(run_id)
            if journal.get("source") != "cleanup":
                raise RemoveError("Это не уборка")
            return trash.undo(run_id)
        except (OSError, trash.TrashError) as exc:
            raise RemoveError(str(exc)) from exc
        finally:
            _allowed.clear()


def last_run() -> dict | None:
    with _lock:
        return trash.last_run("cleanup")
