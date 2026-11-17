"""Поиск дубликатов по содержимому и безопасное удаление лишних копий.

Сравниваем не имена, а байты: сначала группируем по размеру (дешёво),
потом считаем BLAKE2b только для файлов с одинаковым размером.

Ничего не удаляет насовсем: выбранные копии уезжают в data/trash/<run_id>
и возвращаются кнопкой «Вернуть».
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from pathlib import Path

CHUNK = 1024 * 1024
DEFAULT_MIN_SIZE = 1024
MAX_FILES = 20_000

SYSTEM_JUNK = {
    "$recycle.bin",
    "system volume information",
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "site-packages",
    "dist-info",
    ".idea",
    ".vs",
    ".vscode",
    ".cache",
    ".gradle",
    ".m2",
    "target",
    "dist",
    "build",
    ".next",
    ".nuxt",
    ".turbo",
}


class ScanError(RuntimeError):
    """Папку не удалось прочитать."""


class RemoveError(RuntimeError):
    """Нельзя убрать выбранные файлы."""


# --- Куда складываем «корзину» ---------------------------------------------


def _trash_dir() -> Path:
    override = os.environ.get("HUB_TRASH_DIR")
    base = (
        Path(override)
        if override
        else Path(__file__).resolve().parent.parent / "data" / "trash"
    )
    base.mkdir(parents=True, exist_ok=True)
    return base


# --- Сканирование ----------------------------------------------------------


def _hash_file(path: Path) -> str | None:
    digest = hashlib.blake2b(digest_size=16)
    try:
        with path.open("rb") as handle:
            while True:
                block = handle.read(CHUNK)
                if not block:
                    break
                digest.update(block)
    except OSError:
        return None
    return digest.hexdigest()


def _iter_files(root: Path, recursive: bool) -> tuple[list[Path], list[dict], bool, int]:
    found: list[Path] = []
    errors: list[dict] = []
    truncated = False
    skipped = 0
    stack = [root]

    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError as exc:
            errors.append({"path": str(current), "reason": f"папка недоступна: {exc.strerror or exc}"})
            continue

        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    if recursive:
                        if entry.name.lower() in SYSTEM_JUNK:
                            skipped += 1
                        else:
                            stack.append(Path(entry.path))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
            except OSError:
                continue

            found.append(Path(entry.path))
            if len(found) >= MAX_FILES:
                truncated = True
                return found, errors, truncated, skipped

    return found, errors, truncated, skipped


def _public_file(root: Path, path: Path, size: int, mtime: float) -> dict:
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        relative = path.name
    parent = relative.rsplit("/", 1)[0] if "/" in relative else ""
    return {
        "path": str(path),
        "name": path.name,
        "rel": relative,
        "dir": parent,
        "size": size,
        "mtime": mtime,
    }


def scan(folder: str, recursive: bool = True, min_size: int = DEFAULT_MIN_SIZE) -> dict:
    if not folder or not folder.strip():
        raise ScanError("Укажи папку для проверки")

    root = Path(folder).expanduser()
    if not root.exists():
        raise ScanError("Такой папки нет — проверь путь")
    if not root.is_dir():
        raise ScanError("Это файл, а нужна папка")
    root = root.resolve()

    min_size = max(0, int(min_size or 0))
    candidates, errors, truncated, skipped = _iter_files(root, recursive)

    by_size: dict[int, list[tuple[Path, float]]] = {}
    for path in candidates:
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_size < max(1, min_size):
            continue
        by_size.setdefault(stat.st_size, []).append((path, stat.st_mtime))

    groups: list[dict] = []
    duplicate_files = 0
    wasted = 0

    for size, entries in by_size.items():
        if len(entries) < 2:
            continue
        by_hash: dict[str, list[tuple[Path, float]]] = {}
        for path, mtime in entries:
            digest = _hash_file(path)
            if digest is None:
                errors.append({"path": str(path), "reason": "не удалось прочитать файл"})
                continue
            by_hash.setdefault(digest, []).append((path, mtime))

        for digest, matches in by_hash.items():
            if len(matches) < 2:
                continue
            matches.sort(key=lambda item: item[1])
            files = [_public_file(root, path, size, mtime) for path, mtime in matches]
            free = size * (len(files) - 1)
            groups.append(
                {
                    "key": digest[:12],
                    "hash": digest,
                    "size": size,
                    "files": files,
                    "count": len(files),
                    "free": free,
                }
            )
            duplicate_files += len(files) - 1
            wasted += free

    groups.sort(key=lambda group: group["free"], reverse=True)

    result = {
        "folder": str(root),
        "groups": groups,
        "total_files": len(candidates),
        "checked_files": sum(len(entries) for entries in by_size.values()),
        "groups_count": len(groups),
        "duplicate_files": duplicate_files,
        "wasted": wasted,
        "errors": errors,
        "truncated": truncated,
        "skipped_dirs": skipped,
        "recursive": bool(recursive),
        "min_size": min_size,
    }
    _last_scan.clear()
    _last_scan.update({"folder": str(root), "groups": groups})
    return result


# Последний скан держим в памяти: по нему проверяем, что удалять можно только
# то, что реально нашлось, и что в каждой группе остаётся хотя бы одна копия.
_last_scan: dict = {}


def _scan_signature() -> tuple[str, dict[str, dict]]:
    folder = str(_last_scan.get("folder") or "")
    index: dict[str, dict] = {}
    for group in _last_scan.get("groups", []):
        for item in group["files"]:
            index[item["path"]] = {"group": group["hash"], "size": item["size"]}
    return folder, index


# --- Удаление в корзину хаба ----------------------------------------------


def remove(folder: str, paths: list[str]) -> dict:
    folder, index = _scan_signature()
    if not folder:
        raise RemoveError("Сначала найди дубликаты, потом убирай")

    wanted: list[str] = []
    for raw in paths:
        path = str(Path(str(raw)))
        if path not in index:
            raise RemoveError("Список устарел — проверь папку заново")
        if path not in wanted:
            wanted.append(path)
    if not wanted:
        raise RemoveError("Ничего не выбрано")

    # В каждой группе должна остаться хотя бы одна копия.
    chosen_per_group: dict[str, int] = {}
    for path in wanted:
        chosen_per_group[index[path]["group"]] = chosen_per_group.get(index[path]["group"], 0) + 1
    for group in _last_scan.get("groups", []):
        hash_value = group["hash"]
        total = len(group["files"])
        if chosen_per_group.get(hash_value, 0) >= total:
            raise RemoveError(
                "Нельзя убрать все копии одного файла — оставь хотя бы одну"
            )

    run_id = f"del_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    trash_root = _trash_dir() / run_id
    files_root = trash_root / "files"
    files_root.mkdir(parents=True, exist_ok=True)

    moved: list[dict] = []
    errors: list[dict] = []
    for number, path in enumerate(wanted, start=1):
        source = Path(path)
        size = index[path]["size"]
        if not source.is_file():
            errors.append({"path": path, "reason": "файл уже исчез"})
            continue
        try:
            if source.stat().st_size != size:
                errors.append({"path": path, "reason": "файл изменился — проверь заново"})
                continue
        except OSError:
            errors.append({"path": path, "reason": "нет доступа к файлу"})
            continue

        target = files_root / f"{number:04d}_{source.name}"
        try:
            shutil.move(str(source), str(target))
        except OSError as exc:
            errors.append({"path": path, "reason": exc.strerror or str(exc)})
            continue
        moved.append({"from": str(source), "to": str(target), "size": size})

    journal = {
        "id": run_id,
        "folder": folder,
        "time": time.time(),
        "moved": moved,
        "undone": False,
    }
    (trash_root / "journal.json").write_text(
        json.dumps(journal, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Скан устарел: часть файлов уехала.
    _last_scan.clear()

    if not moved:
        shutil.rmtree(trash_root, ignore_errors=True)
        return {
            "run_id": None,
            "removed_count": 0,
            "removed_size": 0,
            "errors": errors,
        }

    return {
        "run_id": run_id,
        "removed_count": len(moved),
        "removed_size": sum(item["size"] for item in moved),
        "errors": errors,
    }


def _read_journal(run_id: str) -> tuple[Path, dict]:
    if not run_id or any(char not in "0123456789abcdefghijklmnopqrstuvwxyz_" for char in run_id):
        raise RemoveError("Некорректный номер переноса")
    journal_path = _trash_dir() / run_id / "journal.json"
    try:
        data = json.loads(journal_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise RemoveError("Не нашёл журнал этого переноса")
    return journal_path, data


def undo(run_id: str) -> dict:
    journal_path, data = _read_journal(run_id)
    if data.get("undone"):
        return {"restored_count": 0, "restored_size": 0}

    restored: list[dict] = []
    errors: list[dict] = []
    for item in data.get("moved", []):
        source = Path(item["to"])
        target = Path(item["from"])
        if not source.is_file():
            errors.append({"path": item["from"], "reason": "копия в корзине пропала"})
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise RemoveError("на месте уже есть файл с таким именем")
            shutil.move(str(source), str(target))
        except (OSError, RemoveError) as exc:
            errors.append({"path": item["from"], "reason": str(exc)})
            continue
        restored.append(item)

    data["undone"] = not errors
    journal_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if not errors:
        shutil.rmtree(journal_path.parent, ignore_errors=True)

    _last_scan.clear()
    return {
        "restored_count": len(restored),
        "restored_size": sum(item["size"] for item in restored),
        "errors": errors,
    }


def last_run() -> dict | None:
    base = _trash_dir()
    try:
        journals = sorted(base.glob("*/journal.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return None

    for journal in journals:
        try:
            data = json.loads(journal.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("undone"):
            continue
        moved = data.get("moved", [])
        if not moved:
            continue
        return {
            "run_id": data.get("id"),
            "folder": data.get("folder"),
            "time": data.get("time"),
            "count": len(moved),
            "size": sum(item.get("size", 0) for item in moved),
        }
    return None


def allowed_path(path: str) -> bool:
    """Файл показываем только если он был в последнем скане."""
    _, index = _scan_signature()
    return str(Path(path)) in index
