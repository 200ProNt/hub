"""Заметки: короткие записи, которые живут в data/notes.json.

Файл читается и пишется атомарно: если запись не удалась, старая версия остаётся
целой. Ничего никуда не отправляется — заметки только на этом компьютере.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path

MAX_TITLE = 120
MAX_TEXT = 40_000
MAX_NOTES = 2_000


class NoteError(RuntimeError):
    """Заметку не удалось сохранить или найти."""


def path() -> Path:
    override = os.environ.get("HUB_NOTES_FILE")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "data" / "notes.json"


class NotesStore:
    def __init__(self, file: Path | None = None) -> None:
        self.file = file or path()
        self._lock = threading.Lock()
        self._notes: list[dict] = []
        self._load()

    # - файл -

    def _load(self) -> None:
        raw = None
        backup_file = self.file.with_name(f"{self.file.name}.bak")

        if self.file.exists():
            try:
                raw = json.loads(self.file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                # Файл повреждён (например, при резком выключении питания)
                try:
                    if self.file.stat().st_size > 0:
                        ts = int(time.time())
                        corrupted_copy = self.file.with_name(f"{self.file.stem}.corrupted.{ts}.json")
                        shutil.copy2(self.file, corrupted_copy)
                except OSError:
                    pass

                # Пробуем восстановиться из автоматической резервной копии .bak
                if backup_file.exists():
                    try:
                        raw = json.loads(backup_file.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        raw = None

        elif backup_file.exists():
            try:
                raw = json.loads(backup_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raw = None

        if raw is None:
            self._notes = []
            return

        items = raw.get("notes") if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            self._notes = []
            return
        cleaned = []
        for item in items:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "")
            title = str(item.get("title") or "")
            if not text and not title:
                continue
            created = float(item.get("created") or time.time())
            cleaned.append(
                {
                    "id": str(item.get("id") or uuid.uuid4().hex[:12]),
                    "title": title[:MAX_TITLE],
                    "text": text[:MAX_TEXT],
                    "pinned": bool(item.get("pinned")),
                    "created": created,
                    "updated": float(item.get("updated") or created),
                }
            )
        self._notes = cleaned

    def _save(self) -> None:
        payload = json.dumps({"notes": self._notes}, ensure_ascii=False)
        temporary = self.file.with_suffix(".tmp")
        backup_file = self.file.with_name(f"{self.file.name}.bak")
        try:
            self.file.parent.mkdir(parents=True, exist_ok=True)
            # Запись с принудительным fsync для защиты от сбоев питания
            with temporary.open("w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())

            # Создаём актуальный .bak перед заменой
            if self.file.exists():
                try:
                    shutil.copy2(self.file, backup_file)
                except OSError:
                    pass

            temporary.replace(self.file)
        except OSError as exc:
            raise NoteError(f"Не получилось сохранить заметки: {exc}") from exc

    # - данные -

    @staticmethod
    def _public(note: dict) -> dict:
        return {
            "id": note["id"],
            "title": note["title"],
            "text": note["text"],
            "pinned": note["pinned"],
            "created": note["created"],
            "updated": note["updated"],
            "chars": len(note["text"]),
        }

    def listing(self, query: str = "") -> list[dict]:
        with self._lock:
            notes = [dict(note) for note in self._notes]
        if query and query.strip():
            needle = query.strip().lower()
            notes = [
                note
                for note in notes
                if needle in note["title"].lower() or needle in note["text"].lower()
            ]
        notes.sort(key=lambda note: (0 if note["pinned"] else 1, -note["updated"]))
        return [self._public(note) for note in notes]

    def count(self) -> int:
        with self._lock:
            return len(self._notes)

    def get(self, note_id: str) -> dict | None:
        with self._lock:
            for note in self._notes:
                if note["id"] == note_id:
                    return self._public(note)
        return None

    # - изменения -

    @staticmethod
    def _clean(title: str, text: str) -> tuple[str, str]:
        title = (title or "").replace("\x00", "").strip()[:MAX_TITLE]
        text = (text or "").replace("\x00", "")[:MAX_TEXT]
        if not title and not text.strip():
            raise NoteError("Заметка пустая — напиши хотя бы строку")
        return title, text

    def create(self, title: str = "", text: str = "") -> dict:
        title, text = self._clean(title, text)
        with self._lock:
            if len(self._notes) >= MAX_NOTES:
                raise NoteError(f"Больше {MAX_NOTES} заметок хранить не получится")
            stamp = time.time()
            note = {
                "id": uuid.uuid4().hex[:12],
                "title": title,
                "text": text,
                "pinned": False,
                "created": stamp,
                "updated": stamp,
            }
            self._notes.insert(0, note)
            self._save()
            return self._public(note)

    def update(self, note_id: str, title: str, text: str) -> dict:
        title, text = self._clean(title, text)
        with self._lock:
            for note in self._notes:
                if note["id"] == note_id:
                    note["title"] = title
                    note["text"] = text
                    note["updated"] = time.time()
                    self._save()
                    return self._public(note)
        raise NoteError("Заметка не найдена — возможно, её уже удалили")

    def toggle_pin(self, note_id: str) -> dict:
        with self._lock:
            for note in self._notes:
                if note["id"] == note_id:
                    note["pinned"] = not note["pinned"]
                    note["updated"] = time.time()
                    self._save()
                    return self._public(note)
        raise NoteError("Заметка не найдена")

    def delete(self, note_id: str) -> bool:
        with self._lock:
            for index, note in enumerate(self._notes):
                if note["id"] == note_id:
                    del self._notes[index]
                    self._save()
                    return True
        return False


_store: NotesStore | None = None


def store() -> NotesStore:
    global _store
    if _store is None:
        _store = NotesStore()
    return _store
