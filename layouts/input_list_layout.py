from kivy.core.image import Image as CoreImage
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, InstructionGroup, Rectangle
from kivy.graphics.texture import Texture
from kivy.metrics import dp, sp
from kivy.resources import resource_find
from kivy.uix.stencilview import StencilView
from PIL import Image

from images import get_standard_button_icon
from input_list import LIST_BUTTON_ORDER, draw_direction_glyph, input_key

ROW_HEIGHT = dp(42)
ICON_SIZE = dp(32)
COUNT_WIDTH = dp(52)
PANEL_WIDTH = dp(420)
PANEL_MARGIN = dp(24)
LINE_FRACTION = 0.3  # Height of the hit line, as a fraction of the view.
MAX_COUNT = 999

PANEL_COLOR = (0, 0, 0, 0.35)
LINE_COLOR = (1, 1, 1, 0.8)
MATCH_COLOR = (0.45, 0.9, 0.5, 1)
HISTORY_ALPHA = 0.4


def _texture_from_pil(image):
    texture = Texture.create(size=image.size, colorfmt="rgba")
    texture.blit_buffer(image.transpose(Image.FLIP_TOP_BOTTOM).tobytes(), colorfmt="rgba", bufferfmt="ubyte")
    return texture


class _InputGraphic:
    """Direction glyph followed by button icons, drawn from pooled rectangles."""

    def __init__(self, group):
        self.direction = Rectangle(size=(ICON_SIZE, ICON_SIZE))
        self.buttons = [Rectangle(size=(ICON_SIZE, ICON_SIZE)) for _ in LIST_BUTTON_ORDER]
        group.add(self.direction)
        for button in self.buttons:
            group.add(button)

    def set(self, x, y, key, direction_textures, button_textures):
        direction, pressed = key
        self.direction.texture = direction_textures[direction]
        self.direction.pos = (x, y)
        x += ICON_SIZE + dp(10)
        for i, rect in enumerate(self.buttons):
            if i < len(pressed):
                rect.texture = button_textures[pressed[i]]
                rect.pos = (x, y)
                rect.size = (ICON_SIZE, ICON_SIZE)
                x += ICON_SIZE + dp(4)
            else:
                rect.size = (0, 0)


class _Row:
    def __init__(self, canvas):
        self.group = InstructionGroup()
        self.highlight_color = Color(1, 1, 1, 0)
        self.highlight = Rectangle()
        self.underline_color = Color(1, 1, 1, 0)
        self.underline = Rectangle()
        self.content_color = Color(1, 1, 1, 0)
        self.count = Rectangle()
        for instruction in (self.highlight_color, self.highlight, self.underline_color, self.underline,
                            self.content_color, self.count):
            self.group.add(instruction)
        self.input = _InputGraphic(self.group)
        canvas.add(self.group)

    def hide(self):
        self.highlight_color.a = self.underline_color.a = self.content_color.a = 0


class InputListLayout(StencilView):
    """Training-mode style input list that scrolls down toward a hit line.

    Rows have a fixed height and each crosses the line exactly on the frame it starts, so short
    inputs stay readable (the scroll speeds up through them). The row being held straddles the line,
    and the player's live input is shown at the right end of the line, turning it green on a match.
    """

    def __init__(self, controller_type="XGamepad", button_icon_style="Alt", **kwargs):
        super().__init__(**kwargs)
        font = resource_find("data/fonts/Roboto-Bold.ttf")
        glyph_pixels = int(ICON_SIZE * 2)  # Render larger than shown so scaling stays crisp.
        self.direction_textures = {
            d: _texture_from_pil(draw_direction_glyph(d, glyph_pixels, font)) for d in range(1, 10)
        }
        self.button_textures = {
            name: CoreImage(get_standard_button_icon(controller_type, button_icon_style, name)).texture
            for name in LIST_BUTTON_ORDER
        }
        self.count_textures = {}
        self.rows = []
        with self.canvas:
            Color(*PANEL_COLOR)
            self.panel = Rectangle()
            self.line_color = Color(*LINE_COLOR)
            self.line = Rectangle()
            self.live_color = Color(1, 1, 1, 1)
            live_group = InstructionGroup()
        self.live = _InputGraphic(live_group)
        self.bind(pos=self._layout, size=self._layout)

    def _line_y(self):
        return self.y + self.height * LINE_FRACTION

    def _layout(self, *args):
        self.panel.pos = (self.x + PANEL_MARGIN, self.y)
        self.panel.size = (PANEL_WIDTH, self.height)
        self.line.pos = (self.x + PANEL_MARGIN, self._line_y() - dp(1))
        self.line.size = (PANEL_WIDTH + dp(16) + (ICON_SIZE + dp(10)) * 4, dp(2))

    def rows_needed(self):
        """How many rows the view can show (before, after) the hit line."""
        below = self.height * LINE_FRACTION
        return int(below // ROW_HEIGHT) + 2, int((self.height - below) // ROW_HEIGHT) + 2

    def _count_texture(self, frames):
        text = str(frames) if frames <= MAX_COUNT else f"{MAX_COUNT}+"
        texture = self.count_textures.get(text)
        if texture is None:
            label = CoreLabel(text=text, font_size=sp(20), bold=True)
            label.refresh()
            texture = self.count_textures[text] = label.texture
        return texture

    def update_state(self, live_state, rows, position, recording):
        current = int(position)
        live_key = input_key(live_state)
        target_key = next((key for index, _, key in rows if index == current), None)
        matched = not recording and live_key == target_key

        left = self.x + PANEL_MARGIN + dp(12)
        line_y = self._line_y()
        shown = 0
        for index, frames, key in rows:
            y = line_y + (index - position) * ROW_HEIGHT
            if y > self.top or y + ROW_HEIGHT < self.y:
                continue
            if shown == len(self.rows):
                self.rows.append(_Row(self.canvas))
            row = self.rows[shown]
            shown += 1

            is_current = index == current or (recording and index == current - 1)
            alpha = 1 if recording or index >= current else HISTORY_ALPHA
            row.content_color.a = alpha
            row.underline_color.a = 0.2 * alpha
            if is_current:
                row.highlight_color.rgba = (*MATCH_COLOR[:3], 0.18) if matched else (1, 1, 1, 0.1)
            else:
                row.highlight_color.a = 0
            row.highlight.pos = (self.x + PANEL_MARGIN, y)
            row.highlight.size = (PANEL_WIDTH, ROW_HEIGHT)
            row.underline.pos = (left, y)
            row.underline.size = (PANEL_WIDTH - dp(24), dp(1))

            count = self._count_texture(frames)
            row.count.texture = count
            row.count.size = count.size
            row.count.pos = (left + COUNT_WIDTH - count.width, y + (ROW_HEIGHT - count.height) / 2)
            row.input.set(left + COUNT_WIDTH + dp(10), y + (ROW_HEIGHT - ICON_SIZE) / 2, key,
                          self.direction_textures, self.button_textures)
        for row in self.rows[shown:]:
            row.hide()

        self.line_color.rgba = MATCH_COLOR if matched else LINE_COLOR
        self.live_color.a = 0 if recording else 1
        self.live.set(self.x + PANEL_MARGIN + PANEL_WIDTH + dp(16), line_y - ICON_SIZE / 2, live_key,
                      self.direction_textures, self.button_textures)
