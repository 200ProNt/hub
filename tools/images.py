"""Сжатие и конвертация изображений: сохранение на диск и базовая проверка форматов.

Обработка и сжатие (PNG, JPEG, WebP) происходят в браузере через HTML5 Canvas
(высококачественное бикубическое масштабирование и нативное сжатие браузера),
а сервер отвечает за безопасное сохранение файлов в указанную папку на компьютере.
"""

from __future__ import annotations

import base64
import os
import re
from pathlib import Path

from tools import fileguard

MAX_IMAGE_BYTES = 50 * 1024 * 1024  # 50 МБ
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


class ImageError(RuntimeError):
    """Ошибка обработки или сохранения изображения."""


def sanitize_filename(name: str) -> str:
    """Очищает имя файла от опасных символов и разделителей путей."""
    base = os.path.basename(str(name).replace("\\", "/").strip())
    # Заменяем запрещенные символы Windows на дефис
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", base)
    cleaned = re.sub(r"-+", "-", cleaned).strip(" .")
    if not cleaned:
        cleaned = "image"
    ext = Path(cleaned).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        cleaned += ".webp"
    return cleaned


def save_image(target_dir: str, filename: str, data_base64: str) -> dict:
    """Сохраняет сжатое изображение в выбранную папку."""
    if not target_dir or not target_dir.strip():
        raise ImageError("Укажи папку для сохранения")

    try:
        dest_folder = fileguard.check_safe_folder(target_dir)
    except fileguard.GuardError as exc:
        raise ImageError(str(exc)) from exc

    safe_name = sanitize_filename(filename)
    dest_path = dest_folder / safe_name

    # Предотвращаем перезапись существующего файла — подбираем уникальное имя
    stem = dest_path.stem
    ext = dest_path.suffix
    counter = 1
    while dest_path.exists():
        dest_path = dest_folder / f"{stem}_{counter}{ext}"
        counter += 1

    # Извлекаем чистые base64 данные
    raw = data_base64.strip()
    if "," in raw:
        _, raw = raw.split(",", 1)

    try:
        data = base64.b64decode(raw)
    except Exception as exc:
        raise ImageError("Некорректные base64 данные изображения") from exc

    if len(data) > MAX_IMAGE_BYTES:
        raise ImageError(f"Файл превышает лимит в {MAX_IMAGE_BYTES // (1024 * 1024)} МБ")

    if not data:
        raise ImageError("Пустые данные изображения")

    try:
        dest_path.write_bytes(data)
    except OSError as exc:
        raise ImageError(f"Не удалось записать файл: {exc}") from exc

    return {
        "ok": True,
        "filename": dest_path.name,
        "path": str(dest_path),
        "size": len(data),
    }
