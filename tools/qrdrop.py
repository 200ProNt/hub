"""Инструмент «Обмен с телефоном (QR-Drop)»: передача текста, заметок и файлов по Wi-Fi."""

from __future__ import annotations

import json
import re
import socket
from datetime import datetime
from pathlib import Path

from tools import paths

from tools import fileguard

DATA_DIR = paths.DATA_DIR
INCOMING_DIR = DATA_DIR / "incoming"
SHARED_DIR = DATA_DIR / "shared"
INCOMING_TEXTS_FILE = DATA_DIR / "incoming_texts.json"

MAX_FILE_BYTES = 100 * 1024 * 1024  # 100 MB per transfer


def get_local_ip() -> str:
    """Определяет локальный IP-адрес компьютера в сети Wi-Fi/LAN."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        # 8.8.8.8 не опрашивается по сети, соединение сокета позволяет ОС выбрать интерфейс
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_drop_url(port: int = 8770) -> str:
    """Возвращает мобильный URL для подключения с телефона."""
    return f"http://{get_local_ip()}:{port}/drop"


def qr_png(url: str) -> bytes:
    """Скругляет модули, сохраняя квадратные ориентиры и белое поле QR."""
    from io import BytesIO

    import qrcode
    from PIL import Image, ImageDraw
    from qrcode.image.styledpil import StyledPilImage
    from qrcode.image.styles.moduledrawers.pil import RoundedModuleDrawer, SquareModuleDrawer

    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=8, border=4)
    code.add_data(url)
    picture = code.make_image(image_factory=StyledPilImage, module_drawer=RoundedModuleDrawer(radius_ratio=.78),
                              eye_drawer=SquareModuleDrawer()).get_image().convert("RGBA")
    width, height = picture.size
    radius = min(24, width // 11)
    mask = Image.new("L", picture.size)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=255)
    picture.putalpha(mask)
    with BytesIO() as data:
        picture.save(data, format="PNG")
        return data.getvalue()


def _sanitize_filename(name: str) -> str:
    """Очищает имя файла от опасных символов и попыток обхода директорий."""
    basename = Path(name).name
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", basename).strip(". ")
    return cleaned or "file_download"


def _load_incoming_texts() -> list[dict]:
    if not INCOMING_TEXTS_FILE.is_file():
        return []
    try:
        return json.loads(INCOMING_TEXTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_incoming_texts(records: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = INCOMING_TEXTS_FILE.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(records[-50:], ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(INCOMING_TEXTS_FILE)


def save_incoming_text(text: str, source: str = "phone") -> dict:
    """Сохраняет текст, отправленный со смартфона, и добавляет его в буфер обмена Hub."""
    clean_text = str(text or "").strip()
    if not clean_text:
        raise ValueError("Текст не может быть пустым")

    record = {
        "text": clean_text,
        "source": source,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": int(datetime.now().timestamp()),
    }
    texts = _load_incoming_texts()
    texts.append(record)
    _save_incoming_texts(texts)

    # Добавляем в буфер обмена Hub, если доступен
    try:
        from tools import clipboard
        store = clipboard.store()
        store.add(clean_text, skip_sensitive=False)
    except Exception:
        pass

    return record


def list_incoming_texts(limit: int = 20) -> list[dict]:
    """Возвращает список последних принятых сообщений."""
    texts = _load_incoming_texts()
    return list(reversed(texts))[:limit]


def save_incoming_file(raw_name: str, data: bytes) -> dict:
    """Сохраняет файл, переданный со смартфона, в папку data/incoming."""
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("Файл слишком большой (максимум 100 МБ)")

    INCOMING_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = _sanitize_filename(raw_name)

    target_path = INCOMING_DIR / safe_name
    stem = target_path.stem
    ext = target_path.suffix
    counter = 1
    while target_path.exists():
        target_path = INCOMING_DIR / f"{stem} ({counter}){ext}"
        counter += 1

    target_path.write_bytes(data)
    stat = target_path.stat()

    return {
        "name": target_path.name,
        "path": str(target_path),
        "size": stat.st_size,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def list_incoming_files() -> list[dict]:
    """Возвращает список принятых файлов."""
    INCOMING_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for f in INCOMING_DIR.iterdir():
        if f.is_file() and not f.name.startswith("."):
            try:
                stat = f.stat()
                files.append({
                    "name": f.name,
                    "path": str(f),
                    "size": stat.st_size,
                    "mtime": int(stat.st_mtime),
                    "url": f"/api/drop/download?name={f.name}&type=incoming",
                })
            except OSError:
                continue
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return files


def list_shared_files() -> list[dict]:
    """Возвращает список файлов, доступных для скачивания на смартфон."""
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for f in SHARED_DIR.iterdir():
        if f.is_file() and not f.name.startswith("."):
            try:
                stat = f.stat()
                files.append({
                    "name": f.name,
                    "path": str(f),
                    "size": stat.st_size,
                    "mtime": int(stat.st_mtime),
                    "url": f"/api/drop/download?name={f.name}&type=shared",
                })
            except OSError:
                continue
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return files


def share_file(file_path: str) -> dict:
    """Добавляет файл с ПК в список файлов для скачивания на телефон."""
    src = Path(file_path).resolve()
    if not src.is_file():
        raise FileNotFoundError(f"Файл не найден: {file_path}")

    fileguard.check_safe_folder(src.parent)
    SHARED_DIR.mkdir(parents=True, exist_ok=True)

    dest = SHARED_DIR / _sanitize_filename(src.name)
    # Копируем файл в shared
    import shutil
    shutil.copy2(src, dest)
    stat = dest.stat()

    return {
        "name": dest.name,
        "path": str(dest),
        "size": stat.st_size,
        "url": f"/api/drop/download?name={dest.name}&type=shared",
    }


def unshare_file(name: str) -> bool:
    """Убирает файл из раздачи."""
    safe_name = _sanitize_filename(name)
    target = SHARED_DIR / safe_name
    if target.is_file():
        target.unlink(missing_ok=True)
        return True
    return False


def get_info(port: int = 8770) -> dict:
    """Сводка данных для экрана обмена с телефоном."""
    ip = get_local_ip()
    return {
        "ip": ip,
        "port": port,
        "url": get_drop_url(port),
        "shared_files": list_shared_files(),
        "incoming_files": list_incoming_files(),
        "incoming_texts": list_incoming_texts(),
    }
