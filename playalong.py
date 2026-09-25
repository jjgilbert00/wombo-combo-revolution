import threading
from enum import Enum

from collections import namedtuple

from controller import get_neutral_controller_state
from input_list import match_runs, runs_in_range

PLAYALONG_FRAMELENGTH = 120


ListSnapshot = namedtuple("ListSnapshot", "live_state frame recording target_runs attempt_runs match_runs notes")


class RUNNING_STATES(Enum):
    STOPPED = 0
    PLAYING = 1
    RECORDING = 2


class PlayalongController:
    """Owns the input track and playhead.

    tick() runs on the sampler thread once per 60 Hz frame; everything else is called from the UI
    thread. All shared state is guarded by a lock, and the UI reads it through snapshot().

    Alongside the track it keeps the player's attempt: one entry per track frame, None where they
    haven't played it. While playing in practice mode, live input is written into the attempt at the
    playhead, so the two can be compared frame for frame and replayed together afterwards.

    Notes annotate a range of track frames with text: {"start": frame, "end": frame, "text": str},
    with an inclusive range. They're kept sorted by start frame.
    """

    def __init__(self, input_track=None):
        self._lock = threading.RLock()
        self.running_state = RUNNING_STATES.STOPPED
        self.input_track = list(input_track or [])
        self.current_frame = 0
        self.loop = False
        self.live_state = get_neutral_controller_state()
        # Called with the tick count after each recorded frame (e.g. to grab a matching video frame).
        self.frame_sink = None
        self.filled_frames = 0  # Recorded frames that repeat the previous one because the sampler ran late.
        self.practice = True  # Playing records the player's attempt; off, playback just replays it.
        self._reset_attempt()
        self.notes = []

    def _fit_notes(self, notes):
        """Drops notes that start past the end of the track and trims ones that run off it."""
        last = len(self.input_track) - 1
        fitted = [dict(note, end=min(note["end"], last)) for note in notes if note["start"] <= last]
        self.notes = sorted(fitted, key=lambda note: (note["start"], note["end"]))

    def _reset_attempt(self, attempt=None):
        self.attempt_track = list(attempt) if attempt else [None] * len(self.input_track)
        self.attempt_track += [None] * (len(self.input_track) - len(self.attempt_track))
        del self.attempt_track[len(self.input_track):]
        self.attempted_frames = sum(frame is not None for frame in self.attempt_track)
        self.matched_frames = sum(
            attempt is not None and attempt == target for attempt, target in zip(self.attempt_track, self.input_track)
        )

    def _record_attempt(self, frame, state):
        previous = self.attempt_track[frame]
        if previous is not None:
            self.attempted_frames -= 1
            self.matched_frames -= previous == self.input_track[frame]
        self.attempt_track[frame] = state
        self.attempted_frames += 1
        self.matched_frames += state == self.input_track[frame]

    def tick(self, controller_state, ticks=1):
        sink = None
        with self._lock:
            self.live_state = controller_state
            if self.running_state == RUNNING_STATES.PLAYING:
                if self.practice:
                    # This tick's input answers the frame at the line (and any frames skipped by a late tick).
                    for offset in range(ticks):
                        frame = self.current_frame + offset
                        if frame < len(self.input_track):
                            self._record_attempt(frame, controller_state)
                self._advance(ticks)
            elif self.running_state == RUNNING_STATES.RECORDING:
                if not self.input_track:
                    ticks = 1  # Anything missed before recording started isn't part of the take.
                # Frames the sampler missed repeat the last known state so timing stays intact.
                self.filled_frames += ticks - 1
                self.input_track.extend(self.input_track[-1] for _ in range(ticks - 1))
                self.input_track.append(controller_state)
                sink = self.frame_sink
        if sink:
            sink(ticks)

    def _advance(self, ticks):
        self.current_frame += ticks
        if self.current_frame >= len(self.input_track):
            if self.loop and self.input_track:
                self.current_frame %= len(self.input_track)
            else:
                self.current_frame = max(0, len(self.input_track) - 1)
                self.running_state = RUNNING_STATES.STOPPED

    def snapshot(self):
        """Returns (live controller state, upcoming frames to prompt) for the view."""
        with self._lock:
            if self.running_state == RUNNING_STATES.RECORDING:
                return self.live_state, []
            return self.live_state, self.get_playalong_frames()

    def list_snapshot(self, frames_before, frames_after):
        """Target runs, attempt runs and per-frame matches around the playhead, for the input list."""
        with self._lock:
            recording = self.running_state == RUNNING_STATES.RECORDING
            frame = len(self.input_track) if recording else self.current_frame
            lo, hi = frame - frames_before, frame + frames_after + 1
            if recording:
                return ListSnapshot(self.live_state, frame, True, runs_in_range(self.input_track, lo, hi), [], [], [])
            return ListSnapshot(
                self.live_state, frame, False,
                runs_in_range(self.input_track, lo, hi),
                runs_in_range(self.attempt_track, lo, hi),
                match_runs(self.input_track, self.attempt_track, lo, hi),
                [(i, note["start"], note["end"], note["text"]) for i, note in enumerate(self.notes)
                 if note["start"] < hi and note["end"] >= lo],
            )

    def get_notes(self):
        with self._lock:
            return [dict(note) for note in self.notes]

    def set_note(self, index, start, end, text):
        """Adds a note (index None) or replaces the note at index. Returns the note's new index."""
        with self._lock:
            notes = [dict(note) for note in self.notes]
            note = {"start": min(start, end), "end": max(start, end), "text": text}
            if index is None:
                notes.append(note)
            else:
                notes[index] = note
            self._fit_notes(notes)
            return self.notes.index(note) if note in self.notes else None

    def remove_note(self, index):
        with self._lock:
            del self.notes[index]

    def get_attempt_track(self):
        with self._lock:
            return list(self.attempt_track)

    def set_attempt_track(self, attempt):
        with self._lock:
            self._reset_attempt(attempt)

    def clear_attempt(self):
        self.set_attempt_track(None)

    def set_practice(self, practice):
        self.practice = practice

    def set_frame(self, frame):
        with self._lock:
            self.current_frame = max(0, min(frame, len(self.input_track) - 1))

    def play(self):
        with self._lock:
            if self.running_state == RUNNING_STATES.STOPPED and self.input_track:
                if self.current_frame >= len(self.input_track) - 1:
                    self.current_frame = 0
                self.running_state = RUNNING_STATES.PLAYING

    def pause(self):
        with self._lock:
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
        with self._lock:
            return list(self.input_track)

    def set_input_track(self, input_track, attempt=None, notes=None):
        with self._lock:
            self.running_state = RUNNING_STATES.STOPPED
            self.input_track = list(input_track)
            self.current_frame = 0
            self._reset_attempt(attempt)
            self._fit_notes(notes or [])

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

    def clear_track(self):
        self.set_input_track([])

    def start_recording(self, frame_sink=None):
        with self._lock:
            self.frame_sink = frame_sink
            self.filled_frames = 0
            self.input_track = []
            self.current_frame = 0
            self._reset_attempt()
            self.notes = []
            self.running_state = RUNNING_STATES.RECORDING

    def stop_recording(self):
        with self._lock:
            self.running_state = RUNNING_STATES.STOPPED
            self.frame_sink = None
            self.current_frame = 0
            self._reset_attempt()

    def truncate(self, frame_count):
        """Drops trailing frames, e.g. one recorded after the video capture had already stopped."""
        with self._lock:
            del self.input_track[frame_count:]
            self._reset_attempt(self.attempt_track)
            self._fit_notes(self.notes)

    def clean_track(self):
        """Reduces held buttons to their first frame so prompts show presses, not holds."""
        with self._lock:
            self.running_state = RUNNING_STATES.STOPPED
            cleaned = [dict(frame) for frame in self.input_track]
            for i in range(len(cleaned) - 1, 0, -1):
                for button in cleaned[i]:
                    if button == "direction":
                        continue
                    if self.input_track[i][button] == self.input_track[i - 1][button]:
                        cleaned[i][button] = 0
            self.input_track = cleaned
            self.current_frame = 0
            self._reset_attempt(self.attempt_track)  # Re-score the attempt against the cleaned track.
