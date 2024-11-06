import array
import mss
import cv2
import numpy as np
import time
import dxcam
from moviepy.editor import ImageSequenceClip

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
        if not self.frames:
            print("No frames to save.")
            return
        frames_written = 0
        if not target_frames:
            target_frames = len(self.frames)
        frames = []
        for i in range(len(self.frames)):
            if self.frames[i] is None:
                continue
            frame = self.frames[i][:, :, :3]
            # Frame interpolation. If we can't get screenshots at 60fps, we need to fill in gaps.
            while frames_written < (i + 1) / len(self.frames) * target_frames:
                frames.append(frame)
                frames_written += 1
        clip = ImageSequenceClip(frames, fps=self.fps)
        clip.write_videofile(output_path, codec='libx264', fps=self.fps)

    def __del__(self):
        if self.video:
            self.video.release()
