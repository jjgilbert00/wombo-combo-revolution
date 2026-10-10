"""Stand-in controllers for checks: they answer the sampler's polls without real hardware."""
from input_list import LIST_BUTTON_ORDER


def st(direction, *buttons):
    return dict({button: int(button in buttons) for button in LIST_BUTTON_ORDER}, direction=direction)


class WarmUpPad:
    """Plays the warm-up sample perfectly: LP, MP, HP, then a Hadoken (236HP)."""

    name, connected, menu = "Scripted pad", True, (False, False)
    PRESSES = ((41, 42, st(5, "X")), (71, 72, st(5, "Y")), (101, 102, st(5, "RB")), (130, 133, st(2)),
               (134, 137, st(3)), (138, 139, st(6)), (140, 143, st(6, "RB")))

    def __init__(self, controller):
        self.controller = controller

    def poll(self):
        c = self.controller
        if not c.is_playing() or c.get_lead():
            return st(5)
        frame = c.get_current_frame()
        return next((state for first, last, state in self.PRESSES if first <= frame <= last), st(5))


def use_pad(app, pad):
    app.sampler.reader = pad
    app.check_controller = lambda dt: None  # Keep the stand-in; don't look for real pads.


def popup(h, name):
    return next((c for c in h.app.root_window.children if type(c).__name__ == name), None)
