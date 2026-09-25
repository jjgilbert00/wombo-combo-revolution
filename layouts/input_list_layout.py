import ctypes
import sys

from kivy.core.image import Image as CoreImage
from kivy.core.text import Label as CoreLabel
from kivy.core.window import Window
from kivy.graphics import Color, InstructionGroup, Line, Rectangle
from kivy.graphics.texture import Texture
from kivy.metrics import dp, sp
from kivy.resources import resource_find
from kivy.uix.stencilview import StencilView
from PIL import Image

from images import get_standard_button_icon
from input_list import LIST_BUTTON_ORDER, draw_direction_glyph, input_key

ICON_SIZE = dp(26)
# A label is one icon wide: frame count on top, then the direction, then pressed buttons in a column.
LABEL_PADDING = dp(2)
LABEL_WIDTH = ICON_SIZE + 2 * LABEL_PADDING
COUNT_FONT_SIZE = sp(14)
DISPLAY_COUNT_LIMIT = 99  # Longer holds show "99+", like training-mode input displays.
LANE_BUTTON_ROWS = 3  # Lanes are tall enough for this many buttons; more overflow the lane.
MARGIN = dp(24)
GUTTER_WIDTH = dp(72)  # Lane names, left of the track.
METER_HEIGHT = dp(18)  # Frame meter: one block per target frame, above the target lane.
LANE_HEIGHT = dp(4) + dp(18) + (ICON_SIZE + dp(2)) * (1 + LANE_BUTTON_ROWS) + dp(4)
STRIP_HEIGHT = dp(8)  # Per-frame match indicator between the two lanes.
LANE_GAP = dp(8)
LINE_FRACTION = 0.25  # Position of the hit line, as a fraction of the track width.

# By default one frame is exactly one label wide, so every input has room for its label. Zooming
# out shows more of the track; boxes then too narrow for a label just show the box.
DEFAULT_PX_PER_FRAME = LABEL_WIDTH
MIN_PX_PER_FRAME = dp(4)
MAX_PX_PER_FRAME = dp(64)

PANEL_COLOR = (0, 0, 0, 0.35)
GUTTER_COLOR = (0.08, 0.08, 0.1, 1)
LINE_COLOR = (1, 1, 1, 0.8)
MATCH_COLOR = (0.45, 0.9, 0.5)
MISS_COLOR = (1, 0.42, 0.42)
TARGET_BOX_COLOR = (1, 1, 1)
ATTEMPT_BOX_COLOR = (0.45, 0.65, 1)
HISTORY_ALPHA = 0.45
METER_NEUTRAL_COLOR = (0.38, 0.38, 0.42)
METER_DIRECTION_COLOR = (0.3, 0.55, 0.95)
METER_BUTTON_COLOR = (1.0, 0.68, 0.2)
NOTE_COLOR = (1.0, 0.85, 0.35)
TOAST_COLOR = (0.12, 0.12, 0.15)
TOAST_MAX_WIDTH = dp(260)
TOAST_PADDING = dp(8)
TOAST_ROWS = 3  # Overlapping notes stack into this many rows; any more are skipped.
BRACE_HEIGHT = dp(12)
SELECTION_COLOR = (0.4, 0.65, 1.0)
CLICK_SLOP = dp(4)  # A press that moves less than this is a click, not a drag.


_VIRTUAL_KEYS = {"shift": 0x10, "ctrl": 0x11}


def _modifier_held(name):
    """Whether Shift/Ctrl is down right now. Asks Windows directly: Kivy's Window.modifiers isn't
    reliably updated for mouse events, so it can miss a held key."""
    if sys.platform == "win32":
        return bool(ctypes.windll.user32.GetKeyState(_VIRTUAL_KEYS[name]) & 0x8000)
    return name in Window.modifiers


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

    def set_stacked(self, x, top, key, textures, count_texture):
        """Count on top, direction glyph under it, then button icons in a column, all one icon wide."""
        direction, pressed = key
        self.count.texture = count_texture
        self.count.size = count_texture.size
        self.count.pos = (x + (ICON_SIZE - count_texture.width) / 2, top - dp(18) + (dp(18) - count_texture.height) / 2)
        y = top - dp(18) - dp(2) - ICON_SIZE
        self.direction.texture = textures.directions[direction]
        self.direction.pos = (x, y)
        self.direction.size = (ICON_SIZE, ICON_SIZE)
        for i, rect in enumerate(self.buttons):
            if i < len(pressed):
                rect.texture = textures.buttons[pressed[i]]
                rect.pos = (x, y - (i + 1) * (ICON_SIZE + dp(2)))
                rect.size = (ICON_SIZE, ICON_SIZE)
            else:
                rect.size = (0, 0)

    def set_row(self, x, y, icon, key, textures):
        """Direction glyph followed by button icons in a single row."""
        direction, pressed = key
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
    """One run of input: a box as wide as the run lasts, with its label."""

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


class _NoteGraphic:
    """A note: a bar over its frames above the meter, a brace under the display spanning them, and a
    toast with the text hanging from the brace's tip."""

    def __init__(self, layer):
        self.group = InstructionGroup()
        self.tint_color = Color(*NOTE_COLOR, 0)
        self.tint = Rectangle()
        self.brace_color = Color(*NOTE_COLOR, 0)
        self.brace = Line(width=dp(1.3))
        self.connector = Line(width=dp(1.3))  # From the brace's tip down to the toast.
        self.toast_color = Color(*TOAST_COLOR, 0)
        self.toast = Rectangle()
        self.accent_color = Color(*NOTE_COLOR, 0)
        self.accent = Rectangle()
        self.text_color = Color(1, 1, 1, 0)
        self.text = Rectangle()
        for instruction in (self.tint_color, self.tint, self.brace_color, self.brace, self.connector,
                            self.toast_color, self.toast,
                            self.accent_color, self.accent, self.text_color, self.text):
            self.group.add(instruction)
        layer.add(self.group)

    def hide(self):
        for color in (self.tint_color, self.brace_color, self.toast_color, self.accent_color, self.text_color):
            color.a = 0


def _quadratic(p0, p1, p2, steps=6):
    points = []
    for step in range(1, steps + 1):
        t = step / steps
        points += [(1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
                   (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]]
    return points


def _brace_points(x0, x1, top, height):
    """An underbrace from x0 to x1 hanging down from top, with its tip at the middle. Too narrow for
    curls (e.g. a single frame), it's a V pointing at the frame instead."""
    middle = (x0 + x1) / 2
    if x1 - x0 < 4 * height:
        return [x0, top, middle, top - height, x1, top]
    r = height / 2
    points = [x0, top]
    points += _quadratic((x0, top), (x0, top - r), (x0 + r, top - r))
    points += [middle - r, top - r]
    points += _quadratic((middle - r, top - r), (middle, top - r), (middle, top - height))
    points += _quadratic((middle, top - height), (middle, top - r), (middle + r, top - r))
    points += [x1 - r, top - r]
    points += _quadratic((x1 - r, top - r), (x1, top - r), (x1, top))
    return points


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
        self.notes = {}

    def count(self, frames):
        text = str(frames) if frames <= DISPLAY_COUNT_LIMIT else f"{DISPLAY_COUNT_LIMIT}+"
        if text not in self.counts:
            self.counts[text] = _text_texture(text, COUNT_FONT_SIZE)
        return self.counts[text]

    def note(self, text):
        if text not in self.notes:
            label = CoreLabel(text=text, font_size=sp(14))
            label.refresh()
            if label.texture.width > TOAST_MAX_WIDTH - 2 * TOAST_PADDING:
                # Only long notes wrap; short ones keep a toast that fits their text.
                label = CoreLabel(text=text, font_size=sp(14), text_size=(TOAST_MAX_WIDTH - 2 * TOAST_PADDING, None))
                label.refresh()
            self.notes[text] = label.texture
        return self.notes[text]


class InputListLayout(StencilView):
    """Training-mode style input list that scrolls right to left onto a hit line at a constant speed.

    Time runs left to right, so the player reads upcoming inputs like text. Each run of input is a
    box as wide as it's held: its left edge reaches the line on the frame it should be pressed and
    its right edge when it should be released. Lanes from the top: a frame meter (one block per
    target frame), the target track, a strip marking each frame green (matched) or red (missed), and
    the player's attempt. Notes hang underneath as toasts, each with a brace pointing at the frames
    it annotates. Mouse wheel or drag scrubs; Ctrl + wheel zooms. Clicking selects a frame (Shift
    extends the selection) and dragging in the frame meter selects a range.
    """

    def __init__(self, controller_type="XGamepad", button_icon_style="Alt", **kwargs):
        super().__init__(**kwargs)
        self.textures = _Textures(controller_type, button_icon_style)
        self.px_per_frame = DEFAULT_PX_PER_FRAME
        self.show_notes = True  # When off, notes only show as bars over their frames.
        self.on_scrub = None  # Called with a frame delta when the user scrolls or drags.
        self.on_zoom = None  # Called with the new pixels-per-frame.
        self.on_select = None  # Called with (start, end) frames, inclusive, when the user selects frames.
        self.on_note_click = None  # Called with a note's index when its toast is clicked.
        self._toast_hits = []  # (x, y, width, height, note index) of each toast drawn, for clicks.
        self.selection = None  # (start, end) to highlight, set by the app.
        self._frame = 0  # Frame at the hit line when last drawn, for mapping clicks to frames.
        self._drag_frames = 0.0

        with self.canvas:
            Color(*PANEL_COLOR)
            self.panels = [Rectangle(), Rectangle(), Rectangle()]  # Meter, target, attempt lanes.
            self.box_layer = InstructionGroup()
            self.strip_layer = InstructionGroup()
            self.meter_layer = InstructionGroup()
            self.meter_divider_layer = InstructionGroup()
            self.note_layer = InstructionGroup()
            self.selection_color = Color(*SELECTION_COLOR, 0)
            self.selection_fill = Rectangle()
            self.selection_edge_color = Color(*SELECTION_COLOR, 0)
            self.selection_edges = [Rectangle(), Rectangle()]
        with self.canvas.after:
            # The gutter covers boxes that scroll past the left edge of the track.
            Color(*GUTTER_COLOR)
            self.gutter = Rectangle()
            Color(1, 1, 1, 0.85)
            self.lane_labels = [Rectangle(texture=_text_texture(text, sp(13))) for text in ("Frames", "Target", "You")]
            self.line_color = Color(*LINE_COLOR)
            self.line = Rectangle()
            self.live_color = Color(1, 1, 1, 1)
            live_group = InstructionGroup()
        self.live = _InputLabel(live_group, with_count=False)
        self.target_boxes = _Pool(self.box_layer, _Box)
        self.attempt_boxes = _Pool(self.box_layer, _Box)
        self.strips = _Pool(self.strip_layer, self._make_strip)
        self.meter_blocks = _Pool(self.meter_layer, self._make_strip)
        self.meter_dividers = _Pool(self.meter_divider_layer, self._make_strip)
        self.note_graphics = _Pool(self.note_layer, _NoteGraphic)
        self.bind(pos=self._layout, size=self._layout)

    @staticmethod
    def _make_strip(layer):
        color, rect = Color(1, 1, 1, 0), Rectangle()
        layer.add(color)
        layer.add(rect)
        return color, rect

    # ---- Geometry ----------------------------------------------------------------------------

    def _track_left(self):
        return self.x + MARGIN + GUTTER_WIDTH

    def _track_right(self):
        return self.right - MARGIN

    def _line_x(self):
        return self._track_left() + (self._track_right() - self._track_left()) * LINE_FRACTION

    def _frame_x(self, frame, now):
        return self._line_x() + (frame - now) * self.px_per_frame

    def _lanes(self):
        """Bottom y of the meter, target, strip and attempt lanes."""
        meter_y = self.top - MARGIN - METER_HEIGHT
        target_y = meter_y - LANE_GAP - LANE_HEIGHT
        strip_y = target_y - LANE_GAP / 2 - STRIP_HEIGHT
        attempt_y = strip_y - LANE_GAP / 2 - LANE_HEIGHT
        return meter_y, target_y, strip_y, attempt_y

    def _layout(self, *args):
        meter_y, target_y, strip_y, attempt_y = self._lanes()
        left, right = self._track_left(), self._track_right()
        for panel, (y, height) in zip(self.panels, ((meter_y, METER_HEIGHT), (target_y, LANE_HEIGHT),
                                                    (attempt_y, LANE_HEIGHT))):
            panel.pos = (left, y)
            panel.size = (right - left, height)
        self.gutter.pos = (self.x, attempt_y - LANE_GAP)
        self.gutter.size = (left - self.x, self.top - attempt_y + LANE_GAP)
        for label, (y, height) in zip(self.lane_labels, ((meter_y, METER_HEIGHT), (target_y, LANE_HEIGHT),
                                                         (attempt_y, LANE_HEIGHT))):
            label.size = label.texture.size
            label.pos = (self.x + MARGIN, y + (height - label.texture.height) / 2)
        live_y = attempt_y - LANE_GAP - ICON_SIZE
        self.line.pos = (self._line_x() - dp(1), live_y - dp(4))
        self.line.size = (dp(2), self.top - MARGIN - live_y + dp(4))

    def frames_needed(self):
        """How many frames fit (before, after) the hit line."""
        line_x = self._line_x()
        return (int((line_x - self._track_left()) / self.px_per_frame) + 2,
                int((self._track_right() - line_x) / self.px_per_frame) + 2)

    def frame_at(self, x):
        return self._frame + int((x - self._line_x()) // self.px_per_frame)

    def set_zoom(self, px_per_frame):
        self.px_per_frame = max(MIN_PX_PER_FRAME, min(MAX_PX_PER_FRAME, px_per_frame))

    # ---- Scrolling ---------------------------------------------------------------------------

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        if touch.is_mouse_scrolling:
            # Kivy reports wheel-away-from-you as "scrolldown"; that moves forward in time.
            direction = {"scrolldown": 1, "scrollright": 1, "scrollup": -1, "scrollleft": -1}.get(touch.button, 0)
            if _modifier_held("ctrl"):
                self.set_zoom(self.px_per_frame * (1.25 if direction > 0 else 0.8))
                if self.on_zoom:
                    self.on_zoom(self.px_per_frame)
            elif direction and self.on_scrub:
                self.on_scrub(direction)  # One frame per wheel notch, for frame-by-frame stepping.
            return True
        touch.grab(self)
        self._drag_frames = 0.0
        meter_y = self._lanes()[0]
        # Dragging in the frame meter selects frames; anywhere else it scrubs.
        touch.ud["selecting"] = meter_y - LANE_GAP / 2 <= touch.y <= meter_y + METER_HEIGHT + MARGIN
        touch.ud["anchor"] = self.frame_at(touch.x)
        touch.ud["dragged"] = False
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return super().on_touch_move(touch)
        if abs(touch.x - touch.ox) > CLICK_SLOP or abs(touch.y - touch.oy) > CLICK_SLOP:
            touch.ud["dragged"] = True
        if touch.ud["selecting"]:
            if touch.ud["dragged"] and self.on_select:
                self.on_select(touch.ud["anchor"], self.frame_at(touch.x))
            return True
        # Dragging the track left brings later frames onto the line.
        self._drag_frames -= touch.dx / self.px_per_frame
        whole = int(self._drag_frames)
        if whole and self.on_scrub:
            self.on_scrub(whole)
            self._drag_frames -= whole
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return super().on_touch_up(touch)
        touch.ungrab(self)
        if not touch.ud["dragged"] and self.on_note_click:
            for x, y, width, height, index in self._toast_hits:
                if x <= touch.x <= x + width and y <= touch.y <= y + height:
                    self.on_note_click(index)
                    return True
        if not touch.ud["dragged"] and self.on_select:
            frame = self.frame_at(touch.x)
            if _modifier_held("shift") and self.selection:
                # Extend from whichever end of the current selection is farther away.
                start, end = self.selection
                anchor = start if abs(frame - start) > abs(frame - end) else end
                self.on_select(anchor, frame)
            else:
                self.on_select(frame, frame)
        return True

    # ---- Drawing -----------------------------------------------------------------------------

    def _draw_runs(self, pool, runs, snapshot, lane_y, color, dim_history):
        line_x = self._line_x()
        track_left, track_right = self._track_left(), self._track_right()
        for start, length, key in runs:
            x0 = self._frame_x(start, snapshot.frame)
            x1 = x0 + length * self.px_per_frame
            if x1 < track_left or x0 > track_right:
                continue
            box = pool.next()
            neutral = key == (5, ())
            past = x1 <= line_x
            active = x0 <= line_x < x1
            alpha = HISTORY_ALPHA if past and dim_history else 1
            box.fill_color.rgba = (*color, (0.05 if neutral else 0.16 if not active else 0.28) * alpha)
            box.fill.pos = (x0, lane_y)
            box.fill.size = (x1 - x0, LANE_HEIGHT)
            box.edge_color.rgba = (*color, 0.6 * alpha)
            box.edge.pos = (x0, lane_y)
            box.edge.size = (dp(1), LANE_HEIGHT)
            # Labels are all the same size, anchored to the edge where the input starts. A held run
            # keeps its label just right of the line, and a long run's label stays in view. When
            # zoomed out, runs too narrow for a label show only the box.
            if x1 - x0 < LABEL_WIDTH:
                box.content_color.a = 0
                continue
            box.content_color.a = alpha
            label_x = x0 + LABEL_PADDING
            label_right = x1 - ICON_SIZE - LABEL_PADDING
            label_x = max(label_x, min(track_left + LABEL_PADDING, label_right))
            if active:
                label_x = max(label_x, min(line_x + LABEL_PADDING, label_right))
            box.label.set_stacked(label_x, lane_y + LANE_HEIGHT - dp(4), key, self.textures,
                                  self.textures.count(length))
        pool.finish(_Box.hide)

    def _draw_matches(self, runs, snapshot, strip_y):
        for start, length, matched in runs:
            color, rect = self.strips.next()
            color.rgba = (*(MATCH_COLOR if matched else MISS_COLOR), 0.9)
            rect.pos = (self._frame_x(start, snapshot.frame), strip_y)
            rect.size = (length * self.px_per_frame, STRIP_HEIGHT)
        self.strips.finish(lambda strip: setattr(strip[0], "a", 0))

    def _draw_meter(self, runs, snapshot, meter_y):
        """One block per target frame, coloured by input type, with a divider where the input changes."""
        ppf = self.px_per_frame
        gap = dp(1) if ppf >= dp(4) else 0
        line_x = self._line_x()
        first_visible = snapshot.frame - int((line_x - self._track_left()) / ppf) - 1
        last_visible = snapshot.frame + int((self._track_right() - line_x) / ppf) + 1
        for start, length, key in runs:
            direction, buttons = key
            color = METER_BUTTON_COLOR if buttons else METER_NEUTRAL_COLOR if direction == 5 else METER_DIRECTION_COLOR
            for frame in range(max(start, first_visible), min(start + length, last_visible + 1)):
                past = frame < snapshot.frame and not snapshot.recording
                block_color, block = self.meter_blocks.next()
                block_color.rgba = (*color, HISTORY_ALPHA if past else 0.95)
                block.pos = (self._frame_x(frame, snapshot.frame) + gap, meter_y)
                block.size = (ppf - gap, METER_HEIGHT)
            if first_visible <= start <= last_visible:
                divider_color, divider = self.meter_dividers.next()
                divider_color.rgba = (1, 1, 1, 0.9)
                divider.pos = (self._frame_x(start, snapshot.frame) - dp(1), meter_y - dp(3))
                divider.size = (dp(2), METER_HEIGHT + dp(6))
        hide = lambda item: setattr(item[0], "a", 0)
        self.meter_blocks.finish(hide)
        self.meter_dividers.finish(hide)

    def _draw_notes(self, notes, snapshot, meter_y, notes_top):
        track_left, track_right = self._track_left(), self._track_right()
        row_ends = []  # Right edge of the last toast placed in each row.
        self._toast_hits = []
        for index, start, end, text in notes:
            x0 = self._frame_x(start, snapshot.frame)
            x1 = self._frame_x(end + 1, snapshot.frame)
            if x1 < track_left or x0 > track_right:
                continue
            texture = self.textures.note(text)
            width, height = texture.width + 2 * TOAST_PADDING, texture.height + 2 * TOAST_PADDING
            middle = (x0 + x1) / 2
            toast_x = max(track_left, min(middle - width / 2, track_right - width))
            row = next((i for i, row_end in enumerate(row_ends) if row_end + dp(8) <= toast_x), len(row_ends))
            if row >= TOAST_ROWS:
                continue
            row_ends[row:row + 1] = [toast_x + width]
            toast_top = notes_top - BRACE_HEIGHT - dp(2) - row * (height + dp(6))
            active = start <= snapshot.frame <= end
            alpha = 1 if active else 0.75

            note = self.note_graphics.next()
            note.tint_color.a = 0.9
            note.tint.pos = (x0 + dp(1), meter_y + METER_HEIGHT + dp(2))
            note.tint.size = (x1 - x0 - dp(2), dp(3))
            if not self.show_notes:
                note.brace_color.a = note.toast_color.a = note.accent_color.a = note.text_color.a = 0
                continue
            note.brace_color.a = alpha
            note.brace.points = _brace_points(x0, x1, notes_top, BRACE_HEIGHT)
            # Reaches down past other toasts when overlapping notes pushed this one to a lower row.
            note.connector.points = [middle, notes_top - BRACE_HEIGHT, middle, toast_top]
            note.toast_color.a = 0.92 * alpha
            note.toast.pos = (toast_x, toast_top - height)
            note.toast.size = (width, height)
            note.accent_color.a = alpha
            note.accent.pos = (toast_x, toast_top - height)
            note.accent.size = (dp(3), height)
            note.text_color.a = alpha
            note.text.texture = texture
            note.text.pos = (toast_x + TOAST_PADDING, toast_top - height + TOAST_PADDING)
            note.text.size = texture.size
            self._toast_hits.append((toast_x, toast_top - height, width, height, index))
        self.note_graphics.finish(_NoteGraphic.hide)

    def _draw_selection(self, snapshot, meter_y, attempt_y):
        if not self.selection:
            self.selection_color.a = self.selection_edge_color.a = 0
            return
        start, end = self.selection
        x0 = self._frame_x(start, snapshot.frame)
        x1 = self._frame_x(end + 1, snapshot.frame)
        top = meter_y + METER_HEIGHT
        self.selection_color.a = 0.16
        self.selection_fill.pos = (x0, attempt_y)
        self.selection_fill.size = (x1 - x0, top - attempt_y)
        self.selection_edge_color.a = 0.9
        for edge, x in zip(self.selection_edges, (x0, x1 - dp(2))):
            edge.pos = (x, attempt_y)
            edge.size = (dp(2), top - attempt_y)

    def update_state(self, snapshot):
        self._frame = snapshot.frame
        meter_y, target_y, strip_y, attempt_y = self._lanes()
        self._draw_meter(snapshot.target_runs, snapshot, meter_y)
        self._draw_runs(self.target_boxes, snapshot.target_runs, snapshot, target_y, TARGET_BOX_COLOR,
                        dim_history=not snapshot.recording)
        self._draw_runs(self.attempt_boxes, snapshot.attempt_runs, snapshot, attempt_y, ATTEMPT_BOX_COLOR,
                        dim_history=False)
        self._draw_matches(snapshot.match_runs, snapshot, strip_y)
        self._draw_notes(snapshot.notes, snapshot, meter_y, attempt_y - LANE_GAP - ICON_SIZE - dp(14))
        self._draw_selection(snapshot, meter_y, attempt_y)

        # The player's live input sits under the line, which turns green when it matches.
        live_key = input_key(snapshot.live_state)
        target_key = next((key for start, length, key in snapshot.target_runs
                           if start <= snapshot.frame < start + length), None)
        matched = not snapshot.recording and live_key == target_key
        self.line_color.rgba = (*MATCH_COLOR, 1) if matched else LINE_COLOR
        self.live_color.a = 0 if snapshot.recording else 1
        self.live.set_row(self._line_x() - ICON_SIZE / 2, attempt_y - LANE_GAP - ICON_SIZE - dp(4), ICON_SIZE,
                          live_key, self.textures)
