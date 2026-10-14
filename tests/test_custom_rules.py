"""The player's own input rules: their packs (for a game, its characters, or a game the app doesn't
know), a recording's own changes, a key input's own leniency, and the edits that make them."""
import json
import os
import shutil
import tempfile
import unittest

from helpers import key_input, track

import input_rules
import rule_edits
from games import GAMES
from input_rules import RECORDING, STRICT, YOURS, YOURS_CHARACTER, layered, resolve
from key_inputs import HIT, MISS, acceptance, derive, describe, result
from playalong import PlayalongController

LAYOUT = GAMES["sf6"]["default_layout"]
BUTTON = {action: button for button, action in LAYOUT.items()}


def press(direction, action, before=5, after=5):
    return track((before, 5), (2, direction, BUTTON[action]), (after, 5))


class UserPacks(unittest.TestCase):
    """The player's packs sit on top of the app's; a recording's changes on top of those."""

    def setUp(self):
        self.folder = tempfile.mkdtemp()
        input_rules.USER_PACKS = self.folder

    def tearDown(self):
        input_rules.USER_PACKS = None
        shutil.rmtree(self.folder)

    def save(self, key, pack):
        input_rules.save_user_pack(key, pack)

    def test_your_rules_change_a_games(self):
        self.save("sf6", {"rules": [{"id": "buffer", "frames": 6}]})
        self.assertEqual(resolve("sf6", character="ken", layout=LAYOUT).buffer, 6)
        self.assertEqual(layered("sf6", character="ken").origins["buffer"], [input_rules.BUILT_IN, YOURS])

    def test_a_built_in_exception_can_be_undone_for_a_character(self):
        # Say the pack were wrong about Ryu's 6MP: allowing it makes 6MP his standing MP again.
        self.save("sf6", {"characters": {"ryu": {"allow": [{"rule": "standing", "direction": 6, "button": "MP"}]}}})
        rules = resolve("sf6", character="ryu", layout=LAYOUT)
        standing = derive(press(5, "MP"), 0, 11, rules)
        self.assertEqual(result(standing, press(6, "MP"), press(5, "MP"), rules), HIT)

    def test_a_recording_can_add_a_move_of_its_own(self):
        rules = resolve("sf6", character="ken", layout=LAYOUT,
                        recording={"except": [{"rule": "crouching", "direction": 3, "button": "MK"}]})
        sweep = derive(press(2, "MK"), 0, 11, rules)
        self.assertEqual(result(sweep, press(3, "MK"), press(2, "MK"), rules), MISS)
        self.assertEqual(result(sweep, press(1, "MK"), press(2, "MK"), rules), HIT)

    def test_a_motion_you_add_isnt_lost_to_a_characters_motion_list(self):
        # Guile has no 236 in the pack; adding one for him reads his walk-and-press as one.
        motion = {"id": "my-236", "type": "motion", "name": "236", "steps": [[2], [3], [6]]}
        self.save("sf6", {"characters": {"guile": {"name": "Guile", "rules": [motion]}}})
        inputs = track((3, 5), (2, 6), (1, 2), (1, 3), (2, 6, BUTTON["LP"]), (3, 5))
        self.assertEqual(describe(derive(inputs, 0, 11, resolve("sf6", character="guile", layout=LAYOUT))),
                         "236" + BUTTON["LP"])
        self.save("sf6", {"rules": [motion]})  # For every character: Guile's list doesn't drop it.
        self.assertEqual(describe(derive(inputs, 0, 11, resolve("sf6", character="guile", layout=LAYOUT))),
                         "236" + BUTTON["LP"])

    def test_a_game_the_app_doesnt_know(self):
        self.save("my-game", {"name": "My Game", "custom": True,
                              "rules": [{"id": "buffer", "type": "buffer", "frames": 8},
                                        {"id": "my-41236", "type": "motion", "name": "41236",
                                         "steps": [[4], [1], [2], [3], [6]]}],
                              "characters": {"hero": {"name": "Hero",
                                                      "except": [{"rule": "crouching", "direction": 3, "button": "B"}]}}})
        self.assertEqual(input_rules.custom_rule_sets(), {"my-game": "My Game"})
        rules = resolve(None, character="hero", recording={"pack": "my-game"})
        self.assertEqual(rules.name, "My Game + Hero")
        self.assertEqual(rules.buffer, 8)
        self.assertEqual(rules.press_directions(3, ["B"])[0], {3})
        self.assertIsNotNone(rules.motion_named([4, 1, 2, 3, 6]))
        self.assertEqual(input_rules.pack_characters("my-game"), {"hero": "Hero"})

    def test_a_recording_carries_its_custom_rule_set(self):
        carried = {"name": "Their Game", "custom": True, "rules": [{"id": "buffer", "type": "buffer", "frames": 9}]}
        rules = resolve(None, recording={"pack": "their-game", "pack_data": carried})
        self.assertEqual((rules.name, rules.buffer), ("Their Game", 9))

    def test_unreadable_or_odd_files_are_ignored(self):
        with open(os.path.join(self.folder, "sf6.json"), "w") as f:
            f.write("{not json")
        with self.assertLogs("input_rules", "WARNING"):
            self.assertEqual(input_rules.load_user_pack("sf6"), {})
        self.assertEqual(input_rules.load_user_pack("../sf6"), {})
        with self.assertLogs("input_rules", "WARNING"):
            self.assertEqual(resolve("sf6", character="ken").buffer, 4)

    def test_an_empty_pack_is_removed(self):
        self.save("sf6", {"rules": [{"id": "buffer", "frames": 6}]})
        self.save("sf6", {"rules": []})
        self.assertFalse(os.path.exists(os.path.join(self.folder, "sf6.json")))

    def test_a_change_to_a_rule_that_isnt_there_changes_nothing(self):
        rules = resolve("sf6", character="guile", recording={"rules": [{"id": "qcf", "max_frames": 10}]})
        self.assertIsNone(rules.motion_named([2, 3, 6]))


class KeyInputLeniency(unittest.TestCase):
    """A key input's own changes, for when the rules are wrong about one input."""

    def test_simultaneous_window(self):
        rules = resolve("sf6", character="ken", layout=LAYOUT)
        k = key_input(0, 12, buttons=[BUTTON["MP"], BUTTON["MK"]])
        apart = track((3, 5), (4, 5, BUTTON["MP"]), (3, 5, BUTTON["MP"], BUTTON["MK"]), (5, 5))
        self.assertEqual(result(k, apart, apart, rules), MISS)
        self.assertEqual(result(dict(k, accept={"simultaneous": 4}), apart, apart, rules), HIT)

    def test_buffer_even_in_a_strict_recording(self):
        k = key_input(10, 12, buttons=["X"])
        early = track((4, 5), (2, 5, "X"), (10, 5))
        self.assertEqual(result(k, early, early, STRICT), MISS)
        self.assertEqual(result(dict(k, accept={"buffer": 6}), early, early, STRICT), HIT)

    def test_motion_time_limit(self):
        rules = resolve("sf6", character="ken", layout=LAYOUT)
        k = key_input(0, 30, motion=[2, 3, 6], buttons=[BUTTON["LP"]])
        slow = track((1, 2), (12, 3), (2, 6, BUTTON["LP"]), (15, 5))
        self.assertEqual(result(k, slow, slow, rules), HIT)
        self.assertEqual(result(dict(k, accept={"max_frames": 8}), slow, slow, rules), MISS)

    def test_charge(self):
        rules = resolve("sf6", character="guile", layout=LAYOUT)
        boom = track((2, 5), (30, 4), (2, 6, BUTTON["LP"]), (4, 5))
        k = dict(derive(track((2, 5), (50, 4), (2, 6, BUTTON["LP"]), (4, 5)), 40, 57, rules), start=20,
                 end=len(boom) - 1)
        self.assertEqual(result(k, boom, boom, rules), MISS)  # 45 frames needed.
        self.assertEqual(result(dict(k, accept={"charge": {"frames": 30, "keep": 10}}), boom, boom, rules), HIT)

    def test_acceptance_says_what_counts(self):
        rules = resolve("sf6", character="ken", layout=LAYOUT)
        k = key_input(0, 10, direction=2, buttons=[BUTTON["HK"]])
        accepts = acceptance(k, rules)
        self.assertEqual((accepts["directions"], accepts["group"], accepts["buffer"]), ([1, 2, 3], "Crouching normals", 4))
        narrowed = acceptance(dict(k, accept={"directions": [2], "buffer": 0}), rules)
        self.assertEqual((narrowed["directions"], narrowed["group"], narrowed["buffer"]), ([2], None, 0))
        self.assertTrue(acceptance(dict(k, accept={"strict": True}), rules)["strict"])


class Edits(unittest.TestCase):
    def test_changes_stay_minimal(self):
        layer = {}
        rule_edits.change_rule(layer, "buffer", frames=6)
        rule_edits.change_rule(layer, "buffer", enabled=False)
        self.assertEqual(layer, {"rules": [{"id": "buffer", "frames": 6, "enabled": False}]})
        rule_edits.remove_rule(layer, "buffer")
        self.assertEqual(layer, {})

    def test_exceptions_from_below_are_allowed_and_mine_removed(self):
        layer = {}
        rule_edits.add_exception(layer, "crouching", 3, "HK")
        rule_edits.add_exception(layer, "crouching", 3, "HK")
        self.assertEqual(layer, {"except": [{"rule": "crouching", "direction": 3, "button": "HK"}]})
        rule_edits.drop_exception(layer, "crouching", 3, "HK")
        self.assertEqual(layer, {})
        rule_edits.drop_exception(layer, "standing", 6, "MP")
        self.assertEqual(layer, {"allow": [{"rule": "standing", "direction": 6, "button": "MP"}]})
        rule_edits.add_exception(layer, "standing", 6, "MP")
        self.assertEqual(layer, {"except": [{"rule": "standing", "direction": 6, "button": "MP"}]})

    def test_steps_as_typed(self):
        self.assertEqual(rule_edits.parse_steps("236"), [[2], [3], [6]])
        self.assertEqual(rule_edits.parse_steps("6 21 3"), [[6], [2, 1], [3]])
        self.assertIsNone(rule_edits.parse_steps("2a6"))
        self.assertIsNone(rule_edits.parse_steps("6 22 3"))
        self.assertEqual(rule_edits.steps_text([[6], [2, 1], [3]]), "6 21 3")

    def test_new_rules_build(self):
        rules = {}
        made = [rule_edits.direction_group(rules, "Back", [4, 1, 7]),
                rule_edits.motion(rules, "Hcf", [[4], [1], [2], [3], [6]], [[[4], [2], [6]]], 20),
                rule_edits.charge_motion(rules, "Flash", [2, 1, 3], [8, 7, 9], 40, 10)]
        built = resolve(pack={"rules": made})
        self.assertEqual(built.press_directions(1, ["X"])[0], {4, 1, 7})
        self.assertEqual(built.motion_named([4, 1, 2, 3, 6]).max_frames, 20)
        self.assertEqual(built.motion_named([2, 8]).notation(), "[2]8")


class Session(unittest.TestCase):
    """Editing the open recording's rules, in each scope."""

    def setUp(self):
        self.folder = tempfile.mkdtemp()
        input_rules.USER_PACKS = self.folder
        self.controller = PlayalongController()
        self.controller.set_input_track(track((20, 5)))
        self.changed = 0
        self.session = rule_edits.RulesSession(self.controller, {"sf6": list(GAMES["sf6"]["actions"])},
                                               lambda: setattr(self, "changed", self.changed + 1))

    def tearDown(self):
        input_rules.USER_PACKS = None
        shutil.rmtree(self.folder)

    def test_recording_changes_are_the_recordings(self):
        self.controller.set_game("sf6")
        self.session.edit(RECORDING, lambda layer: rule_edits.change_rule(layer, "buffer", frames=7))
        self.assertEqual(self.controller.get_input_rules()[2].buffer, 7)
        self.assertEqual(self.controller.get_rule_changes(), {"rules": [{"id": "buffer", "frames": 7}]})
        self.assertEqual(self.changed, 1)
        self.assertEqual(os.listdir(self.folder), [])

    def test_your_rules_are_saved_for_every_recording(self):
        self.controller.set_game("sf6")
        self.controller.set_input_rules("ryu")
        self.assertEqual(self.session.scopes(), [RECORDING, YOURS, YOURS_CHARACTER])
        self.session.edit(YOURS_CHARACTER, lambda layer: rule_edits.drop_exception(layer, "standing", 6, "MP"))
        with open(os.path.join(self.folder, "sf6.json"), encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["characters"]["ryu"]["allow"], [{"rule": "standing", "direction": 6, "button": "MP"}])
        self.assertEqual(self.controller.get_input_rules()[2].press_directions(6, [BUTTON["MP"]])[0], {4, 5, 6})
        self.assertEqual(self.changed, 0)  # The recording itself didn't change.
        self.session.reset(YOURS)
        self.assertFalse(os.path.exists(os.path.join(self.folder, "sf6.json")))

    def test_a_new_rule_set_and_character_for_an_unknown_game(self):
        self.assertEqual(self.session.scopes(), [RECORDING])
        self.session.new_rule_set("Brawler EX")
        self.assertEqual(self.controller.get_rule_changes(), {"pack": "brawler-ex"})
        self.assertEqual(self.controller.get_input_rules()[2].name, "Brawler EX")
        self.session.new_character("Big Guy")
        self.assertEqual(self.session.character(), "big-guy")
        self.session.edit(YOURS_CHARACTER, lambda layer: rule_edits.add_exception(layer, "crouching", 3, "B"))
        self.assertEqual(self.controller.get_input_rules()[2].press_directions(3, ["B"])[0], {3})
        self.assertEqual(self.session.button_names()[:2], ["X", "Y"])  # No game: recorded buttons.
        self.session.use_rule_set(None)
        self.assertIsNone(self.session.character())
        self.assertEqual(self.controller.get_input_rules()[2].name, "Any game")


if __name__ == "__main__":
    unittest.main()
