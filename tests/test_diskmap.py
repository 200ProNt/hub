"""Тесты карты диска: размеры папок и разбиение на сектора."""

from __future__ import annotations

import sys
import tempfile
import unittest
import json
import os
import subprocess
import threading
import stat
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock, patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import diskmap, jobs  # noqa: E402


class DiskMapTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        diskmap._cache.clear()

    def tearDown(self) -> None:
        diskmap._cache.clear()
        self._tmp.cleanup()

    def write(self, name: str, size: int) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * size)
        return path

    def entry(self, result: dict, name: str) -> dict:
        return next(item for item in result["entries"] if item["name"] == name)

    @unittest.skipUnless(os.name == "nt", "Windows drive roots are required")
    def test_mounted_volume_root_can_only_be_sized(self):
        self.write("projects/note.txt", 7)
        self.write("loose.bin", 8)
        self.write("Windows/private.bin", 20)
        drive = next((f"{letter}:" for letter in "ZYXWVUTSRQPONMLK" if not Path(f"{letter}:\\").exists()), None)
        if drive is None:
            self.skipTest("No free drive letter for the temporary test volume")
        mount = subprocess.run(["subst.exe", drive, str(self.root)], capture_output=True, check=False)
        if mount.returncode:
            self.skipTest(f"SUBST failed: {mount.stdout or mount.stderr!r}")
        try:
            root = drive + "\\"
            data = diskmap.scan(root, allow_volume_root=True)
            self.assertTrue(data["read_only_root"])
            self.assertEqual((data["files"], data["total"]), (2, 15))
            self.assertEqual(len(data["errors"]), 1)
            with self.assertRaises(diskmap.ScanError):
                diskmap.scan(root)
            with self.assertRaises(diskmap.ScanError):
                diskmap.files(root)
            with self.assertRaises(diskmap.RemoveError):
                diskmap.remove_file(root + "loose.bin", "delete", True)
            self.assertTrue((self.root / "loose.bin").exists())
            with patch.object(diskmap.fileguard, "get_system_directories", return_value={self.root.resolve()}):
                with self.assertRaises(diskmap.ScanError):
                    diskmap.scan(root, allow_volume_root=True)
        finally:
            subprocess.run(["subst.exe", drive, "/D"], check=True, capture_output=True)

    def test_mutation_during_iteration_has_no_stale_follow_up(self):
        first = self.write("old.txt", 3)
        self.write("kept.txt", 4)
        real_scandir = os.scandir

        @contextmanager
        def scandir(path):
            with real_scandir(path) as iterator:
                def entries():
                    for entry in iterator:
                        yield entry
                        if entry.name == first.name:
                            first.write_bytes(b"rewritten")
                yield entries()

        with patch.object(diskmap.os, "scandir", scandir):
            self.assertEqual(diskmap.scan(str(self.root))["total"], 7)
        self.assertEqual(diskmap.scan(str(self.root))["total"], 13)

    def test_sums_sizes_of_subfolders_and_root_files(self) -> None:
        self.write("видео/a.mp4", 3000)
        self.write("видео/b.mp4", 2000)
        self.write("фото/c.jpg", 1200)
        self.write("readme.txt", 500)

        result = diskmap.scan(str(self.root))

        self.assertEqual(result["total"], 6700)
        self.assertEqual(result["dirs"], 2)
        self.assertEqual(result["files"], 4)
        self.assertEqual(self.entry(result, "видео")["size"], 5000)
        self.assertEqual(self.entry(result, "видео")["kind"], "dir")
        self.assertEqual(self.entry(result, "видео")["count"], 2)
        self.assertEqual(self.entry(result, "фото")["size"], 1200)

        loose = self.entry(result, "Файлы в этой папке")
        self.assertEqual(loose["kind"], "files")
        self.assertEqual(loose["size"], 500)
        self.assertEqual(loose["count"], 1)

    def test_nested_folders_are_counted_recursively(self) -> None:
        self.write("Фильмы/2024/отпуск.mkv", 4000)
        self.write("Фильмы/2024/ещё.mkv", 1000)
        self.write("Фильмы/обложка.png", 300)

        result = diskmap.scan(str(self.root))

        self.assertEqual(result["total"], 5300)
        self.assertEqual(result["dirs"], 2)
        self.assertEqual(result["files"], 3)
        self.assertEqual(self.entry(result, "Фильмы")["size"], 5300)

    def test_entries_are_sorted_by_size(self) -> None:
        self.write("малая/a.bin", 100)
        self.write("большая/a.bin", 9000)
        self.write("средняя/a.bin", 2000)

        names = [item["name"] for item in diskmap.scan(str(self.root))["entries"]]

        self.assertEqual(names[:3], ["большая", "средняя", "малая"])

    def test_empty_folder_is_not_an_error(self) -> None:
        result = diskmap.scan(str(self.root))

        self.assertEqual(result["total"], 0)
        self.assertEqual(result["entries"], [])
        self.assertEqual(result["dirs"], 0)
        self.assertEqual(result["files"], 0)

    def test_parent_and_name_are_filled(self) -> None:
        (self.root / "Папка").mkdir()
        result = diskmap.scan(str(self.root / "Папка"))

        self.assertEqual(result["name"], "Папка")
        self.assertEqual(Path(result["parent"]), self.root.resolve())

    def test_bad_paths_raise_scan_error(self) -> None:
        with self.assertRaises(diskmap.ScanError):
            diskmap.scan("")
        with self.assertRaises(diskmap.ScanError):
            diskmap.scan(str(self.root / "нет-такой"))

        file_path = self.write("файл.txt", 10)
        with self.assertRaises(diskmap.ScanError):
            diskmap.scan(str(file_path))

    def test_truncates_when_too_many_entries(self) -> None:
        for number in range(6):
            self.write(f"папка{number}/файл.bin", 10)

        original = diskmap.MAX_ENTRIES
        diskmap.MAX_ENTRIES = 3
        try:
            result = diskmap.scan(str(self.root))
        finally:
            diskmap.MAX_ENTRIES = original

        self.assertTrue(result["truncated"])
        self.assertLess(len(result["entries"]), 6)

    def test_second_scan_uses_cache(self) -> None:
        self.write("папка/a.bin", 1000)

        first = diskmap.scan(str(self.root), use_cache=True)
        second = diskmap.scan(str(self.root), use_cache=True)

        self.assertIs(first, second)
        self.write("папка/b.bin", 12)
        self.assertEqual(diskmap.scan(str(self.root))["total"], 1012)

    def test_streaming_cap_and_depth(self):
        for number in range(500):
            self.write(f"{number:03}.bin", 1)
        scandir = os.scandir
        read = []

        @contextmanager
        def counted(path):
            with scandir(path) as entries:
                def iterate():
                    for entry in entries:
                        read.append(entry.name)
                        yield entry
                yield iterate()

        with patch.object(diskmap, "MAX_ENTRIES", 5), patch.object(diskmap.os, "scandir", counted):
            result = diskmap.scan(str(self.root))
        self.assertEqual((result["files"], len(read)), (5, 6))
        self.assertTrue(result["truncated"])
        self.write("/".join(["a"] * 62) + "/deep.bin", 40)
        result = diskmap.scan(str(self.root))
        self.assertTrue(result["truncated"])
        self.assertEqual(result["total"], 500)

    def test_permission_errors_keep_other_results(self):
        self.write("allowed/a.bin", 13)
        blocked = self.write("blocked/b.bin", 39).parent
        scandir = os.scandir

        def checked(path):
            if Path(path) == blocked:
                raise PermissionError("denied")
            return scandir(path)

        with patch.object(diskmap.os, "scandir", checked), patch.object(diskmap, "MAX_ERRORS", 0):
            result = diskmap.scan(str(self.root))
        self.assertEqual((result["files"], result["total"]), (1, 13))
        self.assertEqual((result["error_count"], result["errors"]), (1, []))

    def test_symlink_mode_and_reparse_attributes_are_excluded(self):
        dummy = [
            SimpleNamespace(name="link", path="link", stat=Mock(return_value=SimpleNamespace(st_mode=stat.S_IFLNK))),
            SimpleNamespace(name="reparse", path="reparse", stat=Mock(return_value=SimpleNamespace(
                st_mode=stat.S_IFREG, st_file_attributes=diskmap.FILE_ATTRIBUTE_REPARSE_POINT))),
        ]

        @contextmanager
        def entries(_):
            yield iter(dummy)

        with patch.object(diskmap.os, "scandir", entries):
            result = diskmap.scan(str(self.root))
        self.assertEqual((result["files"], result["links"], result["total"]), (0, 2, 0))

    def test_volume_scan_omits_system_folders_and_does_not_authorize_removal(self):
        path = self.write("normal.bin", 31)
        self.write("System Volume Information/secret.bin", 80)
        self.write("Windows/system.bin", 100)
        self.write("nested/$Recycle.Bin/deleted.bin", 51)
        with patch.object(diskmap, "_volume_root", return_value=True):
            result = diskmap.scan(str(self.root), allow_volume_root=True)
        self.assertTrue(result["read_only_root"])
        self.assertEqual(result["total"], 31)
        self.assertEqual(len(result["errors"]), 3)
        with self.assertRaises(diskmap.RemoveError):
            diskmap.remove_file(str(path), "delete", True)
        with self.assertRaises(diskmap.ScanError):
            diskmap.files(self.root.resolve().anchor)
        self.assertTrue(path.is_file())


class DiskMapActionsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base / "source"
        self.root.mkdir()
        self.env = patch.dict(os.environ, {"HUB_TRASH_DIR": str(self.base / "trash")})
        self.env.start()
        diskmap._cache.clear()

    def tearDown(self) -> None:
        self.env.stop()
        diskmap._cache.clear()
        self.tmp.cleanup()

    def write(self, name="a.bin", content=b"123") -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_lists_only_direct_files_sorted_by_size_and_name(self) -> None:
        self.write("b.bin", b"xx")
        self.write("a.bin", b"xx")
        self.write("large.bin", b"12345")
        self.write("nested/hidden.bin")
        result = diskmap.files(str(self.root))
        self.assertEqual(result, {"folder": str(self.root), "files": [
            {"name": "large.bin", "path": str(self.root / "large.bin"), "size": 5},
            {"name": "a.bin", "path": str(self.root / "a.bin"), "size": 2},
            {"name": "b.bin", "path": str(self.root / "b.bin"), "size": 2},
        ], "truncated": False, "errors": []})

    def test_listing_is_bounded_and_invalid_folder_revokes_authorization(self) -> None:
        path = self.write()
        self.write("b.bin")
        with patch.object(diskmap, "MAX_ENTRIES", 1):
            self.assertTrue(diskmap.files(str(self.root))["truncated"])
        diskmap.files(str(self.root))
        with self.assertRaises(diskmap.ScanError):
            diskmap.files(str(self.root / "missing"))
        with self.assertRaises(diskmap.RemoveError):
            diskmap.remove_file(str(path), "trash")
        self.assertTrue(path.exists())

    def test_only_latest_listing_authorizes_regular_files(self) -> None:
        path = self.write()
        other = self.write("other/b.bin")
        diskmap.files(str(self.root))
        for rejected in (other, self.root / "other"):
            with self.assertRaises(diskmap.RemoveError):
                diskmap.remove_file(str(rejected), "trash")
        diskmap.files(str(other.parent))
        with self.assertRaises(diskmap.RemoveError):
            diskmap.remove_file(str(path), "trash")
        self.assertTrue(path.exists())

    def test_modified_or_replaced_file_is_rejected(self) -> None:
        path = self.write()
        diskmap.files(str(self.root))
        path.write_bytes(b"changed")
        with self.assertRaises(diskmap.RemoveError):
            diskmap.remove_file(str(path), "trash")
        diskmap.files(str(self.root))
        replacement = self.write("replacement.bin", b"changed")
        os.replace(replacement, path)
        with self.assertRaises(diskmap.RemoveError):
            diskmap.remove_file(str(path), "delete", True)
        self.assertEqual(path.read_bytes(), b"changed")

    def test_paged_listing_only_authorizes_shown_unchanged_files(self) -> None:
        first = self.write("first.bin", b"12345")
        next_file = self.write("next.bin", b"123")
        self.write("last.bin", b"1")
        with patch.object(diskmap, "FILE_PAGE_SIZE", 1):
            page = diskmap.files(str(self.root), paged=True)
            token = page["listing"]
            self.assertEqual([row["path"] for row in page["files"]], [str(first)])
            self.assertEqual((page["count"], page["next_offset"]), (3, 1))
            for path, listing in [(first, None), (next_file, token)]:
                with self.assertRaises(diskmap.RemoveError):
                    diskmap.remove_file(str(path), "delete", True, listing=listing)
            first.write_bytes(b"updated")
            with self.assertRaises(diskmap.RemoveError):
                diskmap.remove_file(str(first), "trash", listing=token)
            self.assertEqual(diskmap.file_page(token, 0)["files"], [])
            page = diskmap.file_page(token, page["next_offset"])
            self.assertEqual([row["path"] for row in page["files"]], [str(next_file)])
            moved = diskmap.remove_file(str(next_file), "trash", listing=token)
            self.assertEqual(moved["removed_count"], 1)
            self.assertEqual(diskmap.undo(moved["run_id"])["restored_count"], 1)
            self.assertEqual(next_file.read_bytes(), b"123")
            with self.assertRaises(diskmap.ScanError):
                diskmap.file_page(token, 2)

    def test_parent_replacement_is_rejected_even_when_file_identity_is_unchanged(self) -> None:
        path = self.write("nested/a.bin")
        diskmap.files(str(path.parent))
        old = self.root / "old"
        path.parent.rename(old)
        path.parent.mkdir()
        (old / path.name).rename(path)
        with self.assertRaises(diskmap.RemoveError):
            diskmap.remove_file(str(path), "trash")
        self.assertTrue(path.exists())

    def test_file_replaced_by_directory_is_rejected(self) -> None:
        path = self.write()
        diskmap.files(str(self.root))
        path.unlink()
        path.mkdir()
        with self.assertRaises(diskmap.RemoveError):
            diskmap.remove_file(str(path), "trash")
        self.assertTrue(path.is_dir())

    def test_links_are_not_listed_or_authorized(self) -> None:
        target = self.write("nested/target.bin")
        link = self.root / "link.bin"
        try:
            link.symlink_to(target)
        except OSError as exc:
            if getattr(exc, "winerror", None) == 1314:
                self.skipTest("WinError 1314: the Windows token cannot create symbolic links")
            raise
        self.assertEqual(diskmap.files(str(self.root))["files"], [])
        with self.assertRaises(diskmap.RemoveError):
            diskmap.remove_file(str(link), "trash")
        with self.assertRaises(diskmap.ScanError):
            diskmap.files(str(link.parent / "nested-link"))

    def test_parent_junction_after_listing_is_rejected(self) -> None:
        import subprocess
        path = self.write("nested/a.bin")
        diskmap.files(str(path.parent))
        old = self.root / "old"
        path.parent.rename(old)
        if os.name == "nt":
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(path.parent), str(old)], capture_output=True)
            if result.returncode:
                self.skipTest("Cannot create junction")
        else:
            path.parent.symlink_to(old, target_is_directory=True)
        try:
            result = diskmap.scan(str(self.root))
            self.assertEqual((result["files"], result["links"]), (1, 1))
            with self.assertRaises(diskmap.RemoveError):
                diskmap.remove_file(str(path), "trash")
            with self.assertRaises(diskmap.ScanError):
                diskmap.files(str(path.parent))
            self.assertEqual((old / "a.bin").read_bytes(), b"123")
        finally:
            if os.name == "nt":
                path.parent.rmdir()
            else:
                path.parent.unlink()

    def test_trash_undo_last_run_and_cache_invalidation(self) -> None:
        path = self.write()
        self.assertEqual(diskmap.scan(str(self.root))["total"], 3)
        diskmap.files(str(self.root))
        result = diskmap.remove_file(str(path), "trash")
        self.assertEqual(result["removed_count"], 1)
        self.assertEqual(result["removed_size"], 3)
        self.assertEqual(result["errors"], [])
        self.assertFalse(path.exists())
        self.assertEqual(diskmap.last_run()["run_id"], result["run_id"])
        self.assertEqual(diskmap.last_run()["folder"], str(self.root))
        self.assertEqual(diskmap.scan(str(self.root))["total"], 0)
        self.assertEqual(diskmap.undo(result["run_id"])["restored_count"], 1)
        self.assertEqual(path.read_bytes(), b"123")
        self.assertEqual(diskmap.scan(str(self.root))["total"], 3)
        self.assertIsNone(diskmap.last_run())
        with self.assertRaises(diskmap.RemoveError):
            diskmap.remove_file(str(path), "trash")

    def test_permanent_delete_requires_literal_confirmation_and_valid_mode(self) -> None:
        path = self.write()
        diskmap.files(str(self.root))
        for confirmation in (False, "true", 1, None):
            with self.assertRaises(diskmap.RemoveError):
                diskmap.remove_file(str(path), "delete", confirmation)
        with self.assertRaises(diskmap.RemoveError):
            diskmap.remove_file(str(path), "invalid", True)
        result = diskmap.remove_file(str(path), "delete", True)
        self.assertEqual(result, {"removed_count": 1, "removed_size": 3, "errors": [], "run_id": None})
        self.assertFalse(path.exists())
        self.assertIsNone(diskmap.last_run())

    def test_failed_delete_reports_error_without_claiming_removal(self) -> None:
        path = self.write()
        diskmap.files(str(self.root))
        with patch.object(Path, "unlink", side_effect=PermissionError("denied")):
            result = diskmap.remove_file(str(path), "delete", True)
        self.assertEqual(result["removed_count"], 0)
        self.assertEqual(result["removed_size"], 0)
        self.assertTrue(result["errors"])
        self.assertTrue(path.exists())

    def test_repeated_and_concurrent_removals_have_only_one_winner(self) -> None:
        path = self.write()
        diskmap.files(str(self.root))
        results = []
        rejected = []

        def remove():
            try:
                results.append(diskmap.remove_file(str(path), "trash"))
            except diskmap.RemoveError as exc:
                rejected.append(str(exc))

        workers = [threading.Thread(target=remove) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["removed_count"], 1)
        self.assertEqual(len(rejected), 1)

    def test_failed_trash_move_reports_zero_removed(self) -> None:
        path = self.write()
        diskmap.files(str(self.root))
        with patch("tools.trash.shutil.move", side_effect=PermissionError("denied")):
            result = diskmap.remove_file(str(path), "trash")
        self.assertEqual(result["removed_count"], 0)
        self.assertEqual(result["removed_size"], 0)
        self.assertIsNone(result["run_id"])
        self.assertTrue(result["errors"])
        self.assertTrue(path.exists())

    def test_diskmap_undo_rejects_other_tools_journals(self) -> None:
        from tools import trash
        path = self.write()
        run = trash.move([str(path)], "other")
        with self.assertRaises(diskmap.RemoveError):
            diskmap.undo(run["run_id"])
        self.assertFalse(path.exists())

    def test_http_endpoints_and_validation(self) -> None:
        from server import HubHandler, HubServer
        path = self.write()
        server = HubServer(("127.0.0.1", 0), HubHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{server.server_port}"

        def request(route, body=None):
            data = None if body is None else json.dumps(body).encode()
            req = urllib.request.Request(base + "/api/diskmap/" + route, data=data,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.load(response)

        try:
            self.assertIsNone(request("last-run")["last_run"])
            with patch.object(diskmap, "last_run", side_effect=PermissionError("denied")):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    request("last-run")
                self.assertEqual(caught.exception.code, 400)
                self.assertIn("error", json.load(caught.exception))
                caught.exception.close()
            self.assertEqual(len(request("files", {"folder": str(self.root)})["files"]), 1)
            with self.assertRaises(urllib.error.HTTPError) as caught:
                request("remove", {"path": str(path), "mode": "delete", "confirmed": "true"})
            self.assertEqual(caught.exception.code, 400)
            self.assertIn("error", json.load(caught.exception))
            caught.exception.close()
            removed = request("remove", {"path": str(path), "mode": "trash"})
            self.assertEqual(request("last-run")["last_run"]["run_id"], removed["run_id"])
            self.assertEqual(request("undo", {"run_id": removed["run_id"]})["restored_count"], 1)
            with self.assertRaises(urllib.error.HTTPError) as caught:
                request("undo", {"run_id": "../invalid"})
            self.assertEqual(caught.exception.code, 400)
            caught.exception.close()

            old = request("files", {"folder": str(self.root), "paged": True})
            other = self.base / "other"
            other.mkdir()
            request("scan", {"folder": str(other)})
            for route, body in (
                ("files/page", {"listing": old["listing"], "offset": 0}),
                ("remove", {"path": str(path), "mode": "delete", "confirmed": True,
                            "listing": old["listing"]}),
            ):
                with self.assertRaises(urllib.error.HTTPError) as stale:
                    request(route, body)
                self.assertEqual(stale.exception.code, 400)
                stale.exception.close()
            current = request("files", {"folder": str(self.root), "paged": True})
            self.assertNotEqual(old["listing"], current["listing"])
            self.assertEqual(path.read_bytes(), b"123")

            entered, release, closed = (threading.Event() for _ in range(3))
            real_scandir = os.scandir
            for index in range(73):
                self.write(f"sample-{index}")

            @contextmanager
            def scandir(directory):
                with real_scandir(directory) as iterator:
                    def entries():
                        for index, entry in enumerate(iterator):
                            if index == 70:
                                entered.set()
                                release.wait(5)
                            if index > 70:
                                self.fail("Cancelled job consumed another directory entry")
                            yield entry
                    try:
                        yield entries()
                    finally:
                        closed.set()

            def terminal(identity):
                for _ in range(100):
                    update = request("jobs/status", identity)
                    if update["state"] not in ("running", "cancelling"):
                        return update
                    time.sleep(.02)
                self.fail("Background job did not finish")

            folder = {"folder": str(self.root)}
            with patch.object(diskmap.os, "scandir", scandir):
                identity = request("jobs/start", folder)
                try:
                    self.assertTrue(entered.wait(5))
                    status = request("jobs/status", identity)
                    self.assertEqual((status["state"], status["entries"]), ("running", 64))
                    self.assertGreater(status["files"], 0)
                    with self.assertRaises(urllib.error.HTTPError) as busy:
                        request("jobs/start", folder)
                    self.assertEqual(busy.exception.code, 409)
                    busy.exception.close()
                    self.assertEqual(request("jobs/cancel", identity)["state"], "cancelling")
                finally:
                    release.set()
                self.assertTrue(closed.wait(5))
                self.assertEqual(terminal(identity)["state"], "cancelled")

            result = terminal(request("jobs/start", folder))
            self.assertEqual((result["state"], result["result"]["files"]), ("done", 74))
            failed = terminal(request("jobs/start", {"folder": str(self.root / "missing")}))
            self.assertEqual(failed["state"], "failed")
            self.assertTrue(failed["error"])
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


class JobsTestCase(unittest.TestCase):
    def test_abandoned_job_checks_lease_and_closes(self):
        manager = jobs.Jobs(lease_seconds=.05)
        entered, release, closed = (threading.Event() for _ in range(3))

        def worker(job):
            try:
                entered.set()
                release.wait(3)
                job.check()
            finally:
                closed.set()

        identity = manager.start(worker)
        try:
            self.assertTrue(entered.wait(3))
            time.sleep(.1)
            release.set()
            self.assertTrue(closed.wait(3))
            for _ in range(100):
                status = manager.poll(identity)
                if status["state"] == "cancelled":
                    break
                time.sleep(.01)
            self.assertEqual(status["state"], "cancelled")
            self.assertIsNone(manager.poll(identity))
        finally:
            release.set()
            manager.shutdown()


if __name__ == "__main__":
    unittest.main(verbosity=2)
