"""О программе: версия, лицензия и папка проекта."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server
from tools.registry import TOOLS


class AboutTestCase(unittest.TestCase):
    def test_says_what_the_program_is(self):
        info = server.about_info()
        self.assertEqual(info["name"], "Hub")
        self.assertEqual(info["version"], server.VERSION)
        self.assertEqual(info["author"], "devrin")
        self.assertEqual(info["license"], "MIT")
        self.assertEqual(info["tools"], len(TOOLS))
        self.assertTrue(info["python"])

    def test_license_file_is_mit(self):
        info = server.about_info()
        self.assertIn("MIT License", info["license_text"])
        self.assertIn("Copyright (c) 2026 devrin", info["license_text"])
        self.assertIn("WITHOUT WARRANTY", info["license_text"])

    def test_source_folder_and_readme_exist(self):
        info = server.about_info()
        self.assertTrue(Path(info["folder"]).is_dir())
        self.assertTrue(Path(info["readme"]).is_file())
        self.assertEqual(Path(info["readme"]).name, "README.md")

    def test_version_is_exposed_to_the_menu(self):
        self.assertRegex(server.VERSION, r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
