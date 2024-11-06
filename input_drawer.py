from PIL import Image, ImageDraw
import math

from controller import get_cool_controller_pattern
from images import IMAGE_SOURCE_BUTTON_UP, get_standard_button_icon


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
    dot_radius = 2
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
                    outline="blue",
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
                        fill="green",
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
                    bezier_points, fill="green", width=self.line_width, joint="curve"
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
            outline="black",
            width=self.ring_width,
        )

        # Draw the outer circle
        draw.circle(
            (self.center_x, self.center_y),
            self.outer_circle_radius,
            outline="black",
            width=self.ring_width,
        )

        self.draw_lines(draw, input_frames)
        self.draw_arcs(draw, input_frames)
        self.draw_dots(draw, input_frames)


class ButtonDrawer():

    def load_image(self, button_source):
        try:
            self.button_image = Image.open(button_source)
            self.transparent_button = Image.open(button_source)
            alpha = self.transparent_button.split()[3]
            alpha = alpha.point(lambda p: p // 2)
            self.transparent_button.putalpha(alpha)
        except IOError:
            print(f"Unable to load image at {button_source}")


    def draw(self, image, input_frames, x, y, width, height):
        
        button_width, button_height = self.button_image.size
        scale_ratio = width / button_width
        new_height = int(button_height * scale_ratio)
        resized_button = self.button_image.resize((width, new_height))
        # Draw the frames of input data
        if input_frames:
            for i in range(len(input_frames)-1, -1, -1):
                frame_state = input_frames[i]
                if frame_state:
                    button_x = int(x)
                    button_y = int(y + height - new_height - (height-new_height) * (i/len(input_frames)))
                    resized_button = self.button_image.resize((width, new_height))
                    # draw.bitmap((button_x, button_y), resized_button)
                    image.paste(resized_button, (button_x, button_y), mask=resized_button)

        # Draw the button frames at the bottom of the screen
        resized_button = self.transparent_button.resize((width, new_height))
        image.paste(resized_button, (int(x), int(y + height - new_height)), mask=resized_button)


class InputDrawer():
    def draw(self, inputs, image=None, x=0, y=0, width=1600, height=800):
        if not image:
            image = Image.new("RGBA", (width, height), "white")
            image.putalpha(0)
        draw = ImageDraw.Draw(image)

        dpd = DirectionalPromptDrawer()
        dpd.draw(draw, [frame['direction'] for frame in inputs], x, y, width//2, width//2)

        button_drawer = ButtonDrawer()
        button_names = ["A", "X", "B", "Y", "RT", "RB", "LT", "LB"]
        controller_type="XGamepad"
        button_icon_style='Alt'
        for i in range(len(button_names)):
            button_drawer.load_image(get_standard_button_icon(controller_type, button_icon_style, button_names[i]))
            button_x = width * (0.5 + i * (0.48/8))
            button_y = y
            button_drawer.draw(image, [frame[button_names[i]] for frame in inputs], button_x, button_y, width * 7 // 100, height)
        return image


if __name__ == "__main__":
    drawer = InputDrawer()
    inputs = get_cool_controller_pattern()
    image = drawer.draw(inputs[0:120])
    image.show()


