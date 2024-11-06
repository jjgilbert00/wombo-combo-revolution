from controller import get_cool_controller_pattern, get_neutral_controller_state
from input_drawer import InputDrawer
import cv2
# from moviepy.editor import ImageSequenceClip
import numpy as np


# TODO Make this asynchronous
def save_images_as_video(frames, output_path, fps=60):
    if frames:
        
        video = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (frames[0].shape[1], frames[0].shape[0]))
        for frame in frames:
            video.write(cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR))
        video.release()


def write_video_file(inputs, output_path, playalong_length=120):
    if not inputs:
        return
    drawer = InputDrawer()
    extended_inputs = inputs + [get_neutral_controller_state() for _ in range(playalong_length)]
    frames  = [np.array(drawer.draw(extended_inputs[i:i+playalong_length])) for i in range(len(extended_inputs) - playalong_length)]
    save_images_as_video(frames, output_path)


def write_capture_and_overlay(capture_frames, inputs, output_path, playalong_length=120):
    if not inputs:
        return
    drawer = InputDrawer()
    height, width, _ = capture_frames[0].shape

    extended_inputs = inputs + [get_neutral_controller_state() for _ in range(playalong_length)]
    images = [drawer.draw(extended_inputs[i:i+playalong_length], width=width, height=height) for i in range(len(extended_inputs) - playalong_length)]
    input_frames = [np.array(image) for image in images]

    video = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*'mp4v'), 60, (width, height))
    for i in range(min(len(capture_frames), len(input_frames))):
        capture_frame = capture_frames[i]
        overlay_frame = cv2.cvtColor(input_frames[i], cv2.COLOR_RGBA2BGRA)
        combined_frame = cv2.addWeighted(capture_frame, 0.7, overlay_frame, 0.3, 0)
        video.write(cv2.cvtColor(combined_frame, cv2.COLOR_BGRA2BGR))
    video.release()


if __name__ == "__main__":
    playalong_length=120
    drawer = InputDrawer()
    inputs = get_cool_controller_pattern()
    animated_inputs = inputs + [get_neutral_controller_state() for _ in range(playalong_length)]
    images = [drawer.draw(animated_inputs[i:i+120]) for i in range(len(animated_inputs) - playalong_length)]
    frames = [np.array(image) for image in images]
    save_images_as_video(frames, "output_video.mp4")
    