import json
import os
import mss
import numpy as np
from pynput import keyboard
from input_video import write_video_file
from playalong import PlayalongController
from screen_capture import ScreenRecorder
os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.core.window import Window
from controller import get_cool_controller_pattern, ControllerReader
from layouts.controller_layout import ControllerDisplay
from layouts.playalong_layout import PlayAlongLayout
import pygame
import cv2
import logging
from KivyOnTop import register_topmost, unregister_topmost
import tkinter as tk
from tkinter import filedialog
import threading
import time
import queue
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)
TITLE = "Wombo Combo"

TEST_INPUTS = get_cool_controller_pattern()
NUM_CAPTURE_THREADS = 4


class WomboComboApp(App):
    def __init__(self):
        super().__init__()
        self.topmost = False
        self.controller_display = None
        self.controller_reader = None
        self.controller_recorder = None
        self.playalong_controller = None
        self.screen_recorder = ScreenRecorder()
        self.capture_queue = queue.Queue()
        self.executor = ThreadPoolExecutor(max_workers=NUM_CAPTURE_THREADS)
        self.capturing = False

    def on_start(self, *args):
        Window.set_title(TITLE)

        # Global keyboard listener for when the window isn't selected.
        self.listener = keyboard.Listener(on_press=self.on_key_press)
        self.listener.start()
        Clock.schedule_interval(lambda x: self.refresh(), 1.0 / 60.0)

    def build(self):
        # Set the window background color to transparent (RGBA)
        Window.clearcolor = (0.2, 0.2, 0.2, 0)
        Window.opacity= 0.5
        Window.size = (1920, 1080)
        Window.borderless = False
        Window.fullscreen = False

        # Bind keyboard events
        Window.bind(on_key_down=self.on_key_down)

        # Initialize game controller reader
        pygame.init()
        pygame.joystick.init()
        self.controller_reader = None
        if pygame.joystick.get_count() > 0:
            self.controller_reader = ControllerReader(
                pygame.joystick.Joystick(0)
            )
            self.controller_display = ControllerDisplay(self.controller_reader)

        self.playalong_layout = PlayAlongLayout()
        self.playalong_controller = PlayalongController(controller_reader=self.controller_reader, view=self.playalong_layout, input_track=TEST_INPUTS)
        self.playalong_controller.set_looping(True)

        layout = BoxLayout(orientation="vertical")
        layout.add_widget(self.playalong_layout)

        return layout

    def refresh(self):
        self.playalong_controller.refresh()
        if self.playalong_controller.is_recording():
            self.capture_queue.put(self.screen_recorder.capture_screen)

    def start_capture(self):
        self.capturing = True
        for _ in range(NUM_CAPTURE_THREADS):
            self.executor.submit(self.capture_loop)

    def stop_capture(self):
        self.capturing = False
        self.executor.shutdown(wait=True)
        self.executor = ThreadPoolExecutor(max_workers=NUM_CAPTURE_THREADS)

    def capture_loop(self):
        while self.capturing:
            try:
                capture_func = self.capture_queue.get(timeout=1)
                capture_func()
                self.capture_queue.task_done()
            except queue.Empty:
                continue

    def on_stop(self):
        # Clean up when closing the app
        self.listener.stop()
        self.stop_capture()
        cv2.destroyAllWindows()
        pygame.quit()
    
    def on_key_press(self, key):
        if key == keyboard.Key.f2:
            if self.topmost:
                unregister_topmost(Window, TITLE)
            else:
                register_topmost(Window, TITLE)
            self.topmost = not self.topmost
        if key == keyboard.Key.f5:
            self.playalong_controller.set_frame(0)
        if key == keyboard.Key.f6:
            self.playalong_controller.play()
        if key == keyboard.Key.f7:
            self.playalong_controller.pause()
        if key == keyboard.Key.f8:
            if self.playalong_controller.is_recording():
                self.playalong_controller.pause()
                self.stop_capture()
            elif not self.playalong_controller.is_playing():
                self.playalong_controller.start_recording()
                self.start_capture()
        if key == keyboard.Key.f9:
            self.playalong_controller.clean_track()
        if key == keyboard.Key.f10:
            self.playalong_controller.clear_track()
            self.screen_recorder.clear()
        if key == keyboard.Key.f11:
            self.show_file_loader()
        if key == keyboard.Key.f12:
            self.show_file_saver()

    def show_file_saver(self):
        root = tk.Tk()
        root.withdraw()  # Hide the root window
        file_path = filedialog.asksaveasfilename(defaultextension=".mp4", filetypes=[("Video files", "*.mp4"), ("All files", "*.*")])
        if file_path:
            self.screen_recorder.save_video(file_path, target_frames=len(self.playalong_controller.get_input_track()))
            write_video_file(self.playalong_controller.get_input_track(), file_path[0:-4] + '_inputs.mp4')
            with open(file_path[0:-4] + '.json', 'w') as fout:
                json.dump(self.playalong_controller.get_input_track(), fout)
            

    def show_file_loader(self):
        root = tk.Tk()
        root.withdraw()  # Hide the root window
        file_path = filedialog.askopenfilename(defaultextension=".json", filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if file_path:
            with open(file_path, 'r') as fin:
                loaded_data = json.load(fin)
                self.playalong_controller.set_input_track(loaded_data)

    def on_key_down(self, window, key, scancode, codepoint, modifier):
        if key == 61:  # Equals key
            Window.opacity = min(Window.opacity + 0.1, 1)
        elif key == 45:  # Minus key
            Window.opacity = max(Window.opacity - 0.1, 0)

if __name__ == "__main__":
    logging.basicConfig(filename="main.log", level=logging.DEBUG)
    WomboComboApp().run()
