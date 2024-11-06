from kivy.uix.image import Image
from kivy.properties import BooleanProperty
from kivy.uix.widget import Widget
from kivy.graphics import Ellipse, Rectangle, Color, Line
import math

from images import IMAGE_SOURCE_DIRECTION, IMAGE_SOURCE_BUTTON_UP

class StickImage(Image):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.source = IMAGE_SOURCE_DIRECTION[5]

    def update_state(self, direction):
        self.source = IMAGE_SOURCE_DIRECTION[direction]


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
    dot_radius = 5
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lines = []
        self.dots = []
        self.arcs = []
        self.inner_circle_radius = self.width * 0.09
        self.outer_circle_radius = self.width / 2
        with self.canvas:
            Color(1, 1, 1, 0.25)
            self.inner_border = Line(
                circle=(
                    self.x + self.width / 2,
                    self.y + self.width / 2,
                    self.inner_circle_radius,
                    0,
                    90,
                )
            )
            self.outer_border = Line(circle=(*self.pos, self.width / 2))
            self.increments = []

        self.bind(pos=self.update_canvas)
        self.bind(size=self.update_canvas)
        self.update_canvas()

    def update_canvas(self, *args):
        self.inner_circle_radius = self.width * 0.09
        self.outer_circle_radius = self.width / 2
        self.inner_border.circle = (
            self.x + self.width / 2,
            self.y + self.width / 2,
            self.inner_circle_radius,
        )
        self.outer_border.circle = (
            self.x + self.width / 2,
            self.y + self.width / 2,
            self.outer_circle_radius,
        )

    def polar_to_cartesian(self, angle, radius):
        dx = radius * math.cos(math.radians(angle))
        dy = radius * math.sin(math.radians(angle))
        return (dx, dy)

    def draw_dots(self, input_frames):
        i = 0
        dot_counter = 0
        Color(0,1,0,1)
        while i < len(input_frames):
            if input_frames[i] != 5:
                if i > 0 and input_frames[i] == input_frames[i - 1]:
                    if i < len(input_frames) - 1 and input_frames[i] == input_frames[i + 1]:
                        i += 1
                        continue
                # Draw a dot
                dx, dy = self.polar_to_cartesian(
                    self.direction_to_angle[input_frames[i]], self.inner_circle_radius + (i/len(input_frames) * (self.outer_circle_radius - self.inner_circle_radius))
                )
                x = self.x + self.width / 2 + dx - self.dot_radius # Dots have radius 5
                y = self.y + self.width / 2 + dy - self.dot_radius 

                if len(self.dots) <= dot_counter:
                    dot = Ellipse(
                        pos=(x, y),
                        size=(self.dot_radius * 2, self.dot_radius * 2),
                    )
                    self.dots.append(dot)
                    self.canvas.add(dot)
                else:
                    dot = self.dots[dot_counter]
                dot.pos = (x, y)
                dot_counter += 1
            i += 1
        for i in range(dot_counter, len(self.dots)):
            self.dots[i].pos = (-self.width, -self.width) # Move stale dots offscreen.

    def draw_lines(self, input_frames):
        i = 0
        line_counter = 0
        Color(0,1,0,1)
        while i < len(input_frames):
            start = end = None
            if input_frames[i] != 5:
                start = i
                i += 1
                while i < len(input_frames) and input_frames[i] == input_frames[start]:
                    end = i
                    i += 1
                
                if end != None:
                    # Draw a line from start to end
                    dx, dy = self.polar_to_cartesian(
                        self.direction_to_angle[input_frames[start]], self.inner_circle_radius + (start/len(input_frames) * (self.outer_circle_radius - self.inner_circle_radius))
                    )
                    start_x = self.x + self.width / 2 + dx
                    start_y = self.y + self.width / 2 + dy
                    dx, dy = self.polar_to_cartesian(
                        self.direction_to_angle[input_frames[end]], self.inner_circle_radius + (end/len(input_frames) * (self.outer_circle_radius - self.inner_circle_radius))
                    )
                    end_x = self.x + self.width / 2 + dx
                    end_y = self.y + self.width / 2 + dy
                    if len(self.lines) <= line_counter:
                        line = Line(points=[start_x, start_y, end_x, end_y], width=2)
                        self.lines.append(line)
                        self.canvas.add(line)
                    else:
                        line = self.lines[line_counter]
                    line.points = [start_x, start_y, end_x, end_y]
                    line_counter += 1
            else:
                start = None
            i += 1

        for i in range(line_counter, len(self.lines)):
            self.lines[i].points = [-self.width, 0, -self.width, 0] # Move stale lines offscreen.



    def draw_arcs(self, input_frames):
        arc_counter = 0
        Color(0, 1, 0, 1)
        center_x = self.x + self.width / 2
        center_y = self.y + self.width / 2
        adjacent_pairs = [(1, 2), (2, 3), (3, 6), (6, 9), (9, 8), (8, 7), (7, 4), (4, 1)]
        for i in range(len(input_frames) - 1):
            if (input_frames[i], input_frames[i + 1]) in adjacent_pairs or (input_frames[i + 1], input_frames[i]) in adjacent_pairs:
                start_radius = self.inner_circle_radius + (i / len(input_frames) * (self.outer_circle_radius - self.inner_circle_radius))
                start_x, start_y = self.polar_to_cartesian(self.direction_to_angle[input_frames[i]], start_radius)
                end_radius = self.inner_circle_radius + (i + 1) / len(input_frames) * (self.outer_circle_radius - self.inner_circle_radius)
                end_x, end_y = self.polar_to_cartesian(self.direction_to_angle[input_frames[i + 1]], end_radius)
                start_x += center_x
                start_y += center_y
                end_x += center_x
                end_y += center_y

                # Calculate the middle point
                mid_radius = end_radius * 15/14 # 15/14 is a magic number that makes the arcs look good
                if (input_frames[i], input_frames[i + 1]) in [(3, 6), (6, 3)]: # Special case for when 360 degrees becomes 0 degrees
                    mid_x, mid_y = self.polar_to_cartesian(
                        (self.direction_to_angle[input_frames[i]] + self.direction_to_angle[input_frames[i + 1]] + 360) // 2, mid_radius
                    )
                else:
                    mid_x, mid_y = self.polar_to_cartesian(
                        (self.direction_to_angle[input_frames[i]] + self.direction_to_angle[input_frames[i + 1]]) // 2, mid_radius
                    )
                mid_x += center_x
                mid_y += center_y
                

                if len(self.arcs) <= arc_counter:
                    Color(0,1,0,1)
                    arc = Line(bezier=[start_x, start_y, mid_x, mid_y, end_x, end_y], width=2)
                    self.arcs.append(arc)
                    self.canvas.add(arc)
                else:
                    arc = self.arcs[arc_counter]
                arc.bezier = [start_x, start_y, mid_x, mid_y, end_x, end_y]
                arc_counter += 1

        for i in range(arc_counter, len(self.arcs)):
            self.arcs[i].points = [-self.width, 0, -self.width, 0]  # Move stale arcs offscreen.


    def update_state(self, input_frames):
        self.draw_dots(input_frames)
        self.draw_lines(input_frames)
        self.draw_arcs(input_frames)

        self.canvas.ask_update()
        
            


class ButtonImage(Image):
    def __init__(self, *args, opacity=1, source=IMAGE_SOURCE_BUTTON_UP, **kwargs):
        super().__init__(*args, **kwargs)
        self.source = source
        self.color[3] = opacity

    def update_state(self, pressed):
        if pressed:
            self.color[3] = 1
        else:
            self.color[3] = 0.6
