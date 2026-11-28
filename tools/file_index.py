"""Local searchable file index. Each root is published as one SQLite transaction."""

from __future__ import annotations

import fnmatch
import json
import os
import sqlite3
import stat
import time
from contextlib import closing
from pathlib import Path
from threading import Condition, Lock, Thread

from tools import fileguard, jobs, paths

PAGE_SIZE = 150
REFRESH_SECONDS = 120
MAX_DOCUMENT = 512 * 1024
TEXT_EXTENSIONS = frozenset(("txt", "md", "rst", "csv", "tsv", "log", "json", "xml"))
SKIP_NAMES = frozenset((".git", ".hg", ".venv", "node_modules", "__pycache__", "$recycle.bin",
                        "system volume information"))
FILE_TYPES = {
    "documents": TEXT_EXTENSIONS | {"pdf", "doc", "docx", "rtf", "odt"},
    "images": {"jpg", "jpeg", "png", "gif", "bmp", "webp", "heic", "svg"},
    "audio": {"aac", "mp3", "m4a", "wav", "wma", "ogg", "flac"},
    "video": {"mp4", "mkv", "mov", "avi", "webm", "wmv"},
    "archives": {"zip", "7z", "rar", "gz", "tar"},
}
ORDER = {
    "name": "f.name COLLATE NOCASE, f.path",
    "path": "f.path_key, f.path",
    "size": "f.size DESC, f.path",
    "modified": "f.modified DESC, f.path",
}
SCHEMA = """
CREATE TABLE roots(
    id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE, documents INTEGER NOT NULL,
    exclusions TEXT NOT NULL, indexed INTEGER
);
CREATE TABLE files(
    id INTEGER PRIMARY KEY, root INTEGER NOT NULL REFERENCES roots(id) ON DELETE CASCADE,
    path TEXT NOT NULL, name TEXT NOT NULL, path_key TEXT NOT NULL, extension TEXT NOT NULL,
    size INTEGER NOT NULL, modified INTEGER NOT NULL, stamp TEXT NOT NULL, body TEXT NOT NULL,
    UNIQUE(root, path)
);
CREATE INDEX files_extension ON files(extension);
CREATE VIRTUAL TABLE file_text USING fts5(path_key, body, content='files', content_rowid='id', tokenize='trigram');
CREATE TRIGGER files_insert AFTER INSERT ON files BEGIN
    INSERT INTO file_text(rowid,path_key,body) VALUES(new.id,new.path_key,new.body);
END;
CREATE TRIGGER files_delete AFTER DELETE ON files BEGIN
    INSERT INTO file_text(file_text,rowid,path_key,body) VALUES('delete',old.id,old.path_key,old.body);
END;
CREATE TRIGGER files_update AFTER UPDATE OF path_key,body ON files
WHEN old.path_key <> new.path_key OR old.body <> new.body BEGIN
    INSERT INTO file_text(file_text,rowid,path_key,body) VALUES('delete',old.id,old.path_key,old.body);
    INSERT INTO file_text(rowid,path_key,body) VALUES(new.id,new.path_key,new.body);
END;
PRAGMA user_version = 1;
"""
_schema_lock = Lock()


def database():
    return paths.DATA_DIR / "file-index.sqlite3"


def _connect():
    filename = database()
    filename.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(filename, timeout=5)
    try:
        with _schema_lock:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.executescript("BEGIN IMMEDIATE;\n" + SCHEMA + "\nCOMMIT;")
            elif version != 1:
                raise ValueError("Unsupported file index version / Неподдерживаемая версия индекса")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    except BaseException:
        conn.close()
        raise


def _root(path):
    folder = fileguard.local_path(path)
    if folder.is_relative_to(paths.DATA_DIR.resolve()):
        raise ValueError("Hub data is excluded from indexing / Данные Hub исключены из индексации")
    return fileguard.check_safe_folder(folder)


def roots():
    with closing(_connect()) as conn:
        return [{"id": row[0], "path": row[1], "documents": bool(row[2]),
                 "exclusions": json.loads(row[3]), "indexed": row[4]}
                for row in conn.execute("SELECT id,path,documents,exclusions,indexed FROM roots ORDER BY path")]


def save_root(path, documents, exclusions):
    folder = _root(path)
    patterns = [line.strip().replace("\\", "/").casefold() for line in exclusions.splitlines() if line.strip()]
    if len(patterns) > 50 or any(len(pattern) > 200 for pattern in patterns):
        raise ValueError("Too many or overly long exclusions / Слишком много исключений или длинная маска")
    serialized = json.dumps(patterns)
    with closing(_connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        for id_, raw, previous, old_patterns in conn.execute("SELECT id,path,documents,exclusions FROM roots"):
            other = Path(raw)
            if other == folder:
                if (previous, old_patterns) != (documents, serialized):
                    conn.execute("UPDATE roots SET documents=?, exclusions=?, indexed=NULL WHERE id=?",
                                 (bool(documents), serialized, id_))
                    conn.execute("DELETE FROM files WHERE root=?", (id_,))
                break
            if folder.is_relative_to(other) or other.is_relative_to(folder):
                raise ValueError("This folder overlaps another indexed folder / Эта папка пересекается с уже выбранной")
        else:
            conn.execute("INSERT INTO roots(path,documents,exclusions) VALUES(?,?,?)",
                         (str(folder), bool(documents), serialized))


def remove_root(identity):
    with closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM roots WHERE id=?", (identity,))


def _text(path, expected):
    with path.open("rb") as handle:
        opened = fileguard.identity(os.fstat(handle.fileno()))
        # A Windows write time can be refreshed when the file handle opens.
        if opened[:3] != expected[:3]:
            raise OSError("File changed before indexing")
        data = handle.read(MAX_DOCUMENT + 1)
        if fileguard.identity(os.fstat(handle.fileno())) != opened:
            raise OSError("File changed during indexing")
        if len(data) > MAX_DOCUMENT:
            return ""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        value = data.decode("utf-16", errors="replace")
    elif b"\0" in data:
        return ""
    else:
        value = data.decode("utf-8-sig", errors="replace")
    return value.casefold()


def _files(root, exclusions, check, error):
    protected = fileguard.get_system_directories() | {paths.DATA_DIR.resolve()}
    folders = [root]
    while folders:
        check()
        directory = folders.pop()
        try:
            fileguard.parents(directory)
            with os.scandir(directory) as children:
                for entry in children:
                    check()
                    path = Path(entry.path)
                    name = entry.name.casefold()
                    relative = path.relative_to(root).as_posix().casefold()
                    if (name in SKIP_NAMES or path in protected or
                            any(fnmatch.fnmatchcase(relative, pattern) or fnmatch.fnmatchcase(name, pattern)
                                for pattern in exclusions)):
                        continue
                    try:
                        info = entry.stat(follow_symlinks=False)
                    except OSError:
                        error()
                        continue
                    if stat.S_ISLNK(info.st_mode) or fileguard.is_link(info):
                        continue
                    if stat.S_ISDIR(info.st_mode):
                        folders.append(path)
                    elif stat.S_ISREG(info.st_mode):
                        yield path, info
        except (OSError, fileguard.GuardError):
            error()


def update(root, force, check, report, error):
    folder = _root(root["path"])
    with closing(_connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("CREATE TEMP TABLE seen(path TEXT PRIMARY KEY) WITHOUT ROWID")
        for path, info in _files(folder, root["exclusions"], check, error):
            raw = str(path)
            conn.execute("INSERT OR IGNORE INTO seen VALUES(?)", (raw,))
            fingerprint = fileguard.identity(info)
            stamp = ":".join(map(str, fingerprint))
            previous = conn.execute("SELECT stamp FROM files WHERE root=? AND path=?", (root["id"], raw)).fetchone()
            if force or previous != (stamp,):
                extension = path.suffix.casefold().lstrip(".")
                body = ""
                if root["documents"] and extension in TEXT_EXTENSIONS and 0 < info.st_size <= MAX_DOCUMENT:
                    try:
                        fileguard.parents(path.parent)
                        current = path.lstat()
                        if not stat.S_ISREG(current.st_mode) or fileguard.is_link(current):
                            raise OSError("File was replaced with a link")
                        body = _text(path, fileguard.identity(current))
                    except (OSError, fileguard.GuardError):
                        stamp = ""  # Retry the read on the next incremental pass.
                        error()
                conn.execute(
                    "INSERT INTO files(root,path,name,path_key,extension,size,modified,stamp,body) VALUES(?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(root,path) DO UPDATE SET size=excluded.size, modified=excluded.modified, "
                    "stamp=excluded.stamp, body=excluded.body",
                    (root["id"], raw, path.name, raw.casefold(), extension, info.st_size, int(info.st_mtime), stamp, body),
                )
            report()
        check()
        conn.execute("DELETE FROM files WHERE root=? AND path NOT IN (SELECT path FROM seen)", (root["id"],))
        conn.execute("UPDATE roots SET indexed=? WHERE id=?", (int(time.time()), root["id"]))
        check()


def search(query, *, extension="", kind="", min_size=0, max_size=None, after=None, before=None,
           contents=False, sort="name", offset=0):
    query = query.strip().casefold()
    extension = extension.strip().casefold().lstrip(".")
    where, args = ["f.size >= ?"], [min_size]
    table = "files AS f"
    if len(query) >= 3:
        table += " JOIN file_text ON file_text.rowid=f.id"
        where.append("file_text MATCH ?")
        phrase = '"' + query.replace('"', '""') + '"'
        args.append(phrase if contents else "path_key:" + phrase)
    elif query:
        where.append("(instr(f.path_key, ?) > 0 OR instr(f.body, ?) > 0)" if contents else "instr(f.path_key, ?) > 0")
        args.extend([query] * (2 if contents else 1))
    if extension:
        where.append("f.extension = ?")
        args.append(extension)
    if max_size is not None:
        where.append("f.size <= ?")
        args.append(max_size)
    if kind in FILE_TYPES:
        extensions = sorted(FILE_TYPES[kind])
        where.append("f.extension IN (" + ",".join("?" for _ in extensions) + ")")
        args.extend(extensions)
    if after is not None:
        where.append("f.modified >= ?")
        args.append(after)
    if before is not None:
        where.append("f.modified < ?")
        args.append(before)
    sql = (f"SELECT f.path,f.name,f.extension,f.size,f.modified FROM {table} WHERE {' AND '.join(where)} "
           f"ORDER BY {ORDER.get(sort, ORDER['name'])} LIMIT ? OFFSET ?")
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        results = [dict(row) for row in conn.execute(sql, (*args, PAGE_SIZE + 1, max(0, offset)))]
    return results[:PAGE_SIZE], len(results) > PAGE_SIZE


def existing_file(raw):
    path = Path(raw)
    _root(path.parent)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or fileguard.is_link(info):
        raise ValueError("The file moved or became unavailable / Файл перемещён или недоступен")
    return str(path)


class Indexer:
    def __init__(self):
        self.condition = Condition()
        self.thread = None
        self.pending = self.force = self.paused = self.cancelled = self.closed = False
        self.progress = {"state": "idle", "files": 0, "errors": 0}
        self.revision = 0

    def start(self):
        with self.condition:
            if self.thread is None and not self.closed:
                self.thread = Thread(target=self._loop, daemon=True, name="hub-file-index")
                self.thread.start()

    def request(self, rebuild=False):
        self.start()
        with self.condition:
            self.pending = True
            self.force |= rebuild
            self.condition.notify()

    def pause(self, value):
        with self.condition:
            self.paused = value
            self.condition.notify()

    def cancel(self):
        with self.condition:
            self.cancelled = True
            self.pending = self.force = False
            self.condition.notify()

    def status(self):
        with self.condition:
            return {**self.progress, "paused": self.paused, "pending": self.pending, "revision": self.revision}

    def shutdown(self):
        with self.condition:
            self.closed = True
            self.condition.notify()
        if self.thread:
            self.thread.join(timeout=2)

    def _loop(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.closed or self.pending and not self.paused,
                                        timeout=REFRESH_SECONDS)
                self.condition.wait_for(lambda: self.closed or not self.paused)
                if self.closed:
                    return
                force, self.force, self.pending, self.cancelled = self.force, False, False, False
                self.progress = {"state": "running", "files": 0, "errors": 0}
            counts = {"files": 0, "errors": 0}

            def check():
                with self.condition:
                    if self.paused:
                        self.condition.wait_for(lambda: self.cancelled or self.closed or not self.paused)
                    if self.cancelled or self.closed:
                        raise jobs.Cancelled()

            def report():
                counts["files"] += 1
                if counts["files"] % 128 == 0:
                    with self.condition:
                        self.progress.update(counts)

            def error():
                counts["errors"] += 1

            state = "done"
            try:
                for root in roots():
                    check()
                    try:
                        update(root, force, check, report, error)
                    except (OSError, fileguard.GuardError, ValueError):
                        error()
            except jobs.Cancelled:
                state = "cancelled"
            except (sqlite3.Error, ValueError, OSError):
                state = "error"
            with self.condition:
                self.progress.update(counts, state=state)
                if state == "done":
                    self.revision += 1


indexer = Indexer()
