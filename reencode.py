import argparse
from moviepy.editor import VideoFileClip

def reencode_video(input_path):
    # Load the video file
    clip = VideoFileClip(input_path)

    output_path = input_path.replace(".mp4", "_h264.mp4")
    
    # Write the video file with the h264 codec
    clip.write_videofile(output_path, codec='libx264')

    # Scale the video to half size
    half_size_clip = clip.resize(0.5)
    half_size_output_path = output_path.replace(".mp4", "_half.mp4")
    half_size_clip.write_videofile(half_size_output_path, codec='libx264')

    # Scale the video to quarter size
    quarter_size_clip = clip.resize(0.25)
    quarter_size_output_path = output_path.replace(".mp4", "_quarter.mp4")
    quarter_size_clip.write_videofile(quarter_size_output_path, codec='libx264')

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reencode video to h264 and at different sizes.")
    parser.add_argument("input_path", help="Path to the input video file")
    args = parser.parse_args()
    reencode_video(args.input_path)