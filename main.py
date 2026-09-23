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
from kivy.uix.boxlayout import BoxLayout
from KivyOnTop import register_topmost, unregister_topmost
from pynput import keyboard

import dialogs
from controller import find_controllers, get_cool_controller_pattern
from layouts.input_list_layout import InputListLayout
from layouts.menu_layout import HelpPopup, MenuBar, SettingsPopup
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
        self.temp_dir = tempfile.mkdtemp(prefix="wombo_")
        self.take = 0
        self.jobs = ThreadPoolExecutor(max_workers=1)  # Saves/exports run one at a time, off the UI thread.
        self.job_label = None
        self.job_progress = None
        self.message = None  # (markup text, expiry time)

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
            "input_display": "ring",
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
        self.menu_bar = MenuBar(self)
        self.root_layout = BoxLayout(orientation="vertical")
        self.root_layout.add_widget(self.menu_bar)
        self.display = None
        self.show_display(self.config.get("wombo", "input_display"))
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
        actions = {getattr(keyboard.Key, key.lower()): action for key, _, action in HOTKEYS}

        def on_press(key):
            # Must not return False: that stops the listener.
            action = actions.get(key)
            if action:
                Clock.schedule_once(lambda dt: getattr(self, action)())

        self.listener = keyboard.Listener(on_press=on_press)
        self.listener.start()

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
            rows_before, rows_after = self.input_list_layout.rows_needed()
            self.input_list_layout.update_state(*self.playalong_controller.list_snapshot(rows_before, rows_after))
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
            state = "PLAY" if controller.is_playing() else "PAUSED"
            parts.append(f"{state} {format_time(controller.get_current_frame())} / {format_time(frames)}")
        else:
            parts.append("No track")
        if self.job_label:
            progress = f" {int(self.job_progress * 100)}%" if self.job_progress is not None else "..."
            parts.append(f"{self.job_label}{progress}")
        if self.message and time.time() < self.message[1]:
            parts.append(self.message[0])
        reader = self.sampler.reader
        parts.append(reader.name if reader and reader.connected else "[color=ffb454]No controller[/color]")
        parts.append(f"{stats.rate:.1f} Hz")
        self.menu_bar.update(controller.is_recording(), controller.is_playing(), controller.loop, "   |   ".join(parts))

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
        self.playalong_controller.set_frame(0)

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
        self.capture_path = None

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
        # Older saves are a bare list of frames.
        self.playalong_controller.set_input_track(data["inputs"] if isinstance(data, dict) else data)
        video = os.path.splitext(path)[0] + ".mp4"
        self.capture_path = video if os.path.exists(video) else None
        self.flash(f"Opened {os.path.basename(path)}")

    def save_recording(self):
        if self.playalong_controller.is_recording():
            self.stop_recording()
        inputs = self.playalong_controller.get_input_track()
        if not inputs:
            self.flash("Nothing to save", "ffb454")
            return
        path = dialogs.save_file("Save recording", "Recordings (*.mp4)", "*.mp4", "mp4")
        if not path:
            return
        base = os.path.splitext(path)[0]
        export_overlay = self.config.getboolean("wombo", "export_overlay_on_save")
        capture = self.capture_path  # Read now; a new take started before the job runs would reset it.

        def save(progress):
            with open(base + ".json", "w") as fout:
                json.dump({"fps": FPS, "inputs": inputs}, fout, indent=1, sort_keys=True)
            if not capture:
                return
            if os.path.abspath(capture) != os.path.abspath(base + ".mp4"):
                shutil.copyfile(capture, base + ".mp4")
            if export_overlay:
                self.job_label = "Exporting overlay"
                write_capture_and_overlay(capture, inputs, base + "_overlay.mp4", **self._export_options(progress))

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
            capture = self.capture_path
            self.run_job(
                "Exporting overlay",
                lambda progress: write_capture_and_overlay(capture, inputs, path, **self._export_options(progress)),
                f"Exported {os.path.basename(path)}",
            )

    def export_input_video(self):
        inputs = self.playalong_controller.get_input_track()
        if not inputs:
            self.flash("Nothing to export", "ffb454")
            return
        path = dialogs.save_file("Export input video", "Videos (*.mp4)", "*.mp4", "mp4")
        if path:
            encoder = resolve_encoder(self.config.get("wombo", "encoder"))
            self.run_job(
                "Exporting inputs",
                lambda progress: write_input_video(inputs, path, encoder=encoder, progress=progress),
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

    def toggle_display(self):
        self.show_display("ring" if self.display is self.input_list_layout else "list")

    def show_help(self):
        HelpPopup([(key, description) for key, description, _ in HOTKEYS]).open()

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
        ]
        SettingsPopup(rows).open()


if __name__ == "__main__":
    # Kivy owns the root logger, so module logs (including late sampler ticks) go to ~/.kivy/logs.
    WomboComboApp().run()
