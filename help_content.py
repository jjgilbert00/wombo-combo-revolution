"""What the Help dialog (F1) says: the getting-started steps, the colour legends, and the keys
grouped by task. Keys are named as they are now (keys.current), so changing one changes it here too."""
import keys
import theme

STEPS = [
    "Open a recording with [b]{open_track}[/b] (or drop its .json / .mp4 on the window), or record one with "
    "[b]{toggle_recording}[/b] and save it with [b]{save_recording}[/b]. The File menu has samples to try.",
    "Press [b]{toggle_playback}[/b] or [b]Start[/b] and play along: press each input as it reaches the line. No "
    "controller? [b]WASD[/b] + [b]U I O[/b] / [b]J K L[/b].",
    "Mark what matters: select frames (drag in the frame meter) and press [b]{mark_key_input}[/b]. Runs are "
    "graded below your attempt.",
    "Look back: scroll or drag the list, [b]{save_attempt}[/b] saves an attempt, [b]{open_attempts}[/b] lists "
    "and replays attempts. [b]{toggle_display}[/b] tries another display.",
]


def steps():
    return [keys.fill(step) for step in STEPS]

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
    """[[(group title, [(key, what it does, works in game)])]], in two columns: every action with a
    key (both, if it has a hotkey and a shortcut), and the mouse."""
    groups = []
    for title, actions in keys.ACTION_GROUPS:
        rows = []
        for method, description, _, _ in actions:
            hotkey, shortcut = keys.hotkey(method), keys.shortcut(method)
            if method == "toggle_playback":
                shortcut = " / ".join(filter(None, (shortcut, "Start")))
            if method == "restart_playback":
                shortcut = " / ".join(filter(None, (shortcut, "Back")))
            if shortcut or hotkey:
                rows.append((" / ".join(filter(None, (shortcut, hotkey))), description, bool(hotkey)))
        groups.append((title, rows))
    practise, edit, record, view = groups
    edit[1].insert(0, ("Click", "Select a frame (Shift+click extends)", False))
    edit[1].insert(1, ("Drag in Frames", "Select a range of frames", False))
    edit[1].insert(2, ("Right-click", "Menu for the selection", False))
    edit[1].append(("Click a tag", "Edit a note or key input", False))
    view[1].append(("Wheel / drag", "Move through the list, a frame per notch", False))
    view[1].append(("Ctrl+Wheel", "Scroll speed (zoom)", False))
    return [[practise, edit], [record, view]]
