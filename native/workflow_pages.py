"""Переименование, сравнение папок, изображения, хэши и пароли."""

from base64 import b64encode
from contextlib import contextmanager
from datetime import datetime
from io import BytesIO
import ntpath
from pathlib import Path, PureWindowsPath
import re

from Microsoft.Win32 import OpenFileDialog
from System import Array, Byte, TimeSpan
from System.IO import MemoryStream
from System.Windows import Clipboard, DataFormats, DragDropEffects, HorizontalAlignment, Thickness, Visibility
from System.Windows.Automation import AutomationProperties
from System.Windows.Controls import Image, ProgressBar, Slider, StackPanel, TextBox
from System.Windows.Input import Key, Keyboard, ModifierKeys
from System.Windows.Media import Stretch
from System.Windows.Media.Imaging import BitmapCacheOption, BitmapImage, BitmapFrame, PngBitmapEncoder
from System.Windows.Threading import DispatcherTimer

from tools import checksum, images as image_tools
from tools.i18n import tr

from .widgets import label, make


@contextmanager
def _group(page):
    parent = page.panel
    panel = page.add(StackPanel())
    page.panel = panel
    try:
        yield panel
    finally:
        page.panel = parent


def _switch(page, choice, panels):
    def update(*_):
        for index, panel in enumerate(panels):
            visibility = Visibility.Visible if choice.SelectedIndex == index else Visibility.Collapsed
            if panel.Visibility != visibility:
                panel.Visibility = visibility
                if visibility == Visibility.Visible:
                    page.hub.animate(panel)

    choice.SelectionChanged += update
    update()


def _debounce(page, callback, milliseconds=220):
    timer = make(DispatcherTimer, Interval=TimeSpan.FromMilliseconds(milliseconds))

    def tick(*_):
        timer.Stop()
        callback()

    def schedule(*_):
        timer.Stop()
        timer.Start()

    timer.Tick += tick
    page.on_leave(timer.Stop)
    return schedule


def _slider(page, label, low, high, initial, suffix=""):
    caption = page.text(f"{label} · {initial}{suffix}")
    control = make(Slider, Minimum=low, Maximum=high, Value=initial, TickFrequency=1,
                   IsSnapToTickEnabled=True, Margin=Thickness(0, 0, 0, 8))
    AutomationProperties.SetName(control, label)

    def update(*_):
        caption.Text = f"{label} · {int(control.Value)}{suffix}"

    control.ValueChanged += update
    return page.add(control)


def _size(value):
    units = tr(("B", "KB", "MB", "GB", "TB"), ("Б", "КБ", "МБ", "ГБ", "ТБ"))
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", tr(".", ",")) + f" {unit}"
        value /= 1024


def _file_drop(target, receive):
    def over(_sender, event):
        event.Effects = (DragDropEffects.Copy if event.Data.GetDataPresent(DataFormats.FileDrop)
                         else getattr(DragDropEffects, "None"))
        event.Handled = True

    def drop(_sender, event):
        if event.Data.GetDataPresent(DataFormats.FileDrop):
            paths = event.Data.GetData(DataFormats.FileDrop)
            if paths:
                receive(list(paths))
            event.Handled = True

    target.AllowDrop = True
    target.PreviewDragOver += over
    target.PreviewDrop += drop


def _invalid_windows_name(name):
    if not name or name.endswith((".", " ")) or re.search(r'[<>:"/\\|?*\x00-\x1f]', name):
        return True
    return ntpath.isreserved(name) if hasattr(ntpath, "isreserved") else PureWindowsPath(name).is_reserved()


def _renamer(page):
    folder = page.folder(tr("Folder containing files", "Папка с файлами"), page.default_folder)
    pattern = page.field(tr("File patterns, separated by commas", "Маски файлов через запятую"), "*")
    modes = ("replace", "number", "affix", "case", "translit", "date")
    mode = page.choice(tr("Rename rule", "Правило переименования"), (
        tr("Replace text", "Замена текста"),
        tr("Numbering", "Нумерация"),
        tr("Prefix and suffix", "Префикс и суффикс"),
        tr("Letter case", "Регистр букв"),
        tr("Transliterate", "Транслитерация"),
        tr("Add date", "Добавить дату"),
    ))
    with _group(page) as replace_panel:
        find = page.field(tr("Find text", "Что найти"))
        replacement = page.field(tr("Replace with", "На что заменить"))
        regex = page.check(tr("Regular expression", "Регулярное выражение"))
        case_sensitive = page.check(tr("Match case", "Учитывать регистр"))
    with _group(page) as number_panel:
        number_prefix = page.field(tr("Prefix", "Префикс"))
        start = page.field(tr("Starting number", "Начальный номер"), "1")
        digits = page.field(tr("Number of digits", "Количество цифр"), "2")
        step = page.field(tr("Numbering step", "Шаг нумерации"), "1")
        keep = page.check(tr("Keep the original name", "Сохранять исходное имя"))
    with _group(page) as affix_panel:
        prefix = page.field(tr("Prefix", "Префикс"))
        suffix = page.field(tr("Suffix", "Суффикс"))
    with _group(page) as case_panel:
        target = page.choice(tr("Case", "Регистр"), (
            tr("lowercase", "строчные"),
            tr("UPPERCASE", "ЗАГЛАВНЫЕ"),
            tr("Sentence case", "Как в предложении"),
            tr("Title Case", "Каждое Слово С Заглавной"),
        ))
    with _group(page) as translit_panel:
        page.text(tr("For example, “документ.pdf” becomes “dokument.pdf”.", "Например, «документ.pdf» станет «dokument.pdf»."), muted=True)
    with _group(page) as date_panel:
        date_format = page.choice(tr("File modification date format", "Формат даты изменения файла"), (
            tr("YYYY-MM-DD", "ГГГГ-ММ-ДД"), tr("YYYY-MM-DD_HH-MM", "ГГГГ-ММ-ДД_ЧЧ-ММ"),
        ))
        position = page.choice(tr("Date position", "Где добавить дату"), (
            tr("Start of filename", "В начале имени"), tr("End of filename", "В конце имени"),
        ))
    _switch(page, mode, (replace_panel, number_panel, affix_panel, case_panel, translit_panel, date_panel))

    source = None
    files = []
    preview_result = None
    revision = 0

    def scope():
        return folder.Text.strip(), pattern.Text.strip() or "*"

    def config():
        name = modes[mode.SelectedIndex]
        rule = {"mode": name}
        if name == "replace":
            rule.update(find=find.Text, replace=replacement.Text, use_regex=bool(regex.IsChecked),
                        case_sensitive=bool(case_sensitive.IsChecked))
        elif name == "number":
            try:
                first, width, stride = int(start.Text), int(digits.Text), int(step.Text)
            except ValueError as error:
                raise ValueError(tr(
                    "Starting number, digit count and step must be integers.",
                    "Начальный номер, количество цифр и шаг должны быть целыми числами.",
                )) from error
            if first < 0 or not 1 <= width <= 8 or stride < 1:
                raise ValueError(tr(
                    "Use a starting number of 0 or more, 1–8 digits, and a step of at least 1.",
                    "Номер — от 0, количество цифр — от 1 до 8, шаг — от 1.",
                ))
            rule.update(prefix=number_prefix.Text, start=first, digits=width, step=stride, keep_name=bool(keep.IsChecked))
        elif name == "affix":
            rule.update(prefix=prefix.Text, suffix=suffix.Text)
        elif name == "case":
            rule["target"] = ("lower", "upper", "sentence", "title")[target.SelectedIndex]
        elif name == "date":
            rule["format"] = ("YYYY-MM-DD", "YYYY-MM-DD_HH-mm")[date_format.SelectedIndex]
            rule["position"] = ("prefix", "suffix")[position.SelectedIndex]
        return rule

    def invalidate(caption, clear=False):
        nonlocal revision, preview_result
        revision += 1
        preview_result = None
        apply_button.IsEnabled = False
        stats.Text = caption
        if clear:
            page.show_rows(rows, [], str)

    def display(data):
        nonlocal preview_result
        items = data["preview"]
        for item in items:
            if item["status"] == "ok" and _invalid_windows_name(item["new_name"]):
                item.update(status="error", error=tr("Invalid Windows filename", "Недопустимое имя файла в Windows"))
        states = {
            "ok": tr("Ready", "Готово"),
            "unchanged": tr("Unchanged", "Без изменений"),
            "conflict": tr("Conflict", "Конфликт"),
            "error": tr("Error", "Ошибка"),
        }
        ready = sum(item["status"] == "ok" for item in items)
        errors = sum(item["status"] == "error" for item in items)
        stats.Text = tr(
            f"Total: {data['total']} · Ready: {ready} · Unchanged: {data['unchanged_count']} "
            f"· Conflicts: {data['conflict_count']} · Errors: {errors}",
            f"Всего {data['total']} · готово {ready} · без изменений {data['unchanged_count']} "
            f"· конфликтов {data['conflict_count']} · ошибок {errors}",
        )

        def describe(item):
            detail = states[item["status"]]
            if item.get("error"):
                detail += f" · {item['error']}"
            return f"{item['old_name']} → {item['new_name']}  ·  {detail}"

        page.show_rows(rows, items, describe)
        if ready and not (errors or data["conflict_count"]):
            preview_result = data, ready
            apply_button.IsEnabled = True

    def preview():
        if source != scope() or not files:
            return
        try:
            rule = config()
        except ValueError as error:
            invalidate(str(error), clear=True)
            return
        request = {"folder": source[0], "files": files, "rule": rule}
        version = revision

        def publish(data):
            if version == revision:
                display(data)

        page.run(lambda: page.post("/api/renamer/preview", request), publish, message="")

    schedule = _debounce(page, preview)

    def rule_changed(*_):
        if source == scope() and files:
            invalidate(tr("Refreshing preview…", "Обновляю предпросмотр…"))
            schedule()

    def scope_changed(*_):
        nonlocal source
        source = None
        invalidate(tr("Find files in the selected folder.", "Найди файлы в выбранной папке."), clear=True)

    def scan(status=""):
        nonlocal source
        if page.busy:
            return
        requested = scope()
        if not requested[0]:
            page.notice(tr("Choose a folder containing files.", "Выбери папку с файлами."))
            return
        source = None
        invalidate(tr("Looking for files…", "Ищу файлы…"), clear=True)
        version = revision

        def scanned(data):
            nonlocal source, files
            if version != revision or requested != scope():
                return
            source, files = requested, data["files"]
            stats.Text = tr("Preparing preview…", "Готовлю предпросмотр…") if files else tr("No matching files.", "Подходящих файлов нет.")
            if status:
                page.notice(status)
            preview()

        page.run(lambda: page.post("/api/renamer/scan", {"folder": requested[0], "filter": requested[1]}),
                 scanned, message=tr("Looking for files…", "Ищу файлы…"))

    def mutated(data, count, message):
        status = f"{message} {data[count]}."
        if data["errors"]:
            status += "\n" + "\n".join(data["errors"])
        if scope()[0]:
            scan(status)
        else:
            page.notice(status)

    def apply():
        if page.busy or preview_result is None or scope() != source:
            return
        data, ready = preview_result
        request = {"folder": data["folder"], "renames": data["preview"]}
        if not page.confirm(tr("Rename the files?", "Переименовать файлы?"), tr(
            f"Files to rename: {ready}\n{data['folder']}",
            f"Будет переименовано {ready} шт. в папке\n{data['folder']}",
        )):
            return
        scope_changed()
        page.run(lambda: page.post("/api/renamer/apply", request),
                 lambda done: mutated(done, "renamed_count", tr("Files renamed", "Переименовано файлов")), message=tr(
                     "Renaming files…",
                     "Переименовываю файлы…",
                 ))

    def undo():
        def choose(data):
            item = data["last_run"]
            if item is None:
                page.notice(tr("Rename history is empty.", "История переименований пуста."))
                return
            if page.confirm(tr("Restore the original names?", "Вернуть исходные имена?"), tr(
                f"Last rename: {item['count']} files\n{item['folder']}",
                f"Последнее переименование: {item['count']} шт.\n{item['folder']}",
            )):
                scope_changed()
                page.run(lambda: page.post("/api/renamer/undo", {"run_id": item["run_id"]}),
                         lambda done: mutated(done, "restored_count", tr("Names restored", "Восстановлено имён")), message=tr(
                             "Restoring names…",
                             "Возвращаю имена…",
                         ))

        page.run(lambda: page.get("/api/renamer/last-run"), choose)

    _, apply_button, _ = page.actions((tr("Find files", "Найти файлы"), scan, True),
                                      (tr("Rename files", "Переименовать файлы"), apply), (tr("Undo last rename", "Отменить последнее"), undo))
    stats = page.text(tr("Find files in the selected folder.", "Найди файлы в выбранной папке."), muted=True)
    rows = page.rows(max_height=360)
    apply_button.IsEnabled = False
    folder.TextChanged += scope_changed
    pattern.TextChanged += scope_changed
    for field in (find, replacement, number_prefix, start, digits, step, prefix, suffix):
        field.TextChanged += rule_changed
    for check in (regex, case_sensitive, keep):
        check.Checked += rule_changed
        check.Unchecked += rule_changed
    for choice in (mode, target, date_format, position):
        choice.SelectionChanged += rule_changed


def _compare(page):
    left = page.folder(tr("First folder", "Первая папка"), page.default_folder)
    right = page.folder(tr("Second folder", "Вторая папка"))
    deep = page.check(tr("Compare file contents", "Сравнивать содержимое файлов"))
    page.text(tr(
        "Quick comparison checks size and type. Content comparison finds changes in files of the same size.",
        "Быстрое сравнение проверяет размер и тип. Проверка содержимого находит изменения одинакового размера.",
    ), muted=True)
    data = None
    shown = []
    copied = set()
    categories = ("added", "removed", "changed")
    titles = {
        "added": tr("Only in the second folder", "Только во второй"),
        "removed": tr("Only in the first folder", "Только в первой"),
        "changed": tr("Changed", "Изменилось"),
    }

    def inputs():
        return left.Text.strip(), right.Text.strip(), bool(deep.IsChecked)

    def describe(item):
        category = item["category"]
        reason = item.get("reason")
        if reason == "size":
            detail = f"{_size(item['left_size'])} → {_size(item['right_size'])}"
        elif reason:
            detail = {
                "type": tr("file and folder", "файл и папка"),
                "content": tr("different contents", "разное содержимое"),
                "unreadable": tr("could not read", "не удалось прочитать"),
            }[reason]
        else:
            detail = tr("folder", "папка") if item["kind"] == "dir" else _size(item["size"])
        marker = tr("  ·  Copied", "  ·  Скопировано") if (category, item["path"]) in copied else ""
        return f"{titles[category]}  ·  {item['path']}  ·  {detail}{marker}"

    def selection(*_):
        selected = page.selected(rows, shown)
        item = selected[0] if selected else None
        enabled = bool(item and item["category"] != "changed" and (item["category"], item["path"]) not in copied)
        copy_button.IsEnabled = enabled
        title = (
            tr("Copy to first folder", "Скопировать в первую") if enabled and item["category"] == "added" else
            tr("Copy to second folder", "Скопировать во вторую") if enabled else tr("Copy selected", "Скопировать выбранное")
        )
        copy_button.Content = label(title)
        copy_button.ToolTip = title
        AutomationProperties.SetName(copy_button, title)

    def render(*_):
        nonlocal shown
        active = categories[view.SelectedIndex - 1:view.SelectedIndex] if view.SelectedIndex > 0 else categories
        available = [dict(item, category=key) for key in active for item in data[key]] if data else []
        shown = available[:500]
        page.show_rows(rows, shown, describe)
        selection()
        if data is None:
            return
        counts = data["counts"]
        summary.Text = (" · ".join(f"{titles[key]} {counts[key]}" for key in categories)
                        + tr(f" · {counts['same']} matching", f" · совпадает {counts['same']}"))
        expected = sum(counts[key] for key in active)
        method = tr("Compared contents", "Проверено содержимое") if data["deep"] else tr("Compared size and type", "Проверены размер и тип")
        detail = tr(f"{method} · {data['seconds']:g} s", f"{method} · {data['seconds']:g} с")
        if len(shown) < expected:
            detail += tr(f" · Showing {len(shown)} of {expected}", f" · показано {len(shown)} из {expected}")
        if not expected:
            detail += tr(" · No differences in this list", " · отличий в этом списке нет")
        if data["errors"]:
            detail += tr(f" · Access errors: {len(data['errors'])}", f" · ошибок доступа {len(data['errors'])}")
        if data["truncated"]:
            detail += tr(" · Some files were excluded", " · часть файлов не вошла в сравнение")
        note.Text = detail

    def clear(*_):
        nonlocal data
        data = None
        copied.clear()
        summary.Text = tr("Choose two folders to compare.", "Выбери две папки для сравнения.")
        note.Text = ""
        render()

    def compare():
        one, two, contents = inputs()
        if not one or not two:
            page.notice(tr("Enter both folders.", "Укажи обе папки."))
            return
        if page.busy:
            return
        clear()

        def finished(result):
            nonlocal data
            if (one, two, contents) == inputs():
                data = result
                view.SelectedIndex = 0
                render()

        page.run(lambda: page.post("/api/compare/run", {"left": one, "right": two, "deep": contents}),
                 finished, message=tr("Comparing folders…", "Сравниваю папки…"))

    def copy():
        selected = page.selected(rows, shown)
        if not copy_button.IsEnabled or not data or not selected or page.busy:
            return
        item = selected[0]
        category, rel = item["category"], item["path"]
        origin, destination = ("right", "left") if category == "added" else ("left", "right")
        request = {"source": data[origin], "target": data[destination], "path": rel}
        snapshot = data
        target_path = Path(request["target"]) / rel
        if not page.confirm(tr("Copy the selected items?", "Скопировать выбранное?"), tr(
            f"{rel}\n\nDestination folder\n{request['target']}",
            f"{rel}\n\nПапка назначения\n{request['target']}",
        )):
            return

        def work():
            if target_path.exists() or target_path.is_symlink():
                raise ValueError(tr(
                    "An item with the same name already exists in the destination. Run the comparison again.",
                    "В папке назначения уже есть такой файл или папка. Повтори сравнение.",
                ))
            return page.post("/api/compare/sync", request)

        def finish(_result):
            if data is snapshot:
                copied.add((category, rel))
                render()
            page.notice(tr(f"Copied to {request['target']}", f"Скопировано в {request['target']}"))

        page.run(work, finish, message=tr("Copying…", "Копирую…"))

    page.actions((tr("Compare", "Сравнить"), compare, True))
    summary = page.text(tr("Choose two folders to compare.", "Выбери две папки для сравнения."), muted=True)
    view = page.choice(tr("Show", "Показать"), (tr("All differences", "Все отличия"), *(titles[key] for key in categories)))
    rows = page.rows(max_height=430)
    note = page.text("", muted=True)
    copy_button, = page.actions((tr("Copy selected", "Скопировать выбранное"), copy))
    copy_button.IsEnabled = False
    view.SelectionChanged += render
    rows.SelectionChanged += selection
    left.TextChanged += clear
    right.TextChanged += clear

    def rules_changed(*_):
        had_result = data is not None
        clear()
        if had_result:
            compare()

    deep.Checked += rules_changed
    deep.Unchecked += rules_changed


_IMAGE_INPUTS = ("PNG", "JPEG", "WEBP", "GIF", "BMP")
_IMAGE_OUTPUTS = (("WEBP", "webp"), ("JPEG", "jpg"), ("PNG", "png"))


def _process_image(name, source, format_name, ext, quality, max_dimension):
    from PIL import Image as PillowImage, ImageOps

    original_size = source.stat().st_size if isinstance(source, Path) else len(source)
    with PillowImage.open(source if isinstance(source, Path) else BytesIO(source), formats=_IMAGE_INPUTS) as opened:
        with ImageOps.exif_transpose(opened) as oriented:
            original_dimensions = oriented.size
            with oriented.convert("RGBA") as converted:
                if max_dimension:
                    converted.thumbnail((max_dimension, max_dimension), PillowImage.Resampling.LANCZOS)
                with BytesIO() as output:
                    if format_name == "JPEG":
                        with PillowImage.new("RGB", converted.size) as opaque:
                            opaque.paste(converted, mask=converted.getchannel("A"))
                            opaque.save(output, format_name, quality=quality, optimize=True)
                    else:
                        options = {"quality": quality} if format_name == "WEBP" else {"optimize": True}
                        converted.save(output, format_name, **options)
                    encoded = output.getvalue()
                dimensions = converted.size

    # Preview the encoded result, including any compression artifacts.
    with PillowImage.open(BytesIO(encoded)) as result:
        result.thumbnail((320, 220), PillowImage.Resampling.LANCZOS)
        with BytesIO() as preview:
            result.save(preview, "PNG")
            thumbnail = preview.getvalue()
    return {
        "name": f"{Path(name).stem}.{ext}",
        "original_size": original_size,
        "original_dimensions": original_dimensions,
        "dimensions": dimensions,
        "data": encoded,
        "thumbnail": thumbnail,
    }


def _bitmap(data):
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


def _clipboard_image():
    bitmap = Clipboard.GetImage()
    if bitmap is None:
        return None
    encoder = PngBitmapEncoder()
    encoder.Frames.Add(BitmapFrame.Create(bitmap))
    stream = MemoryStream()
    try:
        encoder.Save(stream)
        return bytes(stream.ToArray())
    finally:
        stream.Dispose()


def _images(page):
    output = page.choice(tr("Output format", "Формат результата"), ("WebP", "JPEG", "PNG"))
    with _group(page) as quality_group:
        quality = _slider(page, tr("Quality", "Качество"), 10, 100, 80, "%")
    resize = page.choice(tr("Longest side", "Максимальная сторона"), (tr("Original size", "Исходный размер"), tr("1920 px", "1920 пкс"), tr(
        "1280 px",
        "1280 пкс",
    ), tr(
        "800 px",
        "800 пкс",
    ), tr(
        "400 px",
        "400 пкс",
    )))
    items = []

    def select(*_):
        picked = page.selected(rows, items)
        save_button.IsEnabled = remove_button.IsEnabled = bool(picked)
        picture.Visibility = Visibility.Visible if picked else Visibility.Collapsed
        picture.Source = _bitmap(picked[0]["thumbnail"]) if picked else None
        AutomationProperties.SetName(picture, picked[0]["name"] if picked else tr("Preview", "Предпросмотр"))

    def describe(item):
        old_width, old_height = item["original_dimensions"]
        width, height = item["dimensions"]
        return (f"{item['name']}  ·  {old_width}×{old_height} → {width}×{height}"
                f"  ·  {_size(item['original_size'])} → {_size(len(item['data']))}")

    def render():
        page.show_rows(rows, items, describe)
        if items and rows.SelectedIndex < 0:
            rows.SelectedIndex = 0
        select()
        all_button.IsEnabled = clear_button.IsEnabled = bool(items)
        if not items:
            totals.Text = tr("Add images to process.", "Добавь изображения для обработки.")
            return
        old_size = sum(item["original_size"] for item in items)
        new_size = sum(len(item["data"]) for item in items)
        change = f" ({(new_size / old_size - 1):+.0%})" if old_size and new_size != old_size else ""
        totals.Text = tr(
            f"Processed: {len(items)} · {_size(old_size)} → {_size(new_size)}{change}",
            f"Обработано {len(items)} · {_size(old_size)} → {_size(new_size)}{change}",
        )

    def process(batch):
        if not batch or page.busy:
            return
        format_name, ext = _IMAGE_OUTPUTS[output.SelectedIndex]
        settings = format_name, ext, int(quality.Value), (0, 1920, 1280, 800, 400)[resize.SelectedIndex]

        def work():
            produced, failures = [], []
            for name, source in batch:
                try:
                    produced.append(_process_image(name, source, *settings))
                except (OSError, ValueError, OverflowError) as error:
                    failures.append(f"{name} · {error}")
            return produced, failures

        def finish(result):
            produced, failures = result
            items[0:0] = produced
            render()
            if failures:
                page.notice(tr("Could not process:\n", "Не удалось обработать:\n") + "\n".join(failures))

        page.run(work, finish, message=tr("Processing images…", "Обрабатываю изображения…"))

    def receive(paths):
        sources = [Path(path) for path in paths]
        process([(path.name, path) for path in sources])

    def browse():
        if page.busy:
            return
        dialog = make(
            OpenFileDialog, Title=tr("Choose images", "Выбери изображения"), Multiselect=True,
            Filter=tr(
                "Images (*.png;*.jpg;*.jpeg;*.webp;*.gif;*.bmp)|*.png;*.jpg;*.jpeg;*.webp;*.gif;*.bmp",
                "Изображения (*.png;*.jpg;*.jpeg;*.webp;*.gif;*.bmp)|*.png;*.jpg;*.jpeg;*.webp;*.gif;*.bmp",
            ),
        )
        if dialog.ShowDialog(page.window):
            receive(dialog.FileNames)

    def paste():
        if page.busy:
            return False
        try:
            if Clipboard.ContainsFileDropList():
                receive(Clipboard.GetFileDropList())
                return True
            data = _clipboard_image() if Clipboard.ContainsImage() else None
        except Exception:
            page.notice(tr("Could not read the clipboard. Try again.", "Не удалось прочитать буфер обмена. Попробуй ещё раз."))
            return True
        if data is None:
            return False
        process([(tr("clipboard.png", "из буфера.png"), data)])
        return True

    def paste_click():
        if not page.busy and not paste():
            page.notice(tr("There are no images or files on the clipboard.", "В буфере обмена нет изображения или файлов."))

    def paste_key(_sender, event):
        if (event.Key == Key.V and Keyboard.Modifiers == ModifierKeys.Control
                and not isinstance(event.OriginalSource, TextBox) and paste()):
            event.Handled = True

    def remove(all_items=False):
        if page.busy:
            return
        selected = items if all_items else page.selected(rows, items)
        removed = {id(item) for item in selected}
        items[:] = [item for item in items if id(item) not in removed]
        render()

    def save(all_items=False):
        path = destination.Text.strip()
        selected = list(items) if all_items else page.selected(rows, items)
        if not path:
            page.notice(tr("Choose a destination folder.", "Укажи папку для сохранения."))
            return
        if not selected:
            return

        def work():
            saved, errors = [], []
            for item in selected:
                try:
                    encoded = b64encode(item["data"]).decode("ascii")
                    result = image_tools.save_image(path, item["name"], encoded)
                    saved.append(result["filename"])
                except image_tools.ImageError as error:
                    errors.append(f"{item['name']} · {error}")
            return saved, errors

        def finish(result):
            saved, errors = result
            message = tr(f"Saved to {path} · {len(saved)} files", f"Сохранено в {path} · {len(saved)} шт.")
            if len(saved) == 1:
                message = tr(f"Saved: {saved[0]}", f"Сохранено: {saved[0]}")
            if errors:
                message += "\n" + "\n".join(errors)
            page.notice(message)

        page.run(work, finish, message=tr("Saving images…", "Сохраняю изображения…"))

    def update_quality(*_):
        quality_group.Visibility = Visibility.Collapsed if output.SelectedIndex == 2 else Visibility.Visible

    page.text(tr(
        "Drop PNG, JPEG, WebP, GIF or BMP images here. You can also paste with Ctrl+V.",
        "Перетащи сюда изображения PNG, JPEG, WebP, GIF или BMP. Поддерживается вставка Ctrl+V.",
    ), muted=True)
    page.actions((tr("Choose images…", "Выбрать изображения…"), browse, True), (tr("Paste from clipboard", "Вставить из буфера"), paste_click))
    totals = page.text(tr("Add images to process.", "Добавь изображения для обработки."), muted=True)
    rows = page.rows(max_height=260, multiple=True)
    picture = make(Image, MaxWidth=320, MaxHeight=220, Stretch=Stretch.Uniform,
                   HorizontalAlignment=HorizontalAlignment.Left, Margin=Thickness(0, 0, 0, 10),
                   Visibility=Visibility.Collapsed)
    page.add(picture)
    destination = page.folder(tr("Destination folder", "Папка для сохранения"), page.default_folder)
    save_button, all_button, remove_button, clear_button = page.actions(
        (tr("Save selected", "Сохранить выбранные"), save, True), (tr("Save all", "Сохранить все"), lambda: save(True)),
        (tr("Remove selected", "Убрать выбранные"), remove), (tr("Clear list", "Очистить список"), lambda: remove(True)),
    )
    rows.SelectionChanged += select
    output.SelectionChanged += update_quality
    page.panel.PreviewKeyDown += paste_key
    _file_drop(page.panel, receive)
    render()


def _hash_fields(page, fields):
    controls = {}
    for key, title in fields:
        entry = page.field(title)
        entry.IsReadOnly = True
        controls[key] = entry

    def fill(values):
        for key, field in controls.items():
            field.Text = values.get(key, "")

    def copy(key):
        value = controls[key].Text
        if value:
            page.copy(value)

    page.actions(*((tr(f"Copy {title}", f"Копировать {title}"), lambda key=key: copy(key)) for key, title in fields))
    return fill


def _checksum(page):
    mode = page.choice(tr("Tool", "Инструмент"), (tr("File hashes", "Хэши файла"), tr("Text hashes and Base64", "Хэши текста и Base64"), tr(
        "Password generator",
        "Генератор паролей",
    )))
    with _group(page) as file_group:
        path = page.file(tr("File to verify", "Файл для проверки"))
        page.text(tr("You can drag a file from File Explorer.", "Можно перетащить файл из проводника."), muted=True)
        page.actions((tr("Calculate hashes", "Рассчитать хэши"), lambda: calculate(), True))
        file_meta = page.text("", muted=True)
        expected = page.field(tr("Expected hash", "Эталонный хэш"))
        verdict = page.text("")
        fill_file = _hash_fields(page, (("sha256", "SHA-256"), ("md5", "MD5"), ("sha1", "SHA-1"), ("sha512", "SHA-512")))
    with _group(page) as text_group:
        source = page.field(tr("Text", "Текст"), multiline=True)
        fill_text = _hash_fields(page, (("sha256", "SHA-256"), ("md5", "MD5"), ("base64_encode", "Base64")))
    with _group(page) as password_group:
        password = page.field(tr("Password", "Пароль"))
        password.IsReadOnly = True
        strength = page.text("", muted=True)
        meter = page.add(make(ProgressBar, Minimum=0, Maximum=80, Height=6, Margin=Thickness(0, 0, 0, 10)))
        AutomationProperties.SetName(meter, tr("Password strength", "Стойкость пароля"))
        password_mode = page.choice(tr("Generation method", "Способ генерации"), (tr("Random characters", "Случайные символы"), tr(
            "Passphrase",
            "Фраза из слов",
        )))
        with _group(page) as random_panel:
            length = _slider(page, tr("Password length", "Длина пароля"), 8, 64, 16)
            checks = {
                "uppercase": page.check(tr("Uppercase letters A–Z", "Заглавные буквы A–Z"), True),
                "lowercase": page.check(tr("Lowercase letters a–z", "Строчные буквы a–z"), True),
                "digits": page.check(tr("Digits 0–9", "Цифры 0–9"), True),
                "symbols": page.check(tr("Special characters", "Спецсимволы"), True),
                "avoid_ambiguous": page.check(tr("Exclude similar characters: 1, l, I, 0, O", "Исключить похожие символы: 1, l, I, 0, O"), True),
            }
        with _group(page) as phrase_panel:
            words = _slider(page, tr("Number of words", "Количество слов"), 2, 10, 4)
        _switch(page, password_mode, (random_panel, phrase_panel))
        page.actions((tr("New password", "Новый пароль"), lambda: generate(), True),
                     (tr("Copy password", "Копировать пароль"), lambda: page.copy(password.Text)))
    _switch(page, mode, (file_group, text_group, password_group))
    file_hashes = {}
    algorithms = {"sha256": "SHA-256", "md5": "MD5", "sha1": "SHA-1", "sha512": "SHA-512"}

    def verify(*_):
        value = expected.Text.strip().casefold()
        if not value or not file_hashes:
            verdict.Text = ""
            return
        alg = next((algorithms[key] for key, digest in file_hashes.items() if digest.casefold() == value), "")
        verdict.Text = tr(f"Expected hash matches · {alg}", f"Эталонный хэш совпадает · {alg}") if alg else tr(
            "Expected hash does not match.",
            "Эталонный хэш не совпадает.",
        )

    def clear_file(*_):
        file_hashes.clear()
        file_meta.Text = ""
        fill_file({})
        verify()

    def calculate():
        requested = path.Text.strip()
        if not requested:
            page.notice(tr("Choose a file to verify.", "Выбери файл для проверки."))
            return
        if page.busy:
            return
        clear_file()

        def finish(result):
            if requested != path.Text.strip():
                return
            file_hashes.update(result["hashes"])
            file_meta.Text = f"{result['name']} · {_size(result['size'])} · {datetime.fromtimestamp(result['mtime']):%d.%m.%Y %H:%M}"
            fill_file(file_hashes)
            verify()

        page.run(lambda: page.post("/api/checksum/file", {"path": requested}), finish, message=tr("Reading file…", "Читаю файл…"))

    def dropped(paths):
        if paths and not page.busy:
            path.Text = paths[0]
            calculate()

    def text_hash():
        requested = source.Text
        if not requested:
            return

        def finish(result):
            if requested == source.Text:
                fill_text(result)

        page.run(lambda: checksum.compute_text_hash(requested), finish, message="")

    schedule = _debounce(page, text_hash)

    def text_changed(*_):
        fill_text({})
        schedule()

    def generate(*_):
        phrase = password_mode.SelectedIndex == 1
        config = {key: bool(box.IsChecked) for key, box in checks.items()}
        result = checksum.generate_password(
            length=int(length.Value), mode="passphrase" if phrase else "random", words_count=int(words.Value), **config,
        )
        password.Text = result["password"]
        strength.Text = tr(f"Estimated entropy · {result['entropy']:g} bits", f"Оценка энтропии · {result['entropy']:g} бит").replace(".", ",")
        meter.Value = min(80, result["entropy"])

    path.TextChanged += clear_file
    expected.TextChanged += verify
    source.TextChanged += text_changed
    password_mode.SelectionChanged += generate
    length.ValueChanged += generate
    words.ValueChanged += generate
    for box in checks.values():
        box.Checked += generate
        box.Unchecked += generate
    _file_drop(file_group, dropped)
    generate()


def mount(page, tool_id):
    {"renamer": _renamer, "compare": _compare, "images": _images, "checksum": _checksum}[tool_id](page)
