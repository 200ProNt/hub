"""Formatting, validation, encoding, and differences in the native shell."""

import json

from System.Windows import Visibility
from System.Windows.Automation import AutomationProperties
from System.Windows.Controls import ScrollViewer, TextBlock
from System.Windows.Documents import Run
from tools import developer_tools as dev, jobs
from tools.i18n import tr

from .widgets import label, make


def mount(page):
    tool = page.choice(tr("Tool", "Инструмент"), (
        "JSON", "Regex", "Base64", "URL", tr("Text Diff", "Сравнение текста"), tr("Code Diff", "Сравнение кода")))
    json_action = page.choice(tr("JSON operation", "Действие JSON"), (
        tr("Format", "Форматировать"), tr("Minify", "Минифицировать"), tr("Validate", "Проверить")))
    encoding = page.choice(tr("Encoding operation", "Действие кодирования"), (tr("Encode", "Кодировать"), tr("Decode", "Декодировать")))
    use_file = page.check(tr("Use a file", "Использовать файл"))
    pattern = page.field(tr("Regular expression", "Регулярное выражение"))
    ignore_case = page.check(tr("Ignore case", "Игнорировать регистр"))
    left = page.field(tr("Input text", "Исходный текст"), multiline=True)
    right = page.field(tr("Text after changes", "Текст после изменений"), multiline=True)
    left_file = page.file(tr("Input file", "Исходный файл"))
    right_file = page.file(tr("File after changes", "Файл после изменений"))
    destination = page.folder(tr("Output folder", "Папка результата"), page.default_folder)
    output = page.field(tr("Result", "Результат"), multiline=True)
    output.IsReadOnly = True
    output.MaxHeight = 255
    status = page.text("", 13, True)
    styled = label("")
    display = page.add(make(ScrollViewer, Content=styled, MaxHeight=220))
    AutomationProperties.SetName(display, tr("Highlighted preview", "Предпросмотр с подсветкой"))
    display.Visibility = Visibility.Collapsed
    structure = page.rows(max_height=205)
    AutomationProperties.SetName(structure, tr("JSON structure", "Структура JSON"))
    structure.Visibility = Visibility.Collapsed
    task = None

    def changed(*_):
        index = tool.SelectedIndex
        file = index == 2 and use_file.IsChecked
        for control, visible in (
            (json_action.Parent, index == 0), (encoding.Parent, index in (2, 3)), (use_file, index == 2),
            (pattern.Parent, index == 1), (ignore_case, index == 1), (left.Parent, index != 5 and not file),
            (right.Parent, index == 4), (left_file.Parent, index == 5 or file), (right_file.Parent, index == 5),
            (destination.Parent, bool(file)),
        ):
            control.Visibility = Visibility.Visible if visible else Visibility.Collapsed

    def preview(parts):
        styled.Inlines.Clear()
        for text, highlight in parts:
            segment = Run(text)
            if highlight:
                segment.SetResourceReference(Run.BackgroundProperty, "Accent")
                segment.SetResourceReference(Run.ForegroundProperty, "AccentInk")
            styled.Inlines.Add(segment)
        display.Visibility = Visibility.Visible

    def show_regex(text, matches):
        blob = text.encode("utf-16-le")
        chunks = []
        cursor = 0
        for start, length, _, _ in matches:
            end = (start + length) * 2
            chunks.append((blob[cursor:start * 2].decode("utf-16-le", errors="replace"), False))
            chunks.append((blob[start * 2:end].decode("utf-16-le", errors="replace"), True))
            cursor = end
        chunks.append((blob[cursor:].decode("utf-16-le", errors="replace"), False))
        preview(chunks)

    def outline(raw):
        pending = [(0, "$", raw)]
        shown = []
        while pending and len(shown) < 350:
            depth, key, value = pending.pop()
            if isinstance(value, (dict, list)):
                children = value.items() if isinstance(value, dict) else enumerate(value)
                suffix = f" ({len(value)})"
                pending.extend((depth + 1, str(name), child) for name, child in reversed(list(children)[:350]))
            else:
                suffix = "  " + json.dumps(value, ensure_ascii=True)[:90]
            shown.append("    " * min(depth, 30) + key + suffix)
        page.show_rows(structure, shown, str)
        structure.Visibility = Visibility.Visible

    def stop():
        if task:
            task.cancelled.set()

    def run():
        nonlocal task
        if page.busy:
            return
        index = tool.SelectedIndex
        decode = encoding.SelectedIndex == 1
        file = bool(use_file.IsChecked)
        raw, second, expression = left.Text, right.Text, pattern.Text
        chosen_left, chosen_right, folder = left_file.Text.strip(), right_file.Text.strip(), destination.Text.strip()
        action, insensitive = json_action.SelectedIndex, bool(ignore_case.IsChecked)
        if (index == 5 and (not chosen_left or not chosen_right)
                or index == 2 and file and (not chosen_left or not folder)):
            page.notice(tr("Select the required files and folders.", "Выбери нужные файлы и папки."))
            return
        control = task = jobs.Job(float("inf"))
        cancel.IsEnabled = index == 2 and file
        status.Text = output.Text = ""
        display.Visibility = structure.Visibility = Visibility.Collapsed

        def work():
            try:
                if index == 0:
                    return dev.format_json(raw, compact=action == 1), None
                if index == 1:
                    return dev.regex(expression, raw, insensitive), None
                if index == 2:
                    value = dev.base64_file(chosen_left, folder, decode, control) if file else dev.base64_text(raw, decode)
                    return value, None
                if index == 3:
                    return dev.url_text(raw, decode), None
                value = dev.code_diff(chosen_left, chosen_right) if index == 5 else dev.text_diff(raw, second)
                return value, None
            except jobs.Cancelled:
                return None, tr("Cancelled.", "Операция отменена.")
            except json.JSONDecodeError as exc:
                return None, exc
            except Exception as exc:
                return None, str(exc).split("\n", 1)[0]

        def finish(result):
            nonlocal task
            task = None
            cancel.IsEnabled = False
            value, error = result
            if error:
                if isinstance(error, json.JSONDecodeError):
                    status.Text = tr(f"Line {error.lineno}, column {error.colno} · {error.msg}",
                                     f"Строка {error.lineno}, столбец {error.colno} · {error.msg}")
                    if left.Text == raw:
                        left.Select(len(raw[:error.pos].encode("utf-16-le")) // 2, 1 if error.pos < len(raw) else 0)
                        left.Focus()
                else:
                    status.Text = str(error)
            elif index == 0:
                output.Text, tree = value
                status.Text = tr("Valid JSON.", "JSON корректен.")
                outline(tree)
            elif index == 1:
                matches, more = value
                output.Text = "\n".join(f"{number}. {match[2]}  {json.dumps(match[3], ensure_ascii=False)}"
                                        for number, match in enumerate(matches, 1))
                status.Text = tr(f"Matches: {len(matches)}{'+' if more else ''}", f"Совпадений: {len(matches)}{'+' if more else ''}")
                show_regex(raw, matches)
            else:
                output.Text = value
                if index in (4, 5):
                    if value:
                        preview([(line, line.startswith(("+", "-")) and not line.startswith(("+++", "---")))
                                 for line in value.splitlines(keepends=True)[:1000]])
                    else:
                        status.Text = tr("No differences.", "Различий нет.")

        page.run(work, finish)

    _, _, cancel = page.actions((tr("Run", "Выполнить"), run, True),
                                (tr("Copy result", "Скопировать результат"), lambda: page.copy(output.Text)),
                                (tr("Cancel", "Отменить"), stop))
    cancel.IsEnabled = False
    page.on_leave(stop)
    tool.SelectionChanged += changed
    use_file.Checked += changed
    use_file.Unchecked += changed
    changed()
