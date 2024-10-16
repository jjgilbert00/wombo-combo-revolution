
from kivy.uix.image import Image as CoreImage

from images import IMAGE_SOURCE_5, IMAGE_SOURCE_DIRECTION, IMAGE_SOURCE_BUTTON_DOWN, IMAGE_SOURCE_BUTTON_UP
class StickImage(CoreImage):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.source = IMAGE_SOURCE_5
    
    def update_state(self, direction):
        self.source =  IMAGE_SOURCE_DIRECTION[direction]


class ButtonImage(CoreImage):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.source = IMAGE_SOURCE_BUTTON_UP

    def update_state(self, pressed):
        if pressed:
            self.source = IMAGE_SOURCE_BUTTON_DOWN
        else:
            self.source = IMAGE_SOURCE_BUTTON_UP