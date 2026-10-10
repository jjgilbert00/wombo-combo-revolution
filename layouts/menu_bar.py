"""The menu bar along the top: the File, Edit and View menus and Settings, then the transport
cluster (record, play, restart), Loop, Practice | Review and Demo.
"""
import os

from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.slider import Slider
from kivy.uix.widget import Widget

import theme
from layouts.ui_kit import (
    BAR_COLOR, BAR_HEIGHT, DEMO_COLOR, DIM_TEXT_COLOR, FONT_SIZE, RECORD_COLOR, TEXT_COLOR, BarButton, Chip,
    IconButton, Menu, paint_background
)


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


class MenuBar(BoxLayout):
    """Menus and transport controls on the left, live status on the right."""

    def __init__(self, app, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, height=BAR_HEIGHT, padding=(dp(4), 0), **kwargs)
        self.app = app
        paint_background(self, BAR_COLOR)

        self.add_widget(Label(text="WOMBO COMBO", font_size=theme.CAPTION, bold=True, color=(*theme.ACCENT, 1),
                              size_hint_x=None, width=dp(108)))
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
            menu_button = BarButton(text=text, tooltip=MENU_TIPS[text])
            menu_button.bind(on_release=menu.open)
            self.add_widget(menu_button)
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
