"""The input rules engine: STRICT is the old literal reading; a game's rules are more lenient in the
ways its pack says, layered by control scheme, character, recording and key input."""
import unittest

from helpers import key_input, state, track

import input_rules
from input_rules import STRICT, resolve
from key_inputs import HIT, MISS, derive, describe, explain, grade, result

GENERIC = resolve()  # The generic pack: any game without one.

# A small made-up game, to test direction classes and characters without depending on a real pack.
TEST_PACK = {
    "name": "Test game",
    "rules": [
        {"id": "neutral", "type": "neutral"},
        {"id": "simultaneous", "type": "multi_press", "window": 2},
        {"id": "crouching", "type": "direction_classes", "name": "Crouching normals", "classes": [[2, 1, 3]]},
        {"id": "standing", "type": "direction_classes", "name": "Standing normals", "classes": [[5, 4, 6]]},
        {"id": "dp", "type": "motion", "name": "623", "steps": [[6], [2, 1], [3]], "shortcuts": [[[3], [2], [3]]]},
        {"id": "qcf", "type": "motion", "name": "236", "steps": [[2], [3], [6]], "max_frames": 10},
    ],
    "characters": {
        "sweeper": {"name": "Sweeper"},
        "kicker": {"name": "Kicker", "except": [{"rule": "crouching", "direction": 3, "button": "B"}]},
    },
}


def game(character=None, **kwargs):
    return resolve(character=character, pack=TEST_PACK, **kwargs)


class Strict(unittest.TestCase):
    """STRICT is exactly how the app always read inputs."""

    def test_presses_need_the_exact_direction_and_neutral_means_any(self):
        self.assertEqual(STRICT.press_directions(2, ["B"])[0], {2})
        self.assertEqual(STRICT.press_directions(None, ["B"])[0], set(range(1, 10)))
        target = track((2, 5), (2, 5, "Y"), (2, 5))
        k = derive(target, 0, 5)
        self.assertIsNone(k["direction"])  # So 6Y counts too.
        self.assertEqual(result(k, track((2, 5), (2, 6, "Y"), (2, 5)), target), HIT)

    def test_motions_keep_every_direction_seen(self):
        target = track((1, 5), (1, 6), (1, 3), (1, 2), (1, 3), (2, 3, "RB"), (1, 5))
        self.assertEqual(describe(derive(target, 0, 7)), "6323RB")

    def test_asking_for_strict_gives_strict(self):
        self.assertIs(resolve(strict=True), STRICT)
        self.assertIs(resolve(recording={"strict": True}), STRICT)


class GenericRules(unittest.TestCase):
    """What holds whatever the game."""

    def test_neutral_is_neutral(self):
        target = track((2, 5), (2, 5, "Y"), (2, 5))
        k = derive(target, 0, 5, GENERIC)
        self.assertEqual(k["direction"], 5)
        self.assertEqual(describe(k), "5Y")
        self.assertEqual(result(k, track((2, 5), (2, 6, "Y"), (2, 5)), target, GENERIC), MISS)  # 6Y is another move.
        self.assertEqual(result(k, target, target, GENERIC), HIT)

    def test_buttons_pressed_a_frame_apart_are_one_press(self):
        target = track((2, 5), (1, 5, "Y"), (2, 5, "Y", "B"), (2, 5))
        k = derive(target, 0, 6, GENERIC)
        self.assertEqual(k["buttons"], ["Y", "B"])
        self.assertEqual(result(k, target, target, GENERIC), HIT)
        apart = track((2, 5), (4, 5, "Y"), (2, 5, "Y", "B"), (2, 5))
        self.assertEqual(result(k, apart, target, GENERIC), MISS)
        self.assertIn("4 frames apart; up to 2", explain(k, apart, target, GENERIC))

    def test_a_messy_dp_is_recognised_and_a_clean_one_counts(self):
        target = track((1, 5), (1, 6), (1, 3), (1, 2), (1, 3), (2, 3, "RB"), (1, 5))
        k = derive(target, 0, 7, GENERIC)
        self.assertEqual(describe(k), "623RB")
        clean = track((1, 5), (1, 6), (1, 2), (3, 3, "RB"), (1, 5))
        self.assertEqual(result(k, clean, target, GENERIC), HIT)

    def test_a_walk_before_a_fireball_isnt_part_of_it(self):
        target = track((1, 5), (2, 6), (1, 5), (1, 2), (1, 3), (1, 6), (2, 6, "X"), (1, 5))
        self.assertEqual(describe(derive(target, 0, 8, GENERIC)), "236X")

    def test_a_dp_pressed_at_down_forward_isnt_a_fireball(self):
        target = track((1, 5), (1, 6), (1, 2), (2, 3, "RB"), (1, 5))
        self.assertEqual(describe(derive(target, 0, 4, GENERIC)), "623RB")


class GameRules(unittest.TestCase):
    """Direction classes, characters' own moves, shortcuts and time limits, with a made-up game."""

    def test_any_down_direction_is_the_crouching_normal(self):
        rules = game("sweeper")
        target = track((2, 5), (2, 1, "B"), (2, 5))
        k = derive(target, 0, 5, rules)
        self.assertEqual(describe(k), "2B")  # Written as its class.
        for direction in (1, 2, 3):
            self.assertEqual(result(k, track((2, 5), (2, direction, "B"), (2, 5)), target, rules), HIT, direction)
        attempt = track((2, 5), (2, 3, "B"), (2, 5))
        self.assertEqual(explain(k, attempt, target, rules), "3B counted as 2B (Crouching normals)")

    def test_a_characters_own_move_stays_exact(self):
        rules = game("kicker")  # Kicker's 3B is a move of its own.
        sweep = derive(track((2, 5), (2, 2, "B"), (2, 5)), 0, 5, rules)
        self.assertEqual(result(sweep, track((2, 5), (2, 3, "B"), (2, 5)), track((4, 5)), rules), MISS)
        self.assertEqual(result(sweep, track((2, 5), (2, 1, "B"), (2, 5)), track((4, 5)), rules), HIT)
        own = derive(track((2, 5), (2, 3, "B"), (2, 5)), 0, 5, rules)
        self.assertEqual(describe(own), "3B")  # Not written as a sweep.
        self.assertEqual(result(own, track((2, 5), (2, 2, "B"), (2, 5)), track((4, 5)), rules), MISS)

    def test_without_a_character_nothing_that_could_be_another_move_counts(self):
        rules = game()  # Some character has a 3B of its own, so 3B isn't assumed to be the sweep.
        self.assertEqual(rules.press_directions(2, ["B"])[0], {1, 2})
        self.assertEqual(rules.press_directions(2, ["X"])[0], {1, 2, 3})

    def test_shortcuts_and_time_limits(self):
        rules = game("sweeper")
        k = key_input(0, 20, motion=[6, 2, 3], buttons=["RB"])
        shortcut = track((1, 3), (1, 2), (2, 3, "RB"), (17, 5))
        self.assertEqual(result(k, shortcut, shortcut, rules), HIT)
        self.assertIn("623 done as 3-2-3 (a shortcut)", explain(k, shortcut, shortcut, rules))
        fireball = key_input(0, 30, motion=[2, 3, 6], direction=6, buttons=["X"])
        slow = track((1, 2), (12, 3), (1, 6), (1, 6, "X"), (15, 5))
        self.assertEqual(result(fireball, slow, slow, STRICT), HIT)
        self.assertEqual(result(fireball, slow, slow, rules), MISS)  # Over its 10 frames.
        self.assertIn("too slow", explain(fireball, slow, slow, rules))

    def test_the_input_buffer(self):
        rules = game("sweeper", recording={"rules": [{"id": "buffer", "type": "buffer", "frames": 3}]})
        k = key_input(10, 12, buttons=["X"])
        early = track((8, 5), (2, 5, "X"), (6, 5))
        self.assertEqual(result(k, early, early, STRICT), MISS)
        self.assertEqual(result(k, early, early, rules), HIT)
        self.assertEqual(grade(k, early, early, rules=rules), (HIT, 0))
        self.assertIn("2 frames early, within the input buffer", explain(k, early, early, rules))

    def test_a_recording_can_switch_a_rule_off(self):
        rules = game("sweeper", recording={"rules": [{"id": "crouching", "enabled": False}]})
        self.assertEqual(rules.press_directions(2, ["B"])[0], {2})

    def test_a_key_input_can_narrow_or_go_strict(self):
        rules = game("sweeper")
        attempt = track((2, 5), (2, 3, "B"), (2, 5))
        k = dict(key_input(0, 5, direction=2, buttons=["B"]), accept={"directions": [2]})
        self.assertEqual(result(k, attempt, attempt, rules), MISS)
        k = dict(key_input(0, 5, direction=2, buttons=["B"]), accept={"strict": True})
        self.assertEqual(result(k, attempt, attempt, rules), MISS)
        self.assertEqual(explain(k, attempt, attempt, rules), "")


class Packs(unittest.TestCase):
    def test_a_game_without_a_pack_gets_the_generic_one(self):
        self.assertEqual(input_rules.load_pack("no-such-game")["name"], "Any game")
        self.assertEqual(resolve("no-such-game"), GENERIC)

    def test_every_pack_loads_and_its_motions_are_sound(self):
        import json
        import os

        for name in os.listdir(input_rules.PACKS):
            with open(os.path.join(input_rules.PACKS, name), encoding="utf-8") as f:
                pack = json.load(f)
            for character in [None, *pack.get("characters", {})]:
                rules = resolve(pack=pack, character=character)
                for motion in rules.motions:
                    self.assertTrue(all(step and all(d in range(1, 10) for d in step) for step in motion.steps), name)
                    # Done cleanly (each step's first direction; a charge held as long as it needs), it's
                    # recognised as a motion (another one may fit too: 360 also passes through 623).
                    first = [step[0] for step in motion.steps]
                    if motion.charge:
                        clean = [state(first[0])] * motion.charge.frames + [state(first[1], "X")]
                    else:
                        clean = [state(d) for d in first] + [state(first[-1], "X")]
                    found = input_rules.recognise_motion(clean, 0, len(clean) - 1, first[-1], rules)
                    self.assertIsNotNone(found, (name, motion.name))


if __name__ == "__main__":
    unittest.main()
