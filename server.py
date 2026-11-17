"""Hub — локальный сайт с инструментами. Один сервер, только stdlib.

Слушает 127.0.0.1, наружу не смотрит.
"""

from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from tools import (
    bigfiles,
    cleanup,
    clipboard,
    compare,
    diskmap,
    duplicates,
    filesorter,
    monitor,
    notes,
)
from tools.registry import TOOLS

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
DATA_DIR = BASE_DIR / "data"

START_PORT = 8770
PORT_ATTEMPTS = 30
MAX_BODY_BYTES = 8 * 1024 * 1024
VERSION = "1.0.0"

CONTENT_TYPES = {
    ".html": "text/html",
    ".css": "text/css",
    ".js": "application/javascript",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".json": "application/json",
}

IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".avif": "image/avif",
}

MAX_THUMB_BYTES = 12 * 1024 * 1024

_state: dict[str, object] = {"store": None, "watcher": None}


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def store() -> clipboard.ClipboardStore:
    instance = _state.get("store")
    if not isinstance(instance, clipboard.ClipboardStore):
        raise ApiError("История буфера ещё не готова", 503)
    return instance


def watcher() -> clipboard.ClipboardWatcher:
    instance = _state.get("watcher")
    if not isinstance(instance, clipboard.ClipboardWatcher):
        raise ApiError("Наблюдатель буфера не запущен", 503)
    return instance


# --- Системные действия ----------------------------------------------------


def about_info() -> dict:
    """Общие сведения о программе для вкладки «О программе»."""
    try:
        license_text = (BASE_DIR / "LICENSE").read_text(encoding="utf-8")
    except OSError:
        license_text = ""
    return {
        "name": "Hub",
        "version": VERSION,
        "author": "devrin",
        "license": "MIT",
        "license_text": license_text,
        "folder": str(BASE_DIR),
        "readme": str(BASE_DIR / "README.md"),
        "tools": len(TOOLS),
        "python": platform.python_version(),
    }


def default_folder() -> str:
    downloads = Path.home() / "Downloads"
    return str(downloads) if downloads.is_dir() else str(Path.home())


def pick_folder(initial: str = "") -> str:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:  # noqa: BLE001
        raise ApiError("Диалог выбора папки недоступен — впиши путь вручную") from exc

    result = {"path": ""}

    def run_dialog() -> None:
        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:  # noqa: BLE001
            pass
        root.update()
        try:
            result["path"] = filedialog.askdirectory(
                parent=root,
                initialdir=initial or str(Path.home()),
                title="Выбери папку",
                mustexist=True,
            )
        finally:
            root.destroy()

    worker = threading.Thread(target=run_dialog, daemon=True)
    worker.start()
    worker.join(timeout=300)
    if worker.is_alive():
        raise ApiError("Диалог не ответил — впиши путь вручную")
    return result["path"]


def open_in_explorer(path: str) -> None:
    target = Path(path).expanduser()
    if not target.exists():
        raise ApiError("Папка или файл не найдены")
    if sys.platform == "win32":
        if target.is_file():
            subprocess.Popen(["explorer", "/select,", str(target)])
        else:
            os.startfile(str(target))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])


# --- HTTP ------------------------------------------------------------------


class HubHandler(BaseHTTPRequestHandler):
    server_version = "Hub/1.0"

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        if args and str(args[0]).startswith(("4", "5")):
            sys.stderr.write(f"[hub] {fmt % args}\n")

    def _send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path: Path) -> None:
        data = path.read_bytes()
        content_type = CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")
        if content_type.startswith(("text/", "application/json", "application/javascript", "image/svg")):
            content_type += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_thumb(self, raw_path: str) -> None:
        """Превью для найденных дубликатов: только файлы из последнего скана."""
        path = Path(unquote(raw_path))
        if not raw_path or not duplicates.allowed_path(str(path)):
            return self._send_json({"error": "Этот файл не из последней проверки"}, 404)
        content_type = IMAGE_TYPES.get(path.suffix.lower())
        if not content_type:
            return self._send_json({"error": "Превью есть только для картинок"}, 404)
        try:
            if not path.is_file() or path.stat().st_size > MAX_THUMB_BYTES:
                return self._send_json({"error": "Не получилось показать файл"}, 404)
            data = path.read_bytes()
        except OSError:
            return self._send_json({"error": "Не получилось прочитать файл"}, 404)
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=120")
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ApiError("Некорректная длина запроса")
        if length > MAX_BODY_BYTES:
            raise ApiError("Слишком большой запрос", 413)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ApiError("Некорректный JSON")
        return parsed if isinstance(parsed, dict) else {}

    # -- маршруты --

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/info":
                return self._send_json(
                    {
                        "tools": TOOLS,
                        "version": VERSION,
                        "default_folder": default_folder(),
                        "platform": sys.platform,
                    }
                )
            if path == "/api/about":
                return self._send_json(about_info())
            if path == "/api/clipboard/items":
                query = parse_qs(parsed.query)
                text = (query.get("q") or [""])[0]
                try:
                    limit = max(1, min(1000, int((query.get("limit") or ["150"])[0])))
                except ValueError:
                    limit = 150
                return self._send_json(
                    {
                        "items": store().listing(text, limit),
                        "total": store().count(),
                        "paused": watcher().paused.is_set(),
                    }
                )
            if path == "/api/clipboard/state":
                return self._send_json(
                    {
                        "paused": watcher().paused.is_set(),
                        "total": store().count(),
                        "error": watcher().last_error,
                    }
                )
            if path == "/api/sorter/last-run":
                return self._send_json({"last_run": filesorter.last_run()})
            if path == "/api/dupes/last-run":
                return self._send_json({"last_run": duplicates.last_run()})
            if path == "/api/diskmap/last-run":
                try:
                    return self._send_json({"last_run": diskmap.last_run()})
                except OSError as exc:
                    return self._send_json({"error": str(exc)}, 400)
            if path == "/api/bigfiles/last-run":
                return self._send_json({"last_run": bigfiles.last_run()})
            if path == "/api/cleanup/last-run":
                return self._send_json({"last_run": cleanup.last_run()})
            if path == "/api/notes/items":
                query = parse_qs(parsed.query)
                text = (query.get("q") or [""])[0]
                return self._send_json({"items": notes.store().listing(text), "total": notes.store().count()})
            if path == "/api/monitor/snapshot":
                return self._send_json(monitor.snapshot())
            if path == "/api/dupes/thumb":
                query = parse_qs(parsed.query)
                return self._send_thumb((query.get("path") or [""])[0])
            if path.startswith("/api/"):
                return self._send_json({"error": "Неизвестный запрос"}, 404)
        except ApiError as exc:
            return self._send_json({"error": str(exc)}, exc.status)
        return self._serve_static(path)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            body = self._read_json()
            payload = self._dispatch_post(path, body)
        except ApiError as exc:
            return self._send_json({"error": str(exc)}, exc.status)
        except (
            filesorter.ScanError,
            duplicates.ScanError,
            duplicates.RemoveError,
            diskmap.ScanError,
            diskmap.RemoveError,
            bigfiles.ScanError,
            bigfiles.RemoveError,
            cleanup.ScanError,
            cleanup.RemoveError,
            compare.CompareError,
            monitor.MonitorError,
            notes.NoteError,
            FileNotFoundError,
            NotADirectoryError,
            ValueError,
            PermissionError,
        ) as exc:
            return self._send_json({"error": str(exc)}, 400)
        except clipboard.ClipboardUnavailable as exc:
            return self._send_json({"error": str(exc)}, 400)
        except Exception as exc:  # noqa: BLE001
            return self._send_json({"error": f"Внутренняя ошибка: {exc}"}, 500)
        self._send_json(payload)

    def _dispatch_post(self, path: str, body: dict) -> dict:
        if path == "/api/clipboard/copy":
            item = store().get(str(body.get("id", "")))
            if not item:
                raise ApiError("Запись не найдена", 404)
            clipboard.write_text(item["text"])
            return {"ok": True}

        if path == "/api/clipboard/pin":
            item = store().toggle_pin(str(body.get("id", "")))
            if not item:
                raise ApiError("Запись не найдена", 404)
            return {"item": {"id": item["id"], "pinned": item["pinned"]}}

        if path == "/api/clipboard/delete":
            if not store().delete(str(body.get("id", ""))):
                raise ApiError("Запись не найдена", 404)
            return {"ok": True}

        if path == "/api/clipboard/clear":
            return {"removed": store().clear()}

        if path == "/api/clipboard/pause":
            paused = bool(body.get("paused"))
            if paused:
                watcher().pause()
            else:
                watcher().resume()
            return {"paused": paused}

        if path == "/api/sorter/scan":
            return filesorter.scan(str(body.get("folder", "")))

        if path == "/api/sorter/apply":
            files = body.get("files") or []
            if not isinstance(files, list):
                raise ApiError("Список файлов должен быть массивом")
            return filesorter.apply(str(body.get("folder", "")), [str(item) for item in files])

        if path == "/api/sorter/undo":
            return filesorter.undo(str(body.get("run_id", "")))

        if path == "/api/dupes/scan":
            recursive = body.get("recursive")
            try:
                min_size = int(body.get("min_size", duplicates.DEFAULT_MIN_SIZE))
            except (TypeError, ValueError):
                min_size = duplicates.DEFAULT_MIN_SIZE
            return duplicates.scan(
                str(body.get("folder", "")),
                recursive=True if recursive is None else bool(recursive),
                min_size=min_size,
            )

        if path == "/api/dupes/remove":
            paths = body.get("files") or []
            if not isinstance(paths, list):
                raise ApiError("Список файлов должен быть массивом")
            return duplicates.remove(str(body.get("folder", "")), [str(item) for item in paths])

        if path == "/api/dupes/undo":
            return duplicates.undo(str(body.get("run_id", "")))

        if path == "/api/diskmap/scan":
            return diskmap.scan(str(body.get("folder", "")))

        if path == "/api/diskmap/files":
            return diskmap.files(str(body.get("folder", "")))

        if path == "/api/diskmap/remove":
            return diskmap.remove_file(
                str(body.get("path", "")), str(body.get("mode", "")), body.get("confirmed", False)
            )

        if path == "/api/diskmap/undo":
            return diskmap.undo(str(body.get("run_id", "")))

        if path == "/api/bigfiles/scan":
            try:
                limit = int(body.get("limit", bigfiles.DEFAULT_LIMIT))
            except (TypeError, ValueError):
                limit = bigfiles.DEFAULT_LIMIT
            try:
                min_size = int(body.get("min_size", bigfiles.DEFAULT_MIN_SIZE))
            except (TypeError, ValueError):
                min_size = bigfiles.DEFAULT_MIN_SIZE
            return bigfiles.scan(str(body.get("folder", "")), limit=limit, min_size=min_size)

        if path == "/api/bigfiles/remove":
            return bigfiles.remove(
                str(body.get("path", "")), str(body.get("mode", "")), body.get("confirmed", False)
            )

        if path == "/api/bigfiles/undo":
            return bigfiles.undo(str(body.get("run_id", "")))

        if path == "/api/compare/run":
            return compare.compare(
                str(body.get("left", "")), str(body.get("right", "")), deep=bool(body.get("deep"))
            )

        if path == "/api/cleanup/scan":
            try:
                age_days = int(body.get("age_days", cleanup.DEFAULT_AGE_DAYS))
            except (TypeError, ValueError):
                age_days = cleanup.DEFAULT_AGE_DAYS
            include_junk = body.get("include_junk")
            return cleanup.scan(
                str(body.get("folder", "")),
                age_days=age_days,
                include_junk=True if include_junk is None else bool(include_junk),
            )

        if path == "/api/cleanup/remove":
            paths = body.get("paths") or []
            if not isinstance(paths, list):
                raise ApiError("Список путей должен быть массивом")
            return cleanup.remove(
                [str(item) for item in paths],
                str(body.get("mode", "trash")),
                body.get("confirmed", False),
                folder=str(body.get("folder", "")),
            )

        if path == "/api/cleanup/undo":
            return cleanup.undo(str(body.get("run_id", "")))

        if path == "/api/monitor/terminate":
            try:
                pid = int(body.get("pid", 0))
            except (TypeError, ValueError):
                raise ApiError("Не понял, какой процесс закрывать")
            return monitor.terminate(pid)

        if path == "/api/notes/create":
            return {"item": notes.store().create(str(body.get("title", "")), str(body.get("text", "")))}

        if path == "/api/notes/update":
            return {
                "item": notes.store().update(
                    str(body.get("id", "")), str(body.get("title", "")), str(body.get("text", ""))
                )
            }

        if path == "/api/notes/pin":
            return {"item": notes.store().toggle_pin(str(body.get("id", "")))}

        if path == "/api/notes/delete":
            if not notes.store().delete(str(body.get("id", ""))):
                raise ApiError("Заметка не найдена", 404)
            return {"ok": True}

        if path in ("/api/pick-folder", "/api/sorter/pick-folder", "/api/bigfiles/pick-folder",
                    "/api/cleanup/pick-folder", "/api/compare/pick-folder"):
            return {"folder": pick_folder(str(body.get("initial", "")))}

        if path in ("/api/open", "/api/sorter/open", "/api/bigfiles/open",
                    "/api/cleanup/open", "/api/compare/open"):
            open_in_explorer(str(body.get("path", "")))
            return {"ok": True}

        raise ApiError("Неизвестный запрос", 404)

    def _serve_static(self, path: str) -> None:
        relative = "index.html" if path in ("", "/") else unquote(path).lstrip("/")
        try:
            target = (WEB_DIR / relative).resolve()
            target.relative_to(WEB_DIR.resolve())
        except (ValueError, OSError):
            return self._send_json({"error": "Не найдено"}, 404)
        if not target.is_file():
            return self._send_json({"error": "Не найдено"}, 404)
        self._send_file(target)


def find_port(start: int = START_PORT) -> int:
    for port in range(start, start + PORT_ATTEMPTS):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise SystemExit("Не нашёл свободный порт. Закрой лишние программы и попробуй снова.")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    store_instance = clipboard.ClipboardStore(DATA_DIR / "clipboard.json")
    watcher_instance = clipboard.ClipboardWatcher(store_instance)
    _state["store"] = store_instance
    _state["watcher"] = watcher_instance
    watcher_instance.start()

    open_browser = "--no-browser" not in sys.argv
    port = find_port()
    url = f"http://127.0.0.1:{port}/"

    server = ThreadingHTTPServer(("127.0.0.1", port), HubHandler)
    server.daemon_threads = True

    print("Hub запущен")
    print(f"  Адрес: {url}")
    print(f"  История буфера: {DATA_DIR / 'clipboard.json'}")
    print("  Закрыть: Ctrl+C или закрой это окно")
    print()

    if open_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nОстанавливаюсь…")
    finally:
        watcher_instance.stop()
        server.server_close()


if __name__ == "__main__":
    main()
