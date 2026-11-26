import sys
import unittest
from unittest.mock import patch


@unittest.skipUnless(sys.platform == "win32", "WPF requires Windows")
class MaterialThemeTests(unittest.TestCase):
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
