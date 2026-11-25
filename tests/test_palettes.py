import unittest

from native.palettes import ACCENTS, PALETTES, palette


class PaletteTests(unittest.TestCase):
    def test_presets_and_accents_change_the_whole_surface(self):
        for style, mode in PALETTES:
            default = palette(style, mode, None)
            other = palette("glass" if style == "material" else "material", mode, None)
            for key in ("Tint", "Glass", "Layer", "Field", "Track", "Selected"):
                self.assertNotEqual(default[key], other[key], (style, mode, key))
            for accent in ACCENTS:
                themed = palette(style, mode, accent)
                for key in ("Accent", "Glass", "Field", "Hover", "Selected", "Track"):
                    self.assertNotEqual(themed[key], default[key], (style, mode, accent, key))
