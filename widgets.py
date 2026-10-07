from kivy.core.image import Image as CoreImage
from kivy.uix.image import Image
from kivy.uix.widget import Widget
from kivy.graphics import Ellipse, Rectangle, Color, Line, InstructionGroup
import math

from images import IMAGE_SOURCE_DIRECTION

PROMPT_COLOR = (1, 1, 1, 0.9)
GUIDE_COLOR = (1, 1, 1, 0.25)
BUTTON_RELEASED_OPACITY = 0.4
BUTTON_PROMPT_OPACITY = 0.6
# Kivy keeps the old geometry when an Ellipse is resized to zero, so unused graphics are parked here.
OFFSCREEN = (-10000, -10000)


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


class DirectionalPromptWidget(Widget):
    direction_to_angle = {
        1: 225,
        2: 270,
        3: 315,
        4: 180,
        6: 0,
        7: 135,
        8: 90,
        9: 45,
    }
    adjacent_pairs = {(1, 2), (2, 3), (3, 6), (6, 9), (9, 8), (8, 7), (7, 4), (4, 1)}
    dot_radius = 5

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Graphics are pooled and repositioned every frame; unused ones are hidden rather than removed.
        self.lines = []
        self.dots = []
        self.arcs = []
        self.inner_circle_radius = self.width * 0.09
        self.outer_circle_radius = self.width / 2
        self.offset = 0.0  # How far through the current frame, so prompts move smoothly.
        with self.canvas:
            Color(*GUIDE_COLOR)
            self.inner_border = Line()
            self.outer_border = Line()
            Color(*PROMPT_COLOR)
            self.prompt_group = InstructionGroup()

        self.bind(pos=self.update_canvas)
        self.bind(size=self.update_canvas)
        self.update_canvas()

    def update_canvas(self, *args):
        self.inner_circle_radius = self.width * 0.09
        self.outer_circle_radius = self.width / 2
        self.center_point = (self.x + self.width / 2, self.y + self.width / 2)
        self.inner_border.circle = (*self.center_point, self.inner_circle_radius)
        self.outer_border.circle = (*self.center_point, self.outer_circle_radius)

    def _point(self, direction, index, count):
        index = max(0.0, index - self.offset)
        radius = self.inner_circle_radius + index / count * (self.outer_circle_radius - self.inner_circle_radius)
        angle = math.radians(self.direction_to_angle[direction])
        return self.center_point[0] + radius * math.cos(angle), self.center_point[1] + radius * math.sin(angle)

    def _pooled(self, pool, index, factory):
        if index >= len(pool):
            instruction = factory()
            pool.append(instruction)
            self.prompt_group.add(instruction)
        return pool[index]

    def draw_dots(self, input_frames):
        count = len(input_frames)
        dot_counter = 0
        size = (self.dot_radius * 2, self.dot_radius * 2)
        for i, direction in enumerate(input_frames):
            if direction == 5:
                continue
            # Only mark where a direction starts and ends, not every frame it's held.
            if 0 < i < count - 1 and input_frames[i - 1] == direction == input_frames[i + 1]:
                continue
            x, y = self._point(direction, i, count)
            dot = self._pooled(self.dots, dot_counter, Ellipse)
            dot.pos = (x - self.dot_radius, y - self.dot_radius)
            dot.size = size
            dot_counter += 1
        for dot in self.dots[dot_counter:]:
            dot.pos = OFFSCREEN

    def draw_lines(self, input_frames):
        count = len(input_frames)
        line_counter = 0
        i = 0
        while i < count:
            start = i
            while i + 1 < count and input_frames[i + 1] == input_frames[start]:
                i += 1
            if input_frames[start] != 5 and i > start:
                line = self._pooled(self.lines, line_counter, lambda: Line(width=2))
                line.points = [*self._point(input_frames[start], start, count), *self._point(input_frames[i], i, count)]
                line_counter += 1
            i += 1
        for line in self.lines[line_counter:]:
            line.points = []

    def draw_arcs(self, input_frames):
        count = len(input_frames)
        arc_counter = 0
        for i in range(count - 1):
            current, following = input_frames[i], input_frames[i + 1]
            if (current, following) not in self.adjacent_pairs and (following, current) not in self.adjacent_pairs:
                continue
            start = self._point(current, i, count)
            end = self._point(following, i + 1, count)
            # Bow the curve outward through the angle halfway between the two directions.
            mid_angle = (self.direction_to_angle[current] + self.direction_to_angle[following]) / 2
            if {current, following} == {3, 6}:  # 315 and 0 degrees are neighbours.
                mid_angle += 180
            end_radius = self.inner_circle_radius + max(0.0, i + 1 - self.offset) / count * (
                self.outer_circle_radius - self.inner_circle_radius)
            mid_radius = end_radius * 15 / 14  # 15/14 is a magic number that makes the arcs look good
            mid = (
                self.center_point[0] + mid_radius * math.cos(math.radians(mid_angle)),
                self.center_point[1] + mid_radius * math.sin(math.radians(mid_angle)),
            )
            arc = self._pooled(self.arcs, arc_counter, lambda: Line(width=2))
            arc.bezier = [*start, *mid, *end]
            arc_counter += 1
        for arc in self.arcs[arc_counter:]:
            arc.points = []

    def update_state(self, input_frames, offset=0.0):
        if not input_frames:
            input_frames = [5]
        self.offset = offset
        self.draw_lines(input_frames)
        self.draw_arcs(input_frames)
        self.draw_dots(input_frames)


HOLD_TAIL_COLOR = (1, 1, 1, 0.32)


def runs_of(values):
    """[(first index, last index, value)] for each stretch of equal, truthy values."""
    runs, start = [], None
    for i, value in enumerate(values + [None]):
        if start is not None and value != values[start]:
            runs.append((start, i - 1, values[start]))
            start = None
        if start is None and value:
            start = i
    return runs


class FallingRuns:
    """Prompts falling toward the bottom of a column, one per held input: an icon where the input
    starts and a tail behind it as long as it's held, like a dance game's hold notes. (Drawing every
    frame of a hold instead piles up a stack of icons.)"""

    def __init__(self, tail_from=1.0):
        # Where on the icon the tail starts, as a share of its height: the top for a solid icon such
        # as a button, the middle for an arrow drawn from the middle out.
        self.tail_from = tail_from
        self.tail_group, self.head_group = InstructionGroup(), InstructionGroup()
        self.tails, self.heads = [], []
        self.used = 0

    def _pair(self, index):
        if index == len(self.heads):
            self.tails.append(Rectangle())
            self.heads.append(Rectangle())
            self.tail_group.add(self.tails[-1])
            self.head_group.add(self.heads[-1])
        return self.tails[index], self.heads[index]

    def draw(self, runs, x, y, icon, travel, count, offset, texture_for):
        """runs from runs_of(); icon is the (width, height) of a prompt; travel the height it falls."""
        width, height = icon
        place = lambda index: y + travel * max(0.0, index - offset) / count
        for n, (first, last, value) in enumerate(runs):
            tail, head = self._pair(n)
            head.texture = texture_for(value)
            head.pos, head.size = (x, place(first)), icon
            # Up to the middle of where the hold ends; none if that's inside the icon.
            top = place(last) + height / 2
            bottom = place(first) + height * self.tail_from
            tail.pos = (x + width * 0.32, bottom)
            tail.size = (width * 0.36, max(0.0, top - bottom))
        for tail, head in zip(self.tails[len(runs):self.used], self.heads[len(runs):self.used]):
            tail.pos = head.pos = OFFSCREEN
        self.used = len(runs)


class ButtonColumn(Widget):
    """A button at the bottom of a column, with upcoming presses falling down toward it.

    A press falls as the button's icon with a tail as long as it's held (see FallingRuns).
    """

    def __init__(self, button_source, **kwargs):
        super().__init__(**kwargs)
        self.texture = CoreImage(button_source).texture
        self.falling = FallingRuns()
        with self.canvas:
            self.button_color = Color(1, 1, 1, BUTTON_RELEASED_OPACITY)
            self.button = Rectangle(texture=self.texture)
            Color(*HOLD_TAIL_COLOR)
        self.canvas.add(self.falling.tail_group)
        self.canvas.add(Color(1, 1, 1, BUTTON_PROMPT_OPACITY))
        self.canvas.add(self.falling.head_group)
        self.bind(pos=self._layout_button, size=self._layout_button)

    def _icon_size(self):
        return self.width, self.width * self.texture.height / self.texture.width

    def _layout_button(self, *args):
        self.button.pos = self.pos
        self.button.size = self._icon_size()

    def update_state(self, pressed, input_frames, offset=0.0):
        self.button_color.a = 1 if pressed else BUTTON_RELEASED_OPACITY
        icon_size = self._icon_size()
        if not input_frames:
            self.falling.draw([], self.x, self.y, icon_size, 0, 1, offset, None)
            return
        self.falling.draw(runs_of([bool(state) for state in input_frames]), self.x, self.y, icon_size,
                          self.height - icon_size[1], len(input_frames), offset, lambda value: self.texture)
