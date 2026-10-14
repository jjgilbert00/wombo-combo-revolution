"""Facing (playing from either side of the screen) and reading controllers other than Xbox pads."""
import unittest
from types import SimpleNamespace
from unittest import mock

from helpers import key_input, state, track

import controller
import facing
from key_inputs import HIT
from playalong import PlayalongController


class Mirroring(unittest.TestCase):
    def test_left_and_right_swap_and_up_and_down_stay(self):
        self.assertEqual([facing.mirror_direction(d) for d in range(1, 10)], [3, 2, 1, 6, 5, 4, 9, 8, 7])
        self.assertIsNone(facing.mirror_state(None))  # Unplayed frames stay unplayed.
        self.assertEqual(facing.mirror_key_input(key_input(0, 5, motion=[2, 3, 6], direction=6, buttons=["X"])),
                         key_input(0, 5, motion=[2, 1, 4], direction=4, buttons=["X"]))
        self.assertIsNone(facing.mirror_key_input(key_input(0, 5))["direction"])  # "Any" stays "any".


class PlayingFromTheRightSide(unittest.TestCase):
    """Recordings face right; a player on the right side does everything mirrored."""

    def setUp(self):
        # A fireball, written the usual way: 236 + X.
        self.fireball = track((5, 5), (2, 2), (2, 3), (2, 6, "X"), (5, 5))
        self.controller = PlayalongController()
        self.controller.set_lead_in(0)
        self.controller.set_input_track(self.fireball, key_inputs=[key_input(4, 10, motion=[2, 3, 6], buttons=["X"])])

    def play(self, inputs):
        self.controller.play()
        for frame_state in inputs:
            self.controller.tick(frame_state)

    def test_doing_it_facing_left_counts(self):
        self.controller.set_side(facing.RIGHT)
        self.play(facing.mirror_track(self.fireball))  # 214 + X on the stick: forward is left.
        self.assertEqual(self.controller.key_input_score(), (1, 1))
        self.assertEqual(self.controller.get_attempt_track()[9]["direction"], 6)  # Kept facing right.

    def test_the_same_motion_from_the_left_side_doesnt_count_from_the_right(self):
        self.controller.set_side(facing.RIGHT)
        self.play(self.fireball)  # 236 on the stick, from the right side: a backward motion.
        self.assertEqual(self.controller.key_input_score(), (0, 1))

    def test_a_recording_made_from_the_right_side_is_kept_facing_right(self):
        recorder = PlayalongController()
        recorder.set_side(facing.RIGHT)
        recorder.start_recording()
        for frame_state in facing.mirror_track(self.fireball):
            recorder.tick(frame_state)
        recorder.stop_recording()
        self.assertEqual(recorder.get_input_track(), self.fireball)

    def test_demos_go_out_mirrored_to_the_right_side(self):
        sent = []
        self.controller.set_side(facing.RIGHT)
        self.controller.start_demo(self.fireball, sent.append, countdown=0, kind="recording")
        for _ in self.fireball:
            self.controller.tick(state())
        self.assertEqual([s["direction"] for s in sent if s][:9], [5, 5, 5, 5, 5, 2, 2, 1, 1])
        self.assertEqual(sent[9]["direction"], 4)  # Forward, for a character facing left.


class FlippingARecording(unittest.TestCase):
    def test_everything_made_for_it_flips_with_it(self):
        backwards = track((3, 5), (2, 2), (2, 1), (2, 4, "X"), (3, 5))  # Recorded from the right side.
        controller = PlayalongController()
        controller.set_lead_in(0)
        controller.set_input_track(backwards, key_inputs=[key_input(3, 9, motion=[2, 1, 4], buttons=["X"])],
                                   saved_attempts=[{"name": "Mine", "attempt": backwards, "shown": True}])
        controller.flip_recording()
        self.assertEqual([s["direction"] for s in controller.get_input_track()], [5, 5, 5, 2, 2, 3, 3, 6, 6, 5, 5, 5])
        self.assertEqual(controller.get_key_inputs()[0]["motion"], [2, 3, 6])
        self.assertEqual(controller.get_saved()[0]["attempt"], controller.get_input_track())
        controller.play()
        for frame_state in controller.get_input_track():
            controller.tick(frame_state)
        self.assertEqual([j[2] for j in controller.get_judgements()], [HIT])


class FakePad:
    """Stands in for pygame's SDL Controller: buttons and axes by SDL's constants."""

    def __init__(self, buttons=(), axes=None, attached=True):
        self.name = "PS5 Controller"
        self.buttons, self.axes, self._attached = set(buttons), dict(axes or {}), attached

    def attached(self):
        return self._attached

    def get_button(self, button):
        return button in self.buttons

    def get_axis(self, axis):
        return self.axes.get(axis, 0)


class GameControllers(unittest.TestCase):
    """PlayStation pads and others SDL knows, read as Xbox-style pads."""

    def setUp(self):
        import pygame

        self.pg = pygame
        self.sdl = SimpleNamespace(update=mock.Mock())

    def read(self, pad):
        return controller.GameControllerReader(pad, self.sdl).poll()

    def test_face_buttons_and_shoulders_by_position(self):
        pg = self.pg
        pad = FakePad([pg.CONTROLLER_BUTTON_A, pg.CONTROLLER_BUTTON_X, pg.CONTROLLER_BUTTON_RIGHTSHOULDER],
                      {pg.CONTROLLER_AXIS_TRIGGERLEFT: 30000, pg.CONTROLLER_AXIS_TRIGGERRIGHT: 9000})
        result = self.read(pad)
        self.assertEqual({b for b in ("A", "B", "X", "Y", "LB", "RB", "LT", "RT") if result[b]}, {"A", "X", "RB", "LT"})
        self.sdl.update.assert_called()  # Read from the device on the sampler thread, not a stale copy.

    def test_the_dpad_and_then_the_stick_give_the_direction(self):
        pg = self.pg
        self.assertEqual(self.read(FakePad([pg.CONTROLLER_BUTTON_DPAD_DOWN, pg.CONTROLLER_BUTTON_DPAD_RIGHT]))["direction"], 3)
        # SDL's stick y is positive downward: down on the stick is 2.
        self.assertEqual(self.read(FakePad(axes={pg.CONTROLLER_AXIS_LEFTY: 32767}))["direction"], 2)
        self.assertEqual(self.read(FakePad(axes={pg.CONTROLLER_AXIS_LEFTX: -32768}))["direction"], 4)
        self.assertEqual(self.read(FakePad(axes={pg.CONTROLLER_AXIS_LEFTX: 9000}))["direction"], 5)  # Dead zone.
        # Left and right together cancel out, as on an XInput pad.
        self.assertEqual(self.read(FakePad([pg.CONTROLLER_BUTTON_DPAD_LEFT, pg.CONTROLLER_BUTTON_DPAD_RIGHT]))["direction"], 5)

    def test_start_and_back_and_unplugging(self):
        reader = controller.GameControllerReader(FakePad([self.pg.CONTROLLER_BUTTON_START]), self.sdl)
        reader.poll()
        self.assertEqual(reader.menu, (True, False))
        reader.pad = FakePad(attached=False)
        self.assertIsNone(reader.poll())
        self.assertFalse(reader.connected)


class FakeJoystick:
    def __init__(self, buttons=(), hat=None, axes=()):
        self.buttons, self.hat, self.axes = set(buttons), hat, list(axes)

    def init(self):
        pass

    def get_name(self):
        return "Arcade Stick"

    def get_numbuttons(self):
        return 8

    def get_button(self, index):
        return index in self.buttons

    def get_numhats(self):
        return 0 if self.hat is None else 1

    def get_hat(self, index):
        return self.hat

    def get_numaxes(self):
        return len(self.axes)

    def get_axis(self, index):
        return self.axes[index]


class RawJoysticks(unittest.TestCase):
    """Controllers SDL doesn't know: a hat, or a stick (a fight stick in left-stick mode)."""

    def read(self, joystick):
        return controller.RawJoystickReader(joystick, None).poll()

    def test_the_hat_gives_the_direction(self):
        self.assertEqual(self.read(FakeJoystick(hat=(1, 1)))["direction"], 9)

    def test_without_a_hat_the_stick_does(self):
        self.assertEqual(self.read(FakeJoystick(axes=[0.0, 1.0]))["direction"], 2)  # Down is + on a joystick.
        self.assertEqual(self.read(FakeJoystick(hat=(0, 0), axes=[1.0, -1.0]))["direction"], 9)

    def test_triggers_only_when_there_are_trigger_axes(self):
        self.assertEqual(self.read(FakeJoystick(axes=[0, 0, 0, 0, 1.0, -1.0]))["LT"], 1)
        self.assertEqual(self.read(FakeJoystick(axes=[0, 0, 0, 0]))["LT"], 0)  # Axis 4 isn't there.


class FindingControllers(unittest.TestCase):
    def test_known_controllers_get_the_sdl_reader_and_xbox_pads_are_left_to_xinput(self):
        import pygame

        names = {0: "PS5 Controller", 1: "Xbox Series X Controller", 2: "Arcade Stick"}
        fake_sdl = SimpleNamespace(
            get_init=lambda: True, init=lambda: None, update=lambda: None,
            is_controller=lambda index: index in (0, 1), name_forindex=names.get,
            Controller=lambda index: FakePad(),
        )
        with mock.patch.object(controller, "_sdl", return_value=fake_sdl), \
                mock.patch.object(controller.XInputReader, "connected_slots", return_value=[]), \
                mock.patch.object(controller, "_xinput", True), \
                mock.patch.object(pygame.joystick, "get_count", return_value=3), \
                mock.patch.object(pygame.joystick, "Joystick", side_effect=lambda index: FakeJoystick()):
            readers = controller.find_controllers()
        self.assertEqual([type(r).__name__ for r in readers], ["GameControllerReader", "RawJoystickReader"])


if __name__ == "__main__":
    unittest.main()
