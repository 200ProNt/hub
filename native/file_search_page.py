"""File Search UI for the persistent local index."""

from datetime import datetime, timedelta

from System import TimeSpan
from System.Windows import Visibility
from System.Windows.Automation import AutomationProperties
from System.Windows.Controls import StackPanel
from System.Windows.Input import Key
from System.Windows.Threading import DispatcherTimer
from tools import file_index
from tools.i18n import tr


def mount(page):
    worker = file_index.indexer
    query = page.field(tr("File name or part of the path", "Имя файла или часть пути"))
    show_filters = page.check(tr("Show filters", "Показать фильтры"))
    filter_panel = page.add(StackPanel())
    filter_panel.Visibility = Visibility.Collapsed
    fields = (
        page.field(tr("Extension, e.g. pdf", "Расширение, например pdf")),
        page.field(tr("Minimum size, MiB", "Минимальный размер, МиБ")),
        page.field(tr("Maximum size, MiB", "Максимальный размер, МиБ")),
        page.field(tr("Modified since (YYYY-MM-DD)", "Изменён с (ГГГГ-ММ-ДД)")),
        page.field(tr("Modified through (YYYY-MM-DD)", "Изменён по (ГГГГ-ММ-ДД)")),
    )
    kinds = ("", *file_index.FILE_TYPES)
    kind = page.choice(tr("File type", "Тип файла"), (
        tr("Any", "Любой"), tr("Documents", "Документы"), tr("Images", "Изображения"),
        tr("Audio", "Аудио"), tr("Video", "Видео"), tr("Archives", "Архивы")))
    sorts = tuple(file_index.ORDER)
    sort = page.choice(tr("Sort by", "Сортировать по"), (tr("Name", "Имя"), tr("Path", "Путь"),
                                                         tr("Largest first", "Сначала большие"),
                                                         tr("Newest first", "Сначала новые")))
    content_query = page.check(tr("Search indexed document content", "Искать в содержимом проиндексированных документов"))
    for element in (*(field.Parent for field in (*fields, kind, sort)), content_query):
        page.panel.Children.Remove(element)
        filter_panel.Children.Add(element)
    show_filters.Checked += lambda *_: setattr(filter_panel, "Visibility", Visibility.Visible)
    show_filters.Unchecked += lambda *_: setattr(filter_panel, "Visibility", Visibility.Collapsed)
    requested = ("", {})
    offset, has_more = 0, False
    result = []
    roots = []

    def selected_file():
        index = results.SelectedIndex
        return result[index] if 0 <= index < len(result) else None

    def file_selection(*_):
        item = selected_file()
        selected_path.Text = item["path"] if item else ""
        reveal.IsEnabled = copy.IsEnabled = item is not None

    def open_result():
        item = selected_file()
        if item:
            page.run(lambda: page.post("/api/open", {"path": file_index.existing_file(item["path"])}))

    def copy_path():
        item = selected_file()
        if item:
            page.copy(item["path"])

    def show(data):
        nonlocal has_more
        items, has_more = data
        result[:] = items
        unit = tr("MiB", "МиБ")

        def format_result(item):
            try:
                modified = f"{datetime.fromtimestamp(item['modified']):%Y-%m-%d}"
            except (ValueError, OverflowError, OSError):
                modified = tr("Unknown date", "Неизвестная дата")
            return f"{item['name']} · {item['size'] / 1024**2:.2f} {unit} · {modified}\n{item['path']}"

        page.show_rows(results, result, format_result)
        result_count.Text = (tr(f"Results {offset + 1}–{offset + len(items)}",
                                f"Результаты {offset + 1}–{offset + len(items)}") if items else
                             tr("No matching files.", "Подходящих файлов нет."))
        previous.IsEnabled, next_page.IsEnabled = offset > 0, has_more
        file_selection()

    def run_search():
        text, filters = requested
        page.run(lambda: file_index.search(text, offset=offset, **filters), show,
                 tr("Searching index…", "Ищу по индексу…"))

    def search():
        nonlocal offset, requested
        if page.busy:
            return
        extension, min_text, max_text, after_text, before_text = (field.Text.strip() for field in fields)
        try:
            minimum = int(float(min_text.replace(",", ".")) * 1024**2) if min_text else 0
            maximum = int(float(max_text.replace(",", ".")) * 1024**2) if max_text else None
            after = int(datetime.strptime(after_text, "%Y-%m-%d").timestamp()) if after_text else None
            before = int((datetime.strptime(before_text, "%Y-%m-%d") + timedelta(days=1)).timestamp()) if before_text else None
            if not 0 <= minimum < 2**63 or maximum is not None and not minimum <= maximum < 2**63:
                raise ValueError()
            if after is not None and before is not None and after >= before:
                raise ValueError()
        except (ValueError, OverflowError, OSError):
            page.notice(tr("Check the file sizes and dates.", "Проверь размеры файлов и даты."))
            return
        offset = 0
        requested = query.Text, dict(extension=extension, kind=kinds[max(0, kind.SelectedIndex)],
                                     min_size=minimum, max_size=maximum, after=after, before=before,
                                     sort=sorts[max(0, sort.SelectedIndex)], contents=bool(content_query.IsChecked))
        run_search()

    def jump(direction):
        nonlocal offset
        if page.busy or direction > 0 and not has_more or direction < 0 and offset == 0:
            return
        offset += direction * file_index.PAGE_SIZE
        run_search()

    page.actions((tr("Search files", "Найти файлы"), search, True))
    query.KeyDown += lambda _, event: search() if event.Key == Key.Enter else None
    result_count = page.text("", 13, True)
    results = page.rows(max_height=310)
    AutomationProperties.SetName(results, tr("File search results", "Результаты поиска файлов"))
    selected_path = page.field(tr("Full path", "Полный путь"))
    selected_path.IsReadOnly = True
    reveal, copy, previous, next_page = page.actions(
        (tr("Show in File Explorer", "Показать в проводнике"), open_result),
        (tr("Copy path", "Скопировать путь"), copy_path),
        (tr("Previous", "Назад"), lambda: jump(-1)),
        (tr("Next", "Далее"), lambda: jump(1)),
    )
    previous.IsEnabled = next_page.IsEnabled = False
    results.SelectionChanged += file_selection
    file_selection()

    page.section(tr("Indexed folders", "Папки в индексе"))
    roots_view = page.rows(max_height=124)
    AutomationProperties.SetName(roots_view, tr("Indexed folders", "Папки в индексе"))
    root_path = page.folder(tr("Folder", "Папка"))
    documents = page.check(tr("Index the content of small text documents", "Индексировать содержимое небольших текстовых документов"))
    page.text(tr("Text documents are read up to 512 KiB. Binary documents are found by name or path.",
                 "Читаются текстовые документы до 512 КиБ. Двоичные документы можно искать по имени или пути."), 12, True)
    exclusions = page.field(tr("Exclusions, one glob per line", "Исключения, по одной маске на строку"), multiline=True)
    index_status = page.text("", 13, True)

    def show_roots(items):
        roots[:] = items
        page.show_rows(roots_view, roots, lambda item: item["path"])

    def load_roots():
        page.run(file_index.roots, show_roots)

    def selected_root(*_):
        index = roots_view.SelectedIndex
        if 0 <= index < len(roots):
            item = roots[index]
            root_path.Text = item["path"]
            documents.IsChecked = item["documents"]
            exclusions.Text = "\n".join(item["exclusions"])

    def save():
        if worker.status()["state"] == "running":
            page.notice(tr("Wait for indexing or cancel it first.", "Дождись индексации или сначала отмени её."))
            return
        path, content, patterns = root_path.Text.strip(), bool(documents.IsChecked), exclusions.Text
        if not path:
            page.notice(tr("Select a folder to index.", "Выбери папку для индексации."))
            return

        def work():
            file_index.save_root(path, content, patterns)
            return file_index.roots()

        def finish(items):
            show_roots(items)
            worker.request()

        page.run(work, finish)

    def remove():
        index = roots_view.SelectedIndex
        if not 0 <= index < len(roots):
            return
        identity = roots[index]["id"]
        if worker.status()["state"] == "running":
            page.notice(tr("Wait for indexing or cancel it first.", "Дождись индексации или сначала отмени её."))
            return

        def work():
            file_index.remove_root(identity)
            return file_index.roots()

        def finish(items):
            show_roots(items)
            search()

        page.run(work, finish)

    page.actions((tr("Save folder", "Сохранить папку"), save, True),
                 (tr("Remove from index", "Убрать из индекса"), remove))
    pause = page.check(tr("Pause indexing", "Пауза индексации"), worker.status()["paused"])
    pause.Checked += lambda *_: worker.pause(True)
    pause.Unchecked += lambda *_: worker.pause(False)
    _, cancel = page.actions((tr("Rebuild index", "Перестроить индекс"), lambda: worker.request(rebuild=True)),
                             (tr("Cancel indexing", "Отменить индексацию"), worker.cancel))
    roots_view.SelectionChanged += selected_root
    revision = worker.status()["revision"]

    def tick(*_):
        nonlocal revision
        status = worker.status()
        state = status["state"]
        if status["paused"]:
            label = tr("Indexing paused", "Индексация на паузе")
        else:
            label = {"idle": tr("Choose folders to index", "Выбери папки для индексации"),
                     "running": tr("Indexing…", "Индексация…"),
                     "done": tr("Index up to date", "Индекс обновлён"),
                     "cancelled": tr("Indexing cancelled", "Индексация отменена"),
                     "error": tr("Index is unavailable", "Индекс недоступен")}[state]
        index_status.Text = f"{label} · " + tr(f"Files: {status['files']} · Skipped: {status['errors']}",
                                              f"Файлы: {status['files']} · Пропущено: {status['errors']}")
        cancel.IsEnabled = state == "running" or status["pending"]
        if revision != status["revision"] and not page.busy:
            revision = status["revision"]
            run_search()

    timer = DispatcherTimer()
    timer.Interval = TimeSpan.FromMilliseconds(350)
    timer.Tick += tick
    timer.Start()
    page.on_leave(timer.Stop)
    tick()
    load_roots()
