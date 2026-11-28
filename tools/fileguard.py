"""Проверки перед удалением и сканированием: что именно лежит по пути.

И карта диска, и большие файлы, и уборка удаляют только то, что сервер сам показал
пользователю. Для этого запоминается «отпечаток» файла и всех его папок. Если файл
подменили, переименовали папку или подсунули ссылку — отпечаток не совпадёт.

Также модуль защищает системные каталоги Windows/ОС от сканирования и изменения.
"""

from __future__ import annotations

import ctypes
import os
import stat as stat_module
import sys
from pathlib import Path

FILE_ATTRIBUTE_REPARSE_POINT = 0x400


class GuardError(RuntimeError):
    """Путь небезопасен: ссылка, не папка, системный каталог или недоступен."""


def is_link(info) -> bool:
    """Символическая ссылка или junction: и то и другое — reparse point в Windows."""
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & FILE_ATTRIBUTE_REPARSE_POINT)


def identity(info) -> tuple:
    """Отпечаток файла: если хоть что-то изменилось, это уже другой файл."""
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def local_path(path: Path | str) -> Path:
    absolute = Path(os.path.abspath(Path(path).expanduser()))
    if sys.platform == "win32" and (len(absolute.drive) != 2 or
                                   ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(absolute.anchor)) not in (2, 3)):
        raise GuardError("Выбери локальный диск")
    return absolute


def get_system_directories() -> set[Path]:
    """Возвращает набор защищённых системных директорий."""
    system_dirs: set[Path] = set()
    if sys.platform == "win32":
        env_vars = [
            "SystemRoot",
            "windir",
            "ProgramFiles",
            "ProgramFiles(x86)",
            "ProgramW6432",
            "CommonProgramFiles",
            "CommonProgramFiles(x86)",
            "ProgramData",
        ]
        for var in env_vars:
            val = os.environ.get(var)
            if val:
                try:
                    system_dirs.add(Path(val).resolve())
                except OSError:
                    pass
        for folder_name in (
            "Windows",
            "Program Files",
            "Program Files (x86)",
            "ProgramData",
            "$Recycle.Bin",
            "System Volume Information",
        ):
            for drive in ("C:\\", "D:\\"):
                p = Path(drive) / folder_name
                try:
                    if p.exists():
                        system_dirs.add(p.resolve())
                except OSError:
                    pass
    else:
        for p in ("/etc", "/usr", "/bin", "/sbin", "/var", "/System", "/Library", "/proc", "/sys", "/dev", "/boot"):
            path_obj = Path(p)
            try:
                if path_obj.exists():
                    system_dirs.add(path_obj.resolve())
            except OSError:
                pass
    return system_dirs


def is_system_path(path: Path) -> bool:
    """Проверяет, является ли путь корнем диска или системным каталогом."""
    try:
        resolved = path.resolve()
    except OSError:
        return False

    # Корень диска (например, C:\ или /)
    if resolved == Path(resolved.anchor) or resolved.parent == resolved:
        return True

    # Системные папки и их подпапки
    sys_dirs = get_system_directories()
    for sys_dir in sys_dirs:
        if resolved == sys_dir or sys_dir in resolved.parents:
            return True

    # Специфичные папки Windows
    parts = [part.lower() for part in resolved.parts]
    if any(part in ("$recycle.bin", "system volume information") for part in parts):
        return True

    return False


def check_safe_folder(folder: Path | str) -> Path:
    """Проверяет каталог и все компоненты пути до него."""
    raw = Path(os.path.abspath(Path(folder).expanduser()))
    try:
        parents(raw)
    except FileNotFoundError as exc:
        raise GuardError("Такой папки нет — проверь путь") from exc

    if is_system_path(raw):
        raise GuardError("Системная папка защищена: системные каталоги нельзя выбирать для работы")

    return raw


def parents(path: Path) -> tuple:
    """Отпечатки папки и всех её родителей — чтобы переименование не прошло незаметно."""
    identities = []
    for parent in reversed((path, *path.parents)):
        info = parent.lstat()
        if stat_module.S_ISLNK(info.st_mode) or is_link(info):
            raise GuardError("Папка или её родитель — ссылка; выбери обычную папку")
        if not stat_module.S_ISDIR(info.st_mode):
            raise GuardError("Это файл, а нужна папка")
        identities.append((str(parent), info.st_dev, info.st_ino))
    return tuple(reversed(identities))

