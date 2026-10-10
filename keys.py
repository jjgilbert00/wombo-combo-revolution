"""The keyboard: the keys for the app's actions (which the player can change), and playing on the
keyboard without a controller.

Each action has up to two keys: a hotkey, which works even while the game has focus, and a
shortcut, which works in the app's window. Both are named like "Shift+F3" or "Ctrl+O". The keys in
use are a Bindings, `current` here: the defaults in ACTIONS, with the player's changes (kept in the
"keys" setting) on top. Actions name the app method they call; check_actions() verifies those
methods exist, so renaming one can't silently break its key: the app calls it at startup.
"""
from pynput import keyboard

from controller import direction_from_axes
from games import GAMES
from button_map import full_map

HOTKEY, SHORTCUT = "hotkey", "shortcut"

# (group, [(app method, what it does, default hotkey, default shortcut)]); "" is no key.
ACTION_GROUPS = [
    ("Practise", [
        ("toggle_playback", "Play or pause", "", "Space"),
        ("play", "Play", "F6", ""),
        ("pause", "Pause (also stops a demo)", "F7", ""),
        ("restart_playback", "Restart: a fresh attempt while practising", "F5", "Home"),
        ("toggle_practice", "Practice or review (replay your attempt)", "F4", ""),
        ("save_attempt", "Save the attempt with the recording", "", "S"),
        ("open_attempts", "Attempts: rename, show, replay, delete", "", "A"),
    ]),
    ("Edit", [
        ("mark_key_input", "Mark the selection as a key input", "", "K"),
        ("add_note", "Add a note to the selection", "", "N"),
        ("clear_selection", "Clear the selection", "", "Esc"),
    ]),
    ("Record, files and demos", [
        ("toggle_recording", "Start / stop recording", "F8", ""),
        ("open_track", "Open a recording", "F11", "Ctrl+O"),
        ("save", "Save changes to the recording", "", "Ctrl+S"),
        ("save_recording", "Save recording as (with its video)", "F12", ""),
        ("demo_recording", "Demo the recording in game", "Shift+F6", ""),
        ("demo_key_inputs", "Demo just the key inputs in game", "Shift+F7", ""),
    ]),
    ("View", [
        ("show_help", "Help and keys", "F1", ""),
        ("toggle_overlay", "Overlay mode: on top of the game", "F2", ""),
        ("toggle_display", "Next display: input list, arrow lanes, ring", "F3", ""),
        ("toggle_notes", "Show / hide notes", "Shift+F3", ""),
    ]),
]
ACTIONS = [action for _, actions in ACTION_GROUPS for action in actions]
DESCRIPTIONS = {method: text for method, text, _, _ in ACTIONS}

# The keys an action can have: name -> (Kivy key code, Windows virtual-key code).
KEYS = {
    **{chr(c): (c + 32, c) for c in range(ord("A"), ord("Z") + 1)},
    **{str(d): (ord(str(d)), ord(str(d))) for d in range(10)},
    **{f"F{n}": (281 + n, 0x6F + n) for n in range(1, 13)},
    "Space": (32, 0x20), "Esc": (27, 0x1B), "Tab": (9, 0x09), "Enter": (13, 0x0D), "Backspace": (8, 0x08),
    "Insert": (277, 0x2D), "Delete": (127, 0x2E), "Home": (278, 0x24), "End": (279, 0x23),
    "PageUp": (280, 0x21), "PageDown": (281, 0x22),
}
_BY_KIVY = {kivy_code: name for name, (kivy_code, _) in KEYS.items()}
_BY_VK = {vk: name for name, (_, vk) in KEYS.items()}
MODIFIERS = ("Ctrl", "Shift", "Alt")

# Playing without a controller: SF6's PC keyboard layout. Key codes are Kivy's.
GAME_KEYS = {
    273: "up", 274: "down", 275: "right", 276: "left",
    ord("w"): "up", ord("s"): "down", ord("d"): "right", ord("a"): "left",
    ord("u"): "u", ord("i"): "i", ord("o"): "o", ord("j"): "j", ord("k"): "k", ord("l"): "l",
}
ARROW_KEYS = (273, 274, 275, 276)  # These always play; the letters only while practising.
KEY_ACTIONS = {"u": "LP", "i": "MP", "o": "HP", "j": "LK", "k": "MK", "l": "HK"}
LOCKS = ("numlock", "capslock", "scrolllock")  # Come through as modifiers, but aren't keys held down.


def key_name(key, modifiers):
    """The name of a key pressed in the window ("Ctrl+O"), from Kivy's key code and modifiers; None
    for a key actions can't use (or a modifier on its own, or with the Windows key, which Windows
    keeps for itself)."""
    name = _BY_KIVY.get(key)
    if name is None or "meta" in modifiers:
        return None
    held = [m for m in MODIFIERS if m.lower() in modifiers]
    return "+".join(held + [name])


def _chord(name):
    """'Shift+F3' -> (frozenset({'Shift'}), 'F3')."""
    *modifiers, key = name.split("+")
    return frozenset(modifiers), key


def problem(kind, name):
    """Why a key can't be used as this kind of key (a sentence), or "" if it can."""
    modifiers, key = _chord(name)
    if key not in KEYS or not modifiers <= set(MODIFIERS):
        return f"{name} can't be used for an action"
    # A hotkey goes off wherever you are, so a plain key would fire as you type or play.
    if kind == HOTKEY and not (key.startswith("F") and len(key) > 1 or modifiers & {"Ctrl", "Alt"}):
        return "Hotkeys that work in game need an F key, Ctrl or Alt, so they don't go off while you type or play"
    return ""


class Bindings:
    """Each action's hotkey and shortcut: the defaults, with changes ({"hotkey.play": "F9"}, "" for
    no key) on top. Never changed in place: assign() makes a new one (the hotkey listener reads it
    from another thread)."""

    def __init__(self, changes=None):
        self.keys = {(kind, method): default for method, _, hotkey, shortcut in ACTIONS
                     for kind, default in ((HOTKEY, hotkey), (SHORTCUT, shortcut))}
        for spec, name in (changes or {}).items():
            kind, _, method = spec.partition(".")
            if (kind, method) in self.keys and (not name or not problem(kind, name)):
                self.keys[(kind, method)] = name
        self._methods = {(kind, _chord(name)): method for (kind, method), name in self.keys.items() if name}

    @classmethod
    def from_setting(cls, text):
        """From the "keys" setting: "hotkey.play=F9,shortcut.save=" (only the changes)."""
        pairs = (item.partition("=") for item in text.split(",") if "=" in item)
        return cls({spec.strip(): name.strip() for spec, _, name in pairs})

    def to_setting(self):
        defaults = Bindings().keys
        return ",".join(f"{kind}.{method}={name}" for (kind, method), name in self.keys.items()
                        if name != defaults[(kind, method)])

    def get(self, kind, method):
        return self.keys[(kind, method)]

    def owner(self, name):
        """The (kind, method) that has this key, or None. A hotkey also works in the window, so a key
        is only ever used once."""
        return next((slot for slot, key in self.keys.items() if key and _chord(key) == _chord(name)), None)

    def assign(self, kind, method, name):
        """A new Bindings with this key for the action ("" clears it). The key moves here from any
        action that had it. Returns (bindings, the (kind, method) it moved from or None)."""
        changes = {f"{k}.{m}": key for (k, m), key in self.keys.items()}
        moved = self.owner(name) if name else None
        if moved == (kind, method):
            moved = None
        if moved:
            changes[f"{moved[0]}.{moved[1]}"] = ""
        changes[f"{kind}.{method}"] = name
        return Bindings(changes), moved

    def method_for(self, kind, name):
        return self._methods.get((kind, _chord(name))) if name else None


current = Bindings()


def use(bindings):
    global current
    current = bindings


def hotkey(method):
    return current.get(HOTKEY, method)


def shortcut(method):
    return current.get(SHORTCUT, method)


def either(method, missing="no key"):
    """The key to mention for an action in the app's window: its shortcut, else its hotkey (which
    works there too), else missing."""
    return shortcut(method) or hotkey(method) or missing


class _KeyNames(dict):
    def __missing__(self, field):
        if field.startswith("hot_"):
            return hotkey(field[4:]) or "no key"
        return either(field)


def fill(text):
    """Text naming keys by action, with the keys in use: "{toggle_recording}" is the key to press in
    the window, "{hot_play}" the hotkey (in game)."""
    return text.format_map(_KeyNames())


def check_actions(app):
    """Raises if an action names a method the app doesn't have."""
    missing = [method for method, _, _, _ in ACTIONS if not callable(getattr(app, method, None))]
    if missing:
        raise AttributeError(f"Keys name app methods that don't exist: {missing}")


def window_shortcut(key, modifiers):
    """The app method for a key pressed in the window (its shortcut), or None."""
    name = key_name(key, [m for m in modifiers if m not in LOCKS])
    return current.method_for(SHORTCUT, name) if name else None


_MODIFIER_KEYS = {
    "Ctrl": {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r},
    "Shift": {keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r},
    "Alt": {keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr},
}


def listen_for_hotkeys(on_hotkey):
    """Starts a system-wide listener that calls on_hotkey(method name) for each hotkey pressed (as
    `current` has them when it's pressed), from the hook's thread: hand it to the UI thread, don't do
    the work there. Returns the listener (stop() it on exit)."""
    held = set()

    # Neither callback may return False: that stops the listener.
    def on_press(key):
        for name, modifier_keys in _MODIFIER_KEYS.items():
            if key in modifier_keys:
                held.add(key)
                return
        vk = key.value.vk if isinstance(key, keyboard.Key) else getattr(key, "vk", None)
        name = _BY_VK.get(vk)
        if name:
            modifiers = [m for m in MODIFIERS if held & _MODIFIER_KEYS[m]]
            method = current.method_for(HOTKEY, "+".join(modifiers + [name]))
            if method:
                on_hotkey(method)

    def on_release(key):
        held.discard(key)

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
