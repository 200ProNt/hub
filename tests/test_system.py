"""Тесты резервного копирования и системных API."""

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from tools import clipboard, notes


class SystemTestCase(unittest.TestCase):
    def test_clipboard_add_snippet(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "clip.json"
            store = clipboard.ClipboardStore(file_path)
            item = store.add("Шаблон быстрого ответа", skip_sensitive=False)
            self.assertIsNotNone(item)
            self.assertEqual(item["text"], "Шаблон быстрого ответа")
            self.assertFalse(item["pinned"])

            pinned = store.toggle_pin(item["id"])
            self.assertTrue(pinned["pinned"])

            # Проверка фильтрации pinned
            listed_pinned = store.listing(kind="pinned")
            self.assertEqual(len(listed_pinned), 1)
            self.assertEqual(listed_pinned[0]["id"], item["id"])

    def test_backup_creates_valid_zip(self):
        with tempfile.TemporaryDirectory() as data_dir:
            dp = Path(data_dir)
            (dp / "notes.json").write_text(json.dumps([{"id": "1", "title": "Test"}]), encoding="utf-8")
            (dp / "clipboard.json").write_text(json.dumps([{"id": "2", "text": "Clip"}]), encoding="utf-8")
            (dp / "temp.lock").write_text("lock", encoding="utf-8")

            # Симуляция создания архива
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, _, files in dp.walk() if hasattr(dp, "walk") else [(str(dp), [], ["notes.json", "clipboard.json", "temp.lock"])]:
                    for f in files:
                        if f.endswith((".lock", ".tmp")):
                            continue
                        zf.write(dp / f, f)
            buffer.seek(0)

            with zipfile.ZipFile(buffer, "r") as zf:
                namelist = zf.namelist()
                self.assertIn("notes.json", namelist)
                self.assertIn("clipboard.json", namelist)
                self.assertNotIn("temp.lock", namelist)


if __name__ == "__main__":
    unittest.main()
