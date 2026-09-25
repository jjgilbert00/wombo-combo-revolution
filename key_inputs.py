"""Key inputs: the parts of a recorded combo that actually matter, and how an attempt is scored.

Recordings are full of accidental, extra or over-held inputs. A key input marks what's required and
when, plus a window of eligible frames. Performing the input anywhere in that window counts as a
success, so small timing leniency (or a deliberately wide window) is built in. Everything outside
key inputs is treated as non-essential.

A key input is a dict:
    {"start": frame, "end": frame,       # the window, inclusive
     "motion": [2, 3, 6],                # directions to pass through in order, or []
     "direction": 6 or None,             # direction held when the buttons are pressed; None = any
     "buttons": ["X"],                   # buttons to press, or [] for a direction/motion alone
     "exact": False}                     # True: every frame must match the recording instead
Written in numpad notation, that one is "236X".

An exact key input ignores motion/direction/buttons: the attempt must match the recording on every
frame of the window, for things like a 3-frame micro-walk or holding a charge for exactly so long.
"""
from input_list import LIST_BUTTON_ORDER

HIT, MISS, PENDING = "hit", "miss", "pending"


def normalized(key_input):
    """Fills in fields that older saves don't have."""
    return dict({"motion": [], "direction": None, "buttons": [], "exact": False}, **key_input)


def _pressed_at(key_input, attempt, frame):
    """The buttons are all held on this frame, at least one newly pressed, with the right direction.

    Requiring a new press means a button held down since before the window doesn't count.
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


def _motion_done(motion, attempt, start, last):
    """The directions in motion appear in order somewhere in frames start..last. Other directions
    in between are allowed, as most games are lenient about that."""
    step = 0
    for frame in range(start, last + 1):
        state = attempt[frame]
        if state is not None and state["direction"] == motion[step]:
            step += 1
            if step == len(motion):
                return True
    return False


def satisfied_at(key_input, attempt, frame):
    """Whether the attempt completes the key input on this frame."""
    key_input = normalized(key_input)
    motion = key_input["motion"]
    if motion and not _motion_done(motion, attempt, key_input["start"], frame):
        return False
    if motion and not key_input["buttons"] and key_input["direction"] is None:
        return True  # A motion on its own is complete once its last direction is reached.
    return _pressed_at(key_input, attempt, frame)


def result(key_input, attempt, target):
    """HIT if completed on any eligible frame, MISS once the whole window was played without it,
    otherwise PENDING. An exact key input is a MISS on the first frame that differs from the target
    and a HIT once every frame has matched."""
    frames = range(key_input["start"], min(key_input["end"], len(attempt) - 1) + 1)
    if key_input.get("exact"):
        if any(attempt[frame] is not None and attempt[frame] != target[frame] for frame in frames):
            return MISS
        return HIT if all(attempt[frame] is not None for frame in frames) else PENDING
    if any(satisfied_at(key_input, attempt, frame) for frame in frames):
        return HIT
    if frames and all(attempt[frame] is not None for frame in frames):
        return MISS
    return PENDING


def derive(track, start, end):
    """Guesses the key input over track frames start..end, keeping everything the recording shows
    (the editor makes it easy to drop stray parts).

    With a button press in the range: the first press, the direction held at that moment, and any
    motion (two or more directions) leading up to it. Without one: the motion, or the single
    direction, held in the range.
    """
    def directions(first, last):
        seen = []
        for frame in range(first, last + 1):
            direction = track[frame]["direction"]
            if direction != 5 and (not seen or seen[-1] != direction):
                seen.append(direction)
        return seen

    for frame in range(start, end + 1):
        state, previous = track[frame], track[frame - 1] if frame > 0 else None
        pressed = [b for b in LIST_BUTTON_ORDER if state[b] and not (previous and previous[b])]
        if pressed:
            leading = directions(start, frame)
            return {"start": start, "end": end, "motion": leading if len(leading) >= 2 else [],
                    "direction": state["direction"] if state["direction"] != 5 else None, "buttons": pressed}
    held = directions(start, end)
    if len(held) >= 2:
        return {"start": start, "end": end, "motion": held, "direction": None, "buttons": []}
    return {"start": start, "end": end, "motion": [], "direction": held[0] if held else 5, "buttons": []}


def describe(key_input):
    """Numpad notation, e.g. "236X", "6X", "X", "2" or "A+B"; "EXACT 3f" for an exact span."""
    key_input = normalized(key_input)
    if key_input["exact"]:
        return f"EXACT {key_input['end'] - key_input['start'] + 1}f"
    motion = "".join(str(direction) for direction in key_input["motion"])
    direction = key_input["direction"]
    # The press direction is usually the motion's last step, so don't repeat it.
    held = "" if direction is None or (motion and motion[-1] == str(direction)) else str(direction)
    return (motion + held + "+".join(key_input["buttons"])) or "any"
