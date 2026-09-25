"""Builds the sample Street Fighter 6 recordings in this folder.

Each sample is written out frame by frame (60 per second), as if performed on an Xbox pad with SF6's
default Classic layout: X = LP, Y = MP, RB = HP, A = LK, B = MK, RT = HK. Directions are in numpad
notation for a character facing right (2 = down, 4 = back, 6 = forward, 8 = up).

The timing is hand-made to be plausible, not measured in the game: link and cancel windows and the
charge time are placeholders to adjust against the game's frame data, either here or in the app's
key input editor (click a key input's tag). Run this script again to rebuild the .json files.

    python samples/build_samples.py
"""
import json
import os
import time

BUTTONS = ["A", "B", "X", "Y", "RT", "RB", "LT", "LB"]
HERE = os.path.dirname(os.path.abspath(__file__))


def track(length, *segments):
    """A neutral track with (first frame, last frame, direction, buttons) segments laid over it."""
    frames = [{"direction": 5, **{b: 0 for b in BUTTONS}} for _ in range(length)]
    for first, last, direction, buttons in segments:
        for frame in range(first, last + 1):
            frames[frame] = {"direction": direction, **{b: int(b in buttons) for b in BUTTONS}}
    return frames


def key_input(start, end, motion=(), direction=None, buttons=(), hold=0, exact=False):
    return {"start": start, "end": end, "motion": list(motion), "direction": direction, "buttons": list(buttons),
            "hold": hold, "exact": exact}


def example(name, attempt):
    return {"name": name, "created": time.time(), "attempt": attempt, "shown": True}


def save(name, data):
    path = os.path.join(HERE, name + ".json")
    with open(path, "w") as fout:
        json.dump({"fps": 60, **data}, fout, indent=1, sort_keys=True)
    print("wrote", path)


def ryu():
    """Ryu: st.MP, link cr.MP, cancel into medium Tatsumaki (214 MK).

    Shows a link (a press with a short window), a special cancel with a motion, and key inputs
    ignoring what doesn't matter: the recording has a stray frame of down-forward before the cr.MP
    and holds its buttons longer than needed, which aren't part of any requirement.
    """
    def performance(link_at=36, tatsu_at=46):
        return track(
            90,
            (20, 23, 5, "Y"),                        # st.MP
            (link_at - 1, link_at - 1, 3, ""),       # A stray frame of down-forward on the way down.
            (link_at, link_at + 3, 2, "Y"),          # cr.MP
            (link_at + 4, tatsu_at - 5, 2, ""),      # Still holding down: the Tatsu motion starts here.
            (tatsu_at - 4, tatsu_at - 3, 1, ""),     # down-back
            (tatsu_at - 2, tatsu_at - 1, 4, ""),     # back
            (tatsu_at, tatsu_at + 3, 4, "B"),        # back + MK
        )

    save("SF6 Ryu - st.MP, cr.MP, MK Tatsumaki", {
        "inputs": performance(),
        "key_inputs": [
            key_input(17, 23, buttons=["Y"]),                   # The starter: generous, it only sets the pace.
            key_input(35, 37, direction=2, buttons=["Y"]),      # The link: a 3-frame window.
            # The cancel: the motion has to fit in the window too, so it starts while down is still held
            # after the cr.MP (but after the link's window, so a late link still reads as late, not a miss).
            key_input(40, 50, motion=[2, 1, 4], buttons=["B"]),
        ],
        "notes": [
            {"start": 20, "end": 23, "text": "st.MP (Y). Starts the combo"},
            {"start": 35, "end": 37, "text": "Link cr.MP (down + Y) as st.MP's hitstun ends: a tight window"},
            {"start": 40, "end": 49, "text": "Buffer 214 during cr.MP, then MK (B) to cancel into Tatsumaki"},
        ],
        "saved_attempts": [
            example("Example: clean", performance()),
            example("Example: cr.MP 2 frames late", performance(link_at=39, tatsu_at=49)),
        ],
    })


def guile():
    """Guile: st.MP, link cr.MP, cancel into medium Flash Kick ([2] 8 MK).

    Shows a hold: down must be charged long enough for Flash Kick. Starting the charge on the frame
    after st.MP is ideal, but the link leaves some slack, so the key input only needs the charge to
    fit somewhere in its window. The purple bar shows the ideal, the notch the latest start.
    """
    def performance(charge_from=24, link_at=40, kick_at=64):
        return track(
            100,
            (20, 23, 5, "Y"),                        # st.MP
            (charge_from, kick_at - 1, 2, ""),       # Charging down...
            (link_at, link_at + 3, 2, "Y"),          # ...through cr.MP
            (kick_at, kick_at + 3, 8, "B"),          # up + MK
        )

    save("SF6 Guile - st.MP, cr.MP, MK Flash Kick", {
        "inputs": performance(),
        "key_inputs": [
            key_input(17, 23, buttons=["Y"]),                   # The starter.
            key_input(24, 63, direction=2, hold=36),            # The charge: 36 frames anywhere in 24-63.
            key_input(39, 41, direction=2, buttons=["Y"]),      # The link.
            key_input(62, 66, direction=8, buttons=["B"]),      # Flash Kick: up + MK.
        ],
        "notes": [
            {"start": 20, "end": 23, "text": "st.MP (Y), then hold down straight away"},
            {"start": 24, "end": 28, "text": "Start charging here if you can; by the notch at the latest"},
            {"start": 39, "end": 41, "text": "Link cr.MP (Y) while still holding down"},
            {"start": 62, "end": 66, "text": "Up + MK (B): Flash Kick. Charge time is a placeholder, check it"},
        ],
        "saved_attempts": [
            example("Example: clean", performance()),
            example("Example: charged too late", performance(charge_from=31)),
        ],
    })


if __name__ == "__main__":
    ryu()
    guile()
