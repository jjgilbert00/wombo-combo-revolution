"""Input-list representation: a track as runs of "direction + buttons, held for N frames".

This is the fighting-game training-mode style of showing inputs. A new run starts whenever the
direction or any button changes.
"""
from PIL import Image, ImageDraw, ImageFont

# Order buttons appear in within a run.
LIST_BUTTON_ORDER = ["X", "Y", "A", "B", "LB", "RB", "LT", "RT"]

DIRECTION_ANGLES = {6: 0, 9: 45, 8: 90, 7: 135, 4: 180, 1: 225, 2: 270, 3: 315}

# Runs are only followed this far past the visible range; longer holds are labelled "999+".
MAX_COUNT = 999


def input_key(state):
    return state["direction"], tuple(button for button in LIST_BUTTON_ORDER if state[button])


def runs_in_range(track, lo, hi):
    """Runs of identical input overlapping frames [lo, hi), as [(start, length, key), ...].

    Frames that are None (no data, e.g. parts of an attempt not played yet) are skipped. Runs are
    followed past the range so held counts stay correct.
    """
    lo, hi = max(lo, 0), min(hi, len(track))
    first, last = max(0, lo - MAX_COUNT), min(len(track), hi + MAX_COUNT)
    runs = []
    frame = lo
    while frame < hi:
        state = track[frame]
        if state is None:
            frame += 1
            continue
        start, end = frame, frame + 1
        if frame == lo:
            while start > first and track[start - 1] == state:
                start -= 1
        while end < last and track[end] == state:
            end += 1
        runs.append((start, end - start, input_key(state)))
        frame = end
    return runs


def match_runs(target, attempt, lo, hi):
    """Runs of frames where the attempt did or didn't match the target: [(start, length, matched)]."""
    lo, hi = max(lo, 0), min(hi, len(target), len(attempt))
    runs = []
    for frame in range(lo, hi):
        if attempt[frame] is None:
            continue
        matched = attempt[frame] == target[frame]
        if runs and runs[-1][0] + runs[-1][1] == frame and runs[-1][2] == matched:
            runs[-1] = (runs[-1][0], runs[-1][1] + 1, matched)
        else:
            runs.append((frame, 1, matched))
    return runs


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
