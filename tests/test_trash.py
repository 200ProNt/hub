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

    def test_runs_list_what_can_still_come_back(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.dict(os.environ, {"HUB_TRASH_DIR": str(root / "trash")}):
                first = root / "old.txt"
                first.write_bytes(b"12345")
                older = trash.move([str(first)], "cleanup", {"folder": str(root)})
                second = root / "new.txt"
                second.write_bytes(b"12")
                newer = trash.move([str(second)], "bigfiles")

                runs = trash.runs()
                self.assertEqual([run["run_id"] for run in runs], [newer["run_id"], older["run_id"]])
                self.assertEqual(runs[1]["source"], "cleanup")
                self.assertEqual(runs[1]["count"], 1)
                self.assertEqual(runs[1]["size"], 5)
                self.assertEqual(runs[1]["items"][0]["name"], "old.txt")
                self.assertEqual(runs[1]["folder"], str(root))

                trash.undo(newer["run_id"])
                self.assertEqual([run["run_id"] for run in trash.runs()], [older["run_id"]])

    def test_broken_journal_is_skipped_but_its_folder_survives(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.dict(os.environ, {"HUB_TRASH_DIR": str(root / "trash")}):
                broken = root / "trash" / "del_broken"
                broken.mkdir(parents=True)
                (broken / "journal.json").write_text("{не json")
                self.assertEqual(trash.runs(), [])
                self.assertTrue(broken.is_dir())

    def test_purge_removes_one_run_and_reports_freed_space(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.dict(os.environ, {"HUB_TRASH_DIR": str(root / "trash")}):
                file = root / "gone.bin"
                file.write_bytes(b"1234567")
                run = trash.move([str(file)], "diskmap")

                result = trash.purge([run["run_id"]])
                self.assertEqual(result["removed"], 1)
                self.assertGreaterEqual(result["freed"], 7)
                self.assertEqual(result["errors"], [])
                self.assertFalse((root / "trash" / run["run_id"]).exists())
                self.assertEqual(trash.runs(), [])
                with self.assertRaises(trash.TrashError):
                    trash.undo(run["run_id"])

    def test_purge_refuses_unknown_and_escaping_ids(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.dict(os.environ, {"HUB_TRASH_DIR": str(root / "trash")}):
                outside = root / "outside"
                outside.mkdir()
                (outside / "keep.txt").write_bytes(b"keep")
                result = trash.purge(["../outside", "del_missing", ""])
                self.assertEqual(result["removed"], 0)
                self.assertEqual(len(result["errors"]), 2)
                self.assertTrue((outside / "keep.txt").exists())

    def test_empty_clears_the_whole_trash_including_broken_folders(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.dict(os.environ, {"HUB_TRASH_DIR": str(root / "trash")}):
                file = root / "a.txt"
                file.write_bytes(b"1234")
                trash.move([str(file)], "cleanup")
                broken = root / "trash" / "del_broken"
                broken.mkdir(parents=True)
                (broken / "journal.json").write_text("{не json")

                result = trash.empty()
                self.assertEqual(result["removed"], 2)
                self.assertGreaterEqual(result["freed"], 4)
                self.assertEqual(trash.runs(), [])
                self.assertEqual(list((root / "trash").iterdir()), [])
