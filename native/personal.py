"""Главная, заметки и буфер обмена Hub."""

from urllib.parse import quote

from System import DateTime, TimeSpan
from System.Globalization import CultureInfo
from System.Windows import CornerRadius, Thickness, Visibility
from System.Windows.Controls import Border, StackPanel
from System.Windows.Input import Key, Keyboard, ModifierKeys
from System.Windows.Threading import DispatcherTimer

from .widgets import make


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


def card(page, build):
    parent = page.panel
    inner = StackPanel()
    surface = make(Border, CornerRadius=CornerRadius(15), BorderThickness=Thickness(1),
                   Padding=Thickness(14, 11, 14, 9), Margin=Thickness(0, 8, 0, 7), Child=inner)
    surface.SetResourceReference(Border.BackgroundProperty, "Layer")
    surface.SetResourceReference(Border.BorderBrushProperty, "Edge")
    page.add(surface)
    page.panel = inner
    try:
        return build()
    finally:
        page.panel = parent


def excerpt(value, limit=92):
    clean = " ".join(str(value or "").split())
    return clean[:limit] + ("…" if len(clean) > limit else "")


def note_caption(note):
    title = note["title"] or excerpt(note["text"], 45)
    return ("Закреплено · " if note.get("pinned") else "") + title + "\n" + excerpt(note["text"])


def home(page):
    date = DateTime.Now.ToString("dddd, d MMMM", CultureInfo("ru-RU"))
    page.text(date[0].upper() + date[1:], 14, muted=True)

    def quick_actions():
        page.section("Быстрая запись")
        field = page.field("Текст заметки или буфера")

        def store_note():
            text = field.Text.strip()
            if text:
                def saved(_):
                    field.Clear()
                    page.hub.saved()
                    page.notice("Заметка сохранена")
                    summary()
                page.run(lambda: page.post("/api/notes/create", {"text": text}), saved)

        page.actions(("Сохранить заметку", store_note, True), ("Скопировать", lambda: page.copy(field.Text)),
                     ("Открыть заметки", lambda: page.go("notes")))
    card(page, quick_actions)

    def recent():
        page.section("Незавершённые дела")
        todo_box = page.rows(max_height=155)
        page.actions(("Готово", mark_done), ("Открыть заметку", open_todo))
        return todo_box

    def choose_todo():
        selected = page.selected(todos, todo_items)
        if not selected:
            page.notice("Выбери дело")
        return selected[0] if selected else None

    def mark_done():
        selected = choose_todo()
        if selected is None:
            return

        def complete():
            note = next((item for item in page.get("/api/notes/items")["items"]
                         if item["id"] == selected["note_id"]), None)
            if not note:
                raise ValueError("Заметка уже удалена")
            lines = note["text"].splitlines(keepends=True)
            index = selected["line_idx"]
            expected = "- [ ]" + (" " + selected["text"] if selected["text"] else "")
            if index >= len(lines) or " ".join(lines[index].split()) != " ".join(expected.split()):
                raise ValueError("Заметка изменилась. Обнови список дел.")
            lines[index] = lines[index].replace("- [ ]", "- [x]", 1)
            return page.post("/api/notes/update", {"id": note["id"], "title": note["title"], "text": "".join(lines)})
        page.run(complete, lambda _: summary())

    def open_todo():
        selected = choose_todo()
        if selected:
            page.go("notes", selected["text"])

    todo_items = []
    todos = card(page, recent)
    page.section("Буфер обмена")
    clips = page.rows(max_height=130)
    page.actions(("Вся история", lambda: page.go("clipboard")), ("Мониторинг ПК", lambda: page.go("monitor")))
    info = page.text("", 13, muted=True)

    def render(summary_data):
        todo_items[:] = summary_data["todos"]
        page.show_rows(todos, todo_items, lambda item: item["text"] or "Дело без названия")
        if not todo_items:
            todos.Items.Add("Все дела выполнены")
        page.show_rows(clips, summary_data["recent_clips"], lambda item: excerpt(item.get("text")))
        if not summary_data["recent_clips"]:
            clips.Items.Add("История пока пуста")
        stats = summary_data["stats"]
        info.Text = f"{stats['notes_count']} заметок  ·  {stats['clipboard_count']} записей в истории"

    def summary():
        page.run(lambda: page.get("/api/home/summary"), render, message="")

    summary()


def notes(page, query):
    search = page.field("Найти в заметках", query)
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
            box.Items.Add("Заметок пока нет" if not match else "Совпадений нет")

    def refresh():
        match = search.Text.strip()
        page.run(lambda: page.get("/api/notes/items?q=" + quote(match)),
                 lambda data: render(data, match), message="")

    def selected():
        records = page.selected(box, items) if items else []
        if not records:
            page.notice("Выбери заметку")
        return records[0] if records else None

    def edit(item=None):
        nonlocal editing
        editing = item
        editor.Visibility = Visibility.Visible
        title.Text = item["title"] if item else ""
        body.Text = item["text"] if item else ""
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
            page.notice("Заметка сохранена")
        page.run(lambda: page.post("/api/notes/" + kind, payload), done)

    def edit_selected():
        if (item := selected()) is not None:
            edit(item)

    def modify(action):
        if (item := selected()) is None:
            return
        if action == "delete" and not page.confirm("Удалить заметку?", "Заметка будет удалена окончательно."):
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

    page.actions(("Новая заметка", edit, True), ("Открыть", edit_selected), ("Закрепить / открепить", lambda: modify("pin")),
                 ("Удалить", lambda: modify("delete")))
    formats = page.choice("Формат экспорта", ("Markdown", "Обычный текст"))
    page.actions(("Экспорт заметки", lambda: export(True)), ("Экспорт всех заметок", lambda: export(False)))
    editor = make(StackPanel, Visibility=Visibility.Collapsed)
    page.add(editor)
    previous = page.panel
    page.panel = editor
    page.section("Редактор заметки")
    title = page.field("Заголовок")
    body = page.field("Текст", multiline=True)
    page.actions(("Сохранить", save, True), ("Отмена", close_editor))
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
    search = page.field("Найти в истории", query)
    filters = ("", "link", "code", "text")
    kind = page.choice("Тип", ("Все записи", "Ссылки", "Код", "Текст"))
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
            state.Text = f"Записей: {data['total']}" + (" · Запись приостановлена" if paused else "")
            items[:] = data["items"]
            page.show_rows(box, items, lambda item: ("Закреплено · " if item["pinned"] else "")
                           + excerpt(item.get("text"), 165))
            if not items:
                box.Items.Add("Записей нет")

        path = f"/api/clipboard/items?q={quote(match[0])}&type={filters[max(match[1], 0)]}&limit=500"
        page.run(lambda: page.get(path), show, message="")

    def modify(action):
        selected = page.selected(box, items) if items else []
        if not selected:
            page.notice("Выбери запись")
            return
        if action == "delete" and not page.confirm("Удалить запись?", "Запись будет удалена окончательно."):
            return
        identity = selected[0]["id"]
        page.run(lambda: page.post("/api/clipboard/" + action, {"id": identity}),
                 lambda _: page.notice("Скопировано") if action == "copy" else refresh())

    def clear():
        if page.confirm("Очистить историю?", "Все записи, включая закреплённые, будут удалены."):
            page.run(lambda: page.post("/api/clipboard/clear", {}), lambda _: refresh())

    def pause():
        request = {"paused": not paused}
        page.run(lambda: page.post("/api/clipboard/pause", request), lambda _: refresh())

    page.actions(("Скопировать", lambda: modify("copy"), True), ("Закрепить / открепить", lambda: modify("pin")),
                 ("Удалить", lambda: modify("delete")), ("Пауза / продолжить", pause),
                 ("Обновить", refresh), ("Очистить историю", clear))
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
