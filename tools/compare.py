"""Сравнение папок: что появилось, что пропало, что изменилось.

Только чтение — этот модуль ничего не удаляет и не переименовывает.
Обычный режим сравнивает размеры, глубокий дополнительно читает файлы и
сравнивает содержимое по BLAKE2b, чтобы поймать правки того же размера.
"""

from __future__ import annotations

import hashlib
import os
import stat
import time
from pathlib import Path

from tools import fileguard

MAX_ENTRIES = 200_000
MAX_LISTED = 500
MAX_HASH_BYTES = 2 * 1024 * 1024 * 1024
CHUNK = 1024 * 1024


class CompareError(RuntimeError):
    """Папки не удалось сравнить."""


def _collect(root: Path) -> tuple[dict[str, dict], list[dict], int]:
    """Все файлы и папки внутри root: путь относительно root."""
    entries: dict[str, dict] = {}
    errors: list[dict] = []
    count = 0
    for current, dirs, names in os.walk(root, followlinks=False):
        relative = Path(current).relative_to(root)
        kept = []
        for name in dirs:
            child = os.path.join(current, name)
            try:
                info = os.lstat(child)
            except OSError:
                continue
            if stat.S_ISLNK(info.st_mode):
                errors.append({"path": str(Path(relative) / name), "reason": "ссылка, пропущена"})
                continue
            kept.append(name)
            key = str(Path(relative) / name)
            entries[key] = {"kind": "dir", "size": 0, "mtime": info.st_mtime}
        dirs[:] = kept

        for name in names:
            count += 1
            if count > MAX_ENTRIES:
                return entries, errors, count
            child = os.path.join(current, name)
            try:
                info = os.lstat(child)
            except OSError:
                continue
            if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
                continue
            key = str(Path(relative) / name)
            entries[key] = {"kind": "file", "size": info.st_size, "mtime": info.st_mtime, "abs": child}
    return entries, errors, count


def _digest(path: str) -> str | None:
    total = 0
    hasher = hashlib.blake2b()
    try:
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_HASH_BYTES:
                    return None
                hasher.update(chunk)
    except OSError:
        return None
    return hasher.hexdigest()


def _folder(raw: str, side: str) -> Path:
    if not raw or not raw.strip():
        raise CompareError(f"Укажи {side} папку")
    try:
        return fileguard.check_safe_folder(raw)
    except fileguard.GuardError as exc:
        raise CompareError(str(exc)) from exc


def compare(left: str, right: str, deep: bool = False) -> dict:
    left_root = _folder(left, "первую")
    right_root = _folder(right, "вторую")
    if os.path.normcase(str(left_root)) == os.path.normcase(str(right_root)):
        raise CompareError("Это одна и та же папка — выбери две разные")

    started = time.perf_counter()
    left_entries, left_errors, left_count = _collect(left_root)
    right_entries, right_errors, right_count = _collect(right_root)

    added: list[dict] = []
    removed: list[dict] = []
    changed: list[dict] = []
    same = 0
    same_size = 0

    for key in sorted(set(left_entries) | set(right_entries)):
        one = left_entries.get(key)
        two = right_entries.get(key)
        if one is None:
            added.append({"path": key, "kind": two["kind"], "size": two["size"]})
            continue
        if two is None:
            removed.append({"path": key, "kind": one["kind"], "size": one["size"]})
            continue
        if one["kind"] != two["kind"]:
            changed.append({"path": key, "reason": "type"})
            continue
        if one["kind"] == "dir":
            same += 1
            continue
        if one["size"] != two["size"]:
            changed.append(
                {"path": key, "reason": "size", "left_size": one["size"], "right_size": two["size"]}
            )
            continue
        if deep:
            one_hash = _digest(one["abs"])
            two_hash = _digest(two["abs"])
            if one_hash and two_hash and one_hash != two_hash:
                changed.append(
                    {"path": key, "reason": "content", "left_size": one["size"], "right_size": two["size"]}
                )
                continue
            if one_hash is None or two_hash is None:
                changed.append({"path": key, "reason": "unreadable"})
                continue
        same += 1
        same_size += one["size"]

    added.sort(key=lambda item: (item["kind"] != "dir", item["path"].lower()))
    removed.sort(key=lambda item: (item["kind"] != "dir", item["path"].lower()))
    changed.sort(key=lambda item: item["path"].lower())

    return {
        "left": str(left_root),
        "right": str(right_root),
        "deep": bool(deep),
        "added": added[:MAX_LISTED],
        "removed": removed[:MAX_LISTED],
        "changed": changed[:MAX_LISTED],
        "counts": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "same": same,
        },
        "added_size": sum(item["size"] for item in added if item["kind"] == "file"),
        "removed_size": sum(item["size"] for item in removed if item["kind"] == "file"),
        "same_size": same_size,
        "files": {"left": left_count, "right": right_count},
        "errors": (left_errors + right_errors)[:25],
        "truncated": left_count > MAX_ENTRIES or right_count > MAX_ENTRIES,
        "seconds": round(time.perf_counter() - started, 2),
    }
