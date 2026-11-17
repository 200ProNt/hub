"""Автозапуск: запись в HKCU\\...\\Run, проверяется на поддельном реестре."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools import autostart


class FakeKey:
    def __init__(self, values):
        self.values = values

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class FakeRegistry:
    HKEY_CURRENT_USER = "HKCU"
    KEY_READ = 1
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self):
        self.values = {}
        self.paths = []

    def OpenKey(self, root, path, reserved, access):
        self.paths.append((root, path, access))
        if root != self.HKEY_CURRENT_USER or path != autostart.RUN_KEY:
            raise FileNotFoundError(path)
        return FakeKey(self.values)

    def CreateKeyEx(self, root, path, reserved, access):
        if root != self.HKEY_CURRENT_USER or path != autostart.RUN_KEY:
            raise OSError("нет доступа")
        return FakeKey(self.values)

    def SetValueEx(self, key, name, reserved, kind, value):
        self.assert_kind = kind
        key.values[name] = value

    def QueryValueEx(self, key, name):
        if name not in key.values:
            raise FileNotFoundError(name)
        return key.values[name], self.REG_SZ

    def DeleteValue(self, key, name):
        if name not in key.values:
            raise FileNotFoundError(name)
        del key.values[name]


class AutostartTestCase(unittest.TestCase):
    def setUp(self):
        self.registry = FakeRegistry()
        self.patches = [
            patch.object(autostart, "_registry", lambda: self.registry),
            patch.object(autostart, "command", lambda script=None, executable=None: '"pyw" "hub.py" --no-browser'),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()

    def test_absent_value_means_disabled(self):
        state = autostart.status()
        self.assertTrue(state["supported"])
        self.assertFalse(state["enabled"])
        self.assertEqual(state["stored"], "")

    def test_enable_writes_the_command_and_disable_removes_it(self):
        state = autostart.set_enabled(True)
        self.assertTrue(state["enabled"])
        self.assertTrue(state["matches"])
        self.assertEqual(self.registry.values["Hub"], '"pyw" "hub.py" --no-browser')

        state = autostart.set_enabled(False)
        self.assertFalse(state["enabled"])
        self.assertEqual(self.registry.values, {})

    def test_disabling_when_nothing_is_set_is_not_an_error(self):
        state = autostart.set_enabled(False)
        self.assertFalse(state["enabled"])

    def test_a_foreign_command_is_shown_as_stale(self):
        self.registry.values["Hub"] = '"old-python.exe" "D:\\old\\server.py"'
        state = autostart.status()
        self.assertTrue(state["enabled"])
        self.assertFalse(state["matches"])
        self.assertEqual(state["stored"], '"old-python.exe" "D:\\old\\server.py"')

    def test_other_platforms_are_reported_as_unsupported(self):
        with patch.object(autostart.sys, "platform", "linux"):
            state = autostart.status()
            self.assertFalse(state["supported"])
            self.assertFalse(state["enabled"])
            with self.assertRaises(autostart.AutostartError):
                autostart.set_enabled(True)


class CommandTestCase(unittest.TestCase):
    def test_command_points_at_the_real_server_and_asks_for_no_browser(self):
        value = autostart.command()
        self.assertIn("server.py", value)
        self.assertTrue(value.endswith("--no-browser"))
        self.assertTrue(value.startswith('"'))

    def test_pythonw_is_preferred_so_no_console_window_appears(self):
        exists = Path(sys.executable).with_name("pythonw.exe").is_file()
        value = autostart.command()
        self.assertIn("pythonw.exe" if exists else "python.exe", value)

    def test_a_missing_pythonw_falls_back_to_the_current_interpreter(self):
        with tempfile.TemporaryDirectory() as temporary:
            plain = Path(temporary) / "hub-python.exe"
            plain.write_bytes(b"")
            with patch.object(autostart.sys, "executable", str(plain)):
                self.assertIn("hub-python.exe", autostart.command())


if __name__ == "__main__":
    unittest.main()
