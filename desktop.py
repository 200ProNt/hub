"""Окно Hub для Windows. Инструменты и HTTP API остаются общими."""

import argparse
import ctypes
import hashlib
import json
import os
import socket
import sys
import threading
from ctypes import wintypes
from pathlib import Path

from tools import paths, preferences


def run(background, activate_event, kernel, profile):
    import webview
    import server
    from webview.platforms import winforms

    if not winforms.is_chromium:
        raise RuntimeError("Установи Microsoft Edge WebView2 Runtime и снова запусти Hub.")

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
    dark = state.get("hub-theme") == "dark"
    icon = paths.ROOT / "hub.ico"
    webview.settings["ALLOW_DOWNLOADS"] = True
    window = webview.create_window(
        "Hub", f"http://127.0.0.1:{http.server_port}/", width=1120, height=760,
        min_size=(520, 440), hidden=start_hidden, text_select=True, zoomable=True,
        background_color="#202020" if dark else "#f5f6f8",
    )
    exiting = threading.Event()
    hwnd = None

    def apply_theme(dark_mode):
        if hwnd is not None:
            value = wintypes.BOOL(dark_mode)
            set_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
            set_attribute.argtypes = [wintypes.HWND, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD]
            set_attribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))

    def on_before_show():
        nonlocal hwnd
        hwnd = window.native.Handle.ToInt64()
        apply_theme(dark)

    def activate(route=""):
        if exiting.is_set():
            return
        window.show()
        if hwnd is not None:
            user32 = ctypes.windll.user32
            user32.IsIconic.argtypes = [wintypes.HWND]
            user32.SetForegroundWindow.argtypes = [wintypes.HWND]
            if user32.IsIconic(hwnd):
                window.restore()
            user32.SetForegroundWindow(hwnd)
        if route:
            action = "window.HubPalette?.open()" if route == "quick" else (
                "location.hash = " + json.dumps(f"#/{route}")
            )
            window.run_js(action)

    def exit_app():
        exiting.set()
        window.destroy()

    def on_closing():
        if not exiting.is_set() and server.tray.status()["running"]:
            window.hide()
            return False
        exiting.set()
        return True

    def listen_for_launches():
        if state.get("tray") != "off" and not server.tray.start_tray(http.server_port) and start_hidden:
            activate()
        while not exiting.is_set():
            if kernel.WaitForSingleObject(activate_event, 250) == 0:
                activate()

    http.desktop = True
    http.close_window = exit_app
    http.apply_theme = apply_theme
    http.daemon_threads = True
    server.tray.open_window = activate
    server.tray.close_window = exit_app
    server.tray.icon_path = icon if icon.is_file() else None
    window.events.closing += on_closing
    window.events.before_show += on_before_show

    watcher = server.start_clipboard()
    threading.Thread(target=http.serve_forever, daemon=True).start()
    try:
        webview.start(listen_for_launches, gui="edgechromium", icon=str(icon) if icon.is_file() else None,
                      private_mode=False, storage_path=str(profile / "WebView2"))
    finally:
        exiting.set()
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
            run(args.background, event, kernel, profile)
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
