import sys

from PIL import Image, ImageDraw

icon = Image.new("RGBA", (512, 512))
draw = ImageDraw.Draw(icon)
draw.rounded_rectangle((10, 10, 501, 501), radius=99, fill="#182D46", outline="#678EBD", width=9)
for x in (111, 276):
    for y in (111, 276):
        draw.rounded_rectangle((x, y, x + 125, y + 125), radius=29, outline="#CEEAFF", width=22)
icon = icon.resize((256, 256), Image.Resampling.LANCZOS)
icon.save(sys.argv[1], sizes=[(size, size) for size in (16, 24, 32, 48, 64, 128, 256)])
