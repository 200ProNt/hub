import unittest

from native.palettes import ACCENTS, palette


class PaletteTests(unittest.TestCase):
    def test_presets_and_accents_change_the_whole_surface(self):
        for style, mode in ((s, m) for s in ("glass", "material") for m in ("light", "dark")):
            default = palette(style, mode, None)
            other = palette("glass" if style == "material" else "material", mode, None)
            for key in ("Tint", "Glass", "Layer", "Field", "Track", "Selected"):
                self.assertNotEqual(default[key], other[key], (style, mode, key))
            for accent in ACCENTS:
                themed = palette(style, mode, accent)
                for key in ("Accent", "Glass", "Field", "Hover", "Selected", "Track"):
                    self.assertNotEqual(themed[key], default[key], (style, mode, accent, key))

    def test_system_accent_and_explicit_override(self):
        for mode in ("light", "dark"):
            def colors(system, accent=None):
                return palette("material", mode, accent, system)
            self.assertNotEqual(colors("#0078D4")["Selected"], colors("#DC7010")["Selected"])
            self.assertEqual(colors("#0078D4", "pink"), colors("#DC7010", "pink"))
