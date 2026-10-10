"""Small builders for controller states and tracks, so tests read like the inputs they describe."""
import os
import sys

# Tests import the app's modules from the repository root.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from input_list import LIST_BUTTON_ORDER  # noqa: E402


def source(*path):
    """A file of the app's source, as text."""
    with open(os.path.join(ROOT, *path), encoding="utf-8") as f:
        return f.read()


def state(direction=5, *buttons):
    """A controller state: a numpad direction and the buttons held, e.g. state(2, "Y")."""
    return {"direction": direction, **{button: int(button in buttons) for button in LIST_BUTTON_ORDER}}


def track(*spans):
    """A track from (frames, direction, *buttons) spans, e.g. track((5, 5), (3, 2, "Y")) is five
    neutral frames then three of down + Y."""
    frames = []
    for frames_long, direction, *buttons in spans:
        frames += [state(direction, *buttons) for _ in range(frames_long)]
    return frames


def key_input(start, end, motion=(), direction=None, buttons=(), exact=False, hold=0):
    return {"start": start, "end": end, "motion": list(motion), "direction": direction, "buttons": list(buttons),
            "exact": exact, "hold": hold}
