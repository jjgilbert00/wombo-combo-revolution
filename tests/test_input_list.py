"""The input list's model: runs of held input, frame matching, button remapping and game actions."""
import unittest

from helpers import key_input, state, track

from games import to_actions
from button_map import full_map, inverse_map, map_key, map_key_input, map_state
from input_list import input_key, match_runs, runs_in_range


class Runs(unittest.TestCase):
    def test_runs_split_where_the_input_changes(self):
        t = track((3, 5), (2, 2, "Y"), (4, 5))
        self.assertEqual(runs_in_range(t, 0, 9), [(0, 3, (5, ())), (3, 2, (2, ("Y",))), (5, 4, (5, ()))])

    def test_a_run_is_followed_past_the_range_so_its_count_is_right(self):
        t = track((50, 2))
        self.assertEqual(runs_in_range(t, 20, 30), [(0, 50, (2, ()))])

    def test_unplayed_frames_are_skipped(self):
        t = [None, None] + track((3, 6))
        self.assertEqual(runs_in_range(t, 0, 5), [(2, 3, (6, ()))])

    def test_input_key_lists_buttons_in_display_order(self):
        self.assertEqual(input_key(state(6, "B", "X")), (6, ("X", "B")))


class Matching(unittest.TestCase):
    def test_match_runs_mark_matched_and_missed_frames(self):
        target = track((4, 2))
        attempt = track((2, 2), (2, 5))
        self.assertEqual(match_runs(target, attempt, 0, 4), [(0, 2, True), (2, 2, False)])


class ButtonMaps(unittest.TestCase):
    def test_a_map_covers_every_button(self):
        self.assertEqual(full_map({"X": "LB"})["LB"], "LB")
        self.assertEqual(inverse_map({"X": "LB", "LB": "X"})["LB"], "X")

    def test_states_keys_and_key_inputs_are_renamed(self):
        mapping = {"X": "LB", "LB": "X"}
        self.assertEqual(map_state(state(2, "X"), mapping), state(2, "LB"))
        self.assertEqual(map_key((2, ("X",)), mapping), (2, ("LB",)))
        self.assertEqual(map_key_input(key_input(0, 1, buttons=["X"]), mapping)["buttons"], ["LB"])
        self.assertIsNone(map_state(None, mapping))


class GameActions(unittest.TestCase):
    LAYOUT = {"X": "LP", "Y": "MP", "RB": "HP", "A": "LK", "B": "MK", "RT": "HK"}

    def test_single_buttons_are_their_actions(self):
        self.assertEqual(to_actions("sf6", self.LAYOUT, ["Y"]), ["MP"])

    def test_buttons_pressed_together_can_be_one_action(self):
        self.assertEqual(to_actions("sf6", self.LAYOUT, ["RB", "RT"]), ["DI"])
        self.assertEqual(to_actions("sf6", self.LAYOUT, ["Y", "B"]), ["DP"])

    def test_after_a_normal_parry_buttons_are_a_drive_rush_cancel(self):
        self.assertEqual(to_actions("sf6", self.LAYOUT, ["Y", "B"], after_normal=True), ["DRC"])


if __name__ == "__main__":
    unittest.main()
