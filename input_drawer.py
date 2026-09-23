from PIL import Image, ImageDraw
import math

from controller import get_cool_controller_pattern
from images import get_standard_button_icon


class DirectionalPromptDrawer:
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
    dot_radius = 4
    ring_width = 5
    line_width = 5

    def __init__(self):
        pass

    def polar_to_cartesian(self, angle, radius):
        dx = radius * math.cos(math.radians(angle))
        dy = radius * math.sin(math.radians(angle))
        return (dx, dy)

    def bezier_curve_points(self, n, p0, p1, p2):
        points = []
        for t in range(n + 1):
            t /= n
            x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t**2 * p2[0]
            y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t**2 * p2[1]
            points.append((x, y))
        return points

    def draw_dots(self, draw, input_frames):
        i = 0
        for i in range(len(input_frames)):
            if input_frames[i] != 5:
                # Skip consecutive dots
                if (
                    i > 0
                    and input_frames[i] == input_frames[i - 1]
                ):
                    if (
                        i < len(input_frames) - 1
                        and input_frames[i]
                        == input_frames[i + 1]
                    ):
                        continue
                # Draw a dot
                dx, dy = self.polar_to_cartesian(
                    self.direction_to_angle[input_frames[i]],
                    self.inner_circle_radius
                    + (
                        i
                        / len(input_frames)
                        * (self.outer_circle_radius - self.inner_circle_radius)
                    ),
                )
                x = self.x + self.width / 2 + dx
                y = self.y + self.width / 2 - dy
                draw.ellipse(
                    [
                        (x - self.dot_radius, y - self.dot_radius),
                        (x + self.dot_radius, y + self.dot_radius),
                    ],
                    outline="white",
                    width=self.dot_radius * 2,
                )

    def draw_lines(self, draw, input_frames):
        i = 0
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
                        self.direction_to_angle[input_frames[start]],
                        self.inner_circle_radius
                        + (
                            start
                            / len(input_frames)
                            * (self.outer_circle_radius - self.inner_circle_radius)
                        ),
                    )
                    start_x = self.x + self.width / 2 + dx
                    start_y = self.y + self.width / 2 - dy
                    dx, dy = self.polar_to_cartesian(
                        self.direction_to_angle[input_frames[end]],
                        self.inner_circle_radius
                        + (
                            end
                            / len(input_frames)
                            * (self.outer_circle_radius - self.inner_circle_radius)
                        ),
                    )
                    end_x = self.x + self.width / 2 + dx
                    end_y = self.y + self.width / 2 - dy
                    draw.line(
                        [start_x, start_y, end_x, end_y],
                        width=self.line_width,
                        fill="white",
                    )
            else:
                start = None
            i += 1

    def draw_arcs(self, draw, input_frames):
        adjacent_pairs = [
            (1, 2),
            (2, 3),
            (3, 6),
            (6, 9),
            (9, 8),
            (8, 7),
            (7, 4),
            (4, 1),
        ]
        for i in range(len(input_frames) - 1):
            if (input_frames[i], input_frames[i + 1]) in adjacent_pairs or (
                input_frames[i + 1],
                input_frames[i],
            ) in adjacent_pairs:
                start_radius = self.inner_circle_radius + (
                    i
                    / len(input_frames)
                    * (self.outer_circle_radius - self.inner_circle_radius)
                )
                start_dx, start_dy = self.polar_to_cartesian(
                    self.direction_to_angle[input_frames[i]], start_radius
                )
                end_radius = self.inner_circle_radius + (i + 1) / len(input_frames) * (
                    self.outer_circle_radius - self.inner_circle_radius
                )
                end_dx, end_dy = self.polar_to_cartesian(
                    self.direction_to_angle[input_frames[i + 1]], end_radius
                )
                start_x = self.center_x + start_dx
                start_y = self.center_y - start_dy
                end_x = self.center_x + end_dx
                end_y = self.center_y - end_dy

                # Calculate the middle point
                mid_radius = (start_radius + end_radius) / 2
                mid_radius = (
                    mid_radius * 15 / 14
                )  # 15/14 is a magic number that makes the arcs look good
                if (input_frames[i], input_frames[i + 1]) in [
                    (3, 6),
                    (6, 3),
                ]:  # Special case for when 360 degrees becomes 0 degrees
                    mid_dx, mid_dy = self.polar_to_cartesian(
                        (
                            self.direction_to_angle[input_frames[i]]
                            + self.direction_to_angle[input_frames[i + 1]]
                            + 360
                        )
                        // 2,
                        mid_radius,
                    )
                else:
                    mid_dx, mid_dy = self.polar_to_cartesian(
                        (
                            self.direction_to_angle[input_frames[i]]
                            + self.direction_to_angle[input_frames[i + 1]]
                        )
                        // 2,
                        mid_radius,
                    )
                mid_x = self.center_x + mid_dx
                mid_y = self.center_y - mid_dy

                bezier_points = self.bezier_curve_points(
                    20, (start_x, start_y), (mid_x, mid_y), (end_x, end_y)
                )
                draw.line(
                    bezier_points, fill="white", width=self.line_width, joint="curve"
                )

    def draw(self, draw: ImageDraw, input_frames, x, y, width, height):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.center_x = self.width // 2 + self.x
        self.center_y = self.height // 2 + self.y
        self.inner_circle_radius = self.width * 0.09
        self.outer_circle_radius = self.width / 2

        # Draw the inner circle
        draw.circle(
            (self.center_x, self.center_y),
            self.inner_circle_radius,
            outline="white",
            width=self.ring_width,
        )

        # Draw the outer circle
        draw.circle(
            (self.center_x, self.center_y),
            self.outer_circle_radius,
            outline="white",
            width=self.ring_width,
        )

        self.draw_lines(draw, input_frames)
        self.draw_arcs(draw, input_frames)
        self.draw_dots(draw, input_frames)


class ButtonDrawer:
    """Draws one button column. The icon is loaded and scaled once, not per frame."""

    def __init__(self, button_source, width):
        try:
            image = Image.open(button_source).convert("RGBA")
        except IOError:
            print(f"Unable to load image at {button_source}")
            image = Image.new("RGBA", (width, width), (255, 255, 255, 255))
        scale_ratio = width / image.width
        self.button_image = image.resize((width, max(1, int(image.height * scale_ratio))))
        self.transparent_button = self.button_image.copy()
        self.transparent_button.putalpha(self.button_image.getchannel("A").point(lambda p: p // 2))

    def draw(self, image, input_frames, x, y, height):
        new_height = self.button_image.height
        # Draw the frames of input data
        for i in range(len(input_frames) - 1, -1, -1):
            if input_frames[i]:
                button_y = int(y + height - new_height - (height - new_height) * (i / len(input_frames)))
                image.paste(self.button_image, (int(x), button_y), mask=self.button_image)

        # Draw the button frames at the bottom of the screen
        image.paste(self.transparent_button, (int(x), int(y + height - new_height)), mask=self.transparent_button)


class InputDrawer:
    button_names = ["A", "X", "B", "Y", "RT", "RB", "LT", "LB"]

    def __init__(self, width=1600, height=800, controller_type="XGamepad", button_icon_style="Alt"):
        self.width = width
        self.height = height
        self.directional_drawer = DirectionalPromptDrawer()
        self.button_drawers = [
            ButtonDrawer(get_standard_button_icon(controller_type, button_icon_style, name), width * 7 // 100)
            for name in self.button_names
        ]

    def draw(self, inputs):
        image = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        self.directional_drawer.draw(
            draw, [frame["direction"] for frame in inputs], 0, 0, self.width // 2, self.width // 2
        )
        for i, (name, drawer) in enumerate(zip(self.button_names, self.button_drawers)):
            button_x = self.width * (0.5 + i * (0.48 / 8))
            drawer.draw(image, [frame[name] for frame in inputs], button_x, 0, self.height)
        return image


if __name__ == "__main__":
    drawer = InputDrawer()
    inputs = get_cool_controller_pattern()
    image = drawer.draw(inputs[0:120])
    image.show()
