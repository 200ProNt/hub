"""Тесты создания и удаления ярлыков Windows."""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import shortcuts


class ShortcutsTests(unittest.TestCase):
    def test_status_returns_dict(self):
        st = shortcuts.status()
        self.assertIsInstance(st, dict)
        self.assertIn("supported", st)
        self.assertIn("desktop", st)
        self.assertIn("start_menu", st)

    def test_get_shortcut_path(self):
        desktop_path = shortcuts.get_shortcut_path("desktop")
        self.assertTrue(str(desktop_path).endswith("Hub.lnk"))

        start_path = shortcuts.get_shortcut_path("start_menu")
        self.assertTrue(str(start_path).endswith("Hub.lnk"))

    @patch("subprocess.run")
    @patch.object(shortcuts.ctypes, "windll", create=True)
    def test_create_calls_powershell(self, mock_windll, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        with (tempfile.TemporaryDirectory() as directory,
              patch.object(shortcuts, "supported", return_value=True),
              patch("subprocess.CREATE_NO_WINDOW", 0, create=True)):
            link = Path(directory) / "Hub.lnk"
            with patch.object(shortcuts, "get_shortcut_path", return_value=link):
                shortcuts.create("desktop")
            args = mock_run.call_args[0][0]
            self.assertEqual(args[0], "powershell")
            self.assertIn("CreateShortcut", args[4])
            self.assertIn(f"$s.IconLocation = '{shortcuts.paths.ICON.resolve()},0'", args[4])
            mock_windll.shell32.SHChangeNotify.assert_called_once_with(0x2000, 0x0005, str(link), None)

            executable = Path(directory) / "Hub.exe"
            icon = shortcuts.paths.ICON.read_bytes()
            icon_hash = hashlib.sha256(icon).hexdigest()[:12]
            installed = executable.with_name(f"Hub-{icon_hash}.ico")
            installed.write_bytes(icon)
            with (patch.object(shortcuts.paths, "DESKTOP_EXE", executable),
                  patch.object(shortcuts, "get_shortcut_path", return_value=link)):
                shortcuts.create("desktop")
            self.assertIn(f"$s.IconLocation = '{installed.resolve()},0'", mock_run.call_args[0][0][4])

    @patch("pathlib.Path.unlink")
    @patch("pathlib.Path.is_file", return_value=True)
    def test_remove_unlinks_file(self, mock_is_file, mock_unlink):
        with patch.object(shortcuts, "supported", return_value=True):
            shortcuts.remove("desktop")
            self.assertTrue(mock_unlink.called)


if __name__ == "__main__":
    unittest.main()
