"""Inspect existing Windows startup entries and reverse changes made by Hub."""

from __future__ import annotations

import ctypes
import json
import os
import re
import stat
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Lock

from tools import autostart, fileguard
from tools.i18n import tr

_lock = Lock()


class StartupError(RuntimeError):
    pass


@dataclass(frozen=True)
class Entry:
    name: str
    source: str
    system: bool
    registered: bool
    snapshot: tuple
    registry: tuple | None = None
    folder: Path | None = None
    target: str = ""
    company: str = ""
    target_available: bool = False
    can_change: bool = True
    conflict: bool = False


def _registry_sources():
    import winreg

    return (
        ("HKCU · Run", winreg.HKEY_CURRENT_USER, 0, False, "user"),
        ("HKLM · Run (64-bit)", winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY, True, "system64"),
        ("HKLM · Run (32-bit)", winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY, True, "system32"),
    )


def _folders():
    # The WPF runtime is already loaded when this Windows-only tool is mounted.
    from System import Environment

    for special, system in ((Environment.SpecialFolder.Startup, False),
                            (Environment.SpecialFolder.CommonStartup, True)):
        value = Environment.GetFolderPath(special, Environment.SpecialFolderOption.DoNotVerify)
        if value:
            yield Path(str(value)), system


def is_admin():
    return autostart.supported() and bool(ctypes.windll.shell32.IsUserAnAdmin())


def _fixed_path(path):
    return (path.is_absolute() and len(path.drive) == 2
            and ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(path.anchor)) == 3)


def _registry_items(source, hive, view, system, scope):
    import winreg

    backup_path = fr"Software\Hub\DisabledStartup\{scope}"
    items = {}
    for path, registered in ((autostart.RUN_KEY, True), (backup_path, False)):
        try:
            opened = winreg.OpenKey(hive, path, 0, winreg.KEY_READ | view)
        except FileNotFoundError:
            continue
        with opened as key:
            for index in range(winreg.QueryInfoKey(key)[1]):
                name, value, kind = winreg.EnumValue(key, index)
                identity = name.casefold()
                if identity in items:
                    if items[identity].snapshot != (value, kind):
                        items[identity] = replace(items[identity], conflict=True)
                    continue
                valid = isinstance(value, str) and kind in (winreg.REG_SZ, winreg.REG_EXPAND_SZ)
                target = _command_path(value, kind == winreg.REG_EXPAND_SZ) if valid else ""
                items[identity] = Entry(
                    name, source, system, registered, (value, kind), registry=(hive, view, backup_path),
                    target=target, can_change=valid and (system or identity != autostart.VALUE_NAME.casefold()),
                )
    return items.values()


def _command_path(command, expand):
    match = re.match(r'\s*(?:"([^"]+)"|([^\s"]+))', command)
    if not match:
        return ""
    target = match[1] or match[2]
    if expand:
        target = os.path.expandvars(target)
    # In an unquoted command containing spaces, Windows may choose multiple executable names.
    if not match[1] and Path(target).suffix.casefold() not in (".exe", ".com", ".bat", ".cmd"):
        return ""
    return target if Path(target).is_absolute() else ""


def _holding_folder(folder):
    return folder.with_name(folder.name + ".hub-disabled")


def _file_snapshot(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or fileguard.is_link(info):
        raise StartupError(tr("The entry is a link or an unsupported file.",
                              "Запись является ссылкой или неподдерживаемым файлом."))
    return fileguard.identity(info)


def _folder_items(folder, system):
    if not _fixed_path(folder):
        raise StartupError(tr("Startup folder is not on a local fixed drive.",
                              "Папка автозагрузки находится вне локального фиксированного диска."))
    source = tr("Startup · All users", "Startup · Все пользователи") if system else tr(
        "Startup · Current user", "Startup · Текущий пользователь")
    items = {}
    for directory, registered in ((folder, True), (_holding_folder(folder), False)):
        try:
            parents = fileguard.parents(directory)
        except FileNotFoundError:
            continue
        for path in directory.iterdir():
            if path.name.casefold() == "desktop.ini":
                continue
            try:
                info = path.lstat()
            except OSError:
                continue
            link = stat.S_ISLNK(info.st_mode) or fileguard.is_link(info)
            if stat.S_ISDIR(info.st_mode) and not link:
                continue
            identity = path.name.casefold()
            if identity in items:
                items[identity] = replace(items[identity], conflict=True)
                continue
            regular = stat.S_ISREG(info.st_mode) and not link
            direct = path.suffix.lower() in (".exe", ".com", ".cmd", ".bat")
            items[identity] = Entry(path.name, source, system, registered,
                                    (parents, fileguard.identity(info)), folder=folder,
                                    target=str(path) if direct and regular else "", can_change=regular)
    return items.values()


def _shortcut_targets(entries):
    links = [str((entry.folder if entry.registered else _holding_folder(entry.folder)) / entry.name)
             for entry in entries if entry.folder and entry.can_change and entry.name.lower().endswith(".lnk")]
    if not links:
        return {}
    script = """
$ErrorActionPreference = 'Stop'
$payload = [Console]::In.ReadToEnd()
$shell = New-Object -ComObject WScript.Shell
$result = @{}
foreach ($path in (ConvertFrom-Json -InputObject $payload)) {
    try { $result[$path] = $shell.CreateShortcut($path).TargetPath } catch {}
}
$response = ConvertTo-Json -InputObject $result -Compress
[Console]::OutputEncoding = [Text.Encoding]::UTF8
[Console]::Write($response)
"""
    executable = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    try:
        result = subprocess.run(
            [str(executable), "-NoProfile", "-NonInteractive", "-Command", script],
            input=json.dumps(links).encode("ascii"), capture_output=True, check=True,
            timeout=10, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        values = json.loads(result.stdout)
        return {key: values[key] for key in links if isinstance(values.get(key), str)}
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        return {}


def _file_metadata(path):
    from System.Diagnostics import FileVersionInfo

    try:
        target = Path(path)
        if not _fixed_path(target):
            return False, ""
        fileguard.parents(target.parent)
        _file_snapshot(target)
    except (ValueError, OSError, fileguard.GuardError, StartupError):
        return False, ""
    try:
        return True, str(FileVersionInfo.GetVersionInfo(str(target)).CompanyName or "")
    except Exception:
        return True, ""  # Metadata may be missing in a valid executable.


def snapshot():
    if not autostart.supported():
        return [], []
    entries, errors = [], []
    for source in _registry_sources():
        try:
            entries.extend(_registry_items(*source))
        except OSError:
            errors.append(source[0])
    for folder, system in _folders():
        try:
            entries.extend(_folder_items(folder, system))
        except (OSError, fileguard.GuardError, StartupError):
            errors.append(str(folder))
    seen_links = _shortcut_targets(entries)
    result = []
    metadata = {}
    for entry in entries:
        target = entry.target
        if entry.folder and entry.name.lower().endswith(".lnk"):
            directory = entry.folder if entry.registered else _holding_folder(entry.folder)
            target = seen_links.get(str(directory / entry.name), "")
        if target and target not in metadata:
            metadata[target] = _file_metadata(target)
        available, company = metadata.get(target, (False, ""))
        result.append(replace(entry, target=target, company=company, target_available=available))
    return result, errors


def _set_registry(entry):
    import winreg

    hive, view, backup = entry.registry
    original = autostart.RUN_KEY
    source_path, target_path = (original, backup) if entry.registered else (backup, original)
    access = winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE | view
    with winreg.OpenKey(hive, source_path, 0, access) as source:
        value = winreg.QueryValueEx(source, entry.name)
        if value != entry.snapshot:
            raise StartupError(tr("The entry changed. Refresh the list.", "Запись изменилась. Обнови список."))
        with winreg.CreateKeyEx(hive, target_path, 0, access) as target:
            try:
                existing = winreg.QueryValueEx(target, entry.name)
            except FileNotFoundError:
                winreg.SetValueEx(target, entry.name, 0, value[1], value[0])
            else:
                if existing != value:
                    raise FileExistsError(entry.name)
            winreg.FlushKey(target)
            if winreg.QueryValueEx(source, entry.name) != value:
                raise StartupError(tr("The entry changed. Refresh the list.", "Запись изменилась. Обнови список."))
            winreg.DeleteValue(source, entry.name)


def _set_file(entry):
    folder = entry.folder
    holding = _holding_folder(folder)
    fileguard.parents(folder)
    if entry.registered:
        holding.mkdir(exist_ok=True)
    fileguard.parents(holding)
    source_dir, target_dir = (folder, holding) if entry.registered else (holding, folder)
    source, target = source_dir / entry.name, target_dir / entry.name
    if (fileguard.parents(source_dir), _file_snapshot(source)) != entry.snapshot:
        raise StartupError(tr("The file changed. Refresh the list.", "Файл изменился. Обнови список."))
    source.rename(target)  # On Windows this fails if the destination already exists.


def toggle(entry):
    """Use a listed entry. Hub accepts no commands or new targets for startup."""
    if not autostart.supported() or not entry.can_change or entry.conflict:
        raise StartupError(tr("This entry can't be changed in Hub.", "Эту запись нельзя изменить в Hub."))
    if entry.system and not is_admin():
        raise StartupError(tr("Administrator rights are required.", "Нужны права администратора."))
    with _lock:
        try:
            if entry.registry:
                _set_registry(entry)
            else:
                _set_file(entry)
        except FileExistsError as exc:
            raise StartupError(tr("An entry already exists at the destination.",
                                  "Запись с таким именем уже существует в месте назначения.")) from exc
        except (OSError, fileguard.GuardError) as exc:
            raise StartupError(tr("Windows couldn't change the entry. Refresh and check access.",
                                  "Windows не смогла изменить запись. Обнови список и проверь права.")) from exc
