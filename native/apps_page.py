"""WinGet package inventory and actions."""

import os
from datetime import datetime

from System.Windows import Visibility
from System.Windows.Automation import AutomationProperties
from System.Windows.Controls import ProgressBar
from tools import app_manager
from tools.i18n import tr

from .widgets import make

def mount(page):
    query = page.field(tr("App name or package ID", "Имя приложения или ID пакета"))
    count = page.text("", 13, True)
    catalog, loaded, updates_only = False, False, False
    packages, visible = [], []

    def selected():
        index = rows.SelectedIndex
        return visible[index] if 0 <= index < len(visible) else None

    def details(*_):
        package = selected()
        if package:
            text = f"{package.id}  ·  {package.version}"
            if package.available:
                text += f" → {package.available}"
            description.Text = text
        else:
            description.Text = ""
        for command, button in buttons.items():
            button.IsEnabled = ((command == "install") == catalog and app_manager.can_run(command, package))

    def render(*_):
        needle = query.Text.strip().casefold()
        visible[:] = [item for item in packages if catalog or (
            (not updates_only or item.available) and needle in (item.name + " " + item.id).casefold())]
        page.show_rows(rows, visible, lambda item: f"{item.name}\n{item.id}  ·  {item.version}"
                       + (f" → {item.available}" if item.available else ""))
        if loaded:
            if catalog:
                count.Text = tr(f"Catalog results · {len(visible)}", f"Результаты каталога · {len(visible)}")
            elif updates_only:
                count.Text = tr(f"Available updates · {len(visible)}", f"Доступные обновления · {len(visible)}")
            else:
                count.Text = tr(f"Installed apps · {len(visible)}", f"Установленные приложения · {len(visible)}")
            if not visible:
                count.Text = tr("No matching apps.", "Подходящих приложений нет.")
        details()

    def load(search, updates=False):
        needle = query.Text.strip() if search else ""
        if search and not needle:
            page.notice(tr("Enter a name or package ID to search.", "Введи имя или ID пакета."))
            return

        def finish(result):
            nonlocal catalog, loaded, updates_only
            loaded, catalog = True, search
            updates_only = updates
            packages[:] = result
            render()

        page.run(lambda: app_manager.packages(needle), finish,
                 tr("Reading packages with WinGet…", "Читаю список пакетов через WinGet…"))

    page.actions(
        (tr("Installed", "Установленные"), lambda: load(False)),
        (tr("Updates", "Обновления"), lambda: load(False, True)),
        (tr("Search WinGet catalog", "Поиск в каталоге WinGet"), lambda: load(True), True),
        (tr("Windows app settings", "Приложения в параметрах Windows"), lambda: os.startfile("ms-settings:appsfeatures")),
    )
    rows = page.rows(max_height=315)
    AutomationProperties.SetName(rows, tr("Applications", "Приложения"))
    description = page.text("", 13, True)
    result_text = page.text("", 13, True)
    progress = page.add(make(ProgressBar, Minimum=0, Maximum=100, Height=8, Visibility=Visibility.Collapsed))
    AutomationProperties.SetName(progress, tr("WinGet progress", "Ход работы WinGet"))
    verbs = {"install": tr("Install", "Установить"), "upgrade": tr("Update", "Обновить"),
             "uninstall": tr("Uninstall", "Удалить")}

    def render_history():
        records = reversed(app_manager.history())
        page.show_rows(log, list(records), lambda row: (
            f"{datetime.fromtimestamp(row['time']):%Y-%m-%d %H:%M} · {verbs[row['action']]} · {row['package']} · "
            + (tr("Done", "Готово") if not row["code"] else f"0x{row['code']:08X}")))
        log.Visibility = Visibility.Visible if log.Items.Count else Visibility.Collapsed
        empty_log.Visibility = Visibility.Collapsed if log.Items.Count else Visibility.Visible

    def execute(command):
        item = selected()
        if page.busy or not app_manager.can_run(command, item):
            return
        version = item.available if command == "upgrade" else item.version
        title = verbs[command]
        if not page.confirm(title, f"{item.name}\n{item.id}\n{version}\n\n" + tr(
                "Continue with WinGet?", "Продолжить через WinGet?")):
            return
        progress.IsIndeterminate = True
        progress.Visibility = Visibility.Visible
        result_text.Text = ""

        def update(value):
            def show():
                if page.hub.current is page:
                    progress.IsIndeterminate = False
                    progress.Value = value
            page.hub.dispatch(show)

        def work():
            try:
                code, saved = app_manager.run(command, item, update)
                return code, saved, ""
            except app_manager.PackageError as error:
                return None, True, str(error)

        def finish(state):
            code, saved, error = state
            progress.Visibility = Visibility.Collapsed
            result_text.Text = error or (tr("WinGet completed the operation.", "WinGet завершил операцию.") if code == 0 else
                                         tr(f"WinGet reported 0x{code:08X}.", f"WinGet вернул код 0x{code:08X}."))
            if not saved:
                result_text.Text += " " + tr("Couldn't write the history.", "Не удалось записать историю.")
            render_history()
            if code == 0 and not catalog:
                load(False, updates_only)

        page.run(work, finish)

    buttons = dict(zip(verbs, page.actions(*((
        label, lambda action=command: execute(action)) for command, label in verbs.items()))))
    page.section(tr("Recent operations", "Последние операции"))
    empty_log = page.text(tr("No operations yet.", "Операций пока нет."), 13, True)
    log = page.rows(max_height=150)
    AutomationProperties.SetName(log, tr("Operation history", "История операций"))
    rows.SelectionChanged += details
    query.TextChanged += render
    details()
    render_history()
    load(False)
