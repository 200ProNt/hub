"""Тесты для модуля пакетного переименования файлов."""

import tempfile
import unittest
from pathlib import Path

from tools import renamer


class TestRenamer(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp_dir.name)
        (self.folder / "photo_01.jpg").write_text("1", encoding="utf-8")
        (self.folder / "photo_02.jpg").write_text("2", encoding="utf-8")
        (self.folder / "report.txt").write_text("3", encoding="utf-8")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_scan(self):
        res = renamer.scan(str(self.folder))
        self.assertEqual(res["count"], 3)
        names = [f["name"] for f in res["files"]]
        self.assertIn("photo_01.jpg", names)
        self.assertIn("report.txt", names)

    def test_preview_replace(self):
        scan_res = renamer.scan(str(self.folder), filter_pattern="*.jpg")
        prev = renamer.preview(str(self.folder), scan_res["files"], {"mode": "replace", "find": "photo", "replace": "vacation"})
        self.assertEqual(prev["ready_count"], 2)
        new_names = [p["new_name"] for p in prev["preview"]]
        self.assertIn("vacation_01.jpg", new_names)
        self.assertIn("vacation_02.jpg", new_names)

    def test_preview_number(self):
        scan_res = renamer.scan(str(self.folder), filter_pattern="*.jpg")
        prev = renamer.preview(str(self.folder), scan_res["files"], {"mode": "number", "prefix": "pic_", "start": 10, "digits": 3})
        self.assertEqual(prev["ready_count"], 2)
        new_names = [p["new_name"] for p in prev["preview"]]
        self.assertEqual(new_names, ["pic_010.jpg", "pic_011.jpg"])

    def test_preview_translit(self):
        (self.folder / "документ.pdf").write_text("4", encoding="utf-8")
        scan_res = renamer.scan(str(self.folder), filter_pattern="*.pdf")
        prev = renamer.preview(str(self.folder), scan_res["files"], {"mode": "translit"})
        self.assertEqual(prev["ready_count"], 1)
        self.assertEqual(prev["preview"][0]["new_name"], "dokument.pdf")

    def test_apply_and_undo(self):
        scan_res = renamer.scan(str(self.folder), filter_pattern="*.jpg")
        prev = renamer.preview(str(self.folder), scan_res["files"], {"mode": "replace", "find": "photo_", "replace": "img_"})
        apply_res = renamer.apply(str(self.folder), prev["preview"])
        self.assertEqual(apply_res["renamed_count"], 2)

        # Проверяем, что файлы действительно переименовались
        self.assertTrue((self.folder / "img_01.jpg").exists())
        self.assertTrue((self.folder / "img_02.jpg").exists())
        self.assertFalse((self.folder / "photo_01.jpg").exists())

        # Проверяем отмену
        undo_res = renamer.undo(apply_res["run_id"])
        self.assertEqual(undo_res["restored_count"], 2)
        self.assertTrue((self.folder / "photo_01.jpg").exists())
        self.assertTrue((self.folder / "photo_02.jpg").exists())
        self.assertFalse((self.folder / "img_01.jpg").exists())


if __name__ == "__main__":
    unittest.main()
