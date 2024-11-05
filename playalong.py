from kivy.clock import Clock
from controller import get_neutral_controller_state
from enum import Enum
PLAYALONG_FRAMELENGTH = 120

class RUNNING_STATES(Enum):
    STOPPED = 0
    PLAYING = 1
    RECORDING = 2

class PlayalongController:
    def __init__(self, controller_reader, view=None, input_track=[]):
        self.running_state = RUNNING_STATES.STOPPED
        self.view = view
        self.controller_reader = controller_reader
        self.input_track = input_track
        self.current_frame = 0
        self.loop = False

    def set_frame(self, frame):
        self.current_frame = max(0, min(frame, len(self.input_track) - 1))

    def next_frame(self, dt=None):
        self.current_frame += 1
        if self.current_frame >= len(self.input_track):
            if self.loop:
                self.current_frame = 0
            else:
                self.current_frame = len(self.input_track) - 1
                self.pause()

    def play(self):
        if self.running_state == RUNNING_STATES.STOPPED:
            self.running_state = RUNNING_STATES.PLAYING

    def pause(self):
        self.running_state = RUNNING_STATES.STOPPED

    def set_looping(self, loop):
        self.loop = loop

    def is_playing(self):
        return self.running_state == RUNNING_STATES.PLAYING

    def is_recording(self):
        return self.running_state == RUNNING_STATES.RECORDING

    def get_current_frame(self):
        return self.current_frame

    def get_input_track(self):
        return self.input_track

    def set_input_track(self, input_track):
        self.input_track = input_track
        self.current_frame = 0

    def get_playalong_frames(self):
        playalong_frames = self.input_track[
            self.current_frame : self.current_frame + PLAYALONG_FRAMELENGTH
        ]
        if len(playalong_frames) < PLAYALONG_FRAMELENGTH:
            playalong_frames += [
                get_neutral_controller_state()
                for _ in range(PLAYALONG_FRAMELENGTH - len(playalong_frames))
            ]
        return playalong_frames

    def refresh(self):

        if self.running_state == RUNNING_STATES.PLAYING:
            self.next_frame()

        self.controller_reader.update_state()

        controller_state = self.controller_reader.get_controller_state()

        if self.running_state == RUNNING_STATES.RECORDING:
            self.input_track.append(controller_state)
            self.current_frame = max(0, len(self.input_track) - PLAYALONG_FRAMELENGTH)

        self.view.update_state(controller_state, self.get_playalong_frames())

    def clear_track(self):
        self.running_state = RUNNING_STATES.STOPPED
        self.input_track = []
        self.current_frame = 0
        

    def start_recording(self):
        self.running_state = RUNNING_STATES.RECORDING
        self.input_track = []
        self.current_frame = 0

    def clean_track(self):
        self.running_state = RUNNING_STATES.STOPPED
        i=0
        for i in range(len(self.input_track)):
            if self.input_track[i] != get_neutral_controller_state():
                break
        if i > 120:
            self.input_track = self.input_track[i- 120:] # Trim any more than 2 seconds of neutral input at the start
        for i in range(len(self.input_track) - 1, 0, -1):
            for button in self.input_track[i]:
                if button == "direction":
                    continue
                if self.input_track[i][button] == self.input_track[i-1][button]:
                    self.input_track[i][button] = 0
        self.current_frame = 0

    def save_track(self):
        with open("input_track.json", "w") as f:
            json.dump(self.input_track, f)