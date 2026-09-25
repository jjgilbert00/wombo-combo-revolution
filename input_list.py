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


# Button remapping: a recording's buttons shown and played in the player's own layout. A map is
# {recorded button: player's button}, one-to-one; buttons it leaves out map to themselves.

def full_map(mapping):
    """The map for every button, with unmapped ones mapping to themselves."""
    return {button: (mapping or {}).get(button, button) for button in LIST_BUTTON_ORDER}


def inverse_map(mapping):
    return {theirs: recorded for recorded, theirs in full_map(mapping).items()}


def map_state(state, mapping):
    """The state with its buttons renamed through mapping (None stays None)."""
    if state is None or not mapping:
        return state
    mapped = {"direction": state["direction"], **{button: 0 for button in LIST_BUTTON_ORDER}}
    for recorded, theirs in full_map(mapping).items():
        if state.get(recorded):
            mapped[theirs] = 1
    return mapped


def map_key(key, mapping):
    """An input_key() (direction, pressed buttons) with its buttons renamed, in the usual order."""
    if not mapping:
        return key
    direction, pressed = key
    renamed = {full_map(mapping)[button] for button in pressed}
    return direction, tuple(button for button in LIST_BUTTON_ORDER if button in renamed)


def map_key_input(key_input, mapping):
    """A key input with its required buttons renamed. (An exact span compares whole frames, which
    are translated anyway.)"""
    if not mapping:
        return dict(key_input)
    table = full_map(mapping)
    return dict(key_input, buttons=[table[button] for button in key_input.get("buttons", [])])
