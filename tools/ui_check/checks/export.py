"""Video export: an input video and an overlay over a stand-in capture, drawn by the app's displays.
Saves a frame of each to the shots folder to look at."""
import os

import cv2
import numpy as np

import file_dialogs
from video_writer import FfmpegWriter

SHOTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shots")


def frames_in(path):
    capture = cv2.VideoCapture(path)
    count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    capture.set(cv2.CAP_PROP_POS_FRAMES, count // 2)
    ok, middle = capture.read()
    capture.release()
    return count, middle if ok else None


def wait_for_jobs(h):
    while h.app.job_label is not None or h.app.jobs._work_queue.qsize():
        yield 0.2
    yield 0.5


def steps(h):
    c = h.app.playalong_controller
    h.app.open_track(os.path.join(os.getcwd(), "samples", "Warm-up - LP, MP, HP, Hadoken.json")); yield 0.3
    h.app.coaching = False
    count = c.track_length()
    for mode in ("list", "lanes"):
        h.app.show_display(mode); yield 0.2
        path = os.path.join(SHOTS, f"export_inputs_{mode}.mp4")
        file_dialogs.save_file = lambda *args: path
        h.app.export_input_video(); yield 0.5
        yield from wait_for_jobs(h)
        frames, middle = frames_in(path) if os.path.exists(path) else (0, None)
        h.check(f"{mode}: the input video has a frame per recorded frame", frames == count, (frames, count))
        if middle is not None:
            cv2.imwrite(os.path.join(SHOTS, f"export_inputs_{mode}.png"), middle)
            h.check(f"{mode}: it shows the display (not blank)", middle.std() > 5, round(float(middle.std()), 1))

    # An overlay over a stand-in capture: a flat colour, so whatever isn't that colour was drawn.
    h.app.show_display("list"); yield 0.2
    capture = os.path.join(SHOTS, "export_capture.mp4")
    writer = FfmpegWriter(capture, 1280, 720, "bgr24")
    for _ in range(count):
        writer.write(np.full((720, 1280, 3), (40, 90, 160), np.uint8))
    writer.close()
    h.app.capture_path = capture
    path = os.path.join(SHOTS, "export_overlay.mp4")
    file_dialogs.save_file = lambda *args: path
    h.app.export_overlay_video(); yield 0.5
    yield from wait_for_jobs(h)
    frames, middle = frames_in(path) if os.path.exists(path) else (0, None)
    h.check("the overlay video has a frame per recorded frame", frames == count, (frames, count))
    if middle is not None:
        cv2.imwrite(os.path.join(SHOTS, "export_overlay.png"), middle)
        background = np.all(np.abs(middle.astype(int) - (40, 90, 160)) < 12, axis=2).mean()
        h.check("the capture shows through around the inputs", 0.5 < background < 0.995, round(float(background), 3))
