
from kivy.uix.image import Image
from kivy.properties import BooleanProperty
from kivy.uix.widget import Widget
from kivy.graphics import Ellipse, Rectangle, Color

from images import  IMAGE_SOURCE_DIRECTION, IMAGE_SOURCE_BUTTON_UP


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


class StickImage(Image):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.source = IMAGE_SOURCE_DIRECTION[5]
    
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
    
# class ButtonPromptWidget(DraggableWidget):
#     border = None
#     input_pool = []
#     active_buttons = []
#     button_source = None
#     def __init__(self, button_source, **kwargs):
#         super(ButtonPromptWidget, self).__init__(**kwargs)
#         self.button_source = button_source
#         with self.canvas:
#             Color(1,1,1,0.07)
#             self.border = Rectangle(pos=self.pos, size=self.size)
#         self.bind(pos=self.update_canvas)
#         self.bind(size=self.update_canvas)
#         self.update_canvas()
    
#     def spawn_input(self):
#         if self.input_pool:
#             input = self.input_pool.pop()
#         else:
#             input = ButtonImage(source=self.button_source, pos=(self.pos[0], self.pos[1] + self.height), size_hint=(1,1))
#             self.add_widget(input)
        
#         # input.y = self.height
#         # input.x = self.width // 2 - input.width // 2
#         self.active_buttons.append(input)
    
#     def update_state(self, ):
#         self.canvas.ask_update()

#     def update_canvas(self, *args):
#         #Resize/repostion the inputs
#         for i, input in enumerate(self.active_buttons):
#             input.size = (self.width, self.width)
#             input.x = self.x


#         # Draw the border of the column
#         self.border.pos = self.pos
#         self.border.size = self.size

#         # Draw the descending inputs
#         # print("TODO: Draw the descending inputs")


#         if not self.active_buttons:
#             self.spawn_input()

class ButtonImage(Image):
    def __init__(self, *args, opacity=1, source=IMAGE_SOURCE_BUTTON_UP, **kwargs):
        super().__init__(*args, **kwargs)
        self.source = source
        self.color[3] = opacity

    def update_state(self, pressed):
        if pressed:
            self.color[3] = 1
        else:
            self.color[3] = 0.3

    