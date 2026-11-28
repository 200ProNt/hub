"""Native Startup Manager page."""

import os

from System.Windows.Automation import AutomationProperties
from tools import startup_manager
from tools.i18n import tr


def mount(page):
    query = page.field(tr("Search startup entries", "Поиск по автозагрузке"))
    order = page.choice(tr("Sort by", "Сортировать по"),
                        (tr("Name", "Имя"), tr("Source", "Источник"), tr("Status", "Состояние")))
    summary = page.text("", 13, True)
    rows = page.rows(max_height=328)
    AutomationProperties.SetName(rows, tr("Startup entries", "Записи автозагрузки"))
    details = page.field(tr("Executable path", "Путь к программе"), multiline=True)
    details.IsReadOnly = True
    details.MaxHeight = 80
    company = page.text("", 13, True)
    guidance = page.text("", 13, True)
    items, shown, sources = [], [], []
    admin = startup_manager.is_admin()

    def status(entry):
        if entry.conflict:
            return tr("Conflicting entries", "Конфликт записей")
        if not entry.registered:
            return tr("Disabled in Hub", "Отключено в Hub")
        if not entry.target_available:
            return tr("Check target", "Проверь путь")
        return tr("Registered", "Зарегистрировано")

    def selected():
        index = rows.SelectedIndex
        return shown[index] if 0 <= index < len(shown) else None

    def selection_changed(*_):
        entry = selected()
        details.Text = "" if entry is None else entry.target or tr("Unknown", "Неизвестен")
        company.Text = "" if entry is None else tr("Publisher from file metadata: ", "Издатель по данным файла: ") + (
            entry.company or tr("Unknown", "Неизвестен"))
        title = tr("Disable", "Отключить") if entry is None or entry.registered else tr("Restore", "Восстановить")
        toggle_button.Content.Text = toggle_button.ToolTip = title
        AutomationProperties.SetName(toggle_button, title)
        toggle_button.IsEnabled = bool(entry and entry.can_change and not entry.conflict and (not entry.system or admin))
        if entry is None:
            guidance.Text = ""
        elif entry.conflict:
            guidance.Text = tr("Two different entries have this name.", "У двух разных записей совпадает имя.")
        elif entry.system and not admin:
            guidance.Text = tr("Changes to this source require administrator rights.",
                               "Для изменений в этом источнике нужны права администратора.")
        elif not entry.can_change:
            guidance.Text = tr("This entry is read-only. Change Hub's own startup in Hub Settings.",
                               "Эта запись доступна для просмотра. Автозапуск самого Hub можно изменить в настройках Hub.")
        elif not entry.target_available:
            guidance.Text = tr("Hub couldn't verify this local path.", "Hub не удалось проверить локальный путь.")
        else:
            guidance.Text = ""

    def render(*_):
        previous = selected()
        needle = query.Text.strip().casefold()
        shown[:] = [entry for entry in items if needle in " ".join(
            (entry.name, entry.source, entry.target, entry.company, status(entry))).casefold()]
        sort_keys = (lambda entry: entry.name, lambda entry: entry.source, status)
        key = sort_keys[max(0, order.SelectedIndex)]
        shown.sort(key=lambda entry: (key(entry).casefold(), entry.name.casefold(), entry.source))
        unnamed = tr("(default)", "(по умолчанию)")
        page.show_rows(rows, shown, lambda entry: f"{entry.name or unnamed}\n{entry.source}  ·  {status(entry)}")
        if previous:
            rows.SelectedIndex = next((index for index, entry in enumerate(shown)
                                       if (entry.name, entry.source) == (previous.name, previous.source)), -1)
        if shown:
            summary.Text = tr(f"Showing {len(shown)} of {len(items)}", f"Показано {len(shown)} из {len(items)}")
        elif items:
            summary.Text = tr("No matching entries.", "Ничего не найдено.")
        else:
            summary.Text = tr("No startup entries found.", "Записи автозагрузки не найдены.")
        if sources:
            summary.Text += "\n" + tr("Unavailable sources: ", "Недоступные источники: ") + ", ".join(sources)
        selection_changed()

    def show(result):
        entries, unavailable = result
        items[:], sources[:] = entries, unavailable
        render()

    def refresh():
        page.run(startup_manager.snapshot, show, tr("Reading startup entries…", "Читаю записи автозагрузки…"))

    def toggle():
        entry = selected()
        if entry is None or page.busy or not toggle_button.IsEnabled:
            return
        prompt = (tr("Disable this startup entry? Hub can restore it later.",
                     "Отключить эту запись? Её можно будет восстановить в Hub.") if entry.registered else
                  tr("Restore this entry to its original Windows startup location?",
                     "Вернуть запись в исходное место автозагрузки Windows?"))
        if not page.confirm(tr("Change startup entry", "Изменение автозагрузки"), f"{entry.name}\n{entry.source}\n\n{prompt}"):
            return

        def change():
            startup_manager.toggle(entry)
            return startup_manager.snapshot()

        page.run(change, show)

    toggle_button, _, _ = page.actions(
        (tr("Disable", "Отключить"), toggle, True),
        (tr("Refresh", "Обновить"), refresh),
        (tr("Windows startup settings", "Автозагрузка в Windows"), lambda: os.startfile("ms-settings:startupapps")),
    )
    page.text(tr("Windows can also disable registered entries for your account.",
                 "Windows также может отключать зарегистрированные записи для твоей учётной записи."), 12, True)
    rows.SelectionChanged += selection_changed
    query.TextChanged += render
    order.SelectionChanged += render
    selection_changed()
    refresh()
