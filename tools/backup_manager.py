"""Versioned, content-addressed local backups with an atomic SQLite manifest."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import sqlite3
import stat
import tempfile
import time
from contextlib import closing, contextmanager
from pathlib import Path
from threading import Event, Lock, Thread
from uuid import uuid4

from tools import fileguard, jobs, paths
from tools.i18n import tr

BLOCK = 1024 * 1024
_lock = Lock()
_profile_lock = Lock()
_active = None
_digest = re.compile(r"[0-9a-f]{64}\Z")
_profile_id = re.compile(r"[0-9a-f]{32}\Z")
_reserved = re.compile(r"(?i)(?:con|conin\$|conout\$|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\.|$)")
_metadata = """
CREATE TABLE IF NOT EXISTS versions(
    id INTEGER PRIMARY KEY AUTOINCREMENT, created INTEGER NOT NULL, files INTEGER NOT NULL,
    bytes INTEGER NOT NULL, copied INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS manifest(
    version INTEGER REFERENCES versions(id) ON DELETE CASCADE, path TEXT NOT NULL, kind TEXT NOT NULL,
    size INTEGER NOT NULL, stamp TEXT NOT NULL, digest TEXT NOT NULL,
    PRIMARY KEY(version, path)
);
CREATE INDEX IF NOT EXISTS manifest_digest ON manifest(digest);
"""


class BackupError(RuntimeError):
    pass


class BackupBusy(BackupError):
    pass


def _folder(path):
    return fileguard.check_safe_folder(fileguard.local_path(path))


def _regular(path):
    fileguard.parents(path.parent)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or fileguard.is_link(info):
        raise BackupError(tr("An expected regular file is a link or a special file.",
                             "По ожидаемому пути находится ссылка или специальный файл."))
    return info


def _source(raw):
    path = fileguard.local_path(raw)
    fileguard.parents(path.parent)
    info = path.lstat()
    if fileguard.is_link(info) or stat.S_ISLNK(info.st_mode) or fileguard.is_system_path(path):
        raise BackupError(tr("A selected source is protected or redirected.", "Выбранный источник защищён или перенаправлен."))
    if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
        raise BackupError(tr("Select files or folders.", "Выбери файлы или папки."))
    return path


def _profile_db():
    paths.DATA_DIR.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(paths.DATA_DIR / "backup-profiles.sqlite3", timeout=5)
    database.execute("CREATE TABLE IF NOT EXISTS profiles(id TEXT PRIMARY KEY, payload TEXT NOT NULL, attempted INTEGER, error TEXT)")
    return database


def profiles():
    with _profile_lock, closing(_profile_db()) as db:
        return [{**json.loads(raw), "id": identity, "attempted": attempt, "error": error}
                for identity, raw, attempt, error in db.execute("SELECT * FROM profiles ORDER BY rowid")]


def save_profile(identity, name, sources, destination, exclusions, keep_days, interval):
    name = name.strip()
    if not name or len(name) > 100 or not sources:
        raise BackupError(tr("Enter a name and select sources.", "Укажи имя профиля и выбери источники."))
    if not 0 <= keep_days <= 36500 or not 0 <= interval <= 8760:
        raise BackupError(tr("Check retention and the schedule interval.", "Проверь срок хранения и интервал расписания."))
    identity = identity or uuid4().hex
    if not _profile_id.fullmatch(identity):
        raise BackupError(tr("Invalid backup profile.", "Некорректный профиль резервного копирования."))
    destination = _folder(destination)
    managed = destination / "Hub Backups"
    source_paths = list(dict.fromkeys(_source(path) for path in sources))
    seen = set()
    for source in source_paths:
        if source.is_relative_to(managed) or managed.is_relative_to(source):
            raise BackupError(tr("The backup repository overlaps a source.", "Хранилище резервных копий пересекается с источником."))
        if any(source.is_relative_to(parent) or parent.is_relative_to(source) for parent in seen):
            raise BackupError(tr("Sources must not overlap.", "Источники не должны пересекаться."))
        seen.add(source)
    exclusions = [pattern.strip().replace("\\", "/").casefold() for pattern in exclusions if pattern.strip()]
    if len(exclusions) > 50 or any(len(pattern) > 200 for pattern in exclusions):
        raise BackupError(tr("Too many or overly long exclusions.", "Слишком много исключений или длинная маска."))
    payload = {"name": name, "sources": list(map(str, source_paths)), "destination": str(destination),
               "exclusions": exclusions, "keep_days": keep_days, "interval": interval}
    with _profile_lock, closing(_profile_db()) as db, db:
        db.execute("INSERT INTO profiles(id,payload) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                   (identity, json.dumps(payload, ensure_ascii=False)))
    return identity


def _managed_directory(parent, part, create):
    location = parent / part
    if create:
        location.mkdir(exist_ok=True)
    fileguard.parents(location)
    return location


def _repository(profile, create=False):
    if not _profile_id.fullmatch(profile["id"]):
        raise BackupError(tr("Invalid backup profile.", "Некорректный профиль резервного копирования."))
    destination = _folder(profile["destination"])
    profile_dir = _managed_directory(_managed_directory(destination, "Hub Backups", create), profile["id"], create)
    return profile_dir, _managed_directory(profile_dir, "blocks", create)


def _open_manifest(folder, create=False):
    base = folder / "manifest.sqlite3"
    for name in (base, base.with_suffix(".sqlite3-journal"), base.with_suffix(".sqlite3-wal"), base.with_suffix(".sqlite3-shm")):
        if os.path.lexists(name):
            _regular(name)
    if not create and not base.is_file():
        raise FileNotFoundError(base)
    conn = sqlite3.connect(base, timeout=5)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        if create:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(_metadata)
        conn.row_factory = sqlite3.Row
        return conn
    except BaseException:
        conn.close()
        raise


def history(profile):
    try:
        repo, _ = _repository(profile)
        with closing(_open_manifest(repo)) as db:
            return [dict(row) for row in db.execute("SELECT * FROM versions ORDER BY id DESC")]
    except FileNotFoundError:
        return []


@contextmanager
def _job(control):
    global _active
    if not _lock.acquire(blocking=False):
        raise BackupBusy(tr("Another backup operation is running.", "Уже выполняется операция резервного копирования."))
    _active = control
    try:
        control.check()
        yield
    finally:
        _active = None
        _lock.release()


def active_job():
    return _active


def _parts(value):
    parts = value.split("/")
    if any(not part or part in (".", "..") or part.endswith((" ", ".")) or _reserved.match(part) or
           any(char in '\\:*?"<>|' or ord(char) < 32 for char in part) for part in parts):
        raise BackupError(tr("A manifest contains an unsafe file name.", "Манифест содержит небезопасное имя файла."))
    return parts


def _archive_items(profile, control):
    names = set()
    protected = fileguard.get_system_directories()
    managed = Path(profile["destination"]) / "Hub Backups"
    for raw in profile["sources"]:
        root = _source(raw)
        if root.is_relative_to(managed) or managed.is_relative_to(root):
            raise BackupError(tr("The repository overlaps a source.", "Хранилище пересекается с источником."))
        name = root.name
        index = 2
        while name.casefold() in names:
            name = f"{root.name} ({index})"
            index += 1
        names.add(name.casefold())
        pending = [(root, name)]
        while pending:
            control.check()
            path, relative = pending.pop()
            if path in protected or any(fnmatch.fnmatchcase(relative.casefold(), pattern)
                                        or fnmatch.fnmatchcase(path.name.casefold(), pattern)
                                        for pattern in profile["exclusions"]):
                continue
            _parts(relative)
            fileguard.parents(path.parent)
            info = path.lstat()
            if fileguard.is_link(info) or stat.S_ISLNK(info.st_mode):
                continue
            if stat.S_ISREG(info.st_mode):
                yield path, relative, "file", info
            elif stat.S_ISDIR(info.st_mode):
                yield path, relative, "folder", info
                with os.scandir(path) as entries:
                    pending.extend((Path(item.path), relative + "/" + item.name) for item in entries)


def _transfer(path, expected, output, control, target_hash=None):
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        opened = fileguard.identity(os.fstat(source.fileno()))
        if opened[:3] != expected[:3]:
            raise BackupError(tr("A file changed before reading it.", "Файл изменился до начала чтения."))
        while chunk := source.read(BLOCK):
            control.check()
            checksum.update(chunk)
            if output is not None:
                output.write(chunk)
        if fileguard.identity(os.fstat(source.fileno())) != opened:
            raise BackupError(tr("A file changed while reading it.", "Файл изменился во время чтения."))
    digest = checksum.hexdigest()
    if target_hash is not None and target_hash != digest:
        raise BackupError(tr("A backup checksum does not match.", "Контрольная сумма резервной копии не совпадает."))
    return digest


def _blob(blocks, digest):
    if not _digest.fullmatch(digest):
        raise BackupError(tr("A manifest contains an invalid checksum.", "Манифест содержит некорректную контрольную сумму."))
    path = blocks / digest
    return path, _regular(path)


def _publish_new(temporary, destination):
    if os.name == "nt":
        temporary.rename(destination)
    else:
        os.link(temporary, destination)


def _store_file(path, info, blocks, control, published):
    fileguard.parents(blocks)
    staged = tempfile.NamedTemporaryFile(dir=blocks, prefix=".copy-", suffix=".tmp", delete=False)
    temp = Path(staged.name)
    try:
        with staged:
            digest = _transfer(path, fileguard.identity(info), staged, control)
            staged.flush()
            os.fsync(staged.fileno())
        destination = blocks / digest
        control.check()
        if os.path.lexists(destination):
            _transfer(destination, fileguard.identity(_regular(destination)), None, control, digest)
            return digest, 0
        _publish_new(temp, destination)
        published.add(destination)
        return digest, info.st_size
    finally:
        temp.unlink(missing_ok=True)


def _expire(db, profile, identity):
    if not profile["keep_days"]:
        return ()
    older = time.time() - profile["keep_days"] * 86400
    digests = tuple(row[0] for row in db.execute(
        "SELECT DISTINCT digest FROM manifest JOIN versions ON versions.id=manifest.version "
        "WHERE versions.created < ? AND versions.id <> ? AND digest <> ''", (older, identity)))
    db.execute("DELETE FROM versions WHERE created < ? AND id <> ?", (older, identity))
    return tuple(value for value in digests if not db.execute("SELECT 1 FROM manifest WHERE digest=? LIMIT 1", (value,)).fetchone())


def create(profile, control):
    with _job(control):
        published = set()
        repo, blocks = _repository(profile, create=True)
        expired = ()
        committed = False
        try:
            with closing(_open_manifest(repo, create=True)) as db, db:
                previous = db.execute("SELECT max(id) FROM versions").fetchone()[0]
                identity = db.execute("INSERT INTO versions(created,files,bytes,copied) VALUES(?,0,0,0)",
                                      (int(time.time()),)).lastrowid
                files = size = copied = seen = 0
                for source, name, kind, info in _archive_items(profile, control):
                    stamp = ":".join(map(str, fileguard.identity(info)))
                    stored, file_size = "", 0
                    if kind == "file":
                        old = db.execute("SELECT digest,stamp,size FROM manifest WHERE version=? AND path=?",
                                         (previous, name)).fetchone()
                        if old and old["stamp"] == stamp:
                            try:
                                _, existing = _blob(blocks, old["digest"])
                                if existing.st_size == old["size"]:
                                    stored = old["digest"]
                            except FileNotFoundError:
                                pass
                        if not stored:
                            stored, added = _store_file(source, info, blocks, control, published)
                            copied += added
                        file_size = info.st_size
                        size += file_size
                        files += 1
                    db.execute("INSERT INTO manifest VALUES(?,?,?,?,?,?)", (identity, name, kind, file_size, stamp, stored))
                    seen += 1
                    control.report(seen, files, size)
                if not seen:
                    raise BackupError(tr("No selected items could be backed up.", "Нет выбранных объектов для резервного копирования."))
                control.check()
                db.execute("UPDATE versions SET files=?,bytes=?,copied=? WHERE id=?", (files, size, copied, identity))
                expired = _expire(db, profile, identity)
                control.check()
                db.commit()
                committed = True
        except BaseException:
            if not committed:
                for block in published:
                    try:
                        block.unlink(missing_ok=True)
                    except OSError:
                        pass
            raise
        for digest in expired:
            try:
                _blob(blocks, digest)[0].unlink()
            except (OSError, fileguard.GuardError, BackupError):
                pass  # The new backup is already committed. Stale blocks can remain safely.
        return identity


def _entries(db, version):
    if not db.execute("SELECT 1 FROM versions WHERE id=?", (version,)).fetchone():
        raise BackupError(tr("Backup version not found.", "Версия резервной копии не найдена."))
    for item in db.execute("SELECT path,kind,size,digest FROM manifest WHERE version=? ORDER BY path", (version,)):
        _parts(item["path"])
        digest, size = item["digest"], item["size"]
        valid = (item["kind"] == "file" and type(size) is int and size >= 0 and isinstance(digest, str)
                 and bool(_digest.fullmatch(digest)) or
                 item["kind"] == "folder" and size == 0 and not digest)
        if not valid:
            raise BackupError(tr("A manifest contains an invalid entry.", "Манифест содержит некорректную запись."))
        yield item


def verify(profile, version, control):
    with _job(control):
        repo, blocks = _repository(profile)
        with closing(_open_manifest(repo)) as db:
            checked = set()
            size = 0
            for item in _entries(db, version):
                control.check()
                if item["kind"] != "file" or item["digest"] in checked:
                    continue
                path, info = _blob(blocks, item["digest"])
                if info.st_size != item["size"]:
                    raise BackupError(tr("A backup block has the wrong size.", "Размер блока резервной копии не совпадает."))
                _transfer(path, fileguard.identity(info), None, control, item["digest"])
                checked.add(item["digest"])
                size += info.st_size
                control.report(len(checked), len(checked), size)
        return len(checked)


def _target(base, relative, create=False):
    parts = _parts(relative)
    path = base
    fileguard.parents(path)
    for name in parts[:-1]:
        path /= name
        if not os.path.lexists(path):
            if not create:
                return base.joinpath(*parts)
            path.mkdir()
        fileguard.parents(path)
    return path / parts[-1]


def _destination_stamp(path, kind):
    if not os.path.lexists(path):
        return None
    info = path.lstat()
    expected = stat.S_ISREG if kind == "file" else stat.S_ISDIR
    if fileguard.is_link(info) or not expected(info.st_mode):
        raise BackupError(tr("A restore path conflicts with a link or file of another type.",
                             "Путь восстановления занят ссылкой или объектом другого типа."))
    return fileguard.identity(info)


def preview(profile, version, directory, control):
    base = _folder(directory)
    repo, _ = _repository(profile)
    if base.is_relative_to(repo) or repo.is_relative_to(base):
        raise BackupError(tr("Select a restore folder outside the backup repository.",
                             "Выбери папку восстановления вне хранилища резервных копий."))
    records = []
    seen = set()
    with _job(control), closing(_open_manifest(repo)) as db:
        for item in _entries(db, version):
            control.check()
            name, kind = item["path"], item["kind"]
            if name.casefold() in seen or kind not in ("file", "folder"):
                raise BackupError(tr("The manifest contains conflicting entries.", "В манифесте конфликтующие записи."))
            seen.add(name.casefold())
            path = _target(base, name)
            records.append({**dict(item), "original": _destination_stamp(path, kind)})
    return str(base), fileguard.parents(base), records


def restore(profile, plan, control):
    base, identity, records = plan
    base = _folder(base)
    with _job(control):
        if fileguard.parents(base) != identity:
            raise BackupError(tr("The restore folder changed. Preview again.", "Папка восстановления изменилась. Построй план снова."))
        _, blocks = _repository(profile)
        files = size = 0
        for index, item in enumerate(records, 1):
            control.check()
            path = _target(base, item["path"], create=True)
            kind = item["kind"]
            existing = _destination_stamp(path, kind)
            if existing != item["original"]:
                raise BackupError(tr("A restore destination changed. Preview again.",
                                     "Место восстановления изменилось. Построй план снова."))
            if kind == "folder":
                if existing is None:
                    path.mkdir()
                continue
            source, info = _blob(blocks, item["digest"])
            if info.st_size != item["size"]:
                raise BackupError(tr("A backup block has the wrong size.", "Размер блока резервной копии не совпадает."))
            known_parents = fileguard.parents(path.parent)
            staged = tempfile.NamedTemporaryFile(dir=path.parent, prefix=".hub-restore-", suffix=".tmp", delete=False)
            temp = Path(staged.name)
            try:
                with staged:
                    _transfer(source, fileguard.identity(info), staged, control, item["digest"])
                    staged.flush()
                    os.fsync(staged.fileno())
                control.check()
                if fileguard.parents(path.parent) != known_parents or _destination_stamp(path, kind) != existing:
                    raise BackupError(tr("A restore destination changed. Preview again.",
                                         "Место восстановления изменилось. Построй план снова."))
                if existing is not None:
                    temp.replace(path)
                else:
                    _publish_new(temp, path)
            finally:
                temp.unlink(missing_ok=True)
            files += 1
            size += info.st_size
            control.report(index, files, size)
        return files


def run_backup(profile, control):
    message = ""
    try:
        return create(profile, control)
    except BackupBusy:
        message = None
        raise
    except jobs.Cancelled:
        message = "cancelled"
        raise
    except Exception:
        message = "failed"
        raise
    finally:
        if message is not None:
            try:
                with _profile_lock, closing(_profile_db()) as db, db:
                    db.execute("UPDATE profiles SET attempted=?,error=? WHERE id=?", (int(time.time()), message, profile["id"]))
            except (OSError, sqlite3.Error):
                pass  # History on the destination remains authoritative if local settings are unavailable.


class Scheduler:
    def __init__(self):
        self.stop = Event()
        self.thread = None

    def start(self):
        self.thread = Thread(target=self._run, daemon=True, name="hub-backup-scheduler")
        self.thread.start()

    def shutdown(self):
        self.stop.set()
        job = active_job()
        if job:
            job.cancelled.set()
        if self.thread:
            self.thread.join(timeout=2)

    def _run(self):
        while not self.stop.is_set():
            if (paths.DATA_DIR / "backup-profiles.sqlite3").is_file() and not _lock.locked():
                try:
                    now = time.time()
                    for profile in profiles():
                        if self.stop.is_set():
                            return
                        if profile["interval"] and (profile["attempted"] is None or
                                                     now - profile["attempted"] >= profile["interval"] * 3600):
                            try:
                                run_backup(profile, jobs.Job(float("inf")))
                            except Exception:
                                pass
                except Exception:
                    pass  # The last attempt is exposed in the profile even if another destination is offline.
            self.stop.wait(30)


scheduler = Scheduler()
