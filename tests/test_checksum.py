"""Тесты для модуля вычисления хэшей и генератора паролей."""

import tempfile
import unittest
from pathlib import Path

from tools import checksum


class TestChecksum(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.test_file = Path(self.tmp_dir.name) / "sample.txt"
        self.test_file.write_text("Hello Hub 1.3.2!", encoding="utf-8")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_compute_file_hashes(self):
        res = checksum.compute_file_hashes(str(self.test_file))
        self.assertEqual(res["name"], "sample.txt")
        self.assertGreater(res["size"], 0)
        self.assertIn("hashes", res)
        hashes = res["hashes"]
        self.assertIn("md5", hashes)
        self.assertIn("sha1", hashes)
        self.assertIn("sha256", hashes)
        self.assertIn("sha512", hashes)
        self.assertEqual(len(hashes["sha256"]), 64)
        self.assertEqual(len(hashes["md5"]), 32)

    def test_compute_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            checksum.compute_file_hashes("non_existent_file_xyz_123.bin")

    def test_compute_text_hash(self):
        res = checksum.compute_text_hash("test-data")
        self.assertEqual(res["length"], 9)
        self.assertIn("sha256", res)
        self.assertIn("md5", res)
        self.assertIn("base64_encode", res)
        self.assertEqual(res["base64_decode"], None)

        res_b64 = checksum.compute_text_hash(res["base64_encode"])
        self.assertEqual(res_b64["base64_decode"], "test-data")

    def test_generate_password_random(self):
        pwd = checksum.generate_password(length=20, uppercase=True, lowercase=True, digits=True, symbols=True)
        self.assertEqual(len(pwd["password"]), 20)
        self.assertEqual(pwd["mode"], "random")
        self.assertGreater(pwd["entropy"], 60)
        self.assertIn(pwd["strength"], ("strong", "very_strong"))

    def test_generate_password_passphrase(self):
        phrase = checksum.generate_password(mode="passphrase", words_count=4)
        self.assertIn("-", phrase["password"])
        parts = phrase["password"].split("-")
        self.assertEqual(len(parts), 5)  # 4 слова + 1 число в конце
        self.assertEqual(phrase["mode"], "passphrase")
        self.assertGreaterEqual(phrase["entropy"], 38.0)


if __name__ == "__main__":
    unittest.main()
