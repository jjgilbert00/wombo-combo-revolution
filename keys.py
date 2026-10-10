"""The keyboard: hotkeys that work even while the game has focus, the window's own shortcuts, and
playing on the keyboard without a controller.

Hotkeys name the app method they call. check_hotkeys() verifies those methods exist, so renaming one
can't silently break its key: the app calls it at startup.
"""
from pynput import keyboard

from controller import direction_from_axes
from games import GAMES
from input_list import full_map

# (key, what it does, app method). These work while the game has focus.
HOTKEYS = [
    ("F1", "Help and keys", "show_help"),
    ("F2", "Overlay mode (on top, borderless)", "toggle_overlay"),
    ("F3", "Next display: input list, arrow lanes, ring", "toggle_display"),
    ("Shift+F3", "Show / hide notes", "toggle_notes"),
    ("F4", "Practice on/off (record your attempt while playing)", "toggle_practice"),
    ("F5", "Restart playback", "restart_playback"),
    ("F6", "Play", "play"),
    ("F7", "Pause (also stops a demo)", "pause"),
    ("Shift+F6", "Demo the recording in game (virtual controller)", "demo_recording"),
    ("Shift+F7", "Demo just the key inputs in game", "demo_key_inputs"),
    ("F8", "Start / stop recording", "toggle_recording"),
    ("F11", "Open a recording", "open_track"),
    ("F12", "Save recording as (with its video)", "save_recording"),
]

# The window's own shortcuts, by Kivy key code or typed character: (key, modifiers, app method).
SPACE, HOME, ESCAPE = 32, 278, 27
WINDOW_KEYS = [
    (ESCAPE, (), "clear_selection"),
    (SPACE, (), "toggle_playback"),
    (HOME, (), "restart_playback"),
    ("o", ("ctrl",), "open_track"),
    ("s", ("ctrl",), "save"),
    ("n", (), "add_note"),
    ("k", (), "mark_key_input"),
    ("s", (), "save_attempt"),
    ("a", (), "open_attempts"),
]

# Playing without a controller: SF6's PC keyboard layout. Key codes are Kivy's.
GAME_KEYS = {
    273: "up", 274: "down", 275: "right", 276: "left",
    ord("w"): "up", ord("s"): "down", ord("d"): "right", ord("a"): "left",
    ord("u"): "u", ord("i"): "i", ord("o"): "o", ord("j"): "j", ord("k"): "k", ord("l"): "l",
}
ARROW_KEYS = (273, 274, 275, 276)  # These always play; the letters only while practising.
KEY_ACTIONS = {"u": "LP", "i": "MP", "o": "HP", "j": "LK", "k": "MK", "l": "HK"}
LOCKS = ("numlock", "capslock", "scrolllock")  # Come through as modifiers, but aren't keys held down.


def check_hotkeys(app):
    """Raises if a hotkey or shortcut names a method the app doesn't have."""
    missing = [method for _, _, method in HOTKEYS + WINDOW_KEYS if not callable(getattr(app, method, None))]
    if missing:
        raise AttributeError(f"Keys name app methods that don't exist: {missing}")


def window_shortcut(key, codepoint, modifiers):
    """The app method for a key pressed in the window, or None."""
    modifiers = tuple(m for m in modifiers if m not in LOCKS)
    return next((method for which, mods, method in WINDOW_KEYS
                 if (which == key or which == codepoint) and mods == modifiers), None)


def listen_for_hotkeys(on_hotkey):
    """Starts a system-wide listener that calls on_hotkey(method name) for each hotkey pressed, from
    the hook's thread (hand it to the UI thread; don't do the work there). Returns the listener
    (stop() it on exit)."""
    actions = {}
    for key, _, method in HOTKEYS:
        *modifiers, name = key.lower().split("+")
        actions[("shift" in modifiers, getattr(keyboard.Key, name))] = method
    shift_keys = {keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r}
    held_shift = set()

    # Neither callback may return False: that stops the listener.
    def on_press(key):
        if key in shift_keys:
            held_shift.add(key)
        method = actions.get((bool(held_shift), key))
        if method:
            on_hotkey(method)

    def on_release(key):
        held_shift.discard(key)

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    return listener


def keyboard_state(keys_down, action_layout, button_map):
    """The game keys held, as a controller state in the player's buttons (None if none are)."""
    if not keys_down:
        return None
    x = ("right" in keys_down) - ("left" in keys_down)
    y = ("up" in keys_down) - ("down" in keys_down)
    state = {"direction": direction_from_axes(x, y)}
    layout = action_layout or GAMES["sf6"]["default_layout"]
    by_action = {action: recorded for recorded, action in layout.items()}
    mapping = full_map(button_map)
    for key, action in KEY_ACTIONS.items():
        if key in keys_down and action in by_action:
            state[mapping[by_action[action]]] = 1  # The recorded button, then the player's for it.
    return state
