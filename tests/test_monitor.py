"""Мониторинг ПК: проценты, защита процессов и снимок."""

import sys
import unittest
from pathlib import Path
from threading import RLock
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools import monitor


class PercentTestCase(unittest.TestCase):
    def test_system_cpu_uses_idle_time_and_keeps_idle_as_zero(self):
        self.assertEqual(monitor._cpu_percent((100, 50), (200, 100)), 50.0)
        self.assertEqual(monitor._cpu_percent((100, 50), (200, 150)), 0.0)
        self.assertIsNone(monitor._cpu_percent((100, 50), (110, 70)))

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
        self.assertIn("вне твоей сессии", reason)

    def test_failed_session_lookup_is_refused(self):
        self.assertTrue(monitor._refuse_reason({"pid": 700, "name": "game.exe", "session": -1}, 4242, -1))

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
    def test_snapshot_has_system_and_processes(self):
        data = monitor.snapshot()
        self.assertTrue(data["ready"])
        self.assertGreater(data["system"]["cores"], 0)
        self.assertGreater(data["system"]["memory"]["total"], 0)
        self.assertGreater(data["system"]["disk"]["total"], 0)
        self.assertIsInstance(data["processes"], list)
        entry = data["processes"][0]
        for key in ("pid", "name", "cpu", "memory", "created", "creation", "started", "session", "can_stop",
                    "can_minimize", "why_not"):
            self.assertIn(key, entry)
        self.assertTrue(entry["creation"].isdigit())
        self.assertLessEqual(len(data["processes"]), monitor.MAX_PROCESSES)
        self.assertTrue(any(item["can_stop"] for item in data["processes"]))


class ActionTestCase(unittest.TestCase):
    pid = 987_654
    identity = ("game.exe", 1.0, "10200001")

    def setUp(self):
        name, created, creation = self.identity
        self.info = {"pid": self.pid, "name": name, "created": created, "creation": creation, "session": 1}
        self.kernel32 = Mock()
        self.kernel32.WaitForSingleObject.return_value = monitor.WAIT_TIMEOUT
        self.user32 = Mock()
        libs = {"kernel32": self.kernel32, "user32": self.user32, "dwmapi": Mock(), "enum_callback": lambda fn: fn}
        self.libs = libs
        self.allowed = {self.pid: self.identity}
        for mocked in (
            patch.object(monitor, "_state", {"lock": RLock(), "allowed": self.allowed}),
            patch.object(monitor, "_libs", return_value=libs),
            patch.object(monitor, "_process_info", return_value=self.info),
            patch.object(monitor, "_session", return_value=1),
        ):
            mocked.start()
            self.addCleanup(mocked.stop)

    def test_terminate_rejects_unknown_pid(self):
        with self.assertRaises(monitor.MonitorError):
            monitor.terminate(999_999_999)

    def test_terminate_rejects_a_changed_process(self):
        self.info["creation"] = "10200002"
        with self.assertRaises(monitor.MonitorError):
            monitor.terminate(self.pid)
        self.kernel32.TerminateProcess.assert_not_called()

    def test_terminate_refuses_a_protected_process(self):
        self.info["name"] = "explorer.exe"
        self.allowed[self.pid] = monitor._process_identity(self.info)
        with self.assertRaises(monitor.MonitorError):
            monitor.terminate(self.pid)
        self.kernel32.TerminateProcess.assert_not_called()

    def test_minimize_rejects_stale_user_selection(self):
        with self.assertRaises(monitor.MonitorError):
            monitor.minimize(self.pid, self.info["name"], "10200002")
        self.kernel32.OpenProcess.assert_not_called()

    def test_minimize_rejects_changed_inaccessible_and_other_session_processes(self):
        for info in (None, {**self.info, "creation": "10200002"}, {**self.info, "session": 2}):
            with self.subTest(info=info), patch.object(monitor, "_process_info", return_value=info):
                with self.assertRaises(monitor.MonitorError):
                    monitor.minimize(self.pid, self.info["name"], self.info["creation"])
        self.user32.EnumWindows.assert_not_called()
        self.user32.ShowWindowAsync.assert_not_called()

    def test_minimize_rechecks_visible_windows_and_process_lifetime(self):
        self.user32.IsWindowVisible.side_effect = lambda window: window != 2
        self.user32.IsIconic.side_effect = lambda window: window == 3
        self.user32.GetAncestor.side_effect = lambda window, _: 1 if window == 4 else window
        self.user32.EnumWindows.side_effect = lambda callback, param: all(callback(i, param) for i in range(1, 11))

        def cloak(window, _attribute, out, _size):
            out._obj.value = 1 if window == 5 else 0
            return -1 if window == 6 else 0

        def owner(window, out):
            calls[window] = calls.get(window, 0) + 1
            out._obj.value = 700 if window == 7 or (window == 8 and calls[window] > 1) else self.pid
            return 77

        calls = {}
        self.libs["dwmapi"].DwmGetWindowAttribute.side_effect = cloak
        self.user32.GetWindowThreadProcessId.side_effect = owner
        self.kernel32.WaitForSingleObject.side_effect = [monitor.WAIT_TIMEOUT, monitor.WAIT_TIMEOUT, 0]
        self.user32.ShowWindowAsync.side_effect = lambda window, _: window == 1
        result = monitor.minimize(self.pid, self.info["name"], self.info["creation"])
        self.assertEqual(result["requested"], 1)
        self.assertEqual([call.args for call in self.user32.ShowWindowAsync.call_args_list],
                         [(1, monitor.SW_MINIMIZE), (9, monitor.SW_MINIMIZE)])
        self.kernel32.CloseHandle.assert_called_once()


if __name__ == "__main__":
    unittest.main()
