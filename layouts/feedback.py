"""Practice feedback shared by every display: the verdicts that pop up as each key input is settled
and the score banner after a pass. And the getting-started/coach card, which sits over whichever
display is showing (CardLayer). The hint line lives in the status bar, the same for every display.

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
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label

from key_inputs import EARLY, LATE
import theme

GRADE_COLORS = theme.GRADES
BANNER_SECONDS = 3.5  # How long a pass's score stays up.
_verdict_textures = {}


def _verdict_texture(text):
    if text not in _verdict_textures:
        label = MarkupLabel(text=text, font_size=theme.TITLE, bold=True, outline_width=2, outline_color=(0, 0, 0))
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
        self.banner = _panel_label((0.08, 0.08, 0.1, 0.94), font_size=theme.TITLE, color=theme.TEXT,
                                   padding=(dp(18), dp(10)), opacity=0)
        host.add_widget(self.banner)
        self.verdict_layer = InstructionGroup()
        host.canvas.after.add(self.verdict_layer)
        self.verdicts = []  # (Color, Rectangle), pooled.
        self._verdicts_at = (0, 0)
        self._banner_at = (0, 0, False)  # x, top, centred on x

    # ---- Layout ------------------------------------------------------------------------------

    def place(self, verdicts, banner):
        """verdicts: (x, top) of the newest; banner: (x, top, centred) where centred puts its middle
        at x."""
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
                parts.append(theme.markup("PERFECT", theme.HIT, bold=True))
                if last_pass["streak"] > 1:
                    parts.append(f"{last_pass['streak']} in a row")
            else:
                for notation, grade, offset in last_pass["problems"][:2]:
                    detail = {EARLY: f"{-offset}f early", LATE: f"{offset}f late"}.get(grade, "missed")
                    parts.append(f"{notation} {theme.markup(detail, GRADE_COLORS[grade])}")
                parts.append(f"best {last_pass['best']}/{last_pass['total']}")
        elif last_pass["match"] is not None:
            parts = [f"[b]Run {last_pass['run']}[/b]", f"matched {last_pass['match']:.0%} of frames"]
        else:
            return ""
        return "   ·   ".join(parts)


class CardLayer(FloatLayout):
    """The getting-started or coach card, over whichever display is showing: the display dimmed
    behind it, so nothing it draws pokes out from under the card, and its buttons under it. While
    it shows it takes every click (the buttons get theirs); hidden, clicks go through."""

    SCRIM = theme.SCRIM

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            self._scrim_color = Color(*self.SCRIM[:3], 0)
            self._scrim = Rectangle()
        self.bind(pos=self._layout, size=self._layout)
        self.card = _panel_label((*theme.SURFACE, 1), font_size=theme.LARGE, color=theme.TEXT,
                                 halign="left", valign="middle", padding=(dp(28), dp(22)))
        self.buttons = BoxLayout(size_hint=(None, None), height=dp(40), spacing=dp(8))
        self.add_widget(self.card)
        self.add_widget(self.buttons)
        self.card.bind(size=self._layout)
        self._specs = None
        self.showing = False
        self.set_card("")

    def set_card(self, text, buttons=()):
        """The card's text (empty hides it) and its buttons: (text, callback, primary) each."""
        if self.card.text != text:
            self.card.text = text
            self.card.text_size = (dp(620), None)
        self.showing = bool(text)
        self.opacity = 1 if text else 0
        self._scrim_color.a = self.SCRIM[3] if text else 0
        specs = tuple((label, primary) for label, _, primary in buttons) if text else ()
        if specs != self._specs:
            self._specs = specs
            self.buttons.clear_widgets()
            for label, callback, primary in (buttons if text else ()):
                button = Button(text=label, font_size=theme.LARGE, bold=primary, background_normal="",
                                background_down="", background_color=(*theme.ACCENT, 1) if primary else (*theme.SURFACE_RAISED, 1),
                                color=theme.TEXT_ON_ACCENT if primary else theme.TEXT)
                button.bind(on_release=lambda *_, callback=callback: callback())
                self.buttons.add_widget(button)
        self._layout()

    def _layout(self, *args):
        self._scrim.pos, self._scrim.size = self.pos, self.size
        self.card.pos = (self.center_x - self.card.width / 2, self.center_y - self.card.height / 2 + dp(24))
        self.buttons.width = self.card.width
        self.buttons.pos = (self.card.x, self.card.y - self.buttons.height - dp(6))

    def on_touch_down(self, touch):
        if not self.showing:
            return False
        super().on_touch_down(touch)
        return True  # Modal while it shows.

    def on_touch_move(self, touch):
        return self.showing and (super().on_touch_move(touch) or True)

    def on_touch_up(self, touch):
        return self.showing and (super().on_touch_up(touch) or True)


class FeedbackDisplay:
    """For the falling displays (arrow lanes, ring): the shared feedback, laid out around their
    prompts: the banner top centre and verdicts at verdict_spot(), which each display defines in
    its own coordinates."""

    card_up = False  # Set by the app while the card covers the display.

    def _init_feedback(self):
        self.feedback = Feedback(self)

    def show_feedback(self, judgements, last_pass):
        width, height = self.size
        self.feedback.place(verdicts=self.verdict_spot(), banner=(width / 2, height - dp(16), True))
        self.feedback.draw(judgements, last_pass)

    def verdict_spot(self):
        return self.width * 0.25, self.height * 0.6
