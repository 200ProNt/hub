"""Loopback-only Ollama and LM Studio connections."""

from __future__ import annotations

import http.client
import json
import os
import select
import socket
import tempfile
import time
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit

from tools import automation, paths
from tools.i18n import tr

PORTS = {"ollama": 11434, "lmstudio": 1234}
MAX_RESPONSE = 1024 * 1024
_settings_lock = Lock()


class ModelError(RuntimeError):
    pass


class _RequestSocket(socket.socket):
    def recv_into(self, buffer, nbytes=0, flags=0):
        while True:
            self.control.check()
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Local HTTP response timed out")
            if select.select([self], [], [], min(.1, remaining))[0]:
                return super().recv_into(buffer, nbytes, flags)


class _LocalConnection(http.client.HTTPConnection):
    def __init__(self, host, port, control, response_timeout):
        super().__init__(host, port, timeout=5)
        self.control = control
        self.response_timeout = response_timeout

    def connect(self):
        super().connect()
        source = self.sock
        self.sock = _RequestSocket(source.family, source.type, source.proto, fileno=source.detach())
        self.sock.settimeout(self.timeout)
        self.sock.control = self.control
        self.sock.deadline = time.monotonic() + self.response_timeout


def endpoint(provider, address):
    if provider not in PORTS:
        raise ModelError(tr("Select a supported local server.", "Выбери поддерживаемый локальный сервер."))
    try:
        url = urlsplit(address.strip())
        host, port = url.hostname, url.port if url.port is not None else PORTS[provider]
    except ValueError as exc:
        raise ModelError(tr("Invalid server address.", "Некорректный адрес сервера.")) from exc
    if (url.scheme != "http" or host not in ("127.0.0.1", "localhost", "::1") or
            url.username is not None or url.password is not None or url.path not in ("", "/", "/v1", "/v1/") or
            url.query or url.fragment or not 1 <= port <= 65535):
        raise ModelError(tr("Use a loopback HTTP address, such as 127.0.0.1 or localhost.",
                            "Укажи локальный HTTP-адрес, например 127.0.0.1 или localhost."))
    if host == "localhost":
        host = "127.0.0.1"
    return host, port


class Client:
    def __init__(self, provider, address, control, token=""):
        self.provider = provider
        self.host, self.port = endpoint(provider, address)
        self.control = control
        if any(ord(character) < 32 or ord(character) > 126 for character in token) or len(token) > 4096:
            raise ModelError(tr("Invalid local API token.", "Некорректный токен локального API."))
        self.token = token

    def cancel(self):
        self.control.cancelled.set()

    def _request(self, path, payload=None):
        self.control.check()
        connection = _LocalConnection(self.host, self.port, self.control, 5 if payload is None else 120)
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        if payload is not None:
            headers["Content-Type"] = "application/json"
        try:
            self.control.check()
            connection.request("GET" if payload is None else "POST", path, headers=headers,
                               body=json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None)
            with connection.getresponse() as response:
                if response.status != 200:
                    raise ModelError(tr(f"Local server returned HTTP {response.status}.",
                                        f"Локальный сервер вернул HTTP {response.status}."))
                body = response.read(MAX_RESPONSE + 1)
            self.control.check()
            if len(body) > MAX_RESPONSE:
                raise ModelError(tr("Local response is too large.", "Ответ локального сервера слишком большой."))
            value = json.loads(body)
            if not isinstance(value, dict):
                raise ValueError("API object expected")
            return value
        except (OSError, http.client.HTTPException, ValueError) as exc:
            self.control.check()
            raise ModelError(tr("The local server did not return a valid response.",
                                "Локальный сервер не вернул корректный ответ.")) from exc
        finally:
            connection.close()

    def models(self):
        response = self._request("/api/tags" if self.provider == "ollama" else "/api/v1/models")
        models = response.get("models")
        if not isinstance(models, list):
            raise ModelError(tr("The server returned an invalid model list.", "Сервер вернул некорректный список моделей."))
        names = set()
        for model in models:
            if not isinstance(model, dict) or model.get("remote_host") or model.get("remote_model"):
                continue
            if self.provider == "ollama":
                details = model.get("details")
                if not isinstance(details, dict) or details.get("format") not in ("gguf", "safetensors", "mlx"):
                    continue
                size, name = model.get("size"), model.get("name")
            else:
                if model.get("type") != "llm" or model.get("format") not in ("gguf", "mlx"):
                    continue
                size, name = model.get("size_bytes"), model.get("key")
            if (type(size) is int and size > 0 and isinstance(name, str) and 0 < len(name) <= 300 and
                    not name.casefold().endswith((":cloud", "-cloud")) and not any(ord(char) < 32 for char in name)):
                names.add(name)
        return sorted(names, key=str.casefold)

    def ask(self, model, instruction, prompt, temperature, tokens, workflow=False):
        if not prompt.strip() or len(prompt) > 20000 or len(instruction) > 12000:
            raise ModelError(tr("Enter a question within 20,000 characters.", "Введи вопрос длиной до 20 000 символов."))
        if not 0 <= temperature <= 1 or type(tokens) is not int or not 1 <= tokens <= 8192:
            raise ModelError(tr("Check temperature and token limit.", "Проверь температуру и лимит токенов."))
        if model not in self.models():
            raise ModelError(tr("The selected local model is unavailable.", "Выбранная локальная модель недоступна."))
        if self.provider == "ollama":
            payload = {"model": model + ":local", "stream": False, "options": {"temperature": temperature, "num_predict": tokens},
                       "messages": [{"role": "system", "content": instruction}, {"role": "user", "content": prompt}]}
            if workflow:
                payload["format"] = "json"
            reply = self._request("/api/chat", payload)
            message = reply.get("message")
            text = message.get("content") if isinstance(message, dict) else None
        else:
            reply = self._request("/api/v1/chat", {"model": model, "input": prompt, "system_prompt": instruction,
                                                  "temperature": temperature, "max_output_tokens": tokens,
                                                  "stream": False, "store": False})
            output = reply.get("output")
            text = "\n".join(part["content"] for part in output if isinstance(part, dict)
                             and part.get("type") == "message" and isinstance(part.get("content"), str)
                             ) if isinstance(output, list) else None
        if not isinstance(text, str) or not text.strip():
            raise ModelError(tr("The model returned no text.", "Модель не вернула текст."))
        return text


WORKFLOW_PROMPT = (
    'Return one JSON object with "name" and "steps". Each step has "action", "source", '
    '"target" (required for compress), optional integer "age" in days, and "when". '
    'Actions: scan-old, trash-selected, sort, compress, backup. Conditions: always, has-results, no-results. '
    'Source is an explicit local folder, or an existing backup profile name for backup. '
    'Do not invent paths or profile names. If the request needs a missing value, ask the user to supply it. '
    'Do not add scheduling, shell commands, or external integrations. A draft must be reviewed and run by the user.'
)


def proposal(text):
    def unique(pairs):
        value = dict(pairs)
        if len(value) != len(pairs):
            raise ValueError("Duplicate proposal keys")
        return value

    try:
        value = json.loads(text, object_pairs_hook=unique)
        if not isinstance(value, dict) or set(value) != {"name", "steps"} or not isinstance(value["steps"], list):
            raise ValueError("Invalid proposal")
        if any(not isinstance(step, dict) or set(step) - {"action", "source", "target", "age", "when"}
               for step in value["steps"]):
            raise ValueError("Invalid step fields")
        return automation.normalize(value)
    except (ValueError, automation.WorkflowError) as exc:
        raise ModelError(tr("The model did not return a valid workflow draft.",
                            "Модель не вернула корректный черновик сценария.")) from exc


def settings():
    try:
        value = json.loads((paths.DATA_DIR / "local-ai.json").read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def save_settings(provider, address, model, temperature, tokens):
    endpoint(provider, address)
    paths.DATA_DIR.mkdir(parents=True, exist_ok=True)
    value = {"provider": provider, "address": address, "model": model, "temperature": temperature, "tokens": tokens}
    with _settings_lock:
        staged = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=paths.DATA_DIR,
                                             prefix=".local-ai-", suffix=".tmp", delete=False)
        temporary = Path(staged.name)
        try:
            with staged:
                json.dump(value, staged, ensure_ascii=False)
                staged.flush()
                os.fsync(staged.fileno())
            temporary.replace(paths.DATA_DIR / "local-ai.json")
        finally:
            temporary.unlink(missing_ok=True)
