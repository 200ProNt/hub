"""Общие доступные элементы управления нативного интерфейса."""

import json
import threading
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from Microsoft.Win32 import OpenFileDialog, SaveFileDialog
from System.Windows import Clipboard, FontWeights, GridLength, MessageBox, MessageBoxButton, MessageBoxImage, MessageBoxResult
from System.Windows import TextWrapping, Thickness, VerticalAlignment
from System.Windows.Automation import AutomationProperties
from System.Windows.Controls import Border, Button, CheckBox, ColumnDefinition, ComboBox, DockPanel, Dock, Grid, ListBox, ListBoxItem
from System.Windows.Controls import ComboBoxItem
from System.Windows.Controls import Orientation, SelectionMode, StackPanel, TextBlock, TextBox, WrapPanel
from System.Windows.Media import Geometry, PenLineCap, PenLineJoin, Stretch
from System.Windows.Shapes import Path
from System.Windows.Forms import DialogResult, FolderBrowserDialog
from tools.i18n import tr

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
        material = self.hub.settings.get("hub-style") == "material"
        title = label(heading, 22 if material else 17)
        title.FontWeight = FontWeights.Normal if material else FontWeights.SemiBold
        title.Margin = Thickness(0, 10, 0, 7)
        return self.add(title)

    def group(self, title, field):
        column = make(StackPanel, Margin=Thickness(0, 2, 0, 8))
        AutomationProperties.SetName(field, title)
        if self.hub.settings.get("hub-style") == "material" and isinstance(field, TextBox):
            from MaterialDesignThemes.Wpf import HintAssist
            HintAssist.SetHint(field, title)
            HintAssist.SetIsFloating(field, True)
            field.MinHeight = max(56, field.MinHeight)
        else:
            caption = label(title)
            caption.Margin = Thickness(0, 0, 0, 4)
            column.Children.Add(caption)
        self.add(column)
        return column

    def field(self, title, value="", multiline=False):
        field = make(TextBox, Text=str(value), AcceptsReturn=multiline,
                        MinHeight=96 if multiline else 34,
                        TextWrapping=TextWrapping.Wrap if multiline else TextWrapping.NoWrap,
                        VerticalContentAlignment=VerticalAlignment.Top if multiline else VerticalAlignment.Center)
        column = self.group(title, field)
        column.Children.Add(field)
        return field

    def _picker(self, title, value, choose):
        grid = Grid()
        grid.ColumnDefinitions.Add(ColumnDefinition())
        grid.ColumnDefinitions.Add(make(ColumnDefinition, Width=GridLength.Auto))
        field = make(TextBox, Text=str(value))
        column = self.group(title, field)
        grid.Children.Add(field)

        def browse():
            path = choose(field.Text)
            if path:
                field.Text = path

        button = self.hub.button(tr("Browse…", "Обзор…"), browse)
        AutomationProperties.SetName(button, tr(f"Browse: {title}", f"Обзор. {title}"))
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

    def choice(self, title, values, index=0, *, previews=None):
        value = make(ComboBox, MinHeight=32)
        column = self.group(title, value)
        for number, item in enumerate(values):
            if previews is None:
                value.Items.Add(str(item))
                continue
            row = make(StackPanel, Orientation=Orientation.Horizontal)
            preview = previews[number]
            preview.Margin = Thickness(0, 0, 8, 0)
            row.Children.Add(preview)
            row.Children.Add(label(item))
            entry = make(ComboBoxItem, Content=row)
            AutomationProperties.SetName(entry, item)
            value.Items.Add(entry)
        value.SelectedIndex = index
        value.DropDownOpened += lambda *_: self.hub.animate_dropdown(value, True)
        value.DropDownClosed += lambda *_: self.hub.animate_dropdown(value, False)
        column.Children.Add(value)
        return value

    def check(self, title, checked=False):
        check = make(CheckBox, Content=title, IsChecked=bool(checked))
        if self.hub.active == "settings" and self.hub.settings.get("hub-style") == "material":
            check.Content = None
            check.Style = self.hub.material_controls.dictionary["MaterialDesignSwitchToggleButton"]
            AutomationProperties.SetName(check, title)
            row = make(DockPanel, Margin=Thickness(4, 4, 8, 4), MinHeight=44)
            DockPanel.SetDock(check, Dock.Right)
            row.Children.Add(check)
            caption = label(title, 16)
            caption.VerticalAlignment = VerticalAlignment.Center

            def toggle(*_):
                if check.IsEnabled:
                    check.Focus()
                    check.IsChecked = not check.IsChecked

            caption.MouseLeftButtonUp += toggle
            row.Children.Add(caption)
            self.add(row)
            return check

        def changed(*_):
            box = check.Template.FindName("Box", check) if check.Template else None
            if box is not None:
                self.hub.animate(box, "press")

        check.Click += changed
        return self.add(check)

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
        def selected(_, event):
            if self.hub.motion_enabled():
                for row in event.AddedItems:
                    if isinstance(row, ListBoxItem):
                        self.hub._transition(row, ListBoxItem.OpacityProperty, .72, 1, 140)
        box.SelectionChanged += selected
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

    def run(self, work, done=None, message=None):
        if message is None:
            message = tr("Working…", "Работаю…")
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

    def run_job(self, route, payload, done, progress, cancel, finished):
        def work():
            identity = self.post(route + "/start", payload)["id"]
            arguments = {"id": identity}
            complete = False
            try:
                while not cancel.wait(.25):
                    state = self.post(route + "/status", arguments)
                    if state["state"] == "running":
                        self.hub.dispatch(lambda update=state: progress(update) if not cancel.is_set() else None)
                        continue
                    if state["state"] == "cancelling":
                        continue
                    complete = True
                    if state["state"] == "done" and not cancel.is_set():
                        return state["result"]
                    if state["state"] == "failed":
                        raise RuntimeError(state["error"])
                    break
            finally:
                if not complete:
                    self.post(route + "/cancel", arguments)
            return None

        def with_cleanup():
            try:
                return work()
            finally:
                self.hub.dispatch(finished)

        self.run(with_cleanup, done)

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
        self.notice(tr("Copied", "Скопировано"))

    @staticmethod
    def open_url(url):
        import webbrowser
        webbrowser.open(url)

    def download(self, path, suggested_filename):
        from pathlib import Path as FilePath

        dialog = make(SaveFileDialog, FileName=suggested_filename)
        if dialog.ShowDialog(self.window):
            target = FilePath(dialog.FileName)
            self.run(lambda: target.write_bytes(self.bytes(path)),
                     lambda _: self.notice(tr(f"Saved to {target.name}", f"Сохранено в {target.name}")))
