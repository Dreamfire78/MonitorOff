"""Builds the .ico files from monitor_icon.svg (build-time only: pymupdf, pillow).

monitor_off.ico        program icon (exe, dialog)       -> APP_COLOR
monitor_off_light.ico  tray icon for a dark taskbar     -> white
monitor_off_dark.ico   tray icon for a light taskbar    -> near black
"""

import io
import re

import pymupdf
from PIL import Image

SVG_FILE = "monitor_icon.svg"
APP_COLOR = "#0078D4"
ICONS = {
    "monitor_off.ico": APP_COLOR,
    "monitor_off_light.ico": "#FFFFFF",
    "monitor_off_dark.ico": "#1F1F1F",
}
SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]


def render(svg_text, color, size):
    svg = svg_text.replace("currentColor", color)
    # Replace "1em" etc. with a fixed size; drawing is driven by the viewBox.
    svg = re.sub(r'(<svg[^>]*?)\swidth="[^"]*"', r'\1 width="24"', svg, count=1)
    svg = re.sub(r'(<svg[^>]*?)\sheight="[^"]*"', r'\1 height="24"', svg, count=1)
    doc = pymupdf.open(stream=svg.encode("utf-8"), filetype="svg")
    page = doc[0]
    zoom = size / page.rect.width
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=True)
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGBA")
    return img if img.size == (size, size) else img.resize((size, size), Image.LANCZOS)


def main():
    with open(SVG_FILE, encoding="utf-8") as f:
        svg_text = f.read()
    for filename, color in ICONS.items():
        images = [render(svg_text, color, s) for s in SIZES]
        # Every size is rendered separately -> sharp lines even at 16/24 px.
        images[-1].save(filename, sizes=[(s, s) for s in SIZES], append_images=images[:-1])
        print(f"{filename} created ({color})")


if __name__ == "__main__":
    main()
