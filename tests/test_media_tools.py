import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from tools import av_media, jobs, pdf_media


def control():
    return jobs.Job(float("inf"))


class PdfTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.destination = Path(directory.name)
        self.source = self.destination / "example.pdf"
        writer = PdfWriter()
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                 NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject("/Helvetica")})
        for index in range(2):
            page = writer.add_blank_page(width=220, height=120)
            page[NameObject("/Resources")] = DictionaryObject(
                {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
            contents = DecodedStreamObject()
            contents.set_data(f"BT /F1 16 Tf 20 65 Td (Hub Test {index + 1}) Tj ET".encode("ascii"))
            page.replace_contents(contents)
        writer.add_metadata({"/Title": "Hub fixture"})
        with self.source.open("wb") as stream:
            writer.write(stream)

    def test_pdf_merge_split_extract_rotate_compress_and_text(self):
        self.assertEqual(pdf_media.info(self.source)["title"], "Hub fixture")
        before = self.source.read_bytes()
        outputs = pdf_media.process("merge", [self.source, self.source], self.destination, "1", 90, control())
        self.assertEqual(len(PdfReader(outputs[0]).pages), 2)
        split = pdf_media.process("split", [self.source], self.destination, "", 90, control())
        self.assertEqual(len(split), 2)
        self.assertEqual(len(PdfReader(split[0]).pages), 1)
        single, = pdf_media.process("extract", [self.source], self.destination, "2", 90, control())
        self.assertIn("Hub Test 2", PdfReader(single).pages[0].extract_text())
        rotated, = pdf_media.process("rotate", [self.source], self.destination, "2", 90, control())
        self.assertEqual([page.rotation for page in PdfReader(rotated).pages], [0, 90])
        compressed, = pdf_media.process("compress", [self.source], self.destination, "", 90, control())
        self.assertEqual(len(PdfReader(compressed).pages), 2)
        extracted, = pdf_media.process("text", [self.source], self.destination, "", 90, control())
        self.assertIn("Hub Test 2", Path(extracted).read_text(encoding="utf-8"))
        self.assertEqual(self.source.read_bytes(), before)

    def test_out_of_range_and_cancellation_publish_no_results(self):
        with self.assertRaisesRegex(av_media.MediaError, "outside"):
            pdf_media.process("extract", [self.source], self.destination, "3", 90, control())
        job = control()
        job.cancelled.set()
        with self.assertRaises(jobs.Cancelled):
            pdf_media.process("rotate", [self.source], self.destination, "", 90, job)
        self.assertEqual(list(self.destination.iterdir()), [self.source])


@unittest.skipUnless(os.environ.get("HUB_TEST_FFMPEG"), "Set HUB_TEST_FFMPEG to a test FFmpeg bin directory")
class AudioVideoTests(unittest.TestCase):
    def test_video_encoding_and_audio_extraction_preserve_source(self):
        ffmpeg_dir = os.environ["HUB_TEST_FFMPEG"]
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            original = folder / "фрагмент.mp4"
            ffmpeg, _ = av_media._tools(ffmpeg_dir)
            subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=24",
                            "-f", "lavfi", "-i", "sine=frequency=440", "-t", "1.5",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(original)], check=True)
            video, = av_media.convert(ffmpeg_dir, [original], folder, "video", "webm", 480, "balanced", 128, control())
            audio, = av_media.convert(ffmpeg_dir, [original], folder, "audio", "mp3", 0, "balanced", 128, control())
            video_stream, = [stream for stream in av_media.info(ffmpeg_dir, video)["streams"]
                             if stream["codec_type"] == "video"]
            self.assertEqual(video_stream["height"], 480)
            self.assertEqual(av_media.info(ffmpeg_dir, audio)["streams"][0]["codec_name"], "mp3")
            self.assertEqual(av_media.info(ffmpeg_dir, original)["streams"][0]["height"], 240)

    def test_cancelled_encoder_kills_process_and_does_not_publish(self):
        ffmpeg_dir = os.environ["HUB_TEST_FFMPEG"]
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            original = folder / "source.mp4"
            ffmpeg, _ = av_media._tools(ffmpeg_dir)
            subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=24",
                            "-t", "3", "-c:v", "libx264", str(original)], check=True)

            class CancelDuringEncoding(jobs.Job):
                def report(self, entries, files, size):
                    self.cancelled.set()

            with self.assertRaises(jobs.Cancelled):
                av_media.convert(ffmpeg_dir, [original], folder, "video", "webm", 2160, "high", 128,
                                 CancelDuringEncoding(float("inf")))
            self.assertEqual(list(folder.iterdir()), [original])
