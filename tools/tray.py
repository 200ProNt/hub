"""Интеграция с системным треем Windows и глобальные хоткеи (чистый ctypes Win32)."""

from __future__ import annotations

import ctypes
import os
import sys
import threading
import time
import webbrowser
from ctypes import wintypes
from tools.i18n import tr

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_HOTKEY = 0x0312
WM_APP = 0x8000
WM_TRAY = WM_APP + 1

WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205

NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2

NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004

MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
TPM_LEFTALIGN = 0x0000
TPM_RIGHTBUTTON = 0x0002

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

ID_MENU_OPEN = 1001
ID_MENU_NOTES = 1002
ID_MENU_MONITOR = 1003
ID_MENU_DROP = 1004
ID_MENU_EXIT = 1005


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeout", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
    ]


LRESULT = ctypes.c_int64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long

WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HICON),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


_tray_state = {
    "thread": None,
    "hwnd": None,
    "nid": None,
    "port": 8770,
    "running": False,
    "active_hotkeys": [],
    "registered_hotkey_ids": [],
}


def is_supported() -> bool:
    """Проверяет доступность Win32 API для трея и хоткеев."""
    return sys.platform == "win32"


def _wnd_proc(hwnd, msg, wparam, lparam):
    port = _tray_state.get("port", 8770)

    if msg == WM_TRAY:
        if lparam in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
            _open(port)
            return 0
        if lparam == WM_RBUTTONUP:
            user32 = ctypes.windll.user32
            pt = POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            hmenu = user32.CreatePopupMenu()
            user32.AppendMenuW(hmenu, MF_STRING, ID_MENU_OPEN, tr("Open Hub", "Открыть Hub"))
            user32.AppendMenuW(hmenu, MF_STRING, ID_MENU_NOTES, tr("Quick note", "Быстрая заметка"))
            user32.AppendMenuW(hmenu, MF_STRING, ID_MENU_MONITOR, tr("PC Monitor", "Мониторинг ПК"))
            user32.AppendMenuW(hmenu, MF_STRING, ID_MENU_DROP, tr("Phone Transfer (QR-Drop)", "Обмен с телефоном (QR-Drop)"))
            user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(hmenu, MF_STRING, ID_MENU_EXIT, tr("Exit Hub", "Закрыть Hub"))

            user32.SetForegroundWindow(hwnd)
            cmd = user32.TrackPopupMenu(hmenu, TPM_LEFTALIGN | TPM_RIGHTBUTTON | 0x0100, pt.x, pt.y, 0, hwnd, None)
            user32.DestroyMenu(hmenu)

            if cmd == ID_MENU_OPEN:
                _open(port)
            elif cmd == ID_MENU_NOTES:
                _open(port, "notes")
            elif cmd == ID_MENU_MONITOR:
                _open(port, "monitor")
            elif cmd == ID_MENU_DROP:
                _open(port, "qrdrop")
            elif cmd == ID_MENU_EXIT:
                if close_window:
                    threading.Thread(target=close_window, daemon=True).start()
                else:
                    os._exit(0)
            return 0

    elif msg == WM_HOTKEY:
        # Глобальный хоткей нажат (например Ctrl+Alt+H из любой программы)
        _open(port, "quick")
        return 0

    elif msg == WM_CLOSE:
        ctypes.windll.user32.DestroyWindow(hwnd)
        return 0

    elif msg == WM_DESTROY:
        ctypes.windll.user32.PostQuitMessage(0)
        return 0

    return ctypes.windll.user32.DefWindowProcW(hwnd, msg, wparam, lparam)


_wnd_proc_cb = None
open_window = None
close_window = None
icon_path = None
_ready = threading.Event()


def _open(port, route=""):
    if open_window:
        open_window(route)
    else:
        webbrowser.open(f"http://127.0.0.1:{port}/" + (f"#{route}" if route else ""))


def _run_message_loop(port: int):
    global _wnd_proc_cb
    if not is_supported():
        return

    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        shell32 = ctypes.windll.shell32

        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = LRESULT
        user32.PostQuitMessage.argtypes = [ctypes.c_int]
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
        user32.CreatePopupMenu.restype = wintypes.HMENU
        user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.WPARAM, wintypes.LPCWSTR]
        user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                         ctypes.c_int, wintypes.HWND, wintypes.LPVOID]
        user32.TrackPopupMenu.restype = wintypes.UINT
        user32.DestroyMenu.argtypes = [wintypes.HMENU]
        user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        user32.RegisterHotKey.restype = wintypes.BOOL
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HMENU,
            wintypes.HINSTANCE,
            wintypes.LPVOID,
        ]
        user32.CreateWindowExW.restype = wintypes.HWND
        shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.c_void_p]
        shell32.Shell_NotifyIconW.restype = wintypes.BOOL

        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        user32.LoadIconW.restype = wintypes.HICON
        user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, wintypes.INT, wintypes.INT, wintypes.UINT]
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
        hinst = kernel32.GetModuleHandleW(None)
        class_name = f"HubTrayClass_{port}"

        _wnd_proc_cb = WNDPROC(_wnd_proc)

        wcls = WNDCLASSEXW()
        wcls.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wcls.lpfnWndProc = _wnd_proc_cb
        wcls.hInstance = hinst
        wcls.lpszClassName = class_name
        user32.RegisterClassExW(ctypes.byref(wcls))

        hwnd = user32.CreateWindowExW(
            0, class_name, "HubTrayWindow", 0, 0, 0, 0, 0, None, None, hinst, None
        )
        if not hwnd:
            hwnd = user32.CreateWindowExW(
                0, class_name, "HubTrayWindow", 0, 0, 0, 0, 0, -3, None, hinst, None
            )

        if not hwnd:
            return
        _tray_state["hwnd"] = hwnd

        custom_icon = user32.LoadImageW(None, str(icon_path), 1, 16, 16, 0x0010) if icon_path else None
        hicon = custom_icon or user32.LoadIconW(0, 32512)

        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = hicon
        nid.szTip = "Hub — швейцарский нож Windows"

        for _ in range(5):
            if shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
                _tray_state["nid"] = nid
                break
            time.sleep(0.25)

        _tray_state["running"] = True

        # Регистрация глобальных хоткеев (проверяем свободные комбинации)
        candidates = [
            ("Ctrl+Alt+H", 101, MOD_CONTROL | MOD_ALT, 0x48),
            ("Alt+Shift+H", 102, MOD_ALT | MOD_SHIFT, 0x48),
            ("Ctrl+Shift+H", 103, MOD_CONTROL | MOD_SHIFT, 0x48),
            ("Win+Alt+H", 104, MOD_WIN | MOD_ALT, 0x48),
        ]
        active_hotkeys = []
        reg_ids = []
        for name, hk_id, mod, vk in candidates:
            if user32.RegisterHotKey(hwnd, hk_id, mod | MOD_NOREPEAT, vk):
                active_hotkeys.append(name)
                reg_ids.append(hk_id)

        _tray_state["active_hotkeys"] = active_hotkeys
        _tray_state["registered_hotkey_ids"] = reg_ids

        _ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        user32.UnregisterClassW(class_name, hinst)
        if custom_icon:
            user32.DestroyIcon.argtypes = [wintypes.HICON]
            user32.DestroyIcon(custom_icon)

    except Exception:
        pass
    finally:
        _tray_state.update(running=False, hwnd=None, nid=None, active_hotkeys=[], registered_hotkey_ids=[])
        _ready.set()


def start_tray(port: int = 8770) -> bool:
    """Запускает иконку в трее и глобальный хоткей в фоновом потоке."""
    if not is_supported():
        return False
    thread = _tray_state.get("thread")
    if thread and thread.is_alive():
        return bool(_tray_state["nid"])

    _ready.clear()
    _tray_state["port"] = port
    t = threading.Thread(target=_run_message_loop, args=(port,), daemon=True, name="HubTrayThread")
    _tray_state["thread"] = t
    t.start()
    _ready.wait(timeout=3)
    return bool(_tray_state["nid"])


def stop_tray() -> bool:
    """Удаляет иконку из трея и завершает обработку сообщений."""
    if not is_supported():
        return False

    hwnd = _tray_state.get("hwnd")
    nid = _tray_state.get("nid")
    reg_ids = _tray_state.get("registered_hotkey_ids", [])

    try:
        if nid:
            ctypes.windll.shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
        if hwnd:
            for hk_id in reg_ids:
                ctypes.windll.user32.UnregisterHotKey(hwnd, hk_id)
            post = ctypes.windll.user32.PostMessageW
            post.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            post(hwnd, WM_CLOSE, 0, 0)
    except Exception:
        pass

    thread = _tray_state.get("thread")
    if thread and thread is not threading.current_thread():
        thread.join(timeout=3)
    return True


def status() -> dict:
    """Возвращает статус трея и хоткеев."""
    active = _tray_state.get("active_hotkeys", [])
    return {
        "supported": is_supported(),
        "running": bool(_tray_state.get("nid")),
        "hotkeys": active if open_window else active or ["Ctrl+Alt+H"],
        "port": _tray_state.get("port", 8770),
    }
