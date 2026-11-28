import sys
import unittest
from dataclasses import replace
from unittest.mock import patch


@unittest.skipUnless(sys.platform == "win32", "WPF requires Windows")
class MaterialThemeTests(unittest.TestCase):
    def test_startup_filters_and_confirms_disabling_in_both_themes(self):
        from native.ui import ApartmentState, HubWindow, Page, Thread, ThreadStart
        from System.Windows import RoutedEventArgs, Size
        from System.Windows.Automation import AutomationProperties
        from System.Windows.Controls import Button, ListBox, TextBox
        from System.Windows.Media import VisualTreeHelper
        from tools import startup_manager
        from tools.i18n import set_language

        errors = []

        def find(element, name, control_type):
            if isinstance(element, control_type) and AutomationProperties.GetName(element) == name:
                return element
            for index in range(VisualTreeHelper.GetChildrenCount(element)):
                result = find(VisualTreeHelper.GetChild(element, index), name, control_type)
                if result is not None:
                    return result
            return None

        def synchronous_run(page, work, done=None, message=None):
            if page.hub.active == "startup" and done:
                done(work())

        def check():
            try:
                set_language("en")
                for style, theme, width in (("glass", "light", 1080), ("material", "dark", 690)):
                    state = {"hub-style": style, "hub-theme": theme, "hub-motion": "off"}
                    user = startup_manager.Entry("Fixture", "HKCU", False, True, (), target=r"C:\fixture.exe",
                                                 company="Fixture company", target_available=True)
                    system = startup_manager.Entry("System", "HKLM", True, True, ())
                    with (patch("native.ui.preferences.read", return_value=state),
                          patch.object(Page, "run", autospec=True, side_effect=synchronous_run),
                          patch.object(Page, "confirm", side_effect=(False, True, True)) as confirm,
                          patch.object(startup_manager, "is_admin", return_value=False),
                          patch.object(startup_manager, "snapshot", return_value=([user, system], [])) as snapshot,
                          patch.object(startup_manager, "toggle") as toggle):
                        hub = HubWindow(1, "test", "")
                        hub.window.Width = width
                        hub.go("startup")
                        panel = hub.current.panel
                        panel.Measure(Size(width - 220, 700))
                        query = find(panel, "Search startup entries", TextBox)
                        rows = find(panel, "Startup entries", ListBox)
                        details = find(panel, "Executable path", TextBox)
                        button = find(panel, "Disable", Button)
                        self.assertEqual(rows.Items.Count, 2)
                        rows.SelectedIndex = 1
                        self.assertFalse(button.IsEnabled)
                        query.Text = "fixture"
                        self.assertEqual(rows.Items.Count, 1)
                        rows.SelectedIndex = 0
                        self.assertTrue(button.IsEnabled)
                        self.assertEqual(details.Text, user.target)
                        button.RaiseEvent(RoutedEventArgs(Button.ClickEvent))
                        toggle.assert_not_called()
                        saved = replace(user, registered=False)
                        snapshot.return_value = ([saved], [])
                        button.RaiseEvent(RoutedEventArgs(Button.ClickEvent))
                        toggle.assert_called_once_with(user)
                        self.assertEqual(AutomationProperties.GetName(button), "Restore")
                        button.RaiseEvent(RoutedEventArgs(Button.ClickEvent))
                        self.assertEqual(toggle.call_args.args, (saved,))
                        self.assertEqual(confirm.call_count, 3)
                        hub.window.Close()
            except BaseException as error:
                errors.append(error)

        thread = Thread(ThreadStart(check))
        thread.SetApartmentState(ApartmentState.STA)
        thread.Start()
        thread.Join()
        if errors:
            raise errors[0]

    def test_live_theme_change_restores_glass_and_preserves_field_value(self):
        from native.ui import ApartmentState, HubWindow, Page, Thread, ThreadStart
        from System.Windows.Automation import AutomationProperties
        from System.Windows.Controls import ComboBox, StackPanel

        errors = []

        def check():
            try:
                state = {"hub-style": "glass", "hub-motion": "off"}
                with (patch("native.ui.preferences.read", return_value=state),
                      patch("native.ui.preferences.update", side_effect=state.update),
                      patch("native.ui.preferences.system_theme", return_value="light") as system_theme,
                      patch.object(Page, "run")):
                    hub = HubWindow(1, "test", "")
                    self.assertEqual(hub.theme, "light")
                    self.assertEqual(AutomationProperties.GetName(hub.navigation["home"]), "Home")
                    system_theme.return_value = "dark"
                    hub.refresh_system_theme()
                    self.assertEqual(hub.theme, "dark")
                    field = hub.widget("SearchInput")
                    field.Text = "Поиск"
                    original = field.Style
                    for mode in ("dark", "light"):
                        state.update({"hub-style": "material", "hub-theme": mode})
                        hub.apply_theme()
                        kit = hub.material_controls.dictionary
                        from MaterialDesignThemes.Wpf import ButtonAssist
                        self.assertEqual(field.Style, kit["MaterialDesignFilledTextBox"])
                        self.assertEqual(hub.navigation["home"].Style.BasedOn, kit["MaterialDesignFlatButton"])
                        for control in (hub.navigation["home"], hub.search_button):
                            self.assertEqual(ButtonAssist.GetCornerRadius(control).TopLeft, 8)
                        self.assertEqual(hub.window.Resources["PanelRadius"].TopLeft, 12)
                        self.assertEqual(field.Text, "Поиск")
                        hub.go("settings")
                        self.assertEqual(hub.current.field("Тест").MinHeight, 56)
                        state["hub-style"] = "glass"
                        hub.apply_theme()
                        self.assertEqual(field.Style, original)
                    hub.go("settings")

                    def language_choice():
                        return next(control for row in hub.current.panel.Children if isinstance(row, StackPanel)
                                    for control in row.Children if isinstance(control, ComboBox))

                    self.assertEqual(language_choice().SelectedIndex, 0)
                    language_choice().SelectedIndex = 1
                    self.assertEqual(state["hub-language"], "ru")
                    self.assertEqual(AutomationProperties.GetName(hub.navigation["home"]), "Главная")
                    self.assertEqual(language_choice().SelectedIndex, 1)
                    language_choice().SelectedIndex = 0
                    self.assertEqual(AutomationProperties.GetName(hub.navigation["home"]), "Home")
                    hub.window.Close()
            except BaseException as error:
                errors.append(error)

        thread = Thread(ThreadStart(check))
        thread.SetApartmentState(ApartmentState.STA)
        thread.Start()
        thread.Join()
        if errors:
            raise errors[0]
