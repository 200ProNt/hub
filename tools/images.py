"""Сжатие и конвертация изображений: сохранение на диск и базовая проверка форматов.

Обработка и сжатие (PNG, JPEG, WebP) происходят в браузере через HTML5 Canvas
(высококачественное бикубическое масштабирование и нативное сжатие браузера),
а сервер отвечает за безопасное сохранение файлов в указанную папку на компьютере.
"""

from __future__ import annotations

import base64
import os
import re
import tempfile
from io import BytesIO
from pathlib import Path

from tools import fileguard

MAX_IMAGE_BYTES = 50 * 1024 * 1024  # 50 МБ
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
INPUT_FORMATS = ("PNG", "JPEG", "WEBP", "GIF", "BMP")


class ImageError(RuntimeError):
    """Ошибка обработки или сохранения изображения."""


def process_image(name, source, format_name, ext, quality, max_dimension):
    from PIL import Image, ImageOps

    if isinstance(source, Path):
        original_size, input_data = source.stat().st_size, source
    elif isinstance(source, bytes):
        original_size, input_data = len(source), BytesIO(source)
    else:
        original_size, input_data = os.fstat(source.fileno()).st_size, source
    with Image.open(input_data, formats=INPUT_FORMATS) as opened:
        with ImageOps.exif_transpose(opened) as oriented:
            original_dimensions = oriented.size
            with oriented.convert("RGBA") as converted:
                if max_dimension:
                    converted.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
                with BytesIO() as output:
                    if format_name == "JPEG":
                        with Image.new("RGB", converted.size) as opaque:
                            opaque.paste(converted, mask=converted.getchannel("A"))
                            opaque.save(output, format_name, quality=quality, optimize=True)
                    else:
                        options = {"quality": quality} if format_name == "WEBP" else {"optimize": True}
                        converted.save(output, format_name, **options)
                    encoded = output.getvalue()
                dimensions = converted.size

    with Image.open(BytesIO(encoded)) as result:
        result.thumbnail((320, 220), Image.Resampling.LANCZOS)
        with BytesIO() as preview:
            result.save(preview, "PNG")
            thumbnail = preview.getvalue()
    return {
        "name": f"{Path(name).stem}.{ext}", "original_size": original_size, "original_dimensions": original_dimensions,
        "dimensions": dimensions, "data": encoded, "thumbnail": thumbnail,
    }


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

    temporary = None
    try:
        staged = tempfile.NamedTemporaryFile(dir=dest_folder, prefix=".hub-image-", suffix=".tmp", delete=False)
        temporary = Path(staged.name)
        with staged:
            staged.write(data)
            staged.flush()
            os.fsync(staged.fileno())
        fileguard.parents(dest_folder)
        if os.name == "nt":
            temporary.rename(dest_path)
        else:
            os.link(temporary, dest_path)
    except (OSError, fileguard.GuardError) as exc:
        raise ImageError(f"Не удалось записать файл: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

    return {
        "ok": True,
        "filename": dest_path.name,
        "path": str(dest_path),
        "size": len(data),
    }
