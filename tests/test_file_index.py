import os
import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch

from tools import file_index, jobs, paths


class FileIndexTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        base = Path(directory.name)
        self.root = base / "documents"
        self.root.mkdir()
        use_temp = patch.object(paths, "DATA_DIR", base / "hub-data")
        use_temp.start()
        self.addCleanup(use_temp.stop)

    def index(self, *, force=False, check=lambda: None, report=lambda: None, error=lambda: None):
        for root in file_index.roots():
            file_index.update(root, force, check, report, error)

    def test_incremental_index_tracks_unicode_changes_removal_and_exclusions(self):
        old = self.root / "old.txt"
        old.write_text("Hidden content", encoding="utf-8")
        (self.root / "пРОект.md").write_text("Draft", encoding="utf-8")
        skip = self.root / ".git"
        skip.mkdir()
        (skip / "excluded.md").touch()
        (self.root / "ignored.tmp").touch()
        file_index.save_root(self.root, False, "*.tmp")
        self.index()
        self.assertEqual([row["name"] for row in file_index.search("проект")[0]], ["пРОект.md"])
        self.assertFalse(file_index.search("excluded")[0])
        self.assertFalse(file_index.search("ignored")[0])
        self.assertFalse(file_index.search("Hidden content", contents=True)[0])
        old.rename(self.root / "moved.txt")
        self.index()
        self.assertFalse(file_index.search("old.txt")[0])
        self.assertTrue(file_index.search("moved.txt", kind="documents", extension=".txt", min_size=1, max_size=100)[0])
        self.assertFalse(file_index.search("moved.txt", after=2**40)[0])

    def test_document_opt_in_and_removal_refreshes_index_without_touching_file(self):
        item = self.root / "note.md"
        item.write_text("A unique text query", encoding="utf-8")
        file_index.save_root(self.root, True, "")
        self.index()
        self.assertFalse(file_index.search("unique text")[0])
        self.assertEqual(file_index.search("unique text", contents=True)[0][0]["name"], "note.md")
        item.write_text("Another unique phrase", encoding="utf-8")
        self.index()
        self.assertFalse(file_index.search("unique text", contents=True)[0])
        self.assertTrue(file_index.search("unique phrase", contents=True)[0])
        file_index.save_root(self.root, False, "")
        self.assertFalse(file_index.search("unique phrase", contents=True)[0])
        file_index.remove_root(file_index.roots()[0]["id"])
        self.assertTrue(item.is_file())
        self.assertFalse(file_index.search("note")[0])

    def test_cancelled_rebuild_leaves_previous_snapshot_visible(self):
        initial = self.root / "before.txt"
        initial.touch()
        file_index.save_root(self.root, False, "")
        self.index()
        initial.unlink()
        (self.root / "after.txt").touch()

        def cancel():
            raise jobs.Cancelled()

        with self.assertRaises(jobs.Cancelled):
            self.index(force=True, report=cancel)
        self.assertTrue(file_index.search("before")[0])
        self.assertFalse(file_index.search("after")[0])

    def test_search_pages_and_does_not_follow_a_junction(self):
        destination = self.root.parent / "unselected"
        destination.mkdir()
        (destination / "outside_index.txt").touch()
        junction = self.root / "linked"
        if os.name == "nt":
            import subprocess
            if subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/j", str(junction), str(destination)],
                              capture_output=True).returncode:
                self.skipTest("Junction creation needs an unrestricted Windows runner")
        else:
            junction.symlink_to(destination, target_is_directory=True)
        for number in range(file_index.PAGE_SIZE + 1):
            (self.root / f"entry-{number:04d}.zip").touch()
        file_index.save_root(self.root, False, "")
        self.index()
        rows, more = file_index.search("entry", kind="archives")
        last, last_more = file_index.search("entry", offset=len(rows))
        self.assertEqual(len(rows), file_index.PAGE_SIZE)
        self.assertTrue(more)
        self.assertEqual(len(last), 1)
        self.assertFalse(last_more)
        self.assertFalse(file_index.search("outside_index")[0])

    def test_queued_scan_waits_while_paused(self):
        (self.root / "on-resume.txt").touch()
        file_index.save_root(self.root, False, "")
        worker = file_index.Indexer()
        self.addCleanup(worker.shutdown)
        finished = Event()
        original = file_index.update

        def update(*args):
            original(*args)
            finished.set()

        with patch.object(file_index, "update", side_effect=update):
            worker.pause(True)
            worker.request()
            self.assertTrue(worker.status()["pending"])
            self.assertFalse(file_index.search("on-resume")[0])
            worker.pause(False)
            self.assertTrue(finished.wait(5))
            self.assertTrue(file_index.search("on-resume")[0])
