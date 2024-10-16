from kivy.app import App
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.widget import Widget
from kivy.graphics import Rectangle, Color

from controller import ControllerReader
from widgets import ButtonImage, StickImage


class JoystickWidget(Widget):
    # TODO: Design the joystick widget and animate the joystick inputs over time
    pass

class ColumnWidget(Widget):
    button_image = None
    def __init__(self,  **kwargs):
        super(ColumnWidget, self).__init__(**kwargs)
        with self.canvas:
            self.button_image = ButtonImage(pos=self.pos, size_hint=(1, 1))
            # self.button_image = ButtonImage(pos=self.pos, size_hint=(self.size_hint_x, self.size_hint_x))
        self.bind(pos=self.update_canvas)
        self.bind(size=self.update_canvas)
        self.update_canvas()  
    
    def update_canvas(self, *args):
        # Draw the descending inputs
        print("TODO: Draw the descending inputs")

        # Draw the button silhouette at the bottom of the screen
        self.button_image.size = (self.width, self.width)
        self.button_image.pos = self.pos


class PlayAlongLayout(RelativeLayout):
    def __init__(self, controller_reader: ControllerReader, **kwargs):
        super().__init__(**kwargs)
        self.joystick = JoystickWidget(size_hint=(0.4, 1), pos_hint={'center_x': 0.5, 'center_y': 0.8})
        self.add_widget(self.joystick)

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

        initial_positions = [
            (0.5, 0),
            (0.575, 0.05625),
            (0.65, 0),
            (0.725, 0.05625),
            (0.8, 0),
            (0.875, 0.05625),
            (0.95, 0),
            (1.025, 0.05625),
        ]
        for i in range(8):
            width = 0.1
            height = 1 
            x= 0.5 + i * (0.4/8)
            y= 0 if i%2==0 else 0.1
            print(f"X: {x}, Y: {y} Width: {width}, Height: {height}")
            column = ColumnWidget(size_hint=(width, height), pos_hint={'x': x, 'y': y})
            self.add_widget(column)
        
    
    