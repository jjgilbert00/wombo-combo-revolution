from kivy.app import App
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.widget import Widget
from kivy.graphics import Rectangle, Color

from controller import ControllerReader
from widgets import ButtonImage, StickImage, DraggableWidget


class JoystickWidget(Widget):
    stick_image = None
    def __init__(self, **kwargs):
        super(JoystickWidget, self).__init__(**kwargs)
        with self.canvas:
            Color(1,0.5,0,1)
            self.border = Rectangle(pos=self.pos, size=self.size)
            self.stick_image = StickImage(pos=self.pos, size_hint=(1, 1))
        self.bind(pos=self.update_canvas)
        self.bind(size=self.update_canvas)
        self.update_canvas()

    def update_state(self, direction):
        self.stick_image.update_state(direction)
        self.canvas.ask_update()
    
    def update_canvas(self, *args):
        # Draw the border of the column
        self.border.pos = self.pos
        self.border.size = self.size

        self.stick_image.size = (self.width, self.width)
        self.stick_image.pos = self.pos
        self.canvas.ask_update()

class ColumnWidget(DraggableWidget):
    button_image = None
    border = None
    def __init__(self, **kwargs):
        super(ColumnWidget, self).__init__(**kwargs)
        with self.canvas:
            Color(0,0,1,0.25)
            self.border = Rectangle(pos=self.pos, size=self.size)
            self.button_image = ButtonImage(pos=self.pos, size_hint=(1, 1))
        self.bind(pos=self.update_canvas)
        self.bind(size=self.update_canvas)
        self.update_canvas()
    
    def update_state(self, pressed):
        self.button_image.update_state(pressed)
        self.canvas.ask_update()

    def update_canvas(self, *args):
        # Draw the border of the column
        Color(0,0,1,0.25)

        self.border.pos = self.pos
        self.border.size = self.size

        # Draw the descending inputs
        # print("TODO: Draw the descending inputs")

        # Draw the button silhouette at the bottom of the screen
        self.button_image.size = (self.width, self.width)
        self.button_image.pos = self.pos


class PlayAlongLayout(RelativeLayout):
    def __init__(self, controller_reader: ControllerReader, **kwargs):
        super().__init__(**kwargs)
        self.controller_reader = controller_reader
        self.button_displays = {
            "direction": JoystickWidget(size_hint=(0.4, 1), pos_hint={'x': 0.1, 'y': 0})
        }
        button_names = ["A", "X", "B", "Y", "RT", "RB", "LT", "LB"]
        for i in range(len(button_names)):
            self.button_displays[button_names[i]] = ColumnWidget(size_hint=(0.1, 1), pos_hint={'x': 0.5 + i * (0.4/8), 'y': 0 if i%2==0 else 0.1})
        [self.add_widget(self.button_displays[button]) for button in self.button_displays]
        self.update_controller_display()
    
    def update_controller_display(self):
        controller_state = self.controller_reader.get_controller_state()
        for button in controller_state:
            self.button_displays[button].update_state(controller_state[button])
        self.canvas.ask_update()
        
    
    