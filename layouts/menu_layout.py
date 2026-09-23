from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, ListProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.dropdown import DropDown
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.slider import Slider
from kivy.uix.spinner import Spinner, SpinnerOption
from kivy.uix.switch import Switch
from kivy.uix.widget import Widget

BAR_HEIGHT = dp(36)
BAR_COLOR = (0.10, 0.10, 0.12, 0.95)
PANEL_COLOR = (0.14, 0.14, 0.17, 1)
HOVER_COLOR = (1, 1, 1, 0.08)
ACTIVE_COLOR = (1, 1, 1, 0.16)
RECORD_COLOR = (0.85, 0.2, 0.2, 1)
TEXT_COLOR = (0.92, 0.92, 0.92, 1)
DIM_TEXT_COLOR = (0.6, 0.6, 0.64, 1)
FONT_SIZE = sp(14)


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


class BarButton(HoverBehavior, Button):
    """Flat, text-sized button for the menu bar. `highlight` tints it, e.g. while recording."""

    highlight = ListProperty([0, 0, 0, 0])

    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint_x", None)
        super().__init__(
            background_normal="", background_down="", background_disabled_normal="", background_disabled_down="",
            font_size=FONT_SIZE, color=TEXT_COLOR, disabled_color=DIM_TEXT_COLOR, **kwargs
        )
        self.bind(texture_size=lambda *_: setattr(self, "width", self.texture_size[0] + dp(24)))
        self.bind(hovered=self._refresh_color, state=self._refresh_color, highlight=self._refresh_color)
        self._refresh_color()

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
                           text_size=(dp(170), None))
        self.add_widget(self.label)
        self.add_widget(Label(text=shortcut, font_size=FONT_SIZE, color=DIM_TEXT_COLOR, halign="right",
                              size_hint_x=None, width=dp(48), text_size=(dp(48), None)))
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
        file_menu.add_item("Open inputs...", app.open_track, "F11")
        file_menu.add_item("Save recording...", app.save_recording, "F12")
        file_menu.add_separator()
        file_menu.add_item("Export overlay video...", app.export_overlay_video)
        file_menu.add_item("Export input video...", app.export_input_video)
        file_menu.add_separator()
        file_menu.add_item("Quit", app.stop)

        edit_menu = Menu()
        edit_menu.add_item("Clean track", app.clean_track, "F9")
        edit_menu.add_item("Clear track", app.clear_track, "F10")

        view_menu = Menu()
        view_menu.add_item("Overlay mode", app.toggle_overlay, "F2")
        self.display_item = view_menu.add_item("Show input list", app.toggle_display, "F3")
        view_menu.add_item("Hotkeys", app.show_help, "F1")
        view_menu.add_separator()
        view_menu.add_widget(self._opacity_row())
        view_menu.bind(on_dismiss=lambda *_: app.preview_opacity(False))

        # Kivy holds bound methods weakly, so the menus must be kept alive here.
        self.menus = {"File": file_menu, "Edit": edit_menu, "View": view_menu}
        for text, menu in self.menus.items():
            button = BarButton(text=text)
            button.bind(on_release=menu.open)
            self.add_widget(button)
        settings_button = BarButton(text="Settings")
        settings_button.bind(on_release=lambda *_: app.open_settings_popup())
        self.add_widget(settings_button)

        self.add_widget(self._divider())
        self.record_button = self._transport("Record", app.toggle_recording)
        self.play_button = self._transport("Play", app.toggle_playback)
        self._transport("Restart", app.restart_playback)
        self.loop_button = self._transport("Loop", app.toggle_loop)

        self.status = Label(markup=True, font_size=FONT_SIZE, color=DIM_TEXT_COLOR, halign="right", valign="middle",
                            shorten=True, shorten_from="left", padding=(dp(10), 0))
        self.status.bind(size=lambda label, size: setattr(label, "text_size", size))
        self.add_widget(self.status)

    def _transport(self, text, callback):
        button = BarButton(text=text)
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

    def set_display_mode(self, mode):
        self.display_item.label.text = "Show ring display" if mode == "list" else "Show input list"

    def update(self, recording, playing, looping, status):
        self.record_button.text = "Stop" if recording else "Record"
        self.record_button.highlight = RECORD_COLOR if recording else (0, 0, 0, 0)
        self.play_button.text = "Pause" if playing else "Play"
        self.play_button.disabled = recording
        self.loop_button.highlight = ACTIVE_COLOR if looping else (0, 0, 0, 0)
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
    def __init__(self, hotkeys, **kwargs):
        super().__init__(size_hint=(None, None), size=(dp(420), dp(64) + dp(26) * len(hotkeys)),
                         background="", background_color=(0, 0, 0, 0.5), **kwargs)
        panel = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(8))
        _paint_background(panel, PANEL_COLOR)
        panel.add_widget(Label(text="Hotkeys (work while the game has focus)", font_size=sp(16), bold=True,
                               color=TEXT_COLOR, size_hint_y=None, height=dp(24), halign="left",
                               text_size=(dp(388), None)))
        grid = GridLayout(cols=2, row_default_height=dp(26), row_force_default=True)
        for key, description in hotkeys:
            grid.add_widget(Label(text=key, font_size=FONT_SIZE, color=DIM_TEXT_COLOR, size_hint_x=None,
                                  width=dp(60), halign="left", text_size=(dp(60), None)))
            grid.add_widget(Label(text=description, font_size=FONT_SIZE, color=TEXT_COLOR, halign="left",
                                  text_size=(dp(320), None)))
        panel.add_widget(grid)
        self.add_widget(panel)
        self.bind(on_touch_down=lambda *_: self.dismiss())
