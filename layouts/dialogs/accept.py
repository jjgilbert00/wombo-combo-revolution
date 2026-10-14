"""What one key input accepts: its own exceptions to the recording's input rules."""
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget

import theme
from layouts.ui_kit import (
    DIM_TEXT_COLOR, FONT_SIZE, PANEL_COLOR, TEXT_COLOR, Dialog, OnOffSwitch, Stepper, Toggle, button,
    paint_background
)

NUMPAD_ROWS = ((7, 8, 9), (4, 5, 6), (1, 2, 3))


def _frames(count, zero):
    return zero if count == 0 else f"{count} frame{'s' * (count != 1)}"


def frame_choices(top, zero, step=1, start=0):
    return [(_frames(n, zero), n) for n in range(start, top + 1, step)]


def summary(accepts):
    """One line on what a key input accepts (from key_inputs.acceptance)."""
    if accepts["strict"]:
        parts = ["Strict: exact directions and motion"]
    else:
        parts = []
        if accepts["directions"] and len(accepts["directions"]) > 1:
            parts.append("directions " + ", ".join(str(d) for d in accepts["directions"]))
        if accepts["motion"]:
            parts.append(f"{accepts['motion']} by pattern" + (f" in {accepts['max_frames']}f" if accepts["max_frames"]
                                                             else ""))
        if accepts["charge"]:
            parts.append(f"charge {accepts['charge'][0]}f, kept {accepts['charge'][1]}f")
    if accepts["simultaneous"]:
        parts.append(f"buttons {accepts['simultaneous']}f apart")
    if accepts["buffer"]:
        parts.append(f"{accepts['buffer']}f early")
    return "; ".join(parts) or "Exactly as written"


class AcceptPopup(Dialog):
    """Changes what one key input accepts, apart from the recording's rules: the directions its press
    takes, how far apart its buttons can be pressed, how early it can be done, its motion's time limit
    and its charge, or to grade it strictly. game is what the rules give it without changes (from
    key_inputs.acceptance), current what it accepts now; on_done(accept) gets the key input's new
    "accept" (only what differs from the rules; {} for none)."""

    ROW = dp(34)

    def __init__(self, notation, has_press, game, current, accept, on_done, **kwargs):
        super().__init__(size_hint=(None, None), size=(dp(560), dp(400)), background="",
                         background_color=(0, 0, 0, 0.5), **kwargs)
        self.game, self.accept, self.on_done = game, dict(accept), on_done
        self.values = {"simultaneous": current["simultaneous"], "buffer": current["buffer"],
                       "max_frames": current["max_frames"], "charge": current["charge"]}
        panel = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(8), size_hint_y=None)
        panel.bind(minimum_height=lambda p, height: (setattr(p, "height", height), setattr(self, "height", height)))
        paint_background(panel, PANEL_COLOR)
        panel.add_widget(Label(text=f"What {notation} accepts", font_size=theme.TITLE, bold=True, color=TEXT_COLOR,
                               size_hint_y=None, height=dp(24), halign="left", text_size=(dp(528), dp(24))))
        panel.add_widget(Label(
            text="Changes for this key input only, for when the game's rules are wrong about it. The rest of the "
                 "recording keeps its rules.", font_size=theme.CAPTION, color=DIM_TEXT_COLOR, size_hint_y=None,
            height=dp(30), halign="left", valign="top", text_size=(dp(528), dp(30))))

        strict = BoxLayout(spacing=dp(10))
        self.strict_switch = OnOffSwitch(bool(current["strict"]), self._set_strict)
        self.strict_switch.disabled = bool(game["strict"])
        strict.add_widget(self._centered(self.strict_switch))
        strict.add_widget(self._hint("The whole recording is graded strictly (Edit > Input rules)" if game["strict"] else
                                     "Exact direction, every direction of the motion, buttons on the same frame"))
        panel.add_widget(self._row("Strict", strict))

        directions = BoxLayout(spacing=dp(10))
        numpad = GridLayout(cols=3, spacing=dp(3), size_hint=(None, None), width=dp(108), height=dp(96))
        shown = set(current["directions"] or range(1, 10))
        self.direction_toggles = {}
        for row in NUMPAD_ROWS:
            for value in row:
                toggle = Toggle(text=str(value), state="down" if value in shown else "normal")
                toggle.bind(state=lambda *_: self._set_directions())
                toggle.disabled = not has_press
                self.direction_toggles[value] = toggle
                numpad.add_widget(toggle)
        directions.add_widget(numpad)
        game_directions = ", ".join(str(d) for d in game["directions"]) if game["directions"] else "any"
        directions.add_widget(self._hint(
            f"The directions held on the press that count.\nThe rules: {game_directions}"
            + (f" ({game['group']})" if game["group"] else "") if has_press else "Only for a press."))
        panel.add_widget(self._row("Directions", directions, height=dp(96)))

        self.steppers = {}
        panel.add_widget(self._stepper_row("Together", "simultaneous", frame_choices(10, "same frame"),
                                           "Buttons pressed this far apart count as together"))
        panel.add_widget(self._stepper_row("Early by", "buffer", frame_choices(15, "not early"),
                                           "Done this many frames before the window still counts"))
        if game["motion"]:
            panel.add_widget(self._stepper_row("Motion in", "max_frames", frame_choices(60, "any time"),
                                               f"Time limit on the {game['motion']} motion, up to the press"))
        if game["charge"]:
            panel.add_widget(self._charge_row())

        actions = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(8))
        actions.add_widget(button("Use the rules", self._reset))
        actions.add_widget(Widget())
        actions.add_widget(button("Cancel", self.dismiss, "ghost"))
        actions.add_widget(button("Done", self._done, "primary"))
        panel.add_widget(actions)
        self.add_widget(panel)

    # ---- Layout -------------------------------------------------------------------------------

    def _row(self, label, content, height=None):
        row = BoxLayout(size_hint_y=None, height=height or self.ROW, spacing=dp(12))
        row.add_widget(Label(text=label, font_size=FONT_SIZE, color=TEXT_COLOR, halign="left", valign="top",
                             size_hint_x=None, width=dp(84), text_size=(dp(84), height or self.ROW),
                             padding=(0, dp(8))))
        row.add_widget(content)
        return row

    @staticmethod
    def _hint(text):
        label = Label(text=text, font_size=theme.CAPTION, color=DIM_TEXT_COLOR, halign="left", valign="middle")
        label.bind(size=lambda l, size: setattr(l, "text_size", size))
        return label

    @staticmethod
    def _centered(widget):
        box = BoxLayout(size_hint_x=None, width=widget.width, padding=(0, dp(5)))
        box.add_widget(widget)
        return box

    def _stepper_row(self, label, field, choices, hint):
        row = BoxLayout(spacing=dp(10))
        stepper = Stepper(choices, self.values[field], lambda value: self._set(field, value), size_hint_x=None,
                          width=dp(190))
        self.steppers[field] = stepper
        row.add_widget(stepper)
        row.add_widget(self._hint(hint + f" (rules: {dict((v, t) for t, v in choices).get(self.game[field], self.game[field])})"))
        return self._row(label, row)

    def _charge_row(self):
        frames, keep = self.values["charge"]
        row = BoxLayout(spacing=dp(6))
        hold = Stepper(frame_choices(120, "", 1, 1), frames, lambda value: self._set_charge(0, value),
                       size_hint_x=None, width=dp(150))
        kept = Stepper(frame_choices(30, "not kept"), keep, lambda value: self._set_charge(1, value),
                       size_hint_x=None, width=dp(150))
        self.steppers["charge"] = (hold, kept)
        row.add_widget(hold)
        row.add_widget(self._hint("kept"))
        row.add_widget(kept)
        return self._row("Charge", row)

    # ---- Changes ------------------------------------------------------------------------------

    def _set_strict(self, strict):
        if self.game["strict"]:
            return  # The whole recording is strict; the switch only shows it.
        if strict:
            self.accept["strict"] = True
        else:
            self.accept.pop("strict", None)

    def _set_directions(self):
        chosen = sorted(d for d, toggle in self.direction_toggles.items() if toggle.state == "down")
        if not chosen or chosen == (self.game["directions"] or list(range(1, 10))):
            self.accept.pop("directions", None)
        else:
            self.accept["directions"] = chosen

    def _set(self, field, value):
        self.values[field] = value
        if value == self.game[field]:
            self.accept.pop(field, None)
        else:
            self.accept[field] = value

    def _set_charge(self, index, value):
        charge = list(self.values["charge"])
        charge[index] = value
        self.values["charge"] = tuple(charge)
        if tuple(charge) == tuple(self.game["charge"]):
            self.accept.pop("charge", None)
        else:
            self.accept["charge"] = {"frames": charge[0], "keep": charge[1]}

    def _reset(self):
        self.dismiss()
        self.on_done({})

    def _done(self):
        self.dismiss()
        self.on_done(self.accept)
