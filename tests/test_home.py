"""Тесты сводки главной страницы (дашборда)."""

import sys
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server


class HomeSummaryTestCase(unittest.TestCase):
    def test_summary_exposes_sampler_usage(self):
        sample = {"ready": True, "system": {"cpu": 17, "memory": {"total": 8 * 1024**3,
                  "used": 2 * 1024**3, "percent": 25}}}
        with patch.object(server.monitor, "snapshot", return_value=sample):
            vitals = server.home_summary()["vitals"]
        self.assertEqual((vitals["cpu_percent"], vitals["memory_percent"]), (17, 25))

    def test_summary_structure(self):
        summary = server.home_summary()
        self.assertIn("vitals", summary)
        self.assertIn("todos", summary)
        self.assertIn("recent_clips", summary)
        self.assertIn("stats", summary)
        self.assertIn("version", summary)
        self.assertEqual(summary["version"], server.VERSION)

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
