"""История буфера обмена: хранение, поиск и работа с системным буфером Windows."""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path

LIMIT = 500
MAX_TEXT_LENGTH = 20_000
POLL_INTERVAL = 0.4
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

# --- Системный буфер (только Windows) --------------------------------------


class ClipboardUnavailable(RuntimeError):
    """Буфер обмена недоступен на этой системе."""


def _win_api():
    if not hasattr(_win_api, "_cache"):
        try:
            import ctypes
            from ctypes import wintypes
        except ImportError as exc:  # pragma: no cover
            raise ClipboardUnavailable("Нет ctypes") from exc

        if not hasattr(ctypes, "WinDLL"):
            raise ClipboardUnavailable("Системный буфер поддерживается только на Windows")

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.CloseClipboard.restype = wintypes.BOOL
        user32.EmptyClipboard.restype = wintypes.BOOL
        user32.GetClipboardData.argtypes = [wintypes.UINT]
        user32.GetClipboardData.restype = wintypes.HANDLE
        user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        user32.SetClipboardData.restype = wintypes.HANDLE

        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.restype = wintypes.BOOL

        _win_api._cache = (ctypes, user32, kernel32)
    return _win_api._cache


def clipboard_sequence() -> int:
    _, user32, _ = _win_api()
    return int(user32.GetClipboardSequenceNumber())


def read_text() -> str | None:
    """Текст из буфера или None, если там не текст."""
    ctypes, user32, kernel32 = _win_api()
    if not user32.OpenClipboard(None):
        return None
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return None
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def write_text(text: str) -> None:
    ctypes, user32, kernel32 = _win_api()
    payload = text.encode("utf-16-le") + b"\x00\x00"
    if not user32.OpenClipboard(None):
        raise ClipboardUnavailable("Не удалось открыть буфер обмена")
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(payload))
        if not handle:
            raise ClipboardUnavailable("Не хватило памяти для записи в буфер")
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            raise ClipboardUnavailable("Не удалось заблокировать память буфера")
        try:
            ctypes.memmove(pointer, payload, len(payload))
        finally:
            kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            raise ClipboardUnavailable("Не удалось записать текст в буфер")
    finally:
        user32.CloseClipboard()


# --- Хранилище -------------------------------------------------------------


class ClipboardStore:
    def __init__(self, path: Path, limit: int = LIMIT) -> None:
        self.path = path
        self.limit = limit
        self._lock = threading.Lock()
        self._items: list[dict] = []
        self._load()

    # - файл -

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._items = []
            return
        items = raw.get("items") if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            self._items = []
            return
        cleaned = []
        for item in items:
            if not isinstance(item, dict) or not item.get("text"):
                continue
            cleaned.append(
                {
                    "id": str(item.get("id") or uuid.uuid4().hex[:12]),
                    "text": str(item["text"]),
                    "time": float(item.get("time") or time.time()),
                    "pinned": bool(item.get("pinned")),
                }
            )
        self._items = cleaned

    def _save(self) -> None:
        payload = json.dumps({"items": self._items}, ensure_ascii=False)
        temporary = self.path.with_suffix(".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(payload, encoding="utf-8")
            temporary.replace(self.path)
        except OSError:
            pass

    # - данные -

    @staticmethod
    def _public(item: dict) -> dict:
        text = item["text"]
        lines = [" ".join(line.split()) for line in text.splitlines()]
        preview = "\n".join(line for line in lines if line)[:280]
        return {
            "id": item["id"],
            "text": text,
            "preview": preview,
            "time": item["time"],
            "pinned": item["pinned"],
            "chars": len(text),
            "lines": text.count("\n") + 1,
        }

    def listing(self, query: str = "", limit: int = 150) -> list[dict]:
        with self._lock:
            items = list(self._items)
        if query:
            needle = query.strip().lower()
            items = [item for item in items if needle in item["text"].lower()]
        items.sort(key=lambda item: (0 if item["pinned"] else 1, -item["time"]))
        return [self._public(item) for item in items[:limit]]

    def count(self) -> int:
        with self._lock:
            return len(self._items)

    def get(self, item_id: str) -> dict | None:
        with self._lock:
            for item in self._items:
                if item["id"] == item_id:
                    return dict(item)
        return None

    # - изменения -

    def add(self, text: str) -> dict | None:
        text = (text or "").replace("\x00", "")
        if not text.strip() or len(text) > MAX_TEXT_LENGTH:
            return None
        with self._lock:
            for index, item in enumerate(self._items):
                if item["text"] == text:
                    if index > 0:
                        self._items.insert(0, self._items.pop(index))
                    self._items[0]["time"] = time.time()
                    self._save()
                    return dict(self._items[0])
            entry = {
                "id": uuid.uuid4().hex[:12],
                "text": text,
                "time": time.time(),
                "pinned": False,
            }
            self._items.insert(0, entry)
            self._trim()
            self._save()
            return dict(entry)

    def _trim(self) -> None:
        while len(self._items) > self.limit:
            for index in range(len(self._items) - 1, -1, -1):
                if not self._items[index]["pinned"]:
                    del self._items[index]
                    break
            else:
                break

    def toggle_pin(self, item_id: str) -> dict | None:
        with self._lock:
            for item in self._items:
                if item["id"] == item_id:
                    item["pinned"] = not item["pinned"]
                    self._save()
                    return dict(item)
        return None

    def delete(self, item_id: str) -> bool:
        with self._lock:
            for index, item in enumerate(self._items):
                if item["id"] == item_id:
                    del self._items[index]
                    self._save()
                    return True
        return False

    def clear(self) -> int:
        with self._lock:
            removed = len(self._items)
            self._items = []
            self._save()
            return removed


# --- Наблюдатель -----------------------------------------------------------


class ClipboardWatcher(threading.Thread):
    """Опрашивает номер буфера и складывает новый текст в историю."""

    def __init__(self, store: ClipboardStore) -> None:
        super().__init__(daemon=True, name="clipboard-watcher")
        self.store = store
        self.paused = threading.Event()
        self.last_error: str | None = None
        self._stop_event = threading.Event()

    def pause(self) -> None:
        self.paused.set()

    def resume(self) -> None:
        self.paused.clear()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        last_sequence = -1
        while not self._stop_event.is_set():
            try:
                if self.paused.is_set():
                    # Пока на паузе просто запоминаем номер, чтобы не схватить
                    # скопированное в этот момент после снятия паузы.
                    last_sequence = clipboard_sequence()
                else:
                    sequence = clipboard_sequence()
                    if sequence != last_sequence:
                        last_sequence = sequence
                        text = read_text()
                        if text:
                            self.store.add(text)
                self.last_error = None
            except ClipboardUnavailable as exc:
                self.last_error = str(exc)
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"Буфер недоступен: {exc}"
            self._stop_event.wait(POLL_INTERVAL)
