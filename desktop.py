"""Окно Hub для Windows. Инструменты и HTTP API остаются общими."""

import argparse
import ctypes
import hashlib
import os
import socket
import sys
import threading
from ctypes import wintypes
from pathlib import Path

from tools import paths, preferences


def run(background, activate_event, kernel):
    import server
    from native.ui import run_window

    class DesktopServer(server.ThreadingHTTPServer):
        allow_reuse_address = False

        def server_bind(self):
            # On Windows SO_REUSEADDR can bind over a running legacy Hub.
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()

    http = None
    for port in range(server.START_PORT, server.START_PORT + server.PORT_ATTEMPTS):
        try:
            http = DesktopServer(("0.0.0.0", port), server.HubHandler)
            break
        except OSError:
            continue
    if http is None:
        raise RuntimeError("Порты Hub заняты. Закрой старую версию и попробуй снова.")

    state = preferences.read()
    start_hidden = background and state.get("tray") != "off"
    icon = paths.ROOT / "hub.ico"
    exiting = threading.Event()
    listener = None

    def setup(ui):
        nonlocal listener

        def activate(route=""):
            if not exiting.is_set():
                ui.dispatch(lambda: ui.activate(route))

        http.close_window = lambda: ui.dispatch(ui.close)
        http.apply_theme = lambda _: ui.dispatch(ui.apply_theme)
        server.tray.open_window = activate
        server.tray.close_window = http.close_window
        server.tray.icon_path = icon if icon.is_file() else None

        def listen_for_launches():
            if state.get("tray") != "off" and not server.tray.start_tray(http.server_port) and start_hidden:
                activate()
            while not exiting.is_set():
                if kernel.WaitForSingleObject(activate_event, 250) == 0:
                    activate()

        listener = threading.Thread(target=listen_for_launches, daemon=True)
        listener.start()

    http.desktop = True
    http.native_shell = True
    http.close_window = lambda: None
    http.apply_theme = lambda _: None
    http.daemon_threads = True
    watcher = server.start_clipboard()
    threading.Thread(target=http.serve_forever, daemon=True).start()
    try:
        run_window(http.server_port, server.VERSION, server.default_folder(), start_hidden, setup, server.CHANGELOG[0])
    finally:
        exiting.set()
        if listener is not None:
            listener.join(timeout=4)
        server.tray.stop_tray()
        watcher.stop()
        watcher.join(timeout=2)
        http.shutdown()
        http.server_close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--migrate", type=Path)
    parser.add_argument("--migrate-only", action="store_true")
    args = parser.parse_args()
    if args.migrate_only and not args.migrate:
        parser.error("--migrate-only requires --migrate")
    profile = (Path(os.environ["LOCALAPPDATA"]) / "Hub").resolve()
    paths.DATA_DIR = profile / "data"
    if getattr(sys, "frozen", False):
        paths.DESKTOP_EXE = Path(sys.executable)

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateEventW.restype = wintypes.HANDLE
    kernel.SetEvent.argtypes = kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    profile_id = hashlib.sha256(os.fsencode(os.path.normcase(profile))).hexdigest()[:24]
    event = kernel.CreateEventW(None, False, False, f"Local\\Hub-{profile_id}")
    status = ctypes.get_last_error()
    if not event:
        raise ctypes.WinError(status)
    try:
        if status == 183:  # ERROR_ALREADY_EXISTS
            kernel.SetEvent(event)
            if args.migrate:
                raise RuntimeError("Закрой настольный Hub через трей и повтори перенос.")
            return
        profile.mkdir(parents=True, exist_ok=True)
        if args.migrate:
            from tools import autostart

            preferences.migrate(args.migrate, paths.DATA_DIR)
            entry = autostart.status().get("stored", "")
            old_script = args.migrate.resolve() / "server.py"
            if paths.DESKTOP_EXE and f'"{old_script}"'.casefold() in entry.casefold():
                autostart.set_enabled(True)
        if not args.migrate_only:
            run(args.background, event, kernel)
    finally:
        kernel.CloseHandle(event)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        import traceback

        traceback.print_exc()
        ctypes.windll.user32.MessageBoxW(None, str(error), "Hub — ошибка запуска", 0x10)
        sys.exit(1)
