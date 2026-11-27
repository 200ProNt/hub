import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch
from urllib.request import Request, urlopen

from benchmarks.rust_disk_map import blocked_folders
from tools import diskmap, jobs, paths, preferences, rust_diskmap


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

    def test_real_deny_list_directory_keeps_other_results(self):
        self.put("good.bin", b"visible")
        self.put("blocked-folder/secret.bin", b"not counted")
        with blocked_folders(self.root):
            result = self.compare()
        self.assertEqual((result["files"], result["dirs"], result["error_count"], result["total"]), (1, 1, 1, 7))

    def test_windows_junction_cycle_and_repeated_target(self):
        self.put("ordinary/one.bin", b"1")
        for name, target in (("loop", self.root), ("again", self.root / "ordinary")):
            link = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(self.root / name), str(target)],
                                  capture_output=True)
            self.assertEqual(link.returncode, 0, link.stderr)
        result = self.compare()
        self.assertEqual((result["files"], result["links"], result["total"]), (1, 2, 1))

    def test_real_symlink(self):
        existing = self.put("existing/file.bin", b"1234")
        try:
            (self.root / "file-link").symlink_to(existing)
            (self.root / "dir-link").symlink_to(existing.parent, target_is_directory=True)
        except OSError as error:
            if getattr(error, "winerror", None) == 1314:
                self.skipTest("WinError 1314: the Windows token cannot create symbolic links")
            raise
        result = self.compare()
        self.assertEqual((result["files"], result["links"], result["total"]), (1, 2, 4))

    def test_long_unicode_paths_and_depth_limit(self):
        folder = "/".join(["длина"] * 59)
        path = self.put(folder + "/emoji-🙂.bin", b"yes")
        self.assertGreater(len(str(path)), 260)
        self.put(folder + "/one/two/hidden.bin", b"no")
        result = self.compare()
        self.assertEqual((result["files"], result["total"], result["dirs"], result["truncated"]), (1, 3, 60, True))

    def test_files_changed_and_deleted_during_scan_are_fresh_next_time(self):
        updated = self.put("update.bin", b"111")
        deleted = self.put("delete.bin", b"22")
        for index in range(30_000):
            self.put(f"batch-{index // 10}/{index:05}.bin", b"x")
        changed = Event()
        total_entries = 33_002

        class Control:
            def check(self):
                pass

            def report(self, entries, _files, _size):
                if 0 < entries < total_entries and not changed.is_set():
                    updated.write_bytes(b"1234567")
                    deleted.unlink()
                    changed.set()

        report = rust_diskmap.scan(str(self.root), control=Control())
        self.assertTrue(changed.is_set(), "Worker did not report progress before finishing")
        self.assertIn(report["files"], (30_001, 30_002))
        self.assertIn(report["total"], (30_003, 30_005, 30_007, 30_009))
        self.assertEqual(self.compare()["total"], 30_007)

    def test_mounted_volume_root_is_read_only(self):
        normal = self.put("normal.bin", b"12345")
        self.put("Windows/system.bin", b"excluded")
        drive = next((f"{letter}:" for letter in "ZYXWVUTSRQPONMLK" if not Path(f"{letter}:\\").exists()), None)
        self.assertIsNotNone(drive, "No free drive letter for temporary volume")
        subprocess.run(["subst.exe", drive, os.fspath(self.root)], check=True, capture_output=True)
        try:
            mounted = drive + "\\"
            result = rust_diskmap.scan(mounted, allow_volume_root=True)
            python = diskmap.scan(mounted, allow_volume_root=True)
            result.pop("seconds")
            python.pop("seconds")
            self.assertEqual(result, python)
            self.assertEqual((result["total"], result["error_count"], result["read_only_root"]), (5, 1, True))
            with self.assertRaises(diskmap.ScanError):
                diskmap.files(mounted)
            with self.assertRaises(diskmap.RemoveError):
                diskmap.remove_file(mounted + "normal.bin", "delete", True)
            self.assertTrue(normal.is_file())
        finally:
            subprocess.run(["subst.exe", drive, "/D"], check=True, capture_output=True)

    def test_saved_switch_and_single_fallback_through_http(self):
        from server import HubHandler, HubServer

        directory = self.put("scan/а.txt", b"123").parent
        with patch.object(paths, "DATA_DIR", self.root), HubServer(("127.0.0.1", 0), HubHandler) as server:
            serving = threading.Thread(target=server.serve_forever, daemon=True)
            serving.start()
            base = f"http://127.0.0.1:{server.server_port}/api/"

            def fetch(route, body=None):
                data = None if body is None else json.dumps(body).encode()
                request = Request(base + route, data=data, headers={"Content-Type": "application/json"})
                with urlopen(request, timeout=5) as response:
                    return json.load(response)

            def scan():
                identity = fetch("diskmap/jobs/start", {"folder": str(directory)})
                for _ in range(100):
                    report = fetch("diskmap/jobs/status", identity)
                    if report["state"] == "done":
                        return report["result"]
                    self.assertEqual(report["state"], "running", report)
                    time.sleep(.02)
                self.fail("Calculation did not finish")

            try:
                self.assertFalse(fetch("info")["diskmap_rust"])
                self.assertEqual(scan()["scan_backend"], "python")
                self.assertTrue(fetch("diskmap/backend", {"enabled": True})["enabled"])
                self.assertEqual(preferences.read()[preferences.RUST_DISKMAP], "on")
                self.assertEqual(scan()["scan_backend"], "rust")
                damaged = self.put("damaged.exe", b"not an executable")
                with (patch.object(rust_diskmap, "executable", return_value=damaged),
                      patch.object(diskmap, "scan", wraps=diskmap.scan) as fallback):
                    result = scan()
                    self.assertEqual((result["scan_backend"], result["total"], fallback.call_count), ("python", 3, 1))
                    self.assertIn("Rust Worker", result["fallback_reason"])
                self.assertFalse(fetch("diskmap/backend", {"enabled": False})["enabled"])
                self.assertEqual(scan()["scan_backend"], "python")
            finally:
                server.shutdown()
                serving.join(timeout=5)

    def test_worker_failure_after_progress_and_cancel_have_distinct_paths(self):
        from server import _scan_diskmap

        job = jobs.Job(time.monotonic() + 5)

        def crash(_folder, *, allow_volume_root, control):
            control.report(64, 0, 0)
            raise rust_diskmap.WorkerError("Worker crashed")

        with patch.object(rust_diskmap, "scan", side_effect=crash):
            self.assertEqual(_scan_diskmap(str(self.root), True, job)["fallback_reason"], "Worker crashed")
        self.assertEqual(job.progress, (0, 0, 0))
        job.cancelled.set()
        with (patch.object(rust_diskmap, "scan", side_effect=jobs.Cancelled),
              patch.object(diskmap, "scan") as fallback, self.assertRaises(jobs.Cancelled)):
            _scan_diskmap(str(self.root), True, job)
        fallback.assert_not_called()
