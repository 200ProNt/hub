"""Native backup profiles, history, and a confirmed restore preview."""

from datetime import datetime

from System import TimeSpan
from System.Windows.Automation import AutomationProperties
from System.Windows.Threading import DispatcherTimer
from tools import backup_manager as backup, jobs
from tools.i18n import tr


def mount(page):
    profiles, versions, preview_rows = [], [], []
    current_plan = None
    preview_offset, preview_limit = 0, 150
    profile_list = page.rows(max_height=155)
    AutomationProperties.SetName(profile_list, tr("Backup profiles", "Профили резервного копирования"))
    name = page.field(tr("Profile name", "Имя профиля"))
    sources = page.field(tr("Files and folders, one path on each line", "Файлы и папки, по одному пути на строку"), multiline=True)
    folder = page.folder(tr("Choose a source folder", "Выбрать исходную папку"))
    file = page.file(tr("Choose a source file", "Выбрать исходный файл"))
    destination = page.folder(tr("Backup storage folder", "Папка хранения резервных копий"))
    exclusions = page.field(tr("Exclusions, one glob per line", "Исключения, по одной маске на строку"), multiline=True)
    retention = page.field(tr("Keep versions for days (0 keeps all)", "Срок хранения в днях (0 хранит все версии)"), "0")
    interval = page.field(tr("Repeat every hours (0 for manual backups)", "Интервал запуска в часах (0 для ручного запуска)"), "0")
    operation = page.text("", 13, True)
    progress = page.text("", 13, True)

    def selected():
        index = profile_list.SelectedIndex
        return profiles[index] if 0 <= index < len(profiles) else None

    def version_selected():
        index = version_list.SelectedIndex
        return versions[index] if 0 <= index < len(versions) else None

    def add_source(field):
        path = field.Text.strip()
        values = [line for line in sources.Text.splitlines() if line.strip()]
        if path and path not in values:
            sources.Text = "\n".join((*values, path))
        field.Text = ""

    def invalidate(*_):
        nonlocal current_plan, preview_offset
        current_plan = None
        preview_offset = 0
        preview_rows.clear()
        preview_list.Items.Clear()
        plan_summary.Text = ""
        restore_button.IsEnabled = False
        preview_previous.IsEnabled = preview_next.IsEnabled = False

    def page_preview(direction=0):
        nonlocal preview_offset
        preview_offset += direction * preview_limit
        visible = preview_rows[preview_offset:preview_offset + preview_limit]
        page.show_rows(preview_list, visible, lambda item: (
            (tr("Replace · ", "Перезапись · ") if item["original"] is not None else tr("New · ", "Новый объект · ")) + item["path"]))
        preview_previous.IsEnabled = preview_offset > 0
        preview_next.IsEnabled = preview_offset + preview_limit < len(preview_rows)

    def show_history(items):
        versions[:] = items
        page.show_rows(version_list, versions, lambda item: tr(
            f"Version {item['id']} · {datetime.fromtimestamp(item['created']):%Y-%m-%d %H:%M} · {item['files']} files",
            f"Версия {item['id']} · {datetime.fromtimestamp(item['created']):%Y-%m-%d %H:%M} · Файлов: {item['files']}"))
        status.Text = tr("No backup versions yet.", "Версий резервной копии пока нет.") if not versions else ""
        if versions:
            version_list.SelectedIndex = 0

    def history():
        profile = selected()
        if profile is None:
            show_history([])
            return

        def show(items):
            active = selected()
            if active and active["id"] == profile["id"]:
                show_history(items)
                if profile.get("error"):
                    status.Text = (tr("Last attempt was cancelled.", "Последняя попытка отменена.")
                                   if profile["error"] == "cancelled" else
                                   tr("Last backup attempt failed.", "Последняя попытка резервного копирования не удалась."))

        page.run(lambda: backup.history(profile), show, message="")

    def show_profiles(items, identity=None):
        profiles[:] = items
        page.show_rows(profile_list, profiles, lambda item: item["name"])
        profile_list.SelectedIndex = next((index for index, item in enumerate(profiles) if item["id"] == identity), -1)

    def refresh_profiles():
        profile = selected()
        identity = profile["id"] if profile else None
        page.run(backup.profiles, lambda items: show_profiles(items, identity))

    def profile_changed(*_):
        profile = selected()
        if profile:
            name.Text, sources.Text = profile["name"], "\n".join(profile["sources"])
            destination.Text, exclusions.Text = profile["destination"], "\n".join(profile["exclusions"])
            retention.Text, interval.Text = str(profile["keep_days"]), str(profile["interval"])
        invalidate()
        history()

    def new():
        profile_list.SelectedIndex = -1
        for field in (name, sources, folder, file, destination, exclusions):
            field.Text = ""
        retention.Text = interval.Text = "0"

    def save():
        profile = selected()
        try:
            days, hours = int(retention.Text), int(interval.Text)
        except ValueError:
            page.notice(tr("Use whole numbers for retention and scheduling.", "Для хранения и расписания нужны целые числа."))
            return
        if not destination.Text.strip():
            page.notice(tr("Select a backup storage folder.", "Выбери папку хранения резервных копий."))
            return
        if days > 0 and (profile is None or days != profile["keep_days"]):
            if not page.confirm(tr("Apply retention?", "Применить срок хранения?"), tr(
                    f"Hub will remove backup versions older than {days} days after a successful backup.",
                    f"После успешной копии Hub будет удалять версии в этом хранилище старше {days} дней.")):
                return
        values = (profile["id"] if profile else None, name.Text, [part.strip() for part in sources.Text.splitlines() if part.strip()],
                  destination.Text, exclusions.Text.splitlines(), days, hours)

        def work():
            identity = backup.save_profile(*values)
            return backup.profiles(), identity

        page.run(work, lambda result: show_profiles(*result))

    def run_job(message, work, finish):
        if page.busy:
            return
        local_job = jobs.Job(float("inf"))
        operation.Text = message

        def run():
            try:
                return work(local_job), ""
            except jobs.Cancelled:
                return None, tr("Cancelled.", "Операция отменена.")
            except Exception as error:
                return None, str(error)

        def completed(result):
            value, error = result
            operation.Text = error
            if not error:
                finish(value)

        page.run(run, completed, message)

    def create():
        profile = selected()
        if profile:
            run_job(tr("Creating backup…", "Создаю резервную копию…"), lambda job: backup.run_backup(profile, job),
                    lambda _: refresh_profiles())

    def verify():
        profile, version = selected(), version_selected()
        if profile and version:
            run_job(tr("Checking backup integrity…", "Проверяю целостность…"),
                    lambda job: backup.verify(profile, version["id"], job),
                    lambda count: setattr(operation, "Text", tr(f"Verified blocks: {count}", f"Проверено блоков: {count}")))

    def preview():
        profile, version, directory = selected(), version_selected(), restore_to.Text.strip()
        if not profile or not version or not directory:
            page.notice(tr("Select a version and a destination folder.", "Выбери версию и папку для восстановления."))
            return
        invalidate()

        def show(plan):
            nonlocal current_plan
            active, chosen = selected(), version_selected()
            if not active or not chosen or (active["id"], chosen["id"], restore_to.Text.strip()) != (
                    profile["id"], version["id"], directory):
                return
            current_plan = plan
            replacements = [item for item in plan[2] if item["kind"] == "file" and item["original"] is not None]
            preview_rows[:] = replacements + [item for item in plan[2] if item["original"] is None]
            page_preview()
            plan_summary.Text = tr(f"{len(plan[2])} entries · {len(replacements)} replacements",
                                   f"Объектов: {len(plan[2])} · Перезаписей: {len(replacements)}")
            restore_button.IsEnabled = True

        run_job(tr("Preparing restore preview…", "Готовлю план восстановления…"),
                lambda job: backup.preview(profile, version["id"], directory, job), show)

    def restore():
        profile, plan = selected(), current_plan
        if not profile or not plan or page.busy:
            return
        count = sum(item["kind"] == "file" and item["original"] is not None for item in plan[2])
        if page.confirm(tr("Restore backup?", "Восстановить копию?"), tr(
                f"Restore to {plan[0]}? Existing files to replace: {count}.",
                f"Восстановить в {plan[0]}? Существующих файлов к перезаписи: {count}.")):
            invalidate()
            run_job(tr("Restoring files…", "Восстанавливаю файлы…"), lambda job: backup.restore(profile, plan, job),
                    lambda number: setattr(operation, "Text", tr(f"Files restored: {number}", f"Восстановлено файлов: {number}")))

    def cancel_job():
        control = backup.active_job()
        if control:
            control.cancelled.set()

    page.actions((tr("Add folder", "Добавить папку"), lambda: add_source(folder)),
                 (tr("Add file", "Добавить файл"), lambda: add_source(file)),
                 (tr("New profile", "Новый профиль"), new),
                 (tr("Save profile", "Сохранить профиль"), save, True))
    _, cancel, _ = page.actions((tr("Run backup", "Создать копию"), create, True),
                                (tr("Cancel operation", "Отменить операцию"), cancel_job),
                                (tr("Refresh versions", "Обновить версии"), refresh_profiles))
    cancel.IsEnabled = False
    page.section(tr("Backup history", "История копий"))
    status = page.text(tr("Select a backup profile.", "Выбери профиль резервного копирования."), 13, True)
    version_list = page.rows(max_height=190)
    AutomationProperties.SetName(version_list, tr("Backup versions", "Версии резервной копии"))
    page.actions((tr("Verify backup", "Проверить копию"), verify))
    page.section(tr("Restore", "Восстановление"))
    restore_to = page.folder(tr("Restore destination", "Папка восстановления"))
    _, restore_button = page.actions((tr("Preview restore", "Показать план восстановления"), preview),
                                      (tr("Restore files", "Восстановить файлы"), restore, True))
    restore_button.IsEnabled = False
    plan_summary = page.text("", 13, True)
    preview_list = page.rows(max_height=205)
    AutomationProperties.SetName(preview_list, tr("Restore preview", "План восстановления"))
    preview_previous, preview_next = page.actions((tr("Previous", "Назад"), lambda: page_preview(-1)),
                                                   (tr("Next", "Далее"), lambda: page_preview(1)))
    preview_previous.IsEnabled = preview_next.IsEnabled = False
    profile_list.SelectionChanged += profile_changed
    version_list.SelectionChanged += invalidate
    restore_to.TextChanged += invalidate

    def tick(*_):
        active = backup.active_job()
        cancel.IsEnabled = active is not None
        if active:
            _, files, size = active.progress
            progress.Text = tr(f"Processed {files} files · {size / 1024**2:.1f} MiB",
                               f"Файлов обработано: {files} · {size / 1024**2:.1f} МиБ")
        else:
            progress.Text = ""

    timer = DispatcherTimer()
    timer.Interval = TimeSpan.FromMilliseconds(300)
    timer.Tick += tick
    timer.Start()
    page.on_leave(timer.Stop)
    refresh_profiles()
