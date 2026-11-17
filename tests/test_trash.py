"""Shared trash recovery tests; all storage is temporary."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools import trash


class TrashTestCase(unittest.TestCase):
    def test_partial_undo_tracks_only_pending_files_and_can_be_retried(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.dict(os.environ, {"HUB_TRASH_DIR": str(root / "trash")}):
                a, b = root / "a", root / "b"
                a.write_bytes(b"aaa")
                b.write_bytes(b"bb")
                run = trash.move([str(a), str(b)], "diskmap", {"folder": str(root)})
                b.write_bytes(b"replacement")
                first = trash.undo(run["run_id"])
                self.assertEqual(first["restored_count"], 1)
                self.assertEqual(b.read_bytes(), b"replacement")
                pending = trash.last_run("diskmap")
                self.assertEqual(pending["count"], 1)
                self.assertEqual(pending["size"], 2)
                b.unlink()
                second = trash.undo(run["run_id"])
                self.assertEqual(second, {"restored_count": 1, "restored_size": 2, "errors": []})
                self.assertEqual(a.read_bytes(), b"aaa")
                self.assertEqual(b.read_bytes(), b"bb")
                self.assertIsNone(trash.last_run("diskmap"))

    def test_folders_go_to_trash_and_come_back(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.dict(os.environ, {"HUB_TRASH_DIR": str(root / "trash")}):
                folder = root / "empty"
                folder.mkdir()
                inside = root / "box"
                inside.mkdir()
                (inside / "file.txt").write_bytes(b"12345")
                run = trash.move([str(folder), str(inside)], "cleanup")
                self.assertEqual(run["removed_count"], 2)
                self.assertEqual(run["removed_size"], 5)
                self.assertFalse(folder.exists())
                self.assertFalse(inside.exists())
                restored = trash.undo(run["run_id"])
                self.assertEqual(restored["restored_count"], 2)
                self.assertTrue(folder.is_dir())
                self.assertEqual((inside / "file.txt").read_bytes(), b"12345")

    def test_symlinks_are_refused_by_trash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.dict(os.environ, {"HUB_TRASH_DIR": str(root / "trash")}):
                target = root / "target.txt"
                target.write_bytes(b"x")
                link = root / "link.txt"
                try:
                    link.symlink_to(target)
                except (OSError, NotImplementedError):
                    self.skipTest("Symbolic links require Windows privileges")
                run = trash.move([str(link)], "cleanup")
                self.assertIsNone(run["run_id"])
                self.assertIn("ссылка", run["errors"][0]["reason"])
                self.assertTrue(link.exists())

    def test_legacy_journal_without_source_is_not_diskmap_last_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {"HUB_TRASH_DIR": temporary}):
                run = Path(temporary) / "del_legacy"
                run.mkdir()
                (run / "journal.json").write_text(json.dumps({
                    "id": "del_legacy", "moved": [{"from": "a", "to": "b", "size": 3}]
                }))
                self.assertIsNone(trash.last_run("diskmap"))
