"""Тесты истории буфера обмена (без обращения к системному буферу)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.clipboard import ClipboardStore  # noqa: E402


class ClipboardStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "clipboard.json"
        self.store = ClipboardStore(self.path, limit=5)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_add_newest_first(self) -> None:
        self.store.add("первый")
        self.store.add("второй")

        texts = [item["text"] for item in self.store.listing()]
        self.assertEqual(texts, ["второй", "первый"])

    def test_duplicate_moves_to_top_without_copy(self) -> None:
        self.store.add("a")
        self.store.add("b")
        self.store.add("a")

        items = self.store.listing()
        self.assertEqual([item["text"] for item in items], ["a", "b"])
        self.assertEqual(self.store.count(), 2)

    def test_empty_text_is_ignored(self) -> None:
        self.assertIsNone(self.store.add("   "))
        self.assertIsNone(self.store.add(""))
        self.assertEqual(self.store.count(), 0)

    def test_limit_drops_oldest(self) -> None:
        for index in range(8):
            self.store.add(f"запись {index}")

        self.assertEqual(self.store.count(), 5)
        texts = [item["text"] for item in self.store.listing()]
        self.assertEqual(texts[0], "запись 7")
        self.assertNotIn("запись 0", texts)

    def test_pinned_survives_limit_and_sorts_first(self) -> None:
        first = self.store.add("важное")
        self.store.toggle_pin(first["id"])
        for index in range(6):
            self.store.add(f"мусор {index}")

        items = self.store.listing()
        self.assertEqual(items[0]["text"], "важное")
        self.assertTrue(items[0]["pinned"])
        self.assertIn("важное", [item["text"] for item in items])

    def test_delete_and_clear(self) -> None:
        entry = self.store.add("удалить меня")
        self.assertTrue(self.store.delete(entry["id"]))
        self.assertFalse(self.store.delete("нет такого"))
        self.assertEqual(self.store.count(), 0)

        self.store.add("раз")
        self.store.add("два")
        self.assertEqual(self.store.clear(), 2)
        self.assertEqual(self.store.count(), 0)

    def test_search_is_case_insensitive(self) -> None:
        self.store.add("Привет Мир")
        self.store.add("другое")

        found = self.store.listing("привет")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["text"], "Привет Мир")

    def test_classification_and_word_count(self) -> None:
        self.store.add("https://github.com/project/repo")
        self.store.add("def hello_world():\n    return 42\n")
        self.store.add("Простой короткий текст для теста")

        items = self.store.listing()
        url_item = next(i for i in items if i["type"] == "url")
        self.assertEqual(url_item["type"], "url")

        code_item = next(i for i in items if i["type"] == "code")
        self.assertEqual(code_item["type"], "code")

        text_item = next(i for i in items if i["type"] == "text")
        self.assertEqual(text_item["words"], 5)

        self.assertEqual(len(self.store.listing(kind="url")), 1)
        self.assertEqual(len(self.store.listing(kind="code")), 1)
        self.assertEqual(len(self.store.listing(kind="text")), 1)

    def test_persists_between_instances(self) -> None:
        self.store.add("сохранись")

        reopened = ClipboardStore(self.path, limit=5)
        self.assertEqual(reopened.count(), 1)
        self.assertEqual(reopened.listing()[0]["text"], "сохранись")

    def test_preview_keeps_lines_and_collapses_spaces(self) -> None:
        entry = self.store.add("первая строка\n\nвторая   строка")
        self.assertIn("первая строка", entry["text"])
        item = self.store.listing()[0]
        self.assertEqual(item["preview"], "первая строка\nвторая строка")
        self.assertIn("вторая строка", item["preview"])

    def test_long_text_is_skipped(self) -> None:
        self.assertIsNone(self.store.add("x" * 20_001))
        self.assertIsNotNone(self.store.add("x" * 100))


if __name__ == "__main__":
    unittest.main(verbosity=2)
