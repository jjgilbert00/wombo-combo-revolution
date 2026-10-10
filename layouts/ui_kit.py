"""The app's own widgets, styled from theme.py: buttons of each kind, transport icons, toggles,
steppers, pickers and switches, menus and tooltips, the status bar, and the Dialog every dialog
is built on. Screens are assembled from these: the menu bar (menu_bar.py) and the dialogs
(dialogs/).
"""
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Rectangle, RoundedRectangle, Triangle
from kivy.metrics import dp
from kivy.properties import BooleanProperty, ListProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.dropdown import DropDown
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.spinner import Spinner, SpinnerOption
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget

import theme


BAR_HEIGHT = dp(36)

BAR_COLOR = (*theme.BAR, 0.95)

PANEL_COLOR = (*theme.SURFACE, 1)

HOVER_COLOR = (1, 1, 1, 0.08)

ACTIVE_COLOR = (1, 1, 1, 0.16)

RECORD_COLOR = (*theme.DANGER, 1)

DEMO_COLOR = (*theme.HOLD, 0.55)

TEXT_COLOR = theme.TEXT

DIM_TEXT_COLOR = theme.TEXT_DIM

FONT_SIZE = theme.BODY


def paint_background(widget, color):
    with widget.canvas.before:
        widget._bg_color = Color(*color)
        widget._bg_rect = Rectangle(pos=widget.pos, size=widget.size)
    widget.bind(pos=lambda w, pos: setattr(w._bg_rect, "pos", pos))
    widget.bind(size=lambda w, size: setattr(w._bg_rect, "size", size))


class Dialog(ModalView):
    """A modal dialog whose panel fades and rises into place as it opens, rather than popping."""

    def on_pre_open(self):
        if self.children:
            panel = self.children[0]
            panel.opacity = 0
            Animation(opacity=1, d=0.12, t="out_quad").start(panel)


class HoverBehavior:
    hovered = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Window.bind(mouse_pos=self._on_mouse_pos)

    def _on_mouse_pos(self, window, pos):
        self.hovered = bool(self.get_root_window()) and not self.disabled and self.collide_point(*self.to_widget(*pos))


class Tooltip(Label):
    """One shared tooltip, shown under a hovered widget after a short delay."""

    DELAY = 0.5
    _instance = None

    def __init__(self, **kwargs):
        super().__init__(markup=True, font_size=theme.BODY, color=TEXT_COLOR, size_hint=(None, None), halign="left",
                         valign="middle", padding=(dp(10), dp(6)), **kwargs)
        paint_background(self, (0.05, 0.05, 0.07, 0.96))
        self.bind(texture_size=lambda *_: setattr(self, "size", self.texture_size))
        self._pending = None
        self._owner = None

    @property
    def owner_key(self):
        return self._owner

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def schedule(self, widget, text):
        self.hide()
        self._owner = widget
        self._pending = Clock.schedule_once(lambda dt: self._show(widget, text), self.DELAY)

    def schedule_at(self, key, window_pos, text):
        """Like schedule, for something drawn rather than a widget: shown under window_pos. key
        identifies it, for hide(key)."""
        self.hide()
        self._owner = key
        self._pending = Clock.schedule_once(lambda dt: self._show(None, text, window_pos), self.DELAY)

    def _show(self, widget, text, window_pos=None):
        self.text_size = (None, None)
        self.text = text
        self.texture_update()
        if self.texture_size[0] > dp(340):
            self.text_size = (dp(340) - dp(20), None)  # Long tips wrap.
            self.texture_update()
        self.size = self.texture_size
        x, y = window_pos or widget.to_window(widget.x, widget.y)
        self.pos = (max(dp(4), min(x, Window.width - self.width - dp(4))), y - self.height - dp(4))
        if not self.parent:
            Window.add_widget(self)

    def hide(self, owner=None):
        """Hides the tooltip, or with owner, only if it's that widget's (another may have just taken over)."""
        if owner is not None and owner is not self._owner:
            return
        if self._pending:
            self._pending.cancel()
            self._pending = None
        self._owner = None
        if self.parent:
            self.parent.remove_widget(self)


# Button kinds, the same everywhere: (background, text colour). One primary per dialog.
BUTTON_KINDS = {
    "primary": ((*theme.ACCENT, 1), theme.TEXT_ON_ACCENT),
    "secondary": ((1, 1, 1, 0.1), theme.TEXT),
    "danger": ((1, 1, 1, 0.1), theme.MISS),  # Destructive: red text; red fill once it asks to confirm.
    "confirm": ((*theme.DANGER, 1), (1, 1, 1, 1)),
    "selected": ((*theme.ACCENT, 1), theme.TEXT_ON_ACCENT),
    "ghost": ((0, 0, 0, 0), theme.TEXT),  # Bar items.
}


class BarButton(HoverBehavior, Button):
    """Flat, text-sized button: menu bar items, and dialog buttons by `kind` (BUTTON_KINDS).
    `highlight` tints it, e.g. while recording. `tooltip` is shown after hovering for a moment."""

    highlight = ListProperty([0, 0, 0, 0])
    tooltip = StringProperty("")
    kind = StringProperty("ghost")

    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint_x", None)
        kwargs.setdefault("font_size", FONT_SIZE)
        fixed_width = "width" in kwargs  # Otherwise it's as wide as its text.
        super().__init__(
            background_normal="", background_down="", background_disabled_normal="", background_disabled_down="",
            color=TEXT_COLOR, disabled_color=DIM_TEXT_COLOR, **kwargs
        )
        self.bind(kind=self._refresh_color)
        if not fixed_width:
            self.bind(texture_size=lambda *_: setattr(self, "width", self.texture_size[0] + dp(24)))
        self.bind(hovered=self._refresh_color, state=self._refresh_color, highlight=self._refresh_color)
        self.bind(hovered=self._refresh_tooltip, state=self._refresh_tooltip)
        self._refresh_color()

    def _refresh_tooltip(self, *args):
        if self.tooltip and self.hovered and self.state == "normal":
            Tooltip.get().schedule(self, self.tooltip)
        else:
            Tooltip.get().hide(self)

    def _refresh_color(self, *args):
        background, text = BUTTON_KINDS[self.kind]
        self.color = text
        if self.highlight[3]:
            self.background_color = self.highlight
        elif self.kind != "ghost":
            # Lighter on hover, darker pressed.
            shade = 1.12 if self.state == "normal" and self.hovered else 0.88 if self.state == "down" else 1
            r, g, b, a = background
            self.background_color = (min(1, r * shade + (0.04 if a < 0.5 and self.hovered else 0)),
                                     min(1, g * shade), min(1, b * shade), a + (0.06 if a < 0.5 and self.hovered else 0))
        elif self.state == "down":
            self.background_color = ACTIVE_COLOR
        elif self.hovered:
            self.background_color = HOVER_COLOR
        else:
            self.background_color = (0, 0, 0, 0)


def button(text, callback, kind="secondary", **kwargs):
    """A dialog button of a kind from BUTTON_KINDS."""
    widget = BarButton(text=text, kind=kind, **kwargs)
    widget.bind(on_release=lambda *_: callback())
    return widget


def confirm_button(text, callback, **kwargs):
    """A destructive button that asks first: the first click turns it red ("Sure?"), the second acts."""
    widget = BarButton(text=text, kind="danger", **kwargs)

    def click(*_):
        if widget.kind == "danger":
            widget.text, widget.kind = "Sure?", "confirm"
        else:
            callback()

    widget.bind(on_release=click)
    return widget


class IconButton(HoverBehavior, ButtonBehavior, Widget):
    """A square transport button with a drawn icon: record, stop, play, pause or restart."""

    icon = StringProperty("play")
    tooltip = StringProperty("")
    highlight = ListProperty([0, 0, 0, 0])

    def __init__(self, **kwargs):
        super().__init__(size_hint_x=None, width=BAR_HEIGHT + dp(4), **kwargs)
        with self.canvas.before:
            self._bg_color = Color(0, 0, 0, 0)
            self._bg = Rectangle()
        self.bind(pos=self._draw, size=self._draw, icon=self._draw, disabled=self._draw, hovered=self._draw,
                  state=self._draw, highlight=self._draw)
        self.bind(hovered=self._refresh_tooltip, state=self._refresh_tooltip)
        self._draw()

    def _refresh_tooltip(self, *args):
        if self.tooltip and self.hovered and self.state == "normal":
            Tooltip.get().schedule(self, self.tooltip)
        else:
            Tooltip.get().hide(self)

    def _draw(self, *args):
        self._bg.pos, self._bg.size = self.pos, self.size
        self._bg_color.rgba = (self.highlight if self.highlight[3] else ACTIVE_COLOR if self.state == "down"
                               else HOVER_COLOR if self.hovered else (0, 0, 0, 0))
        self.canvas.clear()
        cx, cy, s = self.center_x, self.center_y, dp(13)
        alpha = 0.35 if self.disabled else 1
        with self.canvas:
            if self.icon == "record":
                Color(*theme.DANGER[:3], alpha) if not self.highlight[3] else Color(1, 1, 1, alpha)
                Ellipse(pos=(cx - s / 2, cy - s / 2), size=(s, s))
            elif self.icon == "stop":
                Color(1, 1, 1, alpha)
                Rectangle(pos=(cx - s * 0.42, cy - s * 0.42), size=(s * 0.84, s * 0.84))
            elif self.icon == "play":
                Color(*theme.TEXT[:3], alpha)
                Triangle(points=[cx - s * 0.4, cy - s / 2, cx - s * 0.4, cy + s / 2, cx + s * 0.5, cy])
            elif self.icon == "pause":
                Color(*theme.TEXT[:3], alpha)
                Rectangle(pos=(cx - s * 0.42, cy - s / 2), size=(s * 0.3, s))
                Rectangle(pos=(cx + s * 0.12, cy - s / 2), size=(s * 0.3, s))
            elif self.icon == "restart":
                Color(*theme.TEXT[:3], alpha)
                Rectangle(pos=(cx - s * 0.5, cy - s / 2), size=(s * 0.18, s))
                Triangle(points=[cx + s * 0.45, cy - s / 2, cx + s * 0.45, cy + s / 2, cx - s * 0.3, cy])


class Chip(BarButton):
    """An on/off toggle in the bar: gold when on (the app's one "selected" style)."""

    active = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(active=lambda *_: setattr(self, "kind", "selected" if self.active else "ghost"))


class StatusBar(BoxLayout):
    """Along the bottom: what to do next on the left (the same for every display), the state of
    things on the right."""

    HEIGHT = dp(30)

    def __init__(self, **kwargs):
        super().__init__(size_hint_y=None, height=self.HEIGHT, padding=(dp(14), 0), spacing=dp(16), **kwargs)
        paint_background(self, BAR_COLOR)
        self.hint = Label(markup=True, font_size=FONT_SIZE, color=DIM_TEXT_COLOR, halign="left", valign="middle",
                          shorten=True, shorten_from="right")
        self.hint.bind(size=lambda label, size: setattr(label, "text_size", size))
        self.status = Label(markup=True, font_size=FONT_SIZE, color=DIM_TEXT_COLOR, halign="right", valign="middle",
                            size_hint_x=None)
        self.status.bind(texture_size=lambda label, size: setattr(label, "width", size[0]))
        self.add_widget(self.hint)
        self.add_widget(self.status)

    def set(self, hint, status):
        if self.hint.text != hint:
            self.hint.text = hint
        if self.status.text != status:
            self.status.text = status


class MenuItem(HoverBehavior, ButtonBehavior, BoxLayout):
    """A dropdown row: action on the left, its hotkey on the right."""

    def __init__(self, text, shortcut="", **kwargs):
        super().__init__(size_hint_y=None, height=dp(32), padding=(dp(12), 0), **kwargs)
        paint_background(self, (0, 0, 0, 0))
        self.label = Label(text=text, font_size=FONT_SIZE, color=TEXT_COLOR, halign="left", valign="middle")
        self.label.bind(size=lambda label, size: setattr(label, "text_size", (size[0], None)))
        self.add_widget(self.label)
        self.shortcut = Label(text=shortcut, font_size=FONT_SIZE, color=DIM_TEXT_COLOR, halign="right",
                              size_hint_x=None, width=dp(64), text_size=(dp(64), None))
        self.add_widget(self.shortcut)
        self.bind(hovered=self._refresh_color, state=self._refresh_color)

    def _refresh_color(self, *args):
        self._bg_color.rgba = ACTIVE_COLOR if self.state == "down" else HOVER_COLOR if self.hovered else (0, 0, 0, 0)


class Menu(DropDown):
    def __init__(self, **kwargs):
        super().__init__(auto_width=False, width=dp(220), **kwargs)
        paint_background(self.container, PANEL_COLOR)
        self.container.padding = (0, dp(4))

    MAX_WIDTH = dp(380)

    def add_item(self, text, callback, shortcut=""):
        item = MenuItem(text, shortcut)
        item.bind(on_release=lambda *_: (self.dismiss(), callback()))
        self.add_widget(item)
        self.fit(item)
        return item

    def fit(self, item):
        """Widens the menu to fit an item's text on one line (up to MAX_WIDTH; longer is cut short)."""
        probe = Label(text=item.label.text, font_size=FONT_SIZE)
        probe.texture_update()
        needed = probe.texture_size[0] + item.shortcut.width + dp(12) * 2 + dp(16)
        self.width = min(self.MAX_WIDTH, max(self.width, needed))

    def add_separator(self):
        separator = Widget(size_hint_y=None, height=dp(9))
        with separator.canvas:
            Color(1, 1, 1, 0.1)
            line = Rectangle()
        separator.bind(pos=lambda w, *_: setattr(line, "pos", (w.x + dp(8), w.center_y)),
                       size=lambda w, *_: setattr(line, "size", (w.width - dp(16), 1)))
        self.add_widget(separator)


class Option(SpinnerOption):
    def __init__(self, **kwargs):
        super().__init__(background_normal="", background_color=PANEL_COLOR, color=TEXT_COLOR,
                         font_size=FONT_SIZE, height=dp(32), **kwargs)


class Picker(Spinner):
    """A dropdown, with a caret so it reads as one."""

    def __init__(self, **kwargs):
        super().__init__(option_cls=Option, font_size=FONT_SIZE, color=TEXT_COLOR, background_normal="",
                         background_color=(*theme.SURFACE_RAISED, 1), halign="left", valign="middle",
                         padding=(dp(10), 0), **kwargs)
        self.bind(size=lambda w, size: setattr(w, "text_size", (size[0] - dp(28), size[1])))
        with self.canvas.after:
            Color(*theme.TEXT_DIM)
            self._caret = Triangle()
        self.bind(pos=self._place_caret, size=self._place_caret)

    def _place_caret(self, *args):
        x, y = self.right - dp(16), self.center_y
        self._caret.points = [x - dp(5), y + dp(3), x + dp(5), y + dp(3), x, y - dp(3)]


def dropdown(values, selected, on_select):
    spinner = Picker(text=selected, values=values, size_hint_y=None, height=dp(32))
    spinner.bind(text=lambda _, text: on_select(text))
    return spinner


class Stepper(BoxLayout):
    """‹ value ›: steps through an ordered list of choices."""

    def __init__(self, choices, current, on_change, **kwargs):
        super().__init__(spacing=dp(2), **kwargs)
        self.choices, self.on_change = choices, on_change
        self.index = next((i for i, (_, value) in enumerate(choices) if value == current), 0)
        self.back = button("\u2039", lambda: self._step(-1), size_hint_x=None, width=dp(34), font_size=theme.TITLE)
        self.label = Label(font_size=FONT_SIZE, color=TEXT_COLOR)
        with self.label.canvas.before:
            Color(*theme.SURFACE_RAISED)
            background = Rectangle()
        self.label.bind(pos=lambda w, pos: setattr(background, "pos", pos),
                        size=lambda w, size: setattr(background, "size", size))
        self.forward = button("\u203a", lambda: self._step(1), size_hint_x=None, width=dp(34), font_size=theme.TITLE)
        for widget in (self.back, self.label, self.forward):
            self.add_widget(widget)
        self._show()

    def _step(self, delta):
        index = max(0, min(len(self.choices) - 1, self.index + delta))
        if index != self.index:
            self.index = index
            self._show()
            self.on_change(self.choices[index][1])

    def _show(self):
        self.label.text = self.choices[self.index][0]
        self.back.disabled = self.index == 0
        self.forward.disabled = self.index == len(self.choices) - 1


class OnOffSwitch(ButtonBehavior, Widget):
    """An on/off switch in the app's colours: a pill, gold when on, with its knob at that end."""

    active = BooleanProperty(False)

    def __init__(self, active, on_change, **kwargs):
        super().__init__(size_hint=(None, None), size=(dp(46), dp(24)), **kwargs)
        with self.canvas:
            self._track_color = Color()
            self._track = RoundedRectangle(radius=[dp(12)])
            Color(1, 1, 1, 1)
            self._knob = Ellipse()
        self.bind(pos=self._draw, size=self._draw, active=self._draw)
        self.bind(on_release=lambda *_: setattr(self, "active", not self.active))
        self.bind(active=lambda _, value: on_change(value))
        self.active = active
        self._draw()

    def _draw(self, *args):
        self._track_color.rgba = (*theme.ACCENT, 1) if self.active else (1, 1, 1, 0.18)
        self._track.pos, self._track.size = self.pos, self.size
        knob = self.height - dp(6)
        x = self.right - knob - dp(3) if self.active else self.x + dp(3)
        self._knob.pos, self._knob.size = (x, self.y + dp(3)), (knob, knob)


def section_title(text, width):
    return Label(text=text.upper(), font_size=theme.CAPTION, bold=True, color=(*theme.ACCENT, 1), halign="left",
                 valign="bottom", size_hint_y=None, height=dp(30), text_size=(width, dp(30)))


MINUS = "\u2212"  # A real minus sign; "-" renders as a thin dash on a button.


class Toggle(ToggleButton):
    def __init__(self, **kwargs):
        super().__init__(background_normal="", background_down="", background_disabled_normal="",
                         background_disabled_down="", font_size=FONT_SIZE, color=TEXT_COLOR,
                         disabled_color=DIM_TEXT_COLOR, **kwargs)
        self.bind(state=self._refresh_color, disabled=self._refresh_color)
        self._refresh_color()

    def _refresh_color(self, *args):
        if self.disabled:
            self.background_color = (1, 1, 1, 0.03)
        else:
            self.background_color = (*theme.ACCENT, 1) if self.state == "down" else (1, 1, 1, 0.08)
        self.color = theme.TEXT_ON_ACCENT if self.state == "down" else TEXT_COLOR
