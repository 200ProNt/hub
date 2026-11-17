"""Общий поиск: инструменты, заметки и буфер — чистая логика, без сервера."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools import search

TOOLS = [
    {"id": "clipboard", "name": "Буфер обмена", "hint": "Всё, что копировал, — под рукой", "icon": "clipboard"},
    {"id": "notes", "name": "Заметки", "hint": "Быстрые записи на этом компьютере", "icon": "note"},
    {"id": "trash", "name": "Корзина", "hint": "Что можно вернуть на место", "icon": "undo"},
]


class SearchTestCase(unittest.TestCase):
    def test_empty_query_returns_nothing(self):
        result = search.run("   ", TOOLS, [], [])
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["query"], "")

    def test_tools_match_by_name_and_hint(self):
        by_name = search.run("корз", tools=TOOLS)
        self.assertEqual([tool["id"] for tool in by_name["tools"]], ["trash"])
        by_hint = search.run("вернуть", tools=TOOLS)
        self.assertEqual([tool["id"] for tool in by_hint["tools"]], ["trash"])

    def test_notes_match_title_and_text(self):
        notes = [
            {"id": "n1", "title": "Список покупок", "text": "молоко, хлеб", "updated": 5},
            {"id": "n2", "title": "", "text": "купить корм коту", "updated": 9},
        ]
        result = search.run("корм", notes_items=notes)
        self.assertEqual([note["id"] for note in result["notes"]], ["n2"])
        self.assertIn("корм", result["notes"][0]["snippet"])
        self.assertEqual(result["notes"][0]["title"], "купить корм коту")

    def test_clipboard_hits_carry_a_short_snippet(self):
        items = [{"id": "c1", "text": "длинный текст " * 40 + "иголка" + " хвост " * 40, "time": 1.0}]
        result = search.run("иголка", clipboard_items=items)
        snippet = result["clipboard"][0]["snippet"]
        self.assertIn("иголка", snippet)
        self.assertTrue(snippet.startswith("…"))
        self.assertTrue(snippet.endswith("…"))
        self.assertLess(len(snippet), 200)

    def test_results_are_capped_per_group(self):
        notes = [{"id": f"n{index}", "title": "общее", "text": "общее", "updated": index} for index in range(20)]
        result = search.run("общее", notes_items=notes, limit=3)
        self.assertEqual(len(result["notes"]), 3)
        self.assertEqual(result["total"], 3)

    def test_snippet_keeps_the_start_when_nothing_matches(self):
        self.assertEqual(search.snippet("короткий текст", "нет"), "короткий текст")


if __name__ == "__main__":
    unittest.main()
