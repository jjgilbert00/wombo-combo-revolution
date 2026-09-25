import os

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, ListProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.dropdown import DropDown
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.scrollview import ScrollView
from kivy.uix.slider import Slider
from kivy.uix.spinner import Spinner, SpinnerOption
from kivy.uix.switch import Switch
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget

BAR_HEIGHT = dp(36)
BAR_COLOR = (0.10, 0.10, 0.12, 0.95)
PANEL_COLOR = (0.14, 0.14, 0.17, 1)
HOVER_COLOR = (1, 1, 1, 0.08)
ACTIVE_COLOR = (1, 1, 1, 0.16)
RECORD_COLOR = (0.85, 0.2, 0.2, 1)
DEMO_COLOR = (0.25, 0.5, 0.9, 1)
TEXT_COLOR = (0.92, 0.92, 0.92, 1)
DIM_TEXT_COLOR = (0.6, 0.6, 0.64, 1)
FONT_SIZE = sp(14)
MENU_TIPS = {
    "File": "Open a recording (or drop one on the window), save, and export videos",
    "Edit": "Notes, key inputs and attempts. Select frames in the input list first (right-click for a menu)",
    "View": "Choose which lanes to show, hide notes, overlay mode",
    "Settings": "Controller, video capture, lead-in and attempt history",
    "Record": "Record a new take from your controller: F8 starts and stops, even while the game has focus. "
              "Also captures the screen if Record video is on in Settings",
    "Play": "Play or pause: Space in this window, F6 / F7 in game",
    "Restart": "Back to the first frame: Home in this window, F5 in game. "
               "While practising this starts a fresh attempt",
    "Loop": "Loop on: the recording repeats, and each pass is kept as a recent attempt",
    "Demo": "Watch the combo in game: a virtual controller plays the recording, either as recorded or cleaned "
            "down to its key inputs (Shift+F6 / Shift+F7, even while the game has focus). Needs vgamepad; see the "
            "user guide",
    "Practice": "Practice: playing scores your controller against the recording.\n"
                "Review: playing replays your last attempt instead. F4 switches",
}
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
        super().__init__(markup=True, font_size=sp(13), color=TEXT_COLOR, size_hint=(None, None), halign="left",
                         valign="middle", padding=(dp(10), dp(6)), **kwargs)
        _paint_background(self, (0.05, 0.05, 0.07, 0.96))
        self.bind(texture_size=lambda *_: setattr(self, "size", self.texture_size))
        self._pending = None
        self._owner = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def schedule(self, widget, text):
        self.hide()
        self._owner = widget
        self._pending = Clock.schedule_once(lambda dt: self._show(widget, text), self.DELAY)

    def _show(self, widget, text):
        self.text_size = (None, None)
        self.text = text
        self.texture_update()
        if self.texture_size[0] > dp(340):
            self.text_size = (dp(340) - dp(20), None)  # Long tips wrap.
            self.texture_update()
        self.size = self.texture_size
        x, y = widget.to_window(widget.x, widget.y)
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
        if self.parent:
            self.parent.remove_widget(self)


class BarButton(HoverBehavior, Button):
    """Flat, text-sized button for the menu bar. `highlight` tints it, e.g. while recording.
    `tooltip` is shown after hovering for a moment."""

    highlight = ListProperty([0, 0, 0, 0])
    tooltip = StringProperty("")

    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint_x", None)
        super().__init__(
            background_normal="", background_down="", background_disabled_normal="", background_disabled_down="",
            font_size=FONT_SIZE, color=TEXT_COLOR, disabled_color=DIM_TEXT_COLOR, **kwargs
        )
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
        if self.highlight[3]:
            self.background_color = self.highlight
        elif self.state == "down":
            self.background_color = ACTIVE_COLOR
        elif self.hovered:
            self.background_color = HOVER_COLOR
        else:
            self.background_color = (0, 0, 0, 0)


class MenuItem(HoverBehavior, ButtonBehavior, BoxLayout):
    """A dropdown row: action on the left, its hotkey on the right."""

    def __init__(self, text, shortcut="", **kwargs):
        super().__init__(size_hint_y=None, height=dp(32), padding=(dp(12), 0), **kwargs)
        _paint_background(self, (0, 0, 0, 0))
        self.label = Label(text=text, font_size=FONT_SIZE, color=TEXT_COLOR, halign="left", valign="middle",
                           text_size=(dp(158), None))
        self.add_widget(self.label)
        self.shortcut = Label(text=shortcut, font_size=FONT_SIZE, color=DIM_TEXT_COLOR, halign="right",
                              size_hint_x=None, width=dp(64), text_size=(dp(64), None))
        self.add_widget(self.shortcut)
        self.bind(hovered=self._refresh_color, state=self._refresh_color)

    def _refresh_color(self, *args):
        self._bg_color.rgba = ACTIVE_COLOR if self.state == "down" else HOVER_COLOR if self.hovered else (0, 0, 0, 0)


class Menu(DropDown):
    def __init__(self, **kwargs):
        super().__init__(auto_width=False, width=dp(250), **kwargs)
        _paint_background(self.container, PANEL_COLOR)
        self.container.padding = (0, dp(4))

    def add_item(self, text, callback, shortcut=""):
        item = MenuItem(text, shortcut)
        item.bind(on_release=lambda *_: (self.dismiss(), callback()))
        self.add_widget(item)
        return item

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
        edit_menu.add_separator()
        edit_menu.add_item("Save attempt", app.save_attempt, "S")
        edit_menu.add_item("Attempts...", app.open_attempts, "A")
        edit_menu.add_item("Clear attempt", app.clear_attempt)
        edit_menu.add_separator()
        edit_menu.add_item("Clean track (presses only)", app.clean_track)
        edit_menu.add_item("Clear track", app.clear_track)

        view_menu = Menu()
        view_menu.add_item("Overlay mode", app.toggle_overlay, "F2")
        self.display_item = view_menu.add_item("Show input list", app.toggle_display, "F3")
        self.notes_item = view_menu.add_item("Hide notes", app.toggle_notes, "Shift+F3")
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
        self.record_button = self._transport("Record", app.toggle_recording)
        self.play_button = self._transport("Play", app.toggle_playback)
        self._transport("Restart", app.restart_playback)
        self.loop_button = self._transport("Loop", app.toggle_loop)
        self.practice_button = self._transport("Practice", app.toggle_practice)
        demo_menu = Menu()
        demo_menu.add_item("Demo the recording", app.demo_recording, "Shift+F6")
        demo_menu.add_item("Demo the key inputs", app.demo_key_inputs, "Shift+F7")
        demo_menu.add_separator()
        demo_menu.add_item("Stop the demo", app.stop_demo, "F7")
        self.menus["Demo"] = demo_menu
        self.demo_button = BarButton(text="Demo", tooltip=MENU_TIPS["Demo"])
        self.demo_button.bind(on_release=demo_menu.open)
        self.add_widget(self.demo_button)

        self.status = Label(markup=True, font_size=FONT_SIZE, color=DIM_TEXT_COLOR, halign="right", valign="middle",
                            shorten=True, shorten_from="left", padding=(dp(10), 0))
        self.status.bind(size=lambda label, size: setattr(label, "text_size", size))
        self.add_widget(self.status)

    def _transport(self, text, callback):
        button = BarButton(text=text, tooltip=MENU_TIPS[text])
        button.bind(on_release=lambda *_: callback())
        self.add_widget(button)
        return button

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

    def set_display_mode(self, mode):
        self.display_item.label.text = "Show ring display" if mode == "list" else "Show input list"

    def update(self, recording, playing, looping, practicing, status, demoing=False):
        self.record_button.text = "Stop" if recording else "Record"
        self.record_button.highlight = RECORD_COLOR if recording else (0, 0, 0, 0)
        self.play_button.text = "Pause" if playing else "Play"
        self.play_button.disabled = recording
        # The toggles say what they're set to, rather than relying on a highlight.
        self.loop_button.text = "Loop on" if looping else "Loop off"
        self.loop_button.highlight = ACTIVE_COLOR if looping else (0, 0, 0, 0)
        self.practice_button.text = "Practice" if practicing else "Review"
        self.practice_button.highlight = ACTIVE_COLOR if practicing else (0, 0, 0, 0)
        self.demo_button.highlight = DEMO_COLOR if demoing else (0, 0, 0, 0)
        self.status.text = status


class _Option(SpinnerOption):
    def __init__(self, **kwargs):
        super().__init__(background_normal="", background_color=PANEL_COLOR, color=TEXT_COLOR,
                         font_size=FONT_SIZE, height=dp(32), **kwargs)


def _spinner(values, selected, on_select):
    spinner = Spinner(text=selected, values=values, option_cls=_Option, font_size=FONT_SIZE, color=TEXT_COLOR,
                      background_normal="", background_color=(1, 1, 1, 0.08), size_hint_y=None, height=dp(32))
    spinner.bind(text=lambda _, text: on_select(text))
    return spinner


class SettingsPopup(ModalView):
    """Settings rows are (label, [(choice label, value)], current value, on_change) or a bool switch."""

    def __init__(self, rows, **kwargs):
        super().__init__(size_hint=(None, None), size=(dp(480), dp(64) + dp(44) * (len(rows) + 1)),
                         background="", background_color=(0, 0, 0, 0.5), **kwargs)
        panel = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))
        _paint_background(panel, PANEL_COLOR)
        panel.add_widget(Label(text="Settings", font_size=sp(18), bold=True, color=TEXT_COLOR, size_hint_y=None,
                               height=dp(24), halign="left", text_size=(dp(448), None)))
        grid = GridLayout(cols=2, spacing=(dp(12), dp(12)), row_default_height=dp(32), row_force_default=True)
        for label, choices, current, on_change in rows:
            grid.add_widget(Label(text=label, font_size=FONT_SIZE, color=TEXT_COLOR, halign="left", valign="middle",
                                  size_hint_x=None, width=dp(160), text_size=(dp(160), dp(32))))
            if choices is bool:
                switch = Switch(active=current, size_hint_x=None, width=dp(80))
                switch.bind(active=lambda _, value, cb=on_change: cb(value))
                row = BoxLayout()
                row.add_widget(switch)
                row.add_widget(Widget())
                grid.add_widget(row)
            else:
                labels = [text for text, _ in choices]
                values = dict(choices)
                selected = next((text for text, value in choices if value == current), labels[0])
                grid.add_widget(_spinner(labels, selected, lambda text, cb=on_change, v=values: cb(v[text])))
        panel.add_widget(grid)
        close = BarButton(text="Done", size_hint=(None, None), height=dp(32), pos_hint={"right": 1},
                          highlight=(1, 1, 1, 0.1))
        close.bind(on_release=lambda *_: self.dismiss())
        panel.add_widget(close)
        self.add_widget(panel)


class HelpPopup(ModalView):
    """Getting-started steps across the top, then key sections in two columns.
    columns is [[(section title, [(key, description)])]]; on_manual opens the user guide."""

    KEY_WIDTH = dp(96)
    COLUMN_WIDTH = dp(440)

    def __init__(self, steps, columns, on_manual, **kwargs):
        row_count = max(sum(len(rows) + 1.4 for _, rows in column) for column in columns)
        super().__init__(size_hint=(None, None), size=(dp(940), dp(170) + dp(24) * len(steps) + dp(25) * row_count),
                         background="", background_color=(0, 0, 0, 0.5), **kwargs)
        panel = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(8))
        _paint_background(panel, PANEL_COLOR)
        panel.add_widget(self._label("Getting started", sp(17), TEXT_COLOR, dp(26), bold=True))
        for number, step in enumerate(steps, 1):
            panel.add_widget(self._label(f"{number}.  {step}", FONT_SIZE, TEXT_COLOR, dp(24), markup=True))
        body = BoxLayout(spacing=dp(20), padding=(0, dp(10), 0, 0))
        for column in columns:
            box = BoxLayout(orientation="vertical", spacing=dp(1))
            for title, rows in column:
                box.add_widget(self._label(title, FONT_SIZE, TEXT_COLOR, dp(32), bold=True, valign="bottom"))
                for key, description in rows:
                    row = BoxLayout(size_hint_y=None, height=dp(24))
                    row.add_widget(Label(text=key, font_size=FONT_SIZE, color=(1.0, 0.78, 0.2, 1), size_hint_x=None,
                                         width=self.KEY_WIDTH, halign="left", valign="middle",
                                         text_size=(self.KEY_WIDTH, dp(24))))
                    row.add_widget(Label(text=description, font_size=FONT_SIZE, color=TEXT_COLOR, halign="left",
                                         valign="middle", shorten=True,
                                         text_size=(self.COLUMN_WIDTH - self.KEY_WIDTH, dp(24))))
                    box.add_widget(row)
            box.add_widget(Widget())
            body.add_widget(box)
        panel.add_widget(body)
        actions = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(8))
        actions.add_widget(self._label("Hover over any button for a tip. The user guide covers everything in detail.",
                                       sp(12), DIM_TEXT_COLOR, dp(32)))
        guide = BarButton(text="Open user guide", highlight=(1, 1, 1, 0.1))
        guide.bind(on_release=lambda *_: (self.dismiss(), on_manual()))
        close = BarButton(text="Close", highlight=(1, 1, 1, 0.1))
        close.bind(on_release=lambda *_: self.dismiss())
        actions.add_widget(guide)
        actions.add_widget(close)
        panel.add_widget(actions)
        self.add_widget(panel)

    @staticmethod
    def _label(text, font_size, color, height, bold=False, markup=False, valign="middle"):
        label = Label(text=text, font_size=font_size, color=color, bold=bold, markup=markup, size_hint_y=None,
                      height=height, halign="left", valign=valign)
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
        panel.add_widget(Label(text=title, font_size=sp(16), bold=True, color=TEXT_COLOR, size_hint_y=None,
                               height=dp(22), halign="left", text_size=(dp(388), None)))
        self.input = TextInput(text=text, multiline=False, size_hint_y=None, height=dp(34), font_size=FONT_SIZE,
                               background_color=(1, 1, 1, 0.08), foreground_color=TEXT_COLOR,
                               cursor_color=TEXT_COLOR, hint_text="e.g. hit confirm here")
        self.input.bind(on_text_validate=lambda *_: self._save(on_save))
        panel.add_widget(self.input)

        buttons = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(8))
        if on_delete:
            delete = BarButton(text="Delete", highlight=(0.85, 0.2, 0.2, 0.8))
            delete.bind(on_release=lambda *_: (self.dismiss(), on_delete()))
            buttons.add_widget(delete)
        buttons.add_widget(Widget())
        cancel = BarButton(text="Cancel")
        cancel.bind(on_release=lambda *_: self.dismiss())
        save = BarButton(text="Save", highlight=(1, 1, 1, 0.12))
        save.bind(on_release=lambda *_: self._save(on_save))
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
            self.background_color = (1.0, 0.78, 0.2, 0.9) if self.state == "down" else (1, 1, 1, 0.08)
        self.color = (0.1, 0.08, 0.02, 1) if self.state == "down" else TEXT_COLOR


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
        header.add_widget(Label(text=title, font_size=sp(16), bold=True, color=TEXT_COLOR, halign="left",
                                valign="middle", size_hint_x=None, width=dp(300), text_size=(dp(300), dp(24))))
        self.preview = Label(font_size=sp(16), bold=True, color=(1.0, 0.78, 0.2, 1), halign="right",
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
            delete = BarButton(text="Delete", highlight=(0.85, 0.2, 0.2, 0.8))
            delete.bind(on_release=lambda *_: (self.dismiss(), on_delete()))
            actions.add_widget(delete)
        actions.add_widget(Widget())
        cancel = BarButton(text="Cancel")
        cancel.bind(on_release=lambda *_: self.dismiss())
        save = BarButton(text="Save", highlight=(1, 1, 1, 0.12))
        save.bind(on_release=lambda *_: (self.dismiss(), on_save(self.key_input)))
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
        return Label(text=text, font_size=sp(12), color=DIM_TEXT_COLOR, halign="left", valign="middle",
                     text_size=(dp(250), None))

    def _stepper(self, text, edge, delta):
        button = BarButton(text=text, highlight=(1, 1, 1, 0.08))
        button.bind(on_release=lambda *_: self._step(edge, delta))
        return button

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
        header.add_widget(Label(text="Attempts", font_size=sp(16), bold=True, color=TEXT_COLOR, halign="left",
                                valign="middle", size_hint_x=None, width=dp(120), text_size=(dp(120), dp(24))))
        header.add_widget(Label(text="Saved attempts are kept in the track's file. Replay plays one against the "
                                     "recording; F4 goes back to practice.", font_size=sp(12), color=DIM_TEXT_COLOR,
                                halign="right", valign="middle", text_size=(dp(600), dp(24))))
        panel.add_widget(header)
        self.rows = GridLayout(cols=1, size_hint_y=None, spacing=dp(4))
        self.rows.bind(minimum_height=self.rows.setter("height"))
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(6))
        scroll.add_widget(self.rows)
        panel.add_widget(scroll)
        actions = BoxLayout(size_hint_y=None, height=self.ROW_HEIGHT)
        actions.add_widget(Widget())
        close = BarButton(text="Close", highlight=(1, 1, 1, 0.12))
        close.bind(on_release=lambda *_: self.dismiss())
        actions.add_widget(close)
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
            self.rows.add_widget(self._text(empty_text, DIM_TEXT_COLOR, None))
        for attempt in attempts:
            self.rows.add_widget(self._row(attempt))

    def _text(self, text, color, width):
        label = Label(text=text, font_size=FONT_SIZE, color=color, halign="left", valign="middle",
                      size_hint_x=None if width else 1, width=width or 100, shorten=True)
        label.bind(size=lambda l, size: setattr(l, "text_size", size))
        return label

    def _button(self, text, callback, highlight=(1, 1, 1, 0.08)):
        button = BarButton(text=text, highlight=highlight)
        button.bind(on_release=lambda *_: callback())
        return button

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
        delete = self._button("Delete", lambda: None)

        def confirm(*_):
            if delete.text == "Delete":
                delete.text, delete.highlight = "Sure?", (0.85, 0.2, 0.2, 0.8)
            else:
                self.app.delete_attempt(kind, attempt_id)
                self.refresh()

        delete.bind(on_release=confirm)
        row.add_widget(delete)
        return row
