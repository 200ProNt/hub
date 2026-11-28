import io
import os
import subprocess
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools import app_manager, paths


class PackageTests(unittest.TestCase):
    def test_read_handles_double_spaces_unicode_and_optional_source_column(self):
        # The CJK character takes two display cells. The other values start at the header offsets.
        data = ("Name            Id                 Version  Available\n"
                "----------------------------------------------------\n"
                "图  Editor      Example.Editor     1.0      1.1\n"
                "Text editor     Legacy.App         5        \n")
        with patch.object(app_manager, "_read", return_value=SimpleNamespace(returncode=0, stdout=data.encode())):
            newer, unchanged = app_manager.packages()
        self.assertEqual(newer, app_manager.Package("图  Editor", "Example.Editor", "1.0", "1.1", "winget"))
        self.assertTrue(app_manager.can_run("upgrade", newer))
        self.assertFalse(app_manager.can_run("upgrade", unchanged))
        self.assertTrue(app_manager.can_run("uninstall", unchanged))

    def test_search_fails_closed_for_unexpected_output(self):
        with patch.object(app_manager, "_read", return_value=SimpleNamespace(returncode=0, stdout=b"unexpected")):
            with self.assertRaisesRegex(app_manager.PackageError, "unrecognized"):
                app_manager.packages("test")
        with patch.object(app_manager, "_read", return_value=SimpleNamespace(returncode=0x8A150014, stdout=b"")):
            self.assertEqual(app_manager.packages("test"), [])

    def test_cli_flags_cannot_be_supplied_as_packages(self):
        package = app_manager.Package("Invalid", "--scope", "1.0", "2.0", "winget")
        for action in ("install", "upgrade", "uninstall"):
            self.assertFalse(app_manager.can_run(action, package))
        with patch.object(app_manager, "_read") as run:
            with self.assertRaises(app_manager.PackageError):
                app_manager.packages("--manifest")
        run.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "WinGet runs on Windows")
    def test_completed_operation_uses_exact_version_and_records_only_safe_metadata(self):
        package = app_manager.Package("Editor", "Example.Editor", "1.0", "1.1", "winget")
        process = SimpleNamespace(stdout=io.BytesIO(b"Starting 25%\rDone 100%\r"), wait=lambda: 0)
        with tempfile.TemporaryDirectory() as directory:
            with (patch.object(paths, "DATA_DIR", Path(directory)),
                  patch.object(app_manager, "_executable", return_value="winget.exe"),
                  patch.object(subprocess, "Popen", return_value=nullcontext(process)) as launch):
                progress = []
                self.assertEqual(app_manager.run("upgrade", package, progress.append), (0, True))
                self.assertEqual(progress, [100])
                self.assertEqual(launch.call_args.args[0][1:10],
                                 ["upgrade", "--id", package.id, "--exact", "--source", "winget", "--version",
                                  "1.1", "--disable-interactivity"])
                saved, = app_manager.history()
                self.assertEqual((saved["action"], saved["package"], saved["code"]), ("upgrade", package.id, 0))
                self.assertEqual(set(saved), {"action", "package", "code", "time"})
