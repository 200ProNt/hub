"""Интеграция с системным треем Windows и глобальные хоткеи (чистый ctypes Win32)."""

from __future__ import annotations

import ctypes
import os
import sys
import threading
import webbrowser
from ctypes import wintypes

WM_DESTROY = 0x0002
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

HOTKEY_ID_WIN = 101
HOTKEY_ID_CTRL = 102

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
    "stop_event": None,
}


def is_supported() -> bool:
    """Проверяет доступность Win32 API для трея и хоткеев."""
    return sys.platform == "win32"


def _wnd_proc(hwnd, msg, wparam, lparam):
    port = _tray_state.get("port", 8770)
    base_url = f"http://127.0.0.1:{port}"

    if msg == WM_TRAY:
        if lparam in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
            webbrowser.open(f"{base_url}/")
            return 0
        if lparam == WM_RBUTTONUP:
            user32 = ctypes.windll.user32
            pt = POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            hmenu = user32.CreatePopupMenu()
            user32.AppendMenuW(hmenu, MF_STRING, ID_MENU_OPEN, "Открыть Hub")
            user32.AppendMenuW(hmenu, MF_STRING, ID_MENU_NOTES, "Быстрая заметка")
            user32.AppendMenuW(hmenu, MF_STRING, ID_MENU_MONITOR, "Мониторинг ПК")
            user32.AppendMenuW(hmenu, MF_STRING, ID_MENU_DROP, "Обмен с телефоном (QR-Drop)")
            user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(hmenu, MF_STRING, ID_MENU_EXIT, "Закрыть Hub")

            user32.SetForegroundWindow(hwnd)
            cmd = user32.TrackPopupMenu(hmenu, TPM_LEFTALIGN | TPM_RIGHTBUTTON | 0x0100, pt.x, pt.y, 0, hwnd, None)
            user32.DestroyMenu(hmenu)

            if cmd == ID_MENU_OPEN:
                webbrowser.open(f"{base_url}/")
            elif cmd == ID_MENU_NOTES:
                webbrowser.open(f"{base_url}/#notes")
            elif cmd == ID_MENU_MONITOR:
                webbrowser.open(f"{base_url}/#monitor")
            elif cmd == ID_MENU_DROP:
                webbrowser.open(f"{base_url}/#qrdrop")
            elif cmd == ID_MENU_EXIT:
                stop_tray()
                os._exit(0)
            return 0

    elif msg == WM_HOTKEY:
        # Глобальный хоткей нажат (Win+Alt+H или Ctrl+Shift+H)
        webbrowser.open(f"{base_url}/#quick")
        return 0

    elif msg == WM_DESTROY:
        ctypes.windll.user32.PostQuitMessage(0)
        return 0

    return ctypes.windll.user32.DefWindowProcW(hwnd, msg, wparam, lparam)


_wnd_proc_cb = None


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
        user32.DestroyMenu.argtypes = [wintypes.HMENU]
        user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
        shell32.Shell_NotifyIconW.restype = wintypes.BOOL

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
            0, class_name, "HubTrayWindow", 0, 0, 0, 0, 0, -3, 0, hinst, 0  # HWND_MESSAGE = -3
        )
        if not hwnd:
            # Fallback к обычному невидимому окну, если HWND_MESSAGE не доступен
            hwnd = user32.CreateWindowExW(
                0, class_name, "HubTrayWindow", 0, 0, 0, 0, 0, 0, 0, hinst, 0
            )

        _tray_state["hwnd"] = hwnd

        # Иконка трея
        hicon = user32.LoadIconW(0, 32512)  # IDI_APPLICATION = 32512

        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = hicon
        nid.szTip = "Hub v1.3.2 — швейцарский нож Windows"

        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        _tray_state["nid"] = nid
        _tray_state["running"] = True

        # Регистрация глобальных хоткеев:
        # 1) Win + Alt + H
        user32.RegisterHotKey(hwnd, HOTKEY_ID_WIN, MOD_WIN | MOD_ALT | MOD_NOREPEAT, 0x48)  # 'H' = 0x48
        # 2) Запасной: Ctrl + Shift + H
        user32.RegisterHotKey(hwnd, HOTKEY_ID_CTRL, MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, 0x48)

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    except Exception:
        pass
    finally:
        _tray_state["running"] = False


def start_tray(port: int = 8770) -> bool:
    """Запускает иконку в трее и глобальный хоткей в фоновом потоке."""
    if not is_supported():
        return False
    if _tray_state.get("running"):
        return True

    _tray_state["port"] = port
    t = threading.Thread(target=_run_message_loop, args=(port,), daemon=True, name="HubTrayThread")
    _tray_state["thread"] = t
    t.start()
    return True


def stop_tray() -> bool:
    """Удаляет иконку из трея и завершает обработку сообщений."""
    if not is_supported():
        return False

    hwnd = _tray_state.get("hwnd")
    nid = _tray_state.get("nid")

    try:
        if nid:
            ctypes.windll.shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
        if hwnd:
            ctypes.windll.user32.UnregisterHotKey(hwnd, HOTKEY_ID_WIN)
            ctypes.windll.user32.UnregisterHotKey(hwnd, HOTKEY_ID_CTRL)
            ctypes.windll.user32.DestroyWindow(hwnd)
    except Exception:
        pass

    _tray_state["running"] = False
    _tray_state["hwnd"] = None
    _tray_state["nid"] = None
    return True


def status() -> dict:
    """Возвращает статус трея и хоткеев."""
    return {
        "supported": is_supported(),
        "running": bool(_tray_state.get("running")),
        "hotkeys": ["Win+Alt+H", "Ctrl+Shift+H"],
        "port": _tray_state.get("port", 8770),
    }
