"""Цветовые роли и формы настольного Hub."""

from functools import lru_cache

from materialyoucolor.dynamiccolor.material_dynamic_colors import MaterialDynamicColors
from materialyoucolor.hct import Hct
from materialyoucolor.scheme.scheme_tonal_spot import SchemeTonalSpot

KEYS = ("Ink", "Muted", "Solid", "Tint", "Glass", "Layer", "Field", "Hover", "Edge",
        "Accent", "AccentInk", "Selected", "Track", "Scrim")
PALETTES = {
    ("glass", "dark"): (
        "#F0F6FF", "#CBD9EA", "#121B27", "#81101B2B", "#A3233040", "#F1222F40",
        "#CA141F2D", "#6047678C", "#709DC0E3", "#B9E2FF", "#122838", "#8953769D", "#5E485C72", "#70091424",
    ),
    ("glass", "light"): (
        "#182B40", "#3D5671", "#ECF3FC", "#A9EBF4FF", "#D4F5F9FF", "#F7F8FBFF",
        "#EBEDF5FD", "#607DA7D2", "#C88EACCB", "#235882", "#FFFFFF", "#6898BCE0", "#4E8CAACB", "#4B283B54",
    ),

}
ACCENTS = {
    "emerald": ("#A4F0B6", "#176247"), "ocean": ("#A8D4FF", "#145A9C"),
    "sunset": ("#FFD1A4", "#8D421A"), "pink": ("#FFC0DE", "#8D2E62"),
}
RADII = {"glass": (16, 12, 22, 10), "material": (24, 6, 20, 20)}


def _tint(color, accent, amount):
    alpha = color[1:3] if len(color) == 9 else ""
    base, hue = color[-6:], accent[-6:]
    channels = (round(int(base[i:i + 2], 16) * (1 - amount) + int(hue[i:i + 2], 16) * amount)
                for i in (0, 2, 4))
    return "#" + alpha + "".join(f"{channel:02X}" for channel in channels)


MATERIAL_ROLES = {
    "Ink": "onSurface", "Muted": "onSurfaceVariant", "Solid": "surface", "Tint": "surface",
    "Glass": "surfaceContainer", "Layer": "surfaceContainerLow", "Field": "surfaceContainerHighest",
    "Feature": "primaryContainer", "FeatureInk": "onPrimaryContainer", "Secondary": "secondary",
    "Hover": "secondaryContainer", "Edge": "outlineVariant", "Accent": "primary",
    "AccentInk": "onPrimary", "Selected": "secondaryContainer", "Track": "surfaceContainerHigh",
}


@lru_cache(maxsize=16)
def _material(theme, seed):
    source = Hct.from_int(0xFF000000 | int(seed[1:], 16))
    scheme = SchemeTonalSpot(source, theme == "dark", 0.0, spec_version="2025")
    roles = MaterialDynamicColors(spec="2025")
    colors = {key: getattr(roles, role).get_hex(scheme)[:7] for key, role in MATERIAL_ROLES.items()}
    return dict(colors, Scrim="#73000000")


def palette(style, theme, accent, system_accent=None):
    if style == "material":
        seed = ACCENTS[accent][1] if accent in ACCENTS else system_accent or "#6750A4"
        return _material(theme, seed).copy()
    colors = dict(zip(KEYS, PALETTES.get((style, theme), PALETTES["glass", "dark"])))
    if accent in ACCENTS:
        chosen = ACCENTS[accent][theme == "light"]
        colors["Accent"] = chosen
        colors["AccentInk"] = "#18141D" if theme == "dark" else "#FFFFFF"
        for key in ("Glass", "Layer", "Field", "Hover", "Edge", "Selected", "Track"):
            colors[key] = _tint(colors[key], chosen, .22 if key in ("Hover", "Selected", "Track") else .09)
    return dict(colors, Feature=colors["Layer"], FeatureInk=colors["Ink"])
