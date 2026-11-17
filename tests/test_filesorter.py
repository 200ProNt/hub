"""Тесты логики сортировки файлов: планирование, перенос, отмена."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_runs_tmp = tempfile.TemporaryDirectory()
os.environ["HUB_RUNS_DIR"] = _runs_tmp.name

from tools import filesorter as sorter  # noqa: E402


def tearDownModule() -> None:
    _runs_tmp.cleanup()


class SorterTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def make_file(self, name: str, content: bytes = b"x") -> Path:
        path = self.root / name
        path.write_bytes(content)
        return path

    def test_category_by_extension(self) -> None:
        self.assertEqual(sorter.category_for("photo.JPG"), "Изображения")
        self.assertEqual(sorter.category_for("movie.mkv"), "Видео")
        self.assertEqual(sorter.category_for("song.flac"), "Музыка")
        self.assertEqual(sorter.category_for("report.docx"), "Документы")
        self.assertEqual(sorter.category_for("backup.7z"), "Архивы")
        self.assertEqual(sorter.category_for("setup.exe"), "Программы")
        self.assertEqual(sorter.category_for("main.py"), "Код")
        self.assertEqual(sorter.category_for("README"), "Другое")
        self.assertEqual(sorter.category_for("weird.xyz"), "Другое")

    def test_scan_builds_plan_without_moving(self) -> None:
        self.make_file("a.jpg", b"12345")
        self.make_file("b.pdf")
        self.make_file("notes.txt")
        (self.root / "sub").mkdir()

        plan = sorter.scan(str(self.root))

        self.assertEqual(plan["total"], 3)
        self.assertEqual(plan["counts"], {"Изображения": 1, "Документы": 2})
        self.assertTrue((self.root / "a.jpg").exists(), "scan не должен ничего двигать")
        destinations = {item["name"]: item["dest_rel"] for item in plan["items"]}
        self.assertEqual(destinations["a.jpg"], "Изображения/a.jpg")
        self.assertEqual(destinations["b.pdf"], "Документы/b.pdf")

    def test_scan_uses_free_name_for_existing_target(self) -> None:
        self.make_file("photo.png")
        target_dir = self.root / "Изображения"
        target_dir.mkdir()
        (target_dir / "photo.png").write_bytes(b"old")

        plan = sorter.scan(str(self.root))
        item = next(entry for entry in plan["items"] if entry["name"] == "photo.png")

        self.assertEqual(item["dest_rel"], "Изображения/photo (1).png")
        self.assertTrue(item["renamed"])

    def test_scan_skips_hidden_and_category_folders(self) -> None:
        self.make_file("visible.mp3")
        hidden = self.root / ".secret.txt"
        hidden.write_text("no", encoding="utf-8")
        (self.root / "Изображения").mkdir()
        (self.root / "Изображения" / "inside.jpg").write_bytes(b"1")

        plan = sorter.scan(str(self.root))

        self.assertEqual([item["name"] for item in plan["items"]], ["visible.mp3"])

    def test_apply_moves_only_selected(self) -> None:
        self.make_file("one.jpg")
        self.make_file("two.pdf")

        plan = sorter.scan(str(self.root))
        chosen = [item["path"] for item in plan["items"] if item["name"] == "one.jpg"]
        result = sorter.apply(str(self.root), chosen)

        self.assertEqual(result["moved_count"], 1)
        self.assertTrue((self.root / "Изображения" / "one.jpg").exists())
        self.assertTrue((self.root / "two.pdf").exists(), "невыбранный файл должен остаться")
        self.assertIsNotNone(result["run_id"])

    def test_apply_rejects_file_outside_folder(self) -> None:
        outside = self.root.parent / "outside_file.txt"
        outside.write_text("outside", encoding="utf-8")
        try:
            result = sorter.apply(str(self.root), [str(outside)])
            self.assertEqual(result["moved_count"], 0)
            self.assertEqual(len(result["errors"]), 1)
            self.assertTrue(outside.exists())
        finally:
            outside.unlink(missing_ok=True)

    def test_undo_returns_everything(self) -> None:
        self.make_file("clip.mp4", b"video-bytes")
        self.make_file("doc.pdf", b"pdf-bytes")

        plan = sorter.scan(str(self.root))
        result = sorter.apply(str(self.root), [item["path"] for item in plan["items"]])
        self.assertEqual(result["moved_count"], 2)

        undo_result = sorter.undo(result["run_id"])

        self.assertEqual(undo_result["restored_count"], 2)
        self.assertTrue((self.root / "clip.mp4").exists())
        self.assertTrue((self.root / "doc.pdf").exists())
        for category in ("Документы", "Видео"):
            folder = self.root / category
            self.assertFalse(folder.exists() and any(folder.iterdir()), "пустая папка категории должна исчезнуть")
        self.assertFalse((self.root / "Видео" / "clip.mp4").exists())

    def test_undo_twice_is_refused(self) -> None:
        self.make_file("a.png")
        plan = sorter.scan(str(self.root))
        result = sorter.apply(str(self.root), [item["path"] for item in plan["items"]])

        sorter.undo(result["run_id"])
        with self.assertRaises(ValueError):
            sorter.undo(result["run_id"])

    def test_last_run_reflects_latest_move(self) -> None:
        before = sorter.last_run()
        self.make_file("fresh.jpg")
        plan = sorter.scan(str(self.root))
        result = sorter.apply(str(self.root), [item["path"] for item in plan["items"]])

        latest = sorter.last_run()
        self.assertIsNotNone(latest)
        self.assertEqual(latest["run_id"], result["run_id"])
        self.assertEqual(latest["count"], 1)
        if before:
            self.assertNotEqual(latest["run_id"], before["run_id"])

    def test_journal_is_written_and_readable(self) -> None:
        self.make_file("data.csv")
        plan = sorter.scan(str(self.root))
        result = sorter.apply(str(self.root), [item["path"] for item in plan["items"]])

        journal = sorter._runs_dir() / f"{result['run_id']}.json"  # noqa: SLF001
        payload = json.loads(journal.read_text(encoding="utf-8"))

        self.assertFalse(payload["undone"])
        self.assertEqual(payload["moved"][0]["name"], "data.csv")


if __name__ == "__main__":
    unittest.main(verbosity=2)
