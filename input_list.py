"""Input-list representation: a track as rows of "direction + buttons, held for N frames".

This is the fighting-game training-mode style of showing inputs. A new row starts whenever the
direction or any button changes.
"""
from bisect import bisect_right

from PIL import Image, ImageDraw, ImageFont

# Order buttons appear in within a row.
LIST_BUTTON_ORDER = ["X", "Y", "A", "B", "LB", "RB", "LT", "RT"]

DIRECTION_ANGLES = {6: 0, 9: 45, 8: 90, 7: 135, 4: 180, 1: 225, 2: 270, 3: 315}


def input_key(state):
    return state["direction"], tuple(button for button in LIST_BUTTON_ORDER if state[button])


class InputRuns:
    """Groups a track into rows of identical input, updated incrementally while recording."""

    def __init__(self):
        self._track = None
        self._synced = 0
        self.starts = []
        self.keys = []
        self.total = 0

    def sync(self, track):
        # Tracks are only ever appended to in place; anything else is a new list or a truncation.
        if track is not self._track or len(track) < self._synced:
            self._track, self._synced, self.starts, self.keys = track, 0, [], []
        for i in range(self._synced, len(track)):
            key = input_key(track[i])
            if not self.keys or key != self.keys[-1]:
                self.starts.append(i)
                self.keys.append(key)
        self._synced = self.total = len(track)

    def length(self, row):
        end = self.starts[row + 1] if row + 1 < len(self.starts) else self.total
        return end - self.starts[row]

    def window(self, frame, rows_before, rows_after):
        """Returns ([(row index, frames held, key), ...], position).

        position is fractional: row k reaches the hit line when position == k and has fully passed
        it at k + 1, so each row crosses the line exactly on the frame it starts. A frame past the
        end of the track (e.g. while recording) puts every row behind the line.
        """
        count = len(self.starts)
        if not count:
            return [], 0.0
        if frame >= self.total:
            position = float(count)
        else:
            row = bisect_right(self.starts, frame) - 1
            position = row + (frame - self.starts[row]) / self.length(row)
        current = int(position)
        rows = range(max(0, current - rows_before), min(count, current + rows_after + 1))
        return [(row, self.length(row), self.keys[row]) for row in rows], position


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
        # Right-pointing arrow, rotated into place.
        m = s / 2
        shaft, head = s * 0.15, s * 0.34
        points = [
            (s * 0.08, m - shaft), (s * 0.5, m - shaft), (s * 0.5, m - head), (s * 0.94, m),
            (s * 0.5, m + head), (s * 0.5, m + shaft), (s * 0.08, m + shaft),
        ]
        draw.polygon(points, fill=(245, 245, 245, 255), outline=(30, 30, 34, 255), width=outline)
        image = image.rotate(DIRECTION_ANGLES[direction], resample=Image.BICUBIC)
    return image.resize((size, size), Image.LANCZOS)
