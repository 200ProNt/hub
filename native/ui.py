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
from System.Windows.Controls import Border, Button, Grid, Image, Orientation, ScrollViewer, StackPanel
from System.Windows.Input import Key, Keyboard, KeyboardNavigation, KeyboardNavigationMode, ModifierKeys
from System.Windows.Markup import XamlReader
from System.Windows.Media import BrushConverter, ColorConverter, GradientStop, ImageBrush, LinearGradientBrush, RotateTransform, ScaleTransform, TranslateTransform
from System.Windows.Media.Animation import CubicEase, DoubleAnimation, EasingMode, FillBehavior
from System.Windows.Media.Imaging import BitmapFrame
from System.Windows.Threading import DispatcherTimer

from tools import paths, preferences, tray
from tools.i18n import set_language, tr
from tools.registry import TOOLS

from .backdrop import acrylic
from .palettes import ACCENTS, RADII, palette
from .widgets import Page, glyph, label, make

TITLES = {item["id"]: item for item in TOOLS}
ENGLISH_TITLES = {
    "home": ("Home", "Daily overview and quick actions"),
    "clipboard": ("Clipboard", "Find and reuse copied text"),
    "notes": ("Notes", "Quick notes on this computer"),
    "qrdrop": ("Phone Transfer", "Send files and text over Wi-Fi with a QR code"),
    "sorter": ("File Sorter", "Organize a folder by file type"),
    "renamer": ("Batch Rename", "Rename multiple files with rules"),
    "dupes": ("Duplicate Files", "Find files with identical contents"),
    "bigfiles": ("Large Files", "See what takes up the most space"),
    "diskmap": ("Disk Map", "See what takes up space in a folder or drive"),
    "compare": ("Compare Folders", "Find new, missing, and changed files"),
    "images": ("Image Tools", "Convert, compress, and resize images"),
    "checksum": ("Hashes and Passwords", "Verify file checksums and generate passwords"),
    "cleanup": ("Cleanup", "Find old files and empty folders"),
    "trash": ("Trash", "Restore files moved to Hub Trash"),
    "monitor": ("PC Monitor", "Track system and process activity"),
    "about": ("About", "Version, license, and source code"),
}
GROUPS = (
    (("Workspace", "Рабочее"), ("home", "notes", "clipboard", "qrdrop")),
    (("Files", "Файлы"), ("sorter", "renamer", "dupes", "bigfiles", "diskmap", "compare", "images", "checksum", "cleanup")),
    (("System", "Система"), ("trash", "monitor", "about")),
)
ACCENT_NAMES = {
    "graphite": ("Graphite", "Графит"),
    "ocean": ("Steel blue", "Стальной синий"),
    "emerald": ("Eucalyptus", "Эвкалипт"),
    "lavender": ("Lavender", "Лаванда"),
    "sand": ("Sand", "Песочный"),
    "sunset": ("Terracotta", "Терракота"),
    "pink": ("Dusty rose", "Пыльная роза"),
}


def tool_title(route):
    entry = TITLES[route]
    return tr(ENGLISH_TITLES[route], (entry["name"], entry["hint"]))


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
        self.language = self.settings.get("hub-language", "en")
        set_language(self.language)
        self.release = release
        self.release_overlay = None
        self.release_focus = None
        self.exiting = False
        self.search_items = []
        self.focus_before_search = None
        self.search_timer = make(DispatcherTimer, Interval=TimeSpan.FromMilliseconds(150))
        self.search_timer.Tick += self.refresh_search
        self.window.Icon = BitmapFrame.Create(Uri(paths.ICON.as_uri()))
        self.material_controls = None
        for name in ("Control", "Primary", "Navigation"):
            self.window.Resources["Active" + name] = self.window.FindResource(name)
        self.build_chrome()
        self.apply_theme()
        self.theme_timer = make(DispatcherTimer, Interval=TimeSpan.FromSeconds(2))
        self.theme_timer.Tick += self.refresh_system_theme
        self.theme_timer.Start()
        self.window.SourceInitialized += lambda *_: self.apply_theme()
        self.window.SizeChanged += self.resize
        self.window.PreviewKeyDown += self.keydown
        self.window.Closing += self.closing
        self.window.IsVisibleChanged += lambda *_: self.show_release(once=True) if self.window.IsVisible else None
        self.widget("SearchInput").TextChanged += self.search_changed
        self.widget("SearchResults").MouseDoubleClick += lambda *_: self.choose_search()
        self.widget("Overlay").MouseLeftButtonDown += self.overlay_click
        rail = self.widget("NavigationRail")
        reflection = self.widget("Reflection")
        reflection.Background = reflection.Background.Clone()
        rail.MouseMove += self.move_reflection
        rail.MouseLeave += lambda *_: self.hide_reflection()
        self.go("home")

    def dispatch(self, callback):
        if not self.window.Dispatcher.HasShutdownStarted:
            self.window.Dispatcher.BeginInvoke(Action(callback))

    def notice(self, text):
        status = self.widget("Status")
        message = str(text or tr("Ready", "Готово"))
        if status.Text != message:
            status.Text = message
            if self.motion_enabled():
                self._transition(status, status.OpacityProperty, .65, 1, 140)

    def apply_theme(self):
        self.settings = preferences.read()
        language = self.settings.get("hub-language", "en")
        relabel = self.language != language
        if relabel:
            self.language = language
            set_language(language)
            self.build_chrome()
        style = self.settings.get("hub-style", "glass")
        if style not in RADII:
            style = "glass"
        theme = self.settings.get("hub-theme")
        if theme not in ("dark", "light"):
            theme = preferences.system_theme()
        self.theme = theme
        dark = theme == "dark"
        accent = SystemParameters.WindowGlassColor
        colors = palette(style, theme, self.settings.get("hub-accent"), f"#{accent.R:02X}{accent.G:02X}{accent.B:02X}")
        clear = style == "glass" and self.settings.get("desktop-glass", "on") == "on"
        if not acrylic(self.window, clear, dark):
            colors["Tint"] = colors["Solid"]
        converter = BrushConverter()
        for key, value in colors.items():
            self.window.Resources[key] = converter.ConvertFromString(value)
        accented = self.settings.get("hub-accent") in ACCENTS
        self.logo.Visibility = Visibility.Collapsed if accented else Visibility.Visible
        self.accent_logo.Visibility = Visibility.Visible if accented else Visibility.Collapsed
        for key, value in zip(("ControlRadius", "FieldRadius", "PanelRadius", "RowRadius"), RADII[style]):
            self.window.Resources[key] = CornerRadius(value)
        edge = self.window.Resources["Edge"]
        chrome = self.window.Resources["Glass"]
        rim = edge
        if style == "glass":
            rim = LinearGradientBrush(ColorConverter.ConvertFromString("#C8FFFFFF"), edge.Color, 125)
            rim.GradientStops.Add(GradientStop(ColorConverter.ConvertFromString("#227D93AB"), .53))
            chrome = LinearGradientBrush(self.window.Resources["Selected"].Color, chrome.Color, 124)
            chrome.GradientStops.Add(GradientStop(self.window.Resources["Glass"].Color, .34))
        self.window.Resources["ChromeFill"] = chrome
        self.window.Resources["GlassRim"] = rim
        self.window.Resources["PanelStroke"] = Thickness(0 if style == "material" else 1)
        material = style == "material"
        if material and self.material_controls is None:
            from .material_controls import MaterialControls
            self.material_controls = MaterialControls(self.window)
        if self.material_controls is not None:
            self.material_controls.apply(material, dark, self.motion_enabled())
        self.search_button.MinWidth = 248 if material else 0
        self.search_button.Height = 52 if material else 33
        self.search_button.SetResourceReference(Button.BackgroundProperty, "Field" if material else "Glass")
        self.search_button.BorderThickness = Thickness(0 if material else 1)
        self.search_button.HorizontalContentAlignment = HorizontalAlignment.Left
        self.widget("Scroller").Padding = Thickness(16, 8, 16, 12) if material else Thickness(5, 2, 10, 5)
        self.resize()
        self.hide_reflection()
        if relabel and self.active:
            self.go(self.active)

    def refresh_system_theme(self, *_):
        if self.settings.get("hub-theme", "auto") == "auto" and preferences.system_theme() != self.theme:
            self.apply_theme()

    def hide_reflection(self):
        reflection = self.widget("Reflection")
        opacity = reflection.Opacity
        reflection.Opacity = 0
        if opacity and self.motion_enabled():
            self._transition(reflection, Border.OpacityProperty, opacity, 0, 170)
        else:
            reflection.BeginAnimation(Border.OpacityProperty, None)

    def move_reflection(self, rail, event):
        if self.settings.get("hub-style", "glass") != "glass" or not self.motion_enabled() or SystemParameters.HighContrast:
            return
        cursor = event.GetPosition(rail)
        center = Point(cursor.X / max(1, rail.ActualWidth), cursor.Y / max(1, rail.ActualHeight))
        reflection = self.widget("Reflection")
        reflection.Background.Center = center
        reflection.Background.GradientOrigin = center
        if reflection.ReadLocalValue(Border.OpacityProperty) != 1:
            start = reflection.Opacity
            reflection.Opacity = 1
            self._transition(reflection, Border.OpacityProperty, start, 1, 160)

    def change_settings(self, **values):
        preferences.update(values)
        self.apply_theme()

    def button(self, title, callback, style="Control", icon=None):
        button = make(Button, HorizontalContentAlignment=HorizontalAlignment.Center)
        button.SetResourceReference(Button.StyleProperty, "Active" + style)
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
        def hover(sender, _):
            if self.motion_enabled() and sender.Template:
                layer = sender.Template.FindName("Highlight", sender)
                if layer is not None:
                    entering = sender.IsMouseOver
                    self._transition(layer, Border.OpacityProperty, 0 if entering else .09,
                                     .09 if entering else 0, 130 if entering else 190)
        button.MouseEnter += hover
        button.MouseLeave += hover
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
        self.nav_labels.clear()
        for name in ("Brand", "WindowActions", "Nav", "NavFoot", "TopBar"):
            self.widget(name).Children.Clear()
        search_name = tr("Search Hub", "Поиск по Hub")
        self.widget("SearchTitle").Text = search_name
        AutomationProperties.SetName(self.widget("SearchInput"), search_name)
        self.widget("SearchHint").Text = tr("↑ ↓  Select      Enter  Open      Esc  Close",
                                            "↑ ↓  Выбрать      Enter  Открыть      Esc  Закрыть")
        brand = self.widget("Brand")
        tile = BitmapFrame.Create(Uri(paths.ICON.with_suffix(".png").as_uri()))
        letter = BitmapFrame.Create(Uri(paths.ICON.with_name("hub-icon-letter.png").as_uri()))
        logo = make(Grid, Width=31, Height=31)
        self.logo = make(Image, Source=tile)
        self.accent_logo = make(Grid, OpacityMask=ImageBrush(tile))
        self.accent_logo.SetResourceReference(Grid.BackgroundProperty, "Accent")
        mark = make(Border, OpacityMask=ImageBrush(letter))
        mark.SetResourceReference(Border.BackgroundProperty, "AccentInk")
        self.accent_logo.Children.Add(mark)
        logo.Children.Add(self.logo)
        logo.Children.Add(self.accent_logo)
        brand.Children.Add(logo)
        word = label("Hub", 20)
        word.FontWeight = FontWeights.Bold
        word.Margin = Thickness(9, 0, 0, 0)
        word.VerticalAlignment = VerticalAlignment.Center
        brand.Children.Add(word)
        for title, name, callback in (
            (tr("Minimize", "Свернуть"), "minimize", lambda: setattr(self.window, "WindowState", WindowState.Minimized)),
            (tr("Maximize or restore", "Развернуть или восстановить"), "maximize", self.maximize),
            (tr("Close window", "Закрыть окно"), "close", self.window.Close),
        ):
            button = self.button(title, callback, "Navigation", name)
            button.Width = 38
            button.MinHeight = 0
            button.Height = 32
            button.Padding = Thickness(8, 2, 8, 2)
            button.HorizontalContentAlignment = HorizontalAlignment.Center
            self.widget("WindowActions").Children.Add(button)

        nav = self.widget("Nav")
        for heading, tool_ids in GROUPS:
            name = label(tr(*heading), 11, True)
            name.Margin = Thickness(9, 9, 0, 4)
            self.nav_labels.append(name)
            nav.Children.Add(name)
            for tool_id in tool_ids:
                tool = TITLES[tool_id]
                button = self.nav_button(tool_title(tool_id)[0], tool["icon"], lambda target=tool_id: self.go(target))
                self.navigation[tool_id] = button
                nav.Children.Add(button)
        settings = self.nav_button(tr("Settings", "Настройки"), "settings", lambda: self.go("settings"))
        self.navigation["settings"] = settings
        self.widget("NavFoot").Children.Add(settings)

        search = self.search_button = self.button(search_name, self.open_search)
        AutomationProperties.SetAcceleratorKey(search, "Ctrl+K")
        row = make(StackPanel, Orientation=Orientation.Horizontal)
        row.Children.Add(glyph("search", 16))
        text = label(search_name)
        text.Margin = Thickness(8, 0, 14, 0)
        row.Children.Add(text)
        row.Children.Add(label("Ctrl+K", 12, True))
        search.Content = row
        self.widget("TopBar").Children.Add(search)

    def resize(self, *_):
        compact = (self.window.ActualWidth or self.window.Width) < 740
        material = self.settings.get("hub-style") == "material"
        self.widget("NavColumn").Width = GridLength((80 if material else 64) if compact else (252 if material else 215))
        for caption in self.nav_labels:
            caption.Visibility = Visibility.Collapsed if compact else Visibility.Visible
        for button in self.navigation.values():
            button.HorizontalContentAlignment = HorizontalAlignment.Center if compact else HorizontalAlignment.Left
            inset = 4 if compact else (16 if material else 9)
            button.MinHeight = 48 if material else 33
            button.Padding = Thickness(inset, 5, inset, 5)
            button.Margin = Thickness(0, 1, 0, 1) if material else Thickness(0)

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
            self.theme_timer.Stop()
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
        effect.EasingFunction = make(CubicEase, EasingMode=EasingMode.EaseOut)
        effect.FillBehavior = FillBehavior.Stop
        target.BeginAnimation(prop, effect)

    def animate(self, element, kind="page"):
        if not self.motion_enabled():
            return
        if kind == "chart":
            scale = ScaleTransform(1, 1)
            element.RenderTransformOrigin = Point(.5, .5)
            element.RenderTransform = scale
            self._transition(scale, ScaleTransform.ScaleXProperty, .88, 1, 340)
            self._transition(scale, ScaleTransform.ScaleYProperty, .08, 1, 480)
        elif kind in ("press", "sheet"):
            scale = ScaleTransform(1, 1)
            element.RenderTransformOrigin = Point(.5, .5 if kind == "press" else 0)
            element.RenderTransform = scale
            size, duration = (.975, 155) if kind == "press" else (.965, 260)
            self._transition(scale, ScaleTransform.ScaleXProperty, size, 1, duration)
            self._transition(scale, ScaleTransform.ScaleYProperty, size, 1, duration)
            if kind == "press":
                return
        else:
            shift = TranslateTransform(0, 0)
            element.RenderTransform = shift
            self._transition(shift, TranslateTransform.YProperty, 12, 0, 260)
        self._transition(element, type(element).OpacityProperty, .45, 1, 195)

    def animate_dropdown(self, combo, opened):
        template = combo.Template
        if template is None:
            return
        chevron = template.FindName("Chevron", combo)
        popup = template.FindName("PART_Popup", combo)
        if chevron is not None:
            end = 180 if opened else 0
            previous = chevron.RenderTransform
            start = previous.Angle if isinstance(previous, RotateTransform) else 0
            rotation = RotateTransform(end)
            chevron.RenderTransformOrigin = Point(.5, .5)
            chevron.RenderTransform = rotation
            if self.motion_enabled():
                self._transition(rotation, RotateTransform.AngleProperty, start, end, 180)
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
        header = label(tr(f"What's new in Hub {self.version}", f"Что нового в Hub {self.version}"), 24)
        header.FontWeight = FontWeights.SemiBold
        content.Children.Add(header)
        heading = label(tr(self.release.get("title_en", "Hub update"),
                           self.release.get("title", "Обновление Hub")), 14, True)
        heading.Margin = Thickness(0, 5, 0, 10)
        content.Children.Add(heading)
        for item in tr(self.release.get("items_en", self.release["items"]), self.release["items"]):
            row = label(item, 14)
            row.Margin = Thickness(0, 5, 0, 5)
            content.Children.Add(row)
        done = self.button(tr("Done", "Готово"), self.close_release, "Primary")
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
            title, hint = tool_title("home")[0], ""
        elif target == "settings":
            title, hint = tr("Settings", "Настройки"), tr("Appearance, language, and Windows integration",
                                                         "Внешний вид, язык и интеграция с Windows")
        else:
            title, hint = tool_title(target)
        heading = label(title, 31)
        if self.settings.get("hub-style") == "material":
            heading.FontSize = 36
            heading.FontWeight = FontWeights.Normal
        else:
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
        self.animate(host)

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
            matches = {tool["id"] for tool in data.get("tools", [])}
            rows = [(route, *tool_title(route)) for route in TITLES
                    if route in matches or query.casefold() in " ".join(tool_title(route)).casefold()]
            rows.extend(("notes", item["title"], item["snippet"]) for item in data.get("notes", []))
            rows.extend(("clipboard", tr("Clipboard entry", "В буфере"), item["snippet"]) for item in data.get("clipboard", []))
            if query.casefold() in "settings appearance theme language windows настройки тема язык прозрачность":
                rows.append(("settings", tr("Settings", "Настройки"), tr("Appearance and language", "Внешний вид и язык")))
            self.search_items = rows
            box = self.widget("SearchResults")
            Page.show_rows(box, rows, lambda row: row[1] + "\n" + row[2])
            if rows:
                box.SelectedIndex = 0
            else:
                box.Items.Add(tr("No matches", "Совпадений нет"))

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
        page.section(tr("Appearance", "Внешний вид"))
        flags = [make(Image, Width=23, Height=15,
                      Source=BitmapFrame.Create(Uri((Path(__file__).parent / "flags" / f"{code}.png").as_uri())))
                 for code in ("en", "ru")]
        language = page.choice(tr("Language", "Язык"), ("English", "Русский"),
                               int(self.language == "ru"), previews=flags)
        styles = ("glass", "material")
        preset = page.choice(tr("Style", "Оформление"), ("Liquid Glass", "Material You (beta)"),
                             int(self.settings.get("hub-style") == "material"))
        modes = ("auto", "dark", "light")
        mode = self.settings.get("hub-theme", "auto")
        theme = page.choice(tr("Theme mode", "Режим темы"),
                            (tr("Auto (Windows)", "Авто (Windows)"), tr("Dark", "Тёмный"), tr("Light", "Светлый")),
                            modes.index(mode) if mode in modes else 0)
        accent_values = ("", *ACCENTS)
        current_accent = self.settings.get("hub-accent", "")
        converter = BrushConverter()
        swatches = [make(Border, Width=16, Height=16, CornerRadius=CornerRadius(4),
                         Background=converter.ConvertFromString(color))
                    for color in ("#7B8593", *(pair[1] for pair in ACCENTS.values()))]
        accent = page.choice(tr("Palette accent", "Оттенок палитры"),
                             (tr("Default", "По умолчанию"), *(tr(*ACCENT_NAMES[key]) for key in ACCENTS)),
                             accent_values.index(current_accent) if current_accent in accent_values else 0,
                             previews=swatches)
        glass = page.check(tr("Translucent window", "Просвечивание через окно"), self.settings.get("desktop-glass", "on") == "on")
        motion = page.check(tr("Smooth transitions", "Плавные переходы"), self.settings.get("hub-motion", "on") == "on")
        sound = page.check(tr("Play sound when saving a note", "Звук при сохранении заметки"), self.settings.get("hub-sound", "on") == "on")
        glass.IsEnabled = preset.SelectedIndex == 0

        def change_style(*_):
            if preset.SelectedIndex >= 0:
                glass.IsEnabled = preset.SelectedIndex == 0
                self.change_settings(**{"hub-style": styles[preset.SelectedIndex]})
                self.go("settings")

        preset.SelectionChanged += change_style
        language.SelectionChanged += lambda *_: language.SelectedIndex >= 0 and self.change_settings(
            **{"hub-language": ("en", "ru")[language.SelectedIndex]})
        if self.window.IsKeyboardFocusWithin:
            preset.Focus()
        theme.SelectionChanged += lambda *_: theme.SelectedIndex >= 0 and self.change_settings(**{"hub-theme": modes[theme.SelectedIndex]})
        accent.SelectionChanged += lambda *_: accent.SelectedIndex >= 0 and self.change_settings(**{"hub-accent": accent_values[accent.SelectedIndex]})
        for control, key in ((glass, "desktop-glass"), (motion, "hub-motion"), (sound, "hub-sound")):
            def changed(sender, _, setting=key):
                self.change_settings(**{setting: "on" if sender.IsChecked else "off"})
            control.Checked += changed
            control.Unchecked += changed

        page.section("Windows")
        current = tray.status()
        tray_check = page.check(tr("Show tray icon", "Значок в трее"), self.settings.get("tray", "on") == "on")
        hotkeys = page.text(", ".join(current["hotkeys"]) or tr("Global shortcut unavailable", "Глобальная клавиша пока недоступна"), muted=True)
        auto = page.check(tr("Start Hub with Windows", "Запускать Hub вместе с Windows"))
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
                     lambda result: setattr(hotkeys, "Text", ", ".join(result["hotkeys"]) or tr("Shortcut unavailable", "Горячая клавиша недоступна")))

        tray_check.Checked += toggle_tray
        tray_check.Unchecked += toggle_tray
        auto.Checked += autostart
        auto.Unchecked += autostart
        page.run(lambda: page.get("/api/autostart"), loaded_autostart, message="")

        def shortcut(target):
            page.run(lambda: page.post("/api/shortcuts/create", {"target": target}), lambda _: page.notice(tr("Shortcut created", "Ярлык создан")))

        page.actions((tr("Create desktop shortcut", "Ярлык на рабочем столе"), lambda: shortcut("desktop")),
                     (tr("Create Start menu shortcut", "Ярлык в меню «Пуск»"), lambda: shortcut("start_menu")))
        page.section(tr("Data", "Данные"))
        page.actions((tr("Save a backup", "Сохранить резервную копию"), lambda: page.download("/api/system/backup", "hub-backup.zip")),
                     (tr("Transfer browser settings", "Перенести настройки из браузера"), lambda: page.open_url(self.url + "/transfer.html")),
                     (tr("Import settings from a file", "Импорт настроек из файла"), lambda: self.import_settings(page)))
        from .update_ui import mount
        mount(page)
        page.actions((tr("What's new in this version", "Что нового в этой версии"), self.show_release))

    def import_settings(self, page):
        import json
        from Microsoft.Win32 import OpenFileDialog

        dialog = make(OpenFileDialog, Filter=tr("Hub settings (*.json)|*.json", "Настройки Hub (*.json)|*.json"))
        if dialog.ShowDialog(self.window):
            filename = Path(dialog.FileName)
            if filename.stat().st_size > 16_384:
                raise ValueError(tr("Settings file is too large", "Файл настроек слишком большой"))
            settings = json.loads(filename.read_text(encoding="utf-8-sig"))
            if not isinstance(settings, dict):
                raise ValueError(tr("The file must contain Hub settings", "Файл должен содержать настройки Hub"))
            allowed = {key: value for key, value in settings.items() if key.startswith("hub-") and key in preferences.OPTIONS}
            if not allowed:
                raise ValueError(tr("The file must contain Hub settings", "Файл должен содержать настройки Hub"))
            self.change_settings(**allowed)
            self.go("settings")
            self.notice(tr("Settings imported", "Настройки перенесены"))

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
