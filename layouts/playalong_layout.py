from kivy.app import App
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.widget import Widget
from kivy.graphics import Rectangle, Color

from controller import ControllerReader
from widgets import ButtonImage, ButtonPromptWidget, StickImage, DraggableWidget, DirectionalPromptWidget



# Draws the user-controlled joystick as well as the input prompts.
class JoystickLayout(RelativeLayout):
    stick_image = None
    directional_prompt_widget = [] # For now, this is a list of integers. Maybe later we can make it smaller.
    def __init__(self, **kwargs):
        super(JoystickLayout, self).__init__(**kwargs)
        with self.canvas:
            self.directional_prompt_widget = DirectionalPromptWidget(pos_hint={"center_x": 0.5, "center_y": 0.5}, size=self.size)
            self.add_widget(self.directional_prompt_widget)
            self.stick_image = StickImage(pos_hint={"center_x": 0.5, "center_y": 0.5}, size_hint=(0.25, 0.25))
            self.add_widget(self.stick_image)

    def update_state(self, direction, ):
        self.stick_image.update_state(direction)


class ColumnLayout(RelativeLayout):
    border = None
    button_prompt_widget = None

    def __init__(self, **kwargs):
        super(ColumnLayout, self).__init__(**kwargs)
        with self.canvas:
            Color(0,0,1,0.25)
            self.border = Rectangle(pos=self.pos, size=self.size)
            self.button_prompt_widget = ButtonPromptWidget(pos_hint={"center_x": 0.5, "center_y": 0.5}, size=self.size)
            self.add_widget(self.button_prompt_widget)

    def update_state(self, state):
        self.button_prompt_widget.update_state(state)

class PlayAlongLayout(RelativeLayout):
    def __init__(self, controller_reader: ControllerReader, **kwargs):
        super().__init__(**kwargs)
        self.controller_reader = controller_reader
        self.button_displays = {
            "direction": JoystickLayout(size_hint=(0.5, None), height=self.width * 0.5, pos_hint={'center_x': 0.25, 'bottom': 0})
        }
        button_names = ["A", "X", "B", "Y", "RT", "RB", "LT", "LB"]
        for i in range(len(button_names)):
            self.button_displays[button_names[i]] = ColumnLayout(size_hint=(0.1, 1), pos_hint={'x': 0.5 + i * (0.4/8), 'y': 0 if i%2==0 else 0.1})
        [self.add_widget(self.button_displays[button]) for button in self.button_displays]
        self.bind(size=self.update_joystick_layout_size)
        self.update_controller_display()

    def update_joystick_layout_size(self, *args):
        self.button_displays['direction'].height = self.width * 0.5
    
    def update_controller_display(self):
        controller_state = self.controller_reader.get_controller_state()
        for button in controller_state:
            self.button_displays[button].update_state(controller_state[button])
        
    
    