"""Draws the app's icon: a gold arrow speeding right on a dark tile. Run it to regenerate
app_icon.png (the window's icon) and app_icon.ico (the packaged exe's)."""
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
GOLD = (255, 204, 56, 255)
TILE = (26, 26, 31, 255)


def draw(size=256):
    scale = 4
    s = size * scale
    image = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([0, 0, s - 1, s - 1], radius=s * 0.2, fill=TILE)
    # The arrow, a little right of centre, with speed lines trailing it.
    m = s / 2
    shaft, head = s * 0.09, s * 0.22
    x0, x1, tip = s * 0.36, s * 0.56, s * 0.84
    draw.polygon([(x0, m - shaft), (x1, m - shaft), (x1, m - head), (tip, m), (x1, m + head), (x1, m + shaft),
                  (x0, m + shaft)], fill=GOLD)
    for y, start in ((m - s * 0.2, s * 0.18), (m, s * 0.12), (m + s * 0.2, s * 0.18)):
        draw.rounded_rectangle([start, y - s * 0.025, x0 - s * 0.05 if y == m else s * 0.4, y + s * 0.025],
                               radius=s * 0.025, fill=GOLD)
    return image.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    icon = draw()
    icon.save(os.path.join(HERE, "app_icon.png"))
    icon.save(os.path.join(HERE, "app_icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)])
