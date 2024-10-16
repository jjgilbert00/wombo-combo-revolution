import os
os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
from kivy.app import App
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.config import Config
from kivy.clock import Clock
from kivy.core.window import Window
from controller import ControllerRecorder, ControllerReader
from layouts.controller_layout import ControllerDisplay
from layouts.playalong_layout import PlayAlongLayout
import pygame
import mss
import cv2
import numpy as np
import queue
import logging
import threading
from KivyOnTop import register_topmost, unregister_topmost

logger = logging.getLogger(__name__)
TITLE = "Wombo Combo"

class WomboComboApp(App):
    def __init__(self):
        super().__init__()
        self.controller_display = None
        self.controller_reader = None
        self.controller_recorder = None

    def on_start(self, *args):
        Window.set_title(TITLE)
        register_topmost(Window, TITLE)

    def build(self):
        # Set the window background color to transparent (RGBA)
        Window.clearcolor = (0.2, 0.2, 0.2, 0)
        Window.opacity= 0.5
        Window.size = (1000, 1000)
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
            Clock.schedule_interval(self.refresh, 1.0/60.0)

        self.playalong_layout = PlayAlongLayout(self.controller_reader)

        layout = BoxLayout(orientation="vertical")
        layout.add_widget(self.playalong_layout)
        # layout.add_widget(self.controller_display)
        return layout

    def refresh(self, dt):
        self.controller_reader.update_state()
        self.controller_display.update_display()
        self.playalong_layout.update_controller_display()

    def on_stop(self):
        # Clean up when closing the app
        cv2.destroyAllWindows()
        pygame.quit()
    
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
