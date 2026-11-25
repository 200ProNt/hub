"""Native QR-Drop, Trash, Monitor and About pages."""

from datetime import datetime
from urllib.parse import urlencode

from System import Array, Byte, TimeSpan
from System.IO import MemoryStream
from System.Windows import HorizontalAlignment, MessageBox, Point, Thickness, Visibility, Window
from System.Windows import FontWeights, GridLength, TextAlignment, TextTrimming, TextWrapping
from System.Windows.Automation import AutomationProperties
from System.Windows.Controls import Image, ProgressBar, ScrollBarVisibility, StackPanel, TextBlock
from System.Windows.Controls import Border, ColumnDefinition, Grid, ListBoxItem
from System.Windows.Controls.Primitives import UniformGrid
from System.Windows.Media import PointCollection, Stretch
from System.Windows.Media.Imaging import BitmapCacheOption, BitmapImage
from System.Windows.Shapes import Polyline
from System.Windows.Threading import DispatcherTimer

from tools import paths
from .widgets import label, make


def _size(value):
    size = float(value or 0)
    units = ("Б", "КБ", "МБ", "ГБ", "ТБ")
    for unit in units[:-1]:
        if size < 1024:
            return f"{size:g} {unit}" if unit == "Б" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} {units[-1]}"


def _date(timestamp):
    return datetime.fromtimestamp(timestamp).strftime("%d.%m.%Y %H:%M") if timestamp else ""


def _selected(page, box, items, label):
    selected = page.selected(box, items)
    if selected:
        return selected[0]
    page.notice(label)
    return None


def _replace_rows(page, box, old_items, new_items, fmt, key):
    selected = page.selected(box, old_items)
    chosen = key(selected[0]) if selected else None
    if old_items != new_items:
        page.show_rows(box, new_items, fmt)
        if chosen is not None:
            box.SelectedIndex = next((index for index, item in enumerate(new_items) if key(item) == chosen), -1)
    return new_items


def _poll(page, visible_element, seconds, refresh):
    timer = DispatcherTimer()
    timer.Interval = TimeSpan.FromSeconds(seconds)

    def tick(*_):
        if visible_element.IsVisible:
            refresh()

    timer.Tick += tick
    timer.Start()
    page.on_leave(timer.Stop)


def _loader(page, path, render):
    loading = False

    def work():
        try:
            return page.get(path), ""
        except Exception as error:
            return None, str(error)

    def finish(result):
        nonlocal loading
        loading = False
        data, error = result
        if data is None:
            page.notice(error)
        else:
            render(data)

    def refresh():
        nonlocal loading
        if not loading:
            loading = True
            page.run(work, finish, message="")

    return refresh


def _qr_bitmap(url):
    from tools.qrdrop import qr_png

    data = qr_png(url)
    stream = MemoryStream(Array[Byte](data))
    try:
        bitmap = BitmapImage()
        bitmap.BeginInit()
        bitmap.CacheOption = BitmapCacheOption.OnLoad
        bitmap.StreamSource = stream
        bitmap.EndInit()
        bitmap.Freeze()
        return bitmap
    finally:
        stream.Dispose()


def _qrdrop(page):
    page.text("Подключи телефон и компьютер к одной сети Wi-Fi, затем наведи камеру на QR-код.", muted=True)
    qr = Image()
    qr.Width = qr.Height = 207
    qr.Stretch = Stretch.Uniform
    qr.HorizontalAlignment = HorizontalAlignment.Left
    qr.Margin = Thickness(0, 3, 0, 12)
    qr.Visibility = Visibility.Collapsed
    AutomationProperties.SetName(qr, "QR-код подключения телефона")
    page.add(qr)
    address = page.field("Адрес для телефона")
    address.IsReadOnly = True
    info = {"url": "", "shared_files": [], "incoming_files": [], "incoming_texts": []}

    def render(data):
        url = data["url"]
        if url != info["url"]:
            address.Text = url
            try:
                qr.Source = _qr_bitmap(url)
                qr.Visibility = Visibility.Visible
            except (ImportError, OSError, ValueError):
                qr.Visibility = Visibility.Collapsed
                page.notice("QR-код недоступен. Открой адрес на телефоне вручную.")
            info["url"] = url
        for key, box, formatter, identity in (
            ("shared_files", shared, format_file, lambda item: item["name"]),
            ("incoming_files", incoming, format_incoming, lambda item: item["name"]),
            ("incoming_texts", messages, format_text, lambda item: (item["timestamp"], item["text"])),
        ):
            previous, info[key] = info[key], data.get(key, [])
            _replace_rows(page, box, previous, info[key], formatter, identity)

    refresh = _loader(page, "/api/drop/info", render)

    def copy_address():
        if info["url"]:
            page.copy(info["url"])

    def open_web():
        if info["url"]:
            page.open_url(info["url"])

    def format_file(item):
        return f"{item['name']}  ·  {_size(item['size'])}"

    def format_incoming(item):
        return f"{format_file(item)}  ·  {_date(item.get('mtime'))}"

    def format_text(item):
        text = " ".join(item["text"].split())
        preview = text[:180] + ("…" if len(text) > 180 else "")
        return f"{item['date']}  ·  {preview}"

    def update(route, payload, status):
        def finish(_result):
            refresh()
            page.notice(status)

        page.run(lambda: page.post(route, payload), finish)

    def share():
        path = share_path.Text.strip()
        if not path:
            page.notice("Выбери файл для отправки.")
            return
        update("/api/drop/share-file", {"path": path}, "Файл доступен на телефоне.")

    def unshare():
        item = _selected(page, shared, info["shared_files"], "Выбери файл в раздаче.")
        if item:
            update("/api/drop/unshare-file", {"name": item["name"]}, "Файл убран из раздачи.")

    def open_folder():
        folder = str(paths.DATA_DIR / "incoming")
        page.run(lambda: page.post("/api/drop/open", {"path": folder}), message="")

    def open_incoming():
        item = _selected(page, incoming, info["incoming_files"], "Выбери полученный файл.")
        if item:
            page.run(lambda: page.post("/api/open", {"path": item["path"]}), message="")

    def download():
        item = _selected(page, incoming, info["incoming_files"], "Выбери полученный файл.")
        if item:
            query = urlencode({"name": item["name"], "type": "incoming"})
            page.download(f"/api/drop/download?{query}", item["name"])

    def copy_text():
        item = _selected(page, messages, info["incoming_texts"], "Выбери сообщение.")
        if item:
            page.copy(item["text"])

    def show_message(*_):
        selected = page.selected(messages, info["incoming_texts"])
        text = selected[0]["text"] if selected else ""
        if message_body.Text != text:
            message_body.Text = text

    page.actions(("Скопировать адрес", copy_address), ("Открыть в браузере", open_web), ("Обновить", refresh))
    page.text("Файлы для телефона", size=19)
    share_path = page.file("Файл для отправки")
    shared = page.rows(max_height=130)
    page.actions(("Добавить в раздачу", share, True), ("Убрать из раздачи", unshare))
    page.text("Файлы с телефона", size=19)
    incoming = page.rows(max_height=160)
    page.actions(("Открыть папку", open_folder), ("Показать в проводнике", open_incoming), ("Сохранить как…", download))
    page.text("Текст и ссылки с телефона", size=19)
    messages = page.rows(max_height=180)
    message_body = page.field("Выбранное сообщение", multiline=True)
    message_body.IsReadOnly = True
    message_body.MaxHeight = 160
    message_body.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    messages.SelectionChanged += show_message
    page.actions(("Скопировать сообщение", copy_text))
    refresh()
    _poll(page, address, 4, refresh)


_TRASH_SOURCES = {
    "cleanup": "Уборка",
    "diskmap": "Карта диска",
    "bigfiles": "Большие файлы",
    "duplicates": "Дубликаты",
    "": "Дубликаты",
}


def _trash(page):
    page.text("Файлы, перемещённые инструментами Hub, можно вернуть в исходные папки.", muted=True)
    total = page.text("Загрузка корзины…", size=19)
    box = page.rows(max_height=430)
    runs = []
    summary = ""

    def describe(run):
        source = _TRASH_SOURCES.get(run.get("source", ""), "Удаление файлов")
        detail = [f"{source}  ·  {_date(run['time'])}  ·  {run['count']} шт.  ·  {_size(run['size'])}"]
        if run.get("folder"):
            detail.append(run["folder"])
        for item in run["items"]:
            size = "папка" if item.get("kind") == "dir" else _size(item["size"])
            detail.append(f"  {item['name']}  ·  {size}")
        if len(run["items"]) < run["count"]:
            detail.append(f"  и ещё {run['count'] - len(run['items'])}")
        return "\n".join(detail)

    def render(data):
        nonlocal runs, summary
        summary = f"{data['total_count']} шт.  ·  {_size(data['total_size'])}"
        total.Text = summary if data["runs"] else "Корзина пуста"
        runs = _replace_rows(page, box, runs, data["runs"], describe, lambda run: run["run_id"])

    refresh = _loader(page, "/api/trash/runs", render)

    def change(route, payload, status):
        def finish(result):
            refresh()
            errors = [f"{item.get('path') or item.get('run_id', '')} {item['reason']}".strip()
                      for item in result.get("errors", [])]
            page.notice("\n".join(errors) if errors else status(result))

        page.run(lambda: page.post(f"/api/trash/{route}", payload), finish)

    def restore():
        run = _selected(page, box, runs, "Выбери перенос в корзине.")
        if run:
            change("restore", {"run_id": run["run_id"]}, lambda result: f"Возвращено: {result['restored_count']} шт.")

    def purge():
        run = _selected(page, box, runs, "Выбери перенос в корзине.")
        if run and page.confirm("Удалить навсегда?", f"Будет удалено {run['count']} шт. из выбранного переноса. Восстановить их будет нельзя."):
            change("purge", {"run_ids": [run["run_id"]], "confirmed": True},
                   lambda result: f"Удалено навсегда. Освобождено {_size(result['freed'])}.")

    def empty():
        if not runs:
            page.notice("Корзина пуста.")
            return
        if page.confirm("Очистить корзину Hub?", f"В корзине {summary}. Восстановить файлы после очистки будет нельзя."):
            change("empty", {"confirmed": True}, lambda result: f"Корзина пуста. Освобождено {_size(result['freed'])}.")

    page.actions(("Вернуть на место", restore, True), ("Удалить навсегда", purge),
                 ("Очистить корзину", empty), ("Обновить", refresh))
    refresh()


def _vital(grid, title, *, meter=False, history=False):
    card = make(Border, Margin=Thickness(0, 0, 8, 8), Padding=Thickness(12, 9, 12, 8),
                BorderThickness=Thickness(1))
    card.SetResourceReference(Border.BackgroundProperty, "Glass")
    card.SetResourceReference(Border.BorderBrushProperty, "Edge")
    card.SetResourceReference(Border.CornerRadiusProperty, "PanelRadius")
    panel = StackPanel()
    card.Child = panel
    panel.Children.Add(label(title, 12, muted=True))
    value = label("—", 22)
    value.FontWeight = FontWeights.SemiBold
    value.Margin = Thickness(0, 1, 0, 0)
    panel.Children.Add(value)
    detail = label("", 12, muted=True)
    panel.Children.Add(detail)
    bar = None
    if meter:
        bar = make(ProgressBar, Height=9, Margin=Thickness(0, 7, 0, 0))
        AutomationProperties.SetName(bar, title)
        panel.Children.Add(bar)
    line = None
    if history:
        line = make(Polyline, Points=PointCollection(), Height=16, Width=108, Margin=Thickness(0, 3, 0, 0),
                    HorizontalAlignment=HorizontalAlignment.Left, StrokeThickness=1.25, Opacity=0.75)
        line.SetResourceReference(Polyline.StrokeProperty, "Accent")
        panel.Children.Add(line)
    grid.Children.Add(card)
    return value, detail, bar, line


def _percent(value):
    return f"{float(value or 0):g}%".replace(".", ",")


def _set_vital(vital, caption, description="", percent=0, points=()):
    value, detail, bar, line = vital
    value.Text = caption
    detail.Text = description
    if bar is not None:
        bar.Value = min(100, max(0, percent))
    if line is not None:
        line.Points.Clear()
        if len(points) > 1:
            for index, number in enumerate(points):
                line.Points.Add(Point(index * 106 / (len(points) - 1), 15 - min(100, max(0, number)) * 0.14))


def _process_identity(item):
    return item["pid"], item["name"], item["creation"]


def _process_columns(*values, heading=False):
    grid = Grid()
    for index, (value, width) in enumerate(zip(values, (None, 72, 96, 73))):
        definition = ColumnDefinition()
        if width is not None:
            definition.Width = GridLength(width)
        grid.ColumnDefinitions.Add(definition)
        cell = label(value, 12 if heading else 13, muted=heading)
        cell.TextWrapping = TextWrapping.NoWrap
        cell.TextTrimming = TextTrimming.CharacterEllipsis
        if heading:
            cell.FontWeight = FontWeights.SemiBold
        if index:
            cell.TextAlignment = TextAlignment.Right
        Grid.SetColumn(cell, index)
        grid.Children.Add(cell)
    return grid


def _monitor(page):
    grid = page.add(make(UniformGrid, Columns=2, Margin=Thickness(0, 0, -8, 0)))
    grid.SizeChanged += lambda *_: setattr(grid, "Columns", 4 if grid.ActualWidth >= 720 else 2)
    cpu = _vital(grid, "Процессор", meter=True, history=True)
    ram = _vital(grid, "Память", meter=True, history=True)
    disk = _vital(grid, "Системный диск", meter=True)
    uptime = _vital(grid, "Без перезагрузки")

    filters = page.add(Grid())
    query = page.field("Имя процесса или PID")
    order = page.choice("Сортировка", ["По процессору", "По памяти", "По имени"])
    for index, field in enumerate((query, order)):
        group = field.Parent
        page.panel.Children.Remove(group)
        if index == 0:
            group.Margin = Thickness(0, 2, 10, 8)
        filters.ColumnDefinitions.Add(ColumnDefinition())
        Grid.SetColumn(group, index)
        filters.Children.Add(group)

    state = page.add(Grid())
    state.ColumnDefinitions.Add(make(ColumnDefinition, Width=GridLength.Auto))
    state.ColumnDefinitions.Add(ColumnDefinition())
    paused = page.check("Пауза обновления")
    page.panel.Children.Remove(paused)
    state.Children.Add(paused)
    live = label("Обновление каждые 2 с", 12, muted=True)
    live.Margin = Thickness(10, 5, 0, 6)
    live.TextAlignment = TextAlignment.Right
    Grid.SetColumn(live, 1)
    state.Children.Add(live)

    count = page.section("Процессы")
    processes = []
    shown = []

    def selected(*_):
        selection = page.selected(rows, shown)
        item = selection[0] if selection else None
        stop_button.IsEnabled = bool(item and item["can_stop"])
        minimize_button.IsEnabled = bool(item and item.get("can_minimize"))
        if not item:
            info.Text = "Выбери процесс." if shown else ("Нет подходящих процессов." if processes else "Загружаю процессы…")
        elif not item["can_stop"]:
            info.Text = item["why_not"]
        elif not item.get("can_minimize"):
            info.Text = "У выбранного процесса нет видимых окон."
        else:
            info.Text = f"Выбран {item['name']} · PID {item['pid']}"

    def render_list(*_):
        nonlocal shown
        search = query.Text.strip().casefold()
        items = [item for item in processes if search in item["name"].casefold() or search in str(item["pid"])]

        def sort_keys(item):
            name, cpu, memory = item["name"].casefold(), -item["cpu"], -item["memory"]
            keys = ((cpu, memory, name), (memory, cpu, name), (name, cpu, memory))
            return (*keys[max(order.SelectedIndex, 0)], item["pid"])

        items.sort(key=sort_keys)
        count.Text = f"Процессы · {len(items)} из {len(processes)}" if search else f"Процессы · {len(items)}"
        selection = page.selected(rows, shown)
        chosen = _process_identity(selection[0]) if selection else None
        had_focus = rows.IsKeyboardFocusWithin
        for index, item in enumerate(items):
            if index >= rows.Items.Count:
                content = _process_columns("", "", "", "")
                rows.Items.Add(make(ListBoxItem, Content=content, Tag=index, Padding=Thickness(8, 4, 8, 4)))
            elif item == shown[index]:
                continue
            row = rows.Items[index]
            values = item["name"], _percent(item["cpu"]), _size(item["memory"]), str(item["pid"])
            for cell, value in zip(row.Content.Children, values):
                cell.Text = value
            AutomationProperties.SetName(row, f"{values[0]}, ЦП {values[1]}, память {values[2]}, PID {values[3]}")
            started = f"\nЗапущен {_date(item['started'])}" if item.get("started") else ""
            protected = f"\n{item['why_not']}" if item.get("why_not") else ""
            row.ToolTip = f"{values[0]} · PID {values[3]}{started}{protected}"
        shown = items
        while rows.Items.Count > len(items):
            rows.Items.RemoveAt(rows.Items.Count - 1)
        index = next((i for i, item in enumerate(items) if _process_identity(item) == chosen), -1)
        if rows.SelectedIndex != index:
            rows.SelectedIndex = index
            if had_focus and index >= 0:
                rows.ScrollIntoView(rows.Items[index])
                rows.Items[index].Focus()
        selected()

    def render(data):
        nonlocal processes
        system = data["system"]
        memory, drive = system["memory"], system["disk"]
        history = data.get("history", [])
        _set_vital(cpu, _percent(system["cpu"]), f"Ядер: {system['cores']}", system["cpu"], [v["cpu"] for v in history])
        _set_vital(ram, _percent(memory["percent"]), f"{_size(memory['used'])} из {_size(memory['total'])}",
                   memory["percent"], [v["memory"] for v in history])
        if drive["total"]:
            _set_vital(disk, _size(drive["free"]), f"Свободно из {_size(drive['total'])}", 100 - drive["percent"])
        else:
            _set_vital(disk, "—")
        total_hours, minutes = divmod(int(system["uptime"]) // 60, 60)
        days, hours = divmod(total_hours, 24)
        _set_vital(uptime, f"{days} д  {hours} ч  {minutes} мин" if days else f"{hours} ч  {minutes} мин")
        processes = data["processes"]
        render_list()

    reload = _loader(page, "/api/monitor/snapshot", render)

    def refresh():
        if not paused.IsChecked:
            reload()

    def toggle_pause(*_):
        live.Text = "Обновление на паузе" if paused.IsChecked else "Обновление каждые 2 с"
        refresh()

    def process_action(action):
        item = _selected(page, rows, shown, "Выбери процесс.")
        if not item:
            return
        if not item["can_stop"]:
            page.notice(item.get("why_not") or "Процесс защищён.")
            return
        pid, name, creation = _process_identity(item)
        if action == "terminate":
            if not page.confirm("Закрыть процесс?", f"«{name}» (PID {pid}) завершится. Несохранённые данные будут потеряны."):
                return

        def finished(result):
            reload()
            if action == "terminate":
                page.notice(f"«{result['name']}» закрыт.")
            else:
                page.notice(f"Сворачивание запрошено. Окон: {result['requested']}.")

        payload = {"pid": pid, "created": item["created"], "name": name, "creation": creation}
        message = "Закрываю процесс…" if action == "terminate" else "Сворачиваю окна…"
        page.run(lambda: page.post(f"/api/monitor/{action}", payload), finished, message=message)

    minimize_button, stop_button, _ = page.actions(("Свернуть окна", lambda: process_action("minimize")),
                                                   ("Закрыть процесс", lambda: process_action("terminate")),
                                                   ("Обновить", reload))
    info = page.text("", muted=True)
    header = _process_columns("Имя процесса", "ЦП", "Память", "PID", heading=True)
    header.Margin = Thickness(14, 0, 23, 3)
    page.add(header)
    rows = page.rows(max_height=350)
    AutomationProperties.SetName(rows, "Процессы")
    query.TextChanged += render_list
    order.SelectionChanged += render_list
    paused.Checked += toggle_pause
    paused.Unchecked += toggle_pause
    rows.SelectionChanged += selected
    selected()
    refresh()
    _poll(page, grid, 2, refresh)


def _about(page):
    title = page.text("Hub", size=24)
    page.text("Локальные инструменты для Windows. Данные хранятся на этом компьютере.", muted=True)
    details = page.text("Загрузка сведений…", muted=True)
    project = page.field("Папка приложения")
    project.IsReadOnly = True
    info = {}

    def open_path(key):
        if info.get(key):
            page.run(lambda: page.post("/api/open", {"path": info[key]}), message="")

    def backup():
        filename = f"hub_backup_{datetime.now():%Y-%m-%d}.zip"
        page.download("/api/system/backup", filename)

    def shutdown():
        if page.confirm("Выключить Hub?", "Окно, обмен с телефоном и фоновая запись буфера обмена будут остановлены."):
            page.run(lambda: page.post("/api/system/shutdown", {}), message="Выключаю Hub…")

    def tutorial():
        MessageBox.Show(
            Window.GetWindow(title),
            "Выбирай инструменты на боковой панели.\n\n"
            "Файлы, перемещённые в корзину Hub, можно вернуть на место.\n\n"
            "Открой QR-Drop, чтобы передать файлы и текст по Wi-Fi.\n\n"
            "Тему оформления и параметры запуска можно поменять в настройках.",
            "Знакомство с Hub",
        )

    def render_shortcuts(data):
        desktop_button.Visibility = start_button.Visibility = Visibility.Visible if data.get("supported") else Visibility.Collapsed
        desktop_button.Content = "Удалить ярлык с рабочего стола" if data.get("desktop") else "Ярлык на рабочий стол"
        start_button.Content = "Удалить ярлык из меню «Пуск»" if data.get("start_menu") else "Ярлык в меню «Пуск»"

    def toggle_shortcut(target):
        def work():
            status = page.get("/api/shortcuts/status")
            action = "remove" if status[target] else "create"
            return page.post(f"/api/shortcuts/{action}", {"target": target})

        page.run(work, render_shortcuts)

    def render(data):
        info.update(data)
        title.Text = f"Hub {data['version']}"
        details.Text = f"Автор: {data['author']}  ·  {data['license']}  ·  инструментов: {data['tools']}  ·  Python {data['python']} + WPF"
        project.Text = data["folder"]
        release_notes.Text = "\n\n".join(
            f"{release['version']}  ·  {release['date']}\n" + "\n".join(f"• {item}" for item in release["items"])
            for release in data.get("changes", [])
        ) or "История пока пуста."
        license_text.Text = data.get("license_text") or "Файл LICENSE недоступен."

    page.actions(("Папка приложения", lambda: open_path("folder")),
                 ("README в проводнике", lambda: open_path("readme")),
                 ("Резервная копия (ZIP)", backup), ("Показать обучение", tutorial), ("Выключить Hub", shutdown))
    desktop_button, start_button = page.actions(("Ярлык на рабочий стол", lambda: toggle_shortcut("desktop")),
                                               ("Ярлык в меню «Пуск»", lambda: toggle_shortcut("start_menu")))
    desktop_button.Visibility = start_button.Visibility = Visibility.Collapsed
    release_notes = page.field("История версий", multiline=True)
    release_notes.IsReadOnly = True
    release_notes.MaxHeight = 240
    release_notes.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    license_text = page.field("Текст лицензии MIT", multiline=True)
    license_text.IsReadOnly = True
    license_text.MaxHeight = 220
    license_text.VerticalScrollBarVisibility = ScrollBarVisibility.Auto

    def load():
        return page.get("/api/about"), page.get("/api/shortcuts/status")

    def show(data):
        render(data[0])
        render_shortcuts(data[1])

    page.run(load, show)


def mount(page, tool_id):
    {"qrdrop": _qrdrop, "trash": _trash, "monitor": _monitor, "about": _about}[tool_id](page)
