from kivy.core.image import Image as CoreImage
from kivy.core.text import Label as CoreLabel
from kivy.core.window import Window
from kivy.graphics import Color, InstructionGroup, Rectangle
from kivy.graphics.texture import Texture
from kivy.metrics import dp, sp
from kivy.resources import resource_find
from kivy.uix.stencilview import StencilView
from PIL import Image

from images import get_standard_button_icon
from input_list import LIST_BUTTON_ORDER, MAX_COUNT, draw_direction_glyph, input_key

ICON_SIZE = dp(28)
MIN_ICON_SIZE = dp(16)
COUNT_WIDTH = dp(44)
COLUMN_WIDTH = dp(300)
METER_WIDTH = dp(18)  # Frame meter: one block per frame, left of the target column.
METER_GAP = dp(10)
STRIP_WIDTH = dp(8)  # Per-frame match indicator between the two columns.
COLUMN_GAP = dp(20)
MARGIN = dp(24)
HEADER_HEIGHT = dp(28)
LINE_FRACTION = 0.3  # Height of the hit line, as a fraction of the view.

DEFAULT_PX_PER_FRAME = dp(12)
MIN_PX_PER_FRAME = dp(3)
MAX_PX_PER_FRAME = dp(40)
WHEEL_PIXELS = dp(48)  # How far one wheel notch scrolls.

PANEL_COLOR = (0, 0, 0, 0.35)
HEADER_COLOR = (0.08, 0.08, 0.1, 1)
LINE_COLOR = (1, 1, 1, 0.8)
MATCH_COLOR = (0.45, 0.9, 0.5)
MISS_COLOR = (1, 0.42, 0.42)
TARGET_BOX_COLOR = (1, 1, 1)
ATTEMPT_BOX_COLOR = (0.45, 0.65, 1)
HISTORY_ALPHA = 0.45
METER_NEUTRAL_COLOR = (0.38, 0.38, 0.42)
METER_DIRECTION_COLOR = (0.3, 0.55, 0.95)
METER_BUTTON_COLOR = (1.0, 0.68, 0.2)


def _texture_from_pil(image):
    texture = Texture.create(size=image.size, colorfmt="rgba")
    texture.blit_buffer(image.transpose(Image.FLIP_TOP_BOTTOM).tobytes(), colorfmt="rgba", bufferfmt="ubyte")
    return texture


def _text_texture(text, font_size, bold=True):
    label = CoreLabel(text=text, font_size=font_size, bold=bold)
    label.refresh()
    return label.texture


class _InputLabel:
    """Frame count, direction glyph and button icons, drawn from pooled rectangles at any size."""

    def __init__(self, group, with_count=True):
        self.count = Rectangle() if with_count else None
        self.direction = Rectangle()
        self.buttons = [Rectangle() for _ in LIST_BUTTON_ORDER]
        for rect in ([self.count] if with_count else []) + [self.direction] + self.buttons:
            group.add(rect)

    def set(self, x, y, icon, key, textures, count_texture=None):
        direction, pressed = key
        if self.count is not None:
            scale = icon / ICON_SIZE
            width, height = count_texture.width * scale, count_texture.height * scale
            self.count.texture = count_texture
            self.count.size = (width, height)
            self.count.pos = (x + COUNT_WIDTH * scale - width, y + (icon - height) / 2)
            x += (COUNT_WIDTH + dp(8)) * scale
        self.direction.texture = textures.directions[direction]
        self.direction.pos = (x, y)
        self.direction.size = (icon, icon)
        x += icon * 1.3
        for i, rect in enumerate(self.buttons):
            if i < len(pressed):
                rect.texture = textures.buttons[pressed[i]]
                rect.pos = (x, y)
                rect.size = (icon, icon)
                x += icon * 1.1
            else:
                rect.size = (0, 0)


class _Box:
    """One run of input: a box as tall as the run lasts, with its label."""

    def __init__(self, layer):
        self.group = InstructionGroup()
        self.fill_color = Color(1, 1, 1, 0)
        self.fill = Rectangle()
        self.edge_color = Color(1, 1, 1, 0)
        self.edge = Rectangle()  # Marks the frame the input starts on.
        self.content_color = Color(1, 1, 1, 0)
        for instruction in (self.fill_color, self.fill, self.edge_color, self.edge, self.content_color):
            self.group.add(instruction)
        self.label = _InputLabel(self.group)
        layer.add(self.group)

    def hide(self):
        self.fill_color.a = self.edge_color.a = self.content_color.a = 0


class _Pool:
    def __init__(self, layer, factory):
        self.layer, self.factory, self.items, self.used = layer, factory, [], 0

    def next(self):
        if self.used == len(self.items):
            self.items.append(self.factory(self.layer))
        self.used += 1
        return self.items[self.used - 1]

    def finish(self, hide):
        for item in self.items[self.used:]:
            hide(item)
        self.used = 0


class _Textures:
    def __init__(self, controller_type, button_icon_style):
        font = resource_find("data/fonts/Roboto-Bold.ttf")
        glyph_pixels = int(ICON_SIZE * 2)  # Render larger than shown so scaling stays crisp.
        self.directions = {d: _texture_from_pil(draw_direction_glyph(d, glyph_pixels, font)) for d in range(1, 10)}
        self.buttons = {
            name: CoreImage(get_standard_button_icon(controller_type, button_icon_style, name)).texture
            for name in LIST_BUTTON_ORDER
        }
        self.counts = {}

    def count(self, frames):
        text = str(frames) if frames <= MAX_COUNT else f"{MAX_COUNT}+"
        if text not in self.counts:
            self.counts[text] = _text_texture(text, sp(18))
        return self.counts[text]


class InputListLayout(StencilView):
    """Training-mode style input list that scrolls down onto a hit line at a constant speed.

    Each run of input is a box as tall as it's held, so its bottom edge reaches the line on the
    frame it should be pressed and its top edge when it should be released. The target track is on
    the left and the player's attempt on the right, with a strip between them marking each frame
    green (matched) or red (missed). A frame meter on the far left shows the target as one block per
    frame. Mouse wheel or drag scrubs; Ctrl + wheel zooms.
    """

    def __init__(self, controller_type="XGamepad", button_icon_style="Alt", **kwargs):
        super().__init__(**kwargs)
        self.textures = _Textures(controller_type, button_icon_style)
        self.px_per_frame = DEFAULT_PX_PER_FRAME
        self.on_scrub = None  # Called with a frame delta when the user scrolls or drags.
        self.on_zoom = None  # Called with the new pixels-per-frame.
        self._drag_frames = 0.0

        with self.canvas:
            Color(*PANEL_COLOR)
            self.panels = [Rectangle(), Rectangle(), Rectangle()]  # Target, You, frame meter.
            self.box_layer = InstructionGroup()
            self.meter_layer = InstructionGroup()
            self.meter_divider_layer = InstructionGroup()
            self.strip_layer = InstructionGroup()
        with self.canvas.after:
            self.line_color = Color(*LINE_COLOR)
            self.line = Rectangle()
            self.live_color = Color(1, 1, 1, 1)
            live_group = InstructionGroup()
            Color(*HEADER_COLOR)
            self.header = Rectangle()
            Color(1, 1, 1, 0.85)
            self.header_labels = [Rectangle(texture=_text_texture(text, sp(14))) for text in ("Target", "You")]
        self.live = _InputLabel(live_group, with_count=False)
        self.target_boxes = _Pool(self.box_layer, _Box)
        self.attempt_boxes = _Pool(self.box_layer, _Box)
        self.strips = _Pool(self.strip_layer, self._make_strip)
        self.meter_blocks = _Pool(self.meter_layer, self._make_strip)
        self.meter_dividers = _Pool(self.meter_divider_layer, self._make_strip)
        self.bind(pos=self._layout, size=self._layout)

    @staticmethod
    def _make_strip(layer):
        color, rect = Color(1, 1, 1, 0), Rectangle()
        layer.add(color)
        layer.add(rect)
        return color, rect

    # ---- Geometry ----------------------------------------------------------------------------

    def _line_y(self):
        return self.y + self.height * LINE_FRACTION

    def _meter_x(self):
        return self.x + MARGIN

    def _column_x(self, column):
        return self._meter_x() + METER_WIDTH + METER_GAP + column * (COLUMN_WIDTH + COLUMN_GAP)

    def _layout(self, *args):
        for column, panel in enumerate(self.panels[:2]):
            panel.pos = (self._column_x(column), self.y)
            panel.size = (COLUMN_WIDTH, self.height)
        self.panels[2].pos = (self._meter_x(), self.y)
        self.panels[2].size = (METER_WIDTH, self.height)
        width = METER_WIDTH + METER_GAP + 2 * COLUMN_WIDTH + COLUMN_GAP
        self.line.pos = (self._meter_x(), self._line_y() - dp(1))
        self.line.size = (width + dp(16) + ICON_SIZE * 5, dp(2))
        self.header.pos = (self._meter_x(), self.top - HEADER_HEIGHT)
        self.header.size = (width, HEADER_HEIGHT)
        for column, label in enumerate(self.header_labels):
            label.size = label.texture.size
            label.pos = (self._column_x(column) + dp(12), self.top - (HEADER_HEIGHT + label.texture.height) / 2)

    def frames_needed(self):
        """How many frames fit (before, after) the hit line."""
        below = self.height * LINE_FRACTION
        return int(below / self.px_per_frame) + 2, int((self.height - below) / self.px_per_frame) + 2

    def set_zoom(self, px_per_frame):
        self.px_per_frame = max(MIN_PX_PER_FRAME, min(MAX_PX_PER_FRAME, px_per_frame))

    # ---- Scrolling ---------------------------------------------------------------------------

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        if touch.is_mouse_scrolling:
            # Kivy reports wheel-away-from-you as "scrolldown"; that should reveal what's above (later).
            direction = 1 if touch.button == "scrolldown" else -1 if touch.button == "scrollup" else 0
            if "ctrl" in Window.modifiers:
                self.set_zoom(self.px_per_frame * (1.25 if direction > 0 else 0.8))
                if self.on_zoom:
                    self.on_zoom(self.px_per_frame)
            elif direction and self.on_scrub:
                self.on_scrub(direction * max(1, round(WHEEL_PIXELS / self.px_per_frame)))
            return True
        touch.grab(self)
        self._drag_frames = 0.0
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return super().on_touch_move(touch)
        # Dragging the list down brings later frames onto the line, like pulling a scroll.
        self._drag_frames -= touch.dy / self.px_per_frame
        whole = int(self._drag_frames)
        if whole and self.on_scrub:
            self.on_scrub(whole)
            self._drag_frames -= whole
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            return True
        return super().on_touch_up(touch)

    # ---- Drawing -----------------------------------------------------------------------------

    def _draw_runs(self, pool, runs, snapshot, column, color, dim_history):
        line_y = self._line_y()
        left = self._column_x(column)
        for start, length, key in runs:
            y0 = line_y + (start - snapshot.frame) * self.px_per_frame
            y1 = y0 + length * self.px_per_frame
            if y1 < self.y or y0 > self.top:
                continue
            box = pool.next()
            neutral = key == (5, ())
            past = y1 <= line_y
            active = y0 <= line_y < y1
            alpha = HISTORY_ALPHA if past and dim_history else 1
            box.fill_color.rgba = (*color, (0.05 if neutral else 0.16 if not active else 0.28) * alpha)
            box.fill.pos = (left, y0)
            box.fill.size = (COLUMN_WIDTH, y1 - y0)
            box.edge_color.rgba = (*color, 0.6 * alpha)
            box.edge.pos = (left, y0)
            box.edge.size = (COLUMN_WIDTH, dp(1))
            box.content_color.a = alpha

            # Short runs get a smaller label, anchored to the edge where the input starts. A held run
            # keeps its label just above the line, and a long run's label stays in view.
            icon = max(MIN_ICON_SIZE, min(ICON_SIZE, y1 - y0 - dp(4)))
            label_y = y0 + dp(2) if y1 - y0 >= icon + dp(4) else y0
            label_y = max(label_y, min(self.y + dp(2), y1 - icon - dp(2)))
            if active:
                label_y = max(label_y, min(line_y + dp(2), y1 - icon - dp(2)))
            box.label.set(left + dp(10), label_y, icon, key, self.textures, self.textures.count(length))
        pool.finish(_Box.hide)

    def _draw_matches(self, runs, snapshot):
        line_y = self._line_y()
        x = self._column_x(0) + COLUMN_WIDTH + (COLUMN_GAP - STRIP_WIDTH) / 2
        for start, length, matched in runs:
            y0 = line_y + (start - snapshot.frame) * self.px_per_frame
            color, rect = self.strips.next()
            color.rgba = (*(MATCH_COLOR if matched else MISS_COLOR), 0.9)
            rect.pos = (x, y0)
            rect.size = (STRIP_WIDTH, length * self.px_per_frame)
        self.strips.finish(lambda strip: setattr(strip[0], "a", 0))

    def _draw_meter(self, runs, snapshot):
        """One block per target frame, coloured by input type, with a divider where the input changes."""
        line_y = self._line_y()
        ppf = self.px_per_frame
        gap = dp(1) if ppf >= dp(4) else 0
        x = self._meter_x()
        first_visible = snapshot.frame - int((line_y - self.y) / ppf) - 1
        last_visible = snapshot.frame + int((self.top - line_y) / ppf) + 1
        for start, length, key in runs:
            direction, buttons = key
            color = METER_BUTTON_COLOR if buttons else METER_NEUTRAL_COLOR if direction == 5 else METER_DIRECTION_COLOR
            for frame in range(max(start, first_visible), min(start + length, last_visible + 1)):
                y = line_y + (frame - snapshot.frame) * ppf
                past = frame < snapshot.frame and not snapshot.recording
                block_color, block = self.meter_blocks.next()
                block_color.rgba = (*color, HISTORY_ALPHA if past else 0.95)
                block.pos = (x, y + gap)
                block.size = (METER_WIDTH, ppf - gap)
            if first_visible <= start <= last_visible:
                divider_color, divider = self.meter_dividers.next()
                divider_color.rgba = (1, 1, 1, 0.9)
                divider.pos = (x - dp(3), line_y + (start - snapshot.frame) * ppf - dp(1))
                divider.size = (METER_WIDTH + dp(6), dp(2))
        hide = lambda item: setattr(item[0], "a", 0)
        self.meter_blocks.finish(hide)
        self.meter_dividers.finish(hide)

    def update_state(self, snapshot):
        self._draw_meter(snapshot.target_runs, snapshot)
        self._draw_runs(self.target_boxes, snapshot.target_runs, snapshot, 0, TARGET_BOX_COLOR,
                        dim_history=not snapshot.recording)
        self._draw_runs(self.attempt_boxes, snapshot.attempt_runs, snapshot, 1, ATTEMPT_BOX_COLOR, dim_history=False)
        self._draw_matches(snapshot.match_runs, snapshot)

        # The player's live input sits at the end of the line, which turns green when it matches.
        live_key = input_key(snapshot.live_state)
        target_key = next((key for start, length, key in snapshot.target_runs
                           if start <= snapshot.frame < start + length), None)
        matched = not snapshot.recording and live_key == target_key
        self.line_color.rgba = (*MATCH_COLOR, 1) if matched else LINE_COLOR
        self.live_color.a = 0 if snapshot.recording else 1
        self.live.set(self._column_x(2) - COLUMN_GAP + dp(16), self._line_y() - ICON_SIZE / 2, ICON_SIZE,
                      live_key, self.textures)
