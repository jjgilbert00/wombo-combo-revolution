import json
import os
import shutil
import tempfile

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
import logging
from KivyOnTop import register_topmost, unregister_topmost
import tkinter as tk
from tkinter import filedialog
import threading

logger = logging.getLogger(__name__)
TITLE = "Wombo Combo"

TEST_INPUTS = get_cool_controller_pattern()

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
        self.finishing = None  # Thread finishing the last take's video file.

    def on_start(self, *args):
        Window.set_title(TITLE)

        # Global keyboard listener for when the window isn't selected.
        self.listener = keyboard.Listener(on_press=self.on_key_press)
        self.listener.start()
        self.select_controller()
        self.sampler.start()
        Clock.schedule_interval(self.refresh, 0)  # Every rendered frame; input timing no longer depends on it.
        Clock.schedule_interval(self.check_controller, 1.0)
        # Creating the capture device takes ~100 ms; do it now rather than when recording starts.
        prepare_capture(CAPTURE_DISPLAY)

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
        if self.finishing:
            self.finishing.join()
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
            self.capture_path = recorder.output_path
            # Encoding may still be catching up; let it finish without blocking.
            self.finishing = threading.Thread(target=recorder.finish, daemon=True)
            self.finishing.start()

    def on_key_press(self, key):
        if key == keyboard.Key.f2:
            if self.topmost:
                unregister_topmost(Window, TITLE)
                Window.borderless = False
            else:
                register_topmost(Window, TITLE)
                Window.borderless = True
            self.topmost = not self.topmost
        elif key == keyboard.Key.f5:
            self.playalong_controller.set_frame(0)
        elif key == keyboard.Key.f6:
            self.playalong_controller.play()
        elif key == keyboard.Key.f7:
            self.playalong_controller.pause()
        elif key == keyboard.Key.f8:
            if self.playalong_controller.is_recording():
                self.stop_recording()
            elif not self.playalong_controller.is_playing():
                self.start_recording()
        elif key == keyboard.Key.f9:
            self.playalong_controller.clean_track()
        elif key == keyboard.Key.f10:
            if self.playalong_controller.is_recording():
                self.stop_recording()
            self.playalong_controller.clear_track()
            self.capture_path = None
        elif key == keyboard.Key.f11:
            self.show_file_loader()
        elif key == keyboard.Key.f12:
            self.show_file_saver()
        elif key == keyboard.KeyCode.from_char("="):
            Window.opacity = min(Window.opacity + 0.1, 1)
        elif key == keyboard.KeyCode.from_char("-"):
            Window.opacity = max(Window.opacity - 0.1, 0)

    def show_file_saver(self):
        root = tk.Tk()
        root.withdraw()  # Hide the root window
        file_path = filedialog.asksaveasfilename(
            defaultextension=".mp4",
            filetypes=[("Video files", "*.mp4"), ("All files", "*.*")],
        )
        if file_path:
            if self.playalong_controller.is_recording():
                self.stop_recording()
            base = os.path.splitext(file_path)[0]
            inputs = self.playalong_controller.get_input_track()
            encoder = resolve_encoder(ENCODER)
            with open(base + ".json", "w") as fout:
                json.dump({"fps": FPS, "inputs": inputs}, fout, indent=1, sort_keys=True)
            write_input_video(inputs, base + "_inputs.mp4", encoder=encoder)
            if self.capture_path:
                if self.finishing:
                    self.finishing.join()  # The take's video must be fully written before copying it.
                if os.path.abspath(self.capture_path) != os.path.abspath(base + ".mp4"):
                    shutil.copyfile(self.capture_path, base + ".mp4")
                write_capture_and_overlay(
                    self.capture_path, inputs, base + "_overlay.mp4", delay_frames=OVERLAY_DELAY_FRAMES, encoder=encoder
                )

    def show_file_loader(self):
        root = tk.Tk()
        root.withdraw()  # Hide the root window
        file_path = filedialog.askopenfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
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
