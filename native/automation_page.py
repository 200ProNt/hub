"""Workflow editor and run history."""

from datetime import datetime

from System import TimeSpan
from System.Windows.Automation import AutomationProperties
from System.Windows.Threading import DispatcherTimer
from tools import automation, jobs
from tools.i18n import tr


def mount(page):
    runner = automation.runner
    labels = dict(zip(automation.ACTIONS, (
        tr("Find old files", "Найти старые файлы"), tr("Trash selected files", "Перенести выбранное в корзину"),
        tr("Sort files", "Отсортировать файлы"), tr("Compress images", "Сжать изображения"),
        tr("Run backup profile", "Запустить профиль резервного копирования"),
    )))
    conditions = dict(zip(automation.CONDITIONS, (
        tr("Always", "Всегда"), tr("If the previous step found results", "Если предыдущий шаг дал результат"),
        tr("If the previous step found nothing", "Если предыдущий шаг ничего не нашёл"),
    )))
    states = {"done": tr("Done", "Готово"), "failed": tr("Failed", "Ошибка"), "skipped": tr("Skipped", "Пропущено"),
              "cancelled": tr("Cancelled", "Отменено")}
    configs, steps, candidates, history_rows = [], [], [], []
    authorized, preview_spec = {}, None
    preview_job = None
    stored = page.rows(max_height=135)
    AutomationProperties.SetName(stored, tr("Saved workflows", "Сохранённые сценарии"))
    name = page.field(tr("Workflow name", "Имя сценария"))
    trigger = page.choice(tr("Trigger", "Запуск"), (
        tr("Manual", "Вручную"), tr("Schedule", "По расписанию"), tr("Folder changes", "При изменениях в папке")))
    minutes = page.field(tr("Interval in minutes", "Интервал в минутах"), "60")
    watch = page.folder(tr("Watched folder", "Наблюдаемая папка"))
    enabled = page.check(tr("Enable automatic starts", "Включить автоматический запуск"))
    page.section(tr("Steps", "Шаги"))
    step_list = page.rows(max_height=168)
    AutomationProperties.SetName(step_list, tr("Workflow steps", "Шаги сценария"))
    action = page.choice(tr("Step action", "Действие шага"), list(labels.values()))
    condition = page.choice(tr("Condition", "Условие"), list(conditions.values()))
    source = page.folder(tr("Source folder or backup profile name", "Исходная папка или имя профиля резервного копирования"))
    target = page.folder(tr("Image output folder", "Папка результата сжатия"))
    age = page.field(tr("Age in days", "Возраст файлов в днях"), "30")
    summary = page.text("", 13, True)

    def selected():
        index = stored.SelectedIndex
        return configs[index] if 0 <= index < len(configs) else None

    def invalidate():
        nonlocal preview_spec
        preview_spec = None
        authorized.clear()
        candidates.clear()
        plan.Items.Clear()
        file_choices.Items.Clear()

    def render_steps(index=-1):
        page.show_rows(step_list, steps, lambda row: f"{labels[row['action']]} · {conditions[row['when']]}\n{row['source']}")
        step_list.SelectedIndex = index
        invalidate()

    def read_step():
        value = age.Text.strip()
        return {"action": automation.ACTIONS[max(0, action.SelectedIndex)],
                "when": automation.CONDITIONS[max(0, condition.SelectedIndex)],
                "source": source.Text, "target": target.Text, "age": int(value) if value else 30}

    def edit(mode):
        index = step_list.SelectedIndex
        if mode in ("add", "replace"):
            try:
                step = automation.normalize({"name": "step", "steps": [read_step()]})["steps"][0]
            except (ValueError, automation.WorkflowError) as exc:
                page.notice(str(exc))
                return
            if mode == "replace" and 0 <= index < len(steps):
                steps[index] = step
            elif len(steps) < 40:
                steps.append(step)
                index = len(steps) - 1
            else:
                page.notice(tr("This workflow already has 40 steps.", "В сценарии уже 40 шагов."))
                return
        elif not 0 <= index < len(steps):
            return
        elif mode == "remove":
            steps.pop(index)
            index = min(index, len(steps) - 1)
        elif 0 <= index + mode < len(steps):
            steps[index], steps[index + mode] = steps[index + mode], steps[index]
            index += mode
        render_steps(index)

    def step_selected(*_):
        index = step_list.SelectedIndex
        if 0 <= index < len(steps):
            item = steps[index]
            action.SelectedIndex = automation.ACTIONS.index(item["action"])
            condition.SelectedIndex = automation.CONDITIONS.index(item["when"])
            source.Text, target.Text, age.Text = item["source"], item["target"], str(item["age"])

    def form():
        return automation.normalize({"name": name.Text, "steps": list(steps),
                                     "trigger": automation.TRIGGERS[max(0, trigger.SelectedIndex)],
                                     "interval": int(minutes.Text or "60"), "watch": watch.Text,
                                     "enabled": bool(enabled.IsChecked)})

    def fill(data):
        name.Text = data.get("name", "")
        steps[:] = data.get("steps", [])
        trigger.SelectedIndex = automation.TRIGGERS.index(data.get("trigger", "manual"))
        minutes.Text, watch.Text = str(data.get("interval", 60)), data.get("watch", "")
        enabled.IsChecked = data.get("enabled", False)
        render_steps()

    def show_history(items):
        history_rows[:] = items
        page.show_rows(log, items, lambda row: (
            f"{datetime.fromtimestamp(row['time']):%Y-%m-%d %H:%M} · {states[row['state']]}\n"
            + "\n".join(f"{labels[step['action']]} · {states[step['state']]} · {step['count']}"
                        + (f" · {step['error']}" if step.get("error") else "") for step in row["steps"])))
        empty.Text = "" if history_rows else tr("No runs yet.", "Запусков пока нет.")

    def refresh_history():
        item = selected()
        if item:
            identity = item["id"]
            page.run(lambda: automation.history(identity), lambda data: show_history(data)
                     if selected() and selected()["id"] == identity else None, message="")
        else:
            show_history([])

    def chosen(*_):
        if selected():
            fill(selected())
        refresh_history()

    def show_workflows(items, identity=None):
        configs[:] = items
        page.show_rows(stored, configs, lambda item: item["name"])
        stored.SelectedIndex = next((idx for idx, item in enumerate(configs) if item["id"] == identity), -1)

    def save():
        data = form()
        current = selected()
        if data["trigger"] != "manual" and data["enabled"] and (not current or automation.normalize(current) != data):
            if not page.confirm(tr("Enable automatic starts?", "Включить автоматический запуск?"),
                                tr("Hub will run these steps in the selected folders while it is open.",
                                   "Hub будет выполнять эти шаги в выбранных папках, пока приложение запущено.")):
                return

        def work():
            identity = automation.save(current["id"] if current else None, data)
            return automation.workflows(), identity

        page.run(work, lambda result: show_workflows(*result))

    def new():
        stored.SelectedIndex = -1
        fill({})

    def prepare():
        nonlocal preview_job
        if page.busy:
            return
        data = form()
        invalidate()
        control = preview_job = jobs.Job(float("inf"))

        def show(result):
            nonlocal preview_spec, preview_job
            preview_job = None
            value, error = result
            if error:
                summary.Text = error
                return
            description, files = value
            preview_spec = data
            authorized.update(files)
            candidates[:] = list(files)
            page.show_rows(plan, description, lambda row: f"{labels[row[0]]} · {conditions[row[1]]}\n{row[2]}")
            page.show_rows(file_choices, candidates, str)

        def work():
            try:
                return automation.preview(data, control), ""
            except jobs.Cancelled:
                return None, tr("Preview cancelled.", "Предпросмотр отменён.")
            except Exception as exc:
                return None, str(exc)

        page.run(work, show, tr("Preparing preview…", "Готовлю предпросмотр…"))

    def execute():
        current, data = selected(), form()
        if not current or data != automation.normalize(current):
            page.notice(tr("Save this version of the workflow first.", "Сначала сохрани эту версию сценария."))
            return
        if data != preview_spec:
            page.notice(tr("Preview this workflow first.", "Сначала просмотри план этого сценария."))
            return
        picked = {path: authorized[path] for path in page.selected(file_choices, candidates)}
        if not page.confirm(tr("Run workflow?", "Запустить сценарий?"),
                            tr(f"{current['name']}\nSelected files to move to Trash: {len(picked)}.",
                               f"{current['name']}\nВыбрано для переноса в корзину: {len(picked)}.")):
            return
        control = jobs.Job(float("inf"))

        def done(result):
            summary.Text = states[result[0]]
            refresh_history()
            invalidate()

        page.run(lambda: runner.execute(current, control, confirmed=picked), done,
                 tr("Running workflow…", "Выполняю сценарий…"))

    def cancel_run():
        if preview_job:
            preview_job.cancelled.set()
        else:
            runner.cancel()

    page.actions((tr("Add step", "Добавить шаг"), lambda: edit("add")),
                 (tr("Replace step", "Заменить шаг"), lambda: edit("replace")),
                 (tr("Remove step", "Убрать шаг"), lambda: edit("remove")),
                 (tr("Move up", "Выше"), lambda: edit(-1)), (tr("Move down", "Ниже"), lambda: edit(1)))
    page.actions((tr("New workflow", "Новый сценарий"), new), (tr("Save workflow", "Сохранить сценарий"), save, True))
    page.section(tr("Preview and run", "Предпросмотр и запуск"))
    _, _, cancel = page.actions((tr("Preview", "Предпросмотр"), prepare), (tr("Run workflow", "Запустить сценарий"), execute, True),
                                (tr("Cancel run", "Отменить запуск"), cancel_run))
    pause = page.check(tr("Pause workflows between steps", "Приостановить сценарии между шагами"), runner.paused)
    pause.Checked += lambda *_: runner.pause(True)
    pause.Unchecked += lambda *_: runner.pause(False)
    plan = page.rows(max_height=150)
    AutomationProperties.SetName(plan, tr("Workflow preview", "Предпросмотр сценария"))
    file_choices = page.rows(max_height=170, multiple=True)
    AutomationProperties.SetName(file_choices, tr("Select files for Trash", "Выбери файлы для корзины"))
    page.section(tr("Run history", "История запусков"))
    empty = page.text("", 13, True)
    log = page.rows(max_height=210)
    AutomationProperties.SetName(log, tr("Workflow history", "История сценариев"))
    page.actions((tr("Refresh history", "Обновить историю"), refresh_history))
    step_list.SelectionChanged += step_selected
    stored.SelectionChanged += chosen

    timer = DispatcherTimer()
    timer.Interval = TimeSpan.FromMilliseconds(350)

    def tick(*_):
        cancel.IsEnabled = runner.active is not None or preview_job is not None

    timer.Tick += tick
    timer.Start()
    page.on_leave(timer.Stop)
    page.on_leave(lambda: preview_job.cancelled.set() if preview_job else None)
    tick()
    draft = getattr(page.hub, "workflow_draft", None)
    if draft:
        page.hub.workflow_draft = None
        fill(draft)
    page.run(automation.workflows, show_workflows)
