"""Тесты для модуля обмена данными с телефоном (QR-Drop)."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import qrdrop


class TestQrDrop(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.patch_dir = Path(self.tmp_dir.name)
        self.orig_incoming = qrdrop.INCOMING_DIR
        self.orig_shared = qrdrop.SHARED_DIR
        self.orig_texts = qrdrop.INCOMING_TEXTS_FILE

        qrdrop.INCOMING_DIR = self.patch_dir / "incoming"
        qrdrop.SHARED_DIR = self.patch_dir / "shared"
        qrdrop.INCOMING_TEXTS_FILE = self.patch_dir / "texts.json"

    def tearDown(self):
        qrdrop.INCOMING_DIR = self.orig_incoming
        qrdrop.SHARED_DIR = self.orig_shared
        qrdrop.INCOMING_TEXTS_FILE = self.orig_texts
        self.tmp_dir.cleanup()

    def test_get_local_ip(self):
        ip = qrdrop.get_local_ip()
        self.assertIsInstance(ip, str)
        self.assertIn(".", ip)

    def test_get_drop_url(self):
        url = qrdrop.get_drop_url(8770)
        self.assertTrue(url.startswith("http://"))
        self.assertTrue(url.endswith(":8770/drop"))

    def test_save_and_list_incoming_text(self):
        rec = qrdrop.save_incoming_text("Привет с телефона!", source="phone")
        self.assertEqual(rec["text"], "Привет с телефона!")
        self.assertEqual(rec["source"], "phone")

        texts = qrdrop.list_incoming_texts()
        self.assertEqual(len(texts), 1)
        self.assertEqual(texts[0]["text"], "Привет с телефона!")

    def test_save_incoming_file(self):
        content = b"Binary photo contents"
        saved = qrdrop.save_incoming_file("my_photo.jpg", content)
        self.assertEqual(saved["name"], "my_photo.jpg")
        self.assertEqual(saved["size"], len(content))

        # Проверка защиты от перезаписи одинаковых имён
        saved2 = qrdrop.save_incoming_file("my_photo.jpg", content)
        self.assertEqual(saved2["name"], "my_photo (1).jpg")

        files = qrdrop.list_incoming_files()
        self.assertEqual(len(files), 2)

    def test_share_and_unshare_file(self):
        sample = self.patch_dir / "document.pdf"
        sample.write_bytes(b"PDF data")

        shared = qrdrop.share_file(str(sample))
        self.assertEqual(shared["name"], "document.pdf")
        self.assertEqual(len(qrdrop.list_shared_files()), 1)

        ok = qrdrop.unshare_file("document.pdf")
        self.assertTrue(ok)
        self.assertEqual(len(qrdrop.list_shared_files()), 0)


if __name__ == "__main__":
    unittest.main()
