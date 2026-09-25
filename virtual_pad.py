"""A virtual Xbox 360 controller for demoing a recording in game.

Software can't press buttons on the player's own controller, but it can plug in a virtual one:
the ViGEmBus driver makes it look like a real Xbox controller to the game, and the vgamepad
package drives it. The game sees a second controller, which has to be the one controlling the
player's character for the demo to show up (see the user guide).

Directions go out on the D-pad, as recorded (numpad notation: 6 is right, whichever way the
character faces), buttons as buttons, and LT/RT fully pressed or released.
"""

import importlib

SETUP_HELP = ("Demo needs the vgamepad package and the ViGEmBus driver: run  pip install vgamepad  "
              "(it offers to install the driver if it's missing)")


class VirtualPadError(Exception):
    pass


class VirtualPad:
    def __init__(self):
        importlib.invalidate_caches()  # So a vgamepad installed while the app is running is found.
        try:
            import vgamepad
        except ImportError as e:
            raise VirtualPadError(SETUP_HELP) from e
        try:
            self._pad = vgamepad.VX360Gamepad()
        except Exception as e:
            raise VirtualPadError(f"Couldn't plug in the virtual controller ({e}). {SETUP_HELP}") from e
        buttons = vgamepad.XUSB_BUTTON
        self._buttons = {
            "A": buttons.XUSB_GAMEPAD_A, "B": buttons.XUSB_GAMEPAD_B, "X": buttons.XUSB_GAMEPAD_X,
            "Y": buttons.XUSB_GAMEPAD_Y, "LB": buttons.XUSB_GAMEPAD_LEFT_SHOULDER,
            "RB": buttons.XUSB_GAMEPAD_RIGHT_SHOULDER,
        }
        self._dpad = {
            "up": buttons.XUSB_GAMEPAD_DPAD_UP, "down": buttons.XUSB_GAMEPAD_DPAD_DOWN,
            "left": buttons.XUSB_GAMEPAD_DPAD_LEFT, "right": buttons.XUSB_GAMEPAD_DPAD_RIGHT,
        }
        self._last = object()  # Nothing sent yet, so the neutral state below goes out.
        self.send(None)

    def send(self, state):
        """Sets the controller to a recorded frame's state, or to neutral for None. Called once a
        frame from the sampler thread; unchanged frames aren't resent."""
        key = None if state is None else (state["direction"], tuple(sorted(b for b in state if b != "direction" and state[b])))
        if key == self._last or self._pad is None:
            return
        self._last = key
        pad = self._pad
        pad.reset()
        if state is not None:
            direction = state["direction"]
            for name, directions in (("up", (7, 8, 9)), ("down", (1, 2, 3)), ("left", (1, 4, 7)),
                                     ("right", (3, 6, 9))):
                if direction in directions:
                    pad.press_button(button=self._dpad[name])
            for name, button in self._buttons.items():
                if state.get(name):
                    pad.press_button(button=button)
            pad.left_trigger(value=255 if state.get("LT") else 0)
            pad.right_trigger(value=255 if state.get("RT") else 0)
        pad.update()

    def close(self):
        """Releases everything and unplugs the controller. Safe to call more than once."""
        try:
            self.send(None)
        finally:
            self._pad = None  # Dropping the last reference unplugs it.
