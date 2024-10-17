from kivy.app import App
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.widget import Widget
from kivy.graphics import Rectangle, Color
import math
import random
from controller import ControllerReader
from widgets import ButtonImage, StickImage, DraggableWidget, DirectionalPromptWidget
from images import IMAGE_SOURCE_BUTTON_UP, get_standard_button_icon

PLAYALONG_FRAMELENGTH = 120




def get_random_controller_state():
    return {
        "direction": math.floor(random.random() * 8) + 1,
        "A": round(random.random()),
        "B": round(random.random()),
        "X": round(random.random()),
        "Y": round(random.random()),
        "RT": round(random.random()),
        "RB": round(random.random()),
        "LT": round(random.random()),
        "LB": round(random.random()),
    }
TEST_INPUTS = [get_random_controller_state() for _ in range(60 * 10)] # 10 seconds of random inputs




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

    def update_state(self, direction, input_frames):
        self.stick_image.update_state(direction)


# Draws the user-controlled buttons as well as the input prompts.
class ButtonLayout(RelativeLayout):
    border = None
    button_source = None
    controller_button = None
    input_pool = []
    def __init__(self, button_source=IMAGE_SOURCE_BUTTON_UP, **kwargs):
        super(ButtonLayout, self).__init__(**kwargs)
        self.button_source = button_source
        with self.canvas:
            self.controller_button = ButtonImage(source=self.button_source, pos_hint={"center_x": 0.5, "bottom": 0}, size_hint=(1, None), opacity=0.3)
            self.add_widget(self.controller_button)

    
    def update_state(self, controller_state, input_frames):
        input_counter = 0
        reversed = input_frames.copy()
        reversed.reverse()

        for i, frame_state in enumerate(input_frames):
            if frame_state:
                if len(self.input_pool) <= input_counter:
                    self.input_pool.append(ButtonImage(source=self.button_source, size_hint=(1,None), opacity=0.8, pos_hint={"center_x": 0.5, "y": 1-i/len(input_frames)}))
                    self.add_widget(self.input_pool[-1])
                else:
                    self.input_pool[input_counter].pos_hint["y"] = 1-i/len(input_frames)
                    
                input_counter += 1


        self.controller_button.update_state(controller_state)

    

class PlayAlongLayout(RelativeLayout):
  
    def __init__(self, controller_reader: ControllerReader, controller_type="XGamepad", button_icon_style='Alt', **kwargs):
        super().__init__(**kwargs)
        self.controller_type = controller_type
        self.button_icon_style = button_icon_style
        self.controller_reader = controller_reader
        self.button_displays = {
            "direction": JoystickLayout(size_hint=(0.5, None), height=self.width * 0.5, pos_hint={'center_x': 0.25, 'bottom': 0})
        }
        button_names = ["A", "X", "B", "Y", "RT", "RB", "LT", "LB"]
        for i in range(len(button_names)):
            self.button_displays[button_names[i]] = ButtonLayout(button_source=get_standard_button_icon(self.controller_type, self.button_icon_style, button_names[i]), size_hint=(0.07, 1), pos_hint={'x': 0.5 + i * (0.48/8), 'y': 0 if i%2==0 else 0.1})
        [self.add_widget(self.button_displays[button]) for button in self.button_displays]
        self.bind(size=self.update_joystick_layout_size)
        self.update_state()

    def update_joystick_layout_size(self, *args):
        self.button_displays['direction'].height = self.width * 0.5
    
    def update_state(self):
        controller_state = self.controller_reader.get_controller_state()
        for button in controller_state:
            self.button_displays[button].update_state(controller_state[button], [frame[button] for frame in TEST_INPUTS])


        
        
    
    