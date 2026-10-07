from kivy.uix.relativelayout import RelativeLayout
from widgets import ButtonColumn, StickImage, DirectionalPromptWidget
from images import get_standard_button_icon
from kivy.metrics import dp
from layouts.feedback import FeedbackDisplay


# Draws the user-controlled joystick as well as the input prompts.
class JoystickLayout(RelativeLayout):
    def __init__(self, **kwargs):
        super(JoystickLayout, self).__init__(**kwargs)
        self.stick_image = StickImage(pos_hint={"center_x": 0.5, "center_y": 0.5}, size_hint=(0.25, 0.25))
        self.add_widget(self.stick_image)
        self.directional_prompt_widget = DirectionalPromptWidget(pos_hint={"center_x": 0.5, "center_y": 0.5})
        self.add_widget(self.directional_prompt_widget)

    def update_state(self, direction, input_frames, offset=0.0):
        self.stick_image.update_state(direction)
        self.directional_prompt_widget.update_state(input_frames, offset)


class PlayAlongLayout(FeedbackDisplay, RelativeLayout):
    """The ring display: the stick as a spiral of upcoming directions around a circle, and the
    buttons falling down columns, with the same practice feedback as every display."""

    button_names = ["A", "X", "B", "Y", "RT", "RB", "LT", "LB"]

    def __init__(self, controller_type="XGamepad", button_icon_style='Alt', **kwargs):
        super().__init__(**kwargs)
        self.controller_type = controller_type
        self.button_icon_style = button_icon_style
        self.button_displays = {
            "direction": JoystickLayout(size_hint=(0.5, None), height=self.width * 0.5, pos_hint={'center_x': 0.25, 'y': 0})
        }
        for i, name in enumerate(self.button_names):
            self.button_displays[name] = ButtonColumn(
                button_source=get_standard_button_icon(self.controller_type, self.button_icon_style, name),
                size_hint=(0.07, 1),
                pos_hint={'x': 0.5 + i * (0.48 / 8), 'y': 0},
            )
        for display in self.button_displays.values():
            self.add_widget(display)
        self._init_feedback()

    def verdict_spot(self):
        # Up and to the right of the stick's middle, where inputs arrive.
        return self.width * 0.25 + dp(110), self.height * 0.62
        self.bind(size=self.update_joystick_layout_size)

    def update_joystick_layout_size(self, *args):
        self.button_displays['direction'].height = self.width * 0.5

    def update_state(self, controller_state, input_track, offset=0.0):
        """offset is how far through the current frame the clock is, for smooth movement."""
        for button, display in self.button_displays.items():
            display.update_state(controller_state[button], [frame[button] for frame in input_track], offset)
