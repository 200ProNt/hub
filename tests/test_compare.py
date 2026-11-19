"""Сравнение папок: добавленные, пропавшие и изменённые файлы."""

from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools import compare


class CompareTestCase(unittest.TestCase):
    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)
        self.left = self.root / "left"
        self.right = self.root / "right"
        self.left.mkdir()
        self.right.mkdir()

    def tearDown(self):
        self._temporary.cleanup()

    def write(self, folder: Path, name: str, data: bytes) -> Path:
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_detects_added_removed_and_same(self):
        self.write(self.left, "both.txt", b"same")
        self.write(self.right, "both.txt", b"same")
        self.write(self.left, "only-left.txt", b"old")
        self.write(self.right, "only-right.txt", b"new")
        result = compare.compare(str(self.left), str(self.right))
        self.assertEqual([item["path"] for item in result["added"]], ["only-right.txt"])
        self.assertEqual([item["path"] for item in result["removed"]], ["only-left.txt"])
        self.assertEqual(result["counts"], {"added": 1, "removed": 1, "changed": 0, "same": 1})

    def test_size_change_is_reported(self):
        self.write(self.left, "a.txt", b"one")
        self.write(self.right, "a.txt", b"longer text")
        result = compare.compare(str(self.left), str(self.right))
        self.assertEqual(result["changed"][0]["reason"], "size")
        self.assertEqual(result["changed"][0]["left_size"], 3)
        self.assertEqual(result["changed"][0]["right_size"], 11)

    def test_same_size_change_needs_deep_mode(self):
        self.write(self.left, "a.txt", b"aaaa")
        self.write(self.right, "a.txt", b"bbbb")
        shallow = compare.compare(str(self.left), str(self.right))
        self.assertEqual(shallow["counts"]["changed"], 0)
        deep = compare.compare(str(self.left), str(self.right), deep=True)
        self.assertEqual(deep["counts"]["changed"], 1)
        self.assertEqual(deep["changed"][0]["reason"], "content")

    def test_folder_versus_file_is_type_change(self):
        (self.left / "node").mkdir()
        self.write(self.right, "node", b"file")
        result = compare.compare(str(self.left), str(self.right))
        self.assertEqual(result["changed"][0]["reason"], "type")

    def test_nested_paths_keep_relative_names(self):
        self.write(self.left, "sub/inner/file.txt", b"xxx")
        self.write(self.right, "sub/inner/file.txt", b"yyyy")
        result = compare.compare(str(self.left), str(self.right))
        self.assertEqual(result["changed"][0]["path"], str(Path("sub/inner/file.txt")))
        self.assertEqual(result["counts"]["same"], 2)

    def test_sizes_are_summed(self):
        self.write(self.left, "a.bin", b"1" * 10)
        self.write(self.right, "b.bin", b"2" * 25)
        result = compare.compare(str(self.left), str(self.right))
        self.assertEqual(result["added_size"], 25)
        self.assertEqual(result["removed_size"], 10)

    def test_bad_paths_are_rejected(self):
        with self.assertRaises(compare.CompareError):
            compare.compare("", str(self.right))
        with self.assertRaises(compare.CompareError):
            compare.compare(str(self.left), str(self.root / "нет-такой"))
        with self.assertRaises(compare.CompareError):
            compare.compare(str(self.left), str(self.left))
        file_path = self.write(self.root, "file.txt", b"x")
        with self.assertRaises(compare.CompareError):
            compare.compare(str(file_path), str(self.right))

    def test_identical_folders_report_no_differences(self):
        for folder in (self.left, self.right):
            self.write(folder, "a.txt", b"one")
            self.write(folder, "nested/b.txt", b"two")
        result = compare.compare(str(self.left), str(self.right), deep=True)
        self.assertEqual(result["counts"], {"added": 0, "removed": 0, "changed": 0, "same": 3})

    def test_sync_entry_copies_file_and_creates_parents(self):
        src_file = self.write(self.left, "nested/doc.txt", b"sync content")
        rel = "nested/doc.txt"
        res = compare.sync_entry(str(self.left), str(self.right), rel)
        self.assertTrue(res["ok"])
        self.assertEqual(res["kind"], "file")
        target_file = self.right / "nested" / "doc.txt"
        self.assertTrue(target_file.is_file())
        self.assertEqual(target_file.read_bytes(), b"sync content")

    def test_sync_entry_rejects_unsafe_paths(self):
        with self.assertRaises(compare.CompareError):
            compare.sync_entry(str(self.left), str(self.right), "../outside.txt")
        with self.assertRaises(compare.CompareError):
            compare.sync_entry(str(self.left), str(self.right), "")



if __name__ == "__main__":
    unittest.main()
