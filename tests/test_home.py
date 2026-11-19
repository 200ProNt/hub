"""Тесты сводки главной страницы (дашборда)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server


class HomeSummaryTestCase(unittest.TestCase):
    def test_summary_structure(self):
        summary = server.home_summary()
        self.assertIn("vitals", summary)
        self.assertIn("todos", summary)
        self.assertIn("recent_clips", summary)
        self.assertIn("stats", summary)
        self.assertIn("version", summary)
        self.assertEqual(summary["version"], server.VERSION)
        self.assertEqual(summary["version"], "1.3.1")

    def test_stats_fields(self):
        summary = server.home_summary()
        stats = summary["stats"]
        self.assertIn("notes_count", stats)
        self.assertIn("clipboard_count", stats)
        self.assertIn("trash_count", stats)
        self.assertIn("trash_size", stats)
        self.assertIsInstance(stats["notes_count"], int)
        self.assertIsInstance(stats["clipboard_count"], int)

    def test_todos_format(self):
        summary = server.home_summary()
        self.assertIsInstance(summary["todos"], list)
        for todo in summary["todos"]:
            self.assertIn("note_id", todo)
            self.assertIn("note_title", todo)
            self.assertIn("line_idx", todo)
            self.assertIn("text", todo)
