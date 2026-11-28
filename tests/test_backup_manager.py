import os
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from threading import Event
from unittest.mock import patch

from tools import backup_manager as backup, jobs, paths


class BackupTests(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        base = Path(workspace.name)
        profile_store = patch.object(paths, "DATA_DIR", base / "hub")
        profile_store.start()
        self.addCleanup(profile_store.stop)
        self.source, self.destination, self.restore = (base / name for name in ("source", "copies", "restore"))
        for directory in (self.source, self.destination, self.restore):
            directory.mkdir()

    def profile(self, days=0):
        backup.save_profile(None, "Example", [self.source], self.destination, ["*.tmp"], days, 0)
        return backup.profiles()[0]

    @staticmethod
    def job():
        return jobs.Job(float("inf"))

    def test_versions_copy_only_changes_then_restore_files_and_empty_folders(self):
        item = self.source / "заметка.txt"
        item.write_bytes(b"first version")
        (self.source / "ignored.tmp").touch()
        (self.source / "empty").mkdir()
        profile = self.profile()
        first = backup.run_backup(profile, self.job())
        repeat = backup.create(profile, self.job())
        item.write_bytes(b"next version with more data")
        latest = backup.create(profile, self.job())
        self.assertEqual([row["id"] for row in backup.history(profile)], [latest, repeat, first])
        self.assertEqual([row["copied"] for row in backup.history(profile)],
                         [len(b"next version with more data"), 0, len(b"first version")])
        self.assertEqual(backup.verify(profile, first, self.job()), 1)
        plan = backup.preview(profile, first, self.restore, self.job())
        self.assertEqual(backup.restore(profile, plan, self.job()), 1)
        restored = self.restore / self.source.name
        self.assertEqual((restored / item.name).read_bytes(), b"first version")
        self.assertFalse((restored / "ignored.tmp").exists())
        self.assertTrue((restored / "empty").is_dir())

    def test_cancellation_removes_new_blocks_and_keeps_published_version(self):
        item = self.source / "file.txt"
        item.write_text("preserve previous copy", encoding="utf-8")
        profile = self.profile()
        original = backup.create(profile, self.job())
        blocks = backup._repository(profile)[1]
        expected = [item.name for item in blocks.iterdir()]
        item.write_text("a new copy that will be cancelled", encoding="utf-8")

        class CancelOnFirstFile(jobs.Job):
            def report(self, entries, files, size):
                if files:
                    self.cancelled.set()

        with self.assertRaises(jobs.Cancelled):
            backup.create(profile, CancelOnFirstFile(float("inf")))
        self.assertEqual([row["id"] for row in backup.history(profile)], [original])
        self.assertEqual(expected, [item.name for item in blocks.iterdir()])

    def test_changed_destination_and_bad_checksum_never_replace_existing_file(self):
        source = self.source / "file.txt"
        source.write_bytes(b"backup bytes")
        profile = self.profile()
        version = backup.create(profile, self.job())
        output_dir = self.restore / self.source.name
        output_dir.mkdir()
        output = output_dir / source.name
        output.write_bytes(b"original")
        plan = backup.preview(profile, version, self.restore, self.job())
        output.write_bytes(b"changed outside Hub")
        with self.assertRaisesRegex(backup.BackupError, "changed"):
            backup.restore(profile, plan, self.job())
        plan = backup.preview(profile, version, self.restore, self.job())
        blocks = backup._repository(profile)[1]
        block, = blocks.iterdir()
        block.write_bytes(b"tamper bytes")
        with self.assertRaisesRegex(backup.BackupError, "checksum"):
            backup.verify(profile, version, self.job())
        with self.assertRaisesRegex(backup.BackupError, "checksum"):
            backup.restore(profile, plan, self.job())
        self.assertEqual(output.read_bytes(), b"changed outside Hub")
        self.assertEqual(list(output_dir.iterdir()), [output])

    def test_expiry_does_not_remove_blocks_referenced_by_current_version(self):
        (self.source / "shared.txt").write_bytes(b"persist")
        profile = self.profile(1)
        first = backup.create(profile, self.job())
        repository, _ = backup._repository(profile)
        with closing(backup._open_manifest(repository)) as conn, conn:
            conn.execute("UPDATE versions SET created=1 WHERE id=?", (first,))
        version = backup.create(profile, self.job())
        self.assertEqual([row["id"] for row in backup.history(profile)], [version])
        self.assertEqual(backup.verify(profile, version, self.job()), 1)

    def test_scheduler_creates_a_first_version_from_saved_profile(self):
        (self.source / "scheduled.txt").touch()
        identity = backup.save_profile(None, "Scheduled", [self.source], self.destination, [], 0, 1)
        scheduler = backup.Scheduler()
        self.addCleanup(scheduler.shutdown)
        finished = Event()
        original = backup.run_backup

        def run(profile, control):
            result = original(profile, control)
            finished.set()
            return result

        with patch.object(backup, "run_backup", side_effect=run):
            scheduler.start()
            self.assertTrue(finished.wait(5))
        profile, = backup.profiles()
        self.assertEqual(profile["id"], identity)
        self.assertIsNotNone(profile["attempted"])
        self.assertEqual(len(backup.history(profile)), 1)

    def test_preview_rejects_a_junction_and_manifest_traversal(self):
        (self.source / "file").touch()
        profile = self.profile()
        version = backup.create(profile, self.job())
        link = self.restore / self.source.name
        if os.name == "nt":
            import subprocess
            if subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/j", str(link), str(self.destination)],
                              capture_output=True).returncode:
                self.skipTest("Junction creation needs an unrestricted Windows runner")
        else:
            link.symlink_to(self.destination, target_is_directory=True)
        with self.assertRaises(backup.BackupError):
            backup.preview(profile, version, self.restore, self.job())
        if os.name == "nt":
            link.rmdir()
        else:
            link.unlink()
        repo, _ = backup._repository(profile)
        with closing(backup._open_manifest(repo)) as conn, conn:
            conn.execute("UPDATE manifest SET path='../outside' WHERE version=? AND kind='file'", (version,))
        with self.assertRaisesRegex(backup.BackupError, "unsafe"):
            backup.preview(profile, version, self.restore, self.job())
