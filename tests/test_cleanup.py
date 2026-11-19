"""Уборка: старые файлы, мусор и пустые папки — только через корзину."""

import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools import cleanup


class CleanupTestCase(unittest.TestCase):
    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)
        self._trash = patch.dict(os.environ, {"HUB_TRASH_DIR": str(self.root / "trash")})
        self._trash.start()
        self.work = self.root / "work"
        self.work.mkdir()
        cleanup._allowed.clear()

    def tearDown(self):
        cleanup._allowed.clear()
        self._trash.stop()
        self._temporary.cleanup()

    def make(self, name: str, data: bytes = b"x", age_days: int = 0) -> Path:
        path = self.work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if age_days:
            stamp = time.time() - age_days * 86_400
            os.utime(path, (stamp, stamp))
        return path

    def test_old_and_junk_are_separated(self):
        old = self.make("photos/report.pdf", b"old", age_days=800)
        self.make("fresh.txt", b"new")
        junk = self.make("cache.tmp", b"temp", age_days=1)
        result = cleanup.scan(str(self.work), age_days=365)
        self.assertEqual([item["path"] for item in result["old"]], [str(old)])
        self.assertEqual([item["path"] for item in result["junk"]], [str(junk)])
        self.assertEqual(result["old_size"], 3)

    def test_recent_files_are_left_alone(self):
        self.make("notes.txt", b"hello")
        result = cleanup.scan(str(self.work), age_days=365)
        self.assertEqual(result["old"], [])
        self.assertEqual(result["junk"], [])

    def test_only_empty_folders_are_offered(self):
        empty = self.work / "empty"
        empty.mkdir()
        filled = self.work / "filled"
        filled.mkdir()
        (filled / "keep.txt").write_bytes(b"1")
        nested = self.work / "outer" / "inner"
        nested.mkdir(parents=True)
        result = cleanup.scan(str(self.work))
        paths = [item["path"] for item in result["empty"]]
        self.assertIn(str(empty), paths)
        self.assertIn(str(nested), paths)
        self.assertNotIn(str(filled), paths)
        self.assertNotIn(str(self.work / "outer"), paths)

    def test_remove_requires_the_last_listing(self):
        old = self.make("gone.txt", b"old", age_days=900)
        result = cleanup.remove([str(old)], "trash")
        self.assertEqual(result["removed_count"], 0)
        self.assertTrue(result["errors"])
        self.assertTrue(old.exists())

    def test_paths_outside_the_listing_are_rejected(self):
        self.make("gone.txt", b"old", age_days=900)
        stranger = self.make("stranger.txt", b"keep")
        cleanup.scan(str(self.work))
        result = cleanup.remove([str(stranger)], "trash")
        self.assertEqual(result["removed_count"], 0)
        self.assertTrue(stranger.exists())

    def test_changed_after_scan_is_rejected(self):
        old = self.make("gone.txt", b"old", age_days=900)
        cleanup.scan(str(self.work))
        old.write_bytes(b"changed and bigger")
        result = cleanup.remove([str(old)], "trash")
        self.assertEqual(result["removed_count"], 0)
        self.assertIn("изменился", result["errors"][0]["reason"])

    def test_trash_and_undo_restore_files_and_folders(self):
        old = self.make("gone.txt", b"old", age_days=900)
        empty = self.work / "empty"
        empty.mkdir()
        cleanup.scan(str(self.work))
        result = cleanup.remove([str(old), str(empty)], "trash")
        self.assertEqual(result["removed_count"], 2)
        self.assertFalse(old.exists())
        self.assertFalse(empty.exists())
        self.assertIsNotNone(cleanup.last_run())

        restored = cleanup.undo(result["run_id"])
        self.assertEqual(restored["restored_count"], 2)
        self.assertTrue(old.exists())
        self.assertTrue(empty.is_dir())
        self.assertIsNone(cleanup.last_run())

    def test_permanent_delete_needs_confirmation_and_clears_empty_folder(self):
        empty = self.work / "empty"
        empty.mkdir()
        cleanup.scan(str(self.work))
        with self.assertRaises(cleanup.RemoveError):
            cleanup.remove([str(empty)], "delete")
        self.assertTrue(empty.exists())

        ok = cleanup.remove([str(empty)], "delete", confirmed=True)
        self.assertEqual(ok["removed_count"], 1)
        self.assertFalse(empty.exists())

    def test_folder_that_filled_up_is_not_removed(self):
        empty = self.work / "empty"
        empty.mkdir()
        cleanup.scan(str(self.work))
        (empty / "surprise.txt").write_bytes(b"boo")
        result = cleanup.remove([str(empty)], "trash")
        self.assertEqual(result["removed_count"], 0)
        self.assertTrue(result["errors"])

    def test_junk_can_be_skipped(self):
        self.make("cache.tmp", b"temp")
        result = cleanup.scan(str(self.work), include_junk=False)
        self.assertEqual(result["junk"], [])

    def test_age_is_clamped_and_bad_folder_rejected(self):
        result = cleanup.scan(str(self.work), age_days=99_999)
        self.assertEqual(result["age_days"], cleanup.MAX_AGE_DAYS)
        with self.assertRaises(cleanup.ScanError):
            cleanup.scan("")
        with self.assertRaises(cleanup.ScanError):
            cleanup.scan(str(self.root / "нет-такой"))

    def test_undo_of_foreign_run_is_rejected(self):
        old = self.make("gone.txt", b"old", age_days=900)
        cleanup.scan(str(self.work))
        cleanup.remove([str(old)], "trash")
        with self.assertRaises(cleanup.RemoveError):
            cleanup.undo("del_20000101_00000000")

    def test_custom_cleanup_rules(self):
        custom_file = self.root / "cleanup_rules.json"
        os.environ["HUB_CLEANUP_RULES_FILE"] = str(custom_file)
        try:
            saved = cleanup.save_rules({"suffixes": [".custom_junk", ".trashme"], "names": ["my_junk.dat"]})
            self.assertIn(".custom_junk", saved["suffixes"])
            self.assertIn("my_junk.dat", saved["names"])
            self.assertTrue(cleanup._junk("my_junk.dat"))
            self.assertTrue(cleanup._junk("something.custom_junk"))

            reset = cleanup.reset_rules()
            self.assertNotIn(".custom_junk", reset["suffixes"])
            self.assertFalse(cleanup._junk("something.custom_junk"))
        finally:
            os.environ.pop("HUB_CLEANUP_RULES_FILE", None)
            cleanup.reset_rules()


if __name__ == "__main__":
    unittest.main()
