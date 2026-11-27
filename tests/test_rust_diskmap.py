import subprocess
import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch

from tools import diskmap, jobs, rust_diskmap


@unittest.skipUnless(rust_diskmap.executable().is_file(), "build the Rust Disk Map worker first")
class RustDiskMapTests(unittest.TestCase):
    def setUp(self):
        fixture = tempfile.TemporaryDirectory()
        self.addCleanup(fixture.cleanup)
        self.root = Path(fixture.name).resolve()

    def put(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def compare(self, **options):
        python = diskmap.scan(str(self.root), **options)
        rust = rust_diskmap.scan(str(self.root), **options)
        python.pop("seconds")
        rust.pop("seconds")
        self.assertEqual(rust, python)
        return rust

    def test_regular_nested_unicode_and_entry_limit(self):
        self.put("Семья/写真/🙂.txt", b"sample")
        self.put("notes.txt", b"hello")
        self.put("Семья/empty/data", b"")
        self.assertEqual(self.compare()["total"], 11)
        with patch.object(diskmap, "MAX_ENTRIES", 3):
            self.assertTrue(self.compare()["truncated"])

    def test_launch_error_and_exit_without_success(self):
        with self.assertRaises(rust_diskmap.WorkerError):
            rust_diskmap.scan(str(self.root), worker=self.root / "missing.exe")
        failure = subprocess.run([str(rust_diskmap.executable())], input=b"{}\n", capture_output=True, timeout=5)
        self.assertNotEqual(failure.returncode, 0)
        self.assertNotIn(b'"event":"result"', failure.stdout)

    def test_cancellation_reaps_process(self):
        self.put("one.txt", b"hi")
        paused = Event()
        process = []

        def hang(child, request, messages):
            process.append(child)
            paused.set()
            child.wait(timeout=5)
            child.stdin.close()
            child.stdout.close()
            messages.put(None)

        class Control:
            def check(self):
                if paused.is_set():
                    raise jobs.Cancelled

        with patch.object(rust_diskmap, "_exchange", hang), self.assertRaises(jobs.Cancelled):
            rust_diskmap.scan(str(self.root), control=Control())
        self.assertIsNotNone(process[0].returncode)

    def test_hung_process_deadline(self):
        process = []

        def hang(child, request, messages):
            process.append(child)
            child.wait(timeout=5)
            child.stdin.close()
            child.stdout.close()

        with (patch.object(rust_diskmap, "_exchange", hang), patch.object(rust_diskmap, "IDLE_TIMEOUT", .1),
              self.assertRaises(rust_diskmap.WorkerError)):
            rust_diskmap.scan(str(self.root))
        self.assertIsNotNone(process[0].returncode)

    def test_progress_from_running_worker_and_cancel(self):
        for index in range(4000):
            self.put(f"batch-{index // 100}/{index:04}.bin", b"x")
        calls = []

        class Control:
            def check(self):
                if calls:
                    raise jobs.Cancelled

            def report(self, entries, files, size):
                calls.append((entries, files, size))

        with self.assertRaises(jobs.Cancelled):
            rust_diskmap.scan(str(self.root), control=Control())
        self.assertGreater(calls[0][0], 0)
        self.assertGreater(calls[0][1], 0)
