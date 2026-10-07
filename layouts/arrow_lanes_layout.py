"""The arrow lanes display: the ring display's falling button columns, with the stick shown as lanes
of arrows instead of a spiral, like a dance game.

Each lane holds one or two directions (numpad notation). By default there are five, left to right:
left, down-left/up-left, down/up, down-right/up-right, right. An arrow falls in its lane pointing its
own way, so an up arrow comes down the down/up lane pointing up. At the bottom of each lane is its
receptor: the outline of every arrow the lane holds, merged into one frame (a double-headed arrow
for down/up), which lights up with the arrow the player is holding.
"""
from kivy.core.image import Image as CoreImage
from kivy.graphics import Color, Rectangle
from kivy.graphics.texture import Texture
from kivy.resources import resource_find
from kivy.uix.relativelayout import RelativeLayout
from kivy.metrics import dp
from kivy.uix.widget import Widget
from PIL import Image, ImageDraw, ImageFilter

from images import get_standard_button_icon
from layouts.feedback import FeedbackDisplay
from input_list import draw_direction_glyph
from widgets import BUTTON_PROMPT_OPACITY, HOLD_TAIL_COLOR, ButtonColumn, FallingRuns, runs_of

DEFAULT_LANES = ((4,), (1, 7), (2, 8), (3, 9), (6,))  # Left to right.
GLYPH_PIXELS = 128


def _texture(image):
    texture = Texture.create(size=image.size, colorfmt="rgba")
    texture.blit_buffer(image.transpose(Image.FLIP_TOP_BOTTOM).tobytes(), colorfmt="rgba", bufferfmt="ubyte")
    return texture


VECTORS = {1: (-1, -1), 2: (0, -1), 3: (1, -1), 4: (-1, 0), 6: (1, 0), 7: (-1, 1), 8: (0, 1), 9: (1, 1)}


def _half_arrow_mask(direction, size):
    """An arrow from the middle of the square out toward direction, as a mask: a thick shaft with a
    round joint at the middle and a triangular head at the tip. Two of these share the joint, so
    together they read as one shape (a double-headed arrow for down and up)."""
    scale = 4
    s = size * scale
    mask = Image.new("L", (s, s), 0)
    draw = ImageDraw.Draw(mask)
    dx, dy = VECTORS[direction]
    length = (dx * dx + dy * dy) ** 0.5
    ux, uy = dx / length, -dy / length  # Image y runs down.
    px, py = -uy, ux  # Perpendicular.
    c = s / 2
    reach = s * (0.44 if dx and dy else 0.46)  # Diagonals reach toward the corners a little less.
    tip = (c + ux * reach, c + uy * reach)
    base = (c + ux * reach * 0.52, c + uy * reach * 0.52)
    head, shaft = s * 0.19, s * 0.085
    draw.polygon([(c + px * shaft, c + py * shaft), (base[0] + px * shaft, base[1] + py * shaft),
                  (base[0] - px * shaft, base[1] - py * shaft), (c - px * shaft, c - py * shaft)], fill=255)
    draw.polygon([tip, (base[0] + px * head, base[1] + py * head), (base[0] - px * head, base[1] - py * head)],
                 fill=255)
    draw.ellipse([c - shaft, c - shaft, c + shaft, c + shaft], fill=255)  # The joint.
    return mask.resize((size, size), Image.LANCZOS)


def arrow_mask(directions, direction, size, font_path):
    """The shape an arrow takes in a lane: the whole arrow if the lane has one direction, or the half
    from the middle out if it shares the lane."""
    if len(directions) == 1:
        return draw_direction_glyph(direction, size, font_path).getchannel("A")
    return _half_arrow_mask(direction, size)


def draw_arrow(directions, direction, size, font_path):
    """A lane's arrow for direction: white with a dark outline, like the input list's glyphs."""
    if len(directions) == 1:
        return draw_direction_glyph(direction, size, font_path)
    mask = arrow_mask(directions, direction, size, font_path).point(lambda v: 255 if v > 96 else 0)
    border = mask.filter(ImageFilter.MaxFilter(max(3, size // 32) * 2 + 1))
    image = Image.new("RGBA", (size, size), (30, 30, 34, 0))
    image.putalpha(border)
    image.paste((245, 245, 245, 255), mask=mask)
    return image


def draw_receptor(directions, size, font_path):
    """The outline of every arrow the lane holds, merged into one frame, as an RGBA image."""
    shape = Image.new("L", (size, size), 0)
    for direction in directions:
        shape = Image.composite(Image.new("L", (size, size), 255), shape,
                                arrow_mask(directions, direction, size, font_path))
    shape = shape.point(lambda value: 255 if value > 96 else 0)
    inside = shape.filter(ImageFilter.MinFilter(max(3, size // 28) * 2 + 1))
    edge = Image.new("L", (size, size), 0)
    edge.paste(shape, mask=Image.eval(inside, lambda v: 255 - v))
    frame = Image.new("RGBA", (size, size), (235, 235, 240, 0))
    frame.putalpha(edge)
    return frame


class ArrowLane(Widget):
    """One lane: its receptor at the bottom and upcoming arrows falling toward it, a held direction
    as one arrow with a tail as long as it's held."""

    def __init__(self, directions, arrows, receptor, **kwargs):
        super().__init__(**kwargs)
        self.directions = directions
        self.arrows = arrows  # Direction -> arrow texture.
        self.falling = FallingRuns(tail_from=0.5)
        with self.canvas:
            Color(1, 1, 1, 0.55)
            self.receptor = Rectangle(texture=receptor)
            self.held_color = Color(1, 1, 1, 0)
            self.held = Rectangle()
            Color(*HOLD_TAIL_COLOR)
        self.canvas.add(self.falling.tail_group)
        self.canvas.add(Color(1, 1, 1, BUTTON_PROMPT_OPACITY))
        self.canvas.add(self.falling.head_group)
        self.bind(pos=self._layout, size=self._layout)

    def _icon(self):
        return self.width, self.width

    def _layout(self, *args):
        self.receptor.pos = self.held.pos = self.pos
        self.receptor.size = self.held.size = self._icon()

    def update_state(self, direction, input_frames, offset=0.0):
        """direction is the one held now; input_frames the upcoming frames' directions; offset how
        far through the current frame the clock is."""
        if direction in self.directions:
            self.held.texture = self.arrows[direction]
            self.held_color.a = 1
        else:
            self.held_color.a = 0
        icon = self._icon()
        mine = [d if d in self.directions else None for d in input_frames]
        self.falling.draw(runs_of(mine), self.x, self.y, icon, self.height - icon[1], max(1, len(input_frames)),
                          offset, lambda d: self.arrows[d])


class ArrowLanesLayout(FeedbackDisplay, RelativeLayout):
    """Direction lanes on the left half, the button columns on the right, all falling toward the
    bottom. Same update_state as the ring display, so it's driven the same way, and the same practice
    feedback as every display (verdicts pop up just above the receptors)."""

    button_names = ["A", "X", "B", "Y", "RT", "RB", "LT", "LB"]

    def __init__(self, lanes=DEFAULT_LANES, controller_type="XGamepad", button_icon_style="Alt", **kwargs):
        super().__init__(**kwargs)
        font = resource_find("data/fonts/Roboto-Bold.ttf")
        self.lanes = []
        width = 0.44 / len(lanes)
        for i, directions in enumerate(lanes):
            arrows = {direction: _texture(draw_arrow(directions, direction, GLYPH_PIXELS, font))
                      for direction in directions}
            lane = ArrowLane(directions, arrows, _texture(draw_receptor(directions, GLYPH_PIXELS, font)),
                             size_hint=(width * 0.82, 1), pos_hint={"x": 0.03 + i * width, "y": 0})
            self.lanes.append(lane)
            self.add_widget(lane)
        self.button_columns = {}
        for i, name in enumerate(self.button_names):
            column = ButtonColumn(button_source=get_standard_button_icon(controller_type, button_icon_style, name),
                                  size_hint=(0.07, 1), pos_hint={"x": 0.5 + i * (0.48 / 8), "y": 0})
            self.button_columns[name] = column
            self.add_widget(column)
        self._init_feedback()

    def verdict_spot(self):
        receptor_top = self.lanes[0].width if self.lanes else 0
        return self.width * 0.04, receptor_top + dp(150)

    def update_state(self, controller_state, input_track, offset=0.0):
        directions = [frame["direction"] for frame in input_track]
        for lane in self.lanes:
            lane.update_state(controller_state["direction"], directions, offset)
        for name, column in self.button_columns.items():
            column.update_state(controller_state[name], [frame[name] for frame in input_track], offset)
