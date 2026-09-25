"""Key inputs: the parts of a recorded combo that actually matter, and how an attempt is scored.

Recordings are full of accidental, extra or over-held inputs. A key input marks what's required and
when: a direction and/or buttons, plus a window of eligible frames. Performing the input on any of
those frames counts as a success, so small timing leniency (or a deliberately wide window) is built
in. Everything outside key inputs is treated as non-essential.

A key input is a dict: {"start": frame, "end": frame, "direction": 1-9 or None, "buttons": [...]}.
The window is inclusive. direction None means any direction; an empty buttons list means the
direction alone is required (e.g. one step of a motion input).
"""
from input_list import LIST_BUTTON_ORDER

HIT, MISS, PENDING = "hit", "miss", "pending"


def satisfied_at(key_input, attempt, frame):
    """Whether the attempt performs the key input on this frame.

    Required buttons must all be held, and at least one must be newly pressed on this frame, so a
    button held down since before the window doesn't count as pressing it.
    """
    state = attempt[frame]
    if state is None:
        return False
    if key_input["direction"] is not None and state["direction"] != key_input["direction"]:
        return False
    buttons = key_input["buttons"]
    if not buttons:
        return True
    if not all(state[button] for button in buttons):
        return False
    previous = attempt[frame - 1] if frame > 0 else None
    return any(not (previous and previous[button]) for button in buttons)


def result(key_input, attempt):
    """HIT if performed on any eligible frame, MISS once the whole window was played without it,
    otherwise PENDING."""
    frames = range(key_input["start"], min(key_input["end"], len(attempt) - 1) + 1)
    if any(satisfied_at(key_input, attempt, frame) for frame in frames):
        return HIT
    if frames and all(attempt[frame] is not None for frame in frames):
        return MISS
    return PENDING


def derive(track, start, end):
    """Guesses what the key input over track frames start..end is.

    The first button press in the range wins (buttons only; add a direction in the editor for
    command normals). With no press, the first non-neutral direction held in the range is used.
    """
    for frame in range(start, end + 1):
        state, previous = track[frame], track[frame - 1] if frame > 0 else None
        pressed = [b for b in LIST_BUTTON_ORDER if state[b] and not (previous and previous[b])]
        if pressed:
            return {"start": start, "end": end, "direction": None, "buttons": pressed}
    for frame in range(start, end + 1):
        if track[frame]["direction"] != 5:
            return {"start": start, "end": end, "direction": track[frame]["direction"], "buttons": []}
    return {"start": start, "end": end, "direction": track[start]["direction"], "buttons": []}


def describe(key_input):
    """Short requirement in numpad notation, e.g. "6+X", "X", "2" or "A+B"."""
    parts = [] if key_input["direction"] is None else [str(key_input["direction"])]
    return "+".join(parts + list(key_input["buttons"])) or "any"
