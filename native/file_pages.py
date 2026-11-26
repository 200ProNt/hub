"""Native pages for reviewing, organizing and cleaning up local files."""

from collections import Counter
from datetime import datetime
from io import BytesIO
from math import cos, pi, sin, tau
from pathlib import PureWindowsPath
from urllib.parse import quote, urlencode

from tools.i18n import tr


def _size(value):
    units = (tr("B", "Б"), tr("KB", "КБ"), tr("MB", "МБ"), tr("GB", "ГБ"), tr("TB", "ТБ"), tr("PB", "ПБ"))
    amount = value or 0
    for unit in units[:-1]:
        if amount < 1024:
            break
        amount /= 1024
    else:
        unit = units[-1]
    return f"{amount:.1f}".removesuffix(".0").replace(".", ",") + f" {unit}"


def _date(timestamp):
    if timestamp is None:
        return ""
    try:
        return datetime.fromtimestamp(timestamp).strftime("%d.%m.%Y")
    except (OSError, OverflowError, ValueError):
        return ""


def _file_line(item):
    details = [item.get("rel", item["path"]), _size(item["size"])]
    timestamp = item.get("mtime", item.get("modified"))
    if date := _date(timestamp):
        details.append(date)
    if item.get("unsafe"):
        details.append(tr("this file cannot be moved or deleted", "файл недоступен для переноса или удаления"))
    return "  ·  ".join(details)


def _warnings(result):
    parts = []
    if result.get("truncated"):
        parts.append(tr("The scan reached its limit. Some results are missing.", "Достигнут предел обхода, показана часть результатов."))
    errors = result.get("errors") or []
    for error in errors[:5]:
        path = error.get("path") or error.get("file")
        parts.append(f"{path} — {error['reason']}" if path else error["reason"])
    if len(errors) > 5:
        parts.append(tr(f"Total errors: {len(errors)}.", f"Всего ошибок: {len(errors)}."))
    return "\n".join(parts)


def _result_text(result, count_key, caption):
    text = f"{caption}: {result.get(count_key + '_count', 0)} · {_size(result.get(count_key + '_size'))}"
    warnings = _warnings(result)
    return f"{text}\n{warnings}" if warnings else text


def _open(page, path):
    if path:
        page.run(lambda: page.post("/api/open", {"path": path}), message=tr("Opening File Explorer…", "Открываю Проводник…"))
    else:
        page.notice(tr("Select a file or folder first.", "Сначала выбери файл или папку."))


def _target(page, folder):
    path = str(folder.Text).strip()
    if not path:
        page.notice(tr("Choose a folder.", "Укажи папку."))
    return path


def _undo(page, tool, changed):
    endpoint = f"/api/{tool}"

    def act(data):
        run = data.get("last_run")
        if not run:
            page.notice(tr("There are no actions to undo.", "Нет операций, которые можно отменить."))
            return
        details = tr(f"Restore: {run['count']} · {_size(run['size'])}", f"Вернуть на место: {run['count']} · {_size(run['size'])}")
        if run.get("folder"):
            details += f"\n{run['folder']}"
        if page.confirm(tr("Undo the last action?", "Отменить последнее действие?"), details):
            page.run(
                lambda: page.post(f"{endpoint}/undo", {"run_id": run["run_id"]}),
                lambda result: changed(_result_text(result, "restored", tr("Restored", "Возвращено"))),
                tr("Restoring…", "Возвращаю на место…"),
            )

    return lambda: page.run(lambda: page.get(f"{endpoint}/last-run"), act, tr("Checking history…", "Проверяю историю…"))


def _remove(page, tool, items, mode, changed, folder=""):
    if not items:
        page.notice(tr("Select what to remove.", "Выбери, что убрать."))
        return
    if any(item.get("unsafe") for item in items):
        page.notice(tr("Deselect files that cannot be removed.", "Сними отметку с недоступных файлов."))
        return
    deleting = mode == "delete"
    title = tr("Delete permanently?", "Удалить навсегда?") if deleting else tr("Move to the Hub Trash?", "Перенести в корзину Хаба?")
    details = [
        tr(
            f"Selected: {len(items)} · {_size(sum(item['size'] for item in items))}",
            f"Выбрано: {len(items)} · {_size(sum(item['size'] for item in items))}",
        ),
        *[item["path"] for item in items[:5]],
    ]
    if len(items) > 5:
        details.append(tr(f"And {len(items) - 5} more", f"Ещё: {len(items) - 5}"))
    details.append(tr("Deleted items cannot be restored.", "Вернуть удалённое будет невозможно.") if deleting else tr(
        "You can undo the move.",
        "Перенос можно отменить.",
    ))
    if not page.confirm(title, "\n".join(details)):
        return

    paths = [item["path"] for item in items]
    body = {"mode": mode, "confirmed": deleting}
    if tool == "cleanup":
        body.update(paths=paths, folder=folder)
    elif tool == "dupes":
        body.update(files=paths, folder=folder)
    else:
        body["path"] = paths[0]
    page.run(
        lambda: page.post(f"/api/{tool}/remove", body),
        lambda result: changed(_result_text(result, "removed", tr("Deleted", "Удалено") if deleting else tr("Moved to Hub Trash", "В корзину Хаба"))),
        tr("Deleting…", "Удаляю…") if deleting else tr("Moving to Trash…", "Переношу в корзину…"),
    )


class _Selection:
    """Keep checked paths when a result filter hides their rows."""

    def __init__(self, page, box, formatter):
        self.page = page
        self.box = box
        self.formatter = formatter
        self.visible = []
        self.paths = set()

    def capture(self):
        self.paths.difference_update(item["path"] for item in self.visible)
        self.paths.update(item["path"] for item in self.page.selected(self.box, self.visible))

    def show(self, items):
        self.capture()
        self.visible = items
        self._paint()

    def _paint(self):
        self.box.UnselectAll()
        self.page.show_rows(self.box, self.visible, self.formatter)
        indexes = [index for index, item in enumerate(self.visible) if item["path"] in self.paths]
        if self.visible and len(indexes) == len(self.visible):
            self.box.SelectAll()
        else:
            for index in indexes:
                self.box.SelectedItems.Add(self.box.Items[index])

    def select(self, items):
        self.paths = {item["path"] for item in items}
        self._paint()

    def extend(self, items):
        self.capture()
        self.paths.update(item["path"] for item in items if not item.get("unsafe"))
        self._paint()

    def picked(self, items):
        self.capture()
        return [item for item in items if item["path"] in self.paths]


def _csv(text):
    return [part.strip() for part in text.split(",") if part.strip()]


def _sorter_rules(text):
    rules = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        category, separator, extensions = line.partition(" = ")
        if not separator:
            category, separator, extensions = line.rpartition("=")
        if not separator or not category.strip():
            raise ValueError(tr(
                f"Line {number}: separate the category and extensions with =.",
                f"Строка {number}: укажи категорию и расширения через знак =.",
            ))
        rules.append({"name": category.strip(), "extensions": _csv(extensions)})
    return rules


def _sorter(page):
    folder = page.folder(tr("Folder to sort", "Папка для сортировки"), page.default_folder)
    state = {"items": [], "folder": ""}

    def refresh(status=""):
        scan(state["folder"], status) if state["folder"] else page.notice(status)

    page.actions(
        (tr("Preview", "Предпросмотр"), lambda: scan(_target(page, folder)), True),
        (tr("Show folder in File Explorer", "Показать папку в Проводнике"), lambda: _open(page, state["folder"] or _target(page, folder))),
        (tr("Undo last move", "Отменить последний перенос"), _undo(page, "sorter", refresh)),
    )
    summary = page.text("", muted=True)
    query = page.field(tr("Search by filename", "Поиск по имени файла"))
    category = page.choice(tr("Category", "Категория"), [tr("All categories", "Все категории")])
    box = page.rows(multiple=True)
    pick = _Selection(
        page, box, lambda item: f"{item['name']}  →  {item['dest_rel']}  ·  {_size(item['size'])}  ·  {_date(item['mtime'])}"
    )

    def filter_rows(*_):
        search = str(query.Text).strip().casefold()
        selected = category.SelectedItem if category.SelectedIndex > 0 else None
        pick.show([
            item for item in state["items"]
            if search in item["name"].casefold() and (selected is None or item["category"] == selected)
        ])

    def scan(path, status=""):
        if not path:
            return

        def done(data):
            state.update(items=data["items"], folder=data["folder"])
            folder.Text = data["folder"]
            summary.Text = tr(
                f"Files: {data['total']} · Categories: {len(data['counts'])} · {_size(data['total_size'])}",
                f"Файлов: {data['total']} · Категорий: {len(data['counts'])} · {_size(data['total_size'])}",
            )
            category.Items.Clear()
            for name in [tr("All categories", "Все категории"), *data["categories"]]:
                category.Items.Add(name)
            category.SelectedIndex = 0
            filter_rows()
            pick.select(data["items"])
            if status:
                page.notice(status)

        page.run(lambda: page.post("/api/sorter/scan", {"folder": path}), done, tr(
            "Preparing the sorting plan…",
            "Готовлю план сортировки…",
        ))

    def apply():
        items = pick.picked(state["items"])
        if not items:
            page.notice(tr("Select files to move.", "Выбери файлы для переноса."))
            return
        if not page.confirm(
            tr("Move the selected files?", "Перенести выбранные файлы?"),
            tr(
                f"{state['folder']}\nSelected: {len(items)} · {_size(sum(item['size'] for item in items))}",
                f"{state['folder']}\nВыбрано: {len(items)} · {_size(sum(item['size'] for item in items))}",
            ),
        ):
            return
        body = {"folder": state["folder"], "files": [item["path"] for item in items]}
        page.run(
            lambda: page.post("/api/sorter/apply", body),
            lambda result: refresh(_result_text(result, "moved", tr("Moved", "Перенесено"))),
            tr("Moving files…", "Переношу файлы…"),
        )

    query.TextChanged += filter_rows
    category.SelectionChanged += filter_rows
    page.actions(
        (tr("Select visible", "Выбрать видимые"), lambda: pick.extend(pick.visible)),
        (tr("Clear selection", "Снять отметки"), lambda: pick.select([])),
        (tr("Move selected", "Перенести выбранные"), apply, True),
    )
    rules = page.field(tr(
        "Sorting rules. Use one Category = .ext, .ext rule per line.",
        "Правила сортировки. На каждой строке укажи «Категория = .ext, .ext»",
    ), multiline=True)
    rules_loaded = False

    def show_rules(data):
        nonlocal rules_loaded
        rules.Text = "\n".join(
            f"{item['name']} = {', '.join(item['extensions'])}" for item in data["rules"]
        )
        rules_loaded = True

    def load_rules():
        page.run(lambda: page.get("/api/sorter/rules"), show_rules, tr("Loading rules…", "Загружаю правила…"))

    def save_rules(reset=False):
        if reset and not page.confirm(tr("Restore the default rules?", "Вернуть правила по умолчанию?"), tr(
            "Your categories and extensions will be replaced.",
            "Твои категории и расширения будут заменены.",
        )):
            return
        if not reset and not rules_loaded:
            page.notice(tr("Load the current rules first.", "Сначала загрузи текущие правила."))
            return
        try:
            body = {"reset": True} if reset else {"rules": _sorter_rules(str(rules.Text))}
        except ValueError as error:
            page.notice(str(error))
            return

        def done(data):
            show_rules(data)
            refresh(tr("Sorting rules saved.", "Правила сортировки сохранены."))

        page.run(lambda: page.post("/api/sorter/rules", body), done, tr("Saving rules…", "Сохраняю правила…"))

    page.actions(
        (tr("Load rules", "Загрузить правила"), load_rules),
        (tr("Save rules", "Сохранить правила"), save_rules),
        (tr("Defaults", "По умолчанию"), lambda: save_rules(True)),
    )


def _duplicates(page):
    from PIL import Image as PILImage
    from System import Array, Byte
    from System.IO import MemoryStream
    from System.Windows import Visibility
    from System.Windows.Controls import Image
    from System.Windows.Media.Imaging import BitmapCacheOption, BitmapImage

    folder = page.folder(tr("Folder to scan for duplicates", "Папка для поиска дубликатов"), page.default_folder)
    recursive = page.check(tr("Include subfolders", "Искать в подпапках"), True)
    state = {"groups": [], "items": [], "request": None, "limit": 500}

    def refresh(status=""):
        if state["request"]:
            scan(state["request"], status)
        else:
            page.notice(status)

    page.actions(
        (tr("Find duplicates", "Найти дубликаты"), lambda: scan({"folder": _target(page, folder), "recursive": bool(recursive.IsChecked)}), True),
        (tr("Undo last move", "Вернуть последний перенос"), _undo(page, "dupes", refresh)),
    )
    summary = page.text(tr("The scan checks files of at least 1 KB.", "Будут проверены файлы от 1 КБ."), muted=True)
    query = page.field(tr("Search by filename or folder", "Поиск по имени или папке"))
    count = page.text("", muted=True)
    box = page.rows(multiple=True)
    pick = _Selection(page, box, lambda item: tr(
        f"Group {item['group']}  ·  {_file_line(item)}",
        f"Группа {item['group']}  ·  {_file_line(item)}",
    ))
    preview = Image()
    preview.Height = 180
    preview.Visibility = Visibility.Collapsed

    def close_image(*_):
        preview.Source = None
        preview.Visibility = Visibility.Collapsed

    def filter_rows():
        search = str(query.Text).strip().casefold()
        results = [item for item in state["items"] if search in item["rel"].casefold()]
        pick.show(results[:state["limit"]])
        count.Text = tr(f"Showing {len(pick.visible)} of {len(results)}.", f"Показано {len(pick.visible)} из {len(results)}.") if state["request"] else ""

    def reset_limit(*_):
        state["limit"] = 500
        filter_rows()

    def more():
        state["limit"] += 500
        filter_rows()

    def scan(body, status=""):
        if not body["folder"]:
            return

        def done(data):
            state["request"] = {**body, "folder": data["folder"]}
            folder.Text = data["folder"]
            state["groups"] = [
                [{**item, "group": index} for item in group["files"]]
                for index, group in enumerate(data["groups"], 1)
            ]
            state["items"] = [item for group in state["groups"] for item in group]
            summary.Text = (
                tr(
                    f"Groups: {data['groups_count']} · Extra copies: {data['duplicate_files']} · Space used: {_size(data['wasted'])}",
                    f"Групп: {data['groups_count']} · Лишних копий: {data['duplicate_files']} · Занимают {_size(data['wasted'])}",
                )
            )
            pick.select([])
            reset_limit()
            if notice := "\n".join(filter(None, (status, _warnings(data)))):
                page.notice(notice)

        page.run(lambda: page.post("/api/dupes/scan", body), done, tr("Comparing file contents…", "Сравниваю содержимое файлов…"))

    def extra_copies(group_number=None):
        extras = [
            item for group in state["groups"] if group_number is None or group[0]["group"] == group_number
            for item in group[1:]
        ]
        pick.select(extras)

    def selected_group():
        chosen = page.selected(box, pick.visible)
        if chosen:
            extra_copies(chosen[0]["group"])
        else:
            page.notice(tr("Select a file from the group.", "Выбери файл из нужной группы."))

    def reveal():
        chosen = page.selected(box, pick.visible)
        _open(page, chosen[0]["path"] if chosen else "")

    def show_preview():
        chosen = page.selected(box, pick.visible)
        if not chosen:
            page.notice(tr("Select an image from the results.", "Выбери изображение из результатов."))
            return
        name = chosen[0]["path"]
        # The existing endpoint decodes the path after parsing the query string.
        endpoint = "/api/dupes/thumb?" + urlencode({"path": quote(name, safe="")})

        def load():
            with PILImage.open(BytesIO(page.bytes(endpoint))) as original, BytesIO() as rendered:
                original.thumbnail((480, 180))
                original.convert("RGBA").save(rendered, format="PNG")
                return rendered.getvalue()

        def done(data):
            stream = MemoryStream(Array[Byte](data))
            try:
                image = BitmapImage()
                image.BeginInit()
                image.CacheOption = BitmapCacheOption.OnLoad
                image.StreamSource = stream
                image.EndInit()
                image.Freeze()
            except Exception:
                page.notice(tr("Windows could not display this image.", "Windows не удалось показать это изображение."))
                return
            finally:
                stream.Dispose()
            preview.Source = image
            preview.Visibility = Visibility.Visible

        page.run(load, done, tr("Opening image…", "Открываю изображение…"))

    def remove():
        items = pick.picked(state["items"])
        counts = Counter(item["group"] for item in items)
        if any(counts[group[0]["group"]] == len(group) for group in state["groups"]):
            page.notice(tr("Keep at least one copy in each group.", "Оставь хотя бы одну копию в каждой группе."))
            return
        path = state["request"]["folder"] if state["request"] else ""
        _remove(page, "dupes", items, "trash", refresh, path)

    query.TextChanged += reset_limit
    box.SelectionChanged += close_image
    box.MouseDoubleClick += lambda *_: reveal()
    page.actions(
        (tr("Select extra copies", "Отметить лишние копии"), extra_copies),
        (tr("Select extras in this group", "Отметить лишние в этой группе"), selected_group),
        (tr("Clear selection", "Снять отметки"), lambda: pick.select([])),
        (tr("Show in File Explorer", "Показать в Проводнике"), reveal),
    )
    page.actions((tr("Preview image", "Предпросмотр изображения"), show_preview))
    page.add(preview)
    page.actions((tr("Remove selected copies", "Убрать выбранные копии"), remove, True))
    page.actions((tr("Show more", "Показать ещё"), more))


def _bigfiles(page):
    folder = page.folder(tr("Folder to scan for large files", "Папка для поиска крупных файлов"), page.default_folder)
    sizes = (5, 20, 100, 500, 1024)
    minimum = page.choice(tr("Minimum size", "Минимальный размер"), [tr("5 MB", "5 МБ"), tr("20 MB", "20 МБ"), tr("100 MB", "100 МБ"), tr("500 MB", "500 МБ"), tr("1 GB", "1 ГБ")], 1)
    state = {"items": [], "request": None}

    def refresh(status=""):
        if state["request"]:
            scan(state["request"], status)
        else:
            page.notice(status)

    page.actions(
        (tr("Find large files", "Найти крупные файлы"), lambda: scan({
            "folder": _target(page, folder), "min_size": sizes[minimum.SelectedIndex] * 1024 * 1024,
        }), True),
        (tr("Undo last move", "Вернуть последний перенос"), _undo(page, "bigfiles", refresh)),
    )
    summary = page.text("", muted=True)
    box = page.rows()

    def scan(body, status=""):
        if not body["folder"]:
            return

        def done(data):
            state.update(items=data["files"], request={**body, "folder": data["folder"]})
            folder.Text = data["folder"]
            summary.Text = (
                tr(
                    f"Found: {data['matched']} · {_size(data['matched_size'])} · Shown: {len(data['files'])} · Checked: {data['scanned']}",
                    f"Найдено: {data['matched']} · {_size(data['matched_size'])} · Показано: {len(data['files'])} · Проверено: {data['scanned']}",
                )
            )
            box.SelectedIndex = -1
            page.show_rows(box, state["items"], _file_line)
            if notice := "\n".join(filter(None, (status, _warnings(data)))):
                page.notice(notice)

        page.run(lambda: page.post("/api/bigfiles/scan", body), done, tr("Looking for large files…", "Ищу крупные файлы…"))

    def reveal():
        chosen = page.selected(box, state["items"])
        _open(page, chosen[0]["path"] if chosen else "")

    box.MouseDoubleClick += lambda *_: reveal()
    page.actions(
        (tr("Show in File Explorer", "Показать в Проводнике"), reveal),
        (tr("Move to Hub Trash", "В корзину Хаба"), lambda: _remove(page, "bigfiles", page.selected(box, state["items"]), "trash", refresh)),
        (tr("Delete permanently", "Удалить навсегда"), lambda: _remove(page, "bigfiles", page.selected(box, state["items"]), "delete", refresh)),
    )

def _disk_chart(canvas, entries, activate):
    from System.Windows import Point, Size, Visibility
    from System.Windows.Media import Color, SolidColorBrush, StreamGeometry, SweepDirection
    from System.Windows.Shapes import Path as ShapePath

    canvas.Children.Clear()
    total = sum(item["size"] for item in entries)
    canvas.Visibility = Visibility.Visible if total else Visibility.Collapsed
    if not total:
        return
    colors = (
        (52, 154, 242), (73, 191, 156), (255, 170, 84), (165, 130, 236), (241, 115, 152),
        (86, 202, 216), (212, 179, 95), (115, 133, 224), (219, 134, 123), (115, 128, 147),
    )
    shown = entries[:9]
    if len(entries) > len(shown):
        rest = sum(item["size"] for item in entries[len(shown):])
        shown = [*shown, {"name": tr("Other", "Остальное"), "kind": "rest", "size": rest}]
    angle = -pi / 2

    def polar(radius, radians):
        return Point(76 + radius * cos(radians), 76 + radius * sin(radians))

    for item, rgb in zip(shown, colors):
        if not item["size"]:
            continue
        end = angle + tau * item["size"] / total
        half = (angle + end) / 2
        figure = StreamGeometry()
        path = figure.Open()
        path.BeginFigure(polar(72, angle), True, True)
        for radians in (half, end):
            path.ArcTo(polar(72, radians), Size(72, 72), 0, False, SweepDirection.Clockwise, True, False)
        path.LineTo(polar(46, end), True, False)
        for radians in (half, angle):
            path.ArcTo(polar(46, radians), Size(46, 46), 0, False, SweepDirection.Counterclockwise, True, False)
        path.Close()
        figure.Freeze()

        slice_shape = ShapePath()
        slice_shape.Data = figure
        slice_shape.Fill = SolidColorBrush(Color.FromRgb(*rgb))
        slice_shape.ToolTip = f"{item['name']} · {_size(item['size'])} · {item['size'] / total:.1%}"
        if item["kind"] != "rest":
            slice_shape.MouseLeftButtonUp += lambda sender, event, entry=item: activate(entry)
        canvas.Children.Add(slice_shape)
        angle = end


def _diskmap(page):
    from System.Windows import HorizontalAlignment, Visibility
    from System.Windows.Controls import Canvas
    from System.Windows.Input import Key

    folder = page.folder(tr("Folder or drive", "Папка или диск"), page.default_folder)
    state = {"data": None, "files": [], "files_open": False, "limit": 100}

    def refresh(status=""):
        if state["data"]:
            scan(state["data"]["folder"], include_files=state["files_open"], status=status)
        else:
            page.notice(status)

    def parent():
        if state["data"] and state["data"]["parent"]:
            scan(state["data"]["parent"])

    def root_drive():
        drive = PureWindowsPath(str(folder.Text).strip()).anchor
        if drive:
            scan(drive)
        else:
            page.notice(tr("Enter a drive or a full folder path.", "Укажи диск или полный путь к папке."))

    page.actions(
        (tr("Calculate sizes", "Посчитать размеры"), lambda: scan(_target(page, folder)), True),
        (tr("Up one level", "На уровень выше"), parent),
        (tr("Scan entire drive", "Посчитать весь диск"), root_drive),
        (tr("Undo last move", "Вернуть последний перенос"), _undo(page, "diskmap", refresh)),
    )
    summary = page.text("", muted=True)
    chart = Canvas()
    chart.Width = 152
    chart.Height = 152
    chart.HorizontalAlignment = HorizontalAlignment.Center
    chart.Visibility = Visibility.Collapsed
    page.add(chart)
    folders_box = page.rows(max_height=220)
    folders_box.Visibility = Visibility.Collapsed

    def activate(item):
        if item["kind"] == "files":
            open_files()
        else:
            scan(item["path"])

    def open_selection():
        items = state["data"]["entries"] if state["data"] else []
        chosen = page.selected(folders_box, items)
        if chosen:
            activate(chosen[0])
        else:
            page.notice(tr("Select a row in the disk map.", "Выбери строку карты."))

    def open_folder():
        if state["data"]:
            _open(page, state["data"]["folder"])
        else:
            _open(page, _target(page, folder))

    page.actions(
        (tr("Open selected item", "Открыть выбранную строку"), open_selection),
        (tr("Files in this folder", "Файлы в этой папке"), lambda: open_files()),
        (tr("Show folder in File Explorer", "Показать папку в Проводнике"), open_folder),
    )

    file_summary = page.text("", muted=True)
    files_box = page.rows(max_height=240)
    files_box.Visibility = Visibility.Collapsed

    def render_files():
        visible = state["files"][:state["limit"]] if state["files_open"] else []
        count = len(state["files"])
        file_summary.Text = tr(f"Files in this folder · Showing {len(visible)} of {count}",
                               f"Файлы в этой папке · Показано {len(visible)} из {count}") if state["files_open"] else ""
        files_box.Visibility = Visibility.Visible if state["files_open"] else Visibility.Collapsed
        page.show_rows(files_box, visible, _file_line)
        if state["files_open"]:
            page.hub.animate(files_box, "sheet")

    def more_files():
        if state["files_open"] and state["limit"] < len(state["files"]):
            state["limit"] += 100
            render_files()

    def hide_files():
        state["files_open"] = False
        render_files()

    def open_files():
        if not state["data"]:
            page.notice(tr("Calculate the folder sizes first.", "Сначала посчитай размеры папки."))
            return
        body = {"folder": state["data"]["folder"]}

        def done(listing):
            state.update(files=listing["files"], files_open=True, limit=100)
            render_files()
            if warnings := _warnings(listing):
                page.notice(warnings)

        page.run(lambda: page.post("/api/diskmap/files", body), done, tr("Opening file list…", "Открываю список файлов…"))

    def selected_files():
        if not state["files_open"]:
            return []
        return page.selected(files_box, state["files"][:state["limit"]])

    def reveal_file():
        chosen = selected_files()
        _open(page, chosen[0]["path"] if chosen else "")

    def scan(path, include_files=False, status=""):
        if not path:
            return

        def work():
            data = page.post("/api/diskmap/scan", {"folder": path})
            listing = page.post("/api/diskmap/files", {"folder": data["folder"]}) if include_files else {}
            return data, listing

        def done(result):
            data, listing = result
            state.update(data=data, files=listing.get("files", []), files_open=include_files, limit=100)
            folder.Text = data["folder"]
            counts = tr(f"{data['dirs']} folders · {data['files']} files",
                        f"Папок: {data['dirs']} · Файлов: {data['files']}")
            summary.Text = f"{data['folder']}\n{_size(data['total'])} · {counts}"

            def line(item):
                ratio = item["size"] / data["total"] if data["total"] else 0
                count = tr(f"{item['count']} files", f"Файлов: {item['count']}")
                return f"{item['name']}  ·  {_size(item['size'])}  ·  {ratio:.1%}  ·  {count}"

            _disk_chart(chart, data["entries"], activate)
            if chart.Visibility == Visibility.Visible:
                page.hub.animate(chart, "chart")
            folders_box.SelectedIndex = -1
            files_box.SelectedIndex = -1
            page.show_rows(folders_box, data["entries"], line)
            folders_box.Visibility = Visibility.Visible
            if not data["entries"]:
                folders_box.Items.Add(tr("This folder is empty.", "В этой папке ничего нет."))
            page.hub.animate(folders_box, "sheet")
            render_files()
            notice = "\n".join(filter(None, (status, _warnings(data), _warnings(listing))))
            if notice:
                page.notice(notice)

        page.run(work, done, tr("Calculating sizes…", "Считаю размеры…"))

    def on_enter(event, action):
        if event.Key == Key.Enter:
            event.Handled = True
            action()

    folders_box.MouseDoubleClick += lambda *_: open_selection()
    folders_box.KeyDown += lambda sender, event: on_enter(event, open_selection)
    files_box.MouseDoubleClick += lambda *_: reveal_file()
    page.actions(
        (tr("Show more files", "Показать ещё файлы"), more_files),
        (tr("Hide file list", "Скрыть файлы"), hide_files),
        (tr("Show file in File Explorer", "Показать файл в Проводнике"), reveal_file),
    )
    page.actions(
        (tr("Move file to Hub Trash", "Файл в корзину Хаба"), lambda: _remove(page, "diskmap", selected_files(), "trash", refresh)),
        (tr("Delete file permanently", "Удалить файл навсегда"), lambda: _remove(page, "diskmap", selected_files(), "delete", refresh)),
    )


def _cleanup(page):
    folder = page.folder(tr("Folder to clean up", "Папка для уборки"), page.default_folder)
    periods = (90, 180, 365, 730)
    age = page.choice(tr("Files older than", "Файлы старше"), [tr("3 months", "3 месяцев"), tr("6 months", "6 месяцев"), tr("1 year", "1 года"), tr("2 years", "2 лет")], 2)
    junk = page.check(tr("Find junk and temporary files", "Искать мусор и временные файлы"), True)
    state = {"data": {}, "request": None, "items": [], "limit": 500}

    def refresh(status=""):
        if state["request"]:
            scan(state["request"], status)
        else:
            page.notice(status)

    page.actions(
        (tr("Scan for cleanup candidates", "Найти кандидатов на уборку"), lambda: scan({
            "folder": _target(page, folder), "age_days": periods[age.SelectedIndex],
            "include_junk": bool(junk.IsChecked),
        }), True),
        (tr("Undo last cleanup", "Вернуть последнюю уборку"), _undo(page, "cleanup", refresh)),
    )
    summary = page.text("", muted=True)
    groups = ("old", "junk", "empty")
    category = page.choice(tr("Show", "Показать"), [tr("Old files", "Старые файлы"), tr("Junk and cache", "Мусор и кэш"), tr("Empty folders", "Пустые папки")])
    count = page.text("", muted=True)
    box = page.rows(multiple=True)
    pick = _Selection(page, box, _file_line)

    def filter_rows(*_):
        group = groups[category.SelectedIndex]
        items = state["data"].get(group, [])
        pick.show(items[:state["limit"]])
        count.Text = tr(f"Showing {len(pick.visible)} of {len(items)}.", f"Показано {len(pick.visible)} из {len(items)}.") if state["data"] else ""

    def new_category(*_):
        state["limit"] = 500
        filter_rows()

    def scan(body, status=""):
        if not body["folder"]:
            return

        def done(data):
            state.update(data=data, items=[item for group in groups for item in data[group]])
            state["request"] = {**body, "folder": data["folder"]}
            folder.Text = data["folder"]
            summary.Text = (
                tr(
                    f"Old files: {_size(data['old_size'])} · Junk: {_size(data['junk_size'])} · Empty folders: {len(data['empty'])} · Checked: {data['scanned']}",
                    f"Старые файлы: {_size(data['old_size'])} · Мусор: {_size(data['junk_size'])} · Пустые папки: {len(data['empty'])} · Проверено: {data['scanned']}",
                )
            )
            pick.select([])
            new_category()
            notice = "\n".join(filter(None, (status, _warnings(data))))
            if notice:
                page.notice(notice)

        page.run(lambda: page.post("/api/cleanup/scan", body), done, tr("Looking for items to clean up…", "Ищу, что можно убрать…"))

    def more():
        state["limit"] += 500
        filter_rows()

    def mark_visible():
        pick.extend(pick.visible)

    def remove(mode):
        items = pick.picked(state["items"])
        path = state["request"]["folder"] if state["request"] else ""
        _remove(page, "cleanup", items, mode, refresh, path)

    category.SelectionChanged += new_category
    page.actions(
        (tr("Select visible", "Выбрать видимые"), mark_visible),
        (tr("Clear selection", "Снять отметки"), lambda: pick.select([])),
        (tr("Show more", "Показать ещё"), more),
    )
    page.actions(
        (tr("Move selected to Hub Trash", "Выбранное в корзину Хаба"), lambda: remove("trash"), True),
        (tr("Delete selected permanently", "Удалить выбранное навсегда"), lambda: remove("delete")),
    )
    suffixes = page.field(tr("Junk file extensions, separated by commas", "Расширения мусора через запятую"))
    names = page.field(tr("Junk filenames, separated by commas", "Имена мусорных файлов через запятую"))
    rules_loaded = False

    def show_rules(data):
        nonlocal rules_loaded
        suffixes.Text = ", ".join(data["suffixes"])
        names.Text = ", ".join(data["names"])
        rules_loaded = True

    def load_rules():
        page.run(lambda: page.get("/api/cleanup/rules"), show_rules, tr("Loading junk rules…", "Загружаю правила мусора…"))

    def save_rules(reset=False):
        if reset and not page.confirm(tr("Restore the default rules?", "Вернуть правила по умолчанию?"), tr(
            "Your filenames and extensions will be replaced.",
            "Твои имена и расширения будут заменены.",
        )):
            return
        if not reset and not rules_loaded:
            page.notice(tr("Load the current rules first.", "Сначала загрузи текущие правила."))
            return
        rules = {"suffixes": _csv(str(suffixes.Text)), "names": _csv(str(names.Text))}
        body = {"reset": True} if reset else {"rules": rules}

        def done(data):
            show_rules(data)
            refresh(tr("Cleanup rules saved.", "Правила уборки сохранены."))

        page.run(lambda: page.post("/api/cleanup/rules", body), done, tr("Saving junk rules…", "Сохраняю правила мусора…"))

    page.actions(
        (tr("Load junk rules", "Загрузить правила мусора"), load_rules),
        (tr("Save junk rules", "Сохранить правила мусора"), save_rules),
        (tr("Defaults", "По умолчанию"), lambda: save_rules(True)),
    )


def mount(page, tool_id):
    {
        "sorter": _sorter,
        "dupes": _duplicates,
        "bigfiles": _bigfiles,
        "diskmap": _diskmap,
        "cleanup": _cleanup,
    }[tool_id](page)
