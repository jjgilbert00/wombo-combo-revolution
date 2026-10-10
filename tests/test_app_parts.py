"""The parts split out of the app that don't need a window: the recording file, settings and keys."""
import ast
import json
import os
import tempfile
import unittest

from helpers import source, track

import keys
import track_file
from settings import DEFAULTS, Settings


class TrackFile(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.path = os.path.join(self.folder, "take.json")

    def write_raw(self, data):
        with open(self.path, "w") as f:
            json.dump(data, f)

    def test_a_saved_recording_loads_back(self):
        notes = [{"start": 1, "end": 2, "text": "hi"}]
        track_file.save(self.path, {"inputs": track((3, 2)), "notes": notes, "key_inputs": [], "attempt": None})
        data = track_file.load(self.path)
        self.assertEqual((data["inputs"], data["notes"], data["version"]), (track((3, 2)), notes, track_file.VERSION))
        self.assertNotIn("key_inputs", data)  # Empty parts are left out.

    def test_the_oldest_saves_are_a_bare_list_of_frames(self):
        self.write_raw(track((2, 6)))
        self.assertEqual(track_file.load(self.path)["inputs"], track((2, 6)))

    def test_a_newer_format_is_refused(self):
        self.write_raw({"version": track_file.VERSION + 1, "inputs": []})
        with self.assertRaises(track_file.TrackFileError):
            track_file.load(self.path)

    def test_something_else_is_refused(self):
        self.write_raw({"hello": 1})
        with self.assertRaises(track_file.TrackFileError):
            track_file.load(self.path)

    def test_update_keeps_the_rest(self):
        track_file.save(self.path, {"inputs": track((2, 5)), "notes": [{"start": 0, "end": 0, "text": "n"}]})
        track_file.update(self.path, saved_attempts=[{"name": "a"}])
        data = track_file.load(self.path)
        self.assertEqual((len(data["notes"]), data["saved_attempts"]), (1, [{"name": "a"}]))


class FakeConfig(dict):
    def get(self, section, name):
        return self[name]

    def getint(self, section, name):
        return int(self[name])

    def getfloat(self, section, name):
        return float(self[name])

    def getboolean(self, section, name):
        return str(self[name]) in ("1", "True", "true")

    def set(self, section, name, value):
        self[name] = str(value)


class SettingsAccess(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(FakeConfig({name: str(value) for name, value in Settings.defaults().items()}))

    def test_settings_come_back_as_their_defaults_type(self):
        self.assertIs(self.settings.loop, True)
        self.assertEqual(self.settings.lookahead, 1.5)
        self.assertEqual(self.settings.lead_in, 60)

    def test_an_unknown_name_is_an_error(self):
        with self.assertRaises(AttributeError):
            self.settings.lokahead
        with self.assertRaises(AttributeError):
            self.settings.set("lokahead", 2)

    def test_toggle(self):
        self.assertIs(self.settings.toggle("loop"), False)
        self.assertIs(self.settings.loop, False)

    def test_the_lanes_default_lists_every_lane(self):
        lanes_layout = source("layouts", "input_list_layout.py")
        for lane in DEFAULTS["lanes"][0].split(","):
            self.assertIn(f'"{lane}":', lanes_layout)


class Keys(unittest.TestCase):
    def test_every_key_names_a_method_the_app_has(self):
        tree = ast.parse(source("main.py"))
        app = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "WomboComboApp")
        methods = {node.name for node in app.body if isinstance(node, ast.FunctionDef)}
        named = [method for method, _, _, _ in keys.ACTIONS]
        self.assertEqual([m for m in named if m not in methods], [])

    def tearDown(self):
        keys.use(keys.Bindings())

    def test_window_shortcuts(self):
        self.assertEqual(keys.window_shortcut(32, []), "toggle_playback")
        self.assertEqual(keys.window_shortcut(115, ["ctrl"]), "save")
        self.assertEqual(keys.window_shortcut(115, ["numlock"]), "save_attempt")  # Locks aren't modifiers.
        self.assertIsNone(keys.window_shortcut(115, ["shift"]))
        self.assertIsNone(keys.window_shortcut(282, []))  # F1 is a hotkey: the listener has it.

    def test_the_defaults_use_each_key_once_and_are_all_allowed(self):
        names = [name for name in keys.Bindings().keys.values() if name]
        self.assertEqual(len(names), len(set(names)))
        for (kind, method), name in keys.Bindings().keys.items():
            if name:
                self.assertEqual(keys.problem(kind, name), "", (kind, method, name))

    def test_key_names(self):
        self.assertEqual(keys.key_name(111, ["ctrl"]), "Ctrl+O")
        self.assertEqual(keys.key_name(284, ["shift", "ctrl"]), "Ctrl+Shift+F3")
        self.assertEqual(keys.key_name(27, []), "Esc")
        self.assertIsNone(keys.key_name(304, ["shift"]))  # Shift on its own.
        self.assertIsNone(keys.key_name(273, []))  # The arrows play the game.

    def test_hotkeys_need_an_f_key_ctrl_or_alt(self):
        self.assertEqual(keys.problem(keys.HOTKEY, "Ctrl+P"), "")
        self.assertEqual(keys.problem(keys.HOTKEY, "Shift+F9"), "")
        self.assertNotEqual(keys.problem(keys.HOTKEY, "P"), "")  # Would go off while typing or playing.
        self.assertNotEqual(keys.problem(keys.HOTKEY, "Shift+F"), "")
        self.assertEqual(keys.problem(keys.SHORTCUT, "P"), "")

    def test_a_key_moves_from_the_action_that_had_it(self):
        bindings, moved = keys.Bindings().assign(keys.SHORTCUT, "add_note", "K")
        self.assertEqual(moved, (keys.SHORTCUT, "mark_key_input"))
        self.assertEqual(bindings.get(keys.SHORTCUT, "add_note"), "K")
        self.assertEqual(bindings.get(keys.SHORTCUT, "mark_key_input"), "")
        # A hotkey also works in the window, so a shortcut can't have the same key.
        bindings, moved = keys.Bindings().assign(keys.SHORTCUT, "save", "F4")
        self.assertEqual(moved, (keys.HOTKEY, "toggle_practice"))
        self.assertIsNone(bindings.method_for(keys.HOTKEY, "F4"))

    def test_changes_are_kept_as_a_setting(self):
        bindings, _ = keys.Bindings().assign(keys.HOTKEY, "play", "Ctrl+Alt+P")
        bindings, _ = bindings.assign(keys.SHORTCUT, "save", "")
        text = bindings.to_setting()
        self.assertEqual(text, "hotkey.play=Ctrl+Alt+P,shortcut.save=")
        again = keys.Bindings.from_setting(text)
        self.assertEqual(again.keys, bindings.keys)
        keys.use(again)
        self.assertIsNone(keys.window_shortcut(115, ["ctrl"]))
        self.assertEqual(keys.fill("{hot_play} / {save} / {open_track}"), "Ctrl+Alt+P / no key / Ctrl+O")
        self.assertEqual(keys.Bindings.from_setting("").keys, keys.Bindings().keys)

    def test_a_bad_setting_is_ignored(self):
        bindings = keys.Bindings.from_setting("hotkey.play=P,shortcut.nothing=X,junk,shortcut.save=Numpad9")
        self.assertEqual(bindings.keys, keys.Bindings().keys)

    def test_the_keyboard_plays_as_a_controller(self):
        layout = {"X": "LP", "Y": "MP", "RB": "HP", "A": "LK", "B": "MK", "RT": "HK"}
        self.assertEqual(keys.keyboard_state({"down", "i"}, layout, {}), {"direction": 2, "Y": 1})
        self.assertEqual(keys.keyboard_state({"i"}, layout, {"Y": "LB", "LB": "Y"}), {"direction": 5, "LB": 1})
        self.assertIsNone(keys.keyboard_state(set(), layout, {}))


if __name__ == "__main__":
    unittest.main()
