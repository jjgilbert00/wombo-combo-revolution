import ctypes
import math
import random
import sys

BUTTON_NAMES = ["A", "B", "X", "Y", "LB", "RB", "LT", "RT"]


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


def get_random_controller_state():
    return {
        "direction": math.floor(random.random() * 9) + 1,
        "A": round(0.51*random.random()),
        "B": round(0.51*random.random()),
        "X": round(0.51*random.random()),
        "Y": round(0.51*random.random()),
        "RT": round(0.51*random.random()),
        "RB": round(0.51*random.random()),
        "LT": round(0.51*random.random()),
        "LB": round(0.51*random.random())
    }


def get_cool_controller_pattern(frames = 180):
    circles = [1,2,3,6,9,8,7,4]
    inputs = [get_random_controller_state() for _ in range(frames)]
    for i, input in enumerate(inputs[0:len(inputs)//2]):
        if i % 10 != 1:
            input["direction"] = inputs[i-1]["direction"]
            continue
        curdir = circles.pop()
        circles.insert(0, curdir)
        input["direction"] = curdir

    for i, input in enumerate(inputs[len(inputs)//2 :]):
        if i % 10 != 1:
            input["direction"] = inputs[len(inputs)//2 + i-1]["direction"]
            continue
        curdir = circles.pop(0)
        circles.append(curdir)
        input["direction"] = curdir
    return inputs


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
    sampler thread at exactly the moment a frame is due. pygame, by contrast, only refreshes its
    joystick state when the UI thread pumps SDL events.
    """

    DPAD_UP, DPAD_DOWN, DPAD_LEFT, DPAD_RIGHT = 0x0001, 0x0002, 0x0004, 0x0008
    BUTTON_MASKS = {"LB": 0x0100, "RB": 0x0200, "A": 0x1000, "B": 0x2000, "X": 0x4000, "Y": 0x8000}
    TRIGGER_THRESHOLD = 128

    def __init__(self, slot):
        self.slot = slot
        self.name = f"XInput controller {slot + 1}"
        self.connected = True
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


class PygameReader:
    """Fallback for controllers XInput can't see.

    pygame's joystick state only updates when SDL events are pumped, which happens on the Kivy
    UI thread, so samples can be up to one UI frame stale. Prefer XInputReader when possible.
    """

    def __init__(self, joystick):
        self.joystick = joystick
        self.joystick.init()
        self.name = f"{joystick.get_name()} (pygame)"
        self.connected = True

    def poll(self):
        try:
            hat = self.joystick.get_hat(0) if self.joystick.get_numhats() else (0, 0)
            return {
                "direction": direction_from_axes(hat[0], hat[1]),
                "X": self.joystick.get_button(2),
                "Y": self.joystick.get_button(3),
                "A": self.joystick.get_button(0),
                "B": self.joystick.get_button(1),
                "LB": self.joystick.get_button(4),
                "RB": self.joystick.get_button(5),
                "LT": int((round(self.joystick.get_axis(4)) + 1) / 2),
                "RT": int((round(self.joystick.get_axis(5)) + 1) / 2),
            }
        except Exception:
            self.connected = False
            return None


def find_controllers():
    """Returns every usable reader, XInput devices first."""
    readers = [XInputReader(slot) for slot in XInputReader.connected_slots()]
    try:
        import pygame

        if not pygame.joystick.get_init():
            pygame.joystick.init()
        # XInput devices also show up in pygame; skip those so each pad is listed once.
        for index in range(pygame.joystick.get_count()):
            joystick = pygame.joystick.Joystick(index)
            name = joystick.get_name().lower()
            if _xinput and ("xinput" in name or "xbox" in name):
                continue
            readers.append(PygameReader(joystick))
    except Exception:
        pass
    return readers
