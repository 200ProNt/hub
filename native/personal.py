"""Главная, заметки и буфер обмена Hub."""

from urllib.parse import quote

from System import DateTime, TimeSpan
from System.Globalization import CultureInfo
from System.Windows import FontWeights, GridLength, Thickness, VerticalAlignment, Visibility
from System.Windows.Automation import AutomationProperties
from System.Windows.Controls import Border, ColumnDefinition, Dock, DockPanel, Grid, ProgressBar, RowDefinition, StackPanel
from System.Windows.Input import Key, Keyboard, ModifierKeys
from System.Windows.Threading import DispatcherTimer

from tools.i18n import tr

from .widgets import glyph, label, make


def listen(page, field, changed):
    timer = make(DispatcherTimer, Interval=TimeSpan.FromMilliseconds(160))

    def scheduled(*_):
        timer.Stop()
        timer.Start()

    def fire(*_):
        timer.Stop()
        changed()

    field.TextChanged += scheduled
    timer.Tick += fire
    page.on_leave(timer.Stop)


def card(page, title, icon, build, featured=False):
    parent = page.panel
    inner = StackPanel()
    surface = make(Border, Padding=Thickness(18, 16, 18, 15), Child=inner)
    surface.SetResourceReference(Border.CornerRadiusProperty, "PanelRadius")
    surface.SetResourceReference(Border.BorderThicknessProperty, "PanelStroke")
    surface.SetResourceReference(Border.BackgroundProperty, "Feature" if featured else "Layer")
    surface.SetResourceReference(Border.BorderBrushProperty, "Edge")
    header = make(DockPanel, Margin=Thickness(0, 0, 0, 12))
    badge = make(Border, Width=34, Height=34, Margin=Thickness(0, 0, 10, 0),
                 Child=glyph(icon, 18, "AccentInk"))
    badge.SetResourceReference(Border.CornerRadiusProperty, "RowRadius")
    badge.SetResourceReference(Border.BackgroundProperty, "Accent")
    DockPanel.SetDock(badge, Dock.Left)
    header.Children.Add(badge)
    caption = label(title, 19)
    caption.FontWeight = FontWeights.SemiBold
    caption.VerticalAlignment = VerticalAlignment.Center
    caption.SetResourceReference(type(caption).ForegroundProperty, "FeatureInk" if featured else "Ink")
    header.Children.Add(caption)
    inner.Children.Add(header)
    page.add(surface)
    page.panel = inner
    try:
        return surface, build()
    finally:
        page.panel = parent


def excerpt(value, limit=92):
    clean = " ".join(str(value or "").split())
    return clean[:limit] + ("…" if len(clean) > limit else "")


def note_caption(note):
    title = note["title"] or excerpt(note["text"], 45)
    return (tr("Pinned · ", "Закреплено · ") if note.get("pinned") else "") + title + "\n" + excerpt(note["text"])


def home(page):
    date = DateTime.Now.ToString(tr("dddd, MMMM d", "dddd, d MMMM"), CultureInfo(tr("en-US", "ru-RU")))
    page.text(date[0].upper() + date[1:], 14, muted=True)

    def quick_actions():
        field = page.field(tr("A note, link, or task", "Заметка, ссылка или задача"), multiline=True)

        def store_note():
            draft = field.Text
            text = draft.strip()
            if text:
                def saved(_):
                    if field.Text == draft:
                        field.Clear()
                    page.hub.saved()
                    page.notice(tr("Note saved", "Заметка сохранена"))
                    summary()
                page.run(lambda: page.post("/api/notes/create", {"text": text}), saved)

        buttons = page.actions((tr("Save to Notes", "Сохранить в заметки"), store_note, True),
                               (tr("Copy text", "Скопировать"), lambda: page.copy(field.Text)))

        def update_actions(*_):
            for button in buttons:
                button.IsEnabled = bool(field.Text.strip())

        field.TextChanged += update_actions
        update_actions()

    def system():
        meters = []
        for title in (tr("Processor", "Процессор"), tr("Memory", "Память")):
            row = make(DockPanel)
            value = label("—", 16)
            value.FontWeight = FontWeights.SemiBold
            DockPanel.SetDock(value, Dock.Right)
            row.Children.Add(value)
            row.Children.Add(label(title, muted=True))
            page.add(row)
            bar = page.add(make(ProgressBar, Height=6, Margin=Thickness(0, 4, 0, 10)))
            AutomationProperties.SetName(bar, title)
            meters.append((value, bar))
        page.actions((tr("PC monitor", "Мониторинг ПК"), lambda: page.go("monitor")),
                     (tr("Disk map", "Карта диска"), lambda: page.go("diskmap")))
        return meters

    def choose_todo():
        selected = page.selected(todos, todo_items)
        return selected[0] if selected else None

    def mark_done():
        selected = choose_todo()
        if selected is None:
            return

        def complete():
            note = next((item for item in page.get("/api/notes/items")["items"]
                         if item["id"] == selected["note_id"]), None)
            if not note:
                raise ValueError(tr("This note has already been deleted", "Заметка уже удалена"))
            lines = note["text"].splitlines(keepends=True)
            index = selected["line_idx"]
            expected = "- [ ]" + (" " + selected["text"] if selected["text"] else "")
            if index >= len(lines) or " ".join(lines[index].split()) != " ".join(expected.split()):
                raise ValueError(tr("This note changed. Reopen Home to refresh the task list.",
                                    "Заметка изменилась. Открой главную заново, чтобы обновить список дел."))
            lines[index] = lines[index].replace("- [ ]", "- [x]", 1)
            return page.post("/api/notes/update", {"id": note["id"], "title": note["title"], "text": "".join(lines)})
        page.run(complete, lambda _: summary(), tr("Updating task…", "Обновляю задачу…"))

    def open_todo():
        selected = choose_todo()
        if selected:
            page.go("notes", selected["text"])

    todo_items = []
    clip_items = []

    def copy_recent():
        selected = page.selected(clips, clip_items)
        if selected:
            page.copy(selected[0]["text"])

    def recent(title, entries, primary, secondary):
        detail = page.text(tr("Loading…", "Загрузка…"), 13, muted=True)
        rows = page.rows(max_height=138)
        rows.Visibility = Visibility.Collapsed
        AutomationProperties.SetName(rows, title)
        select_action, _ = page.actions(primary, secondary)
        select_action.IsEnabled = False
        rows.SelectionChanged += lambda *_: setattr(select_action, "IsEnabled", bool(page.selected(rows, entries)))
        return rows, detail

    def task_card():
        return recent(tr("Open tasks", "Незавершённые дела"), todo_items,
                      (tr("Mark done", "Выполнено"), mark_done), (tr("All notes", "Все заметки"), lambda: page.go("notes")))

    def clipboard_card():
        return recent(tr("Recent clipboard", "Недавнее в буфере"), clip_items,
                      (tr("Copy selected", "Скопировать"), copy_recent),
                      (tr("Full history", "Вся история"), lambda: page.go("clipboard")))

    capture, _ = card(page, tr("Quick capture", "Быстрая запись"), "note", quick_actions, featured=True)
    pc, meters = card(page, tr("System snapshot", "Состояние ПК"), "pulse", system)
    tasks, (todos, task_detail) = card(page, tr("Open tasks", "Незавершённые дела"), "folder", task_card)
    history, (clips, clip_detail) = card(page, tr("Recent clipboard", "Недавнее в буфере"), "clipboard", clipboard_card)
    todos.MouseDoubleClick += lambda *_: open_todo()
    clips.MouseDoubleClick += lambda *_: copy_recent()

    dashboard = Grid()
    dashboard.ColumnDefinitions.Add(ColumnDefinition())
    dashboard.ColumnDefinitions.Add(ColumnDefinition())
    cards = (capture, pc, tasks, history)
    for panel in cards:
        page.panel.Children.Remove(panel)
        dashboard.Children.Add(panel)
        dashboard.RowDefinitions.Add(make(RowDefinition, Height=GridLength.Auto))

    def arrange(*_):
        wide = dashboard.ActualWidth >= 650
        for index, panel in enumerate(cards):
            column = index % 2 if wide else 0
            Grid.SetColumn(panel, column)
            Grid.SetColumnSpan(panel, 1 if wide else 2)
            Grid.SetRow(panel, index // 2 if wide else index)
            panel.Margin = Thickness(6 if column else 0, 6, 6 if wide and not column else 0, 6)

    arrange()
    dashboard.SizeChanged += arrange
    page.add(dashboard)

    def render(summary_data):
        todo_items[:] = summary_data["todos"]
        clip_items[:] = summary_data["recent_clips"]
        page.show_rows(todos, todo_items, lambda item: excerpt(item["text"]) or tr("Untitled task", "Дело без названия"))
        page.show_rows(clips, clip_items, lambda item: excerpt(item["text"]))
        todos.Visibility = Visibility.Visible if todo_items else Visibility.Collapsed
        clips.Visibility = Visibility.Visible if clip_items else Visibility.Collapsed
        stats = summary_data["stats"]
        task_detail.Text = (tr("From your notes", "Из твоих заметок") if todo_items else
                            tr("Add an unchecked task in Notes with - [ ]", "Добавь задачу в заметках через - [ ]"))
        clip_detail.Text = (tr("Saved items: {count}", "Записей в истории: {count}").format(count=stats["clipboard_count"])
                            if clip_items else tr("Copied text will appear here.", "Здесь появится скопированный текст."))
        vitals = summary_data.get("vitals") or {}
        for key, (value, bar) in zip(("cpu_percent", "memory_percent"), meters):
            percent = vitals.get(key)
            value.Text = "—" if percent is None else f"{percent:.0f}%"
            bar.Visibility = Visibility.Hidden if percent is None else Visibility.Visible
            if percent is not None:
                bar.Value = percent

    def summary():
        page.run(lambda: page.get("/api/home/summary"), render, message="")

    summary()


def notes(page, query):
    search = page.field(tr("Search notes", "Найти в заметках"), query)
    box = page.rows(max_height=290)
    items = []
    editing = None

    def render(data, match):
        if search.Text.strip() != match:
            return
        items[:] = data["items"]
        page.show_rows(box, items, note_caption)
        if items and match:
            box.SelectedIndex = 0
        if not items:
            box.Items.Add(tr("No notes yet", "Заметок пока нет") if not match else tr("No matches", "Совпадений нет"))

    def refresh():
        match = search.Text.strip()
        page.run(lambda: page.get("/api/notes/items?q=" + quote(match)),
                 lambda data: render(data, match), message="")

    def selected():
        records = page.selected(box, items) if items else []
        if not records:
            page.notice(tr("Select a note", "Выбери заметку"))
        return records[0] if records else None

    def edit(item=None):
        nonlocal editing
        editing = item
        editor.Visibility = Visibility.Visible
        title.Text = item["title"] if item else ""
        body.Text = item["text"] if item else ""
        page.hub.animate(editor, "sheet")
        title.Focus()

    def close_editor():
        editor.Visibility = Visibility.Collapsed

    def save():
        text, name = body.Text, title.Text
        payload = {"title": name, "text": text}
        kind = "create" if editing is None else "update"
        if editing is not None:
            payload["id"] = editing["id"]

        def done(_):
            close_editor()
            page.hub.saved()
            refresh()
            page.notice(tr("Note saved", "Заметка сохранена"))
        page.run(lambda: page.post("/api/notes/" + kind, payload), done)

    def edit_selected():
        if (item := selected()) is not None:
            edit(item)

    def modify(action):
        if (item := selected()) is None:
            return
        if action == "delete" and not page.confirm(tr("Delete this note?", "Удалить заметку?"), tr("This note will be permanently deleted.", "Заметка будет удалена окончательно.")):
            return
        page.run(lambda: page.post("/api/notes/" + action, {"id": item["id"]}), lambda _: refresh())

    def export(individual):
        item = selected() if individual else None
        if individual and item is None:
            return
        kinds = ("md", "txt")
        kind = kinds[formats.SelectedIndex]
        query = "&id=" + quote(item["id"]) if item else ""
        page.download(f"/api/notes/export?format={kind}{query}", f"hub-notes.{kind}")

    page.actions((tr("New note", "Новая заметка"), edit, True), (tr("Open", "Открыть"), edit_selected), (tr("Pin / unpin", "Закрепить / открепить"), lambda: modify("pin")),
                 (tr("Delete", "Удалить"), lambda: modify("delete")))
    formats = page.choice(tr("Export format", "Формат экспорта"), ("Markdown", tr("Plain text", "Обычный текст")))
    page.actions((tr("Export note", "Экспорт заметки"), lambda: export(True)), (tr("Export all notes", "Экспорт всех заметок"), lambda: export(False)))
    editor = make(StackPanel, Visibility=Visibility.Collapsed)
    page.add(editor)
    previous = page.panel
    page.panel = editor
    page.section(tr("Note editor", "Редактор заметки"))
    title = page.field(tr("Title", "Заголовок"))
    body = page.field(tr("Text", "Текст"), multiline=True)
    page.actions((tr("Save", "Сохранить"), save, True), (tr("Cancel", "Отмена"), close_editor))
    page.panel = previous

    def key(_, event):
        if event.Key == Key.Enter and Keyboard.Modifiers == ModifierKeys.Control:
            event.Handled = True
            save()
        elif event.Key == Key.Escape:
            event.Handled = True
            close_editor()

    editor.PreviewKeyDown += key
    box.MouseDoubleClick += lambda *_: edit_selected()
    listen(page, search, refresh)
    refresh()


def clipboard(page, query):
    search = page.field(tr("Search history", "Найти в истории"), query)
    filters = ("", "link", "code", "text")
    kind = page.choice(tr("Type", "Тип"), (tr("All entries", "Все записи"), tr("Links", "Ссылки"), tr("Code", "Код"), tr("Text", "Текст")))
    box = page.rows(max_height=340)
    items = []
    state = page.text("", muted=True)
    paused = False

    def refresh():
        match = (search.Text.strip(), kind.SelectedIndex)

        def show(data):
            nonlocal paused
            if match != (search.Text.strip(), kind.SelectedIndex):
                return
            paused = data["paused"]
            state.Text = tr(f"Entries: {data['total']}", f"Записей: {data['total']}") + (tr(" · Capture paused", " · Запись приостановлена") if paused else "")
            items[:] = data["items"]
            page.show_rows(box, items, lambda item: (tr("Pinned · ", "Закреплено · ") if item["pinned"] else "")
                           + excerpt(item.get("text"), 165))
            if not items:
                box.Items.Add(tr("No entries", "Записей нет"))

        path = f"/api/clipboard/items?q={quote(match[0])}&type={filters[max(match[1], 0)]}&limit=500"
        page.run(lambda: page.get(path), show, message="")

    def modify(action):
        selected = page.selected(box, items) if items else []
        if not selected:
            page.notice(tr("Select an entry", "Выбери запись"))
            return
        if action == "delete" and not page.confirm(tr("Delete this entry?", "Удалить запись?"), tr("This entry will be permanently deleted.", "Запись будет удалена окончательно.")):
            return
        identity = selected[0]["id"]
        page.run(lambda: page.post("/api/clipboard/" + action, {"id": identity}),
                 lambda _: page.notice(tr("Copied", "Скопировано")) if action == "copy" else refresh())

    def clear():
        if page.confirm(tr("Clear history?", "Очистить историю?"), tr("All entries, including pinned ones, will be deleted.", "Все записи, включая закреплённые, будут удалены.")):
            page.run(lambda: page.post("/api/clipboard/clear", {}), lambda _: refresh())

    def pause():
        request = {"paused": not paused}
        page.run(lambda: page.post("/api/clipboard/pause", request), lambda _: refresh())

    page.actions((tr("Copy", "Скопировать"), lambda: modify("copy"), True), (tr("Pin / unpin", "Закрепить / открепить"), lambda: modify("pin")),
                 (tr("Delete", "Удалить"), lambda: modify("delete")), (tr("Pause / resume", "Пауза / продолжить"), pause),
                 (tr("Refresh", "Обновить"), refresh), (tr("Clear history", "Очистить историю"), clear))
    box.MouseDoubleClick += lambda *_: modify("copy")
    kind.SelectionChanged += lambda *_: refresh()
    listen(page, search, refresh)
    refresh()


def mount(page, tool_id, query=""):
    if tool_id == "home":
        home(page)
    elif tool_id == "notes":
        notes(page, query)
    else:
        clipboard(page, query)
