from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.metrics import dp
from kivy.resources import resource_find
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.widget import Widget

from images import get_standard_button_icon
from input_list import draw_direction_glyph
from layouts.feedback import FeedbackDisplay
from widgets import ButtonColumn, DirectionalPromptWidget, texture_of
import theme


class StickGlyph(Widget):
    """The stick's direction now, as the input list's arrow glyph (a circled N for neutral) on a disc
    in the middle of the widget, sized to fit inside the ring's inner circle."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        font = resource_find("data/fonts/Roboto-Bold.ttf")
        self.textures = {d: texture_of(draw_direction_glyph(d, 128, font)) for d in range(1, 10)}
        with self.canvas:
            Color(*theme.SURFACE)
            self.disc = Ellipse()
            Color(1, 1, 1, 1)
            self.glyph = Rectangle(texture=self.textures[5])
        self.bind(pos=self._layout, size=self._layout)

    def _layout(self, *args):
        side = min(self.width, self.height) * 0.16
        self.disc.pos = (self.center_x - side / 2, self.center_y - side / 2)
        self.disc.size = (side, side)
        glyph = side * 0.62
        self.glyph.pos = (self.center_x - glyph / 2, self.center_y - glyph / 2)
        self.glyph.size = (glyph, glyph)

    def update_state(self, direction):
        self.glyph.texture = self.textures.get(direction, self.textures[5])


# Draws the user-controlled joystick as well as the input prompts.
class JoystickLayout(RelativeLayout):
    def __init__(self, **kwargs):
        super(JoystickLayout, self).__init__(**kwargs)
        self.directional_prompt_widget = DirectionalPromptWidget(pos_hint={"center_x": 0.5, "center_y": 0.5})
        self.add_widget(self.directional_prompt_widget)
        self.stick_image = StickGlyph()
        self.add_widget(self.stick_image)

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
            "direction": JoystickLayout(size_hint=(0.5, 1), pos_hint={'x': 0, 'y': 0})
        }
        for i, name in enumerate(self.button_names):
            self.button_displays[name] = ButtonColumn(
                button_source=get_standard_button_icon(self.controller_type, self.button_icon_style, name),
                size_hint=(0.052, 1),
                pos_hint={'x': 0.5 + i * (0.48 / 8), 'y': 0},
            )
        for display in self.button_displays.values():
            self.add_widget(display)
        self._init_feedback()

    def verdict_spot(self):
        # Up and to the right of the stick's middle, where inputs arrive.
        return self.width * 0.25 + dp(110), self.height * 0.62

    def update_state(self, controller_state, input_track, offset=0.0):
        """offset is how far through the current frame the clock is, for smooth movement."""
        for button, display in self.button_displays.items():
            display.update_state(controller_state[button], [frame[button] for frame in input_track], offset)
