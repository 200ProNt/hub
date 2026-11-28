import os
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from tools import autostart, startup_manager


@unittest.skipUnless(os.name == "nt", "Startup Manager requires Windows")
class StartupManagerTests(unittest.TestCase):
    def test_command_path_handles_quoted_env_and_leaves_ambiguous_values_unknown(self):
        with patch.dict(os.environ, {"HUB_STARTUP_TEST": r"C:\Program Files\Hub"}):
            self.assertEqual(startup_manager._command_path(r'"%HUB_STARTUP_TEST%\hub.exe" --flag', True),
                             r"C:\Program Files\Hub\hub.exe")
        self.assertEqual(startup_manager._command_path(r"C:\Program Files\Hub\hub.exe --flag", False), "")
        self.assertEqual(startup_manager._command_path("example.exe", False), "")

    def test_startup_folder_round_trip_and_changed_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "Startup"
            folder.mkdir()
            original = folder / "fixture.lnk"
            original.write_bytes(b"test shortcut fixture")

            row, = startup_manager._folder_items(folder, False)
            startup_manager.toggle(row)
            self.assertFalse(original.exists())
            saved, = startup_manager._folder_items(folder, False)
            self.assertFalse(saved.registered)
            original.write_bytes(b"a replacement from outside Hub")
            with self.assertRaisesRegex(startup_manager.StartupError, "already exists"):
                startup_manager.toggle(saved)
            self.assertEqual(original.read_bytes(), b"a replacement from outside Hub")
            original.unlink()

            startup_manager.toggle(saved)
            self.assertEqual(original.read_bytes(), b"test shortcut fixture")
            row, = startup_manager._folder_items(folder, False)
            original.write_bytes(b"modified after listing")
            with self.assertRaisesRegex(startup_manager.StartupError, "changed"):
                startup_manager.toggle(row)
            self.assertEqual(original.read_bytes(), b"modified after listing")

    def test_system_mutation_requires_administrator(self):
        row = startup_manager.Entry("fixture", "HKLM", True, True, ("", 1))
        with (patch.object(startup_manager, "is_admin", return_value=False),
              patch.object(startup_manager, "_set_file") as write):
            with self.assertRaisesRegex(startup_manager.StartupError, "Administrator"):
                startup_manager.toggle(row)
        write.assert_not_called()

    def test_registry_round_trip_keeps_type_and_retries_failed_removal(self):
        import winreg

        view = winreg.KEY_WOW64_32KEY
        key = winreg.HKEY_LOCAL_MACHINE
        original = (key, autostart.RUN_KEY, view)
        value = (r'"%ProgramFiles%\Fixture\fixture.exe" /flag', winreg.REG_EXPAND_SZ)
        fixture = {original: {"Fixture": value, "Unknown": (b"\x01", winreg.REG_BINARY)}}

        def opened(hive, path, _, access):
            identity = (hive, path, access & (winreg.KEY_WOW64_32KEY | winreg.KEY_WOW64_64KEY))
            if identity not in fixture:
                raise FileNotFoundError(path)
            return nullcontext(fixture[identity])

        def created(hive, path, _, access):
            identity = (hive, path, access & (winreg.KEY_WOW64_32KEY | winreg.KEY_WOW64_64KEY))
            return nullcontext(fixture.setdefault(identity, {}))

        def query(mapping, name):
            if name not in mapping:
                raise FileNotFoundError(name)
            return mapping[name]

        def remove(mapping, name):
            del mapping[name]

        def value_at(mapping, index):
            name, (data, kind) = list(mapping.items())[index]
            return name, data, kind

        def refresh():
            return {entry.name: entry for entry in startup_manager._registry_items("Run", key, view, True, "machine")}

        with (patch.object(winreg, "OpenKey", side_effect=opened),
              patch.object(winreg, "CreateKeyEx", side_effect=created),
              patch.object(winreg, "QueryInfoKey", side_effect=lambda values: (0, len(values), 0)),
              patch.object(winreg, "EnumValue", side_effect=value_at),
              patch.object(winreg, "QueryValueEx", side_effect=query),
              patch.object(winreg, "SetValueEx", side_effect=lambda values, name, _, kind, data:
                           values.update({name: (data, kind)})),
              patch.object(winreg, "FlushKey"),
              patch.object(winreg, "DeleteValue", side_effect=remove) as delete,
              patch.object(startup_manager, "is_admin", return_value=True)):
            records = refresh()
            self.assertFalse(records["Unknown"].can_change)
            row = records["Fixture"]
            delete.side_effect = PermissionError
            with self.assertRaises(startup_manager.StartupError):
                startup_manager.toggle(row)
            self.assertEqual(fixture[original]["Fixture"], value)
            delete.side_effect = remove
            data = refresh()["Fixture"]
            self.assertFalse(data.conflict)
            startup_manager.toggle(data)
            self.assertNotIn("Fixture", fixture[original])
            saved = refresh()["Fixture"]
            self.assertFalse(saved.registered)

            fixture[original]["Fixture"] = ("different", winreg.REG_SZ)
            with self.assertRaisesRegex(startup_manager.StartupError, "already exists"):
                startup_manager.toggle(saved)
            self.assertTrue(refresh()["Fixture"].conflict)
            del fixture[original]["Fixture"]
            startup_manager.toggle(saved)
            self.assertEqual(fixture[original]["Fixture"], value)


if __name__ == "__main__":
    unittest.main()
