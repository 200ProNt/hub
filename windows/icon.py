import sys

from PIL import Image, ImageDraw

icon = Image.new("RGBA", (256, 256))
draw = ImageDraw.Draw(icon)
draw.rounded_rectangle((5, 5, 250, 250), radius=51, fill="#005fb8")
for x in (63, 139):
    for y in (63, 139):
        draw.rounded_rectangle((x, y, x + 53, y + 53), radius=12, fill="white")
icon.save(sys.argv[1], sizes=[(size, size) for size in (16, 24, 32, 48, 64, 128, 256)])
