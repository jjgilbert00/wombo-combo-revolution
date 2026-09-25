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
     "exact": False,                     # True: every frame must match the recording instead
     "hold": 0}                          # >0: hold direction/buttons this many frames in a row instead
Written in numpad notation, that one is "236X".

An exact key input ignores motion/direction/buttons: the attempt must match the recording on every
frame of the window, for things like a 3-frame micro-walk or holding a charge for exactly so long.

A hold key input needs the direction and buttons held for at least `hold` contiguous frames anywhere
in the (possibly larger) window, like building charge during a combo: starting at the window's
first frame is ideal, but any start that still fits the full hold counts. Directions are held the
way charge works: 2 is any down direction (1, 2 or 3), 4 any back, and so on; a diagonal needs that
exact diagonal. The motion is ignored.
"""
from input_list import LIST_BUTTON_ORDER

HIT, MISS, PENDING = "hit", "miss", "pending"


def normalized(key_input):
    """Fills in fields that older saves don't have."""
    return dict({"motion": [], "direction": None, "buttons": [], "exact": False, "hold": 0}, **key_input)


# Directions that count as holding each direction, the way charge works.
_HELD_AS = {1: {1}, 2: {1, 2, 3}, 3: {3}, 4: {1, 4, 7}, 5: {5}, 6: {3, 6, 9}, 7: {7}, 8: {7, 8, 9}, 9: {9}}


def _held_at(key_input, state):
    """The direction (charge-style) and all the buttons are held in this state."""
    direction = key_input["direction"]
    if direction is not None and state["direction"] not in _HELD_AS[direction]:
        return False
    return all(state[button] for button in key_input["buttons"])


def best_hold(key_input, track):
    """(start, length) of the longest contiguous hold within the window, or None if there's none.
    Unplayed (None) frames break a hold."""
    best, start, length = None, None, 0
    for frame in range(key_input["start"], min(key_input["end"], len(track) - 1) + 1):
        state = track[frame]
        if state is not None and _held_at(key_input, state):
            start, length = (start if length else frame), length + 1
            if best is None or length > best[1]:
                best = (start, length)
        else:
            length = 0
    return best


def _hold_result(key_input, attempt):
    """HIT once the attempt has held long enough, MISS once no run in the window still can
    (unplayed frames might yet be held), otherwise PENDING."""
    best = best_hold(key_input, attempt)
    if best and best[1] >= key_input["hold"]:
        return HIT
    possible = length = 0
    for frame in range(key_input["start"], key_input["end"] + 1):
        state = attempt[frame] if frame < len(attempt) else None
        length = length + 1 if state is None or _held_at(key_input, state) else 0
        possible = max(possible, length)
    return PENDING if possible >= key_input["hold"] else MISS


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
    key_input = normalized(key_input)
    frames = range(key_input["start"], min(key_input["end"], len(attempt) - 1) + 1)
    if key_input["hold"] and not key_input["exact"]:
        return _hold_result(key_input, attempt)
    if key_input["exact"]:
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
    """Numpad notation, e.g. "236X", "6X", "X", "2" or "A+B"; "EXACT 3f" for an exact span and
    "[2] 45f" for a hold (down held for 45 frames)."""
    key_input = normalized(key_input)
    if key_input["exact"]:
        return f"EXACT {key_input['end'] - key_input['start'] + 1}f"
    if key_input["hold"]:
        direction = "" if key_input["direction"] is None else str(key_input["direction"])
        return f"[{direction + '+'.join(key_input['buttons']) or 'any'}] {key_input['hold']}f"
    motion = "".join(str(direction) for direction in key_input["motion"])
    direction = key_input["direction"]
    # The press direction is usually the motion's last step, so don't repeat it.
    held = "" if direction is None or (motion and motion[-1] == str(direction)) else str(direction)
    return (motion + held + "+".join(key_input["buttons"])) or "any"
