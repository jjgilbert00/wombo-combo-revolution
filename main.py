import os
import math
import random
from pynput import keyboard
from playalong import PlayalongController
os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
from kivy.app import App
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.config import Config
from kivy.core.window import Window
from controller import get_neutral_controller_state, ControllerRecorder, ControllerReader
from layouts.controller_layout import ControllerDisplay
from layouts.playalong_layout import PlayAlongLayout
import pygame
import mss
import cv2
import numpy as np
import queue
import logging
from KivyOnTop import register_topmost, unregister_topmost

logger = logging.getLogger(__name__)
TITLE = "Wombo Combo"




def get_random_controller_state():
    return {
        "direction": math.floor(random.random() * 9) + 1,
        "A": round(0.51*random.random()),
        "B": round(0.51*random.random()),
        "X": round(0.51*random.random()),
        "Y": round(0.51*random.random()),
        "RT": round(0.51*random.random()),
        "RB": round(0.51*random.random()),
        "LT": round(0.51*random.random()),
        "LB": round(0.51*random.random())
    }

circles = [1,2,3,6,9,8,7,4]
TEST_INPUTS = [get_random_controller_state() for _ in range(60*3)]
for i, input in enumerate(TEST_INPUTS[0:len(TEST_INPUTS)//2]):
    if i % 10 != 1:
        input["direction"] = TEST_INPUTS[i-1]["direction"]
        continue
    curdir = circles.pop()
    circles.insert(0, curdir)
    input["direction"] = curdir

for i, input in enumerate(TEST_INPUTS[len(TEST_INPUTS)//2 :]):
    if i % 10 != 1:
        input["direction"] = TEST_INPUTS[len(TEST_INPUTS)//2 + i-1]["direction"]
        continue
    curdir = circles.pop(0)
    circles.append(curdir)
    input["direction"] = curdir



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


    def on_stop(self):
        # Clean up when closing the app
        self.listener.stop()
        cv2.destroyAllWindows()
        pygame.quit()
    
    def on_key_press(self, key):
        if key == keyboard.Key.f10:
            self.playalong_controller.clear_track()
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
