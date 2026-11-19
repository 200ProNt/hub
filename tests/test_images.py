"""Тесты инструмента сжатия и сохранения изображений."""

import base64
import tempfile
import unittest
from pathlib import Path

from tools import images


class ImagesTestCase(unittest.TestCase):
    def test_sanitize_filename(self):
        self.assertEqual(images.sanitize_filename("photo.jpg"), "photo.jpg")
        self.assertEqual(images.sanitize_filename("my:image_test?.png"), "my-image_test-.png")
        self.assertEqual(images.sanitize_filename("noext"), "noext.webp")
        self.assertEqual(images.sanitize_filename("danger.exe"), "danger.exe.webp")

    def test_save_image_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raw_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRtest"
            b64 = "data:image/png;base64," + base64.b64encode(raw_bytes).decode("ascii")

            result = images.save_image(tmpdir, "test.png", b64)
            self.assertTrue(result["ok"])
            self.assertEqual(result["filename"], "test.png")
            self.assertEqual(result["size"], len(raw_bytes))

            saved_file = Path(tmpdir) / "test.png"
            self.assertTrue(saved_file.is_file())
            self.assertEqual(saved_file.read_bytes(), raw_bytes)

    def test_save_image_avoids_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raw_bytes = b"image_data_123"
            b64 = base64.b64encode(raw_bytes).decode("ascii")

            res1 = images.save_image(tmpdir, "pic.webp", b64)
            self.assertEqual(res1["filename"], "pic.webp")

            res2 = images.save_image(tmpdir, "pic.webp", b64)
            self.assertEqual(res2["filename"], "pic_1.webp")

    def test_save_image_validates_path(self):
        with self.assertRaises(images.ImageError):
            images.save_image("", "pic.png", "abc")

        with self.assertRaises(images.ImageError):
            images.save_image("C:\\Windows", "pic.png", "abc")

    def test_save_image_handles_corrupt_base64(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(images.ImageError):
                images.save_image(tmpdir, "pic.png", "not-a-valid-base64-string!!!")


if __name__ == "__main__":
    unittest.main()
