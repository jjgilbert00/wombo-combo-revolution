from kivy.clock import Clock

class PlayalongController:
    def __init__(self, input_track=[]):
        self.input_track = input_track
        self.current_frame = 0
        self.loop = False
        self.playing = False
        self.frame_duration = 1/60  # Duration of each frame in seconds
        self._clock_event = None

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
            self._clock_event = Clock.schedule_interval(self.next_frame, self.frame_duration)

    def pause(self):
        self.playing = False
        if self._clock_event:
            self._clock_event.cancel()
            self._clock_event = None

    def toggle_loop(self):
        self.loop = not self.loop

    def set_frame_duration(self, duration):
        self.frame_duration = duration
        if self.playing:
            self.pause()
            self.play()

    def is_playing(self):
        return self.playing

    def get_current_frame(self):
        return self.current_frame

    def get_input_track(self):
        return self.input_track

    def set_input_track(self, input_track):
        self.input_track = input_track
        self.current_frame = 0

    def get_state(self):
        return self.input_track[self.current_frame:]

