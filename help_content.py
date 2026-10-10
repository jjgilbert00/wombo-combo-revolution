"""What the Help dialog (F1) says: the getting-started steps, the colour legends, and the keys
grouped by task. Hotkeys are named from keys.HOTKEYS, so a key changed there changes here too."""
import theme
from keys import HOTKEYS

STEPS = [
    "Open a recording with [b]Ctrl+O[/b] (or drop its .json / .mp4 on the window), or record one with "
    "[b]F8[/b] and save it with [b]F12[/b]. The File menu has samples to try.",
    "Press [b]Space[/b] or [b]Start[/b] and play along: press each input as it reaches the line. No "
    "controller? [b]WASD[/b] + [b]U I O[/b] / [b]J K L[/b].",
    "Mark what matters: select frames (drag in the frame meter) and press [b]K[/b]. Runs are graded "
    "below your attempt.",
    "Look back: scroll or drag the list, [b]S[/b] saves an attempt, [b]A[/b] lists and replays attempts. "
    "[b]F3[/b] tries another display.",
]

LEGENDS = [
    ("How an input went", [
        (theme.HIT, "Hit", "On time (in a row of runs, with a tick)"),
        (theme.EARLY, "Early", "Too soon, by the frames shown"),
        (theme.LATE, "Late", "Too late, by the frames shown"),
        (theme.MISS, "Missed", "Not done (with a cross)"),
        (theme.PENDING, "Waiting", "Not reached yet"),
    ]),
    ("What the colours mark", [
        (theme.ACCENT, "Key input", "Must be pressed somewhere in its window"),
        (theme.HOLD, "Hold", "A key input held for a number of frames"),
        (theme.EXACT, "Exact span", "A key input matched frame for frame"),
        (theme.METER_BUTTON, "Button", "Frame meter: a button is down on that frame"),
        (theme.METER_DIRECTION, "Stick", "Frame meter: the stick is off neutral"),
    ]),
]


def key_columns():
    """[[(group title, [(key, what it does, works in game)])]], in two columns."""
    hotkey = {method: key for key, _, method in HOTKEYS}
    practise = [
        ("Space / Start", "Play or pause", False),
        (hotkey["play"] + " / " + hotkey["pause"], "Play / pause", True),
        ("Home / Back", "Restart: a fresh attempt while practising", False),
        (hotkey["restart_playback"], "Restart", True),
        (hotkey["toggle_practice"], "Practice or review (replay your attempt)", True),
        ("S", "Save the attempt with the recording", False),
        ("A", "Attempts: rename, show, replay, delete", False),
    ]
    edit = [
        ("Click", "Select a frame (Shift+click extends)", False),
        ("Drag in Frames", "Select a range of frames", False),
        ("Right-click", "Menu for the selection", False),
        ("K", "Mark the selection as a key input", False),
        ("N", "Add a note to the selection", False),
        ("Click a tag", "Edit a note or key input", False),
        ("Esc", "Clear the selection", False),
    ]
    record = [
        (hotkey["toggle_recording"], "Start / stop recording", True),
        ("Ctrl+O / " + hotkey["open_track"], "Open a recording", True),
        ("Ctrl+S", "Save changes to the recording", False),
        (hotkey["save_recording"], "Save recording as (with its video)", True),
        (hotkey["demo_recording"], "Demo the recording in game", True),
        (hotkey["demo_key_inputs"], "Demo just the key inputs in game", True),
    ]
    view = [
        (hotkey["show_help"], "This help", True),
        (hotkey["toggle_overlay"], "Overlay mode: on top of the game", True),
        (hotkey["toggle_display"], "Next display: input list, arrow lanes, ring", True),
        (hotkey["toggle_notes"], "Show / hide notes", True),
        ("Wheel / drag", "Move through the list, a frame per notch", False),
        ("Ctrl+Wheel", "Scroll speed (zoom)", False),
    ]
    return [[("Practise", practise), ("Edit", edit)], [("Record, files and demos", record), ("View", view)]]
