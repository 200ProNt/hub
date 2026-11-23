"""Автозапуск хаба вместе с Windows.

Запись живёт в HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run — это ветка
текущего пользователя, права администратора не нужны. Запускаем через pythonw.exe,
чтобы вместе с хабом не открывалось чёрное окно консоли.
"""

from __future__ import annotations

import sys
from pathlib import Path

from tools import paths

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Hub"
ROOT = Path(__file__).resolve().parent.parent


class AutostartError(RuntimeError):
    """Автозапуск не удалось включить или выключить."""


def supported() -> bool:
    return sys.platform == "win32"


def _registry():
    import winreg

    return winreg


def _pythonw(executable: str | None = None) -> str:
    exe = Path(executable or sys.executable)
    windowless = exe.with_name("pythonw.exe")
    return str(windowless if windowless.is_file() else exe)


def command(script: str | None = None, executable: str | None = None) -> str:
    if paths.DESKTOP_EXE is not None and script is None and executable is None:
        return f'"{paths.DESKTOP_EXE}" --background'
    target = Path(script) if script else ROOT / "server.py"
    return f'"{_pythonw(executable)}" "{target}" --no-browser'


def _stored() -> str:
    winreg = _registry()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _kind = winreg.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        return ""
    except OSError:
        return ""
    return str(value or "")


def status() -> dict:
    expected = command()
    if not supported():
        return {"supported": False, "enabled": False, "command": expected, "matches": False}
    stored = _stored()
    return {
        "supported": True,
        "enabled": bool(stored),
        "command": expected,
        "stored": stored,
        "matches": stored == expected,
    }


def set_enabled(enabled: bool) -> dict:
    if not supported():
        raise AutostartError("Автозапуск умеет только Windows")
    winreg = _registry()
    if enabled:
        try:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
        except OSError as exc:
            raise AutostartError(f"Не получилось записать автозапуск: {exc}") from exc
    else:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, VALUE_NAME)
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise AutostartError(f"Не получилось убрать автозапуск: {exc}") from exc
    return status()
