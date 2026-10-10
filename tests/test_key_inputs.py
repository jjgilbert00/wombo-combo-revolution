"""Grading: what counts as doing a key input, and how a miss is graded early or late."""
import unittest

from helpers import key_input, state, track

from key_inputs import (EARLY, HIT, LATE, MISS, PENDING, best_hold, demo_track, derive, derive_hold, describe,
                        grade, grade_all, normalized, result)


class Presses(unittest.TestCase):
    def test_a_press_anywhere_in_the_window_is_a_hit(self):
        target = track((10, 5), (2, 5, "Y"), (10, 5))
        attempt = track((12, 5), (1, 5, "Y"), (9, 5))  # Pressed on frame 12, the window's last frame.
        self.assertEqual(result(key_input(10, 12, buttons=["Y"]), attempt, target), HIT)

    def test_a_button_held_from_before_the_window_does_not_count(self):
        target = track((20, 5, "Y"))
        attempt = track((20, 5, "Y"))  # Y is down the whole time: never newly pressed in the window.
        self.assertEqual(result(key_input(10, 12, buttons=["Y"]), attempt, target), MISS)

    def test_the_direction_held_with_the_press_matters(self):
        target = track((20, 2, "Y"))
        ki = key_input(10, 12, direction=2, buttons=["Y"])
        wrong = track((10, 5), (1, 5, "Y"), (9, 5))
        right = track((10, 5), (1, 2, "Y"), (9, 5))
        self.assertEqual(result(ki, wrong, target), MISS)
        self.assertEqual(result(ki, right, target), HIT)

    def test_unplayed_frames_leave_it_pending(self):
        target = track((20, 5))
        attempt = track((11, 5)) + [None] * 9  # Played up to frame 10; the window runs to 12.
        self.assertEqual(result(key_input(10, 12, buttons=["Y"]), attempt, target), PENDING)

    def test_a_motion_passes_through_its_directions_in_order(self):
        target = track((20, 5))
        ki = key_input(5, 15, motion=[2, 3, 6], buttons=["X"])
        done = track((6, 5), (2, 2), (1, 3), (1, 6, "X"), (10, 5))
        out_of_order = track((6, 5), (2, 6), (1, 3), (1, 2, "X"), (10, 5))
        self.assertEqual(result(ki, done, target), HIT)
        self.assertEqual(result(ki, out_of_order, target), MISS)


class ExactSpans(unittest.TestCase):
    def test_every_frame_must_match(self):
        target = track((5, 5), (3, 6), (5, 5))
        ki = key_input(5, 7, exact=True)
        self.assertEqual(result(ki, list(target), target), HIT)
        off_by_one = track((5, 5), (2, 6), (6, 5))
        self.assertEqual(result(ki, off_by_one, target), MISS)


class Holds(unittest.TestCase):
    def test_charge_accepts_any_down_direction(self):
        target = track((40, 5))
        ki = key_input(0, 39, direction=2, hold=30)
        down_back_then_down = track((15, 1), (15, 2), (10, 5))
        self.assertEqual(result(ki, down_back_then_down, target), HIT)

    def test_too_short_a_hold_misses(self):
        ki = key_input(0, 39, direction=2, hold=30)
        self.assertEqual(result(ki, track((20, 2), (20, 5)), track((40, 5))), MISS)

    def test_best_hold_is_the_longest_run_in_the_window(self):
        ki = key_input(0, 19, direction=2)
        self.assertEqual(best_hold(ki, track((3, 2), (2, 5), (8, 2), (7, 5))), (5, 8))


class EarlyAndLate(unittest.TestCase):
    def test_a_press_after_the_window_is_late_by_its_distance(self):
        target = track((30, 5))
        attempt = track((14, 5), (1, 5, "Y"), (15, 5))  # Window 10-12; pressed on 14.
        self.assertEqual(grade(key_input(10, 12, buttons=["Y"]), attempt, target), (LATE, 2))

    def test_a_press_before_the_window_is_early(self):
        target = track((30, 5))
        attempt = track((7, 5), (1, 5, "Y"), (22, 5))  # Window 10-12; pressed on 7.
        self.assertEqual(grade(key_input(10, 12, buttons=["Y"]), attempt, target), (EARLY, -3))

    def test_a_neighbours_input_is_not_counted_as_this_one_late(self):
        target = track((40, 5))
        first, second = key_input(10, 12, buttons=["Y"]), key_input(16, 18, buttons=["Y"])
        attempt = track((17, 5), (1, 5, "Y"), (22, 5))  # Only the second's press.
        grades = grade_all([first, second], attempt, target)
        self.assertEqual(grades[0], (MISS, 0))
        self.assertEqual(grades[1], (HIT, 0))


class Notation(unittest.TestCase):
    def test_describe(self):
        self.assertEqual(describe(key_input(0, 5, motion=[2, 3, 6], direction=6, buttons=["X"])), "236X")
        self.assertEqual(describe(key_input(0, 5, direction=2, buttons=["Y"])), "2Y")
        self.assertEqual(describe(key_input(0, 2, exact=True)), "EXACT 3f")
        self.assertEqual(describe(key_input(0, 50, direction=2, hold=45)), "[2] 45f")

    def test_old_saves_get_the_missing_fields(self):
        self.assertEqual(normalized({"start": 1, "end": 2})["hold"], 0)


class Deriving(unittest.TestCase):
    def test_derive_takes_the_first_press_and_the_motion_before_it(self):
        t = track((2, 5), (2, 2), (2, 3), (1, 6, "X"), (3, 5))
        derived = derive(t, 0, 9)
        self.assertEqual((derived["motion"], derived["direction"], derived["buttons"]), ([2, 3, 6], 6, ["X"]))

    def test_derive_hold_finds_the_longest_held_direction(self):
        t = track((5, 5), (30, 2), (5, 5))
        self.assertEqual(derive_hold(t, 0, 39), {"direction": 2, "buttons": [], "hold": 30})


class Demo(unittest.TestCase):
    def test_demo_track_does_only_what_is_required(self):
        target = track((10, 5), (5, 2, "Y"), (10, 5))  # A sloppy recording: Y held 5 frames.
        cleaned = demo_track([key_input(10, 14, direction=2, buttons=["Y"])], target)
        self.assertEqual(len(cleaned), len(target))
        self.assertEqual(cleaned[9], state(5))
        self.assertEqual(cleaned[10], state(2, "Y"))
        self.assertEqual(cleaned[14], state(5))  # Held only briefly, not the recording's 5 frames.
        self.assertEqual(result(key_input(10, 14, direction=2, buttons=["Y"]), cleaned, target), HIT)


if __name__ == "__main__":
    unittest.main()
