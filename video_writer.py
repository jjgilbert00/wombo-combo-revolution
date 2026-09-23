from controller import get_cool_controller_pattern, get_neutral_controller_state
from input_drawer import InputDrawer
import cv2
import numpy as np
import subprocess
import os


def write_video_file(output_path, frames, color_conversion, fps=60):
    if not frames:
        return
    video = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (frames[0].shape[1], frames[0].shape[0]))
    for frame in frames:
        if color_conversion:
            frame = cv2.cvtColor(frame, color_conversion)
        video.write(frame)
    video.release()
    subprocess.run(["python", os.path.join(os.path.dirname(__file__), "reencode.py"), output_path])


def write_input_video(inputs, output_path, playalong_length=120, width=1600, height=800):
    if not inputs:
        return
    drawer = InputDrawer(width, height)
    extended_inputs = inputs + [get_neutral_controller_state() for _ in range(playalong_length)]
    frames = [np.array(drawer.draw(extended_inputs[i:i+playalong_length])) for i in range(len(inputs))]
    write_video_file(output_path, frames, cv2.COLOR_RGBA2BGR)


def write_capture_and_overlay(capture_frames, inputs, output_path, playalong_length=120, opacity=0.8):
    if not inputs:
        return
    height, width, _ = capture_frames[0].shape
    drawer = InputDrawer(width, height)

    # Hacky way to delay the input visualization by 4 frames to compensate for the delay in the capture
    extended_inputs = [get_neutral_controller_state() for _ in range(4)] + inputs + [get_neutral_controller_state() for _ in range(playalong_length)]
    combined_frames = []
    for i in range(min(len(capture_frames), len(extended_inputs) - playalong_length)):
        frame = cv2.cvtColor(capture_frames[i], cv2.COLOR_BGRA2BGR)
        overlay = np.asarray(drawer.draw(extended_inputs[i:i+playalong_length]))
        # Alpha-blend using the overlay's own alpha channel so only the drawn inputs cover the video.
        weight = overlay[:, :, 3].astype(np.float32) * (opacity / 255)
        overlay_bgr = cv2.cvtColor(overlay, cv2.COLOR_RGBA2BGR)
        combined_frames.append(cv2.blendLinear(overlay_bgr, frame, weight, 1.0 - weight))
    write_video_file(output_path, combined_frames, None)
