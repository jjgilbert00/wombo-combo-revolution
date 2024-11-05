import os
from pynput import keyboard
from generate_video import write_video_file
from playalong import PlayalongController
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

logger = logging.getLogger(__name__)
TITLE = "Wombo Combo"

TEST_INPUTS = get_cool_controller_pattern()
# TEST_INPUTS = [get_random_controller_state() for _ in range(60 * 2)] # 10 seconds of random inputs



class WomboComboApp(App):
    def __init__(self):
        super().__init__()
        self.controller_display = None
        self.controller_reader = None
        self.controller_recorder = None
        self.playalong_controller = None

    def on_start(self, *args):
        Window.set_title(TITLE)
        register_topmost(Window, TITLE)

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
        # layout.add_widget(self.controller_display)
        return layout


    def refresh(self):
        self.playalong_controller.refresh()


    def on_stop(self):
        # Clean up when closing the app
        self.listener.stop()
        cv2.destroyAllWindows()
        pygame.quit()
    
    def on_key_press(self, key):
        if key == keyboard.Key.f5:
            self.playalong_controller.set_frame(0)
        if key == keyboard.Key.f6:
            self.playalong_controller.play()
        if key == keyboard.Key.f7:
            self.playalong_controller.pause()
        if key == keyboard.Key.f8:
            if self.playalong_controller.is_recording():
                self.playalong_controller.pause()
            elif not self.playalong_controller.is_playing():
                self.playalong_controller.start_recording()
        if key == keyboard.Key.f9:
            self.playalong_controller.clean_track()
        if key == keyboard.Key.f10:
            self.playalong_controller.clear_track()
        if key == keyboard.Key.f11:
            self.show_file_chooser()

    def show_file_chooser(self):
        root = tk.Tk()
        root.withdraw()  # Hide the root window
        file_path = filedialog.asksaveasfilename(defaultextension=".mp4", filetypes=[("Video files", "*.mp4"), ("All files", "*.*")])
        if file_path:
            write_video_file(self.playalong_controller.get_input_track(), file_path)    

    def on_key_down(self, window, key, scancode, codepoint, modifier):
        if key == 61:  # Equals key
            Window.opacity = min(Window.opacity + 0.1, 1)
        elif key == 45:  # Minus key
            Window.opacity = max(Window.opacity - 0.1, 0)

    # def screen_record(self, dt):
    #     with mss.mss() as sct:
    #         monitor = sct.monitors[1]
    #         try:
    #             img = np.array(sct.grab(monitor))
    #         except Exception as e:
    #             print(e)
    #             return
    #         # Display captured image (as a placeholder, here you can save to file or process it)
    #         # For example, you could display it with OpenCV:
    #         cv2.imshow("Screen Capture", img)
    #         cv2.waitKey(1)


if __name__ == "__main__":
    logging.basicConfig(filename="main.log", level=logging.DEBUG)
    WomboComboApp().run()
