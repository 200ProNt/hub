import sys

from PIL import Image, ImageDraw

icon = Image.new("RGBA", (512, 512))
draw = ImageDraw.Draw(icon)
draw.rounded_rectangle((10, 10, 501, 501), radius=112, fill="#142e2b", outline="#428278", width=8)
ink = "#a9f5d6"
strokes = (
    ((5, 18), (5, 8), (9, 5), (15, 9), (19, 6), (19, 16), (15, 19), (9, 15), (5, 18)),
    ((9, 5), (9, 15)), ((15, 9), (15, 19)),
)
for stroke in strokes:
    points = [(28 + x * 19, 28 + y * 19) for x, y in stroke]
    draw.line(points, fill=ink, width=23, joint="curve")
    for x, y in points:
        draw.ellipse((x - 11, y - 11, x + 11, y + 11), fill=ink)
icon = icon.resize((256, 256), Image.Resampling.LANCZOS)
icon.save(sys.argv[1], sizes=[(size, size) for size in (16, 24, 32, 48, 64, 128, 256)])
