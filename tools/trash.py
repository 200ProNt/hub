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
