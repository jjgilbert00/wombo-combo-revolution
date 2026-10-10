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
EARLY, LATE = "early", "late"  # Grades for a miss that was done just outside the window.
GRADE_REACH = 12  # How many frames outside a window to look for an early or late input.


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


def _hold_runs(key_input, track, first, last):
    """(start, length) of every contiguous hold in track frames first..last."""
    runs, start = [], None
    for frame in range(first, last + 2):
        state = track[frame] if frame <= last else None
        if state is not None and _held_at(key_input, state):
            start = frame if start is None else start
        elif start is not None:
            runs.append((start, frame - start))
            start = None
    return runs


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


def _nearest(offsets):
    """The offset closest to the window, preferring early on a tie; None if there are none."""
    return min(offsets, key=lambda offset: (abs(offset), offset)) if offsets else None


def _missed_by(key_input, attempt, target, lo, hi):
    """How many frames outside the window a missed key input was done: negative for early,
    positive for late, None if it wasn't done within lo..hi at all."""
    start, end = key_input["start"], key_input["end"]
    if key_input["exact"]:
        # The whole span played exactly, just shifted in time.
        shifts = [d for d in range(lo - start, hi - end + 1) if d and all(
            attempt[frame + d] is not None and attempt[frame + d] == target[frame] for frame in range(start, end + 1))]
        return _nearest(shifts)
    if key_input["hold"]:
        # A long enough hold that sits partly outside the window: it started too soon or ended too late.
        offsets = []
        for run_start, length in _hold_runs(key_input, attempt, lo, hi):
            if length >= key_input["hold"]:
                offsets.append(run_start - start if run_start < start else run_start + length - 1 - end)
        return _nearest(offsets)
    early = next((frame - start for frame in range(start - 1, lo - 1, -1)
                  if satisfied_at(dict(key_input, start=lo), attempt, frame)), None)
    late = next((frame - end for frame in range(end + 1, hi + 1) if satisfied_at(key_input, attempt, frame)), None)
    return _nearest([offset for offset in (early, late) if offset is not None])


def grade(key_input, attempt, target, lo=None, hi=None):
    """(grade, offset): HIT/PENDING with offset 0, EARLY or LATE with how many frames outside the
    window it was done (-3 = three frames early), or MISS. Early and late are looked for in frames
    lo..hi, by default GRADE_REACH frames either side of the window."""
    key_input = normalized(key_input)
    outcome = result(key_input, attempt, target)
    if outcome != MISS:
        return outcome, 0
    lo = max(0, key_input["start"] - GRADE_REACH if lo is None else lo)
    hi = min(len(attempt) - 1, key_input["end"] + GRADE_REACH if hi is None else hi)
    offset = _missed_by(key_input, attempt, target, lo, hi)
    if offset is None:
        return MISS, 0
    return (EARLY if offset < 0 else LATE), offset


def grade_all(key_inputs, attempt, target):
    """Grades each key input (sorted by start), looking for early and late inputs only up to the
    neighbouring key inputs' windows, so an input that belongs to the next one isn't counted as
    this one done late. Holds are left out of that both ways: other inputs are done during a
    charge, and a charge started late runs on into the next input."""
    grades = []
    for i, key_input in enumerate(key_inputs):
        key_input = normalized(key_input)
        lo = key_input["start"] - GRADE_REACH
        hi = key_input["end"] + GRADE_REACH
        is_hold = lambda k: k["hold"] and not k["exact"]
        bounding = [normalized(k) for k in key_inputs]
        bounding = [] if is_hold(key_input) else [(j, k) for j, k in enumerate(bounding) if j != i and not is_hold(k)]
        for j, other in bounding:
            if j < i:
                lo = max(lo, other["end"] + 1)
            else:
                hi = min(hi, other["start"] - 1)
        grades.append(grade(key_input, attempt, target, lo, hi))
    return grades


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


def derive_hold(track, start, end):
    """Guesses what's held over track frames start..end: the direction held longest (charge-style),
    or failing that the button held longest. Returns the direction, buttons and hold length."""
    window = {"start": start, "end": end, "motion": [], "direction": None, "buttons": []}
    candidates = [dict(window, direction=d) for d in (2, 4, 6, 8, 1, 3, 7, 9)]
    candidates += [dict(window, buttons=[b]) for b in LIST_BUTTON_ORDER]
    best, length = None, 0
    for candidate in candidates:
        run = best_hold(candidate, track)
        if run and run[1] > length:
            best, length = candidate, run[1]
    if best is None:
        return {"direction": None, "buttons": [], "hold": end - start + 1}
    return {"direction": best["direction"], "buttons": best["buttons"], "hold": length}


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


DEMO_PRESS_FRAMES = 3  # How long a demo holds each press; a 1-frame tap can slip between game polls.
DEMO_MOTION_STEP_FRAMES = 2  # How long a demo holds each direction of a motion.


def demo_track(key_inputs, target):
    """The recording cleaned down to its key inputs: a track (as long as the target) that does only
    what's required, for demoing the combo without the stray and over-held inputs.

    Everything else is neutral. Holds are held over the recording's own longest hold in the window
    (so a charge lasts right up to its release); exact spans are copied frame for frame; presses
    come on the first frame the recording completed them, held briefly, with any motion laid out
    just before. Presses go on last, so they add their buttons to a hold underneath.
    """
    track = [{"direction": 5, **{button: 0 for button in LIST_BUTTON_ORDER}} for _ in target]

    def put(frame, direction=None, buttons=()):
        if 0 <= frame < len(track):
            if direction is not None:
                track[frame]["direction"] = direction
            for button in buttons:
                track[frame][button] = 1

    key_inputs = sorted((normalized(k) for k in key_inputs), key=lambda k: (k["start"], k["end"]))
    is_hold = lambda k: k["hold"] and not k["exact"]
    for key_input in filter(is_hold, key_inputs):
        start, length = best_hold(key_input, target) or (key_input["start"], key_input["hold"])
        for frame in range(start, start + max(length, key_input["hold"])):
            put(frame, key_input["direction"], key_input["buttons"])
    for key_input in (k for k in key_inputs if k["exact"]):
        for frame in range(key_input["start"], min(key_input["end"], len(target) - 1) + 1):
            track[frame] = dict(target[frame])
    for key_input in (k for k in key_inputs if not is_hold(k) and not k["exact"]):
        frame = next((f for f in range(key_input["start"], min(key_input["end"], len(target) - 1) + 1)
                      if satisfied_at(key_input, target, f)), key_input["start"])
        motion = list(key_input["motion"])
        direction = key_input["direction"] if key_input["direction"] is not None else (motion[-1] if motion else None)
        if motion and motion[-1] == direction:
            motion.pop()  # The motion's last direction is the one held on the press.
        step_frame = frame - len(motion) * DEMO_MOTION_STEP_FRAMES
        for step in motion:
            for _ in range(DEMO_MOTION_STEP_FRAMES):
                put(step_frame, step)
                step_frame += 1
        for offset in range(DEMO_PRESS_FRAMES):
            put(frame + offset, direction, key_input["buttons"])
    return track
