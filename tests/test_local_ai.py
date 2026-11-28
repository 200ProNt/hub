import json
import tempfile
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch

from tools import jobs, local_ai, paths


@contextmanager
def fixture(payloads):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def reply(self, data=None):
            requests.append((self.command, self.path, data, self.headers.get("Authorization")))
            status, value = payloads[self.path]
            if callable(value):
                value = value()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            body = json.dumps(value).encode()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except OSError:
                pass

        def do_GET(self):
            self.reply()

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.reply(body)

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://localhost:{server.server_port}", requests
        finally:
            server.shutdown()
            thread.join()


class LocalAiTests(unittest.TestCase):
    def test_strict_loopback_and_path(self):
        self.assertEqual(local_ai.endpoint("ollama", "http://localhost"), ("127.0.0.1", 11434))
        self.assertEqual(local_ai.endpoint("lmstudio", "http://[::1]:1234/v1"), ("::1", 1234))
        for value in ("https://127.0.0.1:1234", "http://192.168.0.1:1234", "http://127.0.0.1:0",
                      "http://name@localhost", "http://localhost/path", "http://localhost?x=1"):
            with self.subTest(value=value), self.assertRaises(local_ai.ModelError):
                local_ai.endpoint("ollama", value)

    def test_ollama_local_only_model_and_validated_draft(self):
        local = {"name": "fixture:latest", "size": 1000, "details": {"format": "gguf"}}
        remote = {"name": "network-alias", "size": 1000, "details": {"format": "gguf"}, "remote_host": "example.test"}
        prompt = {"name": "Example", "steps": [{"action": "sort", "source": "C:/Local"}]}
        with fixture({"/api/tags": (200, {"models": [local, remote]}),
                      "/api/chat": (200, {"message": {"content": json.dumps(prompt)}})}) as (address, records):
            client = local_ai.Client("ollama", address, jobs.Job(float("inf")))
            self.assertEqual(client.models(), ["fixture:latest"])
            text = client.ask("fixture:latest", local_ai.WORKFLOW_PROMPT, "Sort", 0.1, 100, workflow=True)
            self.assertFalse(local_ai.proposal(text)["enabled"])
            request = records[-1][2]
            self.assertEqual(request["model"], "fixture:latest:local")
            self.assertEqual(request["options"]["num_predict"], 100)
            self.assertEqual(request["format"], "json")
            with self.assertRaisesRegex(local_ai.ModelError, "unavailable"):
                client.ask("network-alias", "Test", "Ask", 0.1, 100)
            self.assertEqual(sum(path == "/api/chat" for _, path, _, _ in records), 1)

    def test_lm_studio_sends_token_in_memory_and_disables_storage(self):
        model = {"type": "llm", "key": "fixture", "size_bytes": 500, "format": "gguf"}
        with fixture({"/api/v1/models": (200, {"models": [model]}),
                      "/api/v1/chat": (200, {"output": [{"type": "message", "content": "OK"}]})}) as (address, records):
            client = local_ai.Client("lmstudio", address, jobs.Job(float("inf")), "token-fixture")
            self.assertEqual(client.ask("fixture", "Assist", "Hello", 0.5, 50), "OK")
            self.assertEqual(records[-1][3], "Bearer token-fixture")
            self.assertFalse(records[-1][2]["store"])
            self.assertNotIn("integrations", records[-1][2])
            with tempfile.TemporaryDirectory() as raw, patch.object(paths, "DATA_DIR", Path(raw)):
                local_ai.save_settings("lmstudio", address, "fixture", 0.5, 50)
                self.assertNotIn("token-fixture", (Path(raw) / "local-ai.json").read_text(encoding="utf-8"))

    def test_unrecognized_proposals_never_become_workflow_steps(self):
        for payload in (
            '{"name":"x","steps":[{"action":"shell","source":"test"}]}',
            '{"name":"x","enabled":true,"steps":[{"action":"sort","source":"test"}]}',
            '{"name":"x","steps":[{"action":"sort","source":"test","execute":true}]}',
        ):
            with self.subTest(payload=payload), self.assertRaises(local_ai.ModelError):
                local_ai.proposal(payload)

    def test_cancel_interrupts_pending_local_response(self):
        received, release, done = Event(), Event(), Event()
        result = []

        def pending():
            received.set()
            release.wait(5)
            return {"models": []}

        with fixture({"/api/tags": (200, pending)}) as (address, _):
            client = local_ai.Client("ollama", address, jobs.Job(float("inf")))

            def request():
                try:
                    client.models()
                except Exception as exc:
                    result.append(exc)
                finally:
                    done.set()

            thread = Thread(target=request, daemon=True)
            thread.start()
            try:
                self.assertTrue(received.wait(5))
                client.cancel()
                self.assertTrue(done.wait(2))
                self.assertIsInstance(result[0], jobs.Cancelled)
            finally:
                release.set()
                thread.join(timeout=5)
