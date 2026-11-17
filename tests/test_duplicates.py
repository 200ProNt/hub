"""Тесты поиска дубликатов и корзины хаба."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_trash_tmp = tempfile.TemporaryDirectory()
os.environ["HUB_TRASH_DIR"] = _trash_tmp.name

from tools import duplicates  # noqa: E402


def tearDownModule() -> None:
    _trash_tmp.cleanup()


class DuplicatesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        duplicates._last_scan.clear()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, name: str, content: bytes) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_finds_same_content_with_different_names(self) -> None:
        self.write("отпуск.jpg", b"photo-bytes" * 200)
        self.write("DSC_0421.jpg", b"photo-bytes" * 200)
        self.write("другое.jpg", b"other-bytes" * 200)

        result = duplicates.scan(str(self.root), min_size=1)

        self.assertEqual(result["groups_count"], 1)
        group = result["groups"][0]
        self.assertEqual(group["count"], 2)
        self.assertEqual(sorted(item["name"] for item in group["files"]), ["DSC_0421.jpg", "отпуск.jpg"])
        self.assertEqual(result["duplicate_files"], 1)
        self.assertEqual(result["wasted"], group["size"])

    def test_same_size_different_content_is_not_a_group(self) -> None:
        self.write("a.bin", b"a" * 5000)
        self.write("b.bin", b"b" * 5000)

        result = duplicates.scan(str(self.root), min_size=1)

        self.assertEqual(result["groups"], [])
        self.assertEqual(result["duplicate_files"], 0)

    def test_small_files_are_skipped_by_default(self) -> None:
        self.write("tiny1.txt", b"same")
        self.write("tiny2.txt", b"same")

        self.assertEqual(duplicates.scan(str(self.root))["groups"], [])
        self.assertEqual(duplicates.scan(str(self.root), min_size=1)["groups_count"], 1)

    def test_recursion_toggle(self) -> None:
        self.write("one/a.jpg", b"same-photo" * 100)
        self.write("two/b.jpg", b"same-photo" * 100)

        self.assertEqual(duplicates.scan(str(self.root), recursive=False, min_size=1)["groups"], [])
        self.assertEqual(duplicates.scan(str(self.root), recursive=True, min_size=1)["groups_count"], 1)

    def test_relative_paths_use_forward_slashes(self) -> None:
        self.write("sub/dir/pic.png", b"png-bytes" * 100)
        self.write("pic-copy.png", b"png-bytes" * 100)

        group = duplicates.scan(str(self.root), min_size=1)["groups"][0]
        rels = sorted(item["rel"] for item in group["files"])
        self.assertEqual(rels, ["pic-copy.png", "sub/dir/pic.png"])

    def test_missing_folder_raises(self) -> None:
        with self.assertRaises(duplicates.ScanError):
            duplicates.scan(str(self.root / "нет-такой"))
        with self.assertRaises(duplicates.ScanError):
            duplicates.scan("")

    def test_remove_keeps_one_copy_and_undo_restores(self) -> None:
        first = self.write("a.txt", b"hello" * 500)
        second = self.write("b.txt", b"hello" * 500)
        third = self.write("c.txt", b"hello" * 500)
        duplicates.scan(str(self.root), min_size=1)

        result = duplicates.remove(str(self.root), [str(second), str(third)])

        self.assertEqual(result["removed_count"], 2)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["a.txt"])
        self.assertTrue(first.is_file())
        self.assertIsNotNone(duplicates.last_run())

        restored = duplicates.undo(result["run_id"])

        self.assertEqual(restored["restored_count"], 2)
        self.assertEqual(
            sorted(p.name for p in self.root.iterdir()),
            ["a.txt", "b.txt", "c.txt"],
        )
        self.assertIsNone(duplicates.last_run())

    def test_cannot_remove_every_copy(self) -> None:
        first = self.write("a.txt", b"same" * 500)
        second = self.write("b.txt", b"same" * 500)
        duplicates.scan(str(self.root), min_size=1)

        with self.assertRaises(duplicates.RemoveError):
            duplicates.remove(str(self.root), [str(first), str(second)])
        self.assertTrue(first.exists() and second.exists())

    def test_remove_rejects_unknown_path(self) -> None:
        pics = self.root / "pics"
        self.write("pics/a.txt", b"same" * 500)
        self.write("pics/b.txt", b"same" * 500)
        outside = self.write("outside.txt", b"same" * 500)
        duplicates.scan(str(pics), min_size=1)

        with self.assertRaises(duplicates.RemoveError):
            duplicates.remove(str(pics), [str(outside)])

    def test_remove_without_scan_raises(self) -> None:
        path = self.write("a.txt", b"x" * 2000)
        with self.assertRaises(duplicates.RemoveError):
            duplicates.remove(str(self.root), [str(path)])

    def test_thumb_allowlist_follows_last_scan(self) -> None:
        pics = self.root / "pics"
        first = self.write("pics/a.png", b"png" * 100)
        self.write("pics/b.png", b"png" * 100)
        outside = self.write("outside.png", b"png" * 100)
        duplicates.scan(str(pics), min_size=1)

        self.assertTrue(duplicates.allowed_path(str(first)))
        self.assertFalse(duplicates.allowed_path(str(outside)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
