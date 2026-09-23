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
            end_radius = self.inner_circle_radius + (i + 1) / count * (self.outer_circle_radius - self.inner_circle_radius)
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

    def update_state(self, input_frames):
        if not input_frames:
            input_frames = [5]
        self.draw_lines(input_frames)
        self.draw_arcs(input_frames)
        self.draw_dots(input_frames)


class ButtonColumn(Widget):
    """A button at the bottom of a column, with upcoming presses falling down toward it.

    Prompts are pooled Rectangle instructions sharing the button's texture, which is far cheaper
    than moving up to 120 Image widgets per column every frame.
    """

    def __init__(self, button_source, **kwargs):
        super().__init__(**kwargs)
        self.texture = CoreImage(button_source).texture
        self.prompts = []
        self.visible_prompts = 0
        with self.canvas:
            self.button_color = Color(1, 1, 1, BUTTON_RELEASED_OPACITY)
            self.button = Rectangle(texture=self.texture)
            Color(1, 1, 1, BUTTON_PROMPT_OPACITY)
            self.prompt_group = InstructionGroup()
        self.bind(pos=self._layout_button, size=self._layout_button)

    def _icon_size(self):
        return self.width, self.width * self.texture.height / self.texture.width

    def _layout_button(self, *args):
        self.button.pos = self.pos
        self.button.size = self._icon_size()

    def update_state(self, pressed, input_frames):
        self.button_color.a = 1 if pressed else BUTTON_RELEASED_OPACITY
        icon_size = self._icon_size()
        travel = self.height - icon_size[1]
        count = len(input_frames)
        shown = 0
        for i, frame_state in enumerate(input_frames):
            if not frame_state:
                continue
            if shown == len(self.prompts):
                prompt = Rectangle(texture=self.texture)
                self.prompts.append(prompt)
                self.prompt_group.add(prompt)
            prompt = self.prompts[shown]
            prompt.pos = (self.x, self.y + travel * i / count)
            prompt.size = icon_size
            shown += 1
        for prompt in self.prompts[shown : self.visible_prompts]:
            prompt.pos = OFFSCREEN
        self.visible_prompts = shown
