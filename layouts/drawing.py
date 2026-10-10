"""Drawing helpers shared by the displays: PIL images as Kivy textures, an image's silhouette, and
where unused pooled graphics are parked.
"""
from kivy.graphics.texture import Texture
from PIL import Image as PILImage


# Kivy keeps the old geometry when an Ellipse is resized to zero, so unused graphics are parked here.
OFFSCREEN = (-10000, -10000)


def texture_of(image):
    """A Kivy texture of a PIL image, the right way up."""
    image = image.convert("RGBA")
    texture = Texture.create(size=image.size, colorfmt="rgba")
    texture.blit_buffer(image.transpose(PILImage.FLIP_TOP_BOTTOM).tobytes(), colorfmt="rgba", bufferfmt="ubyte")
    return texture


def silhouette_of(image):
    """A texture of an image's shape in solid white. Drawn in the background colour under the image,
    it hides hold tails wherever the image is, even where the image is see-through."""
    image = image.convert("RGBA")
    solid = PILImage.new("RGBA", image.size, (255, 255, 255, 0))
    solid.putalpha(image.getchannel("A"))
    return texture_of(solid)
