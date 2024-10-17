from kivy.clock import Clock
from controller import get_neutral_controller_state
PLAYALONG_FRAMELENGTH = 120
class PlayalongController:
    def __init__(self, controller_reader, view=None, input_track=[]):
        self.view = view
        self.controller_reader = controller_reader
        self.input_track = input_track
        self.current_frame = 0
        self.loop = False
        self.playing = False
        self.frame_duration = 1/20  # Duration of each frame in seconds
        self._refresh_event = Clock.schedule_interval(lambda x: self.refresh(), self.frame_duration)

    def set_frame(self, frame):
        self.current_frame = max(0, min(frame, len(self.input_track)-1))

    def next_frame(self, dt=None):
        self.current_frame += 1
        if self.current_frame >= len(self.input_track):
            if self.loop:
                self.current_frame = 0
            else:
                self.current_frame = len(self.input_track) - 1
                self.pause()

    def play(self):
        if not self.playing:
            self.playing = True

    def pause(self):
        self.playing = False

    def set_looping(self, loop):
        self.loop = loop

    def is_playing(self):
        return self.playing

    def get_current_frame(self):
        return self.current_frame

    def get_input_track(self):
        return self.input_track

    def set_input_track(self, input_track):
        self.input_track = input_track
        self.current_frame = 0

    def get_playalong_frames(self):
        return self.input_track[self.current_frame:] + [get_neutral_controller_state() for _ in range(PLAYALONG_FRAMELENGTH - len(self.input_track[self.current_frame:]))]
    def refresh(self):
        if self.playing:
            self.next_frame()
        self.controller_reader.update_state()
        self.view.update_state(self.controller_reader.get_controller_state(), self.get_playalong_frames())


