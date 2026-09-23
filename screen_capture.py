import logging
import threading
import time

import dxcam
import numpy as np

from video_writer import AsyncFrameWriter

logger = logging.getLogger(__name__)

_cameras = {}


def list_displays():
    """Returns [(output index, "WxH"), ...] for the primary GPU's displays."""
    displays = []
    for line in dxcam.output_info().splitlines():
        # e.g. "Device[0] Output[1]: Res:(2560, 1440) Rot:0 Primary:False"
        if line.startswith("Device[0]") and "Res:(" in line:
            index = int(line.split("Output[")[1].split("]")[0])
            width, height = line.split("Res:(")[1].split(")")[0].split(", ")
            displays.append((index, f"{width}x{height}"))
    return displays


def prepare_capture(output_idx):
    """Creates (and caches) the capture device for a display. dxcam allows one per output."""
    if output_idx not in _cameras:
        try:
            _cameras[output_idx] = dxcam.create(output_idx=output_idx, output_color="BGRA")
        except Exception:
            logger.exception("Couldn't create capture device for display %d", output_idx)
            return None
    return _cameras[output_idx]


class ScreenRecorder:
    """Captures one desktop frame per input frame and streams it to an encoder.

    capture() is called on the sampler thread right after the controller is polled, so video
    frame i always lines up with input frame i. When the desktop hasn't changed, dxcam returns
    None and the previous frame is repeated.
    """

    def __init__(self, output_idx=0, max_height=None, encoder="libx264", fps=60):
        self.output_idx = output_idx
        self.max_height = max_height
        self.encoder = encoder
        self.fps = fps
        self.camera = None
        self.writer = None
        self._pending_writer = None
        self.output_path = None
        self.frames_captured = 0
        self._last_frame = None
        self._lock = threading.Lock()  # Lets finish() wait for a capture in progress on the sampler thread.

    def start(self, output_path):
        self.camera = prepare_capture(self.output_idx)
        if self.camera is None:
            raise RuntimeError(f"can't capture display {self.output_idx + 1}")
        self.output_path = output_path
        self.frames_captured = 0
        self._last_frame = self._first_frame()
        height, width = self._last_frame.shape[:2]
        if self.max_height and height > self.max_height:
            width, height = round(width * self.max_height / height), self.max_height
        # H.264 with yuv420p needs even dimensions.
        self.writer = AsyncFrameWriter(output_path, width - width % 2, height - height % 2, self.fps, self.encoder)

    def _first_frame(self):
        deadline = time.perf_counter() + 0.5
        while time.perf_counter() < deadline:
            frame = self.camera.grab()
            if frame is not None:
                return frame
            time.sleep(0.005)
        return np.zeros((self.camera.height, self.camera.width, 4), dtype=np.uint8)

    def capture(self, ticks=1):
        with self._lock:
            if self.writer is None:
                return
            frame = self.camera.grab()
            if frame is not None:
                self._last_frame = frame
            for _ in range(ticks):
                self.writer.put(self._last_frame)
            self.frames_captured += ticks

    def backlog(self):
        return self.writer.backlog() if self.writer else 0

    def stop(self):
        """Stops accepting frames. frames_captured is final once this returns."""
        with self._lock:
            if self.writer:
                self._pending_writer, self.writer = self.writer, None

    def finish(self):
        """Blocks until the video file is fully written. Raises if encoding failed."""
        self.stop()
        writer, self._pending_writer = self._pending_writer, None
        if writer:
            writer.close()
