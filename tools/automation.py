"""Saved workflows composed of Hub operations, with a native local scheduler."""

from __future__ import annotations

import base64
import json
import os
import sqlite3
import stat
import time
from contextlib import closing
from pathlib import Path
from threading import Condition, Event, Lock, Thread
from uuid import uuid4

from tools import backup_manager, cleanup, fileguard, filesorter, images, jobs, paths
from tools.i18n import tr

ACTIONS = ("scan-old", "trash-selected", "sort", "compress", "backup")
CONDITIONS = ("always", "has-results", "no-results")
TRIGGERS = ("manual", "schedule", "folder")
_IMAGE_EXTENSIONS = frozenset((".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"))
_database_lock = Lock()


class WorkflowError(RuntimeError):
    pass


def database():
    return paths.DATA_DIR / "workflows.sqlite3"


def _connect():
    filename = database()
    filename.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(filename, timeout=5)
    conn.executescript(
        "CREATE TABLE IF NOT EXISTS workflows(id TEXT PRIMARY KEY, spec TEXT NOT NULL, last_run INTEGER);"
        "CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, workflow TEXT NOT NULL,"
        " time INTEGER NOT NULL, state TEXT NOT NULL, steps TEXT NOT NULL);"
    )
    return conn


def normalize(spec):
    if not isinstance(spec, dict) or not isinstance(spec.get("name"), str) or not spec["name"].strip():
        raise WorkflowError(tr("Enter a workflow name.", "Укажи имя сценария."))
    sequence = spec.get("steps")
    if not isinstance(sequence, list) or not 1 <= len(sequence) <= 40 or len(spec["name"]) > 120:
        raise WorkflowError(tr("A workflow needs between 1 and 40 steps.", "В сценарии должно быть от 1 до 40 шагов."))
    steps = []
    for value in sequence:
        if not isinstance(value, dict) or value.get("action") not in ACTIONS or value.get("when", "always") not in CONDITIONS:
            raise WorkflowError(tr("A step action or condition is not supported.", "Действие или условие шага не поддерживается."))
        action = value["action"]
        source, target = value.get("source", ""), value.get("target", "")
        age = value.get("age", 30)
        if (not isinstance(source, str) or not source.strip() or len(source) > 1024 or
                not isinstance(target, str) or len(target) > 1024 or action == "compress" and not target.strip() or
                type(age) is not int or not 0 <= age <= cleanup.MAX_AGE_DAYS):
            raise WorkflowError(tr("Check the paths, profile, and age in this step.", "Проверь пути, профиль и возраст файлов в шаге."))
        steps.append({"action": action, "source": source.strip(), "target": target.strip(),
                      "age": age, "when": value.get("when", "always")})
    mode = spec.get("trigger", "manual")
    interval, watch = spec.get("interval", 60), spec.get("watch", "")
    enabled = spec.get("enabled", False)
    if (mode not in TRIGGERS or type(interval) is not int or not 1 <= interval <= 525600 or type(enabled) is not bool or
            not isinstance(watch, str) or len(watch) > 1024 or mode == "folder" and not watch.strip()):
        raise WorkflowError(tr("Check the workflow trigger.", "Проверь условие запуска сценария."))
    if enabled and mode != "manual" and any(step["action"] == "trash-selected" for step in steps):
        raise WorkflowError(tr("Trash steps require a manual run and confirmed files.",
                               "Перенос в корзину требует ручного запуска и подтверждения выбранных файлов."))
    if enabled and mode == "folder" and any(step["action"] == "compress" and
                                             Path(step["target"]) == Path(watch) for step in steps):
        raise WorkflowError(tr("Choose an output folder outside the watched folder.",
                               "Выбери папку результата вне наблюдаемой папки."))
    return {"name": spec["name"].strip(), "steps": steps, "trigger": mode, "interval": interval,
            "watch": watch.strip(), "enabled": enabled}


def save(identity, spec):
    identity = identity or uuid4().hex
    data = normalize(spec)
    if data["enabled"] and data["trigger"] == "folder":
        _folder(data["watch"])
    with _database_lock, closing(_connect()) as db, db:
        db.execute("INSERT INTO workflows(id,spec) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET spec=excluded.spec",
                   (identity, json.dumps(data, ensure_ascii=False)))
    return identity


def workflows():
    with _database_lock, closing(_connect()) as db:
        return [{**json.loads(payload), "id": identity, "last_run": last}
                for identity, payload, last in db.execute("SELECT id,spec,last_run FROM workflows ORDER BY rowid")]


def history(identity):
    with _database_lock, closing(_connect()) as db:
        return [{"time": stamp, "state": state, "steps": json.loads(raw)}
                for stamp, state, raw in db.execute(
                    "SELECT time,state,steps FROM history WHERE workflow=? ORDER BY id DESC LIMIT 100", (identity,))]


def _log(identity, stamp, state, details):
    with _database_lock, closing(_connect()) as db, db:
        db.execute("UPDATE workflows SET last_run=? WHERE id=?", (stamp, identity))
        db.execute("INSERT INTO history(workflow,time,state,steps) VALUES(?,?,?,?)",
                   (identity, stamp, state, json.dumps(details, ensure_ascii=False)))
        db.execute("DELETE FROM history WHERE workflow=? AND id NOT IN ("
                   "SELECT id FROM history WHERE workflow=? ORDER BY id DESC LIMIT 100)", (identity, identity))


def _folder(raw):
    return fileguard.check_safe_folder(fileguard.local_path(raw))


def _regular(folder, control=None):
    with os.scandir(folder) as entries:
        for item in entries:
            if control:
                control.check()
            try:
                info = item.stat(follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISREG(info.st_mode) and not fileguard.is_link(info):
                yield Path(item.path), info


def _old(source, age, control, authorize=False):
    result = cleanup.scan(str(source), age, False, authorize=authorize, control=control)
    return [item for item in result["old"] if not item.get("unsafe")]


def _profile(source):
    matches = [profile for profile in backup_manager.profiles() if source in (profile["name"], profile["id"])]
    if len(matches) != 1:
        raise WorkflowError(tr("Backup profile not found or ambiguous.", "Профиль резервного копирования не найден или имя неоднозначно."))
    return matches[0]


def preview(spec, control):
    data = normalize(spec)
    summary, targets = [], {}
    for step in data["steps"]:
        control.check()
        action = step["action"]
        if action == "backup":
            profile = _profile(step["source"])
            details = profile["name"]
        else:
            source = _folder(step["source"])
            details = str(source)
            if action == "compress":
                target = _folder(step["target"])
                details += f" → {target}"
            elif action in ("scan-old", "trash-selected"):
                old = _old(source, step["age"], control)
                details += f" · {len(old)}"
                if action == "trash-selected":
                    for item in old:
                        path = Path(item["path"])
                        targets[str(path)] = (fileguard.identity(path.lstat()), fileguard.parents(path.parent))
            elif action == "sort":
                details += f" · {len(filesorter.scan(str(source))['items'])}"
        summary.append((action, step["when"], details))
    return summary, targets


def _perform(step, control, confirmed, changed, watch):
    action = step["action"]
    if action == "backup":
        backup_manager.run_backup(_profile(step["source"]), control)
        return 1
    source = _folder(step["source"])
    scope = changed if watch is not None and source == watch else None
    if action == "scan-old":
        return len(_old(source, step["age"], control))
    if action == "trash-selected":
        if not confirmed:
            return 0
        eligible = {item["path"] for item in _old(source, step["age"], control, authorize=True)}
        targets = []
        for raw, expected in confirmed.items():
            if raw in eligible:
                path = Path(raw)
                if (fileguard.identity(path.lstat()), fileguard.parents(path.parent)) != expected:
                    raise WorkflowError(tr("A selected file changed. Preview again.", "Выбранный файл изменился. Построй предпросмотр снова."))
                targets.append(raw)
        control.check()
        if not targets:
            return 0
        result = cleanup.remove(targets, "trash", confirmed=True, folder=str(source))
        if result["errors"]:
            raise WorkflowError(tr(f"Moved {result['removed_count']} files. Some files could not be moved.",
                                   f"Перенесено файлов: {result['removed_count']}. Некоторые файлы не удалось перенести."))
        return result["removed_count"]
    if action == "sort":
        entries = [item["path"] for item in filesorter.scan(str(source))["items"]
                   if scope is None or item["path"] in scope]
        control.check()
        result = filesorter.apply(str(source), entries)
        if result["errors"]:
            raise WorkflowError(tr(f"Sorted {result['moved_count']} files. Some files could not be sorted.",
                                   f"Отсортировано файлов: {result['moved_count']}. Некоторые файлы не удалось перенести."))
        return result["moved_count"]
    target = _folder(step["target"])
    if watch is not None and target == watch:
        raise WorkflowError(tr("Choose an output folder outside the watched folder.",
                               "Выбери папку результата вне наблюдаемой папки."))
    count = 0
    for path, _ in _regular(source, control):
        if path.suffix.casefold() not in _IMAGE_EXTENSIONS or scope is not None and str(path) not in scope:
            continue
        fileguard.parents(path.parent)
        info = path.lstat()
        if fileguard.is_link(info) or not stat.S_ISREG(info.st_mode):
            continue
        expected = fileguard.identity(info)
        with path.open("rb") as handle:
            if fileguard.identity(os.fstat(handle.fileno()))[:3] != expected[:3]:
                raise WorkflowError(tr("An image changed before reading it.", "Изображение изменилось до чтения."))
            image = images.process_image(path.name, handle, "WEBP", "webp", 80, 1920)
        control.check()
        images.save_image(str(target), image["name"], base64.b64encode(image["data"]).decode("ascii"))
        count += 1
    return count


class Runner:
    def __init__(self):
        self.condition = Condition()
        self.active = None
        self.paused = False
        self.stop = Event()
        self.thread = None
        self.baselines = {}

    def pause(self, value):
        with self.condition:
            self.paused = value
            self.condition.notify_all()

    def cancel(self):
        with self.condition:
            if self.active:
                self.active.cancelled.set()
            self.condition.notify_all()

    def execute(self, spec, control, confirmed=None, changed=None):
        data = normalize(spec)
        watch = _folder(data["watch"]) if changed is not None else None
        with self.condition:
            if self.active is not None:
                raise WorkflowError(tr("Another workflow is already running.", "Уже выполняется другой сценарий."))
            self.active = control
        stamp, state, results, previous = int(time.time()), "done", [], 0
        try:
            for number, step in enumerate(data["steps"], 1):
                with self.condition:
                    self.condition.wait_for(lambda: not self.paused or control.cancelled.is_set() or self.stop.is_set())
                control.check()
                control.report(number, len(results), 0)
                condition = step["when"]
                if condition != "always" and (condition == "has-results") != bool(previous):
                    results.append({"action": step["action"], "state": "skipped", "count": 0})
                    continue
                try:
                    previous = _perform(step, control, confirmed or {}, changed, watch)
                except jobs.Cancelled:
                    raise
                except Exception as exc:
                    results.append({"action": step["action"], "state": "failed", "count": 0, "error": str(exc)[:450]})
                    state = "failed"
                    break
                results.append({"action": step["action"], "state": "done", "count": previous})
            return state, results
        except jobs.Cancelled:
            state = "cancelled"
            return state, results
        finally:
            try:
                _log(spec["id"], stamp, state, results)
            finally:
                with self.condition:
                    self.active = None

    def start(self):
        self.thread = Thread(target=self._schedule, daemon=True, name="hub-workflows")
        self.thread.start()

    def shutdown(self):
        self.stop.set()
        self.cancel()
        if self.thread:
            self.thread.join(timeout=2)

    def _schedule(self):
        while not self.stop.is_set():
            if database().is_file() and not self.paused and self.active is None:
                try:
                    for spec in workflows():
                        if self.stop.is_set():
                            return
                        self._check_trigger(spec)
                except (OSError, sqlite3.Error, ValueError):
                    pass
            self.stop.wait(5)

    def _check_trigger(self, spec):
        if not spec["enabled"] or spec["trigger"] == "manual":
            self.baselines.pop(spec["id"], None)
            return
        try:
            if spec["trigger"] == "schedule":
                if not spec["last_run"] or time.time() - spec["last_run"] >= spec["interval"] * 60:
                    self.execute(spec, jobs.Job(float("inf")))
                return
            root = _folder(spec["watch"])
            current = {str(path): (info.st_size, info.st_mtime_ns) for path, info in _regular(root)
                       if not path.name.endswith((".part", ".tmp", ".crdownload"))}
            previous = self.baselines.get(spec["id"])
            self.baselines[spec["id"]] = root, current
            if previous is not None and root == previous[0]:
                changed = {path for path, value in current.items() if previous[1].get(path) != value}
                if changed:
                    self.execute(spec, jobs.Job(float("inf")), changed=changed)
        except (OSError, fileguard.GuardError, WorkflowError, sqlite3.Error):
            return


runner = Runner()
