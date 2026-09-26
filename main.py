import json
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
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.modalview import ModalView
from kivy.uix.widget import Widget
import win32api
import win32con
import win32gui
from pynput import keyboard

import dialogs
from controller import direction_from_axes, find_controllers
from input_list import LIST_BUTTON_ORDER, full_map, inverse_map, map_key_input, map_state
from key_inputs import demo_track, derive, derive_hold, describe, normalized
from layouts.input_list_layout import LANES, InputListLayout
from games import GAMES
from layouts.menu_layout import AttemptsPopup, ButtonMapPopup, GameActionsPopup, HelpPopup, KeyInputPopup, Menu, MenuBar, NotePopup, SettingsPopup
from layouts.playalong_layout import PlayAlongLayout
from playalong import PlayalongController
from sampler import FPS, InputSampler
from screen_capture import ScreenRecorder, list_displays, prepare_capture
from virtual_pad import VirtualPad, VirtualPadError
from video_writer import nvenc_available, resolve_encoder, write_capture_and_overlay, write_input_video

logger = logging.getLogger(__name__)
TITLE = "Wombo Combo"

HOTKEYS = [
    ("F1", "Help and keys", "show_help"),
    ("F2", "Overlay mode (on top, borderless)", "toggle_overlay"),
    ("F3", "Switch between ring and input list", "toggle_display"),
    ("Shift+F3", "Show / hide notes", "toggle_notes"),
    ("F4", "Practice on/off (record your attempt while playing)", "toggle_practice"),
    ("F5", "Restart playback", "restart_playback"),
    ("F6", "Play", "play"),
    ("F7", "Pause (also stops a demo)", "pause"),
    ("Shift+F6", "Demo the recording in game (virtual controller)", "demo_recording"),
    ("Shift+F7", "Demo just the key inputs in game", "demo_key_inputs"),
    ("F8", "Start / stop recording", "toggle_recording"),
    ("F11", "Open a recording", "open_track"),
    ("F12", "Save recording as (with its video)", "save_recording"),
]

WELCOME = (
    "[size=22sp][b]Wombo Combo[/b][/size]\n\n"
    "Practise fighting game combos frame by frame. The inputs scroll toward a line, you press them as they "
    "arrive, and it shows exactly how early or late you were.\n\n"
    "New here? The warm-up takes ten seconds."
)

COACH = (
    "[size=20sp][b]Ready when you are[/b][/size]\n\n"
    "Press [b]Space[/b] (or [b]Start[/b] on your controller). After a second to get ready, press each input "
    "as it reaches the white line.\n\n"
    "{controller}"
)

# Playing without a controller: SF6's PC keyboard layout. Key codes are Kivy's.
KEYBOARD_KEYS = {
    273: "up", 274: "down", 275: "right", 276: "left",
    ord("w"): "up", ord("s"): "down", ord("d"): "right", ord("a"): "left",
    ord("u"): "u", ord("i"): "i", ord("o"): "o", ord("j"): "j", ord("k"): "k", ord("l"): "l",
}
ARROW_KEYS = (273, 274, 275, 276)
KEYBOARD_ACTIONS = {"u": "LP", "i": "MP", "o": "HP", "j": "LK", "k": "MK", "l": "HK"}

VIDEO_HEIGHTS = [("Native", 0), ("1080p", 1080), ("720p", 720)]
ENCODERS = [("Auto", "auto"), ("CPU (x264)", "x264"), ("NVIDIA (NVENC)", "nvenc")]


def format_time(frames):
    seconds = frames / FPS
    return f"{int(seconds // 60)}:{seconds % 60:05.2f}"


class WomboComboApp(App):
    title = TITLE

    def __init__(self):
        super().__init__()
        self.topmost = False
        self.playalong_controller = PlayalongController()
        self.sampler = InputSampler(self.playalong_controller.tick)
        self.screen_recorder = None
        self.capture_path = None  # Video that belongs to the current input track, if any.
        self.track_path = None  # The current track's .json file, once it's been opened or saved.
        self.virtual_pad = None  # Plugged in the first time a demo plays.
        self.coaching = False  # Showing the "press Space" card until the player first plays.
        self.keys_down = set()  # Game keys held on the keyboard, for playing without a controller.
        self.unsaved_take = False  # A new take that hasn't been saved anywhere yet.
        self.unsaved_edits = False  # Notes, key inputs or cleaning not yet saved.
        self.temp_dir = tempfile.mkdtemp(prefix="wombo_")
        self.take = 0
        self.jobs = ThreadPoolExecutor(max_workers=1)  # Saves/exports run one at a time, off the UI thread.
        self.job_label = None
        self.job_progress = None
        self.message = None  # (markup text, expiry time)
        self.selection = None  # (start, end) frames selected in the input list, inclusive.

    # ---- Setup ---------------------------------------------------------------------------------

    def build_config(self, config):
        config.setdefaults("wombo", {
            "controller": "auto",
            "capture_video": 1,
            "display": 0,
            "video_height": 1080,
            "encoder": "auto",
            "overlay_delay": 4,
            "export_overlay_on_save": 1,
            "opacity": 0.5,
            "loop": 1,
            "practice": 1,
            "list_frame_width": 0,  # Pixels per frame in the input list; 0 = one label wide.
            "input_display": "list",  # The input list is where practice happens; the ring is optional.
            "show_notes": 1,
            "show_actions": 1,  # Show a game's actions (a medium punch, a Drive Impact) instead of buttons.
            "default_game": "sf6",  # Game for new recordings, and old ones that don't say.
            "first_run": 1,  # Opens the warm-up the first time the app starts.
            "lanes": ",".join(LANES),  # Input list lanes shown.
            "recent": "",  # Recently opened recordings (.json paths), newest first, separated by "|".
            "recent_attempts": 5,  # Recent runs shown in the input list.
            "lead_in": 60,  # Frames of run-up before practice playback, to get ready.
            "demo_countdown": 180,  # Frames before a demo starts, to switch to the game.
        })

    def get_application_config(self):
        return super().get_application_config(os.path.join(self.user_data_dir, "%(appname)s.ini"))

    def open_settings(self, *args):
        return False  # Disable Kivy's built-in F1 settings panel; F1 shows hotkeys instead.

    def build(self):
        Window.clearcolor = (0.2, 0.2, 0.2, 0.5)
        # Up to 1920x1080, but never bigger than the screen (with room for the taskbar).
        screen_width, screen_height = win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1)
        Window.size = (min(1920, int(screen_width * 0.9)), min(1080, int(screen_height * 0.85)))
        Window.borderless = False
        Window.fullscreen = False

        self.playalong_controller.set_looping(self.config.getboolean("wombo", "loop"))
        self.playalong_layout = PlayAlongLayout()
        self.input_list_layout = InputListLayout()
        frame_width = self.config.getfloat("wombo", "list_frame_width")
        if frame_width:
            self.input_list_layout.set_zoom(dp(frame_width))
        self.input_list_layout.on_scrub = self.scrub
        self.input_list_layout.on_zoom = self.set_list_zoom
        self.input_list_layout.on_select = self.set_selection
        self.input_list_layout.on_note_click = self.edit_note
        self.input_list_layout.on_key_input_click = self.edit_key_input
        self.input_list_layout.on_context_menu = self.open_context_menu
        self.playalong_controller.set_practice(self.config.getboolean("wombo", "practice"))
        self.playalong_controller.set_history_count(self.config.getint("wombo", "recent_attempts"))
        self.playalong_controller.lead_in = self.config.getint("wombo", "lead_in")
        self.menu_bar = MenuBar(self)
        self.root_layout = BoxLayout(orientation="vertical")
        self.root_layout.add_widget(self.menu_bar)
        self.display = None
        self.show_display(self.config.get("wombo", "input_display"))
        self.set_notes_visible(self.config.getboolean("wombo", "show_notes"))
        self.set_game(self.default_game(), None, mark_edited=False)
        self.set_actions_visible(self.config.getboolean("wombo", "show_actions"))
        self.set_lanes_shown(set(filter(None, self.config.get("wombo", "lanes").split(","))))
        self.menu_bar.set_recent(self.recent_recordings())
        return self.root_layout

    def on_start(self):
        self.select_controller()
        self.sampler.extra = self.keyboard_state
        self.sampler.on_menu = lambda name: Clock.schedule_once(lambda dt: self.on_menu_button(name))
        Window.bind(on_key_up=self.on_key_up, focus=lambda window, focused: focused or self.keys_down.clear())
        self.sampler.start()
        if self.config.getboolean("wombo", "first_run"):
            # Straight into something to try: nothing to find, open or set up first.
            self.config.set("wombo", "first_run", 0)
            self.config.write()
            Clock.schedule_once(lambda dt: self.try_warm_up())
        Clock.schedule_interval(self.refresh, 0)  # Every rendered frame.
        Clock.schedule_interval(self.update_status, 0.1)
        Clock.schedule_interval(self.check_controller, 1.0)
        if self.config.get("wombo", "encoder") == "auto":
            threading.Thread(target=nvenc_available, daemon=True).start()  # Warm the cached probe.
        if self.config.getboolean("wombo", "capture_video"):
            # Creating the capture device takes ~100 ms; do it now rather than when recording starts.
            prepare_capture(self.config.getint("wombo", "display"))

        # Global keyboard listener for when the window isn't selected. The callback runs inside a
        # system-wide keyboard hook, so it only hands the action to the UI thread and returns.
        # Keyed by (shift held, key), e.g. "Shift+F3" -> (True, Key.f3).
        actions = {}
        for key, _, action in HOTKEYS:
            *modifiers, name = key.lower().split("+")
            actions[("shift" in modifiers, getattr(keyboard.Key, name))] = action
        shift_keys = {keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r}
        held_shift = set()

        # Neither callback may return False: that stops the listener.
        def on_press(key):
            if key in shift_keys:
                held_shift.add(key)
            action = actions.get((bool(held_shift), key))
            if action:
                Clock.schedule_once(lambda dt: getattr(self, action)())

        def on_release(key):
            held_shift.discard(key)

        self.listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self.listener.start()
        Window.bind(on_key_down=self.on_key_down)
        Window.bind(on_request_close=lambda *args: not self._keep_unsaved_work("quitting"))
        Window.bind(on_drop_file=lambda window, filename, *args: self.open_track(filename.decode("utf-8")))

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
        return controller.is_playing() and controller.practice and not controller.demo_kind()

    def keyboard_state(self):
        """The keyboard as a controller (from the sampler thread), in the player's buttons: SF6's PC
        layout of WASD or arrows to move, U I O punches, J K L kicks."""
        keys = set(self.keys_down)
        if not keys:
            return None
        x = (keys & {"right"} and 1 or 0) - (keys & {"left"} and 1 or 0)
        y = (keys & {"up"} and 1 or 0) - (keys & {"down"} and 1 or 0)
        state = {"direction": direction_from_axes(x, y)}
        controller = self.playalong_controller
        layout = controller.action_layout or GAMES["sf6"]["default_layout"]
        by_action = {action: recorded for recorded, action in layout.items()}
        mapping = full_map(controller.get_button_map())
        for key, action in KEYBOARD_ACTIONS.items():
            if key in keys and action in by_action:
                state[mapping[by_action[action]]] = 1  # The recorded button, then the player's for it.
        return state

    def on_key_up(self, window, key, scancode):
        name = KEYBOARD_KEYS.get(key)
        if name:
            self.keys_down.discard(name)

    def on_key_down(self, window, key, scancode, codepoint, modifiers):
        """Shortcuts that only apply while the app window is focused."""
        if any(isinstance(child, ModalView) for child in Window.children):
            return False  # A popup is open; let it have the keys.
        # Num Lock (usually on) and the other locks come through as modifiers; they aren't keys held down.
        modifiers = [modifier for modifier in modifiers if modifier not in ("numlock", "capslock", "scrolllock")]
        name = KEYBOARD_KEYS.get(key)
        if name and not modifiers:
            self.keys_down.add(name)
            # The arrows always play. While practising the letters do too; when paused, they're shortcuts.
            if key in ARROW_KEYS or self._playing_by_keyboard():
                return True
        if key == 27:  # Esc
            self.set_selection(None)
            return True
        if key == 32 and not modifiers:  # Space
            self.toggle_playback()
            return True
        if key == 278 and not modifiers:  # Home
            self.restart_playback()
            return True
        if codepoint == "o" and modifiers == ["ctrl"]:
            self.open_track()
            return True
        if codepoint == "s" and modifiers == ["ctrl"]:
            self.save()
            return True
        if codepoint == "n" and not modifiers:
            self.add_note()
            return True
        if codepoint == "k" and not modifiers:
            self.mark_key_input()
            return True
        if codepoint == "s" and not modifiers:
            self.save_attempt()
            return True
        if codepoint == "a" and not modifiers:
            self.open_attempts()
            return True
        return False

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
        if self.display is self.input_list_layout:
            self.input_list_layout.dim_non_key = bool(self.playalong_controller.key_inputs)
            frames_before, frames_after = self.input_list_layout.frames_needed()
            self.input_list_layout.update_state(self.playalong_controller.list_snapshot(frames_before, frames_after))
            if self.topmost:
                self._fit_overlay()
        else:
            controller_state, upcoming_frames = self.playalong_controller.snapshot()
            self.playalong_layout.update_state(controller_state, upcoming_frames)

    def select_controller(self):
        readers = find_controllers()
        wanted = self.config.get("wombo", "controller")
        self.sampler.reader = next((r for r in readers if r.name == wanted), readers[0] if readers else None)
        return readers

    def check_controller(self, dt):
        reader = self.sampler.reader
        if reader is None or not reader.connected:
            self.select_controller()

    def flash(self, text, color="dddddd", seconds=4):
        self.message = (f"[color={color}]{text}[/color]", time.time() + seconds)
        # Also logged: a message shown while the game has focus is never seen.
        logger.log(logging.WARNING if color in ("ff6b6b", "ffb454") else logging.INFO, "Status: %s", text)

    @staticmethod
    def beep(ok=True):
        """A system sound for feedback that has to reach the player in game (asynchronous)."""
        winsound.MessageBeep(winsound.MB_OK if ok else winsound.MB_ICONHAND)

    def update_status(self, dt):
        controller = self.playalong_controller
        # A demo's countdown ticks once a second, so it can be followed without seeing the app.
        if controller.demo_kind() and controller.get_lead():
            second = -(-controller.get_lead() // FPS)
            if second != getattr(self, "_countdown_second", None):
                self._countdown_second = second
                self.beep()
        stats = self.sampler.stats
        frames = len(controller.input_track)
        parts = []
        if controller.is_recording():
            parts.append(f"[color=ff6b6b]REC[/color] {format_time(frames)}")
            if controller.filled_frames:
                parts.append(f"[color=ffb454]{controller.filled_frames} late frames[/color]")
            backlog = self.screen_recorder.backlog() if self.screen_recorder else 0
            if backlog > FPS // 2:
                parts.append(f"[color=ffb454]encoder {backlog / FPS:.1f}s behind[/color]")
        elif frames:
            if controller.demo_kind():
                lead = controller.get_lead()
                state = f"DEMO IN {lead / FPS:.1f}s" if lead else f"DEMO ({controller.demo_kind()})"
            elif controller.get_lead():
                state = "GET READY"
            elif controller.is_playing():
                state = "PRACTICE" if controller.practice else "REVIEW"
            else:
                state = "PAUSED"
            parts.append(f"{state} {format_time(controller.get_current_frame())} / {format_time(frames)}")
            hits, total = controller.key_input_score()
            if total:
                # With key inputs marked, only they count; other frames are non-essential.
                parts.append(f"Key inputs {hits}/{total}")
            elif controller.attempted_frames:
                accuracy = controller.matched_frames / controller.attempted_frames
                parts.append(f"Match {accuracy:.0%} of {controller.attempted_frames}f")
            if controller.button_map:
                parts.append("[color=8fb8ff]Buttons remapped[/color]")
            if self.unsaved_take or self.unsaved_edits:
                parts.append("[color=ffb454]Unsaved[/color]")
        else:
            parts.append("No track")
        if self.job_label:
            progress = f" {int(self.job_progress * 100)}%" if self.job_progress is not None else "..."
            parts.append(f"{self.job_label}{progress}")
        if self.selection:
            start, end = self.selection
            span = f"frame {start}" if start == end else f"frames {start}-{end} ({end - start + 1}f)"
            parts.append(f"[color=8fb8ff]Selected {span}[/color]")
        if self.message and time.time() < self.message[1]:
            parts.append(self.message[0])
        reader = self.sampler.reader
        parts.append(reader.name if reader and reader.connected else "[color=ffb454]No controller[/color]")
        parts.append(f"{stats.rate:.1f} Hz")
        self.menu_bar.update(controller.is_recording(), controller.is_playing(), controller.loop, controller.practice,
                             "   |   ".join(parts), demoing=bool(controller.demo_kind()))
        card, buttons = self._card(frames)
        # Over the game, the overlay shows the list only; the hints are for the app window.
        hint = "" if self.topmost or card else self._next_step_hint()  # The card says it all when shown.
        self.input_list_layout.set_guidance(hint, card, buttons)

    def _card(self, frames):
        """The card in the middle of the list: getting started with nothing loaded, or a first go at
        the warm-up until the player starts playing. Returns (text, buttons)."""
        controller = self.playalong_controller
        if controller.is_recording():
            return "", ()
        if not frames:
            return WELCOME, (("Try the warm-up", self.try_warm_up, True),
                             ("Open a recording...", self.open_track, False),
                             ("Record your own (F8)", self.toggle_recording, False))
        if self.coaching and not controller.is_playing():
            reader = self.sampler.reader
            if reader and reader.connected:
                note = f"Using [b]{reader.name}[/b]: press a button and it shows up under the line."
            else:
                note = ("[color=ffb454][b]No controller found.[/b][/color] Plug one in (it's picked up by itself), "
                        "or play on the keyboard: [b]WASD[/b] to move, [b]U I O[/b] punches, [b]J K L[/b] kicks.")
            return COACH.format(controller=note), (("Start", self.play, True),)
        return "", ()

    def _next_step_hint(self):
        """One line on what to do next, for where the player is right now."""
        controller = self.playalong_controller
        if controller.is_recording():
            return ("[b]Recording.[/b] Perform the combo, then press [b]F8[/b] (or Stop) to finish. "
                    "F-key hotkeys work while the game has focus.")
        if not controller.input_track:
            return ""
        if controller.demo_kind():
            if controller.get_lead():
                return (f"[b]Demo of the {controller.demo_kind()}[/b] starts in {controller.get_lead() / FPS:.1f}s. "
                        "Switch to the game: the virtual controller has to be the one playing your character. "
                        "[b]Space[/b] / [b]F7[/b] stops.")
            return (f"[b]Demo:[/b] the virtual controller is playing the {controller.demo_kind()}; the You lane "
                    "shows what it presses. [b]Space[/b] / [b]F7[/b] stops.")
        if self.selection:
            return ("[b]Frames selected.[/b] [b]N[/b] adds a note, [b]K[/b] marks what must be pressed there "
                    "(a key input), right-click for more, [b]Esc[/b] clears.")
        if controller.get_lead():
            return f"[b]Get ready.[/b] The first input reaches the line in {controller.get_lead() / FPS:.1f}s."
        if controller.is_playing():
            if controller.practice:
                reader = self.sampler.reader
                keys = ("" if reader and reader.connected else
                        " No controller: [b]WASD[/b] moves, [b]U I O[/b] punch, [b]J K L[/b] kick.")
                return ("[b]Practising.[/b] Press each input as it reaches the line. [b]Start[/b] / [b]Space[/b] "
                        "pauses, [b]Back[/b] / [b]Home[/b] starts over." + keys)
            return "[b]Reviewing[/b] your attempt against the recording. [b]F4[/b] goes back to practice."
        if controller.attempted_frames:
            return ("Scroll or drag to look back at your attempt. [b]S[/b] saves it, [b]A[/b] lists all "
                    "attempts, [b]Space[/b] practises again.")
        if not controller.key_inputs:
            return ("Press [b]Space[/b] (or [b]F6[/b] in game) to practise. Tip: drag in the frame meter to select "
                    "frames and press [b]K[/b] to mark what really matters; only those are scored then.")
        return ("Press [b]Space[/b] (or [b]F6[/b] in game) to practise. Hit the key inputs (outlined) as they "
                "reach the line.")

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
        if controller.is_recording() or not controller.input_track:
            self.flash("Open or record something to demo first", "ffb454")
            self.beep(False)
            return
        if kind == "key inputs":
            if not controller.key_inputs:
                self.flash("No key inputs to demo: select frames and press K to mark them", "ffb454", 6)
                self.beep(False)
                return
            track = demo_track(controller.get_key_inputs(), controller.get_input_track())
        else:
            track = controller.get_input_track()
        if self.virtual_pad is None:
            try:
                self.virtual_pad = VirtualPad()
            except VirtualPadError as e:
                self.flash(str(e), "ff6b6b", 12)
                self.beep(False)
                return
        controller.pause()  # Also ends a demo already playing.
        countdown = self.config.getint("wombo", "demo_countdown")
        mapping, pad = controller.get_button_map(), self.virtual_pad
        # The game reads the player's own layout, so the demo presses the player's buttons.
        controller.start_demo(track, lambda state: pad.send(map_state(state, mapping)), countdown, kind)
        self.set_selection(None)
        self.flash(f"Demo of the {kind} in {countdown / FPS:g}s: switch to the game", "8fd18f", 5)
        self._countdown_second = None  # update_status ticks each second of the countdown audibly.

    def scrub(self, frames):
        """Moves the playhead (pausing playback) so a part of the run can be inspected."""
        controller = self.playalong_controller
        if not controller.is_recording():
            controller.pause()
            controller.set_frame(controller.get_current_frame() + frames)

    def set_list_zoom(self, px_per_frame):
        self.config.set("wombo", "list_frame_width", round(px_per_frame / dp(1), 1))

    def set_selection(self, start, end=None):
        """Selects frames start..end (inclusive, either order) of the track, or clears with None."""
        if start is not None:
            last = len(self.playalong_controller.input_track) - 1
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
        if controller.is_recording() or not controller.input_track:
            return
        frame = max(0, min(frame, len(controller.input_track) - 1))
        if not self.selection or not self.selection[0] <= frame <= self.selection[1]:
            self.set_selection(frame, frame)
        start = self.selection[0]
        menu = Menu()
        menu.add_item("Add note", self.add_note, "N")
        menu.add_item("Mark key input", self.mark_key_input, "K")
        menu.add_item("Practise from here", lambda: (controller.set_frame(start), self.play()))
        menu.add_item("Clear selection", lambda: self.set_selection(None), "Esc")
        menu.add_separator()
        menu.add_item("Save attempt", self.save_attempt, "S")
        menu.add_item("Attempts...", self.open_attempts, "A")
        # A dropdown opens from a widget, so a one-pixel anchor stands in for the cursor.
        anchor = Widget(size_hint=(None, None), size=(1, 1), pos=pos)
        self.input_list_layout.add_widget(anchor)
        menu.bind(on_dismiss=lambda *_: self.input_list_layout.remove_widget(anchor))
        self._context_menu = menu  # Kivy holds bound callbacks weakly; keep the menu alive while open.
        menu.open(anchor)

    def add_note(self):
        """Opens the note editor for the selected frames, or the frame on the line if none are selected."""
        controller = self.playalong_controller
        if controller.is_recording() or not controller.input_track:
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
        if controller.is_recording() or not controller.input_track:
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
                self.flash("A key input needs a motion, a direction or a button (or to be an exact span)", "ffb454")
                return
            if edited["hold"] and not edited["exact"]:
                count = edited["end"] - edited["start"] + 1
                if not (edited["buttons"] or edited["direction"]):
                    self.flash("A hold needs a direction or a button to hold", "ffb454")
                    return
                if edited["hold"] > count:
                    self.flash(f"The hold is longer than its {count}-frame window", "ffb454")
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
        if controller.is_recording() or not controller.input_track:
            self.flash("Open a recording to remap its buttons", "ffb454")
            return
        track = controller.get_input_track()
        used = {button: sum(1 for i, frame in enumerate(track) if frame[button] and (i == 0 or not track[i - 1][button]))
                for button in LIST_BUTTON_ORDER}
        ButtonMapPopup(full_map(controller.get_button_map()), used, self.set_button_map).open()

    def set_button_map(self, mapping):
        self.playalong_controller.set_button_map(mapping)
        self.unsaved_edits = True

    def toggle_practice(self):
        practice = not self.playalong_controller.practice
        self.playalong_controller.set_practice(practice)
        self.config.set("wombo", "practice", int(practice))
        self.flash("Practice: playing records your attempt" if practice else "Review: playing replays your attempt")

    def save_attempt(self):
        """Keeps the attempt on screen (or the latest run) with the track."""
        controller = self.playalong_controller
        if controller.is_recording():
            return
        saved = controller.save_attempt()
        if not saved:
            self.flash("No attempt to save yet: turn on Practice (F4) and play", "ffb454")
            return
        self.store_saved_attempts(f"Saved attempt as \"{saved['name']}\"")

    def store_saved_attempts(self, message):
        """Writes the saved attempts into the track's file, so they're kept without re-saving the
        recording. A track that hasn't been saved yet keeps them until it is. The write queues
        behind any save still running, so it can't be overwritten by an older list."""
        if not self.track_path:
            self.flash(f"{message}; it's kept with the track when you save the recording (F12)")
            return
        path, saved_attempts = self.track_path, self.playalong_controller.get_saved()

        def write(progress):
            with open(path, "r") as fin:
                data = json.load(fin)
            if not isinstance(data, dict):
                data = {"fps": FPS, "inputs": data}  # Older saves are a bare list of frames.
            data["saved_attempts"] = saved_attempts
            with open(path, "w") as fout:
                json.dump(data, fout, indent=1, sort_keys=True)

        self.run_job("Saving attempts", write, message)

    def open_attempts(self):
        AttemptsPopup(self).open()

    def attempts_overview(self):
        """Saved attempts and recent runs (newest first) as the attempts manager lists them."""
        controller = self.playalong_controller

        def describe(kind, item, name):
            done, total = controller.score(item["attempt"])
            if controller.key_inputs:
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
        if controller.practice:
            self.toggle_practice()
        controller.pause()
        controller.set_attempt_track(item["attempt"])
        controller.set_frame(0)
        controller.play()
        self.flash(f"Replaying {item.get('name') or 'Run ' + str(attempt_id)}; F4 to practice again")

    def clear_attempt(self):
        self.playalong_controller.clear_attempt()

    def toggle_loop(self):
        loop = not self.playalong_controller.loop
        self.playalong_controller.set_looping(loop)
        self.config.set("wombo", "loop", int(loop))

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
        if self.config.getboolean("wombo", "capture_video"):
            self.take += 1
            self.screen_recorder = ScreenRecorder(
                output_idx=self.config.getint("wombo", "display"),
                max_height=self.config.getint("wombo", "video_height") or None,
                encoder=resolve_encoder(self.config.get("wombo", "encoder")),
            )
            try:
                self.screen_recorder.start(os.path.join(self.temp_dir, f"take_{self.take}.mp4"))
                frame_sink = self.screen_recorder.capture
            except Exception as e:
                logger.exception("Couldn't start video capture")
                self.flash(f"Recording inputs only, video capture failed: {e}", "ffb454", 8)
                self.screen_recorder = None
        self.playalong_controller.start_recording(frame_sink)
        self.set_selection(None)

    def stop_recording(self):
        self.playalong_controller.stop_recording()
        self.unsaved_take = bool(self.playalong_controller.input_track)
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
        return [path for path in self.config.get("wombo", "recent").split("|") if path and os.path.exists(path)]

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
            self.flash("The warm-up sample is missing from the samples folder", "ff6b6b", 6)
            return
        self.open_track(warm_up)
        self.coaching = bool(self.playalong_controller.input_track)

    def _remember_recent(self, path):
        recent = [path] + [p for p in self.recent_recordings() if os.path.normcase(p) != os.path.normcase(path)]
        self.config.set("wombo", "recent", "|".join(recent[:5]))
        self.menu_bar.set_recent(recent[:5])

    def open_track(self, path=None):
        """Opens a recording ready to practise: its inputs (.json), with its video if there is one.
        Either file of a saved recording can be picked, or dropped onto the window."""
        if not self._keep_unsaved_work("opening another"):
            return
        self.playalong_controller.stop_demo()
        if path is None:
            path = dialogs.open_file("Open recording", "Recordings (*.json, *.mp4)", "*.json;*.mp4")
        if not path:
            return
        if path.lower().endswith(".mp4"):
            path = os.path.splitext(path)[0] + ".json"
            if not os.path.exists(path):
                self.flash(f"No inputs for that video: {os.path.basename(path)} is missing", "ff6b6b", 8)
                return
        elif not path.lower().endswith(".json"):
            self.flash("Open a recording's .json or .mp4 file", "ffb454")
            return
        try:
            with open(path, "r") as fin:
                data = json.load(fin)
        except (OSError, ValueError) as e:
            self.flash(f"Couldn't open {os.path.basename(path)}: {e}", "ff6b6b", 8)
            return
        if self.playalong_controller.is_recording():
            self.stop_recording()
        if isinstance(data, dict):
            self.playalong_controller.set_input_track(data["inputs"], data.get("attempt"), data.get("notes"),
                                                      data.get("key_inputs"), data.get("saved_attempts"),
                                                      data.get("button_map"))
            self.set_game(data.get("game", self.default_game()), data.get("action_layout"), mark_edited=False)
        else:
            self.playalong_controller.set_input_track(data)  # Older saves are a bare list of frames.
            self.set_game(self.default_game(), None, mark_edited=False)
        self.track_path = path
        video = os.path.splitext(path)[0] + ".mp4"
        self.capture_path = video if os.path.exists(video) else None
        self.set_selection(None)
        self.unsaved_take = self.unsaved_edits = False
        self._remember_recent(path)
        # Straight into practice: the input list, practice on, from the first frame.
        self.show_display("list")
        if not self.playalong_controller.practice:
            self.toggle_practice()
        Window.set_title(f"{TITLE} - {os.path.splitext(os.path.basename(path))[0]}")
        self.flash(f"Opened {os.path.basename(path)}. Press Space (or F6 in game) to practise", "8fd18f", 6)

    def _track_data(self):
        """The track and everything made for it, as saved in its .json."""
        controller = self.playalong_controller
        data = {"fps": FPS, "inputs": controller.get_input_track()}
        attempt = controller.get_attempt_track()
        if any(frame is not None for frame in attempt):
            data["attempt"] = attempt
        for key, value in (("notes", controller.get_notes()), ("key_inputs", controller.get_key_inputs()),
                           ("saved_attempts", controller.get_saved()), ("button_map", controller.get_button_map()),
                           ("game", controller.game), ("action_layout", controller.action_layout if controller.game else None)):
            if value:
                data[key] = value
        return data

    def save(self):
        """Saves into the open recording's file, or for a new take asks where to save it (with its
        video). Returns False if nothing was saved."""
        if self.playalong_controller.is_recording():
            self.stop_recording()
        if not self.track_path:
            return self.save_recording()
        data, path = self._track_data(), self.track_path

        def write(progress):
            with open(path, "w") as fout:
                json.dump(data, fout, indent=1, sort_keys=True)

        self.run_job("Saving", write, f"Saved {os.path.basename(path)}")
        self.unsaved_edits = False
        return True

    def _keep_unsaved_work(self, doing, edits_only=False):
        """Before something replaces the track, offers to save unsaved work. Returns False to stop."""
        unsaved = self.unsaved_edits or (self.unsaved_take and not edits_only)
        if not unsaved or not self.playalong_controller.input_track:
            return True
        answer = dialogs.ask_save("Unsaved changes", f"Save the current recording before {doing}?")
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
        inputs, notes = data["inputs"], data.get("notes", [])
        if not inputs:
            self.flash("Nothing to save", "ffb454")
            return False
        path = dialogs.save_file("Save recording", "Recordings (*.mp4)", "*.mp4", "mp4")
        if not path:
            return False
        base = os.path.splitext(path)[0]
        export_overlay = self.config.getboolean("wombo", "export_overlay_on_save")
        self.track_path = base + ".json"  # Later saved attempts go straight into it.
        capture = self.capture_path  # Read now; a new take started before the job runs would reset it.

        def save(progress):
            with open(base + ".json", "w") as fout:
                json.dump(data, fout, indent=1, sort_keys=True)
            if not capture:
                return
            if os.path.abspath(capture) != os.path.abspath(base + ".mp4"):
                shutil.copyfile(capture, base + ".mp4")
            if export_overlay:
                self.job_label = "Exporting overlay"
                write_capture_and_overlay(capture, inputs, base + "_overlay.mp4", notes=notes,
                                          **self._export_options(progress))

        self.run_job("Saving", save, f"Saved {os.path.basename(base)}")
        self.unsaved_take = self.unsaved_edits = False
        self._remember_recent(base + ".json")
        Window.set_title(f"{TITLE} - {os.path.basename(base)}")
        return True

    def export_overlay_video(self):
        if self.playalong_controller.is_recording():
            self.stop_recording()
        if not self.capture_path:
            self.flash("No video for this track. Record with video capture on, or open a saved recording.", "ffb454", 6)
            return
        path = dialogs.save_file("Export overlay video", "Videos (*.mp4)", "*.mp4", "mp4")
        if path:
            inputs = self.playalong_controller.get_input_track()
            notes = self.playalong_controller.get_notes()
            capture = self.capture_path
            self.run_job(
                "Exporting overlay",
                lambda progress: write_capture_and_overlay(capture, inputs, path, notes=notes,
                                                           **self._export_options(progress)),
                f"Exported {os.path.basename(path)}",
            )

    def export_input_video(self):
        inputs = self.playalong_controller.get_input_track()
        notes = self.playalong_controller.get_notes()
        key_inputs = self.playalong_controller.get_key_inputs()
        if not inputs:
            self.flash("Nothing to export", "ffb454")
            return
        path = dialogs.save_file("Export input video", "Videos (*.mp4)", "*.mp4", "mp4")
        if path:
            encoder = resolve_encoder(self.config.get("wombo", "encoder"))
            self.run_job(
                "Exporting inputs",
                lambda progress: write_input_video(inputs, path, encoder=encoder, progress=progress, notes=notes),
                f"Exported {os.path.basename(path)}",
            )

    def _export_options(self, progress):
        return {
            "delay_frames": self.config.getint("wombo", "overlay_delay"),
            "encoder": resolve_encoder(self.config.get("wombo", "encoder")),
            "progress": progress,
        }

    def run_job(self, label, work, done_message=None):
        """Runs work(progress_callback) on the job thread and reports progress in the status bar."""

        def task():
            self.job_label, self.job_progress = label, None
            try:
                work(lambda fraction: setattr(self, "job_progress", fraction))
                if done_message:
                    self.flash(done_message, "8fd18f")
            except Exception as e:
                logger.exception("%s failed", label)
                self.flash(f"{label} failed: {e}", "ff6b6b", 10)
            finally:
                self.job_label, self.job_progress = None, None

        self.jobs.submit(task)

    # ---- View ----------------------------------------------------------------------------------

    def get_opacity(self):
        return self.config.getfloat("wombo", "opacity")

    def set_opacity(self, opacity):
        Window.opacity = opacity
        self.config.set("wombo", "opacity", round(opacity, 2))

    def preview_opacity(self, active):
        # The window is only see-through in overlay mode; the slider previews it while adjusting.
        Window.opacity = self.get_opacity() if active or self.topmost else 1

    def toggle_overlay(self):
        self.topmost = not self.topmost
        hwnd = Window.get_window_info().window
        if self.topmost:
            # Windows' own record of where the window was (maximized or not), to put it back exactly.
            self._normal_placement = win32gui.GetWindowPlacement(hwnd)
            left, top = win32gui.ClientToScreen(hwnd, (0, 0))
            _, _, width, height = win32gui.GetClientRect(hwnd)
            # The overlay sits where the window's content was, at the same width; _fit_overlay (every
            # frame) trims its height and puts it back there if the style change nudged it. Set before
            # anything below, which can run frames from inside Windows' message handling.
            self._overlay_origin = (left, top, width)
            self._overlay_note_rows = 0
            if self._normal_placement[1] == win32con.SW_SHOWMAXIMIZED:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)  # A maximized window can't be resized.
            Window.borderless = True
            self.root_layout.remove_widget(self.menu_bar)
            self._place_window(left, top, width, height)
            Window.bind(on_draw=self._keep_on_top)
        else:
            Window.unbind(on_draw=self._keep_on_top)
            Window.borderless = False
            self.root_layout.add_widget(self.menu_bar, index=len(self.root_layout.children))
            self._set_on_top(False)
            self._overlay_origin = None
            # Put back exactly where it was. Again shortly after, as the border comes back after a delay
            # and would otherwise grow the window by its own size.
            placement = self._normal_placement
            win32gui.SetWindowPlacement(hwnd, placement)
            Clock.schedule_once(lambda dt: self.topmost or win32gui.SetWindowPlacement(hwnd, placement), 0.15)
        self.preview_opacity(False)

    @staticmethod
    def _place_window(left, top, width, height):
        """Moves and sizes the window (in screen pixels) through Windows directly; Kivy follows along."""
        win32gui.SetWindowPos(Window.get_window_info().window, win32con.HWND_TOPMOST, left, top, width, height,
                              win32con.SWP_NOACTIVATE)

    def _fit_overlay(self):
        """Trims the overlay window to what the input list draws, so no empty space covers the game.
        It keeps its top edge and grows again when more is shown (e.g. another attempt row)."""
        if not getattr(self, "_overlay_origin", None):
            return  # Overlay mode is still being set up (or torn down).
        layout = self.input_list_layout
        # Room for as many rows of notes as have been needed so far: one to start with if there are
        # notes, more only if overlapping notes stack up. It doesn't shrink back, so the window
        # doesn't jump as notes scroll by.
        wanted = 1 if layout.show_notes and self.playalong_controller.notes else 0
        self._overlay_note_rows = max(getattr(self, "_overlay_note_rows", 0), wanted, layout.note_rows_used)
        if not layout.show_notes:
            self._overlay_note_rows = 0
        left, top, width = self._overlay_origin
        # Kivy measures in its own units; scale to pixels by the width, which doesn't change.
        pixels = width / Window.width if Window.width else 1
        height = round((layout.content_height(self._overlay_note_rows) + Window.height - layout.height) * pixels)
        actual = win32gui.GetWindowRect(Window.get_window_info().window)
        if max(abs(a - b) for a, b in zip(actual, (left, top, left + width, top + height))) > 2:
            self._place_window(left, top, width, height)

    @staticmethod
    def _set_on_top(on_top):
        hwnd = Window.get_window_info().window  # The window's own handle; its title changes with the recording.
        flags = win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST if on_top else win32con.HWND_NOTOPMOST, 0, 0, 0, 0, flags)

    def _keep_on_top(self, *args):
        """Keeps overlay mode on top. Checked every frame, since changing the window (e.g. borderless) can
        drop it, but only reapplied when it has been dropped."""
        hwnd = Window.get_window_info().window
        if not win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) & win32con.WS_EX_TOPMOST:
            self._set_on_top(True)

    def show_display(self, mode):
        display = self.input_list_layout if mode == "list" else self.playalong_layout
        if self.display:
            self.root_layout.remove_widget(self.display)
        self.root_layout.add_widget(display)  # Added last, so it sits below the menu bar.
        self.display = display
        self.config.set("wombo", "input_display", mode)
        self.menu_bar.set_display_mode(mode)

    def default_game(self):
        game = self.config.get("wombo", "default_game")
        return game if game in GAMES else None

    def set_game(self, game, action_layout=None, mark_edited=True):
        """The recording's game and action layout (None for the game's usual one)."""
        self.playalong_controller.set_game(game, action_layout)
        self.input_list_layout.textures.buttons.game = game
        if mark_edited:
            self.unsaved_edits = True

    def set_actions_visible(self, visible):
        self.playalong_controller.show_actions = visible
        self.config.set("wombo", "show_actions", int(visible))
        self.menu_bar.set_actions_visible(visible)

    def toggle_actions(self):
        self.set_actions_visible(not self.playalong_controller.show_actions)
        if self.playalong_controller.show_actions and not self.playalong_controller.game:
            self.flash("This recording has no game: choose one in Edit > Game actions...", "ffb454", 6)

    def edit_game_actions(self):
        controller = self.playalong_controller
        if controller.is_recording() or not controller.input_track:
            self.flash("Open a recording to set its game actions", "ffb454")
            return
        track = controller.get_input_track()
        used = {button: sum(1 for i, frame in enumerate(track) if frame[button] and (i == 0 or not track[i - 1][button]))
                for button in LIST_BUTTON_ORDER}
        GameActionsPopup({key: game["name"] for key, game in GAMES.items()}, controller.game, controller.action_layout,
                         {key: list(game["actions"]) for key, game in GAMES.items()},
                         {key: game["default_layout"] for key, game in GAMES.items()}, used,
                         lambda game, layout: self.set_game(game, layout)).open()

    def set_notes_visible(self, visible):
        self.input_list_layout.show_notes = visible
        self.config.set("wombo", "show_notes", int(visible))
        self.menu_bar.set_notes_visible(visible)

    def set_lanes_shown(self, shown):
        self.input_list_layout.lanes_shown = shown
        self.config.set("wombo", "lanes", ",".join(name for name in LANES if name in shown))
        self.menu_bar.set_lanes_shown(shown)

    def toggle_lane(self, name):
        self.set_lanes_shown(self.input_list_layout.lanes_shown ^ {name})
        if self.display is not self.input_list_layout:
            self.show_display("list")  # Lanes are part of the input list.

    def toggle_notes(self):
        self.set_notes_visible(not self.input_list_layout.show_notes)

    def toggle_display(self):
        self.show_display("ring" if self.display is self.input_list_layout else "list")

    def show_help(self):
        steps = [
            "Open a recording with [b]Ctrl+O[/b] (or drop its .json / .mp4 on the window), or record one with "
            "[b]F8[/b] and save it with [b]F12[/b].",
            "Press [b]Space[/b] or [b]Start[/b] and play along: press each input as it reaches the line. No "
            "controller? [b]WASD[/b] + [b]U I O[/b] / [b]J K L[/b].",
            "Mark what matters: select frames (drag in the frame meter) and press [b]K[/b]. Runs are graded "
            "below your attempt.",
            "Look back: scroll or drag the list, [b]S[/b] saves an attempt, [b]A[/b] lists and replays attempts.",
        ]
        in_game = [(key, description) for key, description, _ in HOTKEYS]
        in_window = [
            ("Space", "Play / pause"),
            ("Home", "Restart (a fresh attempt while practising)"),
            ("Ctrl+O", "Open a recording"),
            ("Ctrl+S", "Save changes to the recording"),
            ("N", "Add a note to the selection"),
            ("K", "Mark the selection as a key input"),
            ("S", "Save the attempt with the recording"),
            ("A", "Attempts: rename, show, replay, delete"),
            ("Esc", "Clear the selection"),
        ]
        in_window = [("Start / Back", "On the controller: play or pause / start over")] + in_window
        mouse = [
            ("Wheel / drag", "Move through the list, a frame per notch"),
            ("Ctrl+Wheel", "Zoom in and out"),
            ("Click", "Select a frame (Shift+click extends)"),
            ("Drag Frames", "Select a range (in the frame meter)"),
            ("Right-click", "Menu for the selection"),
            ("Click a tag", "Edit a note or key input"),
        ]
        colours = [
            ("Green", "Hit (or a frame that matched)"),
            ("Blue / orange", "Early / late, with frames off"),
            ("Red", "Missed"),
            ("Grey", "Not reached yet"),
        ]
        columns = [[("In game (these work while the game has focus)", in_game)],
                   [("In this window", in_window), ("Mouse", mouse), ("Attempt colours", colours)]]
        HelpPopup(steps, columns, self.open_user_guide).open()

    def open_user_guide(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "USER_GUIDE.md")
        try:
            os.startfile(path)
        except OSError as e:
            self.flash(f"Couldn't open the user guide ({path}): {e}", "ff6b6b", 8)

    def open_settings_popup(self):
        readers = self.select_controller()

        def setter(key, apply=None):
            def on_change(value):
                self.config.set("wombo", key, int(value) if isinstance(value, bool) else value)
                self.config.write()
                if apply:
                    apply()
            return on_change

        displays = list_displays() or [(0, "")]
        rows = [
            ("Controller", [("First connected", "auto")] + [(r.name, r.name) for r in readers],
             self.config.get("wombo", "controller"), setter("controller", self.select_controller)),
            ("Record video", bool, self.config.getboolean("wombo", "capture_video"), setter("capture_video")),
            ("Capture display", [(f"Display {i + 1}  {size}", str(i)) for i, size in displays],
             self.config.get("wombo", "display"), setter("display")),
            ("Video size", [(label, str(h)) for label, h in VIDEO_HEIGHTS],
             self.config.get("wombo", "video_height"), setter("video_height")),
            ("Encoder", ENCODERS, self.config.get("wombo", "encoder"), setter("encoder")),
            ("Overlay input delay", [(f"{n} frames", str(n)) for n in range(13)],
             self.config.get("wombo", "overlay_delay"), setter("overlay_delay")),
            ("Export overlay on save", bool, self.config.getboolean("wombo", "export_overlay_on_save"),
             setter("export_overlay_on_save")),
            ("Lead-in before practice", [("Off", "0"), ("0.5 s", "30"), ("1 s", "60"), ("2 s", "120")],
             self.config.get("wombo", "lead_in"),
             setter("lead_in", lambda: setattr(self.playalong_controller, "lead_in",
                                               self.config.getint("wombo", "lead_in")))),
            ("Demo countdown", [("1 s", "60"), ("2 s", "120"), ("3 s", "180"), ("5 s", "300")],
             self.config.get("wombo", "demo_countdown"), setter("demo_countdown")),
            ("Game for new recordings", [("None", "")] + [(game["name"], key) for key, game in GAMES.items()],
             self.config.get("wombo", "default_game"), setter("default_game")),
            ("Recent attempts shown", [(str(n), str(n)) for n in (0, 1, 2, 3, 5, 8, 10, 15, 20)],
             self.config.get("wombo", "recent_attempts"),
             setter("recent_attempts", lambda: self.playalong_controller.set_history_count(
                 self.config.getint("wombo", "recent_attempts")))),
        ]
        SettingsPopup(rows).open()


if __name__ == "__main__":
    # Kivy owns the root logger, so module logs (including late sampler ticks) go to ~/.kivy/logs.
    WomboComboApp().run()
