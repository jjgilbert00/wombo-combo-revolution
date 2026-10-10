import logging
import os
import shutil
import tempfile
import threading
import time
import winsound
from concurrent.futures import ThreadPoolExecutor

from timing import enable_high_resolution_timing, disable_high_resolution_timing

# Must happen before Kivy starts so its frame limiter gets 1 ms sleeps instead of 15.6 ms ones.
enable_high_resolution_timing()

os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
from kivy.config import Config

Config.set("kivy", "exit_on_escape", "0")
Config.set("input", "mouse", "mouse,multitouch_on_demand")  # No red dots on right click.
# Waiting for vsync inside the buffer swap holds the GIL for up to a frame, which starves the input
# sampler thread. Kivy's own 60 fps limiter paces rendering instead (it sleeps without the GIL).
Config.set("graphics", "vsync", "0")

from kivy.app import App
from kivy.base import ExceptionHandler, ExceptionManager
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.modalview import ModalView
from kivy.uix.widget import Widget
import win32api

import file_dialogs
from controller import find_controllers
from button_map import full_map, inverse_map, map_key_input, map_state
from input_list import LIST_BUTTON_ORDER
from key_inputs import demo_track, derive, derive_hold, describe, normalized
from layouts.input_list_layout import LANES, InputListLayout
from games import GAMES
import guidance
import help_content
import keys
import track_file
from overlay import Overlay
from settings import Settings, dialog_columns
from layouts.dialogs import (
    AttemptsPopup, ButtonMapPopup, GameActionsPopup, HelpPopup, KeyInputPopup, KeysPopup, NotePopup, SettingsPopup
)
from layouts.menu_bar import MenuBar
from layouts.ui_kit import Menu, StatusBar
from layouts.arrow_lanes_layout import ArrowLanesLayout
from layouts.feedback import CardLayer
from layouts.ring_layout import RingLayout
from playalong import PlayalongController
from sampler import FPS, InputSampler
from screen_capture import ScreenRecorder, list_displays, prepare_capture
from virtual_pad import VirtualPad, VirtualPadError
import theme
from theme import markup
from video_writer import nvenc_available, resolve_encoder, video_size, write_capture_and_overlay, write_input_video
from layouts.export_frames import DisplayFrames

logger = logging.getLogger(__name__)


class KeepRunning(ExceptionHandler):
    """An error in one event handler is logged and reported, and the app carries on: left to Kivy,
    it would stop the event loop, leaving the window up but frozen."""

    def handle_exception(self, inst):
        logger.exception("Unhandled error in an event handler")
        app = App.get_running_app()
        if app and hasattr(app, "flash"):
            app.flash(f"Something went wrong ({type(inst).__name__}: {inst}); it's in the log", "error", 10)
        return ExceptionManager.PASS


def write_tick(path):
    """A short, soft click: a decaying 1.6 kHz blip, 30 ms, as a WAV file."""
    import math
    import struct
    import wave
    rate, length = 44100, 0.03
    samples = [int(9000 * math.exp(-i / (rate * 0.006)) * math.sin(2 * math.pi * 1600 * i / rate))
               for i in range(int(rate * length))]
    with wave.open(path, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(struct.pack(f"<{len(samples)}h", *samples))
TITLE = "Wombo Combo"
EXPORT_SIZE = (1600, 900)  # Input videos, in pixels.


class WomboComboApp(App):
    title = TITLE

    def __init__(self):
        super().__init__()
        self.settings = None  # Settings over Kivy's config, once it's loaded (build).
        self.overlay = Overlay(self)
        self.playalong_controller = PlayalongController()
        self.sampler = InputSampler(self.playalong_controller.tick)
        self.screen_recorder = None
        self.capture_path = None  # Video that belongs to the current input track, if any.
        self.track_path = None  # The current track's .json file, once it's been opened or saved.
        self.virtual_pad = None  # Plugged in the first time a demo plays.
        self.coaching = False  # Showing the "press Space" card until the player first plays.
        # Game keys held on the keyboard, for playing without a controller. The sampler thread reads it,
        # so it's replaced rather than changed in place (a set changing while it's copied raises).
        self.keys_down = frozenset()
        self.unsaved_take = False  # A new take that hasn't been saved anywhere yet.
        self.unsaved_edits = False  # Notes, key inputs or cleaning not yet saved.
        self.temp_dir = tempfile.mkdtemp(prefix="wombo_")
        self.take = 0
        self.jobs = ThreadPoolExecutor(max_workers=1)  # Saves/exports run one at a time, off the UI thread.
        self.job_label = None
        self.job_progress = None
        self.message = None  # (markup text, expiry time)
        self.selection = None  # (start, end) frames selected in the input list, inclusive.
        self._hits_heard = 0  # Key input hits already ticked for (Hit sound).
        self._countdown_second = None  # The demo countdown's last second beeped.
        self._context_menu = None  # The right-click menu while it's open (Kivy holds callbacks weakly).

    # ---- Setup ---------------------------------------------------------------------------------

    def build_config(self, config):
        config.setdefaults("wombo", Settings.defaults())

    def get_application_config(self):
        return super().get_application_config(os.path.join(self.user_data_dir, "%(appname)s.ini"))

    def open_settings(self, *args):
        return False  # Disable Kivy's built-in F1 settings panel; F1 shows hotkeys instead.

    def build(self):
        ExceptionManager.add_handler(KeepRunning())
        self.settings = Settings(self.config)
        keys.check_actions(self)
        keys.use(keys.Bindings.from_setting(self.settings.keys))
        self.waiting_for_key = False  # The Keys dialog is waiting for a new key: hotkeys hold off.
        self.icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images", "app_icon.png")
        Window.clearcolor = (*theme.BACKGROUND, 0.5)
        # Up to 1920x1080, centred in the screen's work area (clear of the taskbar). Windows places a
        # new window wherever it likes, which can leave the bottom, and the status bar, behind the
        # taskbar.
        work_left, work_top, work_right, work_bottom = win32api.GetMonitorInfo(
            win32api.MonitorFromPoint((0, 0), 1))["Work"]  # 1: the primary monitor.
        title_bar = 40  # Window.top is the inside of the window; leave room for its title bar.
        width = min(1920, int((work_right - work_left) * 0.9))
        height = min(1080, int((work_bottom - work_top - title_bar) * 0.95))
        Window.size = (width, height)
        Window.left = work_left + (work_right - work_left - width) // 2
        Window.top = work_top + title_bar + (work_bottom - work_top - title_bar - height) // 2
        Window.borderless = False
        Window.fullscreen = False

        self.playalong_controller.set_looping(self.settings.loop)
        self.ring_layout = RingLayout()
        self.arrow_lanes_layout = ArrowLanesLayout()
        self.input_list_layout = InputListLayout()
        self.displays = {"list": self.input_list_layout, "lanes": self.arrow_lanes_layout, "ring": self.ring_layout}
        self.input_list_layout.set_lookahead(self.settings.lookahead)
        self.input_list_layout.on_scrub = self.scrub
        self.input_list_layout.on_zoom = self.set_list_zoom
        self.input_list_layout.on_select = self.set_selection
        self.input_list_layout.on_note_click = self.edit_note
        self.input_list_layout.on_key_input_click = self.edit_key_input
        self.input_list_layout.on_context_menu = self.open_context_menu
        self.playalong_controller.set_practice(self.settings.practice)
        self.playalong_controller.set_history_count(self.settings.recent_attempts)
        self.playalong_controller.set_lead_in(self.settings.lead_in)
        self.menu_bar = MenuBar(self)
        self.root_layout = BoxLayout(orientation="vertical")
        self.root_layout.add_widget(self.menu_bar)
        # The display, with the getting-started card over it.
        self.stage = FloatLayout()
        self.card_layer = CardLayer(pos_hint={"x": 0, "y": 0})
        self.stage.add_widget(self.card_layer)
        self.root_layout.add_widget(self.stage)
        self.status_bar = StatusBar()
        self.root_layout.add_widget(self.status_bar)
        self.display = None
        self.show_display(self.settings.input_display)
        self.set_notes_visible(self.settings.show_notes)
        self.set_game(self.default_game(), None, mark_edited=False)
        self.set_actions_visible(self.settings.show_actions)
        self.set_up_next_visible(self.settings.show_next)
        self.apply_feedback_settings()
        self.menu_bar.set_see_through(self.settings.see_through)
        self.set_lanes_shown(set(filter(None, self.settings.lanes.split(","))))
        self.menu_bar.set_recent(self.recent_recordings())
        return self.root_layout

    def on_start(self):
        self.select_controller()
        self.sampler.extra = self.keyboard_state
        self.sampler.on_menu = lambda name: Clock.schedule_once(lambda dt: self.on_menu_button(name))
        Window.bind(on_key_up=self.on_key_up, focus=lambda window, focused: focused or self._release_keys())
        self.sampler.start()
        if self.settings.first_run:
            # Straight into something to try: nothing to find, open or set up first.
            self.settings.set("first_run", 0)
            self.config.write()
            Clock.schedule_once(lambda dt: self.try_warm_up())
        Clock.schedule_interval(self.refresh, 0)  # Every rendered frame.
        Clock.schedule_interval(self.update_status, 0.1)
        Clock.schedule_interval(self.check_controller, 1.0)
        if self.settings.encoder == "auto":
            threading.Thread(target=nvenc_available, daemon=True).start()  # Warm the cached probe.
        if self.settings.capture_video:
            # Creating the capture device takes ~100 ms; do it now rather than when recording starts.
            prepare_capture(self.settings.display)

        # Hotkeys work while the game has focus. The listener runs inside a system-wide keyboard hook,
        # so it only hands the call to the UI thread.
        self.listener = keys.listen_for_hotkeys(lambda method: Clock.schedule_once(lambda dt: self._on_hotkey(method)))
        Window.bind(on_key_down=self.on_key_down)
        Window.bind(on_request_close=lambda *args: not self._keep_unsaved_work("quitting"))
        Window.bind(on_drop_file=lambda window, filename, *args: self.open_track(filename.decode("utf-8")))

    def _on_hotkey(self, method):
        if not self.waiting_for_key:
            getattr(self, method)()

    def on_menu_button(self, name):
        """Start plays or pauses and Back restarts, so practice never needs the keyboard. Only while
        the app is in front: in game, those buttons belong to the game."""
        if not self.app_focused() or any(isinstance(child, ModalView) for child in Window.children):
            return
        if name == "start":
            self.toggle_playback()
        else:
            self.restart_playback()

    @staticmethod
    def app_focused():
        return Window.focus

    def _playing_by_keyboard(self):
        controller = self.playalong_controller
        return controller.is_playing() and controller.is_practicing() and not controller.demo_kind()

    def keyboard_state(self):
        """The keyboard as a controller (called from the sampler thread), in the player's buttons."""
        controller = self.playalong_controller
        return keys.keyboard_state(self.keys_down, controller.get_game()[1], controller.get_button_map())

    def _release_keys(self):
        self.keys_down = frozenset()

    def on_key_up(self, window, key, scancode):
        name = keys.GAME_KEYS.get(key)
        if name:
            self.keys_down = self.keys_down - {name}

    def on_key_down(self, window, key, scancode, codepoint, modifiers):
        """Shortcuts that only apply while the app window is focused (keys.shortcut), and the game
        keys for playing without a controller."""
        if any(isinstance(child, ModalView) for child in Window.children):
            return False  # A popup is open; let it have the keys.
        held = [modifier for modifier in modifiers if modifier not in keys.LOCKS]
        name = keys.GAME_KEYS.get(key)
        if name and not held:
            self.keys_down = self.keys_down | {name}
            # The arrows always play. While practising the letters do too; when paused, they're shortcuts.
            if key in keys.ARROW_KEYS or self._playing_by_keyboard():
                return True
        method = keys.window_shortcut(key, modifiers)
        if method:
            getattr(self, method)()
            return True
        return False

    def clear_selection(self):
        self.set_selection(None)

    def on_stop(self):
        self.listener.stop()
        self.playalong_controller.stop_demo()
        if self.virtual_pad:
            self.virtual_pad.close()
        if self.playalong_controller.is_recording():
            self.stop_recording()
        self.sampler.stop()
        self.config.write()
        self.jobs.shutdown(wait=True, cancel_futures=True)
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        disable_high_resolution_timing()

    # ---- Per-frame -----------------------------------------------------------------------------

    def refresh(self, dt):
        self._tick_on_hits()  # Every frame, so the tick comes with the hit.
        if self.display is self.input_list_layout:
            self.input_list_layout.dim_non_key = self.playalong_controller.has_key_inputs()
            frames_before, frames_after = self.input_list_layout.frames_needed()
            self.input_list_layout.update_state(self.playalong_controller.list_snapshot(frames_before, frames_after))
            if self.overlay.active:
                self.overlay.fit()
        else:  # The arrow lanes and the ring are drawn from the same upcoming frames.
            # As much time ahead as the scroll speed setting says, like the input list.
            count = max(10, round(self.input_list_layout.lookahead * FPS))
            controller_state, upcoming_frames, offset = self.playalong_controller.snapshot(count)
            self.display.update_state(controller_state, upcoming_frames, offset)
            self.display.show_feedback(*self.playalong_controller.feedback())
            if self.overlay.active:
                self.overlay.fit()

    def select_controller(self):
        readers = find_controllers()
        wanted = self.settings.controller
        self.sampler.reader = next((r for r in readers if r.name == wanted), readers[0] if readers else None)
        return readers

    def check_controller(self, dt):
        reader = self.sampler.reader
        if reader is None or not reader.connected:
            self.select_controller()

    FLASH_COLORS = {"info": theme.TEXT, "warning": theme.WARNING, "error": theme.MISS}

    def flash(self, text, kind="info", seconds=4):
        """A message in the status bar for a few seconds: kind is "info", "warning" or "error"."""
        self.message = (markup(text, self.FLASH_COLORS[kind]), time.time() + seconds)
        # Also logged: a message shown while the game has focus is never seen.
        logger.log(logging.INFO if kind == "info" else logging.WARNING, "Status: %s", text)

    @staticmethod
    def beep(ok=True):
        """A system sound for feedback that has to reach the player in game (asynchronous)."""
        winsound.MessageBeep(winsound.MB_OK if ok else winsound.MB_ICONHAND)

    def _tick_on_hits(self):
        """With Hit sound on, a short tick for each key input hit (heard even with the game in front)."""
        controller = self.playalong_controller
        hits, _ = controller.key_input_score() if controller.is_playing() and controller.is_practicing() else (0, 0)
        if hits > self._hits_heard and self.settings.hit_sound:
            path = os.path.join(self.temp_dir, "tick.wav")
            if not os.path.exists(path):
                write_tick(path)
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        self._hits_heard = hits

    def update_status(self, dt):
        controller = self.playalong_controller
        # A demo's countdown ticks once a second, so it can be followed without seeing the app.
        if controller.demo_kind() and controller.get_lead():
            second = -(-controller.get_lead() // FPS)
            if second != self._countdown_second:
                self._countdown_second = second
                self.beep()
        self.menu_bar.update(controller.is_recording(), controller.is_playing(), controller.is_looping(), controller.is_practicing(),
                             demoing=bool(controller.demo_kind()))
        card, buttons = guidance.card(self)
        # Over the game, the overlay shows the displays only; the hints are for the app window.
        # The card says it all when shown.
        hint = "" if self.overlay.active or card or not self.settings.show_hints else guidance.hint(self)
        self.card_layer.set_card(card, buttons)
        self.status_bar.set(hint, guidance.status_text(self))
        for display in self.displays.values():
            display.card_up = bool(card)

    def skip_coaching(self):
        """Closes the coach card without starting, to look around first."""
        self.coaching = False

    # ---- Transport -----------------------------------------------------------------------------

    def play(self):
        if not self.playalong_controller.is_recording():
            self.coaching = False
            self.playalong_controller.play()

    def pause(self):
        if not self.playalong_controller.is_recording():
            self.playalong_controller.pause()

    def toggle_playback(self):
        self.pause() if self.playalong_controller.is_playing() else self.play()

    def restart_playback(self):
        kind = self.playalong_controller.demo_kind()
        if kind:
            self._demo(kind)  # Start the demo again from the top.
        else:
            self.playalong_controller.restart()

    # ---- Demo ----------------------------------------------------------------------------------

    def demo_recording(self):
        """Plays the recording, exactly as recorded, on a virtual controller for the game to see."""
        self._demo("recording")

    def demo_key_inputs(self):
        """Plays just the key inputs (the recording cleaned of stray and over-held inputs)."""
        self._demo("key inputs")

    def stop_demo(self):
        self.playalong_controller.stop_demo()

    def _demo(self, kind):
        controller = self.playalong_controller
        if controller.is_recording() or not controller.track_length():
            self.flash("Open or record something to demo first", "warning")
            self.beep(False)
            return
        if kind == "key inputs":
            if not controller.has_key_inputs():
                self.flash(keys.fill("No key inputs to demo: select frames and press {mark_key_input} to mark them"),
                           "warning", 6)
                self.beep(False)
                return
            track = demo_track(controller.get_key_inputs(), controller.get_input_track())
        else:
            track = controller.get_input_track()
        if self.virtual_pad is None:
            try:
                self.virtual_pad = VirtualPad()
            except VirtualPadError as e:
                self.flash(str(e), "error", 12)
                self.beep(False)
                return
        controller.pause()  # Also ends a demo already playing.
        countdown = self.settings.demo_countdown
        mapping, pad = controller.get_button_map(), self.virtual_pad
        # The game reads the player's own layout, so the demo presses the player's buttons.
        controller.start_demo(track, lambda state: pad.send(map_state(state, mapping)), countdown, kind)
        self.set_selection(None)
        self.flash(f"Demo of the {kind} in {countdown / FPS:g}s: switch to the game", "info", 5)
        self._countdown_second = None  # update_status ticks each second of the countdown audibly.

    def scrub(self, frames):
        """Moves the playhead (pausing playback) so a part of the run can be inspected."""
        controller = self.playalong_controller
        if not controller.is_recording():
            controller.pause()
            controller.set_frame(controller.get_current_frame() + frames)

    def set_list_zoom(self, lookahead):
        self.settings.set("lookahead", round(lookahead, 2))

    def set_selection(self, start, end=None):
        """Selects frames start..end (inclusive, either order) of the track, or clears with None."""
        if start is not None:
            last = self.playalong_controller.track_length() - 1
            start, end = sorted((start, start if end is None else end))
            start, end = max(0, start), min(end, last)
            if start > end:
                start = None
        self.selection = None if start is None else (start, end)
        self.input_list_layout.selection = self.selection

    def open_context_menu(self, frame, pos):
        """Right-click menu in the input list, for the selection (or the frame clicked, if it's
        outside the selection)."""
        controller = self.playalong_controller
        if controller.is_recording() or not controller.track_length():
            return
        frame = max(0, min(frame, controller.track_length() - 1))
        if not self.selection or not self.selection[0] <= frame <= self.selection[1]:
            self.set_selection(frame, frame)
        start = self.selection[0]
        menu = Menu()
        menu.add_item("Add note", self.add_note, keys.either("add_note", ""))
        menu.add_item("Mark key input", self.mark_key_input, keys.either("mark_key_input", ""))
        menu.add_item("Practise from here", lambda: (controller.set_frame(start), self.play()))
        menu.add_item("Clear selection", lambda: self.set_selection(None), keys.either("clear_selection", ""))
        menu.add_separator()
        menu.add_item("Save attempt", self.save_attempt, keys.either("save_attempt", ""))
        menu.add_item("Attempts...", self.open_attempts, keys.either("open_attempts", ""))
        # A dropdown opens from a widget, so a one-pixel anchor stands in for the cursor.
        anchor = Widget(size_hint=(None, None), size=(1, 1), pos=pos)
        self.input_list_layout.add_widget(anchor)
        menu.bind(on_dismiss=lambda *_: self.input_list_layout.remove_widget(anchor))
        self._context_menu = menu  # Kivy holds bound callbacks weakly; keep the menu alive while open.
        menu.open(anchor)

    def add_note(self):
        """Opens the note editor for the selected frames, or the frame on the line if none are selected."""
        controller = self.playalong_controller
        if controller.is_recording() or not controller.track_length():
            return
        start, end = self.selection or (controller.get_current_frame(),) * 2
        existing = next((i for i, note in enumerate(controller.get_notes())
                         if (note["start"], note["end"]) == (start, end)), None)
        if existing is not None:
            self.edit_note(existing)
            return
        self._open_note_popup(None, start, end, "")

    def edit_note(self, index):
        note = self.playalong_controller.get_notes()[index]
        self._open_note_popup(index, note["start"], note["end"], note["text"])

    def _open_note_popup(self, index, start, end, text):
        span = f"frame {start}" if start == end else f"frames {start}-{end}"

        def save(new_text):
            if new_text:
                self.playalong_controller.set_note(index, start, end, new_text)
            elif index is not None:
                self.playalong_controller.remove_note(index)
            self.unsaved_edits = True

        def delete():
            self.playalong_controller.remove_note(index)
            self.unsaved_edits = True

        delete = delete if index is not None else None
        title = f"Note on {span}" if index is None else f"Edit note on {span}"
        NotePopup(title, text, save, delete).open()

    def mark_key_input(self):
        """Marks the selected frames (or the frame on the line) as a key input, guessing the
        requirement from the target, and opens it for review. Edits an overlapping one instead."""
        controller = self.playalong_controller
        if controller.is_recording() or not controller.track_length():
            return
        start, end = self.selection or (controller.get_current_frame(),) * 2
        existing = next((i for i, k in enumerate(controller.get_key_inputs())
                         if k["start"] <= end and start <= k["end"]), None)
        if existing is not None:
            self.edit_key_input(existing)
            return
        self._open_key_input_popup(None, derive(controller.get_input_track(), start, end))

    def edit_key_input(self, index):
        self._open_key_input_popup(index, self.playalong_controller.get_key_inputs()[index])

    def _open_key_input_popup(self, index, key_input):
        controller = self.playalong_controller
        # The editor works in the player's buttons; key inputs are kept in the recording's.
        mapping = controller.get_button_map()
        to_recorded = inverse_map(mapping)

        def save(shown):
            edited = map_key_input(shown, to_recorded)
            if not edited.get("exact") and not (edited["motion"] or edited["buttons"] or edited["direction"]):
                self.flash("A key input needs a motion, a direction or a button (or to be an exact span)", "warning")
                return
            if edited["hold"] and not edited["exact"]:
                count = edited["end"] - edited["start"] + 1
                if not (edited["buttons"] or edited["direction"]):
                    self.flash("A hold needs a direction or a button to hold", "warning")
                    return
                if edited["hold"] > count:
                    self.flash(f"The hold is longer than its {count}-frame window", "warning")
                    return
            controller.set_key_input(index, edited)
            self.unsaved_edits = True
            self.flash(f"Key input {describe(shown)} on frames {edited['start']}-{edited['end']}")

        def delete():
            controller.remove_key_input(index)
            self.unsaved_edits = True

        delete = delete if index is not None else None
        title = "Mark key input" if index is None else "Edit key input"
        track = controller.get_input_track()
        KeyInputPopup(title, map_key_input(normalized(key_input), mapping), len(track) - 1, LIST_BUTTON_ORDER,
                      describe, lambda edited: map_key_input(derive_hold(track, edited["start"], edited["end"]), mapping),
                      save, delete).open()

    def remap_buttons(self):
        """Opens the button map for this recording: which of the player's buttons does what each
        recorded button did."""
        controller = self.playalong_controller
        if controller.is_recording() or not controller.track_length():
            self.flash("Open a recording to remap its buttons", "warning")
            return
        track = controller.get_input_track()
        used = {button: sum(1 for i, frame in enumerate(track) if frame[button] and (i == 0 or not track[i - 1][button]))
                for button in LIST_BUTTON_ORDER}
        ButtonMapPopup(full_map(controller.get_button_map()), used, self.set_button_map).open()

    def set_button_map(self, mapping):
        self.playalong_controller.set_button_map(mapping)
        self.unsaved_edits = True

    def toggle_practice(self):
        practice = not self.playalong_controller.is_practicing()
        self.playalong_controller.set_practice(practice)
        self.settings.set("practice", int(practice))
        self.flash("Practice: playing records your attempt" if practice else "Review: playing replays your attempt")

    def save_attempt(self):
        """Keeps the attempt on screen (or the latest run) with the track."""
        controller = self.playalong_controller
        if controller.is_recording():
            return
        saved = controller.save_attempt()
        if not saved:
            self.flash(keys.fill("No attempt to save yet: turn on Practice ({toggle_practice}) and play"), "warning")
            return
        self.store_saved_attempts(f"Saved attempt as \"{saved['name']}\"")

    def store_saved_attempts(self, message):
        """Writes the saved attempts into the track's file, so they're kept without re-saving the
        recording. A track that hasn't been saved yet keeps them until it is. The write queues
        behind any save still running, so it can't be overwritten by an older list."""
        if not self.track_path:
            self.flash(f"{message}; it's kept with the track when you save the recording "
                       f"({keys.either('save_recording')})")
            return
        path, saved_attempts = self.track_path, self.playalong_controller.get_saved()

        self.run_job("Saving attempts", lambda progress: track_file.update(path, saved_attempts=saved_attempts), message)

    def open_attempts(self):
        AttemptsPopup(self).open()

    def attempts_overview(self):
        """Saved attempts and recent runs (newest first) as the attempts manager lists them."""
        controller = self.playalong_controller

        def describe(kind, item, name):
            done, total = controller.score(item["attempt"])
            if controller.has_key_inputs():
                score = f"Key inputs {done}/{total}"
            else:
                score = f"Match {done / total:.0%}" if total else "Not played"
            created = time.localtime(item["created"])
            when = time.strftime("%H:%M:%S" if created[:3] == time.localtime()[:3] else "%b %d %H:%M", created)
            return {"kind": kind, "id": item["id"], "name": name, "score": score, "when": when,
                    "shown": item.get("shown")}

        return {
            "saved": [describe("saved", saved, saved["name"]) for saved in controller.get_saved_attempts()],
            "recent": [describe("recent", run, f"Run {run['id']}") for run in reversed(controller.get_runs())],
        }

    def rename_saved(self, saved_id, name):
        current = next(s for s in self.playalong_controller.get_saved_attempts() if s["id"] == saved_id)
        if current["name"] != name.strip():
            self.playalong_controller.update_saved(saved_id, name=name.strip())
            self.store_saved_attempts(f"Renamed to \"{name.strip()}\"")

    def show_saved(self, saved_id, shown):
        self.playalong_controller.update_saved(saved_id, shown=shown)
        self.store_saved_attempts("Shown in the input list" if shown else "Hidden from the input list")

    def save_run(self, run_id):
        saved = self.playalong_controller.save_attempt(run_id)
        if saved:
            self.store_saved_attempts(f"Saved Run {run_id} as \"{saved['name']}\"")

    def delete_attempt(self, kind, attempt_id):
        if kind == "saved":
            self.playalong_controller.remove_saved(attempt_id)
            self.store_saved_attempts("Deleted the saved attempt")
        else:
            self.playalong_controller.remove_run(attempt_id)

    def replay_attempt(self, kind, attempt_id):
        """Plays an earlier attempt back against the recording, in review mode so it isn't overwritten."""
        controller = self.playalong_controller
        items = controller.get_saved_attempts() if kind == "saved" else controller.get_runs()
        item = next((item for item in items if item["id"] == attempt_id), None)
        if item is None or controller.is_recording():
            return
        if controller.is_practicing():
            self.toggle_practice()
        controller.pause()
        controller.set_attempt_track(item["attempt"])
        controller.set_frame(0)
        controller.play()
        self.flash(f"Replaying {item.get('name') or 'Run ' + str(attempt_id)}; "
                   f"{keys.either('toggle_practice')} to practice again")

    def clear_attempt(self):
        self.playalong_controller.clear_attempt()

    def toggle_loop(self):
        loop = not self.playalong_controller.is_looping()
        self.playalong_controller.set_looping(loop)
        self.settings.set("loop", int(loop))

    def toggle_recording(self):
        if self.playalong_controller.is_recording():
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        # A raw take is easy to record again, so only edits are worth stopping for.
        if not self._keep_unsaved_work("recording a new take", edits_only=True):
            return
        self.track_path = None
        self.unsaved_take = self.unsaved_edits = False
        self.set_game(self.default_game(), None, mark_edited=False)
        self.playalong_controller.pause()
        self.capture_path = None
        frame_sink = None
        if self.settings.capture_video:
            self.take += 1
            self.screen_recorder = ScreenRecorder(
                output_idx=self.settings.display,
                max_height=self.settings.video_height or None,
                encoder=resolve_encoder(self.settings.encoder),
            )
            try:
                self.screen_recorder.start(os.path.join(self.temp_dir, f"take_{self.take}.mp4"))
                frame_sink = self.screen_recorder.capture
            except Exception as e:
                logger.exception("Couldn't start video capture")
                self.flash(f"Recording inputs only, video capture failed: {e}", "warning", 8)
                self.screen_recorder = None
        self.playalong_controller.start_recording(frame_sink)
        self.set_selection(None)

    def stop_recording(self):
        self.playalong_controller.stop_recording()
        self.unsaved_take = bool(self.playalong_controller.track_length())
        recorder, self.screen_recorder = self.screen_recorder, None
        if recorder:
            recorder.stop()
            # A frame can be sampled just after the video stopped; keep the two the same length.
            self.playalong_controller.truncate(recorder.frames_captured)
            # Jobs run in order, so anything queued after this sees the finished file.
            self.capture_path = recorder.output_path

            def finish(progress):
                try:
                    recorder.finish()
                except Exception:
                    self.capture_path = None
                    raise

            self.run_job("Finishing video", finish)

    # ---- Track ---------------------------------------------------------------------------------

    def clean_track(self):
        if not self.playalong_controller.is_recording():
            self.playalong_controller.clean_track()
            self.unsaved_edits = True
            self.flash("Track cleaned")

    def clear_track(self):
        self.playalong_controller.stop_demo()
        if self.playalong_controller.is_recording():
            self.stop_recording()
        if not self._keep_unsaved_work("clearing it"):
            return
        self.unsaved_take = self.unsaved_edits = False
        self.playalong_controller.clear_track()
        self.set_selection(None)
        self.capture_path = None
        self.track_path = None

    def recent_recordings(self):
        return [path for path in self.settings.recent.split("|") if path and os.path.exists(path)]

    def sample_recordings(self):
        """The sample recordings that come with the app (samples/*.json), the warm-up first."""
        folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples")
        try:
            names = [name for name in os.listdir(folder) if name.endswith(".json")]
        except OSError:
            return []
        return [os.path.join(folder, name) for name in sorted(names, key=lambda n: (not n.startswith("Warm-up"), n))]

    def try_warm_up(self):
        """Opens the warm-up sample and coaches the player through a first go."""
        warm_up = next((path for path in self.sample_recordings() if "Warm-up" in os.path.basename(path)), None)
        if not warm_up:
            self.flash("The warm-up sample is missing from the samples folder", "error", 6)
            return
        self.open_track(warm_up)
        self.coaching = bool(self.playalong_controller.track_length())

    def _remember_recent(self, path):
        recent = [path] + [p for p in self.recent_recordings() if os.path.normcase(p) != os.path.normcase(path)]
        self.settings.set("recent", "|".join(recent[:5]))
        self.menu_bar.set_recent(recent[:5])

    def open_track(self, path=None):
        """Opens a recording ready to practise: its inputs (.json), with its video if there is one.
        Either file of a saved recording can be picked, or dropped onto the window."""
        if not self._keep_unsaved_work("opening another"):
            return
        self.playalong_controller.stop_demo()
        if path is None:
            path = file_dialogs.open_file("Open recording", "Recordings (*.json, *.mp4)", "*.json;*.mp4")
        if not path:
            return
        if path.lower().endswith(".mp4"):
            path = os.path.splitext(path)[0] + ".json"
            if not os.path.exists(path):
                self.flash(f"No inputs for that video: {os.path.basename(path)} is missing", "error", 8)
                return
        elif not path.lower().endswith(".json"):
            self.flash("Open a recording's .json or .mp4 file", "warning")
            return
        try:
            data = track_file.load(path)
        except (OSError, track_file.TrackFileError) as e:
            self.flash(f"Couldn't open {os.path.basename(path)}: {e}", "error", 8)
            return
        if self.playalong_controller.is_recording():
            self.stop_recording()
        self.playalong_controller.set_input_track(data["inputs"], data.get("attempt"), data.get("notes"),
                                                  data.get("key_inputs"), data.get("saved_attempts"),
                                                  data.get("button_map"))
        self.set_game(data.get("game", self.default_game()), data.get("action_layout"), mark_edited=False)
        self.track_path = path
        video = os.path.splitext(path)[0] + ".mp4"
        self.capture_path = video if os.path.exists(video) else None
        self.set_selection(None)
        self.unsaved_take = self.unsaved_edits = False
        self._remember_recent(path)
        # Straight into practice: the input list, practice on, from the first frame.
        self.show_display("list")
        if not self.playalong_controller.is_practicing():
            self.toggle_practice()
        Window.set_title(f"{TITLE} - {os.path.splitext(os.path.basename(path))[0]}")
        self.flash(f"Opened {os.path.basename(path)}", "info", 6)

    def _track_data(self):
        """The track and everything made for it, for track_file.save()."""
        controller = self.playalong_controller
        attempt = controller.get_attempt_track()
        game, action_layout = controller.get_game()
        return {"inputs": controller.get_input_track(),
                "attempt": attempt if any(frame is not None for frame in attempt) else None,
                "notes": controller.get_notes(), "key_inputs": controller.get_key_inputs(),
                "saved_attempts": controller.get_saved(), "button_map": controller.get_button_map(),
                "game": game, "action_layout": action_layout if game else None}

    def save(self):
        """Saves into the open recording's file, or for a new take asks where to save it (with its
        video). Returns False if nothing was saved."""
        if self.playalong_controller.is_recording():
            self.stop_recording()
        if not self.track_path:
            return self.save_recording()
        data, path = self._track_data(), self.track_path

        self.run_job("Saving", lambda progress: track_file.save(path, data), f"Saved {os.path.basename(path)}")
        self.unsaved_edits = False
        return True

    def _keep_unsaved_work(self, doing, edits_only=False):
        """Before something replaces the track, offers to save unsaved work. Returns False to stop."""
        unsaved = self.unsaved_edits or (self.unsaved_take and not edits_only)
        if not unsaved or not self.playalong_controller.track_length():
            return True
        answer = file_dialogs.ask_save("Unsaved changes", f"Save the current recording before {doing}?")
        if answer == "save":
            return self.save()
        return answer == "discard"

    def quit(self):
        if self._keep_unsaved_work("quitting"):
            self.stop()

    def save_recording(self):
        """Saves the track (.json) and its video (.mp4) under a new name. Returns False if cancelled."""
        if self.playalong_controller.is_recording():
            self.stop_recording()
        data = self._track_data()
        if not data["inputs"]:
            self.flash("Nothing to save", "warning")
            return False
        path = file_dialogs.save_file("Save recording", "Recordings (*.mp4)", "*.mp4", "mp4")
        if not path:
            return False
        base = os.path.splitext(path)[0]
        export_overlay = self.settings.export_overlay_on_save
        self.track_path = base + ".json"  # Later saved attempts go straight into it.
        capture = self.capture_path  # Read now; a new take started before the job runs would reset it.
        encoder = resolve_encoder(self.settings.encoder)

        def save(progress):
            track_file.save(base + ".json", data)
            if not capture:
                return
            if os.path.abspath(capture) != os.path.abspath(base + ".mp4"):
                shutil.copyfile(capture, base + ".mp4")
            if export_overlay:
                self.job_label = "Exporting overlay"
                self._write_overlay(capture, base + "_overlay.mp4", len(data["inputs"]), encoder, progress)

        self.run_job("Saving", save, f"Saved {os.path.basename(base)}")
        self.unsaved_take = self.unsaved_edits = False
        self._remember_recent(base + ".json")
        Window.set_title(f"{TITLE} - {os.path.basename(base)}")
        return True

    def export_overlay_video(self):
        if self.playalong_controller.is_recording():
            self.stop_recording()
        if not self.capture_path:
            self.flash("No video for this track. Record with video capture on, or open a saved recording.", "warning", 6)
            return
        path = file_dialogs.save_file("Export overlay video", "Videos (*.mp4)", "*.mp4", "mp4")
        if path:
            capture, count = self.capture_path, self.playalong_controller.track_length()
            encoder = resolve_encoder(self.settings.encoder)
            self.run_job("Exporting overlay", lambda progress: self._write_overlay(capture, path, count, encoder, progress),
                         f"Exported {os.path.basename(path)}")

    def export_input_video(self):
        count = self.playalong_controller.track_length()
        if not count:
            self.flash("Nothing to export", "warning")
            return
        path = file_dialogs.save_file("Export input video", "Videos (*.mp4)", "*.mp4", "mp4")
        if path:
            encoder = resolve_encoder(self.settings.encoder)

            def export(progress):
                frames = self._on_ui(lambda: self._export_frames(EXPORT_SIZE, count, overlay=False))
                write_input_video(frames.frames(), count, EXPORT_SIZE, path, encoder=encoder, progress=progress)

            self.run_job("Exporting inputs", export, f"Exported {os.path.basename(path)}")

    def _write_overlay(self, capture, path, count, encoder, progress):
        """On the job thread: the current display drawn over the captured video."""
        size = video_size(capture)  # Known only once the capture is finished (an earlier job).
        frames = self._on_ui(lambda: self._export_frames(size, count, overlay=True))
        write_capture_and_overlay(capture, frames.frames(), count, path, encoder=encoder, progress=progress)

    def _export_frames(self, size, count, overlay):
        """Frames of the display showing, drawn offscreen for a video (see layouts/export_frames.py),
        from a copy of the recording: the input list without the player's lanes, or the arrow lanes
        or ring. An overlay is drawn over a transparent background, delayed by Settings > Overlay
        input delay to line up with the game."""
        controller = self.playalong_controller
        copy = PlayalongController()
        copy.set_lead_in(0)
        copy.set_input_track(controller.get_input_track(), notes=controller.get_notes(),
                             key_inputs=controller.get_key_inputs(), button_map=controller.get_button_map())
        copy.set_game(*controller.get_game())
        copy.set_show_actions(controller.is_showing_actions())
        lookahead = self.input_list_layout.lookahead
        mode = self.settings.input_display
        if mode == "lanes" or mode == "ring":
            display = ArrowLanesLayout() if mode == "lanes" else RingLayout()
            display.set_background((0, 0, 0) if overlay else theme.BACKGROUND)
        else:
            display = InputListLayout()
            display.lanes_shown = {"meter", "target", "keys"}
            display.show_notes, display.show_live, display.minimal = self.input_list_layout.show_notes, False, overlay
            display.textures.buttons.game = copy.get_game()[0]
            display.set_lookahead(lookahead)
        background = (0, 0, 0, 0) if overlay else (*theme.BACKGROUND, 1)
        delay = self.settings.overlay_delay if overlay else 0
        return DisplayFrames(display, copy, size, count, first=-delay, background=background, lookahead=lookahead)

    @staticmethod
    def _on_ui(make):
        """From a job: runs make() on the UI thread (widgets are made there) and returns its result."""
        done, result = threading.Event(), {}

        def run(dt):
            try:
                result["value"] = make()
            except Exception as e:
                result["error"] = e
            finally:
                done.set()

        Clock.schedule_once(run)
        if not done.wait(30):
            raise RuntimeError("the window stopped responding")
        if "error" in result:
            raise result["error"]
        return result["value"]

    def run_job(self, label, work, done_message=None):
        """Runs work(progress_callback) on the job thread and reports progress in the status bar."""

        def task():
            self.job_label, self.job_progress = label, None
            try:
                work(lambda fraction: setattr(self, "job_progress", fraction))
                if done_message:
                    self.flash(done_message, "info")
            except Exception as e:
                logger.exception("%s failed", label)
                self.flash(f"{label} failed: {e}", "error", 10)
            finally:
                self.job_label, self.job_progress = None, None

        self.jobs.submit(task)

    # ---- View ----------------------------------------------------------------------------------

    def toggle_overlay(self):
        self.overlay.toggle()

    def toggle_see_through(self):
        self.overlay.toggle_see_through()
        self.menu_bar.set_see_through(self.settings.see_through)

    def get_opacity(self):
        return self.settings.opacity

    def set_opacity(self, opacity):
        self.overlay.set_opacity(opacity)

    def preview_opacity(self, previewing):
        self.overlay.preview_opacity(previewing)

    def set_bars_visible(self, visible):
        """The menu and status bars (hidden in overlay mode)."""
        if visible:
            self.root_layout.add_widget(self.menu_bar, index=len(self.root_layout.children))
            self.root_layout.add_widget(self.status_bar, index=0)
        else:
            self.root_layout.remove_widget(self.menu_bar)
            self.root_layout.remove_widget(self.status_bar)

    def set_background(self, rgb):
        """The window's background colour changed: the displays' hold lines are hidden in it."""
        for display in (self.arrow_lanes_layout, self.ring_layout):
            display.set_background(rgb)

    def show_display(self, mode):
        mode = mode if mode in self.displays else "list"
        display = self.displays[mode]
        if self.display:
            self.stage.remove_widget(self.display)
        display.pos_hint = {"x": 0, "y": 0}  # Fill the stage, between the bars.
        self.stage.add_widget(display, index=len(self.stage.children))  # Under the card.
        self.display = display
        self.settings.set("input_display", mode)
        self.menu_bar.set_display_mode(mode)

    def default_game(self):
        game = self.settings.default_game
        return game if game in GAMES else None

    def set_game(self, game, action_layout=None, mark_edited=True):
        """The recording's game and action layout (None for the game's usual one)."""
        self.playalong_controller.set_game(game, action_layout)
        self.input_list_layout.textures.buttons.game = game
        if mark_edited:
            self.unsaved_edits = True

    def set_up_next_visible(self, visible):
        self.input_list_layout.show_next = visible
        self.settings.set("show_next", int(visible))
        self.menu_bar.set_up_next_visible(visible)

    def toggle_up_next(self):
        self.set_up_next_visible(not self.input_list_layout.show_next)

    def set_actions_visible(self, visible):
        self.playalong_controller.set_show_actions(visible)
        self.settings.set("show_actions", int(visible))
        self.menu_bar.set_actions_visible(visible)

    def toggle_actions(self):
        self.set_actions_visible(not self.playalong_controller.is_showing_actions())
        if self.playalong_controller.is_showing_actions() and not self.playalong_controller.get_game()[0]:
            self.flash("This recording has no game: choose one in Edit > Game actions...", "warning", 6)

    def edit_game_actions(self):
        controller = self.playalong_controller
        if controller.is_recording() or not controller.track_length():
            self.flash("Open a recording to set its game actions", "warning")
            return
        track = controller.get_input_track()
        used = {button: sum(1 for i, frame in enumerate(track) if frame[button] and (i == 0 or not track[i - 1][button]))
                for button in LIST_BUTTON_ORDER}
        current_game, current_layout = controller.get_game()
        GameActionsPopup({key: game["name"] for key, game in GAMES.items()}, current_game, current_layout,
                         {key: list(game["actions"]) for key, game in GAMES.items()},
                         {key: game["default_layout"] for key, game in GAMES.items()}, used,
                         lambda game, layout: self.set_game(game, layout)).open()

    def apply_feedback_settings(self):
        """The grade popups and the score banner, on or off in every display."""
        for display in self.displays.values():
            display.feedback.show_verdicts = self.settings.show_verdicts
            display.feedback.show_score = self.settings.show_score

    def set_notes_visible(self, visible):
        self.input_list_layout.show_notes = visible
        self.settings.set("show_notes", int(visible))
        self.menu_bar.set_notes_visible(visible)

    def set_lanes_shown(self, shown):
        self.input_list_layout.lanes_shown = shown
        self.settings.set("lanes", ",".join(name for name in LANES if name in shown))
        self.menu_bar.set_lanes_shown(shown)

    def toggle_lane(self, name):
        self.set_lanes_shown(self.input_list_layout.lanes_shown ^ {name})
        if self.display is not self.input_list_layout:
            self.show_display("list")  # Lanes are part of the input list.

    def toggle_notes(self):
        self.set_notes_visible(not self.input_list_layout.show_notes)

    def toggle_display(self):
        """The next display in turn: input list, arrow lanes, ring."""
        modes = list(self.displays)
        current = next(mode for mode, display in self.displays.items() if display is self.display)
        self.show_display(modes[(modes.index(current) + 1) % len(modes)])

    def show_help(self):
        HelpPopup(help_content.steps(), help_content.LEGENDS, help_content.key_columns(), self.open_user_guide,
                  self.open_keys).open()

    def open_keys(self):
        KeysPopup(keys.current, self.set_key_bindings, lambda waiting: setattr(self, "waiting_for_key", waiting)).open()

    def set_key_bindings(self, bindings):
        keys.use(bindings)
        self.settings.set("keys", bindings.to_setting(), write=True)
        self.menu_bar.refresh_keys()

    def open_user_guide(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "USER_GUIDE.md")
        try:
            os.startfile(path)
        except OSError as e:
            self.flash(f"Couldn't open the user guide ({path}): {e}", "error", 8)

    def open_settings_popup(self):
        readers = self.select_controller()
        SettingsPopup(dialog_columns(self, readers, list_displays() or [(0, "")], GAMES),
                      [("Change keys...", self.open_keys)]).open()

if __name__ == "__main__":
    # Kivy owns the root logger, so module logs (including late sampler ticks) go to ~/.kivy/logs.
    WomboComboApp().run()
