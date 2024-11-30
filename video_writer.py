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


def write_input_video(inputs, output_path, playalong_length=120):
    if not inputs:
        return
    drawer = InputDrawer()
    extended_inputs = inputs + [get_neutral_controller_state() for _ in range(playalong_length)]
    frames  = [np.array(drawer.draw(extended_inputs[i:i+playalong_length])) for i in range(len(extended_inputs) - playalong_length)]
    write_video_file(output_path, frames, cv2.COLOR_RGBA2BGR)


def write_capture_and_overlay(capture_frames, inputs, output_path, playalong_length=120):
    if not inputs:
        return
    drawer = InputDrawer()
    height, width, _ = capture_frames[0].shape
    
    # Hacky way to delay the input visualization by 4 frames to compensate for the delay in the capture
    extended_inputs = [get_neutral_controller_state() for _ in range(4)] + inputs + [get_neutral_controller_state() for _ in range(playalong_length)]
    images = [drawer.draw(extended_inputs[i:i+playalong_length], width=width, height=height) for i in range(len(extended_inputs) - playalong_length)]
    input_frames = [np.array(image) for image in images]
    combined_frames = []
    for i in range(min(len(capture_frames), len(input_frames))):
        capture_frame = capture_frames[i]
        overlay_frame = cv2.cvtColor(input_frames[i], cv2.COLOR_RGBA2BGRA)
        combined_frame = cv2.addWeighted(capture_frame, 0.7, overlay_frame, 0.3, 0)
        combined_frames.append(combined_frame)
    write_video_file(output_path, combined_frames, cv2.COLOR_BGRA2BGR)

