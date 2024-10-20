from kivy.app import App
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.widget import Widget
from kivy.graphics import Rectangle, Color
from widgets import ButtonImage, StickImage, DraggableWidget, DirectionalPromptWidget
from images import IMAGE_SOURCE_BUTTON_UP, get_standard_button_icon



# Draws the user-controlled joystick as well as the input prompts.
class JoystickLayout(RelativeLayout):
    def __init__(self, **kwargs):
        super(JoystickLayout, self).__init__(**kwargs)
        with self.canvas:
            self.stick_image = StickImage(pos_hint={"center_x": 0.5, "center_y": 0.5}, size_hint=(0.25, 0.25))
            self.add_widget(self.stick_image)
            self.directional_prompt_widget = DirectionalPromptWidget(pos_hint={"center_x": 0.5, "center_y": 0.5}, size=self.size)
            self.add_widget(self.directional_prompt_widget)

    def update_state(self, direction, input_frames):
        self.stick_image.update_state(direction)
        self.directional_prompt_widget.update_state(input_frames)


# Draws the user-controlled buttons as well as the input prompts.
class ButtonLayout(RelativeLayout):
    def __init__(self, button_source=IMAGE_SOURCE_BUTTON_UP, **kwargs):
        super(ButtonLayout, self).__init__(**kwargs)
        self.button_source = button_source
        self.input_pool =[]
        with self.canvas:
            self.controller_button = ButtonImage(source=self.button_source, pos_hint={"center_x": 0.5, "bottom": 0}, size_hint=(1, None), opacity=0.5)
            self.add_widget(self.controller_button)

    
    def update_state(self, controller_state, input_frames):
        if input_frames:
            input_counter = 0
            for i in range(len(input_frames)-1, -1, -1):
                frame_state = input_frames[i]
                if frame_state:
                    if len(self.input_pool) <= input_counter:
                        button = ButtonImage(source=self.button_source, size_hint=(1,None), opacity=0.5)
                        self.input_pool.append(button)
                        self.add_widget(button)
                    else:
                        button = self.input_pool[input_counter]
                    button.y = self.height * (i/len(input_frames))
                    input_counter += 1
            for i in range(input_counter, len(self.input_pool)):
                self.input_pool[i].y = -self.height
        self.controller_button.update_state(controller_state)
        self.canvas.ask_update()



class PlayAlongLayout(RelativeLayout):
  
    def __init__(self, controller_type="XGamepad", button_icon_style='Alt', **kwargs):
        super().__init__(**kwargs)
        self.controller_type = controller_type
        self.button_icon_style = button_icon_style
        self.button_displays = {
            "direction": JoystickLayout(size_hint=(0.5, None), height=self.width * 0.5, pos_hint={'center_x': 0.25, 'bottom': 0})
        }
        button_names = ["A", "X", "B", "Y", "RT", "RB", "LT", "LB"]
        for i in range(len(button_names)):
            self.button_displays[button_names[i]] = ButtonLayout(button_source=get_standard_button_icon(self.controller_type, self.button_icon_style, button_names[i]), size_hint=(0.07, 1), pos_hint={'x': 0.5 + i * (0.48/8), 'y': 0 if i%2==0 else 0})
        [self.add_widget(self.button_displays[button]) for button in self.button_displays]
        self.bind(size=self.update_joystick_layout_size)

    def update_joystick_layout_size(self, *args):
        self.button_displays['direction'].height = self.width * 0.5
    
    def update_state(self, controller_state, input_track):
        for button in controller_state:
            self.button_displays[button].update_state(controller_state[button], [frame[button] for frame in input_track])


        
        
    
    