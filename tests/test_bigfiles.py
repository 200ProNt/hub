"""Большие файлы: поиск по размеру и защита удаления."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools import bigfiles, trash


class BigFilesTestCase(unittest.TestCase):
    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)
        self._trash = patch.dict(os.environ, {"HUB_TRASH_DIR": str(self.root / "trash")})
        self._trash.start()
        bigfiles._allowed.clear()

    def tearDown(self):
        bigfiles._allowed.clear()
        self._trash.stop()
        self._temporary.cleanup()

    def make(self, name: str, size: int) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * size)
        return path

    def test_finds_biggest_files_recursively(self):
        self.make("small.txt", 5)
        self.make("big.bin", 400)
        self.make("nested/huge.bin", 900)
        result = bigfiles.scan(str(self.root), limit=10, min_size=1)
        self.assertEqual([item["name"] for item in result["files"]], ["huge.bin", "big.bin", "small.txt"])
        self.assertEqual(result["files"][0]["size"], 900)
        self.assertEqual(result["matched"], 3)
        self.assertEqual(result["matched_size"], 1305)

    def test_min_size_and_limit_are_applied(self):
        self.make("a.bin", 100)
        self.make("b.bin", 300)
        self.make("c.bin", 500)
        result = bigfiles.scan(str(self.root), limit=2, min_size=200)
        self.assertEqual([item["name"] for item in result["files"]], ["c.bin", "b.bin"])
        self.assertEqual(result["matched"], 2)

    def test_limit_is_clamped(self):
        result = bigfiles.scan(str(self.root), limit=10_000, min_size=0)
        self.assertEqual(result["limit"], bigfiles.MAX_LIMIT)

    def test_bad_folder_is_rejected(self):
        with self.assertRaises(bigfiles.ScanError):
            bigfiles.scan("")
        with self.assertRaises(bigfiles.ScanError):
            bigfiles.scan(str(self.root / "нет-такой"))
        file_path = self.make("file.txt", 3)
        with self.assertRaises(bigfiles.ScanError):
            bigfiles.scan(str(file_path))

    def test_remove_requires_the_last_listing(self):
        path = self.make("thing.bin", 50)
        with self.assertRaises(bigfiles.RemoveError):
            bigfiles.remove(str(path), "trash")
        bigfiles.scan(str(self.root), limit=5, min_size=1)
        result = bigfiles.remove(str(path), "trash")
        self.assertEqual(result["removed_count"], 1)
        self.assertFalse(path.exists())
        self.assertTrue(result["run_id"])

    def test_changed_file_is_rejected(self):
        path = self.make("thing.bin", 50)
        bigfiles.scan(str(self.root), limit=5, min_size=1)
        path.write_bytes(b"y" * 51)
        with self.assertRaises(bigfiles.RemoveError):
            bigfiles.remove(str(path), "trash")

    def test_delete_needs_explicit_confirmation(self):
        path = self.make("thing.bin", 10)
        bigfiles.scan(str(self.root), limit=5, min_size=1)
        with self.assertRaises(bigfiles.RemoveError):
            bigfiles.remove(str(path), "delete", confirmed="yes")
        with self.assertRaises(bigfiles.RemoveError):
            bigfiles.remove(str(path), "shred")
        result = bigfiles.remove(str(path), "delete", confirmed=True)
        self.assertEqual(result["removed_count"], 1)
        self.assertFalse(path.exists())

    def test_trash_can_be_undone_and_last_run_clears(self):
        path = self.make("keep.bin", 70)
        bigfiles.scan(str(self.root), limit=5, min_size=1)
        run = bigfiles.remove(str(path), "trash")
        pending = bigfiles.last_run()
        self.assertEqual(pending["run_id"], run["run_id"])
        self.assertEqual(pending["count"], 1)
        restored = bigfiles.undo(run["run_id"])
        self.assertEqual(restored["restored_count"], 1)
        self.assertEqual(path.read_bytes(), b"x" * 70)
        self.assertIsNone(bigfiles.last_run())

    def test_undo_of_foreign_run_is_rejected(self):
        path = self.make("keep.bin", 20)
        bigfiles.scan(str(self.root), limit=5, min_size=1)
        run = bigfiles.remove(str(path), "trash")
        _, journal = trash._read(run["run_id"])
        journal["source"] = "diskmap"
        journal_path = Path(self.root) / "trash" / run["run_id"] / "journal.json"
        journal_path.write_text(json.dumps(journal), encoding="utf-8")
        with self.assertRaises(bigfiles.RemoveError):
            bigfiles.undo(run["run_id"])

    def test_links_are_not_listed_or_authorized(self):
        target = self.make("target.bin", 100)
        link = self.root / "link.bin"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("Symbolic links require Windows privileges")
        result = bigfiles.scan(str(self.root), limit=10, min_size=1)
        self.assertEqual([item["name"] for item in result["files"]], ["target.bin"])
        self.assertEqual(result["links"], 1)
        with self.assertRaises(bigfiles.RemoveError):
            bigfiles.remove(str(link), "trash")


if __name__ == "__main__":
    unittest.main()
