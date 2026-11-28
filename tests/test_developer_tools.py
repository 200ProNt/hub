import binascii
import os
import tempfile
import unittest
from pathlib import Path

from tools import developer_tools as dev, jobs


class DeveloperToolsTests(unittest.TestCase):
    def test_json_formatting_and_validation(self):
        formatted, value = dev.format_json('{"array":[1,true],"текст":"значение"}')
        self.assertEqual(value["array"], [1, True])
        self.assertIn("\n", formatted)
        self.assertEqual(dev.format_json(' { "a" : 1 } ', compact=True)[0], '{"a":1}')
        for bad in ('{"a":1,"a":2}', '{"a":NaN}', '{'):
            with self.assertRaises(ValueError):
                dev.parse_json(bad)

    def test_text_encodings_validate_and_round_trip(self):
        content = "Я & 😄"
        self.assertEqual(dev.url_text(dev.url_text(content, False), True), content)
        self.assertEqual(dev.base64_text(dev.base64_text(content, False), True), content)
        with self.assertRaises(ValueError):
            dev.url_text("%X", True)
        with self.assertRaises(binascii.Error):
            dev.base64_text("!!!", True)

    def test_code_diff_shows_changed_lines_and_final_newline(self):
        self.assertIn("\\ No newline at end of file", dev.text_diff("line", "line\n"))
        with tempfile.TemporaryDirectory() as folder:
            left, right = Path(folder) / "old.py", Path(folder) / "new.py"
            left.write_text("print(1)\n", encoding="utf-8")
            right.write_text("print(2)\n", encoding="utf-8")
            result = dev.code_diff(left, right)
            self.assertIn("old.py", result)
            self.assertIn("-print(1)", result)
            self.assertIn("+print(2)", result)

    def test_streaming_binary_round_trip_and_cancel_no_output(self):
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder)
            source = parent / "image.bin"
            content = bytes(range(256)) * 12_289 + b"end"
            source.write_bytes(content)
            encoded = dev.base64_file(source, parent, False, jobs.Job(float("inf")))
            restored = dev.base64_file(encoded, parent, True, jobs.Job(float("inf")))
            self.assertNotEqual(Path(restored), source)
            self.assertEqual(Path(restored).read_bytes(), content)
            invalid = parent / "invalid.b64"
            invalid.write_bytes(b"Zg==      Zm8=")
            with self.assertRaises(binascii.Error):
                dev.base64_file(invalid, parent, True, jobs.Job(float("inf")))
            control = jobs.Job(float("inf"))
            control.cancelled.set()
            with self.assertRaises(jobs.Cancelled):
                dev.base64_file(source, parent, False, control)
            self.assertEqual(len(list(parent.iterdir())), 4)

    @unittest.skipUnless(os.name == "nt", "Uses the Windows desktop regex engine")
    def test_regex_returns_utf16_spans_and_named_groups(self):
        import native.ui  # Loads the same .NET runtime used by the page.
        matches, truncated = dev.regex(r"(?<word>[a-z]+)", "😄 One TWO", ignore_case=True)
        self.assertFalse(truncated)
        self.assertEqual(matches[0], (3, 3, "One", {"word": "One"}))
        self.assertEqual(matches[1], (7, 3, "TWO", {"word": "TWO"}))

    @unittest.skipUnless(os.name == "nt", "Uses the Windows desktop regex engine")
    def test_regex_ends_when_the_engine_exceeds_its_budget(self):
        import native.ui
        with self.assertRaisesRegex(ValueError, "time limit"):
            dev.regex(r"(x+)+z$", "x" * 2500 + ".")
