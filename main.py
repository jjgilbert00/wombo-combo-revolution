import json
import os
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor

from timing import enable_high_resolution_timing, disable_high_resolution_timing

# Must happen before Kivy starts so its frame limiter gets 1 ms sleeps instead of 15.6 ms ones.
enable_high_resolution_timing()

from pynput import keyboard
from video_writer import resolve_encoder, write_capture_and_overlay, write_input_video
from playalong import PlayalongController
from sampler import FPS, InputSampler
from screen_capture import ScreenRecorder, prepare_capture

os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
from kivy.config import Config

# Waiting for vsync inside the buffer swap holds the GIL for up to a frame, which starves the input
# sampler thread. Kivy's own 60 fps limiter paces rendering instead (it sleeps without the GIL).
Config.set("graphics", "vsync", "0")

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.core.window import Window
from controller import find_controllers, get_cool_controller_pattern
from layouts.playalong_layout import PlayAlongLayout
import dialogs
import logging
from KivyOnTop import register_topmost, unregister_topmost

logger = logging.getLogger(__name__)
TITLE = "Wombo Combo"

TEST_INPUTS = get_cool_controller_pattern()

HOTKEYS = [
    ("F2", "Overlay mode (on top, borderless)", "toggle_overlay"),
    ("F5", "Restart playback", "restart_playback"),
    ("F6", "Play", "play"),
    ("F7", "Pause", "pause"),
    ("F8", "Start / stop recording", "toggle_recording"),
    ("F9", "Clean track (presses only)", "clean_track"),
    ("F10", "Clear track", "clear_track"),
    ("F11", "Open inputs", "open_track"),
    ("F12", "Save recording", "save_recording"),
]

CAPTURE_DISPLAY = 0
CAPTURE_MAX_HEIGHT = 1080  # Downscale larger displays; None records at native resolution.
ENCODER = "auto"  # NVENC when available, otherwise x264.
# Shifts inputs later in the overlay video to line up with what the game shows on screen.
OVERLAY_DELAY_FRAMES = 4


class WomboComboApp(App):
    def __init__(self):
        super().__init__()
        self.topmost = False
        # Owns the track and playhead; the sampler thread drives it once per 60 Hz frame.
        self.playalong_controller = PlayalongController(TEST_INPUTS)
        self.sampler = InputSampler(self.playalong_controller.tick)
        self.screen_recorder = None
        self.capture_path = None  # Video that belongs to the current input track, if any.
        self.temp_dir = tempfile.mkdtemp(prefix="wombo_")
        self.take = 0
        self.jobs = ThreadPoolExecutor(max_workers=1)  # Saves/exports run one at a time, off the UI thread.
        self.job_label = None
        self.job_progress = None

    def on_start(self, *args):
        Window.set_title(TITLE)

        self.select_controller()
        self.sampler.start()
        Clock.schedule_interval(self.refresh, 0)  # Every rendered frame; input timing no longer depends on it.
        Clock.schedule_interval(self.check_controller, 1.0)
        # Creating the capture device takes ~100 ms; do it now rather than when recording starts.
        prepare_capture(CAPTURE_DISPLAY)

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

    def build(self):
        # Set the window background color to fully transparent (RGBA)
        Window.clearcolor = (0.2, 0.2, 0.2, 0.5)
        Window.opacity = 0.5  # Ensure the window itself is fully opaque
        Window.size = (1920, 1080)
        Window.borderless = False
        Window.fullscreen = False

        self.playalong_layout = PlayAlongLayout()
        self.playalong_controller.set_looping(True)

        layout = BoxLayout(orientation="vertical")
        layout.add_widget(self.playalong_layout)

        return layout

    def refresh(self, dt):
        # Draw whatever the sampler thread last recorded; rendering never advances the playhead.
        controller_state, upcoming_frames = self.playalong_controller.snapshot()
        self.playalong_layout.update_state(controller_state, upcoming_frames)

    def select_controller(self):
        # Prefers an XInput controller; falls back to pygame for anything else.
        readers = find_controllers()
        self.sampler.reader = readers[0] if readers else None

    def check_controller(self, dt):
        # Picks up a controller that was plugged in (or back in) after startup.
        reader = self.sampler.reader
        if reader is None or not reader.connected:
            self.select_controller()

    def on_stop(self):
        # Clean up when closing the app
        self.listener.stop()
        if self.playalong_controller.is_recording():
            self.stop_recording()
        self.sampler.stop()
        self.jobs.shutdown(wait=True, cancel_futures=True)
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        disable_high_resolution_timing()

    def start_recording(self):
        self.playalong_controller.pause()
        self.capture_path = None
        self.take += 1
        self.screen_recorder = ScreenRecorder(
            output_idx=CAPTURE_DISPLAY, max_height=CAPTURE_MAX_HEIGHT, encoder=resolve_encoder(ENCODER)
        )
        frame_sink = None
        try:
            self.screen_recorder.start(os.path.join(self.temp_dir, f"take_{self.take}.mp4"))
            frame_sink = self.screen_recorder.capture
        except Exception:
            logger.exception("Couldn't start video capture; recording inputs only")
            self.screen_recorder = None
        # The sampler calls frame_sink right after each recorded input, so video frame i matches input i.
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

    # ---- Hotkey actions ------------------------------------------------------------------------

    def play(self):
        if not self.playalong_controller.is_recording():
            self.playalong_controller.play()

    def pause(self):
        if not self.playalong_controller.is_recording():
            self.playalong_controller.pause()

    def restart_playback(self):
        self.playalong_controller.set_frame(0)

    def toggle_recording(self):
        if self.playalong_controller.is_recording():
            self.stop_recording()
        else:
            self.start_recording()

    def clean_track(self):
        if not self.playalong_controller.is_recording():
            self.playalong_controller.clean_track()

    def clear_track(self):
        if self.playalong_controller.is_recording():
            self.stop_recording()
        self.playalong_controller.clear_track()
        self.capture_path = None

    def toggle_overlay(self):
        self.topmost = not self.topmost
        if self.topmost:
            register_topmost(Window, TITLE)
            Window.borderless = True
        else:
            unregister_topmost(Window, TITLE)
            Window.borderless = False

    def save_recording(self):
        file_path = dialogs.save_file("Save recording", "Recordings (*.mp4)", "*.mp4", "mp4")
        if file_path:
            if self.playalong_controller.is_recording():
                self.stop_recording()
            base = os.path.splitext(file_path)[0]
            inputs = self.playalong_controller.get_input_track()
            capture = self.capture_path  # Read now; a new take started before the job runs would reset it.
            encoder = resolve_encoder(ENCODER)

            def save(progress):
                with open(base + ".json", "w") as fout:
                    json.dump({"fps": FPS, "inputs": inputs}, fout, indent=1, sort_keys=True)
                write_input_video(inputs, base + "_inputs.mp4", encoder=encoder)
                if not capture:
                    return
                if os.path.abspath(capture) != os.path.abspath(base + ".mp4"):
                    shutil.copyfile(capture, base + ".mp4")
                self.job_label = "Exporting overlay"
                write_capture_and_overlay(
                    capture, inputs, base + "_overlay.mp4", delay_frames=OVERLAY_DELAY_FRAMES, encoder=encoder,
                    progress=progress,
                )

            self.run_job("Saving", save)

    def run_job(self, label, work):
        """Runs work(progress_callback) on the job thread; job_label/job_progress describe what's running."""

        def task():
            self.job_label, self.job_progress = label, None
            try:
                work(lambda fraction: setattr(self, "job_progress", fraction))
                logger.info("%s finished", label)
            except Exception:
                logger.exception("%s failed", label)
            finally:
                self.job_label, self.job_progress = None, None

        self.jobs.submit(task)

    def open_track(self):
        file_path = dialogs.open_file("Open inputs", "Input tracks (*.json)", "*.json")
        if file_path:
            with open(file_path, "r") as fin:
                data = json.load(fin)
            # Older saves are a bare list of frames.
            self.playalong_controller.set_input_track(data["inputs"] if isinstance(data, dict) else data)
            # A video saved alongside the inputs can be used for overlay exports.
            video = os.path.splitext(file_path)[0] + ".mp4"
            self.capture_path = video if os.path.exists(video) else None


if __name__ == "__main__":
    logging.basicConfig(filename="main.log", level=logging.DEBUG)
    WomboComboApp().run()
