"""The key input editor: its type, frames, motion, direction and buttons."""
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

import theme
from layouts.ui_kit import (
    DIM_TEXT_COLOR, FONT_SIZE, MINUS, PANEL_COLOR, TEXT_COLOR, Dialog, Toggle, button, confirm_button,
    paint_background
)


class KeyInputPopup(Dialog):
    """Edits a key input: whether it's a press in a window, a hold or an exact span, its eligible
    frames, and the motion, direction and buttons it requires. Every part can be dropped with one
    click or keystroke, so stray directions or buttons from the recording are easy to remove.
    on_save(key_input) gets the edited copy; on_delete is only offered for an existing one.
    describe(key_input) supplies the live notation preview, and suggest_hold(key_input) what the
    recording holds in the window (direction, buttons and length) as a starting point for a hold."""

    ROW_HEIGHT = dp(32)
    NUMPAD_ROWS = ((7, 8, 9), (4, 5, 6), (1, 2, 3))

    def __init__(self, title, key_input, last_frame, button_names, describe, suggest_hold, on_save, on_delete=None,
                 **kwargs):
        super().__init__(size_hint=(None, None), size=(dp(520), dp(426)), background="",
                         background_color=(0, 0, 0, 0.5), **kwargs)
        self.key_input = dict(key_input, motion=list(key_input["motion"]), buttons=list(key_input["buttons"]))
        self.last_frame = last_frame
        self.describe = describe
        self.suggest_hold = suggest_hold
        panel = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))
        paint_background(panel, PANEL_COLOR)
        header = BoxLayout(size_hint_y=None, height=dp(24))
        header.add_widget(Label(text=title, font_size=theme.TITLE, bold=True, color=TEXT_COLOR, halign="left",
                                valign="middle", size_hint_x=None, width=dp(300), text_size=(dp(300), dp(24))))
        self.preview = Label(font_size=theme.LARGE, bold=True, color=(*theme.ACCENT, 1), halign="right",
                             valign="middle")
        self.preview.bind(size=lambda label, size: setattr(label, "text_size", size))
        header.add_widget(self.preview)
        panel.add_widget(header)

        kinds = BoxLayout(spacing=dp(4))
        for text, kind in (("Press in window", "press"), ("Hold", "hold"), ("Exact span", "exact")):
            toggle = Toggle(text=text, group="kind", allow_no_selection=False,
                             state="down" if self._kind() == kind else "normal")
            toggle.bind(state=lambda t, state, kind=kind: state == "down" and self._set_kind(kind))
            kinds.add_widget(toggle)
        panel.add_widget(self._row("Type", kinds))

        frames = BoxLayout(spacing=dp(4))
        self.window_label = Label(font_size=FONT_SIZE, color=TEXT_COLOR, size_hint_x=None, width=dp(150))
        frames.add_widget(self._stepper(MINUS, "start", -1))
        frames.add_widget(self._stepper("+", "start", 1))
        frames.add_widget(self.window_label)
        frames.add_widget(self._stepper(MINUS, "end", -1))
        frames.add_widget(self._stepper("+", "end", 1))
        frames.add_widget(Widget())
        panel.add_widget(self._row("Frames", frames))

        hold = BoxLayout(spacing=dp(8))
        self.hold_input = TextInput(
            text=str(self.key_input["hold"] or ""), multiline=False, font_size=FONT_SIZE, size_hint_x=None,
            width=dp(60), background_color=(1, 1, 1, 0.08), foreground_color=TEXT_COLOR, cursor_color=TEXT_COLOR,
            input_filter=lambda text, from_undo: "".join(c for c in text if c.isdigit()),
        )
        self.hold_input.bind(text=lambda _, text: self._set_hold(text))
        hold.add_widget(self.hold_input)
        hold.add_widget(self._hint("frames in a row, anywhere in the window"))
        panel.add_widget(self._row("Hold for", hold))

        self.press_widgets = []
        motion = BoxLayout(spacing=dp(8))
        self.motion_input = TextInput(
            text="".join(str(d) for d in self.key_input["motion"]), multiline=False, font_size=FONT_SIZE,
            size_hint_x=None, width=dp(120), background_color=(1, 1, 1, 0.08), foreground_color=TEXT_COLOR,
            cursor_color=TEXT_COLOR, hint_text="e.g. 236",
            input_filter=lambda text, from_undo: "".join(c for c in text if c in "123456789"),
        )
        self.motion_input.bind(text=lambda _, text: self._set_motion(text))
        motion.add_widget(self.motion_input)
        motion.add_widget(self._hint("Numpad notation; leave empty for no motion"))
        panel.add_widget(self._row("Motion", motion))

        direction = BoxLayout(spacing=dp(10))
        numpad = GridLayout(cols=3, spacing=dp(4), size_hint=(None, None), width=dp(116), height=dp(104))
        for row in self.NUMPAD_ROWS:
            for value in row:
                toggle = Toggle(text=str(value), group="direction",
                                 state="down" if self.key_input["direction"] == value else "normal")
                toggle.bind(state=lambda t, state, value=value: self._set_direction(value if state == "down" else None))
                numpad.add_widget(toggle)
                self.press_widgets.append(toggle)
        direction.add_widget(numpad)
        self.direction_hint = self._hint("")
        direction.add_widget(self.direction_hint)
        panel.add_widget(self._row("Direction", direction, height=dp(104)))

        buttons = BoxLayout(spacing=dp(4))
        for name in button_names:
            toggle = Toggle(text=name, state="down" if name in self.key_input["buttons"] else "normal")
            toggle.bind(state=lambda t, state, name=name: self._set_button(name, state == "down"))
            buttons.add_widget(toggle)
            self.press_widgets.append(toggle)
        panel.add_widget(self._row("Buttons", buttons))

        actions = BoxLayout(size_hint_y=None, height=self.ROW_HEIGHT, spacing=dp(8))
        if on_delete:
            actions.add_widget(confirm_button("Delete", lambda: (self.dismiss(), on_delete())))
        actions.add_widget(Widget())
        cancel = button("Cancel", self.dismiss, "ghost")
        save = button("Save", lambda: (self.dismiss(), on_save(self.key_input)), "primary")
        actions.add_widget(cancel)
        actions.add_widget(save)
        panel.add_widget(actions)
        self.add_widget(panel)
        self._refresh()

    def _row(self, label, content, height=None):
        row = BoxLayout(size_hint_y=None, height=height or self.ROW_HEIGHT, spacing=dp(12))
        row.add_widget(Label(text=label, font_size=FONT_SIZE, color=TEXT_COLOR, halign="left", valign="top",
                             size_hint_x=None, width=dp(84), text_size=(dp(84), height or self.ROW_HEIGHT),
                             padding=(0, dp(7))))
        row.add_widget(content)
        return row

    @staticmethod
    def _hint(text):
        return Label(text=text, font_size=theme.CAPTION, color=DIM_TEXT_COLOR, halign="left", valign="middle",
                     text_size=(dp(250), None))

    def _stepper(self, text, edge, delta):
        return button(text, lambda: self._step(edge, delta))

    def _step(self, edge, delta):
        start, end = self.key_input["start"], self.key_input["end"]
        if edge == "start":
            start = max(0, min(start + delta, end))
        else:
            end = min(self.last_frame, max(end + delta, start))
        self.key_input.update(start=start, end=end)
        self._refresh()

    def _kind(self):
        if self.key_input["exact"]:
            return "exact"
        return "hold" if self.key_input["hold"] else "press"

    def _set_kind(self, kind):
        self.key_input["exact"] = kind == "exact"
        if kind != "hold":
            self.key_input["hold"] = 0
        elif not self.key_input["hold"]:
            # Start from what the recording holds (a press guess picks up buttons that aren't held).
            self.key_input.update(self.suggest_hold(self.key_input))
            self.hold_input.text = str(self.key_input["hold"])
            for toggle in self.press_widgets:
                if getattr(toggle, "group", None) == "direction":
                    toggle.state = "down" if toggle.text == str(self.key_input["direction"]) else "normal"
                else:
                    toggle.state = "down" if toggle.text in self.key_input["buttons"] else "normal"
        self._refresh()

    def _set_hold(self, text):
        if self._kind() == "hold":
            self.key_input["hold"] = max(1, int(text or 0))  # Still a hold while the field is cleared.
            self._refresh()

    def _set_motion(self, text):
        self.key_input["motion"] = [int(c) for c in text]
        self._refresh()

    def _set_direction(self, direction):
        # Toggling one numpad key off and another on fires twice; ignore the stale "off".
        if direction is None and any(getattr(t, "group", None) == "direction" and t.state == "down"
                                     for t in self.press_widgets):
            return
        self.key_input["direction"] = direction
        self._refresh()

    def _set_button(self, name, pressed):
        buttons = [b for b in self.key_input["buttons"] if b != name]
        self.key_input["buttons"] = buttons + [name] if pressed else buttons
        self._refresh()

    def _refresh(self):
        start, end = self.key_input["start"], self.key_input["end"]
        count = end - start + 1
        self.window_label.text = f"{start} - {end}  ({count} frame{'s' if count != 1 else ''})"
        kind = self._kind()
        # Direction and buttons don't apply to an exact span, which matches whole frames; a hold
        # has no motion.
        for widget in self.press_widgets:
            widget.disabled = kind == "exact"
        self.motion_input.disabled = kind != "press"
        self.hold_input.disabled = kind != "hold"
        self.direction_hint.text = (
            ("Held throughout; 2 counts 1-3, like charge." if kind == "hold" else "Held when the buttons are pressed.")
            + "\nClick the lit key again for any direction."
        )
        self.preview.text = self.describe(self.key_input)
