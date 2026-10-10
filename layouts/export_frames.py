"""Exported videos are drawn by the app's own displays, so they look exactly like practising.

DisplayFrames draws a display offscreen, one frame of the recording at a time. Kivy only draws on
the UI thread, while exports are encoded on the job thread, so frames are drawn on the UI thread a
few at a time (on the clock, so the window stays responsive) into a short queue, and the export
takes them from it in order with frames().
"""
import queue

import numpy as np
from kivy.clock import Clock
from kivy.graphics import ClearBuffers, ClearColor, Fbo

from layouts.input_list_layout import InputListLayout
from sampler import FPS

QUEUE_FRAMES = 30  # Frames drawn ahead of the encoder.
FRAMES_PER_TICK = 4  # Frames drawn per UI frame: enough to keep up, few enough to keep the window smooth.
STALL_SECONDS = 10  # If no frame comes for this long (the app is closing), the export gives up.


class DisplayFrames:
    """display is a fresh display (not the one on screen) and controller a PlayalongController with the
    recording, used only for this. Frames first..first+count-1 are drawn (frames before 0 show frame 0,
    for a delayed overlay). background is the RGBA colour behind the display: transparent for an
    overlay over captured video. lookahead is how many seconds ahead the falling displays show."""

    def __init__(self, display, controller, size, count, first=0, background=(0, 0, 0, 0), lookahead=1.5):
        self.display, self.controller = display, controller
        self.ahead = max(10, round(lookahead * FPS))
        self.size, self.count, self.first = size, count, first
        self.queue = queue.Queue(maxsize=QUEUE_FRAMES)
        self.cancelled = False
        self.next = 0
        self.fbo = Fbo(size=size, with_stencilbuffer=True)  # The input list clips with a stencil.
        with self.fbo:
            ClearColor(*background)
            ClearBuffers()
        display.size_hint = (None, None)
        display.size, display.pos = size, (0, 0)
        for widget in display.walk():  # Lay out now; the clock would only do it on the next frame.
            if hasattr(widget, "do_layout"):
                widget.do_layout()
        self.fbo.add(display.canvas)
        self._event = Clock.schedule_interval(self._draw_some, 0)

    def _draw_some(self, dt):
        if self.cancelled or self.next >= self.count:
            self._finish()
            return False
        for _ in range(FRAMES_PER_TICK):
            if self.next >= self.count or self.queue.full():
                break
            self.queue.put(self._draw(self.first + self.next))
            self.next += 1
        return None

    def _draw(self, frame):
        """The display at a frame of the recording, as an RGBA array, top row first."""
        controller, display = self.controller, self.display
        controller.set_frame(max(0, frame))
        if isinstance(display, InputListLayout):
            before, after = display.frames_needed()
            display.dim_non_key = controller.has_key_inputs()
            display.update_state(controller.list_snapshot(before, after))
        else:
            state, upcoming, offset = controller.snapshot(self.ahead)
            display.update_state(state, upcoming, offset)
            display.show_feedback([], None)
        self.fbo.draw()
        width, height = self.size
        return np.frombuffer(self.fbo.pixels, np.uint8).reshape(height, width, 4)[::-1]

    def frames(self):
        """The frames in order, for the export's thread. Blocks until each is drawn."""
        try:
            for _ in range(self.count):
                try:
                    yield self.queue.get(timeout=STALL_SECONDS)
                except queue.Empty:
                    raise RuntimeError("drawing the video stopped") from None
        finally:
            self.cancel()

    def cancel(self):
        """Stops drawing (the export finished or failed)."""
        self.cancelled = True

    def _finish(self):
        self.fbo.remove(self.display.canvas)

