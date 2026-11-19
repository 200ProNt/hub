"""Заметки: хранение, поиск, закрепление и защита от пустых записей."""

from pathlib import Path
import json
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools import notes


class NotesTestCase(unittest.TestCase):
    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)
        self.store = notes.NotesStore(self.root / "notes.json")

    def tearDown(self):
        self._temporary.cleanup()

    def test_create_and_list_newest_first(self):
        first = self.store.create("Список", "молоко\nхлеб")
        second = self.store.create("Идея", "сделать хаб")
        listing = self.store.listing()
        self.assertEqual([item["id"] for item in listing], [second["id"], first["id"]])
        self.assertEqual(listing[1]["text"], "молоко\nхлеб")
        self.assertEqual(listing[1]["chars"], len("молоко\nхлеб"))

    def test_empty_note_is_rejected(self):
        with self.assertRaises(notes.NoteError):
            self.store.create("   ", "  \n ")
        self.assertEqual(self.store.count(), 0)

    def test_pinned_notes_float_to_top(self):
        old = self.store.create("Старая", "текст")
        self.store.create("Новая", "текст")
        self.store.toggle_pin(old["id"])
        self.assertEqual(self.store.listing()[0]["id"], old["id"])

    def test_search_matches_title_and_text(self):
        self.store.create("Покупки", "молоко")
        self.store.create("Дела", "позвонить в школу")
        self.assertEqual(len(self.store.listing("МОЛОКО")), 1)
        self.assertEqual(self.store.listing("школ")[0]["title"], "Дела")
        self.assertEqual(self.store.listing("нет такого"), [])

    def test_update_changes_text_and_keeps_position(self):
        note = self.store.create("Черновик", "старый текст")
        updated = self.store.update(note["id"], "Готово", "новый текст")
        self.assertEqual(updated["title"], "Готово")
        self.assertEqual(self.store.get(note["id"])["text"], "новый текст")
        self.assertGreaterEqual(updated["updated"], note["updated"])

    def test_unknown_note_raises_or_returns_false(self):
        with self.assertRaises(notes.NoteError):
            self.store.update("нет", "a", "b")
        with self.assertRaises(notes.NoteError):
            self.store.toggle_pin("нет")
        self.assertFalse(self.store.delete("нет"))

    def test_notes_survive_reload(self):
        note = self.store.create("Живая", "переживает перезапуск")
        self.store.toggle_pin(note["id"])
        again = notes.NotesStore(self.root / "notes.json")
        loaded = again.get(note["id"])
        self.assertEqual(loaded["text"], "переживает перезапуск")
        self.assertTrue(loaded["pinned"])

    def test_broken_file_does_not_crash(self):
        broken = self.root / "notes.json"
        broken.write_text("{ это не json", encoding="utf-8")
        self.assertEqual(notes.NotesStore(broken).listing(), [])

    def test_save_is_atomic_and_leaves_no_temporary_file(self):
        self.store.create("Одна", "запись")
        self.assertTrue((self.root / "notes.json").is_file())
        self.assertFalse((self.root / "notes.tmp").exists())

    def test_long_text_is_cut_to_limit(self):
        note = self.store.create("Длинная", "я" * (notes.MAX_TEXT + 500))
        self.assertEqual(len(note["text"]), notes.MAX_TEXT)

    def test_json_shape_is_stable(self):
        self.store.create("Форма", "поля")
        raw = json.loads((self.root / "notes.json").read_text(encoding="utf-8"))
        self.assertIn("notes", raw)
        self.assertEqual(
            sorted(raw["notes"][0]),
            ["created", "id", "pinned", "text", "title", "updated"],
        )

    def test_export_note_markdown_and_txt(self):
        note = self.store.create("Список дел", "- Купить молоко\n- Позвонить маме")
        filename_md, content_md = self.store.export_note(note["id"], "md")
        self.assertTrue(filename_md.endswith(".md"))
        self.assertIn("# Список дел", content_md)
        self.assertIn("- Купить молоко", content_md)

        filename_txt, content_txt = self.store.export_note(note["id"], "txt")
        self.assertTrue(filename_txt.endswith(".txt"))
        self.assertIn("Список дел", content_txt)
        self.assertIn("- Позвонить маме", content_txt)

    def test_export_all_notes(self):
        self.store.create("Заметка 1", "Текст 1")
        self.store.create("Заметка 2", "Текст 2")
        filename_all, content_all = self.store.export_all("md")
        self.assertTrue(filename_all.endswith(".md"))
        self.assertIn("Заметка 1", content_all)
        self.assertIn("Заметка 2", content_all)

    def test_tags_extraction(self):
        note = self.store.create("План на день #работа", "Нужно сделать задачу #hub и купить кофе #еда")
        listed = self.store.listing()
        found = next(item for item in listed if item["id"] == note["id"])
        self.assertEqual(sorted(found["tags"]), ["hub", "еда", "работа"])


if __name__ == "__main__":
    unittest.main()
