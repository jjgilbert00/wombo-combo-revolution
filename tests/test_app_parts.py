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
        named = [method for _, _, method in keys.HOTKEYS + keys.WINDOW_KEYS]
        self.assertEqual([m for m in named if m not in methods], [])

    def test_window_shortcuts(self):
        self.assertEqual(keys.window_shortcut(keys.SPACE, " ", []), "toggle_playback")
        self.assertEqual(keys.window_shortcut(115, "s", ["ctrl"]), "save")
        self.assertEqual(keys.window_shortcut(115, "s", ["numlock"]), "save_attempt")  # Locks aren't modifiers.
        self.assertIsNone(keys.window_shortcut(115, "s", ["shift"]))

    def test_the_keyboard_plays_as_a_controller(self):
        layout = {"X": "LP", "Y": "MP", "RB": "HP", "A": "LK", "B": "MK", "RT": "HK"}
        self.assertEqual(keys.keyboard_state({"down", "i"}, layout, {}), {"direction": 2, "Y": 1})
        self.assertEqual(keys.keyboard_state({"i"}, layout, {"Y": "LB", "LB": "Y"}), {"direction": 5, "LB": 1})
        self.assertIsNone(keys.keyboard_state(set(), layout, {}))


if __name__ == "__main__":
    unittest.main()
