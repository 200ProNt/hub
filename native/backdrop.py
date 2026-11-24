"""Системная композиция окна Windows."""

import ctypes
from ctypes import wintypes

from System.Windows import SystemParameters
from System.Windows.Interop import HwndSource, WindowInteropHelper
from System.Windows.Media import Colors


class Margins(ctypes.Structure):
    _fields_ = [(edge, ctypes.c_int) for edge in ("left", "right", "top", "bottom")]


def acrylic(window, enabled, dark):
    handle = WindowInteropHelper(window).Handle
    hwnd = handle.ToInt64()
    if not hwnd:
        return False
    target = HwndSource.FromHwnd(handle).CompositionTarget
    target.BackgroundColor = Colors.Transparent
    dwm = ctypes.windll.dwmapi
    set_attribute = dwm.DwmSetWindowAttribute
    set_attribute.argtypes = [wintypes.HWND, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD]
    extend = dwm.DwmExtendFrameIntoClientArea
    extend.argtypes = [wintypes.HWND, ctypes.POINTER(Margins)]

    def set_value(attribute, value):
        number = ctypes.c_int(value)
        return set_attribute(hwnd, attribute, ctypes.byref(number), ctypes.sizeof(number)) == 0

    set_value(20, dark)
    set_value(33, 2)
    enabled = enabled and not SystemParameters.HighContrast
    extend(hwnd, ctypes.byref(Margins(-1, -1, -1, -1)))
    backdrop_ok = set_value(38, 3 if enabled else 1)
    return enabled and backdrop_ok
