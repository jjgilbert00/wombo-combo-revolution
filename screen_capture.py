import array
import mss
import cv2
import numpy as np
import time
import dxcam

from video_writer import write_video_file

class ScreenRecorder:
    def __init__(self, fps=60):
        self.frames = []
        self.fps = fps
        self.video = None
        self.camera = dxcam.create(output_idx=0, output_color="BGRA")

    def clear(self):
        self.frames = []
        if self.video:
            self.video.release()
            self.video = None

    def start_recording(self):
        self.camera.start(target_fps=60, video_mode=True)

    def stop_recording(self):
        self.camera.stop()

    def capture_screen(self):
        if self.camera.is_capturing:
            self.frames.append(self.camera.get_latest_frame())
        else:
            self.frames.append(self.camera.grab())
    
    def get_frames(self, target_frames=None):
        if not self.frames:
            return None
        frames = []
        if not target_frames:
            target_frames = len(self.frames)
        total_frames = 0
        for i in range(len(self.frames)):
            if self.frames[i] is None:
                continue
            # Frame interpolation. If we can't get screenshots at 60fps, we need to fill in gaps. 
            while total_frames < (i + 1) / len(self.frames) * target_frames:
                frames.append(self.frames[i])
                total_frames += 1
        return frames
    
    def save_video(self, output_path, width=2560, height=1440, target_frames=None):
        frames = self.get_frames(target_frames=target_frames)
        if not frames:
            print("No frames to save.")
            return
        write_video_file(output_path, frames, cv2.COLOR_BGRA2BGR)

    def __del__(self):
        if self.video:
            self.video.release()
