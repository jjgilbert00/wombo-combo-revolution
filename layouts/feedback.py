"""Practice feedback shared by every display: the hint line, the getting-started/coach card with its
buttons, the verdicts that pop up as each key input is settled, and the score banner after a pass.

A display makes one Feedback, which adds its widgets to the display, tells it where things go with
place() as it lays itself out, and passes it the latest verdicts and pass with draw(). Positions are
in the display's own coordinates (local ones for a RelativeLayout).
"""
import time

from kivy.core.text.markup import MarkupLabel
from kivy.graphics import Color, InstructionGroup, Rectangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

from key_inputs import EARLY, LATE

GRADE_COLORS = {"hit": (0.45, 0.9, 0.5), "early": (0.45, 0.62, 1.0), "late": (1.0, 0.62, 0.2),
                "miss": (1, 0.42, 0.42), "pending": (0.45, 0.45, 0.5)}
BANNER_SECONDS = 3.5  # How long a pass's score stays up.
_verdict_textures = {}


def _hex(rgb):
    return "".join(f"{round(c * 255):02x}" for c in rgb)


def _verdict_texture(text):
    if text not in _verdict_textures:
        label = MarkupLabel(text=text, font_size=sp(24), bold=True, outline_width=2, outline_color=(0, 0, 0))
        label.refresh()
        _verdict_textures[text] = label.texture
    return _verdict_textures[text]


def _panel_label(background, **kwargs):
    """A label with a dark panel behind it that sizes itself to its text."""
    label = Label(markup=True, size_hint=(None, None), **kwargs)
    with label.canvas.before:
        Color(*background)
        background = Rectangle()
    label.bind(pos=lambda w, pos: setattr(background, "pos", pos),
               size=lambda w, size: setattr(background, "size", size),
               texture_size=lambda w, size: setattr(w, "size", size))
    return label


class Feedback:
    def __init__(self, host):
        self.host = host
        self.hint = Label(markup=True, font_size=sp(14), color=(0.78, 0.78, 0.82, 1), halign="left", valign="top",
                          size_hint=(None, None))
        self.card = _panel_label((0.1, 0.1, 0.13, 0.97), font_size=sp(15), color=(0.9, 0.9, 0.92, 1),
                                 halign="left", valign="middle", padding=(dp(28), dp(22)), opacity=0)
        self.banner = _panel_label((0.08, 0.08, 0.1, 0.94), font_size=sp(18), color=(0.95, 0.95, 0.97, 1),
                                   padding=(dp(18), dp(10)), opacity=0)
        self.card_buttons = BoxLayout(size_hint=(None, None), height=dp(40), spacing=dp(8), opacity=0)
        self._button_specs = None
        for widget in (self.hint, self.card, self.banner, self.card_buttons):
            host.add_widget(widget)
        self.verdict_layer = InstructionGroup()
        host.canvas.after.add(self.verdict_layer)
        self.verdicts = []  # (Color, Rectangle), pooled.
        self._verdicts_at = (0, 0)
        self._banner_at = (0, 0, False)  # x, top, centred on x

    # ---- The card and hint -------------------------------------------------------------------

    def set_guidance(self, hint, card="", buttons=()):
        """The hint line's text, and the card's (empty hides it) with its buttons: (text, callback,
        primary) each, under the card."""
        if self.hint.text != hint:
            self.hint.text = hint
        if self.card.text != card:
            self.card.text = card
            self.card.text_size = (dp(620), None)
        self.card.opacity = 1 if card else 0
        specs = tuple((text, primary) for text, _, primary in buttons) if card else ()
        if specs != self._button_specs:
            self._button_specs = specs
            self.card_buttons.clear_widgets()
            for text, callback, primary in (buttons if card else ()):
                button = Button(text=text, font_size=sp(15), bold=primary, background_normal="", background_down="",
                                background_color=(0.25, 0.55, 0.95, 1) if primary else (1, 1, 1, 0.12))
                button.bind(on_release=lambda *_, callback=callback: callback())
                self.card_buttons.add_widget(button)
        self.card_buttons.opacity = 1 if specs else 0
        self.card_buttons.disabled = not specs

    @property
    def card_showing(self):
        return bool(self.card.opacity)

    def card_hit(self, touch):
        return bool(self.card_buttons.opacity) and self.card_buttons.collide_point(*touch.pos)

    # ---- Layout ------------------------------------------------------------------------------

    def place(self, hint, card_center, verdicts, banner):
        """hint: (x, top, width); card_center: (x, y); verdicts: (x, top) of the newest; banner:
        (x, top, centred) where centred puts its middle at x."""
        x, top, width = hint
        self.hint.text_size = (width, None)
        self.hint.texture_update()
        self.hint.size = (width, self.hint.texture_size[1])
        self.hint.pos = (x, top - self.hint.height)
        cx, cy = card_center
        self.card.pos = (cx - self.card.width / 2, cy - self.card.height / 2 + dp(24))
        self.card_buttons.width = self.card.width
        self.card_buttons.pos = (self.card.x, self.card.y - self.card_buttons.height - dp(6))
        self._verdicts_at = verdicts
        self._banner_at = banner

    # ---- Verdicts and the pass banner --------------------------------------------------------

    def draw(self, judgements, last_pass):
        self._draw_verdicts(judgements)
        self._show_banner(last_pass)

    def _draw_verdicts(self, judgements):
        """Verdicts popping up as each key input is settled, newest on top, rising as they fade."""
        x, top = self._verdicts_at
        recent = list(reversed(judgements[-3:]))
        for row, (grade, offset, notation, age) in enumerate(recent):
            if row == len(self.verdicts):
                color, rect = Color(1, 1, 1, 0), Rectangle()
                self.verdict_layer.add(color)
                self.verdict_layer.add(rect)
                self.verdicts.append((color, rect))
            color, rect = self.verdicts[row]
            text = {EARLY: f"EARLY {offset:+d}", LATE: f"LATE {offset:+d}"}.get(grade, grade.upper())
            texture = _verdict_texture(f"{text}  [size=14sp]{notation}[/size]")
            color.rgba = (*GRADE_COLORS[grade], max(0.0, 1 - age * age))
            rect.texture, rect.size = texture, texture.size
            rect.pos = (x, top - texture.height - row * dp(36) + age * dp(14))
        for color, _ in self.verdicts[len(recent):]:
            color.a = 0

    def _show_banner(self, last_pass):
        """The last pass's score for a few seconds after it ends."""
        text = self.banner_text(last_pass)
        if not text:
            self.banner.opacity = 0
            return
        if self.banner.text != text:
            self.banner.text = text
            self.banner.texture_update()
        self.banner.opacity = 1
        x, top, centred = self._banner_at
        self.banner.pos = (x - self.banner.width / 2 if centred else x, top - self.banner.height)

    @staticmethod
    def banner_text(last_pass):
        if not last_pass or time.monotonic() - last_pass["time"] > BANNER_SECONDS:
            return ""
        if last_pass["total"]:
            parts = [f"[b]Run {last_pass['run']}[/b]", f"[b]{last_pass['hits']}/{last_pass['total']}[/b]"]
            if last_pass["hits"] == last_pass["total"]:
                parts.append("[color=5ce176][b]PERFECT[/b][/color]")
                if last_pass["streak"] > 1:
                    parts.append(f"{last_pass['streak']} in a row")
            else:
                for notation, grade, offset in last_pass["problems"][:2]:
                    detail = {EARLY: f"{-offset}f early", LATE: f"{offset}f late"}.get(grade, "missed")
                    parts.append(f"{notation} [color={_hex(GRADE_COLORS[grade])}]{detail}[/color]")
                parts.append(f"best {last_pass['best']}/{last_pass['total']}")
        elif last_pass["match"] is not None:
            parts = [f"[b]Run {last_pass['run']}[/b]", f"matched {last_pass['match']:.0%} of frames"]
        else:
            return ""
        return "   ·   ".join(parts)


class FeedbackDisplay:
    """For the falling displays (arrow lanes, ring): the shared feedback, laid out around their
    prompts: the hint top left, the banner centred under it, the card in the middle and verdicts at
    verdict_spot(), which each display defines in its own coordinates."""

    def _init_feedback(self):
        self.feedback = Feedback(self)

    def set_guidance(self, hint, card="", buttons=()):
        self.feedback.set_guidance(hint, card, buttons)

    def show_feedback(self, judgements, last_pass):
        width, height = self.size
        hint_top = height - dp(12)
        hint = self.feedback.hint
        hint_bottom = hint_top - (hint.height + dp(8) if hint.text else 0)
        self.feedback.place(hint=(dp(16), hint_top, width * 0.45), card_center=(width / 2, height / 2),
                            verdicts=self.verdict_spot(), banner=(width / 2, hint_bottom - dp(4), True))
        self.feedback.draw(judgements, last_pass)

    def verdict_spot(self):
        return self.width * 0.25, self.height * 0.6
