"""Prompts falling down columns toward the bottom, as in the arrow lanes and the ring's buttons:
one icon per input with a thin line behind it while it's held, kept behind everything drawn over
it (Knockout), and ButtonColumn, a button with its presses falling toward it.
"""
from kivy.graphics import Color, InstructionGroup, Rectangle
from kivy.uix.widget import Widget
from PIL import Image as PILImage

import theme
from layouts.drawing import OFFSCREEN, silhouette_of, texture_of


BUTTON_PROMPT_OPACITY = 1.0

IDLE_TINT = (0.5, 0.5, 0.54, 1)  # A button not pressed: dimmed but solid, so it doesn't read as disabled.

HOLD_TAIL_COLOR = (0.62, 0.62, 0.65, 1)

HOLD_TAIL_WIDTH = 0.12  # Of the icon's width: a thin line, like a guitar game's sustain.


class Prompt:
    """A falling prompt's art, from a PIL image: its texture and its silhouette (see Knockout)."""

    def __init__(self, image):
        image = image.convert("RGBA")
        self.texture = texture_of(image)
        self.silhouette = silhouette_of(image)


_knockout_colors = []  # Every Knockout's colour, to follow the window's background.


def set_background(rgb):
    """The window's background changed (e.g. to the see-through overlay's): knockouts follow it."""
    for color in _knockout_colors:
        color.rgb = rgb


class Knockout:
    """Keeps hold tails behind everything: each thing drawn over the tails gets a rectangle of its
    silhouette in the background colour, in group, which goes between the tails and the things."""

    def __init__(self):
        self.group = InstructionGroup()
        color = Color(*theme.BACKGROUND, 1)
        _knockout_colors.append(color)
        self.group.add(color)

    def add(self, silhouette):
        """A rectangle for one covering thing; keep its pos and size in step with the thing's."""
        rect = Rectangle(texture=silhouette)
        self.group.add(rect)
        return rect


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
    starts and a thin line behind it as long as it's held, like a guitar game's sustained notes.
    (Drawing every frame of a hold instead piles up a stack of icons.)"""

    def __init__(self, knockout):
        self.knockout = knockout  # Hides the lines under the icons.
        self.tail_group, self.head_group = InstructionGroup(), InstructionGroup()
        self.tails, self.heads, self.knocks = [], [], []
        self.used = 0

    def _run(self, index):
        if index == len(self.heads):
            self.tails.append(Rectangle())
            self.heads.append(Rectangle())
            self.knocks.append(self.knockout.add(None))
            self.tail_group.add(self.tails[-1])
            self.head_group.add(self.heads[-1])
        return self.tails[index], self.heads[index], self.knocks[index]

    def draw(self, runs, x, y, icon, travel, count, offset, prompt_for):
        """runs from runs_of(); icon is the (width, height) of a prompt; travel the height it falls;
        prompt_for(value) the Prompt for a run's value."""
        width, height = icon
        place = lambda index: y + travel * max(0.0, index - offset) / count
        line = width * HOLD_TAIL_WIDTH
        for n, (first, last, value) in enumerate(runs):
            tail, head, knock = self._run(n)
            prompt = prompt_for(value)
            head.texture, knock.texture = prompt.texture, prompt.silhouette
            start, finish = place(first), place(last)
            head.pos = knock.pos = (x, start)
            head.size = knock.size = icon
            # From the icon's middle (it covers the start, so the line joins it) to the middle of
            # where the hold ends.
            tail.pos = (x + (width - line) / 2, start + height / 2)
            tail.size = (line, max(0.0, finish - start))
        for n in range(len(runs), self.used):
            self.tails[n].pos = self.heads[n].pos = self.knocks[n].pos = OFFSCREEN
        self.used = len(runs)


class ButtonColumn(Widget):
    """A button at the bottom of a column, with upcoming presses falling down toward it.

    A press falls as the button's icon with a tail as long as it's held (see FallingRuns).
    """

    def __init__(self, button_source, **kwargs):
        super().__init__(**kwargs)
        self.prompt = Prompt(PILImage.open(button_source))
        self.texture = self.prompt.texture
        knockout = Knockout()
        self.falling = FallingRuns(knockout)
        # Tails first, then everything else over them with the tails knocked out underneath.
        self.canvas.add(Color(*HOLD_TAIL_COLOR))
        self.canvas.add(self.falling.tail_group)
        self.button_knock = knockout.add(self.prompt.silhouette)
        self.canvas.add(knockout.group)
        with self.canvas:
            self.button_color = Color(*IDLE_TINT)
            self.button = Rectangle(texture=self.texture)
        self.canvas.add(Color(1, 1, 1, BUTTON_PROMPT_OPACITY))
        self.canvas.add(self.falling.head_group)
        self.bind(pos=self._layout_button, size=self._layout_button)

    def _icon_size(self):
        return self.width, self.width * self.texture.height / self.texture.width

    def _layout_button(self, *args):
        self.button.pos = self.button_knock.pos = self.pos
        self.button.size = self.button_knock.size = self._icon_size()

    def update_state(self, pressed, input_frames, offset=0.0):
        # Pressed: lit, and green while the recording wants it pressed now (holding it right).
        wanted = bool(input_frames) and bool(input_frames[0])
        self.button_color.rgba = ((0.6, 1, 0.65, 1) if wanted else (1, 1, 1, 1)) if pressed else IDLE_TINT
        icon_size = self._icon_size()
        if not input_frames:
            self.falling.draw([], self.x, self.y, icon_size, 0, 1, offset, None)
            return
        self.falling.draw(runs_of([bool(state) for state in input_frames]), self.x, self.y, icon_size,
                          self.height - icon_size[1], len(input_frames), offset, lambda value: self.prompt)
