import json
import logging
import os
import shutil
import tempfile
import threading
import time
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
from KivyOnTop import register_topmost, unregister_topmost
from pynput import keyboard

import dialogs
from controller import find_controllers, get_cool_controller_pattern
from input_list import LIST_BUTTON_ORDER
from key_inputs import derive, derive_hold, describe, normalized
from layouts.input_list_layout import LANES, InputListLayout
from layouts.menu_layout import AttemptsPopup, HelpPopup, KeyInputPopup, MenuBar, NotePopup, SettingsPopup
from layouts.playalong_layout import PlayAlongLayout
from playalong import PlayalongController
from sampler import FPS, InputSampler
from screen_capture import ScreenRecorder, list_displays, prepare_capture
from video_writer import nvenc_available, resolve_encoder, write_capture_and_overlay, write_input_video

logger = logging.getLogger(__name__)
TITLE = "Wombo Combo"

TEST_INPUTS = get_cool_controller_pattern()

HOTKEYS = [
    ("F1", "Show hotkeys", "show_help"),
    ("F2", "Overlay mode (on top, borderless)", "toggle_overlay"),
    ("F3", "Switch between ring and input list", "toggle_display"),
    ("Shift+F3", "Show / hide notes", "toggle_notes"),
    ("F4", "Practice on/off (record your attempt while playing)", "toggle_practice"),
    ("F5", "Restart playback", "restart_playback"),
    ("F6", "Play", "play"),
    ("F7", "Pause", "pause"),
    ("F8", "Start / stop recording", "toggle_recording"),
    ("F9", "Clean track (presses only)", "clean_track"),
    ("F10", "Clear track", "clear_track"),
    ("F11", "Open inputs", "open_track"),
    ("F12", "Save recording", "save_recording"),
]

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
        self.playalong_controller = PlayalongController(TEST_INPUTS)
        self.sampler = InputSampler(self.playalong_controller.tick)
        self.screen_recorder = None
        self.capture_path = None  # Video that belongs to the current input track, if any.
        self.track_path = None  # The current track's .json file, once it's been opened or saved.
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
            "input_display": "ring",
            "show_notes": 1,
            "lanes": ",".join(LANES),  # Input list lanes shown.
            "recent_attempts": 5,  # Recent runs shown in the input list.
        })

    def get_application_config(self):
        return super().get_application_config(os.path.join(self.user_data_dir, "%(appname)s.ini"))

    def open_settings(self, *args):
        return False  # Disable Kivy's built-in F1 settings panel; F1 shows hotkeys instead.

    def build(self):
        Window.clearcolor = (0.2, 0.2, 0.2, 0.5)
        Window.size = (1920, 1080)
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
        self.playalong_controller.set_practice(self.config.getboolean("wombo", "practice"))
        self.playalong_controller.set_history_count(self.config.getint("wombo", "recent_attempts"))
        self.menu_bar = MenuBar(self)
        self.root_layout = BoxLayout(orientation="vertical")
        self.root_layout.add_widget(self.menu_bar)
        self.display = None
        self.show_display(self.config.get("wombo", "input_display"))
        self.set_notes_visible(self.config.getboolean("wombo", "show_notes"))
        self.set_lanes_shown(set(filter(None, self.config.get("wombo", "lanes").split(","))))
        return self.root_layout

    def on_start(self):
        self.select_controller()
        self.sampler.start()
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

    def on_key_down(self, window, key, scancode, codepoint, modifiers):
        """Shortcuts that only apply while the app window is focused."""
        if any(isinstance(child, ModalView) for child in Window.children):
            return False  # A popup is open; let it have the keys.
        if key == 27:  # Esc
            self.set_selection(None)
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

    def update_status(self, dt):
        controller = self.playalong_controller
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
            if controller.is_playing():
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
                             "   |   ".join(parts))

    # ---- Transport -----------------------------------------------------------------------------

    def play(self):
        if not self.playalong_controller.is_recording():
            self.playalong_controller.play()

    def pause(self):
        if not self.playalong_controller.is_recording():
            self.playalong_controller.pause()

    def toggle_playback(self):
        self.pause() if self.playalong_controller.is_playing() else self.play()

    def restart_playback(self):
        self.playalong_controller.restart()

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

        delete = (lambda: self.playalong_controller.remove_note(index)) if index is not None else None
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

        def save(edited):
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
            self.flash(f"Key input {describe(edited)} on frames {edited['start']}-{edited['end']}")

        delete = (lambda: controller.remove_key_input(index)) if index is not None else None
        title = "Mark key input" if index is None else "Edit key input"
        track = controller.get_input_track()
        KeyInputPopup(title, normalized(key_input), len(track) - 1, LIST_BUTTON_ORDER, describe,
                      lambda edited: derive_hold(track, edited["start"], edited["end"]), save, delete).open()

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
        self.track_path = None
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
            self.flash("Track cleaned")

    def clear_track(self):
        if self.playalong_controller.is_recording():
            self.stop_recording()
        self.playalong_controller.clear_track()
        self.set_selection(None)
        self.capture_path = None
        self.track_path = None

    def open_track(self):
        path = dialogs.open_file("Open inputs", "Input tracks (*.json)", "*.json")
        if not path:
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
                                                      data.get("key_inputs"), data.get("saved_attempts"))
        else:
            self.playalong_controller.set_input_track(data)  # Older saves are a bare list of frames.
        self.track_path = path
        video = os.path.splitext(path)[0] + ".mp4"
        self.capture_path = video if os.path.exists(video) else None
        self.flash(f"Opened {os.path.basename(path)}")
        self.set_selection(None)

    def save_recording(self):
        if self.playalong_controller.is_recording():
            self.stop_recording()
        inputs = self.playalong_controller.get_input_track()
        attempt = self.playalong_controller.get_attempt_track()
        notes = self.playalong_controller.get_notes()
        key_inputs = self.playalong_controller.get_key_inputs()
        saved_attempts = self.playalong_controller.get_saved()
        if not inputs:
            self.flash("Nothing to save", "ffb454")
            return
        path = dialogs.save_file("Save recording", "Recordings (*.mp4)", "*.mp4", "mp4")
        if not path:
            return
        base = os.path.splitext(path)[0]
        export_overlay = self.config.getboolean("wombo", "export_overlay_on_save")
        self.track_path = base + ".json"  # Later saved attempts go straight into it.
        capture = self.capture_path  # Read now; a new take started before the job runs would reset it.

        def save(progress):
            with open(base + ".json", "w") as fout:
                data = {"fps": FPS, "inputs": inputs}
                if any(frame is not None for frame in attempt):
                    data["attempt"] = attempt
                if notes:
                    data["notes"] = notes
                if key_inputs:
                    data["key_inputs"] = key_inputs
                if saved_attempts:
                    data["saved_attempts"] = saved_attempts
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
        if self.topmost:
            register_topmost(Window, TITLE)
            Window.borderless = True
            self.root_layout.remove_widget(self.menu_bar)
        else:
            unregister_topmost(Window, TITLE)
            Window.borderless = False
            self.root_layout.add_widget(self.menu_bar, index=len(self.root_layout.children))
        self.preview_opacity(False)

    def show_display(self, mode):
        display = self.input_list_layout if mode == "list" else self.playalong_layout
        if self.display:
            self.root_layout.remove_widget(self.display)
        self.root_layout.add_widget(display)  # Added last, so it sits below the menu bar.
        self.display = display
        self.config.set("wombo", "input_display", mode)
        self.menu_bar.set_display_mode(mode)

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
        mouse_help = [
            ("Wheel", "Scrub the input list (pauses)"),
            ("Drag", "Scrub the input list"),
            ("Ctrl+Wheel", "Zoom the input list"),
            ("Click", "Select a frame (Shift+click extends)"),
            ("Frames drag", "Select a range of frames"),
            ("N", "Add a note to the selection (click a note to edit it)"),
            ("K", "Mark the selection as a key input (click its tag to edit)"),
            ("S", "Save the attempt (or the latest run) with the track"),
            ("A", "Attempts: rename, show, replay or delete saved and recent attempts"),
            ("Esc", "Clear the selection"),
            ("Attempts", "Green hit, blue early, orange late, red missed, grey not reached (+/- frames off)"),
        ]
        HelpPopup([(key, description) for key, description, _ in HOTKEYS] + mouse_help).open()

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
            ("Recent attempts shown", [(str(n), str(n)) for n in (0, 1, 2, 3, 5, 8, 10, 15, 20)],
             self.config.get("wombo", "recent_attempts"),
             setter("recent_attempts", lambda: self.playalong_controller.set_history_count(
                 self.config.getint("wombo", "recent_attempts")))),
        ]
        SettingsPopup(rows).open()


if __name__ == "__main__":
    # Kivy owns the root logger, so module logs (including late sampler ticks) go to ~/.kivy/logs.
    WomboComboApp().run()
