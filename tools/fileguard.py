"""Проверки перед удалением: что именно лежит по пути.

И карта диска, и большие файлы, и уборка удаляют только то, что сервер сам показал
пользователю. Для этого запоминается «отпечаток» файла и всех его папок. Если файл
подменили, переименовали папку или подсунули ссылку — отпечаток не совпадёт.
"""

from __future__ import annotations

import stat as stat_module
from pathlib import Path

FILE_ATTRIBUTE_REPARSE_POINT = 0x400


class GuardError(RuntimeError):
    """Путь небезопасен: ссылка, не папка или недоступен."""


def is_link(info) -> bool:
    """Символическая ссылка или junction: и то и другое — reparse point в Windows."""
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & FILE_ATTRIBUTE_REPARSE_POINT)


def identity(info) -> tuple:
    """Отпечаток файла: если хоть что-то изменилось, это уже другой файл."""
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def parents(path: Path) -> tuple:
    """Отпечатки папки и всех её родителей — чтобы переименование не прошло незаметно."""
    identities = []
    for parent in (path, *path.parents):
        info = parent.lstat()
        if stat_module.S_ISLNK(info.st_mode) or is_link(info) or not stat_module.S_ISDIR(info.st_mode):
            raise GuardError("Папка или её родитель — ссылка; выбери обычную папку")
        identities.append((str(parent), info.st_dev, info.st_ino))
    return tuple(identities)
