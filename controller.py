import ctypes
import math
import sys


def get_neutral_controller_state():
    return {
        "direction": 5,
        "A": 0,
        "B": 0,
        "X": 0,
        "Y": 0,
        "RT": 0,
        "RB": 0,
        "LT": 0,
        "LB": 0,
    }


def direction_from_axes(x, y):
    """Numpad notation from x/y in -1..1 (y up). Opposing inputs cancel out (SOCD neutral)."""
    dirmap = [[1, 4, 7], [2, 5, 8], [3, 6, 9]]
    return dirmap[x + 1][y + 1]


# Numpad directions for 45 degree stick sectors, counter-clockwise starting at "right".
STICK_SECTORS = [6, 9, 8, 7, 4, 1, 2, 3]
STICK_DEADZONE = 0.5


def direction_from_stick(x, y):
    if math.hypot(x, y) < STICK_DEADZONE:
        return 5
    angle = math.degrees(math.atan2(y, x)) % 360
    return STICK_SECTORS[int((angle + 22.5) // 45) % 8]


class _XInputGamepad(ctypes.Structure):
    _fields_ = [
        ("wButtons", ctypes.c_ushort),
        ("bLeftTrigger", ctypes.c_ubyte),
        ("bRightTrigger", ctypes.c_ubyte),
        ("sThumbLX", ctypes.c_short),
        ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short),
        ("sThumbRY", ctypes.c_short),
    ]


class _XInputState(ctypes.Structure):
    _fields_ = [("dwPacketNumber", ctypes.c_ulong), ("Gamepad", _XInputGamepad)]


def _load_xinput():
    if sys.platform != "win32":
        return None
    for dll in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
        try:
            return ctypes.WinDLL(dll)
        except OSError:
            continue
    return None


_xinput = _load_xinput()


class XInputReader:
    """Reads an XInput (Xbox-style) controller directly.

    XInputGetState is thread safe and takes a few microseconds, so this can be polled from the
    sampler thread at exactly the moment a frame is due. Other controllers go through SDL
    (GameControllerReader, RawJoystickReader), which reads their state from the device on each poll.
    """

    DPAD_UP, DPAD_DOWN, DPAD_LEFT, DPAD_RIGHT = 0x0001, 0x0002, 0x0004, 0x0008
    START, BACK = 0x0010, 0x0020
    BUTTON_MASKS = {"LB": 0x0100, "RB": 0x0200, "A": 0x1000, "B": 0x2000, "X": 0x4000, "Y": 0x8000}
    TRIGGER_THRESHOLD = 128

    def __init__(self, slot):
        self.slot = slot
        self.name = f"XInput controller {slot + 1}"
        self.connected = True
        self.menu = (False, False)  # Start and Back as last polled; not part of the recorded state.
        self._state = _XInputState()

    @staticmethod
    def connected_slots():
        # Polling an empty slot is comparatively slow, so only do this from the UI thread.
        if not _xinput:
            return []
        state = _XInputState()
        return [slot for slot in range(4) if _xinput.XInputGetState(slot, ctypes.byref(state)) == 0]

    def poll(self):
        if _xinput.XInputGetState(self.slot, ctypes.byref(self._state)) != 0:
            self.connected = False
            return None
        self.connected = True
        pad = self._state.Gamepad
        buttons = pad.wButtons
        self.menu = (bool(buttons & self.START), bool(buttons & self.BACK))
        x = bool(buttons & self.DPAD_RIGHT) - bool(buttons & self.DPAD_LEFT)
        y = bool(buttons & self.DPAD_UP) - bool(buttons & self.DPAD_DOWN)
        direction = direction_from_axes(x, y)
        if direction == 5:
            direction = direction_from_stick(pad.sThumbLX / 32767, pad.sThumbLY / 32767)
        state = {name: int(bool(buttons & mask)) for name, mask in self.BUTTON_MASKS.items()}
        state["direction"] = direction
        state["LT"] = int(pad.bLeftTrigger >= self.TRIGGER_THRESHOLD)
        state["RT"] = int(pad.bRightTrigger >= self.TRIGGER_THRESHOLD)
        return state


def _sdl():
    """pygame's SDL GameController module, set up (None without pygame)."""
    try:
        import pygame
        from pygame._sdl2 import controller as sdl_controller
    except ImportError:
        return None
    if not pygame.joystick.get_init():
        pygame.joystick.init()
    if not sdl_controller.get_init():
        sdl_controller.init()
    return sdl_controller


def _refresh(sdl_controller):
    """Reads every controller's state from the device now. Without this, SDL only updates it when
    something pumps its events (the UI thread), so samples could be a UI frame stale."""
    sdl_controller.update()


class GameControllerReader:
    """Any controller SDL knows the layout of: PlayStation and Switch pads, and most fight sticks and
    third-party pads. SDL's GameController interface lays each one out like an Xbox pad, so its
    buttons are recorded under the same names as an Xbox pad's, by position: Cross is A, Circle B,
    Square X, Triangle Y, L1 LB, R1 RB, L2 LT, R2 RT. The D-pad, or else the left stick, gives the
    direction, as for XInput."""

    TRIGGER_THRESHOLD = 16384  # Half pressed (triggers read 0 to 32767).

    def __init__(self, pad, sdl_controller):
        import pygame

        self.pad = pad
        self._sdl = sdl_controller
        self.name = f"{pad.name} (SDL)"
        self.connected = True
        self.menu = (False, False)
        self._buttons = {"A": pygame.CONTROLLER_BUTTON_A, "B": pygame.CONTROLLER_BUTTON_B,
                         "X": pygame.CONTROLLER_BUTTON_X, "Y": pygame.CONTROLLER_BUTTON_Y,
                         "LB": pygame.CONTROLLER_BUTTON_LEFTSHOULDER, "RB": pygame.CONTROLLER_BUTTON_RIGHTSHOULDER}
        self._dpad = (pygame.CONTROLLER_BUTTON_DPAD_LEFT, pygame.CONTROLLER_BUTTON_DPAD_RIGHT,
                      pygame.CONTROLLER_BUTTON_DPAD_DOWN, pygame.CONTROLLER_BUTTON_DPAD_UP)
        self._menu = (pygame.CONTROLLER_BUTTON_START, pygame.CONTROLLER_BUTTON_BACK)
        self._axes = (pygame.CONTROLLER_AXIS_LEFTX, pygame.CONTROLLER_AXIS_LEFTY,
                      pygame.CONTROLLER_AXIS_TRIGGERLEFT, pygame.CONTROLLER_AXIS_TRIGGERRIGHT)

    def poll(self):
        try:
            _refresh(self._sdl)
            if not self.pad.attached():
                self.connected = False
                return None
            button = lambda b: int(bool(self.pad.get_button(b)))
            left, right, down, up = (button(b) for b in self._dpad)
            direction = direction_from_axes(right - left, up - down)
            stick_x, stick_y, trigger_l, trigger_r = (self.pad.get_axis(a) for a in self._axes)
            if direction == 5:
                direction = direction_from_stick(stick_x / 32767, -stick_y / 32767)  # SDL's y is down.
            self.menu = tuple(bool(button(b)) for b in self._menu)
            state = {name: button(b) for name, b in self._buttons.items()}
            state["direction"] = direction
            state["LT"] = int(trigger_l >= self.TRIGGER_THRESHOLD)
            state["RT"] = int(trigger_r >= self.TRIGGER_THRESHOLD)
            self.connected = True
            return state
        except Exception:
            self.connected = False
            return None


class RawJoystickReader:
    """A controller SDL doesn't know the layout of: read as a plain joystick. The direction comes
    from its hat (D-pad), or else its first two axes (a stick, or a fight stick in left-stick mode).
    Buttons are guessed in the usual order (A, B, X, Y, LB, RB); if they come out wrong, Edit > Remap
    buttons fixes a recording."""

    def __init__(self, joystick, sdl_controller):
        self.joystick = joystick
        self.joystick.init()
        self._sdl = sdl_controller
        self.name = f"{joystick.get_name()} (joystick: buttons may need remapping)"
        self.connected = True
        self.menu = (False, False)

    def poll(self):
        try:
            if self._sdl:
                _refresh(self._sdl)
            joystick = self.joystick
            count, axes = joystick.get_numbuttons(), joystick.get_numaxes()
            button = lambda index: int(bool(joystick.get_button(index))) if index < count else 0
            self.menu = (bool(button(7)), bool(button(6)))
            hat = joystick.get_hat(0) if joystick.get_numhats() else (0, 0)
            direction = direction_from_axes(hat[0], hat[1])
            if direction == 5 and axes >= 2:
                direction = direction_from_stick(joystick.get_axis(0), -joystick.get_axis(1))  # Down is +.
            trigger = lambda index: int(joystick.get_axis(index) > 0) if axes > index else 0  # Rest at -1.
            return {
                "direction": direction,
                "A": button(0), "B": button(1), "X": button(2), "Y": button(3),
                "LB": button(4), "RB": button(5),
                "LT": trigger(4) if axes >= 6 else 0,
                "RT": trigger(5) if axes >= 6 else 0,
            }
        except Exception:
            self.connected = False
            return None


def _is_xinput(name):
    """XInput devices also show up through SDL; XInputReader reads those (directly, so each pad is
    listed once)."""
    name = name.lower()
    return "xinput" in name or "xbox" in name


def find_controllers():
    """Returns every usable reader: XInput devices first, then controllers SDL knows, then other
    joysticks."""
    readers = [XInputReader(slot) for slot in XInputReader.connected_slots()]
    try:
        import pygame

        sdl_controller = _sdl()
        for index in range(pygame.joystick.get_count()):
            known = sdl_controller is not None and sdl_controller.is_controller(index)
            name = sdl_controller.name_forindex(index) if known else pygame.joystick.Joystick(index).get_name()
            if _xinput and _is_xinput(name or ""):
                continue
            if known:
                readers.append(GameControllerReader(sdl_controller.Controller(index), sdl_controller))
            else:
                readers.append(RawJoystickReader(pygame.joystick.Joystick(index), sdl_controller))
    except Exception:
        pass
    return readers
