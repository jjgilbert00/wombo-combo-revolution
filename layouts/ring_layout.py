"""The ring display: the stick as a spiral of upcoming directions around a circle (RingPrompts),
the direction held now in the middle, and the buttons falling down columns beside it.
"""
import math

from kivy.graphics import Color, Ellipse, InstructionGroup, Line, Rectangle
from kivy.metrics import dp
from kivy.resources import resource_find
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.widget import Widget

import theme
from glyphs import draw_direction_glyph
from images import get_standard_button_icon
from layouts.drawing import OFFSCREEN, texture_of
from layouts.falling import ButtonColumn
from layouts.feedback import FeedbackDisplay


PROMPT_COLOR = (0.93, 0.93, 0.95, 1)

GUIDE_COLOR = (1, 1, 1, 0.16)


class RingPrompts(Widget):
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
    dot_radius = 6
    line_width = 3

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
            self.inner_border = Line(width=1.5)
            self.outer_border = Line(width=1.5)
            # A faint spoke for each direction, the paths prompts come in along.
            self.spokes = [Line(width=1) for _ in self.direction_to_angle]
            Color(*PROMPT_COLOR)
            self.prompt_group = InstructionGroup()

        self.bind(pos=self.update_canvas)
        self.bind(size=self.update_canvas)
        self.update_canvas()

    def update_canvas(self, *args):
        # The ring fits the widget's shorter side, centred.
        side = min(self.width, self.height) * 0.96
        self.inner_circle_radius = side * 0.09
        self.outer_circle_radius = side / 2
        self.center_point = self.center
        self.inner_border.circle = (*self.center_point, self.inner_circle_radius)
        self.outer_border.circle = (*self.center_point, self.outer_circle_radius)
        for spoke, angle in zip(self.spokes, self.direction_to_angle.values()):
            a = math.radians(angle)
            spoke.points = [self.center_point[0] + self.inner_circle_radius * math.cos(a),
                            self.center_point[1] + self.inner_circle_radius * math.sin(a),
                            self.center_point[0] + self.outer_circle_radius * math.cos(a),
                            self.center_point[1] + self.outer_circle_radius * math.sin(a)]

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
                line = self._pooled(self.lines, line_counter, lambda: Line(width=self.line_width, cap="round"))
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
            arc = self._pooled(self.arcs, arc_counter, lambda: Line(width=self.line_width, cap="round"))
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


class StickGlyph(Widget):
    """The stick's direction now, as the input list's arrow glyph (a circled N for neutral) on a disc
    in the middle of the widget, sized to fit inside the ring's inner circle."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        font = resource_find("data/fonts/Roboto-Bold.ttf")
        self.textures = {d: texture_of(draw_direction_glyph(d, 128, font)) for d in range(1, 10)}
        with self.canvas:
            Color(*theme.SURFACE)
            self.disc = Ellipse()
            Color(1, 1, 1, 1)
            self.glyph = Rectangle(texture=self.textures[5])
        self.bind(pos=self._layout, size=self._layout)

    def _layout(self, *args):
        side = min(self.width, self.height) * 0.16
        self.disc.pos = (self.center_x - side / 2, self.center_y - side / 2)
        self.disc.size = (side, side)
        glyph = side * 0.62
        self.glyph.pos = (self.center_x - glyph / 2, self.center_y - glyph / 2)
        self.glyph.size = (glyph, glyph)

    def update_state(self, direction):
        self.glyph.texture = self.textures.get(direction, self.textures[5])


class RingStick(RelativeLayout):
    def __init__(self, **kwargs):
        super(RingStick, self).__init__(**kwargs)
        self.prompts = RingPrompts(pos_hint={"center_x": 0.5, "center_y": 0.5})
        self.add_widget(self.prompts)
        self.stick_image = StickGlyph()
        self.add_widget(self.stick_image)

    def update_state(self, direction, input_frames, offset=0.0):
        self.stick_image.update_state(direction)
        self.prompts.update_state(input_frames, offset)


class RingLayout(FeedbackDisplay, RelativeLayout):
    """The ring display: the stick as a spiral of upcoming directions around a circle, and the
    buttons falling down columns, with the same practice feedback as every display."""

    button_names = ["A", "X", "B", "Y", "RT", "RB", "LT", "LB"]

    def __init__(self, controller_type="XGamepad", button_icon_style='Alt', **kwargs):
        super().__init__(**kwargs)
        self.controller_type = controller_type
        self.button_icon_style = button_icon_style
        self.button_displays = {
            "direction": RingStick(size_hint=(0.5, 1), pos_hint={'x': 0, 'y': 0})
        }
        for i, name in enumerate(self.button_names):
            self.button_displays[name] = ButtonColumn(
                button_source=get_standard_button_icon(self.controller_type, self.button_icon_style, name),
                size_hint=(0.052, 1),
                pos_hint={'x': 0.5 + i * (0.48 / 8), 'y': 0},
            )
        for display in self.button_displays.values():
            self.add_widget(display)
        self._init_feedback()

    def verdict_spot(self):
        # Up and to the right of the stick's middle, where inputs arrive.
        return self.width * 0.25 + dp(110), self.height * 0.62

    def update_state(self, controller_state, input_track, offset=0.0):
        """offset is how far through the current frame the clock is, for smooth movement."""
        for button, display in self.button_displays.items():
            display.update_state(controller_state[button], [frame[button] for frame in input_track], offset)
