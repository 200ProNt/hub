"""Логика сортировки файлов: категории, план переноса, применение, отмена.

Модуль не знает ничего про интерфейс и сервер — только про файлы.
Журналы переносов лежат в hub/data/runs.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
import uuid
from pathlib import Path

# --- Категории -------------------------------------------------------------

CATEGORY_RULES: list[tuple[str, set[str]]] = [
    (
        "Изображения",
        {
            ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".ico",
            ".heic", ".heif", ".tif", ".tiff", ".avif", ".raw", ".cr2", ".nef",
            ".psd", ".ai",
        },
    ),
    (
        "Видео",
        {
            ".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".flv", ".m4v",
            ".mpg", ".mpeg", ".3gp", ".ts", ".ogv",
        },
    ),
    (
        "Музыка",
        {
            ".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus",
            ".aiff", ".aif", ".mid", ".midi", ".amr",
        },
    ),
    (
        "Документы",
        {
            ".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".xls", ".xlsx",
            ".csv", ".ppt", ".pptx", ".md", ".epub", ".fb2", ".djvu", ".pages",
            ".numbers", ".key", ".ods", ".odp", ".one", ".acsm",
        },
    ),
    (
        "Архивы",
        {
            ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso",
            ".tgz", ".cab", ".lz", ".zst",
        },
    ),
    (
        "Программы",
        {
            ".exe", ".msi", ".apk", ".dmg", ".deb", ".rpm", ".appimage", ".bat",
            ".cmd", ".ps1", ".jar", ".msix", ".pkg", ".appx", ".reg",
        },
    ),
    (
        "Код",
        {
            ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".json", ".html",
            ".htm", ".css", ".scss", ".sass", ".less", ".java", ".c", ".cpp",
            ".h", ".hpp", ".cs", ".go", ".rs", ".php", ".rb", ".swift", ".kt",
            ".lua", ".sql", ".yml", ".yaml", ".toml", ".ini", ".sh", ".xml",
            ".vue", ".svelte", ".ipynb", ".gradle", ".cmake",
        },
    ),
]

FALLBACK_CATEGORY = "Другое"

EXT_TO_CATEGORY: dict[str, str] = {}
for _category, _extensions in CATEGORY_RULES:
    for _ext in _extensions:
        EXT_TO_CATEGORY.setdefault(_ext, _category)

CATEGORY_ORDER: list[str] = [name for name, _ in CATEGORY_RULES] + [FALLBACK_CATEGORY]
CATEGORY_NAMES: set[str] = set(CATEGORY_ORDER)

IGNORED_NAMES = {"desktop.ini", "thumbs.db", ".ds_store"}

RUN_ID_PATTERN = re.compile(r"^run_\d+_[0-9a-f]{8}$")

_FILE_ATTRIBUTE_HIDDEN = 0x2


class ScanError(Exception):
    """Папку нельзя прочитать."""


# --- Вспомогательное -------------------------------------------------------


def category_for(name: str) -> str:
    """Категория по расширению. Файлы без расширения попадают в «Другое»."""
    suffix = Path(name).suffix.lower()
    if not suffix:
        return FALLBACK_CATEGORY
    return EXT_TO_CATEGORY.get(suffix, FALLBACK_CATEGORY)


def unique_target(path: Path, taken: set[Path] | None = None) -> Path:
    """Свободное имя: file.txt -> file (1).txt, если такое уже есть."""
    if not path.exists() and (taken is None or path not in taken):
        return path
    stem, suffix = path.stem, path.suffix
    index = 1
    while True:
        candidate = path.with_name(f"{stem} ({index}){suffix}")
        if not candidate.exists() and (taken is None or candidate not in taken):
            return candidate
        index += 1


def is_hidden(path: Path) -> bool:
    name = path.name
    if name.startswith("."):
        return True
    if name.lower() in IGNORED_NAMES:
        return True
    try:
        attributes = getattr(path.stat(), "st_file_attributes", 0)
    except OSError:
        return True
    return bool(attributes & _FILE_ATTRIBUTE_HIDDEN)


def _normalized(path: Path) -> str:
    return os.path.normcase(str(path))


def _runs_dir() -> Path:
    override = os.environ.get("HUB_RUNS_DIR")
    directory = (
        Path(override)
        if override
        else Path(__file__).resolve().parent.parent / "data" / "runs"
    )
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _write_run(root: Path, moved: list[dict]) -> str:
    run_id = f"run_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    payload = {
        "id": run_id,
        "folder": str(root),
        "time": time.time(),
        "moved": moved,
        "undone": False,
    }
    target = _runs_dir() / f"{run_id}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return run_id


def _cleanup_empty_category_dirs(root: Path, categories: set[str]) -> None:
    """После отмены убираем папки категорий, если они опустели."""
    for name in categories:
        candidate = root / name
        try:
            if candidate.is_dir() and not any(candidate.iterdir()):
                candidate.rmdir()
        except OSError:
            pass


# --- Основные операции -----------------------------------------------------


def scan(folder: str) -> dict:
    """План сортировки: что куда переедет. Ничего не двигает."""
    raw = Path(folder).expanduser()
    if not str(folder).strip():
        raise ScanError("Не указана папка")
    try:
        if not raw.is_dir():
            raise ScanError(f"Папка не найдена: {folder}")
        root = raw.resolve()
        entries = sorted(root.iterdir(), key=lambda p: p.name.lower())
    except PermissionError as exc:
        raise ScanError("Нет доступа к этой папке") from exc
    except OSError as exc:
        raise ScanError(f"Не получилось открыть папку: {exc}") from exc

    items: list[dict] = []
    taken: set[Path] = set()

    for entry in entries:
        try:
            if not entry.is_file() or is_hidden(entry):
                continue
            if entry.name in CATEGORY_NAMES:
                continue
            info = entry.stat()
        except OSError:
            continue

        category = category_for(entry.name)
        target = unique_target(root / category / entry.name, taken)
        taken.add(target)
        items.append(
            {
                "id": f"f{len(items)}",
                "name": entry.name,
                "path": str(entry),
                "size": info.st_size,
                "mtime": info.st_mtime,
                "category": category,
                "dest": str(target),
                "dest_rel": f"{category}/{target.name}",
                "renamed": target.name != entry.name,
            }
        )

    items.sort(key=lambda item: (CATEGORY_ORDER.index(item["category"]), item["name"].lower()))

    counts: dict[str, int] = {}
    for item in items:
        counts[item["category"]] = counts.get(item["category"], 0) + 1

    return {
        "folder": str(root),
        "items": items,
        "counts": counts,
        "categories": [name for name in CATEGORY_ORDER if counts.get(name)],
        "total_size": sum(item["size"] for item in items),
        "total": len(items),
    }


def apply(folder: str, files: list[str]) -> dict:
    """Переносит только переданные файлы. Возвращает отчёт."""
    raw = Path(folder).expanduser()
    if not raw.is_dir():
        raise ScanError(f"Папка не найдена: {folder}")
    root = raw.resolve()

    moved: list[dict] = []
    errors: list[dict] = []

    for source in files:
        try:
            candidate = Path(source)
            if not candidate.is_absolute():
                candidate = root / candidate
            candidate = candidate.resolve()
        except OSError:
            errors.append({"file": str(source), "reason": "Некорректный путь"})
            continue

        if _normalized(candidate.parent) != _normalized(root):
            errors.append({"file": candidate.name, "reason": "Файл не из выбранной папки"})
            continue
        if not candidate.is_file():
            errors.append({"file": candidate.name, "reason": "Файл уже перемещён или недоступен"})
            continue

        category = category_for(candidate.name)
        destination_dir = root / category
        try:
            destination_dir.mkdir(exist_ok=True)
            target = unique_target(destination_dir / candidate.name)
            size = candidate.stat().st_size
            shutil.move(str(candidate), str(target))
        except OSError as exc:
            errors.append({"file": candidate.name, "reason": str(exc)})
            continue

        moved.append(
            {
                "name": candidate.name,
                "src": str(candidate),
                "dst": str(target),
                "category": category,
                "size": size,
            }
        )

    run_id = _write_run(root, moved) if moved else None

    return {
        "run_id": run_id,
        "folder": str(root),
        "moved": moved,
        "errors": errors,
        "moved_count": len(moved),
        "moved_size": sum(item["size"] for item in moved),
    }


def undo(run_id: str) -> dict:
    """Возвращает файлы из последнего переноса на исходные места."""
    if not RUN_ID_PATTERN.match(run_id or ""):
        raise ValueError("Неверный идентификатор переноса")

    journal = _runs_dir() / f"{run_id}.json"
    if not journal.exists():
        raise FileNotFoundError("Журнал этого переноса не найден")

    data = json.loads(journal.read_text(encoding="utf-8"))
    if data.get("undone"):
        raise ValueError("Этот перенос уже отменён")

    restored: list[dict] = []
    errors: list[dict] = []

    for record in reversed(data.get("moved", [])):
        destination = Path(record["dst"])
        source = Path(record["src"])
        if not destination.exists():
            errors.append({"file": record["name"], "reason": "Файл не найден на новом месте"})
            continue
        try:
            source.parent.mkdir(parents=True, exist_ok=True)
            target = unique_target(source)
            shutil.move(str(destination), str(target))
        except OSError as exc:
            errors.append({"file": record["name"], "reason": str(exc)})
            continue

        restored.append(
            {
                "name": record["name"],
                "src": str(destination),
                "dst": str(target),
                "category": record.get("category", FALLBACK_CATEGORY),
                "size": record.get("size", 0),
            }
        )

    data["undone"] = True
    journal.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    root = Path(data.get("folder", ""))
    if root.is_dir():
        _cleanup_empty_category_dirs(root, {record.get("category", "") for record in data.get("moved", [])})

    return {
        "run_id": run_id,
        "folder": str(root),
        "restored": restored,
        "errors": errors,
        "restored_count": len(restored),
        "restored_size": sum(item["size"] for item in restored),
    }


def last_run() -> dict | None:
    """Последний неотменённый перенос — для кнопки «Отменить» после перезапуска."""
    try:
        journals = sorted(_runs_dir().glob("run_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return None

    for journal in journals:
        try:
            data = json.loads(journal.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("undone"):
            continue
        folder = data.get("folder")
        if not folder or not Path(folder).is_dir():
            # Папку уже удалили или перенесли — возвращать некуда.
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
