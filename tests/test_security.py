"""Тесты защитных механизмов: защита API, буфера, системных папок и заметок."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server
from tools import clipboard, fileguard, notes


class SystemFolderGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_drive_root_is_system_path(self) -> None:
        anchor = Path(Path.cwd().anchor)
        self.assertTrue(fileguard.is_system_path(anchor))

    def test_safe_user_folder_is_not_system_path(self) -> None:
        self.assertFalse(fileguard.is_system_path(self.test_dir))
        checked = fileguard.check_safe_folder(self.test_dir)
        self.assertEqual(checked, self.test_dir.resolve())

    def test_check_safe_folder_rejects_root(self) -> None:
        anchor = Path(Path.cwd().anchor)
        with self.assertRaises(fileguard.GuardError) as caught:
            fileguard.check_safe_folder(anchor)
        self.assertIn("Системная папка защищена", str(caught.exception))

    def test_check_safe_folder_rejects_windows_or_etc(self) -> None:
        if sys.platform == "win32":
            windir = os.environ.get("SystemRoot") or "C:\\Windows"
            target = Path(windir)
            if target.exists():
                with self.assertRaises(fileguard.GuardError):
                    fileguard.check_safe_folder(target)
        else:
            target = Path("/etc")
            if target.exists():
                with self.assertRaises(fileguard.GuardError):
                    fileguard.check_safe_folder(target)


class ClipboardSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "clipboard.json"
        self.store = clipboard.ClipboardStore(self.path, limit=10)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_detects_private_keys(self) -> None:
        rsa_key = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0...\n-----END RSA PRIVATE KEY-----"
        ssh_key = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAA...\n-----END OPENSSH PRIVATE KEY-----"
        self.assertTrue(clipboard.is_sensitive(rsa_key))
        self.assertTrue(clipboard.is_sensitive(ssh_key))

    def test_detects_api_tokens_and_jwt(self) -> None:
        gh_token = "ghp_123456789012345678901234567890123456"
        openai_key = "sk-proj-123456789012345678901234567890"
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozG4B_d_example_token_signature_string"
        aws = "AKIAIOSFODNN7EXAMPLE"
        self.assertTrue(clipboard.is_sensitive(gh_token))
        self.assertTrue(clipboard.is_sensitive(openai_key))
        self.assertTrue(clipboard.is_sensitive(jwt))
        self.assertTrue(clipboard.is_sensitive(aws))

    def test_allows_normal_text(self) -> None:
        self.assertFalse(clipboard.is_sensitive("Обычный текст для буфера обмена"))
        self.assertFalse(clipboard.is_sensitive("SELECT * FROM users WHERE active = 1;"))
        self.assertFalse(clipboard.is_sensitive("const path = require('path');"))

    def test_store_skips_sensitive_by_default(self) -> None:
        token = "ghp_123456789012345678901234567890123456"
        res = self.store.add(token)
        self.assertIsNone(res)
        self.assertEqual(self.store.count(), 0)

        # Обычный текст добавляется
        normal = self.store.add("Заметка для работы")
        self.assertIsNotNone(normal)
        self.assertEqual(self.store.count(), 1)


class CrashDurabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_notes_corrupted_file_backup_and_bak_restore(self) -> None:
        notes_file = self.tmp_dir / "notes.json"
        store = notes.NotesStore(notes_file)
        store.create("Заголовок", "Важный текст заметок")
        self.assertEqual(store.count(), 1)

        # Убедимся, что .bak файл существует
        bak_file = self.tmp_dir / "notes.json.bak"
        self.assertTrue(notes_file.exists())
        # Делаем повторное сохранение, чтобы .bak обновился
        store.create("Вторая", "Текст второй")
        self.assertTrue(bak_file.exists())

        # Симулируем поломку основного файла (например, сбой питания записал мусор)
        notes_file.write_text("CORRUPTED_JSON_DATA{{{", encoding="utf-8")

        # Переоткрываем хранилище: должно восстановить из .bak и создать .corrupted файл
        reopened = notes.NotesStore(notes_file)
        self.assertGreaterEqual(reopened.count(), 1)

        corrupted_backups = list(self.tmp_dir.glob("notes.corrupted.*.json"))
        self.assertEqual(len(corrupted_backups), 1)
        self.assertEqual(corrupted_backups[0].read_text(encoding="utf-8"), "CORRUPTED_JSON_DATA{{{")

    def test_clipboard_corrupted_file_backup_and_bak_restore(self) -> None:
        clip_file = self.tmp_dir / "clipboard.json"
        store = clipboard.ClipboardStore(clip_file, limit=10)
        store.add("Первая запись")
        store.add("Вторая запись")

        bak_file = self.tmp_dir / "clipboard.json.bak"
        self.assertTrue(bak_file.exists())

        # Симулируем поломку файла
        clip_file.write_text("{невалидный json", encoding="utf-8")

        reopened = clipboard.ClipboardStore(clip_file, limit=10)
        self.assertGreaterEqual(reopened.count(), 1)

        corrupted_backups = list(self.tmp_dir.glob("clipboard.corrupted.*.json"))
        self.assertEqual(len(corrupted_backups), 1)


class HttpApiSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), server.HubHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def test_security_headers_present_in_responses(self) -> None:
        req = urllib.request.Request(f"{self.base_url}/api/info")
        with urllib.request.urlopen(req) as response:
            headers = dict(response.headers)
            self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
            self.assertEqual(headers.get("X-Frame-Options"), "DENY")
            self.assertIn("default-src 'self'", headers.get("Content-Security-Policy", ""))

    def test_dns_rebinding_host_header_blocked(self) -> None:
        req = urllib.request.Request(
            f"{self.base_url}/api/info",
            headers={"Host": "evil-attacker.com"},
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(req)
        self.assertEqual(caught.exception.code, 403)
        body = json.loads(caught.exception.read().decode())
        self.assertIn("Host", body.get("error", ""))

    def test_cross_origin_origin_header_blocked(self) -> None:
        req = urllib.request.Request(
            f"{self.base_url}/api/info",
            headers={"Origin": "https://malicious-website.com"},
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(req)
        self.assertEqual(caught.exception.code, 403)
        body = json.loads(caught.exception.read().decode())
        self.assertIn("CSRF", body.get("error", ""))

    def test_cross_site_sec_fetch_site_blocked(self) -> None:
        req = urllib.request.Request(
            f"{self.base_url}/api/info",
            headers={"Sec-Fetch-Site": "cross-site"},
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(req)
        self.assertEqual(caught.exception.code, 403)

    def test_system_folder_scan_via_api_is_rejected(self) -> None:
        anchor = str(Path(Path.cwd().anchor))
        payload = json.dumps({"folder": anchor}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/diskmap/scan",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(req)
        self.assertEqual(caught.exception.code, 400)
        body = json.loads(caught.exception.read().decode())
        self.assertIn("Системная папка защищена", body.get("error", ""))


if __name__ == "__main__":
    unittest.main()
