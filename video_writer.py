import logging
import queue
import subprocess
import threading

import cv2
import imageio_ffmpeg
import numpy as np

from controller import get_neutral_controller_state
from input_drawer import InputDrawer

logger = logging.getLogger(__name__)

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# Fast settings while capturing (must keep up in real time), smaller files when exporting.
CODEC_ARGS = {
    ("libx264", "capture"): ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "18"],
    ("libx264", "export"): ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"],
    # p1-p7 presets need ffmpeg 4.3+ (imageio-ffmpeg 0.5.1 bundles 4.2, which current drivers reject).
    ("h264_nvenc", "capture"): ["-c:v", "h264_nvenc", "-preset", "p2", "-rc", "vbr", "-cq", "19", "-b:v", "0"],
    ("h264_nvenc", "export"): ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "21", "-b:v", "0"],
}

_nvenc_available = None


def nvenc_available():
    """Encodes one tiny frame with NVENC to see whether an NVIDIA encoder is usable. Cached."""
    global _nvenc_available
    if _nvenc_available is None:
        try:
            result = subprocess.run(
                [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=s=256x256",
                 "-frames:v", "1", *CODEC_ARGS[("h264_nvenc", "capture")], "-f", "null", "-"],
                capture_output=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            _nvenc_available = result.returncode == 0
        except Exception:
            _nvenc_available = False
    return _nvenc_available


def resolve_encoder(preference):
    if preference == "nvenc" or (preference == "auto" and nvenc_available()):
        return "h264_nvenc"
    return "libx264"


class FfmpegWriter:
    """Pipes raw frames into ffmpeg, which encodes straight to H.264. Nothing is held in memory."""

    def __init__(self, output_path, width, height, pix_fmt="bgra", fps=60, encoder="libx264", purpose="export"):
        self.output_path = output_path
        self.frames_written = 0
        command = [
            FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", pix_fmt, "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
            "-an", *CODEC_ARGS[(encoder, purpose)], "-pix_fmt", "yuv420p", output_path,
        ]
        self.process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self._stderr = []
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()

    def _drain_stderr(self):
        for line in self.process.stderr:
            self._stderr.append(line.decode(errors="replace").rstrip())

    def write(self, frame):
        # Writing to the pipe releases the GIL, so this doesn't stall the sampler thread.
        self.process.stdin.write(memoryview(np.ascontiguousarray(frame)))
        self.frames_written += 1

    def close(self):
        try:
            self.process.stdin.close()
        except OSError:
            pass
        self.process.wait()
        self._stderr_thread.join(timeout=1)
        if self.process.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {' '.join(self._stderr[-3:]) or self.process.returncode}")


class AsyncFrameWriter:
    """Accepts frames from a time-critical thread and encodes them on a background thread."""

    def __init__(self, output_path, width, height, fps=60, encoder="libx264"):
        self.size = (width, height)
        self.error = None
        self._queue = queue.Queue()
        self._writer = FfmpegWriter(output_path, width, height, "bgra", fps, encoder, purpose="capture")
        self._thread = threading.Thread(target=self._run, name="FrameWriter", daemon=True)
        self._thread.start()

    def put(self, frame):
        self._queue.put(frame)

    def backlog(self):
        return self._queue.qsize()

    def _run(self):
        while True:
            frame = self._queue.get()
            if frame is None:
                break
            if self.error:
                continue  # Keep draining so memory is released.
            try:
                if (frame.shape[1], frame.shape[0]) != self.size:
                    frame = cv2.resize(frame, self.size, interpolation=cv2.INTER_AREA)
                self._writer.write(frame)
            except Exception as e:
                logger.exception("Frame writer failed")
                self.error = e
        try:
            self._writer.close()
        except Exception as e:
            self.error = self.error or e

    def close(self):
        """Blocks until every queued frame is encoded. Raises if encoding failed."""
        self._queue.put(None)
        self._thread.join()
        if self.error:
            raise RuntimeError(str(self.error))


def _padded(inputs, before, after):
    return (
        [get_neutral_controller_state() for _ in range(before)]
        + list(inputs)
        + [get_neutral_controller_state() for _ in range(after)]
    )


# A note is shown from half a second before its frames until a second after them.
NOTE_LEAD_FRAMES = 30
NOTE_LINGER_FRAMES = 60


def notes_at(notes, frame):
    return [note["text"] for note in notes or ()
            if note["start"] - NOTE_LEAD_FRAMES <= frame <= note["end"] + NOTE_LINGER_FRAMES]


def write_input_video(inputs, output_path, playalong_length=120, width=1600, height=800, encoder="libx264", progress=None,
                      notes=None):
    if not inputs:
        return
    drawer = InputDrawer(width, height)
    writer = FfmpegWriter(output_path, width, height, "rgba", encoder=encoder)
    extended_inputs = _padded(inputs, 0, playalong_length)
    try:
        for i in range(len(inputs)):
            writer.write(np.asarray(drawer.draw(extended_inputs[i : i + playalong_length], notes_at(notes, i))))
            if progress and i % 30 == 0:
                progress(i / len(inputs))
    finally:
        writer.close()


def write_capture_and_overlay(capture_path, inputs, output_path, playalong_length=120, delay_frames=4, opacity=0.8,
                              encoder="libx264", progress=None, notes=None):
    """Draws the input display over a captured video, frame for frame.

    delay_frames shifts the inputs later to line them up with what the game shows on screen.
    """
    if not inputs:
        return
    capture = cv2.VideoCapture(capture_path)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if not width or not height:
        raise RuntimeError(f"Couldn't read {capture_path}")
    drawer = InputDrawer(width, height)
    writer = FfmpegWriter(output_path, width, height, "bgr24", encoder=encoder)
    extended_inputs = _padded(inputs, delay_frames, playalong_length)
    try:
        for i in range(len(inputs)):
            ok, frame = capture.read()
            if not ok:
                break
            # Inputs (and their notes) are shown delay_frames later, to match what the game shows.
            overlay = np.asarray(drawer.draw(extended_inputs[i : i + playalong_length], notes_at(notes, i - delay_frames)))
            # Alpha-blend using the overlay's own alpha channel so only the drawn inputs cover the video.
            weight = overlay[:, :, 3].astype(np.float32) * (opacity / 255)
            overlay_bgr = cv2.cvtColor(overlay, cv2.COLOR_RGBA2BGR)
            writer.write(cv2.blendLinear(overlay_bgr, frame, weight, 1.0 - weight))
            if progress and i % 30 == 0:
                progress(i / len(inputs))
    finally:
        capture.release()
        writer.close()
