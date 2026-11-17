"""Тесты карты диска: размеры папок и разбиение на сектора."""

from __future__ import annotations

import sys
import tempfile
import unittest
import json
import os
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import diskmap  # noqa: E402


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

        first = diskmap.scan(str(self.root))
        second = diskmap.scan(str(self.root))

        self.assertIs(first, second)


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
        except OSError:
            self.skipTest("Symbolic links require Windows privileges")
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
        from server import HubHandler
        path = self.write()
        server = ThreadingHTTPServer(("127.0.0.1", 0), HubHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{server.server_port}"

        def request(route, body=None):
            data = None if body is None else json.dumps(body).encode()
            req = urllib.request.Request(base + "/api/diskmap/" + route, data=data,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req) as response:
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
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == "__main__":
    unittest.main(verbosity=2)
