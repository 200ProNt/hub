"""Оболочка Hub на WPF."""

import os
from pathlib import Path
from urllib.parse import quote

import clr

for assembly in ("WindowsBase", "PresentationCore", "PresentationFramework", "System.Xaml",
                 "System.Windows.Forms", "UIAutomationTypes", "UIAutomationProvider"):
    try:
        clr.AddReference(assembly)
    except Exception:
        framework = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319"
        library = framework / "WPF" / (assembly + ".dll")
        clr.AddReference(str(library if library.is_file() else framework / (assembly + ".dll")))

from System import Action, TimeSpan, Uri
from System.Media import SystemSounds
from System.Threading import ApartmentState, Thread, ThreadStart
from System.Windows import Application, CornerRadius, FontWeights, GridLength, HorizontalAlignment, ShutdownMode
from System.Windows import Duration, Point, SystemParameters, TextWrapping, Thickness, VerticalAlignment, Visibility, WindowState
from System.Windows.Automation import AutomationProperties
from System.Windows.Controls import Border, Button, Grid, Orientation, ScrollViewer, StackPanel
from System.Windows.Input import Key, Keyboard, KeyboardNavigation, KeyboardNavigationMode, ModifierKeys
from System.Windows.Markup import XamlReader
from System.Windows.Media import BrushConverter, ColorConverter, LinearGradientBrush, RotateTransform, ScaleTransform, TranslateTransform
from System.Windows.Media.Animation import DoubleAnimation, QuadraticEase, EasingMode, FillBehavior
from System.Windows.Media.Imaging import BitmapFrame
from System.Windows.Threading import DispatcherTimer

from tools import paths, preferences, tray
from tools.registry import TOOLS

from .backdrop import acrylic
from .palettes import RADII, palette
from .widgets import Page, glyph, label, make

TITLES = {item["id"]: item for item in TOOLS}
GROUPS = (
    ("Рабочее", ("home", "notes", "clipboard", "qrdrop")),
    ("Файлы", ("sorter", "renamer", "dupes", "bigfiles", "diskmap", "compare", "images", "checksum", "cleanup")),
    ("Система", ("trash", "monitor", "about")),
)
class HubWindow:
    def __init__(self, port, version, default_folder, release=None):
        self.url = f"http://127.0.0.1:{port}"
        self.version = version
        self.default_folder = default_folder
        self.window = XamlReader.Parse((Path(__file__).parent / "window.xaml").read_text(encoding="utf-8"))
        self.widget = self.window.FindName
        self.current = None
        self.active = ""
        self.navigation = {}
        self.nav_labels = []
        self.settings = preferences.read()
        self.release = release
        self.release_overlay = None
        self.release_focus = None
        self.exiting = False
        self.search_items = []
        self.focus_before_search = None
        self.search_timer = make(DispatcherTimer, Interval=TimeSpan.FromMilliseconds(150))
        self.search_timer.Tick += self.refresh_search
        icon_file = paths.ROOT / "hub.ico"
        if icon_file.is_file():
            from System.Windows.Media.Imaging import BitmapCacheOption, BitmapCreateOptions
            self.window.Icon = BitmapFrame.Create(Uri(icon_file.as_uri()), BitmapCreateOptions.PreservePixelFormat,
                                                   BitmapCacheOption.OnLoad)
        self.build_chrome()
        self.apply_theme()
        self.window.SourceInitialized += lambda *_: self.apply_theme()
        self.window.SizeChanged += self.resize
        self.window.PreviewKeyDown += self.keydown
        self.window.Closing += self.closing
        self.window.IsVisibleChanged += lambda *_: self.show_release(once=True) if self.window.IsVisible else None
        self.widget("SearchInput").TextChanged += self.search_changed
        self.widget("SearchResults").MouseDoubleClick += lambda *_: self.choose_search()
        self.widget("Overlay").MouseLeftButtonDown += self.overlay_click
        self.go("home")

    def dispatch(self, callback):
        if not self.window.Dispatcher.HasShutdownStarted:
            self.window.Dispatcher.BeginInvoke(Action(callback))

    def notice(self, text):
        self.widget("Status").Text = str(text or "Готово")

    def apply_theme(self):
        self.settings = preferences.read()
        style = self.settings.get("hub-style", "glass")
        if style not in RADII:
            style = "glass"
        theme = "light" if self.settings.get("hub-theme") == "light" else "dark"
        dark = theme == "dark"
        colors = palette(style, theme, self.settings.get("hub-accent"))
        clear = style == "glass" and self.settings.get("desktop-glass", "on") == "on"
        if not acrylic(self.window, clear, dark):
            colors["Tint"] = colors["Solid"]
        converter = BrushConverter()
        for key, value in colors.items():
            self.window.Resources[key] = converter.ConvertFromString(value)
        for key, value in zip(("ControlRadius", "FieldRadius", "PanelRadius", "RowRadius"), RADII[style]):
            self.window.Resources[key] = CornerRadius(value)
        edge = self.window.Resources["Edge"]
        self.window.Resources["GlassRim"] = (
            LinearGradientBrush(ColorConverter.ConvertFromString("#A8F1F8FF"), edge.Color, 110)
            if style == "glass" else edge
        )

    def change_settings(self, **values):
        preferences.update(values)
        self.apply_theme()

    def button(self, title, callback, style="Control", icon=None):
        button = make(Button, Style=self.window.FindResource(style), HorizontalContentAlignment=HorizontalAlignment.Center)
        AutomationProperties.SetName(button, title)
        button.ToolTip = title
        if icon:
            button.Content = glyph(icon)
        else:
            text = label(title)
            text.SetResourceReference(type(text).ForegroundProperty, "AccentInk" if style == "Primary" else "Ink")
            button.Content = text

        def clicked(*_):
            try:
                self.animate(button, "press")
                callback()
            except Exception as error:
                self.notice(str(error))

        button.Click += clicked
        return button

    def nav_button(self, name, icon, callback):
        button = self.button(name, callback, "Navigation")
        button.HorizontalContentAlignment = HorizontalAlignment.Left
        row = make(StackPanel, Orientation=Orientation.Horizontal)
        mark = glyph(icon)
        mark.VerticalAlignment = VerticalAlignment.Center
        row.Children.Add(mark)
        text = label(name)
        text.TextWrapping = TextWrapping.NoWrap
        text.Margin = Thickness(10, 0, 0, 0)
        row.Children.Add(text)
        self.nav_labels.append(text)
        button.Content = row
        return button

    def build_chrome(self):
        brand = self.widget("Brand")
        logo = make(Border, CornerRadius=CornerRadius(9), Width=31, Height=31)
        logo.SetResourceReference(Border.BackgroundProperty, "Accent")
        logo.Child = glyph("mark", 21, "AccentInk")
        brand.Children.Add(logo)
        word = label("Hub", 20)
        word.FontWeight = FontWeights.Bold
        word.Margin = Thickness(9, 0, 0, 0)
        word.VerticalAlignment = VerticalAlignment.Center
        brand.Children.Add(word)
        for title, name, callback in (
            ("Свернуть", "minimize", lambda: setattr(self.window, "WindowState", WindowState.Minimized)),
            ("Развернуть или восстановить", "maximize", self.maximize),
            ("Закрыть окно", "close", self.window.Close),
        ):
            button = self.button(title, callback, "Navigation", name)
            button.Width = 38
            button.Height = 32
            button.Padding = Thickness(8, 2, 8, 2)
            button.HorizontalContentAlignment = HorizontalAlignment.Center
            self.widget("WindowActions").Children.Add(button)

        nav = self.widget("Nav")
        for heading, tool_ids in GROUPS:
            name = label(heading, 11, True)
            name.Margin = Thickness(9, 9, 0, 4)
            self.nav_labels.append(name)
            nav.Children.Add(name)
            for tool_id in tool_ids:
                tool = TITLES[tool_id]
                button = self.nav_button(tool["name"], tool["icon"], lambda target=tool_id: self.go(target))
                self.navigation[tool_id] = button
                nav.Children.Add(button)
        settings = self.nav_button("Настройки", "settings", lambda: self.go("settings"))
        self.navigation["settings"] = settings
        self.widget("NavFoot").Children.Add(settings)

        search = self.button("Поиск по Hub", self.open_search)
        AutomationProperties.SetAcceleratorKey(search, "Ctrl+K")
        row = make(StackPanel, Orientation=Orientation.Horizontal)
        row.Children.Add(glyph("search", 16))
        text = label("Поиск по Hub")
        text.Margin = Thickness(8, 0, 14, 0)
        row.Children.Add(text)
        row.Children.Add(label("Ctrl+K", 12, True))
        search.Content = row
        self.widget("TopBar").Children.Add(search)

    def resize(self, *_):
        compact = self.window.ActualWidth < 740
        self.widget("NavColumn").Width = GridLength(64 if compact else 215)
        for caption in self.nav_labels:
            caption.Visibility = Visibility.Collapsed if compact else Visibility.Visible
        for button in self.navigation.values():
            button.HorizontalContentAlignment = HorizontalAlignment.Center if compact else HorizontalAlignment.Left
            button.Padding = Thickness(4 if compact else 9, 5, 4 if compact else 9, 5)

    def maximize(self):
        self.window.WindowState = WindowState.Normal if self.window.WindowState == WindowState.Maximized else WindowState.Maximized

    def activate(self, route=""):
        if self.exiting:
            return
        self.window.ShowActivated = True
        self.window.Show()
        if self.window.WindowState == WindowState.Minimized:
            self.window.WindowState = WindowState.Normal
        self.window.Activate()
        if self.release_overlay is not None:
            return
        if route == "quick":
            self.open_search()
        elif route:
            self.go(route)

    def closing(self, _, event):
        if not self.exiting and tray.status()["running"]:
            event.Cancel = True
            self.window.Hide()
        else:
            self.exiting = True
            if self.current:
                for callback in self.current.leave:
                    callback()

    def close(self):
        self.exiting = True
        self.window.Close()

    def motion_enabled(self):
        return self.settings.get("hub-motion", "on") == "on" and SystemParameters.ClientAreaAnimation

    @staticmethod
    def _transition(target, prop, start, end, milliseconds):
        effect = DoubleAnimation(start, end, Duration(TimeSpan.FromMilliseconds(milliseconds)))
        effect.EasingFunction = make(QuadraticEase, EasingMode=EasingMode.EaseOut)
        effect.FillBehavior = FillBehavior.Stop
        target.BeginAnimation(prop, effect)

    def animate(self, element, kind="page"):
        if not self.motion_enabled():
            return
        if kind in ("press", "sheet"):
            scale = ScaleTransform(1, 1)
            element.RenderTransformOrigin = Point(.5, .5 if kind == "press" else 0)
            element.RenderTransform = scale
            size, duration = (.96, 120) if kind == "press" else (.975, 230)
            self._transition(scale, ScaleTransform.ScaleXProperty, size, 1, duration)
            self._transition(scale, ScaleTransform.ScaleYProperty, size, 1, duration)
            if kind == "press":
                return
        else:
            shift = TranslateTransform(0, 0)
            element.RenderTransform = shift
            self._transition(shift, TranslateTransform.YProperty, 7, 0, 185)
        self._transition(element, type(element).OpacityProperty, .72, 1, 205)

    def animate_dropdown(self, combo, opened):
        template = combo.Template
        if template is None:
            return
        chevron = template.FindName("Chevron", combo)
        popup = template.FindName("PART_Popup", combo)
        if chevron is not None:
            end = 180 if opened else 0
            rotation = RotateTransform(end)
            chevron.RenderTransformOrigin = Point(.5, .5)
            chevron.RenderTransform = rotation
            if self.motion_enabled():
                self._transition(rotation, RotateTransform.AngleProperty, 180 - end, end, 150)
        if opened and popup is not None and popup.Child is not None:
            self.animate(popup.Child, "sheet")

    def show_release(self, *, once=False):
        if not self.release or self.release_overlay is not None:
            return
        if once and self.settings.get("hub-release-seen") == self.version:
            return
        if self.widget("Overlay").Visibility == Visibility.Visible:
            self.close_search()
        self.release_focus = Keyboard.FocusedElement
        overlay = self.release_overlay = Grid()
        overlay.SetResourceReference(Grid.BackgroundProperty, "Scrim")
        card = make(Border, BorderThickness=Thickness(1), Padding=Thickness(23, 19, 23, 21),
                    Margin=Thickness(14, 49, 14, 15), MaxWidth=560,
                    HorizontalAlignment=HorizontalAlignment.Stretch, VerticalAlignment=VerticalAlignment.Center)
        card.SetResourceReference(Border.BackgroundProperty, "Layer")
        card.SetResourceReference(Border.BorderBrushProperty, "GlassRim")
        card.SetResourceReference(Border.CornerRadiusProperty, "PanelRadius")
        KeyboardNavigation.SetTabNavigation(card, KeyboardNavigationMode.Cycle)
        content = StackPanel()
        header = label(f"Что нового в Hub {self.version}", 24)
        header.FontWeight = FontWeights.SemiBold
        content.Children.Add(header)
        heading = label(self.release.get("title", "Обновление Hub"), 14, True)
        heading.Margin = Thickness(0, 5, 0, 10)
        content.Children.Add(heading)
        for item in self.release["items"]:
            row = label(item, 14)
            row.Margin = Thickness(0, 5, 0, 5)
            content.Children.Add(row)
        done = self.button("Готово", self.close_release, "Primary")
        done.HorizontalAlignment = HorizontalAlignment.Right
        done.Margin = Thickness(0, 12, 0, 0)
        content.Children.Add(done)
        card.Child = make(ScrollViewer, Content=content)
        overlay.Children.Add(card)
        self.widget("Shell").IsEnabled = False
        self.window.Content.Children.Add(overlay)
        self.animate(card, "sheet")
        done.Focus()

    def close_release(self):
        if self.release_overlay is None:
            return
        self.window.Content.Children.Remove(self.release_overlay)
        self.release_overlay = None
        self.widget("Shell").IsEnabled = True
        preferences.update({"hub-release-seen": self.version})
        self.settings["hub-release-seen"] = self.version
        if self.release_focus is not None:
            Keyboard.Focus(self.release_focus)

    def go(self, target, query=""):
        if target not in TITLES and target != "settings":
            return
        if self.current is not None:
            for callback in self.current.leave:
                callback()
        self.active = target
        for key, button in self.navigation.items():
            token = "Selected" if key == target else "Transparent"
            if token == "Selected":
                button.SetResourceReference(Button.BackgroundProperty, token)
                button.SetResourceReference(Button.BorderBrushProperty, "Edge")
            else:
                button.ClearValue(Button.BackgroundProperty)
                button.ClearValue(Button.BorderBrushProperty)
        self.notice("")
        page = self.current = Page(self)
        host = self.widget("ContentPanel")
        host.Children.Clear()
        if target == "home":
            title, hint = "Рабочий стол", ""
        elif target == "settings":
            title, hint = "Настройки", "Оформление, клавиатура и системная интеграция"
        else:
            title, hint = TITLES[target]["name"], TITLES[target]["hint"]
        heading = label(title, 31)
        heading.FontWeight = FontWeights.SemiBold
        heading.Margin = Thickness(0, 0, 0, 3)
        host.Children.Add(heading)
        if hint:
            subtitle = label(hint, 14, True)
            subtitle.Margin = Thickness(0, 0, 0, 14)
            host.Children.Add(subtitle)
        host.Children.Add(page.panel)
        self.widget("Scroller").ScrollToTop()
        try:
            if target == "settings":
                self.mount_settings(page)
            elif target in ("home", "notes", "clipboard"):
                from .personal import mount
                mount(page, target, query)
            elif target in ("sorter", "dupes", "bigfiles", "diskmap", "cleanup"):
                from .file_pages import mount
                mount(page, target)
            elif target in ("renamer", "compare", "images", "checksum"):
                from .workflow_pages import mount
                mount(page, target)
            else:
                from .system_pages import mount
                mount(page, target)
        except Exception as error:
            page.notice(str(error))
            import traceback
            traceback.print_exc()
        self.animate(page.panel)

    def keydown(self, _, event):
        if self.release_overlay is not None:
            if event.Key == Key.Escape:
                event.Handled = True
                self.close_release()
            return
        modifiers = Keyboard.Modifiers
        opened = self.widget("Overlay").Visibility == Visibility.Visible
        if modifiers == ModifierKeys.Control and event.Key == Key.K:
            self.close_search() if opened else self.open_search()
        elif modifiers == ModifierKeys.Control and event.Key == Key.OemComma:
            if opened:
                self.close_search()
            self.go("settings")
        elif opened and event.Key == Key.Escape:
            self.close_search()
        elif opened and event.Key == Key.Enter:
            self.choose_search()
        elif opened and event.Key in (Key.Up, Key.Down):
            box = self.widget("SearchResults")
            if box.Items.Count:
                offset = 1 if event.Key == Key.Down else -1
                box.SelectedIndex = max(0, min(box.Items.Count - 1, box.SelectedIndex + offset))
                box.ScrollIntoView(box.SelectedItem)
        else:
            return
        event.Handled = True

    def overlay_click(self, _, event):
        if event.OriginalSource == self.widget("Overlay"):
            self.close_search()

    def open_search(self):
        if self.release_overlay is not None:
            return
        overlay = self.widget("Overlay")
        if overlay.Visibility == Visibility.Visible:
            self.widget("SearchInput").Focus()
            return
        self.focus_before_search = Keyboard.FocusedElement
        self.widget("Shell").IsEnabled = False
        overlay.Visibility = Visibility.Visible
        self.widget("SearchInput").Clear()
        self.refresh_search()
        self.widget("SearchInput").Focus()
        self.animate(self.widget("Palette"), "sheet")

    def close_search(self):
        self.search_timer.Stop()
        self.widget("Overlay").Visibility = Visibility.Collapsed
        self.widget("Shell").IsEnabled = True
        if self.focus_before_search is not None:
            Keyboard.Focus(self.focus_before_search)

    def search_changed(self, *_):
        self.search_timer.Stop()
        self.search_timer.Start()

    def refresh_search(self, *_):
        self.search_timer.Stop()
        page = self.current
        query = self.widget("SearchInput").Text.strip()

        def show(data):
            if self.widget("Overlay").Visibility != Visibility.Visible or query != self.widget("SearchInput").Text.strip():
                return
            rows = [(tool["id"], tool["name"], tool["hint"]) for tool in data["tools"]]
            rows.extend(("notes", item["title"], item["snippet"]) for item in data.get("notes", []))
            rows.extend(("clipboard", "В буфере", item["snippet"]) for item in data.get("clipboard", []))
            if not query or query.casefold() in "настройки тема прозрачность настройки windows":
                rows.append(("settings", "Настройки", "Тема и прозрачность"))
            self.search_items = rows
            box = self.widget("SearchResults")
            Page.show_rows(box, rows, lambda row: row[1] + "\n" + row[2])
            if rows:
                box.SelectedIndex = 0
            else:
                box.Items.Add("Совпадений нет")

        if not query:
            show({"tools": TOOLS})
        else:
            page.run(lambda: page.get("/api/search?q=" + quote(query)), show, message="")

    def choose_search(self):
        index = self.widget("SearchResults").SelectedIndex
        if 0 <= index < len(self.search_items):
            route = self.search_items[index][0]
            query = self.widget("SearchInput").Text.strip() if route in ("notes", "clipboard") else ""
            self.close_search()
            self.go(route, query)

    def mount_settings(self, page):
        page.section("Внешний вид")
        styles = ("glass", "material")
        preset = page.choice("Оформление", ("Liquid Glass", "Material You"), int(self.settings.get("hub-style") == "material"))
        theme = page.choice("Режим", ("Тёмный", "Светлый"), int(self.settings.get("hub-theme") == "light"))
        accent_values = ("", "ocean", "emerald", "sunset", "pink")
        current_accent = self.settings.get("hub-accent", "")
        accent = page.choice("Оттенок палитры", ("По умолчанию", "Синий", "Изумрудный", "Тёплый", "Розовый"),
                             accent_values.index(current_accent) if current_accent in accent_values else 0)
        glass = page.check("Просвечивание через окно", self.settings.get("desktop-glass", "on") == "on")
        motion = page.check("Плавные переходы", self.settings.get("hub-motion", "on") == "on")
        sound = page.check("Звук при сохранении заметки", self.settings.get("hub-sound", "on") == "on")
        glass.IsEnabled = preset.SelectedIndex == 0

        def change_style(*_):
            if preset.SelectedIndex >= 0:
                glass.IsEnabled = preset.SelectedIndex == 0
                self.change_settings(**{"hub-style": styles[preset.SelectedIndex]})
                self.animate(page.panel)

        preset.SelectionChanged += change_style
        theme.SelectionChanged += lambda *_: theme.SelectedIndex >= 0 and self.change_settings(**{"hub-theme": ("dark", "light")[theme.SelectedIndex]})
        accent.SelectionChanged += lambda *_: accent.SelectedIndex >= 0 and self.change_settings(**{"hub-accent": accent_values[accent.SelectedIndex]})
        for control, key in ((glass, "desktop-glass"), (motion, "hub-motion"), (sound, "hub-sound")):
            def changed(sender, _, setting=key):
                self.change_settings(**{setting: "on" if sender.IsChecked else "off"})
            control.Checked += changed
            control.Unchecked += changed

        page.section("Windows")
        current = tray.status()
        tray_check = page.check("Значок в трее", self.settings.get("tray", "on") == "on")
        hotkeys = page.text(", ".join(current["hotkeys"]) or "Глобальная клавиша пока недоступна", muted=True)
        auto = page.check("Запускать Hub вместе с Windows")
        loaded = False

        def loaded_autostart(result):
            nonlocal loaded
            auto.IsChecked = result["enabled"]
            loaded = True

        def autostart(*_):
            if loaded:
                enabled = bool(auto.IsChecked)
                page.run(lambda: page.post("/api/autostart", {"enabled": enabled}))

        def toggle_tray(*_):
            enabled = bool(tray_check.IsChecked)
            page.run(lambda: page.post("/api/tray/toggle", {"enabled": enabled}),
                     lambda result: setattr(hotkeys, "Text", ", ".join(result["hotkeys"]) or "Горячая клавиша недоступна"))

        tray_check.Checked += toggle_tray
        tray_check.Unchecked += toggle_tray
        auto.Checked += autostart
        auto.Unchecked += autostart
        page.run(lambda: page.get("/api/autostart"), loaded_autostart, message="")

        def shortcut(target):
            page.run(lambda: page.post("/api/shortcuts/create", {"target": target}), lambda _: page.notice("Ярлык создан"))

        page.actions(("Ярлык на рабочем столе", lambda: shortcut("desktop")),
                     ("Ярлык в меню «Пуск»", lambda: shortcut("start_menu")))
        page.section("Данные")
        page.actions(("Сохранить резервную копию", lambda: page.download("/api/system/backup", "hub-backup.zip")),
                     ("Перенести настройки из браузера", lambda: page.open_url(self.url + "/transfer.html")),
                     ("Импорт настроек из файла", lambda: self.import_settings(page)))
        from .update_ui import mount
        mount(page)
        page.actions(("Что нового в этой версии", self.show_release))

    def import_settings(self, page):
        import json
        from Microsoft.Win32 import OpenFileDialog

        dialog = make(OpenFileDialog, Filter="Настройки Hub (*.json)|*.json")
        if dialog.ShowDialog(self.window):
            filename = Path(dialog.FileName)
            if filename.stat().st_size > 16_384:
                raise ValueError("Файл настроек слишком большой")
            settings = json.loads(filename.read_text(encoding="utf-8-sig"))
            if not isinstance(settings, dict):
                raise ValueError("Файл должен содержать настройки Hub")
            allowed = {key: value for key, value in settings.items() if key.startswith("hub-") and key in preferences.OPTIONS}
            if not allowed:
                raise ValueError("Файл должен содержать настройки Hub")
            self.change_settings(**allowed)
            self.go("settings")
            self.notice("Настройки перенесены")

    def saved(self):
        if self.settings.get("hub-sound", "on") == "on":
            SystemSounds.Asterisk.Play()


def run_window(port, version, default_folder, hidden, setup, release=None):
    failures = []

    def main():
        try:
            app = make(Application, ShutdownMode=ShutdownMode.OnMainWindowClose)
            ui = HubWindow(port, version, default_folder, release)
            app.MainWindow = ui.window
            setup(ui)
            if hidden:
                ui.window.ShowActivated = False
                ui.window.Show()
                ui.window.Hide()
                app.Run()
            else:
                app.Run(ui.window)
        except Exception as error:
            failures.append(error)

    thread = Thread(ThreadStart(main))
    thread.SetApartmentState(ApartmentState.STA)
    thread.Start()
    thread.Join()
    if failures:
        raise failures[0]
