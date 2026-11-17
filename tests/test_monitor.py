"""Мониторинг ПК: проценты, защита процессов и снимок."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools import monitor


class PercentTestCase(unittest.TestCase):
    def test_share_of_all_cores(self):
        self.assertEqual(monitor._percent(1.0, 1.0, 4), 25.0)
        self.assertEqual(monitor._percent(2.0, 1.0, 4), 50.0)

    def test_is_clamped_to_a_hundred(self):
        self.assertEqual(monitor._percent(9.0, 1.0, 2), 100.0)

    def test_empty_span_or_negative_delta_is_zero(self):
        self.assertEqual(monitor._percent(1.0, 0.0, 4), 0.0)
        self.assertEqual(monitor._percent(-1.0, 1.0, 4), 0.0)
        self.assertEqual(monitor._percent(1.0, 1.0, 0), 0.0)


class ProtectTestCase(unittest.TestCase):
    def test_protected_names_ignore_case_and_spaces(self):
        self.assertTrue(monitor._protected(" explorer.exe "))
        self.assertTrue(monitor._protected("SVCHOST.EXE"))
        self.assertFalse(monitor._protected("chrome.exe"))
        self.assertFalse(monitor._protected(""))

    def test_system_and_own_processes_are_refused(self):
        own = 4242
        self.assertIn("системный", monitor._refuse_reason({"pid": 4, "name": "System"}, own, 1))
        self.assertIn("хаб", monitor._refuse_reason({"pid": own, "name": "python.exe"}, own, 1))

    def test_protected_name_is_refused(self):
        reason = monitor._refuse_reason({"pid": 700, "name": "lsass.exe", "session": 1}, 4242, 1)
        self.assertIn("защищён", reason)

    def test_foreign_session_is_refused(self):
        reason = monitor._refuse_reason({"pid": 700, "name": "game.exe", "session": 0}, 4242, 1)
        self.assertIn("системы", reason)

    def test_user_process_is_allowed(self):
        self.assertEqual(monitor._refuse_reason({"pid": 700, "name": "game.exe", "session": 1}, 4242, 1), "")


class SortTestCase(unittest.TestCase):
    def test_cpu_then_memory_then_name(self):
        entries = [
            {"name": "b.exe", "cpu": 5.0, "memory": 10},
            {"name": "a.exe", "cpu": 5.0, "memory": 20},
            {"name": "c.exe", "cpu": 9.0, "memory": 1},
            {"name": "d.exe", "cpu": 5.0, "memory": 20},
        ]
        names = [item["name"] for item in monitor._sort_processes(entries)]
        self.assertEqual(names, ["c.exe", "a.exe", "d.exe", "b.exe"])


@unittest.skipUnless(sys.platform == "win32", "WinAPI нужен только на Windows")
class SnapshotTestCase(unittest.TestCase):
    def setUp(self):
        with monitor._state["lock"]:
            monitor._state["allowed"] = {}

    def test_snapshot_has_system_and_processes(self):
        data = monitor.snapshot()
        self.assertTrue(data["ready"])
        self.assertGreater(data["system"]["cores"], 0)
        self.assertGreater(data["system"]["memory"]["total"], 0)
        self.assertGreater(data["system"]["disk"]["total"], 0)
        self.assertIsInstance(data["processes"], list)
        entry = data["processes"][0]
        for key in ("pid", "name", "cpu", "memory", "created", "started", "session", "can_stop", "why_not"):
            self.assertIn(key, entry)
        self.assertLessEqual(len(data["processes"]), monitor.MAX_PROCESSES)
        self.assertTrue(any(item["can_stop"] for item in data["processes"]))

    def test_terminate_rejects_unknown_pid(self):
        with self.assertRaises(monitor.MonitorError):
            monitor.terminate(999_999_999)

    def test_terminate_rejects_a_changed_process(self):
        with monitor._state["lock"]:
            monitor._state["allowed"][987_654] = ("old.exe", 1.0)
        info = {"pid": 987_654, "name": "new.exe", "created": 2.0, "session": 1}
        with patch.object(monitor, "_process_info", return_value=info):
            with self.assertRaises(monitor.MonitorError):
                monitor.terminate(987_654)
        with monitor._state["lock"]:
            monitor._state["allowed"].pop(987_654, None)

    def test_terminate_refuses_a_protected_process(self):
        with monitor._state["lock"]:
            monitor._state["allowed"][987_655] = ("explorer.exe", 5.0)
        info = {"pid": 987_655, "name": "explorer.exe", "created": 5.0, "session": 1}
        with patch.object(monitor, "_process_info", return_value=info):
            with self.assertRaises(monitor.MonitorError):
                monitor.terminate(987_655)
        with monitor._state["lock"]:
            monitor._state["allowed"].pop(987_655, None)


if __name__ == "__main__":
    unittest.main()
