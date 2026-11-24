"""Native QR-Drop, Trash, Monitor and About pages."""

from datetime import datetime
from io import BytesIO
from urllib.parse import urlencode

from System import Array, Byte, TimeSpan
from System.IO import MemoryStream
from System.Windows import HorizontalAlignment, MessageBox, Point, Thickness, Visibility, Window
from System.Windows.Automation import AutomationProperties
from System.Windows.Controls import Image, ProgressBar, ScrollBarVisibility, StackPanel, TextBlock
from System.Windows.Controls.Primitives import UniformGrid
from System.Windows.Media import PointCollection, Stretch
from System.Windows.Media.Imaging import BitmapCacheOption, BitmapImage
from System.Windows.Shapes import Polyline
from System.Windows.Threading import DispatcherTimer

from tools import paths


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
    import qrcode

    with BytesIO() as output:
        qrcode.make(url, box_size=5).save(output, format="PNG")
        data = output.getvalue()
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
    qr.Width = qr.Height = 195
    qr.Stretch = Stretch.Uniform
    qr.HorizontalAlignment = HorizontalAlignment.Left
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


def _vital(grid, label, *, meter=False, history=False):
    panel = StackPanel()
    panel.Margin = Thickness(0, 0, 18, 12)
    heading = TextBlock()
    heading.Text = label
    panel.Children.Add(heading)
    value = TextBlock()
    value.FontSize = 16
    value.Text = "—"
    panel.Children.Add(value)
    bar = None
    if meter:
        bar = ProgressBar()
        bar.Height = 7
        bar.Margin = Thickness(0, 6, 0, 2)
        bar.SetResourceReference(ProgressBar.ForegroundProperty, "Accent")
        AutomationProperties.SetName(bar, label)
        panel.Children.Add(bar)
    line = None
    if history:
        line = Polyline()
        line.Points = PointCollection()
        line.Height = 26
        line.Width = 160
        line.Margin = Thickness(0, 4, 0, 0)
        line.HorizontalAlignment = HorizontalAlignment.Left
        line.SetResourceReference(Polyline.StrokeProperty, "Accent")
        line.StrokeThickness = 1.5
        panel.Children.Add(line)
    grid.Children.Add(panel)
    return value, bar, line


def _percent(value):
    return f"{float(value or 0):g}%".replace(".", ",")


def _set_vital(vital, caption, percent=0, points=()):
    value, bar, line = vital
    value.Text = caption
    if bar is not None:
        bar.Value = min(100, max(0, percent))
    if line is not None:
        line.Points.Clear()
        if len(points) > 1:
            for index, number in enumerate(points):
                line.Points.Add(Point(index * 158 / (len(points) - 1), 25 - min(100, max(0, number)) * 0.24))


def _process_identity(item):
    return item["pid"], item["created"], item["name"]


def _monitor(page):
    grid = UniformGrid()
    grid.Columns = 2
    page.add(grid)
    cpu = _vital(grid, "Процессор", meter=True, history=True)
    ram = _vital(grid, "Память", meter=True, history=True)
    disk = _vital(grid, "Системный диск", meter=True)
    uptime = _vital(grid, "Без перезагрузки")
    live = page.text("Обновляется каждые 2 секунды", muted=True)
    query = page.field("Имя процесса или PID")
    order = page.choice("Сортировка", ["По процессору", "По памяти", "По имени"])
    paused = page.check("Пауза обновления")
    count = page.text("Процессы", size=19)
    rows = page.rows(max_height=390)
    page.text("Системные процессы защищены.", muted=True)
    processes = []
    shown = []

    def describe(item):
        suffix = "  ·  Hub" if item.get("own") else ""
        if not item["can_stop"] and item.get("why_not"):
            suffix += f"  ·  {item['why_not']}"
        started = f"  ·  запущен {_date(item['started'])}" if item.get("started") else ""
        return f"{item['name']}  ·  PID {item['pid']}  ·  ЦП {_percent(item['cpu'])}  ·  {_size(item['memory'])}{started}{suffix}"

    def render_list(*_):
        nonlocal shown
        search = query.Text.strip().casefold()
        items = [item for item in processes if search in item["name"].casefold() or search in str(item["pid"])]

        def sort_keys(item):
            name, cpu, memory = item["name"].casefold(), -item["cpu"], -item["memory"]
            return ((cpu, memory, name), (memory, cpu, name), (name, cpu, memory))[max(order.SelectedIndex, 0)]

        items.sort(key=sort_keys)
        count.Text = f"Процессы · {len(items)} из {len(processes)}" if search else f"Процессы · {len(items)}"
        shown = _replace_rows(page, rows, shown, items, describe, _process_identity)

    def render(data):
        nonlocal processes
        system = data["system"]
        memory, drive = system["memory"], system["disk"]
        history = data.get("history", [])
        _set_vital(cpu, f"{_percent(system['cpu'])}  ·  ядер: {system['cores']}", system["cpu"], [v["cpu"] for v in history])
        _set_vital(ram, f"{_percent(memory['percent'])}  ·  {_size(memory['used'])} из {_size(memory['total'])}",
                   memory["percent"], [v["memory"] for v in history])
        free = 100 - drive["percent"] if drive["total"] else 0
        _set_vital(disk, f"Свободно {_size(drive['free'])} из {_size(drive['total'])}" if drive["total"] else "—", free)
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
        live.Text = "Обновление приостановлено" if paused.IsChecked else "Обновляется каждые 2 секунды"
        refresh()

    def terminate():
        item = _selected(page, rows, shown, "Выбери процесс.")
        if not item:
            return
        if not item["can_stop"]:
            page.notice(item.get("why_not") or "Процесс защищён.")
            return
        pid, created, name = _process_identity(item)
        if not page.confirm("Закрыть процесс?", f"«{name}» (PID {pid}) завершится. Несохранённые данные будут потеряны."):
            return

        def finished(result):
            reload()
            page.notice(f"«{result['name']}» закрыт.")

        payload = {"pid": pid, "created": created, "name": name}
        page.run(lambda: page.post("/api/monitor/terminate", payload), finished, message="Закрываю процесс…")

    query.TextChanged += render_list
    order.SelectionChanged += render_list
    paused.Checked += toggle_pause
    paused.Unchecked += toggle_pause
    page.actions(("Закрыть процесс", terminate), ("Обновить", reload))
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
