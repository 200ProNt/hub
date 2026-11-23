"""Интеграция с Windows: создание ярлыков на Рабочем столе и в меню «Пуск»."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from tools import paths

ROOT = Path(__file__).resolve().parent.parent
START_BAT = ROOT / "start.bat"


class ShortcutError(RuntimeError):
    """Ошибка создания или удаления ярлыка."""


def supported() -> bool:
    return sys.platform == "win32"


def _desktop_dir() -> Path:
    if supported():
        try:
            import winreg

            key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                val, _ = winreg.QueryValueEx(key, "Desktop")
                expanded = os.path.expandvars(str(val))
                if os.path.isdir(expanded):
                    return Path(expanded)
        except OSError:
            pass
    return Path.home() / "Desktop"


def _start_menu_dir() -> Path:
    if supported():
        try:
            import winreg

            key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                val, _ = winreg.QueryValueEx(key, "Programs")
                expanded = os.path.expandvars(str(val))
                if os.path.isdir(expanded):
                    return Path(expanded)
        except OSError:
            pass
    return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def get_shortcut_path(kind: str) -> Path:
    if kind == "start_menu":
        return _start_menu_dir() / "Hub.lnk"
    return _desktop_dir() / "Hub.lnk"


def status() -> dict:
    if not supported():
        return {"supported": False, "desktop": False, "start_menu": False}
    desktop_lnk = get_shortcut_path("desktop")
    start_lnk = get_shortcut_path("start_menu")
    return {
        "supported": True,
        "desktop": desktop_lnk.is_file(),
        "start_menu": start_lnk.is_file(),
    }


def create(target: str = "desktop") -> dict:
    if not supported():
        raise ShortcutError("Создание ярлыков доступно только в Windows")
    lnk = get_shortcut_path(target)
    lnk.parent.mkdir(parents=True, exist_ok=True)

    escaped_lnk = str(lnk.resolve()).replace("'", "''")
    launch = paths.DESKTOP_EXE or START_BAT
    escaped_target = str(launch.resolve()).replace("'", "''")
    escaped_work = str(launch.parent.resolve()).replace("'", "''")

    ps_code = (
        f"$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{escaped_lnk}'); "
        f"$s.TargetPath = '{escaped_target}'; "
        f"$s.WorkingDirectory = '{escaped_work}'; "
        f"$s.Description = 'Hub — инструменты для Windows'; "
        f"$s.Save()"
    )

    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_code],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if supported() else 0,
        )
        if res.returncode != 0:
            raise ShortcutError(f"PowerShell error: {res.stderr.strip() or res.stdout.strip()}")
    except (OSError, subprocess.SubprocessError) as exc:
        raise ShortcutError(f"Не удалось создать ярлык: {exc}") from exc

    return status()


def remove(target: str = "desktop") -> dict:
    if not supported():
        raise ShortcutError("Доступно только в Windows")
    lnk = get_shortcut_path(target)
    if lnk.is_file():
        try:
            lnk.unlink()
        except OSError as exc:
            raise ShortcutError(f"Не удалось удалить ярлык: {exc}") from exc
    return status()
