"""The playalong controller, driven tick by tick the way the 60 Hz sampler thread drives it."""
import unittest

from helpers import key_input, state, track

from key_inputs import HIT, MISS
from playalong import PlayalongController


def player(controller, inputs):
    """Plays a whole pass: one tick per frame, with inputs[frame] as the controller's state."""
    controller.play()
    for frame_state in inputs:
        controller.tick(frame_state)


class Practice(unittest.TestCase):
    def setUp(self):
        self.target = track((10, 5), (2, 5, "Y"), (10, 5))
        self.controller = PlayalongController()
        self.controller.set_lead_in(0)
        self.controller.set_input_track(self.target, key_inputs=[key_input(9, 12, buttons=["Y"])])

    def test_a_good_pass_is_scored_and_summed_up(self):
        player(self.controller, self.target)
        self.assertEqual(self.controller.key_input_score(), (1, 1))
        summary = self.controller.get_last_pass()
        self.assertEqual((summary["hits"], summary["total"], summary["streak"]), (1, 1, 1))
        self.assertFalse(self.controller.is_playing())  # Stopped at the end (not looping).

    def test_a_missed_pass_lists_the_problem(self):
        player(self.controller, track((22, 5)))
        self.assertEqual(self.controller.key_input_score(), (0, 1))
        self.assertEqual(self.controller.get_last_pass()["problems"], [("Y", MISS, 0)])

    def test_each_pass_is_kept_as_a_run(self):
        player(self.controller, self.target)
        player(self.controller, track((22, 5)))
        runs = self.controller.get_runs()
        self.assertEqual([run["id"] for run in runs], [1, 2])
        self.assertEqual(self.controller.get_last_pass()["best"], 1)

    def test_looping_starts_a_fresh_pass(self):
        self.controller.set_looping(True)
        player(self.controller, self.target + self.target[:3])  # Round once, and a little more.
        self.assertTrue(self.controller.is_playing())
        self.assertEqual(len(self.controller.get_runs()), 1)
        self.assertEqual(self.controller.get_current_frame(), 3)

    def test_the_lead_in_holds_the_playhead(self):
        self.controller.set_lead_in(5)
        self.controller.play()
        for _ in range(5):
            self.controller.tick(state())
        self.assertEqual(self.controller.get_current_frame(), 0)
        self.controller.tick(state())
        self.assertEqual(self.controller.get_current_frame(), 1)

    def test_judgements_come_as_inputs_settle(self):
        self.controller.play()
        for frame_state in self.target[:12]:
            self.controller.tick(frame_state)
        self.assertEqual([j[2] for j in self.controller.get_judgements()], [HIT])


class EditingKeyInputs(unittest.TestCase):
    def setUp(self):
        # Two key inputs: Y at 9-12 (hit) and B at 15-18 (missed).
        self.target = track((10, 5), (2, 5, "Y"), (4, 5), (2, 5, "B"), (5, 5))
        self.controller = PlayalongController()
        self.controller.set_lead_in(0)
        self.controller.set_input_track(self.target, key_inputs=[key_input(9, 12, buttons=["Y"]),
                                                                  key_input(15, 18, buttons=["B"])])
        player(self.controller, track((10, 5), (2, 5, "Y"), (11, 5)))

    def run_grades(self):
        row = self.controller.list_snapshot(len(self.target), len(self.target)).history[0]
        return [(start, grade) for start, _, grade, _ in row.grades]

    def test_a_runs_grades_follow_a_deleted_key_input(self):
        self.assertEqual(self.run_grades(), [(9, HIT), (15, MISS)])
        self.controller.remove_key_input(0)
        self.assertEqual(self.run_grades(), [(15, MISS)])  # Not the deleted one's HIT, shifted along.

    def test_verdicts_dont_outlive_the_key_inputs_they_name(self):
        self.assertTrue(self.controller.get_judgements())
        self.controller.set_key_input(None, key_input(1, 2, buttons=["X"]))  # Shifts every index.
        self.assertEqual(self.controller.get_judgements(), [])


class ButtonMapping(unittest.TestCase):
    def test_the_player_scores_with_their_own_buttons(self):
        target = track((10, 5), (2, 5, "Y"), (10, 5))
        controller = PlayalongController()
        controller.set_lead_in(0)
        controller.set_input_track(target, key_inputs=[key_input(9, 12, buttons=["Y"])], button_map={"Y": "LB",
                                                                                                    "LB": "Y"})
        player(controller, track((10, 5), (2, 5, "LB"), (10, 5)))  # The player presses their LB for Y.
        self.assertEqual(controller.key_input_score(), (1, 1))

    def test_a_map_must_be_one_to_one(self):
        with self.assertRaises(ValueError):
            PlayalongController().set_button_map({"X": "Y"})


class Recording(unittest.TestCase):
    def test_a_late_tick_repeats_the_last_frame_to_keep_time(self):
        controller = PlayalongController()
        controller.start_recording()
        controller.tick(state(2))
        controller.tick(state(6), ticks=3)  # The sampler ran two frames late.
        controller.stop_recording()
        self.assertEqual(controller.get_input_track(), [state(2), state(2), state(2), state(6)])
        self.assertEqual(controller.status().filled, 2)


class Encapsulation(unittest.TestCase):
    def test_the_controllers_state_is_private(self):
        """Everything goes through methods that take the lock; a public attribute would let callers
        read (or set) state behind it."""
        controller = PlayalongController()
        controller.set_input_track(track((5, 5)))
        self.assertEqual([name for name in vars(controller) if not name.startswith("_")], [])

    def test_status_is_one_consistent_view(self):
        controller = PlayalongController()
        controller.set_input_track(track((5, 5)), key_inputs=[key_input(1, 2, buttons=["Y"])])
        status = controller.status()
        self.assertEqual((status.length, status.key_inputs, status.hits, status.playing), (5, 1, 0, False))


class SavedAttempts(unittest.TestCase):
    def test_saving_keeps_the_attempt_on_screen(self):
        target = track((10, 5))
        controller = PlayalongController()
        controller.set_lead_in(0)
        controller.set_input_track(target)
        player(controller, track((10, 2)))
        saved = controller.save_attempt(name="Mine")
        self.assertEqual(saved["name"], "Mine")
        self.assertEqual(controller.get_saved()[0]["attempt"], track((10, 2)))


if __name__ == "__main__":
    unittest.main()
