"""Перенос и хранение настроек настольного Hub."""

import json
import re
import shutil
import stat
import tempfile
import threading
from pathlib import Path

from tools import paths

OPTIONS = {
    "hub-theme": {"light", "dark"},
    "hub-style": {"glass", "material"},
    "hub-motion": {"on", "off"},
    "hub-glass": {"on", "off"},
    "desktop-glass": {"on", "off"},
    "hub-sound": {"on", "off"},
    "hub-accent": {"", "emerald", "ocean", "sunset", "pink"},
    "hub-onboarded": {"1"},
    "tray": {"on", "off"},
}
_lock = threading.RLock()


def read() -> dict:
    filename = paths.DATA_DIR / "preferences.json"
    with _lock:
        try:
            settings = json.loads(filename.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return {}
        return settings if isinstance(settings, dict) else {}


def update(values: dict) -> dict:
    with _lock:
        settings = read()
        settings.update({
            key: value for key, value in values.items()
            if isinstance(value, str) and (
                value in OPTIONS.get(key, ()) or
                key == "hub-release-seen" and re.fullmatch(r"\d{1,5}(?:\.\d{1,5}){2,4}", value)
            )
        })
        filename = paths.DATA_DIR / "preferences.json"
        temporary = filename.with_suffix(".tmp")
        temporary.write_text(json.dumps(settings), encoding="utf-8")
        temporary.replace(filename)
        return settings


def migrate(old_root: Path, target: Path) -> None:
    source = (old_root / "data").resolve(strict=True)
    if not (old_root / "server.py").is_file() or not source.is_dir():
        raise ValueError("Выбери папку старого Hub, в которой лежат server.py и data.")
    if target.exists():
        raise FileExistsError("У настольного Hub уже есть данные. Перенос отменён, чтобы их сохранить.")

    def ignore(folder, names):
        ignored = []
        for name in names:
            entry = (Path(folder) / name).lstat()
            if name.endswith((".lock", ".tmp")) or stat.S_ISLNK(entry.st_mode) or (
                getattr(entry, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            ):
                ignored.append(name)
        return ignored

    with tempfile.TemporaryDirectory(dir=target.parent, prefix="import-") as temporary:
        staged = Path(temporary) / "data"
        shutil.copytree(source, staged, ignore=ignore)
        for journal in staged.glob("trash/*/journal.json"):
            run = journal.relative_to(staged).parent
            old_files = source / run / "files"
            try:
                data = json.loads(journal.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if not isinstance(data, dict) or not isinstance(data.get("moved"), list):
                continue
            for item in data["moved"]:
                if not isinstance(item, dict) or not isinstance(item.get("to"), str):
                    continue
                stored = Path(item["to"])
                if stored.parent == old_files:
                    item["to"] = str(target / run / "files" / stored.name)
            journal.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        staged.rename(target)
