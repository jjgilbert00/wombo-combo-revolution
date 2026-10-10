"""Widgets no longer used by the app (removed in the clean-up of leftovers)."""
from kivy.core.image import Image as CoreImage
from kivy.uix.image import Image

from images import IMAGE_SOURCE_DIRECTION


class StickImage(Image):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Load every direction once and swap textures, instead of re-resolving a source each change.
        self.textures = {d: CoreImage(source).texture for d, source in IMAGE_SOURCE_DIRECTION.items()}
        self.direction = None
        self.update_state(5)

    def update_state(self, direction):
        if direction != self.direction:
            self.direction = direction
            self.texture = self.textures[direction]
