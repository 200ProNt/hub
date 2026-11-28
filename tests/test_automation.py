import os
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch

from PIL import Image
from tools import automation, backup_manager, filesorter, jobs, paths


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.inbox = self.base / "inbox"
        self.out = self.base / "out"
        self.inbox.mkdir()
        self.out.mkdir()
        using_fixture = patch.object(paths, "DATA_DIR", self.base / "hub")
        using_fixture.start()
        self.addCleanup(using_fixture.stop)
        environment = patch.dict(os.environ, {"HUB_TRASH_DIR": str(self.base / "trash"),
                                               "HUB_RUNS_DIR": str(self.base / "runs")})
        environment.start()
        self.addCleanup(environment.stop)
        self.runner = automation.Runner()
        self.addCleanup(self.runner.shutdown)

    def save(self, steps, **options):
        identity = automation.save(None, dict(name="Fixture", steps=steps, **options))
        return next(item for item in automation.workflows() if item["id"] == identity)

    def step(self, action, **options):
        return dict(action=action, source=str(self.inbox), **options)

    @staticmethod
    def job():
        return jobs.Job(float("inf"))

    def test_runs_only_the_matching_branch_and_records_each_result(self):
        current = self.inbox / "new.txt"
        current.write_text("Keep", encoding="utf-8")
        recipe = self.save([self.step("scan-old", age=365),
                            self.step("sort", when="has-results"), self.step("sort", when="no-results")])
        state, steps = self.runner.execute(recipe, self.job())
        self.assertEqual(state, "done")
        self.assertEqual([item["state"] for item in steps], ["done", "skipped", "done"])
        self.assertFalse(current.exists())
        self.assertTrue((self.inbox / filesorter.category_for(current.name) / current.name).exists())
        self.assertEqual(automation.history(recipe["id"])[0]["steps"], steps)

    def test_folder_trigger_only_sorts_new_and_changed_files(self):
        previous = self.inbox / "old.txt"
        previous.touch()
        recipe = self.save([self.step("sort")], trigger="folder", enabled=True, watch=str(self.inbox))
        self.runner._check_trigger(recipe)
        incoming = self.inbox / "new.txt"
        incoming.touch()
        self.runner._check_trigger(recipe)
        self.assertTrue(previous.exists())
        self.assertFalse(incoming.exists())
        self.assertEqual(automation.history(recipe["id"])[0]["steps"][0]["count"], 1)

    def test_trash_requires_selection_and_rejects_post_preview_changes(self):
        file = self.inbox / "old.txt"
        file.write_text("Old", encoding="utf-8")
        past = time.time() - 90 * 86400
        os.utime(file, (past, past))
        recipe = self.save([self.step("trash-selected", age=30)])
        _, targets = automation.preview(recipe, self.job())
        self.assertIn(str(file), targets)
        self.assertEqual(self.runner.execute(recipe, self.job())[1][0]["count"], 0)
        file.write_text("Changed after preview", encoding="utf-8")
        os.utime(file, (past, past))
        state, _ = self.runner.execute(recipe, self.job(), confirmed=targets)
        self.assertEqual(state, "failed")
        self.assertTrue(file.exists())
        _, targets = automation.preview(recipe, self.job())
        state, result = self.runner.execute(recipe, self.job(), confirmed=targets)
        self.assertEqual((state, result[0]["count"]), ("done", 1))
        self.assertFalse(file.exists())
        with self.assertRaisesRegex(automation.WorkflowError, "manual"):
            self.save([self.step("trash-selected")], trigger="schedule", enabled=True)

    def test_scheduled_compression_runs_existing_encoder(self):
        source = self.inbox / "picture.png"
        with Image.new("RGB", (24, 10), "blue") as fixture:
            fixture.save(source)
        recipe = self.save([self.step("compress", target=str(self.out))], trigger="schedule", enabled=True, interval=1)
        self.runner._check_trigger(recipe)
        with Image.open(self.out / "picture.webp") as result:
            self.assertEqual(result.size, (24, 10))
        self.assertTrue(source.is_file())

    def test_workflow_can_create_a_version_from_an_existing_profile(self):
        source = self.inbox / "one.txt"
        source.write_bytes(b"one file")
        profile_id = backup_manager.save_profile(None, "Workflow backup", [self.inbox], self.out, [], 0, 0)
        recipe = self.save([{"action": "backup", "source": profile_id}])
        self.assertEqual(self.runner.execute(recipe, self.job())[0], "done")
        profile, = backup_manager.profiles()
        self.assertEqual(backup_manager.history(profile)[0]["files"], 1)

    def test_paused_workflow_can_be_cancelled_before_a_step(self):
        recipe = self.save([self.step("sort")])
        completed = Event()
        self.runner.pause(True)
        job = self.job()

        def execute():
            self.runner.execute(recipe, job)
            completed.set()

        thread = Thread(target=execute, daemon=True)
        thread.start()
        for _ in range(100):
            if self.runner.active is job:
                break
            time.sleep(.01)
        self.assertIs(self.runner.active, job)
        self.runner.cancel()
        self.assertTrue(completed.wait(5))
        self.assertEqual(automation.history(recipe["id"])[0]["state"], "cancelled")
