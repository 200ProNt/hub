"""Инструмент «Пакетное переименование файлов»: массовое переименование по правилам с историей и отменой."""

from __future__ import annotations

import fnmatch
import json
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path

from tools import paths

from tools import fileguard

DATA_DIR = paths.DATA_DIR
HISTORY_FILE = DATA_DIR / "renamer_history.json"

CYRILLIC_TO_LATIN = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E", "Ё": "Yo",
    "Ж": "Zh", "З": "Z", "И": "I", "Й": "Y", "К": "K", "Л": "L", "М": "M",
    "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U",
    "Ф": "F", "Х": "Kh", "Ц": "Ts", "Ч": "Ch", "Ш": "Sh", "Щ": "Shch",
    "Ъ": "", "Ы": "Y", "Ь": "", "Э": "E", "Ю": "Yu", "Я": "Ya",
}


def _transliterate(text: str) -> str:
    return "".join(CYRILLIC_TO_LATIN.get(c, c) for c in text)


def _load_history() -> list[dict]:
    if not HISTORY_FILE.is_file():
        return []
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_history(records: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = HISTORY_FILE.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(records[-30:], ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(HISTORY_FILE)


def scan(folder: str, filter_pattern: str = "*", recursive: bool = False) -> dict:
    """Сканирует папку и возвращает список файлов для переименования."""
    target_path = fileguard.check_safe_folder(folder)

    pattern = filter_pattern.strip() or "*"
    patterns = [p.strip() for p in pattern.split(",") if p.strip()] or ["*"]

    files = []
    if recursive:
        iterator = target_path.rglob("*")
    else:
        iterator = target_path.iterdir()

    for item in iterator:
        if not item.is_file():
            continue
        if item.name.startswith((".", "~$", "__hub_tmp_")):
            continue

        matched = any(fnmatch.fnmatch(item.name.lower(), p.lower()) for p in patterns)
        if not matched:
            continue

        try:
            stat = item.stat()
            files.append({
                "name": item.name,
                "path": str(item),
                "size": stat.st_size,
                "mtime": int(stat.st_mtime),
                "rel_path": str(item.relative_to(target_path)),
            })
        except OSError:
            continue

    files.sort(key=lambda x: x["name"].lower())
    return {
        "folder": str(target_path),
        "count": len(files),
        "files": files,
    }


def compute_new_name(old_name: str, index: int, mtime: int, rule: dict) -> str:
    """Вычисляет новое имя файла на основе правила."""
    stem, ext = os.path.splitext(old_name)
    mode = rule.get("mode", "replace")
    include_ext = bool(rule.get("include_ext", False))
    base = old_name if include_ext else stem

    new_base = base

    if mode == "replace":
        find_text = str(rule.get("find", ""))
        replace_text = str(rule.get("replace", ""))
        use_regex = bool(rule.get("use_regex", False))
        case_sensitive = bool(rule.get("case_sensitive", False))

        if find_text:
            if use_regex:
                flags = 0 if case_sensitive else re.IGNORECASE
                try:
                    new_base = re.sub(find_text, replace_text, base, flags=flags)
                except re.error as e:
                    raise ValueError(f"Ошибка в регулярном выражении: {e}") from e
            else:
                if case_sensitive:
                    new_base = base.replace(find_text, replace_text)
                else:
                    pattern = re.compile(re.escape(find_text), re.IGNORECASE)
                    new_base = pattern.sub(replace_text, base)

    elif mode == "number":
        prefix = str(rule.get("prefix", ""))
        suffix = str(rule.get("suffix", ""))
        start = int(rule.get("start", 1))
        step = int(rule.get("step", 1))
        digits = max(1, min(10, int(rule.get("digits", 2))))
        keep_name = bool(rule.get("keep_name", False))

        num = start + index * step
        num_str = f"{num:0{digits}d}"
        if keep_name:
            new_base = f"{prefix}{base}_{num_str}{suffix}"
        else:
            new_base = f"{prefix}{num_str}{suffix}"

    elif mode == "affix":
        prefix = str(rule.get("prefix", ""))
        suffix = str(rule.get("suffix", ""))
        new_base = f"{prefix}{base}{suffix}"

    elif mode == "case":
        target = rule.get("target", "lower")
        if target == "lower":
            new_base = base.lower()
        elif target == "upper":
            new_base = base.upper()
        elif target == "title":
            new_base = base.title()
        elif target == "sentence":
            new_base = base.capitalize()

    elif mode == "translit":
        new_base = _transliterate(base)

    elif mode == "date":
        fmt = rule.get("format", "YYYY-MM-DD")
        pos = rule.get("position", "prefix")
        dt = datetime.fromtimestamp(mtime)
        if fmt == "YYYY-MM-DD_HH-mm":
            date_str = dt.strftime("%Y-%m-%d_%H-%M")
        else:
            date_str = dt.strftime("%Y-%m-%d")

        if pos == "prefix":
            new_base = f"{date_str}_{base}"
        else:
            new_base = f"{base}_{date_str}"

    if include_ext:
        return new_base.strip()
    return f"{new_base.strip()}{ext}"


def preview(folder: str, files: list[dict], rule: dict) -> dict:
    """Формирует предпросмотр переименования и находит конфликты имён."""
    target_path = fileguard.check_safe_folder(folder)

    results = []
    used_new_names: dict[str, int] = {}

    for idx, item in enumerate(files):
        old_name = item.get("name", "")
        old_path = Path(item.get("path", target_path / old_name))
        mtime = item.get("mtime", int(time.time()))

        try:
            new_name = compute_new_name(old_name, idx, mtime, rule)
        except Exception as e:
            results.append({
                "old_name": old_name,
                "new_name": old_name,
                "old_path": str(old_path),
                "new_path": str(old_path),
                "status": "error",
                "error": str(e),
            })
            continue

        parent = old_path.parent
        new_path = parent / new_name

        key = str(new_path).lower()
        used_new_names[key] = used_new_names.get(key, 0) + 1

        results.append({
            "old_name": old_name,
            "new_name": new_name,
            "old_path": str(old_path),
            "new_path": str(new_path),
            "status": "ok",
            "error": None,
        })

    # Проверка на коллизии и неизменность
    for item in results:
        if item["status"] == "error":
            continue

        if item["old_name"] == item["new_name"]:
            item["status"] = "unchanged"
            continue

        key = str(Path(item["new_path"])).lower()
        if used_new_names.get(key, 0) > 1:
            item["status"] = "conflict"
            item["error"] = "Несколько файлов получают одинаковое имя"
            continue

        new_p = Path(item["new_path"])
        if new_p.exists() and str(new_p).lower() != str(Path(item["old_path"])).lower():
            # Если файл с таким именем уже существует на диске и это не исходный файл
            item["status"] = "conflict"
            item["error"] = f"Файл с именем «{item['new_name']}» уже существует на диске"

    ready_count = sum(1 for r in results if r["status"] == "ok")
    conflict_count = sum(1 for r in results if r["status"] == "conflict")
    unchanged_count = sum(1 for r in results if r["status"] == "unchanged")

    return {
        "folder": str(target_path),
        "total": len(results),
        "ready_count": ready_count,
        "conflict_count": conflict_count,
        "unchanged_count": unchanged_count,
        "preview": results,
    }


def apply(folder: str, renames: list[dict]) -> dict:
    """Применяет пакетное переименование файлов с защитой от циклов и записью в историю."""
    target_path = fileguard.check_safe_folder(folder)

    valid_renames = [
        r for r in renames
        if r.get("status") == "ok" and r.get("old_path") != r.get("new_path")
    ]
    if not valid_renames:
        return {"run_id": None, "renamed_count": 0, "errors": ["Нет файлов, готовых к переименованию"]}

    run_id = f"ren_{uuid.uuid4().hex[:8]}"
    applied = []
    errors = []

    # Фаза 1: Переименование через временные уникальные имена при взаимных заменах
    temp_moves = []
    for item in valid_renames:
        old_p = Path(item["old_path"])
        new_p = Path(item["new_path"])
        if not old_p.exists():
            errors.append(f"Исходный файл не найден: {old_p.name}")
            continue

        # Временное имя в той же папке
        tmp_name = f"__hub_tmp_{uuid.uuid4().hex[:8]}_{old_p.name}"
        tmp_p = old_p.parent / tmp_name
        try:
            old_p.rename(tmp_p)
            temp_moves.append((tmp_p, new_p, old_p))
        except OSError as e:
            errors.append(f"Не удалось подготовить {old_p.name}: {e}")

    # Фаза 2: Финальное переименование из временных в новые имена
    for tmp_p, final_p, orig_p in temp_moves:
        try:
            tmp_p.rename(final_p)
            applied.append({
                "old_path": str(orig_p),
                "new_path": str(final_p),
                "old_name": orig_p.name,
                "new_name": final_p.name,
            })
        except OSError as e:
            # Попытка вернуть назад
            try:
                tmp_p.rename(orig_p)
            except OSError:
                pass
            errors.append(f"Не удалось переименовать в {final_p.name}: {e}")

    if applied:
        record = {
            "run_id": run_id,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "folder": str(target_path),
            "count": len(applied),
            "renames": applied,
        }
        history = _load_history()
        history.append(record)
        _save_history(history)

    return {
        "run_id": run_id if applied else None,
        "renamed_count": len(applied),
        "errors": errors,
    }


def undo(run_id: str | None = None) -> dict:
    """Отменяет операцию переименования, возвращая исходные имена файлов."""
    history = _load_history()
    if not history:
        raise ValueError("История переименований пуста")

    target_record = None
    if run_id:
        for rec in reversed(history):
            if rec.get("run_id") == run_id:
                target_record = rec
                break
        if not target_record:
            raise ValueError(f"Операция с ID «{run_id}» не найдена в истории")
    else:
        target_record = history[-1]

    restored = 0
    errors = []
    # Откатываем в обратном порядке
    for item in reversed(target_record.get("renames", [])):
        curr_p = Path(item["new_path"])
        orig_p = Path(item["old_path"])
        if not curr_p.exists():
            errors.append(f"Файл {curr_p.name} не найден для отмены")
            continue
        try:
            curr_p.rename(orig_p)
            restored += 1
        except OSError as e:
            errors.append(f"Ошибка восстановления {curr_p.name}: {e}")

    # Удаляем запись из истории
    history = [r for r in history if r.get("run_id") != target_record.get("run_id")]
    _save_history(history)

    return {
        "run_id": target_record.get("run_id"),
        "restored_count": restored,
        "errors": errors,
    }


def last_run() -> dict | None:
    """Возвращает информацию о последней операции переименования."""
    history = _load_history()
    return history[-1] if history else None
