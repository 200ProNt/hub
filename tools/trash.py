"""Общая корзина хаба: файлы переезжают в data/trash/<номер>/ и возвращаются оттуда.

Ни одна программа хаба не удаляет файлы насовсем этим модулем — только переносит
в корзину, из которой можно вернуть. Насовсем удаляет лишь тот, кто об этом прямо
попросил (карта диска, отдельная кнопка).
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import time
import uuid
from pathlib import Path

from tools import fileguard

ALLOWED_RUN_ID = set("0123456789abcdefghijklmnopqrstuvwxyz_")


class TrashError(RuntimeError):
    """Корзина не смогла принять или вернуть файл."""


def base_dir() -> Path:
    override = os.environ.get("HUB_TRASH_DIR")
    path = Path(override) if override else Path(__file__).resolve().parent.parent / "data" / "trash"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _journal_path(run_id: str) -> Path:
    if not run_id or any(char not in ALLOWED_RUN_ID for char in run_id):
        raise TrashError("Некорректный номер переноса")
    return base_dir() / run_id / "journal.json"


def _read(run_id: str) -> tuple[Path, dict]:
    journal = _journal_path(run_id)
    try:
        data = json.loads(journal.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TrashError("Не нашёл журнал этого переноса") from exc
    return journal, data


def measure(path: Path) -> tuple[int, int]:
    """Размер и число файлов внутри папки; ссылки не разворачиваем."""
    total = 0
    count = 0
    for root, dirs, names in os.walk(path, followlinks=False):
        dirs[:] = [name for name in dirs if not os.path.islink(os.path.join(root, name))]
        for name in names:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
                count += 1
            except OSError:
                continue
    return total, count


def move(paths: list[str], source: str, meta: dict | None = None) -> dict:
    """Перенести файлы и папки в корзину. Возвращает номер переноса и что получилось."""
    unique: list[str] = []
    for raw in paths:
        path = str(Path(str(raw)))
        if path not in unique:
            unique.append(path)
    if not unique:
        raise TrashError("Ничего не выбрано")

    run_id = f"del_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    run_root = base_dir() / run_id
    files_root = run_root / "files"
    files_root.mkdir(parents=True, exist_ok=True)

    moved: list[dict] = []
    errors: list[dict] = []
    for number, path in enumerate(unique, start=1):
        item = Path(path)
        try:
            info = item.lstat()
        except OSError:
            errors.append({"path": path, "reason": "файл уже исчез"})
            continue
        if stat.S_ISLNK(info.st_mode) or fileguard.is_link(info):
            errors.append({"path": path, "reason": "это ссылка, её не трогаем"})
            continue
        if stat.S_ISDIR(info.st_mode):
            kind = "dir"
            size, count = measure(item)
        elif stat.S_ISREG(info.st_mode):
            kind = "file"
            size, count = info.st_size, 1
        else:
            errors.append({"path": path, "reason": "это не файл и не папка"})
            continue

        target = files_root / f"{number:04d}_{item.name}"
        try:
            shutil.move(str(item), str(target))
        except OSError as exc:
            errors.append({"path": path, "reason": exc.strerror or str(exc)})
            continue
        moved.append({"from": str(item), "to": str(target), "size": size, "kind": kind, "count": count})

    if not moved:
        shutil.rmtree(run_root, ignore_errors=True)
        return {"run_id": None, "moved": [], "errors": errors}

    journal = {
        "id": run_id,
        "source": source,
        "time": time.time(),
        "moved": moved,
        "undone": False,
    }
    if meta:
        journal.update(meta)
    (run_root / "journal.json").write_text(
        json.dumps(journal, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "run_id": run_id,
        "moved": moved,
        "removed_count": len(moved),
        "removed_size": sum(item["size"] for item in moved),
        "errors": errors,
    }


def undo(run_id: str) -> dict:
    journal_path, data = _read(run_id)
    if data.get("undone"):
        return {"restored_count": 0, "restored_size": 0, "errors": []}

    restored: list[dict] = []
    errors: list[dict] = []
    for item in data.get("moved", []):
        source = Path(item["to"])
        target = Path(item["from"])
        if not source.exists():
            errors.append({"path": item["from"], "reason": "копия в корзине пропала"})
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                errors.append({"path": item["from"], "reason": "на месте уже что-то есть"})
                continue
            shutil.move(str(source), str(target))
        except OSError as exc:
            errors.append({"path": item["from"], "reason": exc.strerror or str(exc)})
            continue
        restored.append(item)

    data["moved"] = [item for item in data.get("moved", []) if item not in restored]
    data["undone"] = not errors
    journal_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if not errors:
        shutil.rmtree(journal_path.parent, ignore_errors=True)

    return {
        "restored_count": len(restored),
        "restored_size": sum(item["size"] for item in restored),
        "errors": errors,
    }


PREVIEW_ITEMS = 5


def runs() -> list[dict]:
    """Что сейчас лежит в корзине: переносы, которые ещё можно вернуть, свежие сверху."""
    base = base_dir()
    found: list[dict] = []
    try:
        journals = list(base.glob("*/journal.json"))
    except OSError:
        return []

    for journal in journals:
        try:
            data = json.loads(journal.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("undone"):
            continue
        moved = data.get("moved") or []
        if not moved:
            continue
        run_id = journal.parent.name
        if data.get("id") and data["id"] != run_id:
            continue
        try:
            fallback_time = journal.parent.stat().st_mtime
        except OSError:
            fallback_time = 0.0
        found.append(
            {
                "run_id": run_id,
                "source": str(data.get("source") or ""),
                "folder": data.get("folder"),
                "time": float(data.get("time") or fallback_time),
                "count": len(moved),
                "size": sum(int(item.get("size") or 0) for item in moved),
                "items": [
                    {
                        "name": Path(str(item.get("from", ""))).name or "?",
                        "kind": item.get("kind", "file"),
                        "size": int(item.get("size") or 0),
                    }
                    for item in moved[:PREVIEW_ITEMS]
                ],
            }
        )

    found.sort(key=lambda run: run["time"], reverse=True)
    return found


def _remove_tree(path: Path) -> None:
    """Убрать папку корзины вместе с файлами только для чтения."""

    def on_error(function, target, _error) -> None:
        try:
            os.chmod(target, stat.S_IWRITE | stat.S_IREAD)
        except OSError:
            pass
        function(target)

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=on_error)
    else:
        # Python 3.10–3.11: обработчик ошибки получает ещё и исключение.
        shutil.rmtree(path, onerror=lambda function, target, _info: on_error(function, target, None))


def purge(run_ids: list[str]) -> dict:
    """Удалить переносы насовсем. Журнал и файлы уходят, вернуть их уже нельзя."""
    base = base_dir()
    freed = 0
    removed = 0
    errors: list[dict] = []

    for raw in run_ids:
        run_id = str(raw)
        try:
            _journal_path(run_id)
        except TrashError as exc:
            errors.append({"run_id": run_id, "reason": str(exc)})
            continue
        run_root = base / run_id
        try:
            run_root.resolve().relative_to(base.resolve())
        except (ValueError, OSError):
            errors.append({"run_id": run_id, "reason": "папка корзины вне хранилища"})
            continue
        if not run_root.is_dir():
            continue
        size, _ = measure(run_root)
        try:
            _remove_tree(run_root)
        except OSError as exc:
            errors.append({"run_id": run_id, "reason": exc.strerror or str(exc)})
            continue
        freed += size
        removed += 1

    return {"removed": removed, "freed": freed, "errors": errors}


def empty() -> dict:
    """Полностью очистить корзину хаба."""
    base = base_dir()
    try:
        folders = [entry.name for entry in base.iterdir() if entry.is_dir()]
    except OSError:
        return {"removed": 0, "freed": 0, "errors": []}
    return purge(folders)


def last_run(source: str) -> dict | None:
    base = base_dir()
    try:
        journals = sorted(base.glob("*/journal.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return None

    for journal in journals:
        try:
            data = json.loads(journal.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("undone") or data.get("source") != source:
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
