"""Цветовые роли и формы настольного Hub."""

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
    ("material", "dark"): (
        "#F1EDF7", "#D1C7DF", "#181520", "#181520", "#292337", "#2F283E",
        "#221C30", "#3E3451", "#6C5B85", "#D8C4FF", "#342051", "#51406C", "#483C5B", "#88140D20",
    ),
    ("material", "light"): (
        "#242032", "#4D435D", "#FCF7FF", "#FCF7FF", "#EEE4FB", "#F6EEFF",
        "#EAE0F4", "#E3D5F4", "#A68EBB", "#604388", "#FFFFFF", "#DCC9F3", "#D8C9E7", "#5B3D2D56",
    ),
}
ACCENTS = {
    "emerald": ("#A4F0B6", "#176247"), "ocean": ("#A8D4FF", "#145A9C"),
    "sunset": ("#FFD1A4", "#8D421A"), "pink": ("#FFC0DE", "#8D2E62"),
}
RADII = {"glass": (15, 13, 22, 10), "material": (23, 11, 27, 14)}


def _tint(color, accent, amount):
    alpha = color[1:3] if len(color) == 9 else ""
    base, hue = color[-6:], accent[-6:]
    channels = (round(int(base[i:i + 2], 16) * (1 - amount) + int(hue[i:i + 2], 16) * amount)
                for i in (0, 2, 4))
    return "#" + alpha + "".join(f"{channel:02X}" for channel in channels)


def palette(style, theme, accent):
    colors = dict(zip(KEYS, PALETTES.get((style, theme), PALETTES["glass", "dark"])))
    if accent in ACCENTS:
        chosen = ACCENTS[accent][theme == "light"]
        colors["Accent"] = chosen
        colors["AccentInk"] = "#18141D" if theme == "dark" else "#FFFFFF"
        for key in ("Glass", "Layer", "Field", "Hover", "Edge", "Selected", "Track"):
            colors[key] = _tint(colors[key], chosen, .22 if key in ("Hover", "Selected", "Track") else .09)
    return colors
