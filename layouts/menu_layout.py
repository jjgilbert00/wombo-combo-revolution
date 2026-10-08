import os

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Rectangle, RoundedRectangle, Triangle
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, ListProperty, StringProperty
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.dropdown import DropDown
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.scrollview import ScrollView
from kivy.uix.slider import Slider
from kivy.uix.spinner import Spinner, SpinnerOption
from kivy.uix.switch import Switch
from kivy.uix.textinput import TextInput
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
MENU_TIPS = {
    "File": "Open a recording (or drop one on the window), save, and export videos",
    "Edit": "Notes, key inputs and attempts. Select frames in the input list first (right-click for a menu)",
    "View": "Choose which lanes to show, hide notes, overlay mode",
    "Settings": "Controller, video capture, lead-in and attempt history",
    "Record": "Record a new take from your controller (F8, even while the game has focus). "
              "Also captures the screen if Record video is on in Settings",
    "Play": "Play or pause (Space in this window, F6 / F7 in game)",
    "Restart": "Back to the first frame (Home in this window, F5 in game). "
               "While practising this starts a fresh attempt",
    "Loop": "Loop: the recording repeats, and each pass is kept as a recent attempt",
    "Review": "Review: playing replays your last attempt against the recording. F4 switches",
    "Demo": "Watch the combo in game: a virtual controller plays the recording, either as recorded or cleaned "
            "down to its key inputs (Shift+F6 / Shift+F7, even while the game has focus). Needs vgamepad; see the "
            "user guide",
    "Practice": "Practice: playing scores your controller against the recording. F4 switches",
}
DISPLAY_NAMES = {"list": "Input list", "lanes": "Arrow lanes", "ring": "Ring"}
LANE_MENU_ITEMS = [("meter", "Frame meter"), ("target", "Recording"), ("keys", "Key inputs"),
                   ("attempt", "Your attempt"), ("saved", "Saved attempts"), ("recent", "Recent attempts")]


def _paint_background(widget, color):
    with widget.canvas.before:
        widget._bg_color = Color(*color)
        widget._bg_rect = Rectangle(pos=widget.pos, size=widget.size)
    widget.bind(pos=lambda w, pos: setattr(w._bg_rect, "pos", pos))
    widget.bind(size=lambda w, size: setattr(w._bg_rect, "size", size))


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
        _paint_background(self, (0.05, 0.05, 0.07, 0.96))
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
        _paint_background(self, BAR_COLOR)
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
        _paint_background(self, (0, 0, 0, 0))
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
        _paint_background(self.container, PANEL_COLOR)
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


class MenuBar(BoxLayout):
    """Menus and transport controls on the left, live status on the right."""

    def __init__(self, app, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, height=BAR_HEIGHT, padding=(dp(4), 0), **kwargs)
        self.app = app
        _paint_background(self, BAR_COLOR)

        file_menu = Menu()
        self.file_menu = file_menu
        self.set_recent([])

        edit_menu = Menu()
        # The selection, then attempts, then whole-track changes last so they're hard to hit by accident.
        edit_menu.add_item("Add note to selection", app.add_note, "N")
        edit_menu.add_item("Mark key input", app.mark_key_input, "K")
        edit_menu.add_item("Remap buttons...", app.remap_buttons)
        edit_menu.add_item("Game actions...", app.edit_game_actions)
        edit_menu.add_separator()
        edit_menu.add_item("Save attempt", app.save_attempt, "S")
        edit_menu.add_item("Attempts...", app.open_attempts, "A")
        edit_menu.add_item("Clear attempt", app.clear_attempt)
        edit_menu.add_separator()
        edit_menu.add_item("Clean track (presses only)", app.clean_track)
        edit_menu.add_item("Clear track", app.clear_track)

        view_menu = Menu()
        # The three displays, the current one marked; F3 moves to the next from anywhere.
        self.display_items = {mode: view_menu.add_item(name, lambda mode=mode: app.show_display(mode))
                              for mode, name in DISPLAY_NAMES.items()}
        view_menu.add_item("Next display", app.toggle_display, "F3")
        view_menu.add_separator()
        view_menu.add_item("Overlay mode", app.toggle_overlay, "F2")
        self.see_through_item = view_menu.add_item("See-through overlay", app.toggle_see_through)
        self.notes_item = view_menu.add_item("Hide notes", app.toggle_notes, "Shift+F3")
        self.actions_item = view_menu.add_item("Show game actions", app.toggle_actions)
        self.next_item = view_menu.add_item("Hide up-next panel", app.toggle_up_next)
        view_menu.add_item("Help and keys", app.show_help, "F1")
        view_menu.add_separator()
        # Input list lanes, each shown or hidden; the right column says which.
        self.lane_items = {name: view_menu.add_item(text, lambda name=name: app.toggle_lane(name))
                           for name, text in LANE_MENU_ITEMS}
        view_menu.add_separator()
        view_menu.add_widget(self._opacity_row())
        view_menu.bind(on_dismiss=lambda *_: app.preview_opacity(False))

        # Kivy holds bound methods weakly, so the menus must be kept alive here.
        self.menus = {"File": file_menu, "Edit": edit_menu, "View": view_menu}
        for text, menu in self.menus.items():
            button = BarButton(text=text, tooltip=MENU_TIPS[text])
            button.bind(on_release=menu.open)
            self.add_widget(button)
        settings_button = BarButton(text="Settings", tooltip=MENU_TIPS["Settings"])
        settings_button.bind(on_release=lambda *_: app.open_settings_popup())
        self.add_widget(settings_button)

        self.add_widget(self._divider())
        self.record_button = self._icon("record", "Record", app.toggle_recording)
        self.play_button = self._icon("play", "Play", app.toggle_playback)
        self._icon("restart", "Restart", app.restart_playback)
        self.add_widget(self._divider())
        self.loop_button = Chip(text="Loop", tooltip=MENU_TIPS["Loop"])
        self.loop_button.bind(on_release=lambda *_: app.toggle_loop())
        self.add_widget(self.loop_button)
        self.add_widget(Widget(size_hint_x=None, width=dp(10)))
        # Practice | Review: which one playing does. Clicking the other one switches.
        self.practicing = True
        self.practice_button = Chip(text="Practice", tooltip=MENU_TIPS["Practice"])
        self.practice_button.bind(on_release=lambda *_: self.practicing or app.toggle_practice())
        self.review_button = Chip(text="Review", tooltip=MENU_TIPS["Review"])
        self.review_button.bind(on_release=lambda *_: self.practicing and app.toggle_practice())
        self.add_widget(self.practice_button)
        self.add_widget(self.review_button)
        self.add_widget(self._divider())
        demo_menu = Menu()
        demo_menu.add_item("Demo the recording", app.demo_recording, "Shift+F6")
        demo_menu.add_item("Demo the key inputs", app.demo_key_inputs, "Shift+F7")
        demo_menu.add_separator()
        demo_menu.add_item("Stop the demo", app.stop_demo, "F7")
        self.menus["Demo"] = demo_menu
        self.demo_button = BarButton(text="Demo", tooltip=MENU_TIPS["Demo"])
        self.demo_button.bind(on_release=demo_menu.open)
        self.add_widget(self.demo_button)

        self.add_widget(Widget())  # The rest of the bar stays clear.

    def _icon(self, icon, tip, callback):
        widget = IconButton(icon=icon, tooltip=MENU_TIPS[tip])
        widget.bind(on_release=lambda *_: callback())
        self.add_widget(widget)
        return widget

    def _divider(self):
        divider = Widget(size_hint_x=None, width=dp(17))
        with divider.canvas:
            Color(1, 1, 1, 0.12)
            line = Rectangle()
        divider.bind(pos=lambda w, *_: setattr(line, "pos", (w.center_x, w.y + dp(8))),
                     size=lambda w, *_: setattr(line, "size", (1, w.height - dp(16))))
        return divider

    def _opacity_row(self):
        row = BoxLayout(size_hint_y=None, height=dp(36), padding=(dp(12), 0))
        row.add_widget(Label(text="Overlay opacity", font_size=FONT_SIZE, color=TEXT_COLOR, size_hint_x=None,
                             width=dp(110), halign="left", text_size=(dp(110), None)))
        slider = Slider(min=0.2, max=1.0, value=self.app.get_opacity(), cursor_size=(dp(16), dp(16)))
        slider.bind(value=lambda _, value: self.app.set_opacity(value))
        slider.bind(on_touch_down=lambda s, touch: s.collide_point(*touch.pos) and self.app.preview_opacity(True))
        row.add_widget(slider)
        return row

    def set_recent(self, paths):
        """Rebuilds the File menu, listing recently opened recordings right under Open, then the samples."""
        menu, app = self.file_menu, self.app
        menu.clear_widgets()
        menu.width = dp(220)
        menu.add_item("Open recording...", app.open_track, "Ctrl+O")
        for path in paths:
            name = os.path.splitext(os.path.basename(path))[0]
            item = menu.add_item(name, lambda path=path: app.open_track(path))
            item.label.color = DIM_TEXT_COLOR
            item.label.shorten = True
        samples = app.sample_recordings()
        if samples:
            menu.add_separator()
            for path in samples:
                # "SF6 Ryu - st.MP, cr.MP, ..." is listed as "Sample: SF6 Ryu"; the title bar names the combo.
                name = os.path.splitext(os.path.basename(path))[0].split(" - ")[0]
                menu.add_item(f"Sample: {name}", lambda path=path: app.open_track(path)).label.shorten = True
        menu.add_separator()
        menu.add_item("Save", app.save, "Ctrl+S")
        menu.add_item("Save recording as...", app.save_recording, "F12")
        menu.add_separator()
        menu.add_item("Export overlay video...", app.export_overlay_video)
        menu.add_item("Export input video...", app.export_input_video)
        menu.add_separator()
        menu.add_item("Quit", app.quit)

    def set_lanes_shown(self, shown):
        for name, item in self.lane_items.items():
            item.shortcut.text = "shown" if name in shown else "hidden"
            item.label.color = TEXT_COLOR if name in shown else DIM_TEXT_COLOR

    def set_notes_visible(self, visible):
        self.notes_item.label.text = "Hide notes" if visible else "Show notes"

    def set_see_through(self, on):
        """Overlay mode with only what's drawn covering the game (on), or the whole window (off)."""
        self.see_through_item.shortcut.text = "on" if on else "off"

    def set_up_next_visible(self, visible):
        self.next_item.label.text = "Hide up-next panel" if visible else "Show up-next panel"

    def set_actions_visible(self, visible):
        self.actions_item.label.text = "Show controller buttons" if visible else "Show game actions"

    def set_display_mode(self, mode):
        for item_mode, item in self.display_items.items():
            item.shortcut.text = "showing" if item_mode == mode else ""
            item.label.color = TEXT_COLOR if item_mode == mode else DIM_TEXT_COLOR

    def update(self, recording, playing, looping, practicing, demoing=False):
        self.record_button.icon = "stop" if recording else "record"
        self.record_button.highlight = RECORD_COLOR if recording else (0, 0, 0, 0)
        self.record_button.tooltip = "Stop recording (F8)" if recording else MENU_TIPS["Record"]
        self.play_button.icon = "pause" if playing else "play"
        self.play_button.disabled = recording
        self.loop_button.active = looping
        self.practicing = practicing
        self.practice_button.active = practicing
        self.review_button.active = not practicing
        self.demo_button.highlight = DEMO_COLOR if demoing else (0, 0, 0, 0)


class _Option(SpinnerOption):
    def __init__(self, **kwargs):
        super().__init__(background_normal="", background_color=PANEL_COLOR, color=TEXT_COLOR,
                         font_size=FONT_SIZE, height=dp(32), **kwargs)


class _Picker(Spinner):
    """A dropdown, with a caret so it reads as one."""

    def __init__(self, **kwargs):
        super().__init__(option_cls=_Option, font_size=FONT_SIZE, color=TEXT_COLOR, background_normal="",
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


def _spinner(values, selected, on_select):
    spinner = _Picker(text=selected, values=values, size_hint_y=None, height=dp(32))
    spinner.bind(text=lambda _, text: on_select(text))
    return spinner


class _Stepper(BoxLayout):
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


class _Switch(ButtonBehavior, Widget):
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


def _section_title(text, width):
    return Label(text=text.upper(), font_size=theme.CAPTION, bold=True, color=(*theme.ACCENT, 1), halign="left",
                 valign="bottom", size_hint_y=None, height=dp(30), text_size=(width, dp(30)))


class SettingsPopup(ModalView):
    """Settings in sections, laid out in columns. columns is [[(section title, rows)]]; a row is
    (label, kind, choices, current value, on_change) where kind is "pick" (a dropdown, for named
    choices), "step" (‹ value ›, for ordered ones) or "switch" (on/off; choices unused)."""

    ROW = dp(40)
    COLUMN_WIDTH = dp(400)
    LABEL_WIDTH = dp(170)

    def __init__(self, columns, **kwargs):
        rows_height = max(sum(dp(30) + self.ROW * len(rows) for _, rows in column) for column in columns)
        super().__init__(size_hint=(None, None),
                         size=(self.COLUMN_WIDTH * len(columns) + dp(32) * len(columns) + dp(8),
                               rows_height + dp(130)),
                         background="", background_color=(0, 0, 0, 0.5), **kwargs)
        panel = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(8))
        _paint_background(panel, PANEL_COLOR)
        panel.add_widget(Label(text="Settings", font_size=theme.TITLE, bold=True, color=TEXT_COLOR, size_hint_y=None,
                               height=dp(28), halign="left", valign="middle", text_size=(self.width - dp(40), dp(28))))
        body = BoxLayout(spacing=dp(32))
        for column in columns:
            box = BoxLayout(orientation="vertical", size_hint_x=None, width=self.COLUMN_WIDTH)
            for title, rows in column:
                box.add_widget(_section_title(title, self.COLUMN_WIDTH))
                for label, kind, choices, current, on_change in rows:
                    box.add_widget(self._row(label, kind, choices, current, on_change))
            box.add_widget(Widget())
            body.add_widget(box)
        panel.add_widget(body)
        actions = BoxLayout(size_hint_y=None, height=dp(34))
        actions.add_widget(Label(text="Changes apply right away.", font_size=theme.CAPTION, color=DIM_TEXT_COLOR,
                                 halign="left", valign="middle", size_hint_x=None, width=dp(300),
                                 text_size=(dp(300), dp(34))))
        actions.add_widget(Widget())
        actions.add_widget(button("Done", self.dismiss, "primary"))
        panel.add_widget(actions)
        self.add_widget(panel)

    def _row(self, label, kind, choices, current, on_change):
        row = BoxLayout(size_hint_y=None, height=self.ROW, padding=(0, dp(4)), spacing=dp(12))
        row.add_widget(Label(text=label, font_size=FONT_SIZE, color=TEXT_COLOR, halign="left", valign="middle",
                             size_hint_x=None, width=self.LABEL_WIDTH, text_size=(self.LABEL_WIDTH, None)))
        if kind == "switch":
            holder = AnchorLayout(anchor_x="left", anchor_y="center")
            holder.add_widget(_Switch(current, on_change))
            row.add_widget(holder)
        elif kind == "step":
            row.add_widget(_Stepper(choices, current, on_change))
        else:
            labels = [text for text, _ in choices]
            values = dict(choices)
            selected = next((text for text, value in choices if value == current), labels[0])
            picker = _spinner(labels, selected, lambda text, cb=on_change, v=values: cb(v[text]))
            picker.size_hint_y = 1
            row.add_widget(picker)
        return row


class HelpPopup(ModalView):
    """Help in two tabs. Getting started: the steps, then legends for what the colours mean. Keys:
    groups of (key, what it does, works in game) in columns. on_manual opens the user guide."""

    KEY_WIDTH = dp(110)
    COLUMN_WIDTH = dp(440)
    ROW = dp(26)

    def __init__(self, steps, legends, key_columns, on_manual, **kwargs):
        rows = max(sum(len(group) + 1.5 for _, group in column) for column in key_columns)
        super().__init__(size_hint=(None, None), size=(dp(960), dp(150) + self.ROW * rows),
                         background="", background_color=(0, 0, 0, 0.5), **kwargs)
        panel = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(10))
        _paint_background(panel, PANEL_COLOR)
        tabs = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(4))
        self.pages = {"Getting started": self._getting_started(steps, legends), "Keys": self._keys(key_columns)}
        self.tab_buttons = {}
        for name in self.pages:
            tab = Chip(text=name)
            tab.bind(on_release=lambda *_, name=name: self.show(name))
            self.tab_buttons[name] = tab
            tabs.add_widget(tab)
        tabs.add_widget(Widget())
        panel.add_widget(tabs)
        self.page_holder = BoxLayout()
        panel.add_widget(self.page_holder)
        actions = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(8))
        actions.add_widget(self._label("Hover over any button for a tip. The user guide covers everything in detail.",
                                       theme.CAPTION, DIM_TEXT_COLOR, dp(34)))
        actions.add_widget(button("Open user guide", lambda: (self.dismiss(), on_manual())))
        actions.add_widget(button("Close", self.dismiss, "primary"))
        panel.add_widget(actions)
        self.add_widget(panel)
        self.show("Getting started")

    def show(self, name):
        self.page_holder.clear_widgets()
        self.page_holder.add_widget(self.pages[name])
        for tab_name, tab in self.tab_buttons.items():
            tab.active = tab_name == name

    def _getting_started(self, steps, legends):
        page = BoxLayout(orientation="vertical", spacing=dp(6))
        for number, step in enumerate(steps, 1):
            page.add_widget(self._label(f"[b]{number}.[/b]  {step}", FONT_SIZE, TEXT_COLOR, dp(30), markup=True))
        body = BoxLayout(spacing=dp(32), padding=(0, dp(8), 0, 0))
        for title, items in legends:
            box = BoxLayout(orientation="vertical", spacing=dp(2))
            box.add_widget(_section_title(title, self.COLUMN_WIDTH))
            for color, name, description in items:
                row = BoxLayout(size_hint_y=None, height=self.ROW, spacing=dp(10))
                swatch = Widget(size_hint=(None, None), size=(dp(28), dp(14)))
                with swatch.canvas:
                    Color(*color[:3])
                    rect = Rectangle(size=swatch.size)
                swatch.bind(pos=lambda w, pos, r=rect: setattr(r, "pos", pos),
                            size=lambda w, size, r=rect: setattr(r, "size", size))
                holder = AnchorLayout(size_hint_x=None, width=dp(28))
                holder.add_widget(swatch)
                row.add_widget(holder)
                row.add_widget(Label(text=name, font_size=FONT_SIZE, bold=True, color=TEXT_COLOR, halign="left",
                                     valign="middle", size_hint_x=None, width=dp(90), text_size=(dp(90), self.ROW)))
                row.add_widget(self._label(description, FONT_SIZE, DIM_TEXT_COLOR, self.ROW))
                box.add_widget(row)
            box.add_widget(Widget())
            body.add_widget(box)
        page.add_widget(body)
        return page

    def _keys(self, key_columns):
        page = BoxLayout(spacing=dp(32))
        for column in key_columns:
            box = BoxLayout(orientation="vertical", spacing=dp(1))
            for title, group in column:
                box.add_widget(_section_title(title, self.COLUMN_WIDTH))
                for key, description, in_game in group:
                    row = BoxLayout(size_hint_y=None, height=self.ROW)
                    row.add_widget(Label(text=key, font_size=FONT_SIZE, bold=True, color=(*theme.ACCENT, 1),
                                         size_hint_x=None, width=self.KEY_WIDTH, halign="left", valign="middle",
                                         text_size=(self.KEY_WIDTH, self.ROW)))
                    text = description + ("   " + theme.markup("in game too", theme.TEXT_FAINT) if in_game else "")
                    row.add_widget(self._label(text, FONT_SIZE, TEXT_COLOR, self.ROW, markup=True))
                    box.add_widget(row)
            box.add_widget(Widget())
            page.add_widget(box)
        return page

    @staticmethod
    def _label(text, font_size, color, height, bold=False, markup=False, valign="middle"):
        label = Label(text=text, font_size=font_size, color=color, bold=bold, markup=markup, size_hint_y=None,
                      height=height, halign="left", valign=valign, shorten=True)
        label.bind(size=lambda l, size: setattr(l, "text_size", size))
        return label


class NotePopup(ModalView):
    """Edits a note's text. on_save(text) is called with the new text; saving empty text counts as a
    delete. on_delete is only offered when editing an existing note."""

    def __init__(self, title, text, on_save, on_delete=None, **kwargs):
        super().__init__(size_hint=(None, None), size=(dp(420), dp(150)), background="",
                         background_color=(0, 0, 0, 0.5), **kwargs)
        panel = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))
        _paint_background(panel, PANEL_COLOR)
        panel.add_widget(Label(text=title, font_size=theme.TITLE, bold=True, color=TEXT_COLOR, size_hint_y=None,
                               height=dp(22), halign="left", text_size=(dp(388), None)))
        self.input = TextInput(text=text, multiline=False, size_hint_y=None, height=dp(34), font_size=FONT_SIZE,
                               background_color=(1, 1, 1, 0.08), foreground_color=TEXT_COLOR,
                               cursor_color=TEXT_COLOR, hint_text="e.g. hit confirm here")
        self.input.bind(on_text_validate=lambda *_: self._save(on_save))
        panel.add_widget(self.input)

        buttons = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(8))
        if on_delete:
            buttons.add_widget(confirm_button("Delete", lambda: (self.dismiss(), on_delete())))
        buttons.add_widget(Widget())
        cancel = button("Cancel", self.dismiss, "ghost")
        save = button("Save", lambda: self._save(on_save), "primary")
        buttons.add_widget(cancel)
        buttons.add_widget(save)
        panel.add_widget(buttons)
        self.add_widget(panel)
        self.bind(on_open=lambda *_: setattr(self.input, "focus", True))

    def _save(self, on_save):
        self.dismiss()
        on_save(self.input.text.strip())


MINUS = "\u2212"  # A real minus sign; "-" renders as a thin dash on a button.

class _Toggle(ToggleButton):
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


class KeyInputPopup(ModalView):
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
        _paint_background(panel, PANEL_COLOR)
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
            toggle = _Toggle(text=text, group="kind", allow_no_selection=False,
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
                toggle = _Toggle(text=str(value), group="direction",
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
            toggle = _Toggle(text=name, state="down" if name in self.key_input["buttons"] else "normal")
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


class AttemptsPopup(ModalView):
    """Manages saved attempts and recent runs: rename, show or hide saved ones in the input list,
    save a recent run, replay any of them against the target, or delete. Deleting takes a second
    click. `app` provides attempts_overview() and the actions; the list is rebuilt after each one."""

    ROW_HEIGHT = dp(32)

    def __init__(self, app, **kwargs):
        super().__init__(size_hint=(None, None), size=(dp(760), dp(560)), background="",
                         background_color=(0, 0, 0, 0.5), **kwargs)
        self.app = app
        panel = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))
        _paint_background(panel, PANEL_COLOR)
        header = BoxLayout(size_hint_y=None, height=dp(24))
        header.add_widget(Label(text="Attempts", font_size=theme.TITLE, bold=True, color=TEXT_COLOR, halign="left",
                                valign="middle", size_hint_x=None, width=dp(120), text_size=(dp(120), dp(24))))
        header.add_widget(Label(text="Saved attempts are kept in the track's file. Replay plays one against the "
                                     "recording; F4 goes back to practice.", font_size=theme.CAPTION, color=DIM_TEXT_COLOR,
                                halign="right", valign="middle", text_size=(dp(600), dp(24))))
        panel.add_widget(header)
        self.rows = GridLayout(cols=1, size_hint_y=None, spacing=dp(4))
        self.rows.bind(minimum_height=self.rows.setter("height"))
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(6))
        scroll.add_widget(self.rows)
        panel.add_widget(scroll)
        actions = BoxLayout(size_hint_y=None, height=self.ROW_HEIGHT)
        actions.add_widget(Widget())
        actions.add_widget(button("Close", self.dismiss, "primary"))
        panel.add_widget(actions)
        self.add_widget(panel)
        self.refresh()

    def refresh(self):
        self.rows.clear_widgets()
        overview = self.app.attempts_overview()
        self._section("Saved", overview["saved"], "Nothing saved yet: press S to save the attempt on screen.")
        self._section("Recent (this session, newest first)", overview["recent"],
                      "No runs yet: practice (F4) and play; each pass is kept here.")

    def _section(self, title, attempts, empty_text):
        self.rows.add_widget(Label(text=title, font_size=FONT_SIZE, bold=True, color=TEXT_COLOR, halign="left",
                                   valign="bottom", size_hint_y=None, height=dp(28), text_size=(dp(720), dp(28))))
        if not attempts:
            empty = self._text(empty_text, DIM_TEXT_COLOR, None)
            empty.size_hint_y, empty.height = None, self.ROW_HEIGHT
            self.rows.add_widget(empty)
        for attempt in attempts:
            self.rows.add_widget(self._row(attempt))

    def _text(self, text, color, width):
        label = Label(text=text, font_size=FONT_SIZE, color=color, halign="left", valign="middle",
                      size_hint_x=None if width else 1, width=width or 100, shorten=True)
        label.bind(size=lambda l, size: setattr(l, "text_size", size))
        return label

    def _button(self, text, callback):
        return button(text, callback)

    def _row(self, attempt):
        kind, attempt_id = attempt["kind"], attempt["id"]
        row = BoxLayout(size_hint_y=None, height=self.ROW_HEIGHT, spacing=dp(8))
        if kind == "saved":
            name = TextInput(text=attempt["name"], multiline=False, font_size=FONT_SIZE, size_hint_x=None,
                             width=dp(220), background_color=(1, 1, 1, 0.08), foreground_color=TEXT_COLOR,
                             cursor_color=TEXT_COLOR, padding=(dp(6), dp(7)))
            rename = lambda *_: self.app.rename_saved(attempt_id, name.text) if name.text.strip() else None
            name.bind(on_text_validate=rename, focus=lambda _, focused: None if focused else rename())
            row.add_widget(name)
        else:
            row.add_widget(self._text(attempt["name"], TEXT_COLOR, dp(220)))
        row.add_widget(self._text(attempt["score"], TEXT_COLOR, dp(110)))
        row.add_widget(self._text(attempt["when"], DIM_TEXT_COLOR, dp(110)))
        row.add_widget(Widget())
        if kind == "saved":
            shown = _Toggle(text="Shown" if attempt["shown"] else "Hidden", size_hint_x=None, width=dp(70),
                            state="down" if attempt["shown"] else "normal")
            shown.bind(state=lambda t, state: (self.app.show_saved(attempt_id, state == "down"),
                                               setattr(t, "text", "Shown" if state == "down" else "Hidden")))
            row.add_widget(shown)
        else:
            row.add_widget(self._button("Save", lambda: (self.app.save_run(attempt_id), self.refresh())))
        row.add_widget(self._button("Replay", lambda: (self.dismiss(), self.app.replay_attempt(kind, attempt_id))))
        row.add_widget(confirm_button("Delete", lambda: (self.app.delete_attempt(kind, attempt_id), self.refresh())))
        return row


class ButtonMapPopup(ModalView):
    """Maps each recorded button to one of the player's. Picking a button that another recorded
    button already uses swaps the two, so the map stays one-to-one. Changes apply at once through
    on_change(mapping); used is how many times each recorded button is pressed in the recording."""

    ROW_HEIGHT = dp(36)

    def __init__(self, mapping, used, on_change, icon=None, **kwargs):
        from images import get_standard_button_icon
        icon = icon or (lambda name: get_standard_button_icon("XGamepad", "Alt", name))
        super().__init__(size_hint=(None, None), size=(dp(520), dp(150) + self.ROW_HEIGHT * len(mapping)),
                         background="", background_color=(0, 0, 0, 0.5), **kwargs)
        self.mapping = dict(mapping)
        self.on_change = on_change
        self.spinners = {}
        self._updating = False
        panel = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(6))
        _paint_background(panel, PANEL_COLOR)
        panel.add_widget(Label(text="Remap buttons for this recording", font_size=theme.TITLE, bold=True, color=TEXT_COLOR,
                               size_hint_y=None, height=dp(24), halign="left", text_size=(dp(488), None)))
        panel.add_widget(Label(text="Pick the button you press for each recorded one. The list, scoring and demos "
                                    "follow your buttons.", font_size=theme.CAPTION, color=DIM_TEXT_COLOR, size_hint_y=None,
                               height=dp(32), halign="left", valign="middle", text_size=(dp(488), dp(32))))
        for recorded in mapping:
            row = BoxLayout(size_hint_y=None, height=self.ROW_HEIGHT, spacing=dp(10))
            row.add_widget(Image(source=icon(recorded), size_hint_x=None, width=dp(28)))
            count = used.get(recorded, 0)
            row.add_widget(Label(text=f"Recorded {recorded}", font_size=FONT_SIZE, color=TEXT_COLOR if count else
                                 DIM_TEXT_COLOR, halign="left", valign="middle", size_hint_x=None, width=dp(120),
                                 text_size=(dp(120), self.ROW_HEIGHT)))
            row.add_widget(Label(text=f"pressed {count}x" if count else "not used", font_size=theme.CAPTION,
                                 color=DIM_TEXT_COLOR, halign="left", valign="middle", size_hint_x=None, width=dp(80),
                                 text_size=(dp(80), self.ROW_HEIGHT)))
            row.add_widget(Label(text="->", font_size=FONT_SIZE, color=DIM_TEXT_COLOR, size_hint_x=None,
                                 width=dp(24)))
            spinner = _spinner(list(mapping), self.mapping[recorded],
                               lambda theirs, recorded=recorded: self._choose(recorded, theirs))
            spinner.size_hint_y = 1
            self.spinners[recorded] = spinner
            row.add_widget(spinner)
            panel.add_widget(row)
        actions = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(8))
        actions.add_widget(button("Reset to recorded", self._reset))
        actions.add_widget(Widget())
        actions.add_widget(button("Done", self.dismiss, "primary"))
        panel.add_widget(actions)
        self.add_widget(panel)

    def _choose(self, recorded, theirs):
        if self._updating or self.mapping[recorded] == theirs:
            return
        # Whichever recorded button had this one takes over the button being replaced.
        other = next(button for button, mapped in self.mapping.items() if mapped == theirs)
        self.mapping[other], self.mapping[recorded] = self.mapping[recorded], theirs
        self._apply()

    def _reset(self):
        self.mapping = {button: button for button in self.mapping}
        self._apply()

    def _apply(self):
        self._updating = True
        for recorded, spinner in self.spinners.items():
            spinner.text = self.mapping[recorded]
        self._updating = False
        self.on_change(dict(self.mapping))


NO_ACTION = "None"


class GameActionsPopup(ModalView):
    """Picks the recording's game and which recorded button is which of its actions, so the input
    list can show actions (a medium punch, a Drive Impact) instead of buttons. Changes apply at once
    through on_change(game, layout)."""

    ROW_HEIGHT = dp(34)

    def __init__(self, game_names, game, layout, actions, default_layouts, used, on_change, **kwargs):
        from images import get_standard_button_icon
        super().__init__(size_hint=(None, None), size=(dp(520), dp(200) + self.ROW_HEIGHT * 8),
                         background="", background_color=(0, 0, 0, 0.5), **kwargs)
        self.game_names, self.actions, self.default_layouts = game_names, actions, default_layouts
        self.game, self.layout = game, dict(layout)
        self.on_change = on_change
        self.spinners = {}
        self._updating = False
        panel = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(6))
        _paint_background(panel, PANEL_COLOR)
        panel.add_widget(Label(text="Game actions for this recording", font_size=theme.TITLE, bold=True, color=TEXT_COLOR,
                               size_hint_y=None, height=dp(24), halign="left", text_size=(dp(488), None)))
        panel.add_widget(Label(text="Which action each recorded button is, in the layout it was recorded with. "
                                    "View > Show game actions switches the list to them.", font_size=theme.CAPTION,
                               color=DIM_TEXT_COLOR, size_hint_y=None, height=dp(32), halign="left", valign="middle",
                               text_size=(dp(488), dp(32))))
        names = [NO_ACTION] + list(game_names.values())
        row = BoxLayout(size_hint_y=None, height=self.ROW_HEIGHT, spacing=dp(10))
        row.add_widget(Label(text="Game", font_size=FONT_SIZE, color=TEXT_COLOR, halign="left", valign="middle",
                             size_hint_x=None, width=dp(120), text_size=(dp(120), self.ROW_HEIGHT)))
        self.game_spinner = _spinner(names, game_names.get(game, NO_ACTION), self._choose_game)
        self.game_spinner.size_hint_y = 1
        row.add_widget(self.game_spinner)
        panel.add_widget(row)
        for recorded in ("X", "Y", "A", "B", "LB", "RB", "LT", "RT"):
            row = BoxLayout(size_hint_y=None, height=self.ROW_HEIGHT, spacing=dp(10))
            row.add_widget(Image(source=get_standard_button_icon("XGamepad", "Alt", recorded), size_hint_x=None,
                                 width=dp(26)))
            count = used.get(recorded, 0)
            row.add_widget(Label(text=f"Recorded {recorded}", font_size=FONT_SIZE,
                                 color=TEXT_COLOR if count else DIM_TEXT_COLOR, halign="left", valign="middle",
                                 size_hint_x=None, width=dp(120), text_size=(dp(120), self.ROW_HEIGHT)))
            row.add_widget(Label(text=f"pressed {count}x" if count else "not used", font_size=theme.CAPTION,
                                 color=DIM_TEXT_COLOR, halign="left", valign="middle", size_hint_x=None, width=dp(80),
                                 text_size=(dp(80), self.ROW_HEIGHT)))
            spinner = _spinner([NO_ACTION], NO_ACTION, lambda action, recorded=recorded: self._choose(recorded, action))
            spinner.size_hint_y = 1
            self.spinners[recorded] = spinner
            row.add_widget(spinner)
            panel.add_widget(row)
        actions_row = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(8))
        actions_row.add_widget(button("Default layout", self._reset))
        actions_row.add_widget(Widget())
        actions_row.add_widget(button("Done", self.dismiss, "primary"))
        panel.add_widget(actions_row)
        self.add_widget(panel)
        self._refresh()

    def _refresh(self):
        self._updating = True
        choices = [NO_ACTION] + (self.actions[self.game] if self.game else [])
        for recorded, spinner in self.spinners.items():
            spinner.values = choices
            spinner.text = self.layout.get(recorded, NO_ACTION)
            spinner.disabled = not self.game
        self._updating = False

    def _choose_game(self, name):
        if self._updating:
            return
        game = next((key for key, value in self.game_names.items() if value == name), None)
        if game != self.game:
            self.game = game
            self.layout = dict(self.default_layouts.get(game, {}))
            self._changed()

    def _choose(self, recorded, action):
        if self._updating:
            return
        self.layout.pop(recorded, None)
        if action != NO_ACTION:
            # An action belongs to one button; the button that had it is left without one.
            for button in [b for b, a in self.layout.items() if a == action]:
                del self.layout[button]
            self.layout[recorded] = action
        self._changed()

    def _reset(self):
        self.layout = dict(self.default_layouts.get(self.game, {}))
        self._changed()

    def _changed(self):
        self._refresh()
        self.on_change(self.game, dict(self.layout))
