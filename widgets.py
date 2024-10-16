
from kivy.uix.image import Image as CoreImage
from kivy.properties import BooleanProperty
from kivy.uix.widget import Widget
from kivy.graphics import Ellipse, Rectangle, Color

from images import IMAGE_SOURCE_5, IMAGE_SOURCE_DIRECTION, IMAGE_SOURCE_BUTTON_DOWN, IMAGE_SOURCE_BUTTON_UP


class DraggableWidget(Widget):
    dragging = BooleanProperty(False)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self.dragging = True
            self._touch_offset_x = self.x - touch.x
            self._touch_offset_y = self.y - touch.y
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if self.dragging:
            self.pos = ((touch.x + self._touch_offset_x) // 1 , (touch.y + self._touch_offset_y) // 1)
            self.pos_hint = {}
            self.update_canvas()
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if self.dragging:
            self.dragging = False
            return True
        return super().on_touch_up(touch)


class StickImage(CoreImage):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.source = IMAGE_SOURCE_5
    
    def update_state(self, direction):
        self.source =  IMAGE_SOURCE_DIRECTION[direction]

class DirectionalPromptWidget(Widget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        with self.canvas:
            Color(1,1,1,0.25)
            self.border = Ellipse(pos=self.pos, size=self.size)
    
        self.bind(pos=self.update_canvas)
        self.bind(size=self.update_canvas)
        self.update_canvas()
    
    def update_canvas(self, *args):
        self.border.pos = self.pos
        self.border.size = self.size
    
class ButtonPromptWidget(DraggableWidget):
    controller_button = None
    border = None
    button_pool = []
    active_buttons = []
    button_source = None
    def __init__(self, button_source=IMAGE_SOURCE_BUTTON_UP, **kwargs):
        super(ButtonPromptWidget, self).__init__(**kwargs)
        self.button_source = button_source
        with self.canvas:
            Color(0,0,1,0.25)
            self.border = Rectangle(pos=self.pos, size=self.size)
            self.controller_button = ButtonImage(pos=self.pos, size_hint=(1, 1))
        self.bind(pos=self.update_canvas)
        self.bind(size=self.update_canvas)
        self.update_canvas()
    
    def update_state(self, pressed):
        self.controller_button.update_state(pressed)
        self.canvas.ask_update()

    def update_canvas(self, *args):
        # Draw the border of the column
        Color(0,0,1,0.25)

        self.border.pos = self.pos
        self.border.size = self.size

        # Draw the descending inputs
        # print("TODO: Draw the descending inputs")

        # Draw the button silhouette at the bottom of the screen
        self.controller_button.size = (self.width, self.width)
        self.controller_button.pos = self.pos

class ButtonImage(CoreImage):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.source = IMAGE_SOURCE_BUTTON_UP

    def update_state(self, pressed):
        if pressed:
            self.source = IMAGE_SOURCE_BUTTON_DOWN
        else:
            self.source = IMAGE_SOURCE_BUTTON_UP

    