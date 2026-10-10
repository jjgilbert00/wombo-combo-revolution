"""Drawn glyphs shared by the displays: the arrow for each direction (a circled N for neutral), as
PIL images to turn into textures.
"""
import math

from PIL import Image, ImageDraw, ImageFont


DIRECTION_ANGLES = {6: 0, 9: 45, 8: 90, 7: 135, 4: 180, 1: 225, 2: 270, 3: 315}


def draw_direction_glyph(direction, size, font_path):
    """White arrow (or circled N for neutral) with a dark outline, as a PIL RGBA image."""
    scale = 4  # Supersample, then shrink for smooth edges.
    s = size * scale
    image = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    outline = max(2, s // 16)
    if direction == 5:
        inset = outline
        draw.ellipse([inset, inset, s - inset, s - inset], fill=(40, 40, 44, 255), outline=(235, 235, 235, 255),
                     width=outline)
        font = ImageFont.truetype(font_path, int(s * 0.55))
        draw.text((s / 2, s / 2), "N", font=font, fill=(235, 235, 235, 255), anchor="mm")
    else:
        # A right-pointing arrow (as offsets from the centre), turned to point its way. The outline is
        # a stroke around the shape with rounded joins, so it stays even where the head meets the
        # shaft, and the shape is a little smaller than the square to leave room for it.
        m = s / 2
        shaft, head, k = 0.15, 0.34, 0.93
        shape = [(-0.42, -shaft), (0.0, -shaft), (0.0, -head), (0.44, 0.0), (0.0, head), (0.0, shaft), (-0.42, shaft)]
        angle = math.radians(DIRECTION_ANGLES[direction])
        cos, sin = math.cos(angle), math.sin(angle)
        # Counter-clockwise on screen, where y runs down.
        points = [(m + s * k * (x * cos + y * sin), m + s * k * (y * cos - x * sin)) for x, y in shape]
        dark = (30, 30, 34, 255)
        draw.polygon(points, fill=dark)
        draw.line(points + [points[0]], fill=dark, width=outline * 2, joint="curve")
        for x, y in points:  # Round the outer corners too.
            draw.ellipse([x - outline, y - outline, x + outline, y + outline], fill=dark)
        draw.polygon(points, fill=(245, 245, 245, 255))
    return image.resize((size, size), Image.LANCZOS)
