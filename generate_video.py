from controller import get_cool_controller_pattern, get_neutral_controller_state
from image_generator import StateDrawer
from moviepy.editor import ImageSequenceClip
import numpy as np



def save_images_as_video(frames, output_path, fps=60):
    clip = ImageSequenceClip(frames, fps=fps)
    clip.write_videofile(output_path, codec="libx264")


def write_video_file(inputs, output_path, playalong_length=120):
    drawer = StateDrawer()
    extended_inputs = inputs + [get_neutral_controller_state() for _ in range(playalong_length)]
    images = [drawer.draw(extended_inputs[i:i+playalong_length]) for i in range(len(extended_inputs) - playalong_length)]
    frames = [np.array(image) for image in images]
    save_images_as_video(frames, output_path)

if __name__ == "__main__":
    playalong_length=120
    drawer = StateDrawer()
    inputs = get_cool_controller_pattern()
    animated_inputs = inputs + [get_neutral_controller_state() for _ in range(playalong_length)]
    images = [drawer.draw(animated_inputs[i:i+120]) for i in range(len(animated_inputs) - playalong_length)]
    frames = [np.array(image) for image in images]
    save_images_as_video(frames, "output_video.mp4")
    