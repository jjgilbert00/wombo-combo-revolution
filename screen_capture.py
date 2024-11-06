import mss
import cv2
import numpy as np
import time

class ScreenRecorder:
    def __init__(self, fps=60):
        self.frames = []
        self.fps = fps
        self.video = None

    def clear(self):
        self.frames = []
        if self.video:
            self.video.release()
            self.video = None


    # def capture_screen(self):
    #     screen = cv2.imread(cv2.VideoCapture(0).read()[1])
    #     self.frames.append(screen)

    def capture_screen(self):
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            try:
                frame = sct.grab(monitor)
                self.frames.append(frame)
            except Exception as e:
                print(e)
    
    def save_video(self, output_path, width=2560, height=1440, target_frames=None):
        frames_written = 0
        if self.video:
            self.video.release()
        self.video = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*'mp4v'), self.fps, (width, height))
        for i in range(len(self.frames)):
            frame = self.frames[i]
            resized_frame = cv2.resize(cv2.cvtColor(np.array(frame), cv2.COLOR_BGRA2BGR), (width, height))
            # resized_frame = cv2.resize(cv2.cvtColor(np.array(frame), cv2.COLOR_BGR2RGB), (width, height))
            while frames_written < (i + 1) / len(self.frames) * target_frames:
                self.video.write(resized_frame)
                frames_written += 1
        self.video.release()

    def __del__(self):
        if self.video:
            self.video.release()
