"""Тесты для модуля интеграции с системным треем и хоткеями."""

import unittest
from unittest.mock import patch

from tools import tray


class TestTray(unittest.TestCase):
    def test_is_supported(self):
        supported = tray.is_supported()
        self.assertIsInstance(supported, bool)

    def test_status(self):
        st = tray.status()
        self.assertIn("supported", st)
        self.assertIn("running", st)
        self.assertIn("hotkeys", st)
        self.assertIsInstance(st["hotkeys"], list)
        self.assertGreater(len(st["hotkeys"]), 0)
        self.assertIn("Ctrl+Alt+H", st["hotkeys"])

    @patch("tools.tray.is_supported", return_value=False)
    def test_start_unsupported(self, _):
        res = tray.start_tray(9999)
        self.assertFalse(res)


if __name__ == "__main__":
    unittest.main()
