from kivy.uix.boxlayout import BoxLayout
import logging

from widgets import ButtonImage, StickImage

logger = logging.getLogger(__name__)


class ControllerDisplay(BoxLayout):
    controller_reader = None
    running = False

    def __init__(self, controller_reader):
        super().__init__(orientation="horizontal", opacity=1)
        self.controller_reader = controller_reader

        self.button_displays = {
            "direction": StickImage(),
            "X": ButtonImage(),
            "Y": ButtonImage(),
            "A": ButtonImage(),
            "B": ButtonImage(),
            "LB": ButtonImage(),
            "RB": ButtonImage(),
            "LT": ButtonImage(),
            "RT": ButtonImage(),
        }
        self.add_widget(self.button_displays["direction"])

        layout = BoxLayout(orientation="vertical")
        layout.add_widget(self.button_displays["X"])
        layout.add_widget(self.button_displays["A"])
        self.add_widget(layout)

        layout = BoxLayout(orientation="vertical")
        layout.add_widget(self.button_displays["Y"])
        layout.add_widget(self.button_displays["B"])
        self.add_widget(layout)

        layout = BoxLayout(orientation="vertical")
        layout.add_widget(self.button_displays["RB"])
        layout.add_widget(self.button_displays["RT"])
        self.add_widget(layout)

        layout = BoxLayout(orientation="vertical")
        layout.add_widget(self.button_displays["LB"])
        layout.add_widget(self.button_displays["LT"])
        self.add_widget(layout)

    def update_display(self, dt):
        controller_state = self.controller_reader.get_controller_state()
        for button in controller_state:
            self.button_displays[button].update_state(controller_state[button])
        self.canvas.ask_update()
