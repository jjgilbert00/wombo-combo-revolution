"""The arrow lanes display: the ring display's falling button columns, with the stick shown as lanes
of arrows instead of a spiral, like a dance game.

Each lane holds one or two directions (numpad notation). By default there are five, left to right:
left, down-left/up-left, down/up, down-right/up-right, right. An arrow falls in its lane pointing its
own way, so an up arrow comes down the down/up lane pointing up. At the bottom of each lane is its
receptor: the outline of every arrow the lane holds, centred on each other, which lights up with
the arrow the player is holding. In a shared lane one arrow is drawn in front, crisp, over a faint
one behind: the down one (the lane's first) unless an up one is the next to arrive.
"""
from kivy.core.image import Image as CoreImage
from kivy.graphics import Color, Rectangle
from kivy.graphics.texture import Texture
from kivy.resources import resource_find
from kivy.uix.relativelayout import RelativeLayout
from kivy.metrics import dp
from kivy.uix.widget import Widget
from PIL import Image, ImageChops, ImageFilter

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


def draw_arrow(direction, size, font_path):
    """A lane's arrow: the input list's glyph, white with a dark outline, centred in the square.
    Arrows sharing a lane overlap at their centres."""
    return draw_direction_glyph(direction, size, font_path)


BACK_ARROW_STRENGTH = 0.3  # How faint the arrow behind is in a shared lane's receptor.
RECEPTOR_OPACITY = 0.55
SHARED_RECEPTOR_OPACITY = 0.75  # Brighter, so the arrow in front stands out from the one behind.


def _shape(direction, size, font_path):
    """An arrow's whole shape, outline included, as a mask."""
    return draw_arrow(direction, size, font_path).getchannel("A").point(lambda value: 255 if value > 96 else 0)


def _outline(shape, size):
    """The edge of a shape, as a mask."""
    return ImageChops.subtract(shape, shape.filter(ImageFilter.MinFilter(max(3, size // 28) * 2 + 1)))


def draw_receptor(directions, size, font_path, front=None):
    """A lane's receptor as an RGBA image: the outline of its arrow, or with two, both centred on
    each other with front drawn over the other: front's lines at full strength, the one behind
    faint and hidden where it passes under front."""
    front = front or directions[0]
    front_shape = _shape(front, size, font_path)
    edge = _outline(front_shape, size)
    cover = front_shape.filter(ImageFilter.MaxFilter(3))  # A hair wider, for a clean gap.
    for direction in directions:
        if direction != front:
            back = _outline(_shape(direction, size, font_path), size)
            back = ImageChops.subtract(back, cover).point(lambda v: round(v * BACK_ARROW_STRENGTH))
            edge = ImageChops.lighter(edge, back)
    frame = Image.new("RGBA", (size, size), (235, 235, 240, 0))
    frame.putalpha(edge)
    return frame


class ArrowLane(Widget):
    """One lane: its receptor at the bottom and upcoming arrows falling toward it, a held direction
    as one arrow with a tail as long as it's held."""

    def __init__(self, directions, arrows, receptors, **kwargs):
        """receptors: direction in front -> receptor texture. The first direction is in front
        unless another is the next one coming (so down/up shows down until an up is next)."""
        super().__init__(**kwargs)
        self.directions = directions
        self.arrows = arrows  # Direction -> arrow texture.
        self.receptors = receptors
        self.falling = FallingRuns(tail_from=0.5)
        with self.canvas:
            Color(1, 1, 1, RECEPTOR_OPACITY if len(directions) == 1 else SHARED_RECEPTOR_OPACITY)
            self.receptor = Rectangle(texture=receptors[directions[0]])
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
        runs = runs_of(mine)
        # The arrow in front is the next one still to arrive (not one already at the receptor, so an
        # up shows while a down charge is held), else the one held, else the lane's first.
        front = next((d for first, _, d in runs if first > 0),
                     direction if direction in self.directions else self.directions[0])
        self.receptor.texture = self.receptors[front]
        self.falling.draw(runs, self.x, self.y, icon, self.height - icon[1], max(1, len(input_frames)),
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
            arrows = {direction: _texture(draw_arrow(direction, GLYPH_PIXELS, font))
                      for direction in directions}
            receptors = {front: _texture(draw_receptor(directions, GLYPH_PIXELS, font, front))
                         for front in directions}
            lane = ArrowLane(directions, arrows, receptors,
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
