"""Общие доступные элементы управления нативного интерфейса."""

import json
import threading
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from Microsoft.Win32 import OpenFileDialog, SaveFileDialog
from System.Windows import Clipboard, FontWeights, GridLength, MessageBox, MessageBoxButton, MessageBoxImage, MessageBoxResult
from System.Windows import TextWrapping, Thickness, VerticalAlignment
from System.Windows.Automation import AutomationProperties
from System.Windows.Controls import Border, Button, CheckBox, ColumnDefinition, ComboBox, Grid, ListBox, ListBoxItem
from System.Windows.Controls import Orientation, SelectionMode, StackPanel, TextBlock, TextBox, WrapPanel
from System.Windows.Media import Geometry, PenLineCap, PenLineJoin, Stretch
from System.Windows.Shapes import Path
from System.Windows.Forms import DialogResult, FolderBrowserDialog

from .icons import ICONS


def make(control_type, **properties):
    control = control_type()
    for key, value in properties.items():
        setattr(control, key, value)
    return control


def label(text, size=14, muted=False):
    value = make(TextBlock, Text=str(text), FontSize=size, TextWrapping=TextWrapping.Wrap)
    value.SetResourceReference(TextBlock.ForegroundProperty, "Muted" if muted else "Ink")
    return value


def glyph(name, size=19, color="Ink"):
    icon = make(Path, Data=Geometry.Parse(ICONS[name]), Width=size, Height=size, Stretch=Stretch.Uniform,
                StrokeThickness=1.5, StrokeStartLineCap=PenLineCap.Round, StrokeEndLineCap=PenLineCap.Round,
                StrokeLineJoin=PenLineJoin.Round, Focusable=False)
    icon.SetResourceReference(Path.StrokeProperty, color)
    return icon


class Page:
    def __init__(self, hub):
        self.hub = hub
        self.window = hub.window
        self.panel = StackPanel()
        self.default_folder = hub.default_folder
        self.busy = False
        self.leave = []
        self.opener = build_opener(ProxyHandler({}))

    def add(self, element):
        self.panel.Children.Add(element)
        return element

    def text(self, text, size=14, muted=False):
        value = label(text, size, muted)
        value.Margin = Thickness(0, 1, 0, 6)
        return self.add(value)

    def section(self, heading):
        title = label(heading, 17)
        title.FontWeight = FontWeights.SemiBold
        title.Margin = Thickness(0, 10, 0, 7)
        return self.add(title)

    def group(self, title):
        column = make(StackPanel, Margin=Thickness(0, 2, 0, 8))
        caption = label(title)
        caption.Margin = Thickness(0, 0, 0, 4)
        column.Children.Add(caption)
        self.add(column)
        return column

    def field(self, title, value="", multiline=False):
        column = self.group(title)
        field = make(TextBox, Text=str(value), AcceptsReturn=multiline,
                        MinHeight=96 if multiline else 34,
                        TextWrapping=TextWrapping.Wrap if multiline else TextWrapping.NoWrap,
                        VerticalContentAlignment=VerticalAlignment.Top if multiline else VerticalAlignment.Center)
        AutomationProperties.SetName(field, title)
        column.Children.Add(field)
        return field

    def _picker(self, title, value, choose):
        column = self.group(title)
        grid = Grid()
        grid.ColumnDefinitions.Add(ColumnDefinition())
        grid.ColumnDefinitions.Add(make(ColumnDefinition, Width=GridLength.Auto))
        field = make(TextBox, Text=str(value))
        AutomationProperties.SetName(field, title)
        grid.Children.Add(field)

        def browse():
            path = choose(field.Text)
            if path:
                field.Text = path

        button = self.hub.button("Обзор…", browse)
        AutomationProperties.SetName(button, f"Обзор. {title}")
        Grid.SetColumn(button, 1)
        button.Margin = Thickness(6, 0, 0, 0)
        grid.Children.Add(button)
        column.Children.Add(grid)
        return field

    def folder(self, title, value=""):
        def choose(initial):
            dialog = make(FolderBrowserDialog, Description=title, SelectedPath=initial)
            try:
                return dialog.SelectedPath if dialog.ShowDialog() == DialogResult.OK else ""
            finally:
                dialog.Dispose()
        return self._picker(title, value, choose)

    def file(self, title, value=""):
        def choose(_):
            dialog = make(OpenFileDialog, Title=title)
            return dialog.FileName if dialog.ShowDialog(self.window) else ""
        return self._picker(title, value, choose)

    def choice(self, title, values, index=0):
        column = self.group(title)
        value = make(ComboBox, MinHeight=32)
        AutomationProperties.SetName(value, title)
        for item in values:
            value.Items.Add(str(item))
        value.SelectedIndex = index
        column.Children.Add(value)
        return value

    def check(self, title, checked=False):
        return self.add(make(CheckBox, Content=title, IsChecked=bool(checked)))

    def actions(self, *entries):
        wrap = make(WrapPanel, Orientation=Orientation.Horizontal, Margin=Thickness(0, 2, 0, 7))
        buttons = []
        for title, callback, *primary in entries:
            button = self.hub.button(title, callback, "Primary" if primary and primary[0] else "Control")
            button.Margin = Thickness(0, 2, 7, 2)
            wrap.Children.Add(button)
            buttons.append(button)
        self.add(wrap)
        return buttons

    def rows(self, max_height=320, multiple=False):
        box = make(ListBox, MaxHeight=max_height, MinHeight=38, Margin=Thickness(0, 3, 0, 8),
                      SelectionMode=SelectionMode.Extended if multiple else SelectionMode.Single)
        return self.add(box)

    @staticmethod
    def show_rows(box, items, formatter):
        box.Items.Clear()
        for number, item in enumerate(items):
            content = formatter(item)
            if isinstance(content, str):
                content = label(content)
            box.Items.Add(make(ListBoxItem, Content=content, Tag=number))

    @staticmethod
    def selected(box, items):
        return [items[int(row.Tag)] for row in box.SelectedItems
                if isinstance(row, ListBoxItem) and 0 <= int(row.Tag) < len(items)]

    def _request(self, path, payload=None):
        request = Request(self.hub.url + path, headers={"Accept": "application/json"})
        if payload is not None:
            request.data = json.dumps(payload).encode()
            request.add_header("Content-Type", "application/json")
        try:
            with self.opener.open(request, timeout=180) as response:
                return response.read()
        except HTTPError as error:
            try:
                message = json.loads(error.read()).get("error", str(error))
            except ValueError:
                message = str(error)
            raise RuntimeError(message) from error

    def bytes(self, path):
        return self._request(path)

    def get(self, path):
        return json.loads(self._request(path))

    def post(self, path, payload):
        return json.loads(self._request(path, payload))

    def run(self, work, done=None, message="Работаю…"):
        if message and self.busy:
            return
        if message:
            self.busy = True
            self.notice(message)

        def finish(value, error):
            if message:
                self.busy = False
            if self.hub.current is not self:
                return
            if error:
                self.notice(str(error))
                return
            if message:
                self.notice("")
            if done is not None:
                try:
                    done(value)
                except Exception as problem:
                    self.notice(str(problem))

        def worker():
            try:
                result = work()
            except Exception as error:
                self.hub.dispatch(lambda reason=error: finish(None, reason))
            else:
                self.hub.dispatch(lambda: finish(result, None))

        threading.Thread(target=worker, daemon=True).start()

    def notice(self, text):
        if self.hub.current is self:
            self.hub.notice(text)

    def confirm(self, title, body):
        return MessageBox.Show(self.window, body, title, MessageBoxButton.YesNo,
                               MessageBoxImage.Question, MessageBoxResult.No) == MessageBoxResult.Yes

    def go(self, tool_id, query=""):
        self.hub.go(tool_id, query)

    def on_leave(self, callback):
        self.leave.append(callback)

    def copy(self, text):
        Clipboard.SetText(str(text))
        self.notice("Скопировано")

    @staticmethod
    def open_url(url):
        import webbrowser
        webbrowser.open(url)

    def download(self, path, suggested_filename):
        from pathlib import Path as FilePath

        dialog = make(SaveFileDialog, FileName=suggested_filename)
        if dialog.ShowDialog(self.window):
            target = FilePath(dialog.FileName)
            self.run(lambda: target.write_bytes(self.bytes(path)), lambda _: self.notice(f"Сохранено в {target.name}"))
