"""Компоненты Material Design 3 для WPF. Сборки NuGet 5.4.0, Behaviors 1.1.142."""
from pathlib import Path

import clr
from System import Uri
from System.Windows import CornerRadius, FontWeights, ResourceDictionary, Setter, Style, Thickness
from System.Windows.Controls import Button, CheckBox, ComboBox, Slider, TextBox
from System.Windows.Media import FontFamily

from .palettes import MATERIAL_CONTROL_RADIUS

ASSETS = Path(__file__).with_name("material")
for assembly in ("Microsoft.Xaml.Behaviors", "MaterialDesignColors", "MaterialDesignThemes.Wpf"):
    clr.AddReference(str(ASSETS / (assembly + ".dll")))

from MaterialDesignThemes.Wpf import BaseTheme, ButtonAssist, CustomColorTheme, RippleAssist, TransitionAssist


class MaterialControls:
    def __init__(self, window):
        self.window = window
        self.theme = CustomColorTheme()
        defaults = ResourceDictionary()
        defaults.Source = Uri("pack://application:,,,/MaterialDesignThemes.Wpf;component/Themes/MaterialDesign3.Defaults.xaml")
        self.dictionary = ResourceDictionary()
        self.dictionary.MergedDictionaries.Add(self.theme)
        self.dictionary.MergedDictionaries.Add(defaults)
        self.font = FontFamily(Uri((ASSETS.parents[1] / "web/fonts").as_uri() + "/"), "./#Roboto")
        self.original_font = window.FontFamily
        self.styles = {}
        for name, base in (("Control", "MaterialDesignOutlinedButton"), ("Primary", "MaterialDesignRaisedButton"),
                           ("Navigation", "MaterialDesignFlatButton")):
            style = Style(clr.GetClrType(Button), defaults[base])
            style.Setters.Add(Setter(ButtonAssist.CornerRadiusProperty, CornerRadius(MATERIAL_CONTROL_RADIUS)))
            style.Setters.Add(Setter(Button.PaddingProperty, Thickness(20, 0, 20, 0)))
            style.Setters.Add(Setter(Button.MinHeightProperty, 40.0))
            style.Setters.Add(Setter(Button.FontWeightProperty, FontWeights.Medium))
            self.styles["Active" + name] = style
        for control, key in ((TextBox, "MaterialDesignFilledTextBox"), (ComboBox, "MaterialDesignFilledComboBox"),
                             (CheckBox, "MaterialDesignCheckBox"), (Slider, "MaterialDesignSlider")):
            self.styles[clr.GetClrType(control)] = defaults[key]
        resources = window.Resources
        self.original = {key: resources[key] for key in self.styles}

    def apply(self, enabled, dark, motion):
        resources = self.window.Resources
        if enabled:
            self.theme.BaseTheme = BaseTheme.Dark if dark else BaseTheme.Light
            self.theme.PrimaryColor = resources["Accent"].Color
            self.theme.SecondaryColor = resources["Secondary"].Color
            if not resources.MergedDictionaries.Contains(self.dictionary):
                resources.MergedDictionaries.Add(self.dictionary)
            for name, key in (("Foreground", "Ink"), ("ForegroundLight", "Muted"), ("Background", "Solid"),
                              ("Primary.Foreground", "AccentInk"), ("TextBox.FilledBackground", "Field"),
                              ("ComboBox.FilledBackground", "Field"), ("ComboBox.DropDown.Background", "Layer")):
                self.dictionary["MaterialDesign.Brush." + name] = resources[key]
        elif resources.MergedDictionaries.Contains(self.dictionary):
            resources.MergedDictionaries.Remove(self.dictionary)
        for key, style in (self.styles if enabled else self.original).items():
            resources[key] = style
        self.window.FontFamily = self.font if enabled else self.original_font
        RippleAssist.SetIsDisabled(self.window, not motion)
        TransitionAssist.SetDisableTransitions(self.window, not motion)
