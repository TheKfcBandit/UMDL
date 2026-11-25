#!/usr/bin/env python3
"""Draw the menu icons embedded in the UMDL shortcut.

Each icon is a flat coloured tile with a white glyph, drawn at 4x and
scaled down for clean edges. Shortcuts crops contact photos to a circle,
so every glyph stays inside the centre of the tile.

    python tools/make_icons.py            # writes assets/icons/*.png
"""

import math
import os

from PIL import Image, ImageDraw

SIZE = 96
SCALE = 4
S = SIZE * SCALE
WHITE = (255, 255, 255, 255)

BLUE = (10, 132, 255)
INDIGO = (94, 92, 230)
TEAL = (48, 176, 199)
GREEN = (52, 199, 89)
ORANGE = (255, 149, 0)
PINK = (255, 55, 95)
GRAY = (142, 142, 147)
RED = (255, 69, 58)
PURPLE = (175, 82, 222)


def u(value):
    """Icon units (0-96) to supersampled pixels."""
    return value * SCALE


def canvas(color):
    image = Image.new("RGBA", (S, S), color + (255,))
    return image, ImageDraw.Draw(image)


def line(draw, points, width=7):
    points = [(u(x), u(y)) for x, y in points]
    draw.line(points, fill=WHITE, width=u(width), joint="curve")
    radius = u(width) / 2
    for x, y in (points[0], points[-1]):
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=WHITE)


def ring(draw, cx, cy, r, width=7, color=WHITE):
    draw.ellipse((u(cx - r), u(cy - r), u(cx + r), u(cy + r)), outline=color, width=u(width))


def dot(draw, cx, cy, r, color=WHITE):
    draw.ellipse((u(cx - r), u(cy - r), u(cx + r), u(cy + r)), fill=color)


def arc(draw, cx, cy, r, start, end, width=7):
    draw.arc((u(cx - r), u(cy - r), u(cx + r), u(cy + r)), start, end, fill=WHITE, width=u(width))


def arrow_head(draw, tip, angle_deg, size=12):
    """Filled triangle whose point sits at tip, pointing along angle_deg."""
    angle = math.radians(angle_deg)
    tx, ty = tip
    back = (tx - size * math.cos(angle), ty - size * math.sin(angle))
    side = size * 0.72
    left = (back[0] + side * math.sin(angle), back[1] - side * math.cos(angle))
    right = (back[0] - side * math.sin(angle), back[1] + side * math.cos(angle))
    draw.polygon([(u(x), u(y)) for x, y in (tip, left, right)], fill=WHITE)


def download(draw, color):
    line(draw, [(48, 26), (48, 56)])
    line(draw, [(35, 45), (48, 58), (61, 45)])
    line(draw, [(31, 70), (65, 70)])


def pencil(draw, color):
    line(draw, [(34, 62), (60, 36)], width=11)
    draw.polygon([(u(27), u(69)), (u(29), u(58)), (u(38), u(67))], fill=WHITE)
    line(draw, [(52, 70), (68, 70)], width=5)


def cycle(draw, color):
    # Three-quarter ring, clockwise, with the arrowhead leading off its end.
    arc(draw, 48, 48, 20, 20, 285)
    end = math.radians(285)
    ex, ey = 48 + 20 * math.cos(end), 48 + 20 * math.sin(end)
    dx, dy = -math.sin(end), math.cos(end)
    arrow_head(draw, (ex + 11 * dx, ey + 11 * dy), math.degrees(math.atan2(dy, dx)), size=15)


def gear(draw, color):
    teeth = 8
    for i in range(teeth):
        angle = 2 * math.pi * i / teeth
        x, y = 48 + 21 * math.cos(angle), 48 + 21 * math.sin(angle)
        dot(draw, x, y, 6.2)
    dot(draw, 48, 48, 19)
    dot(draw, 48, 48, 8.5, color + (255,))


def key(draw, color):
    ring(draw, 38, 58, 11, width=7)
    line(draw, [(46, 50), (66, 30)])
    line(draw, [(58, 38), (65, 45)], width=6)
    line(draw, [(64, 32), (70, 38)], width=6)


def info(draw, color):
    dot(draw, 48, 31, 5.2)
    line(draw, [(48, 44), (48, 68)], width=8)


def album(draw, color):
    draw.rounded_rectangle((u(27), u(31), u(69), u(67)), radius=u(7), outline=WHITE, width=u(6))
    dot(draw, 39, 43, 3.6)
    draw.polygon([(u(31), u(63)), (u(45), u(48)), (u(53), u(56)), (u(58), u(51)), (u(66), u(63))],
                 fill=WHITE)


def stack(draw, color):
    for y in (34, 48, 62):
        dot(draw, 31, y, 3.4)
        line(draw, [(41, y), (67, y)], width=6)


def swap(draw, color):
    line(draw, [(30, 39), (62, 39)], width=6)
    arrow_head(draw, (70, 39), 0, size=13)
    line(draw, [(34, 57), (66, 57)], width=6)
    arrow_head(draw, (26, 57), 180, size=13)


def check(draw, color):
    line(draw, [(31, 49), (43, 61), (66, 36)], width=8)


def cross(draw, color):
    line(draw, [(34, 34), (62, 62)], width=8)
    line(draw, [(62, 34), (34, 62)], width=8)


def trash(draw, color):
    line(draw, [(30, 36), (66, 36)], width=6)
    line(draw, [(42, 30), (54, 30)], width=6)
    draw.rounded_rectangle((u(35), u(41), u(61), u(70)), radius=u(5), fill=WHITE)
    for x in (43, 53):
        draw.line([(u(x), u(47)), (u(x), u(64))], fill=color + (255,), width=u(4))


ICONS = {
    "download": (download, BLUE),
    "pencil": (pencil, INDIGO),
    "resume": (cycle, ORANGE),
    "settings": (gear, GRAY),
    "key": (key, PURPLE),
    "update": (cycle, GREEN),
    "info": (info, TEAL),
    "album": (album, PINK),
    "stack": (stack, ORANGE),
    "convert": (swap, INDIGO),
    "finish": (check, GREEN),
    "forget": (cross, GRAY),
    "reset": (trash, RED),
}


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = os.path.join(root, "assets", "icons")
    os.makedirs(out, exist_ok=True)
    for name, (painter, color) in ICONS.items():
        image, draw = canvas(color)
        painter(draw, color)
        image = image.resize((SIZE, SIZE), Image.LANCZOS).convert("P", palette=Image.ADAPTIVE, colors=48)
        image.save(os.path.join(out, name + ".png"), optimize=True)
    print("wrote %d icons to %s" % (len(ICONS), out))


if __name__ == "__main__":
    main()
