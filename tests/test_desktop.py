import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import clipboard, notes, paths, preferences, trash


class MigrationTest(unittest.TestCase):
    def test_copies_legacy_data_and_rebases_trash(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"HUB_TRASH_DIR": ""}):
            root = Path(tmp)
            old = root / "old"
            old_data = old / "data"
            old_data.mkdir(parents=True)
            (old / "server.py").touch()
            notes.NotesStore(old_data / "notes.json").create("Legacy note", "Text")
            clipboard.ClipboardStore(old_data / "clipboard.json").add("Legacy clipboard")
            (old_data / "sorter_rules.json").write_text("{}", encoding="utf-8")
            restored = root / "document.txt"
            restored.write_text("legacy trash", encoding="utf-8")
            with patch.object(paths, "DATA_DIR", old_data):
                moved = trash.move([str(restored)], source="cleanup")

            target = root / "profile" / "data"
            target.parent.mkdir()
            preferences.migrate(old, target)
            self.assertEqual(notes.NotesStore(target / "notes.json").listing()[0]["title"], "Legacy note")
            self.assertEqual(clipboard.ClipboardStore(target / "clipboard.json").listing()[0]["text"], "Legacy clipboard")
            self.assertTrue((target / "sorter_rules.json").is_file())
            self.assertEqual((old_data / "notes.json").read_bytes(), (target / "notes.json").read_bytes())

            with patch.object(paths, "DATA_DIR", target):
                self.assertEqual(trash.undo(moved["run_id"])["restored_count"], 1)
                self.assertEqual(restored.read_text(encoding="utf-8"), "legacy trash")
                self.assertTrue(Path(moved["moved"][0]["to"]).is_file())
                preferences.update({"hub-theme": "dark", "hub-accent": "ocean", "bad": "unknown"})
                self.assertEqual(json.loads((target / "preferences.json").read_text(encoding="utf-8")),
                                 {"hub-theme": "dark", "hub-accent": "ocean"})

            with self.assertRaises(FileExistsError):
                preferences.migrate(old, target)
