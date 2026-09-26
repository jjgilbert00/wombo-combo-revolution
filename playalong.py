import threading
import time
from enum import Enum

from collections import namedtuple

from controller import get_neutral_controller_state
from games import GAMES, normal_window, to_actions
from input_list import LIST_BUTTON_ORDER, input_key, full_map, inverse_map, map_key, map_key_input, map_state, match_runs, runs_in_range
from key_inputs import HIT, best_hold, grade_all, normalized, result

PLAYALONG_FRAMELENGTH = 120
MAX_RUNS = 50  # Recent attempts kept in memory.


ListSnapshot = namedtuple(
    "ListSnapshot", "live_state frame recording target_runs attempt_runs match_runs notes key_inputs history live_key"
)
# One earlier attempt in the input list: its label, its key input grades as (start, end, grade, offset),
# when the track has no key inputs its per-frame match runs instead, and whether it's a saved attempt.
HistoryRow = namedtuple("HistoryRow", "label grades match_runs saved")


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

    Key inputs (see key_inputs.py) mark the inputs that matter, each with a window of eligible
    frames; the attempt is scored against them. They're also kept sorted by start frame.

    Each practice pass is kept as a run in the recent history: when playback loops or reaches the
    end, or is restarted partway, the attempt so far is archived and (when starting over) cleared,
    so the next pass starts fresh. Runs are {"id", "created", "attempt"}, oldest first.

    A demo plays a track (the recording, or a cleaned version of it) out through a virtual
    controller, one frame per tick, so the combo can be watched in game. It takes over playback:
    nothing is scored, and it stops at the end of the track or when paused.

    A button map ({recorded button: player's button}) lets the player use their own layout. The
    track and everything made from it stay in the recording's buttons; the player's live input is
    translated into them for scoring, and snapshots translate back, so the player sees their own.

    A recording can belong to a game (see games.py), with an action layout saying which recorded
    button is which of the game's actions. With show_actions on, snapshots show actions (a medium
    punch, a Drive Impact) instead of buttons.

    Saved attempts are ones the player chose to keep with the track (they're saved in its file):
    {"id", "name", "created", "attempt", "shown"}, where shown puts them in the input list.
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
        self.key_inputs = []
        self.runs = []
        self._next_run_id = 1
        self.saved = []
        self._next_saved_id = 1
        self.history_count = 5  # Recent runs shown in the input list.
        self.lead_in = 60  # Frames of run-up before practice playback starts, to get ready.
        self._lead = 0  # Run-up frames left before the playhead moves.
        self.demo = None  # {"track", "output", "kind"} while a demo plays.
        self.button_map = {}  # Recorded button -> the player's; only buttons that differ.
        self._from_player = {}
        self.game = None  # A key of games.GAMES, or None.
        self.action_layout = {}  # Recorded button -> the game's action.
        self.show_actions = False  # Set by the app: show actions instead of buttons.
        self._grades_version = 0  # Bumped when key inputs or the target change, invalidating cached grades.

    def _fit_key_inputs(self, key_inputs):
        """Drops key inputs that start past the end of the track and trims ones that run off it."""
        last = len(self.input_track) - 1
        fitted = [normalized(dict(k, end=min(k["end"], last))) for k in key_inputs if k["start"] <= last]
        self.key_inputs = sorted(fitted, key=lambda k: (k["start"], k["end"]))
        self._grades_version += 1

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
        self._attempt_archived = True  # Nothing new to archive until the player plays a frame.

    def _archive_attempt(self):
        """Keeps the attempt as a recent run, unless it's empty or already kept."""
        if self._attempt_archived or not self.attempted_frames:
            return
        self.runs.append({"id": self._next_run_id, "created": time.time(), "attempt": list(self.attempt_track)})
        self._next_run_id += 1
        del self.runs[:-MAX_RUNS]
        self._attempt_archived = True

    def _start_over(self):
        """Archives the attempt and clears it for a fresh pass."""
        self._archive_attempt()
        self._reset_attempt()

    def _record_attempt(self, frame, state):
        previous = self.attempt_track[frame]
        if previous is not None:
            self.attempted_frames -= 1
            self.matched_frames -= previous == self.input_track[frame]
        self.attempt_track[frame] = state
        self._attempt_archived = False
        self.attempted_frames += 1
        self.matched_frames += state == self.input_track[frame]

    def tick(self, controller_state, ticks=1):
        sink = None
        demo_output = demo_state = None
        with self._lock:
            self.live_state = controller_state
            if self.running_state == RUNNING_STATES.PLAYING and self.demo:
                demo_output = self.demo["output"]
                demo_state = self._demo_frame(ticks)
            elif self.running_state == RUNNING_STATES.PLAYING:
                if self._lead:
                    used = min(ticks, self._lead)
                    self._lead -= used
                    ticks -= used
                if ticks and self.practice:
                    # This tick's input answers the frame at the line (and any frames skipped by a late tick).
                    for offset in range(ticks):
                        frame = self.current_frame + offset
                        if frame < len(self.input_track):
                            self._record_attempt(frame, map_state(controller_state, self._from_player))
                if ticks:
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
        if demo_output:
            demo_output(demo_state)

    def _demo_frame(self, ticks):
        """The demo frame due on this tick (None, neutral, during the countdown), or ends the demo
        once the track is done. A late tick skips to the latest frame due, so the demo keeps time."""
        if self._lead:
            used = min(ticks, self._lead)
            self._lead -= used
            ticks -= used
        if not ticks:
            return None
        track = self.demo["track"]
        frame = self.current_frame + ticks - 1
        if frame >= len(track):
            self._end_demo()
            return None
        self.current_frame = frame + 1
        return track[frame]

    def _end_demo(self):
        self.demo = None
        self._lead = 0
        self.running_state = RUNNING_STATES.STOPPED
        self.current_frame = max(0, min(self.current_frame, len(self.input_track) - 1))

    def start_demo(self, track, output, countdown, kind):
        """Plays track out through output(state) from the first frame, after countdown frames of
        neutral. kind names what's being demoed, for the display."""
        with self._lock:
            if self.running_state == RUNNING_STATES.RECORDING or not track:
                return
            self.demo = {"track": list(track), "output": output, "kind": kind}
            self.current_frame = 0
            self._lead = countdown
            self.running_state = RUNNING_STATES.PLAYING

    def stop_demo(self):
        """Stops a demo and releases everything on the controller."""
        with self._lock:
            output = self.demo["output"] if self.demo else None
            if self.demo:
                self._end_demo()
        if output:
            output(None)

    def demo_kind(self):
        demo = self.demo
        return demo["kind"] if demo else None

    def _advance(self, ticks):
        self.current_frame += ticks
        if self.current_frame >= len(self.input_track):
            if self.loop and self.input_track:
                self.current_frame %= len(self.input_track)
                if self.practice:
                    self._start_over()
                    self._lead = self.lead_in
            else:
                self.current_frame = max(0, len(self.input_track) - 1)
                self.running_state = RUNNING_STATES.STOPPED
                self._archive_attempt()  # Kept on screen to review, and in the history.

    def snapshot(self):
        """Returns (live controller state, upcoming frames to prompt) for the view."""
        with self._lock:
            if self.running_state == RUNNING_STATES.RECORDING:
                return self.live_state, []
            return self.live_state, [map_state(frame, self.button_map) for frame in self.get_playalong_frames()]

    def list_snapshot(self, frames_before, frames_after):
        """Target runs, attempt runs and per-frame matches around the playhead, for the input list."""
        with self._lock:
            recording = self.running_state == RUNNING_STATES.RECORDING
            # During the run-up the view starts before frame 0, so the first inputs scroll in.
            frame = len(self.input_track) if recording else self.current_frame - self._lead
            lo, hi = frame - frames_before, frame + frames_after + 1
            if recording:
                return ListSnapshot(self.live_state, frame, True, self._shown_runs(self.input_track, lo, hi, False),
                                    [], [], [], [], [], self._live_key())
            # A demo shows what it's sending where the attempt would go.
            shown = self.demo["track"] if self.demo else self.attempt_track
            return ListSnapshot(
                self.live_state, frame, False,
                self._shown_runs(self.input_track, lo, hi),
                self._shown_runs(shown, lo, hi),
                [] if self.demo else match_runs(self.input_track, self.attempt_track, lo, hi),
                [(i, note["start"], note["end"], note["text"]) for i, note in enumerate(self.notes)
                 if note["start"] < hi and note["end"] >= lo],
                [(i, self._shown_key_input(k), result(k, self.attempt_track, self.input_track),
                  best_hold(k, self.attempt_track) if k["hold"] and not k["exact"] else None)
                 for i, k in enumerate(self.key_inputs)
                 if k["start"] < hi and k["end"] >= lo],
                self._history_rows(lo, hi),
                self._live_key(),
            )

    def _actions_on(self):
        return self.show_actions and self.game in GAMES

    def _shown_key(self, key, track=None, start=0):
        """A run's (direction, buttons) as shown: the game's actions, or the player's buttons."""
        if not self._actions_on():
            return map_key(key, self.button_map)
        direction, pressed = key
        actions = to_actions(self.game, self.action_layout, pressed)
        window = normal_window(self.game)
        if window and track is not None and actions != to_actions(self.game, self.action_layout, pressed, True):
            actions = to_actions(self.game, self.action_layout, pressed, self._normal_before(track, start, window))
        return direction, tuple(actions)

    def _normal_before(self, track, frame, window):
        """Whether a normal attack (one of the game's single actions) was newly pressed in the frames
        just before this one. The last two frames don't count: pressing two buttons a frame apart is
        still pressing them together."""
        for f in range(max(1, frame - window), min(frame - 2, len(track))):
            now, before = track[f], track[f - 1]
            if now is not None and any(now[b] and not (before and before[b]) and b in self.action_layout
                                       for b in LIST_BUTTON_ORDER):
                return True
        return False

    def _shown_runs(self, track, lo, hi, with_context=True):
        return [(start, length, self._shown_key(key, track if with_context else None, start))
                for start, length, key in runs_in_range(track, lo, hi)]

    def _shown_key_input(self, key_input):
        if self._actions_on():
            return dict(key_input, buttons=to_actions(self.game, self.action_layout, key_input.get("buttons", [])))
        return map_key_input(key_input, self.button_map)

    def _live_key(self):
        """The player's live input as shown: their own buttons, or as the game's actions."""
        if not self._actions_on():
            return input_key(self.live_state)
        return self._shown_key(input_key(map_state(self.live_state, self._from_player)))

    def set_game(self, game, action_layout=None):
        """The recording's game (or None) and which recorded button is which action (default: the
        game's usual layout)."""
        with self._lock:
            self.game = game if game in GAMES else None
            layout = action_layout if action_layout is not None else (GAMES[game]["default_layout"] if self.game else {})
            self.action_layout = {button: action for button, action in layout.items()
                                  if self.game and action in GAMES[self.game]["actions"]}

    def _grades(self, run):
        """The run's key input grades, cached until the key inputs or target change."""
        if run.get("_grades", (None,))[0] != self._grades_version:
            run["_grades"] = (self._grades_version, grade_all(self.key_inputs, run["attempt"], self.input_track))
        return run["_grades"][1]

    def _history_row(self, run, label, saved, lo, hi):
        if not self.key_inputs:
            return HistoryRow(label, [], match_runs(self.input_track, run["attempt"], lo, hi), saved)
        grades = [(k["start"], k["end"], grade, offset) for k, (grade, offset) in zip(self.key_inputs, self._grades(run))
                  if k["start"] < hi and k["end"] >= lo]
        return HistoryRow(label, grades, [], saved)

    def _history_rows(self, lo, hi):
        """Shown saved attempts, then the most recent history_count runs newest first, trimmed to
        frames lo..hi."""
        rows = [self._history_row(saved, saved["name"], True, lo, hi) for saved in self.saved if saved["shown"]]
        for run in reversed(self.runs[-self.history_count:] if self.history_count else []):
            rows.append(self._history_row(run, f"Run {run['id']}", False, lo, hi))
        return rows

    def score(self, attempt):
        """(hits, total) against the key inputs, or with none, (matched frames, played frames)."""
        with self._lock:
            if self.key_inputs:
                grades = grade_all(self.key_inputs, attempt, self.input_track)
                return sum(grade == HIT for grade, _ in grades), len(grades)
            played = [(a, t) for a, t in zip(attempt, self.input_track) if a is not None]
            return sum(a == t for a, t in played), len(played)

    def remove_run(self, run_id):
        with self._lock:
            self.runs = [run for run in self.runs if run["id"] != run_id]

    def save_attempt(self, run_id=None, name=None):
        """Saves a recent run, or with no run_id the attempt on screen (or failing that, the latest
        run). Returns the saved attempt, or None if there's nothing to save."""
        with self._lock:
            if run_id is not None:
                attempt = next((run["attempt"] for run in self.runs if run["id"] == run_id), None)
            elif self.attempted_frames:
                attempt = self.attempt_track
            else:
                attempt = self.runs[-1]["attempt"] if self.runs else None
            if attempt is None:
                return None
            saved = {"id": self._next_saved_id, "name": name or f"Saved {self._next_saved_id}",
                     "created": time.time(), "attempt": list(attempt), "shown": True}
            self._next_saved_id += 1
            self.saved.append(saved)
            return dict(saved)

    def get_saved(self):
        """Saved attempts without their ids or cached grades, as they're written to the track file."""
        with self._lock:
            return [{key: saved[key] for key in ("name", "created", "attempt", "shown")} for saved in self.saved]

    def get_saved_attempts(self):
        with self._lock:
            return [dict(saved) for saved in self.saved]

    def update_saved(self, saved_id, **fields):
        """Renames (name=) or shows/hides (shown=) a saved attempt."""
        with self._lock:
            for saved in self.saved:
                if saved["id"] == saved_id:
                    saved.update(fields)

    def remove_saved(self, saved_id):
        with self._lock:
            self.saved = [saved for saved in self.saved if saved["id"] != saved_id]

    def _set_saved(self, saved_attempts):
        self.saved = []
        for saved in saved_attempts:
            attempt = list(saved["attempt"])[:len(self.input_track)]
            attempt += [None] * (len(self.input_track) - len(attempt))
            self.saved.append({"id": self._next_saved_id, "name": saved.get("name") or f"Saved {self._next_saved_id}",
                               "created": saved.get("created", 0), "attempt": attempt,
                               "shown": saved.get("shown", True)})
            self._next_saved_id += 1

    def get_runs(self):
        with self._lock:
            return [dict(run) for run in self.runs]

    def set_history_count(self, count):
        self.history_count = count

    def restart(self):
        """Back to the first frame. In practice mode that starts a fresh attempt, keeping the
        current one in the history."""
        with self._lock:
            if self.practice:
                self._start_over()
                if self.running_state == RUNNING_STATES.PLAYING:
                    self._lead = self.lead_in
            self.current_frame = 0

    def get_key_inputs(self):
        with self._lock:
            return [dict(k) for k in self.key_inputs]

    def set_key_input(self, index, key_input):
        """Adds a key input (index None) or replaces the one at index. Returns its new index."""
        with self._lock:
            key_inputs = [dict(k) for k in self.key_inputs]
            key_input = dict(key_input, start=min(key_input["start"], key_input["end"]),
                             end=max(key_input["start"], key_input["end"]))
            if index is None:
                key_inputs.append(key_input)
            else:
                key_inputs[index] = key_input
            self._fit_key_inputs(key_inputs)
            return self.key_inputs.index(key_input) if key_input in self.key_inputs else None

    def remove_key_input(self, index):
        with self._lock:
            del self.key_inputs[index]

    def key_input_score(self):
        """(hits, total) for the attempt against the key inputs."""
        with self._lock:
            results = [result(k, self.attempt_track, self.input_track) for k in self.key_inputs]
            return sum(r == HIT for r in results), len(results)

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
        """Shows the given attempt (e.g. a run to replay); it isn't archived again."""
        with self._lock:
            self._reset_attempt(attempt)

    def clear_attempt(self):
        self.set_attempt_track(None)

    def set_practice(self, practice):
        self.practice = practice

    def get_lead(self):
        """Run-up frames left before practice playback starts."""
        return self._lead

    def set_frame(self, frame):
        with self._lock:
            self._lead = 0
            self.current_frame = max(0, min(frame, len(self.input_track) - 1))

    def play(self):
        with self._lock:
            if self.demo:
                return
            if self.running_state == RUNNING_STATES.STOPPED and self.input_track:
                if self.current_frame >= len(self.input_track) - 1:
                    self.current_frame = 0
                    if self.practice:
                        self._start_over()
                if self.practice:
                    self._lead = self.lead_in  # Time to get ready, whenever practice (re)starts.
                self.running_state = RUNNING_STATES.PLAYING

    def pause(self):
        self.stop_demo()
        with self._lock:
            self.running_state = RUNNING_STATES.STOPPED
            self._lead = 0

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

    def get_button_map(self):
        return dict(self.button_map)

    def set_button_map(self, mapping):
        """Sets {recorded button: player's button}; it must be one-to-one."""
        table = full_map(mapping)
        if len(set(table.values())) != len(table):
            raise ValueError(f"Button map isn't one-to-one: {mapping}")
        with self._lock:
            self.button_map = {recorded: theirs for recorded, theirs in table.items() if recorded != theirs}
            self._from_player = {theirs: recorded for theirs, recorded in inverse_map(self.button_map).items()
                                 if theirs != recorded}

    def set_input_track(self, input_track, attempt=None, notes=None, key_inputs=None, saved_attempts=None,
                        button_map=None):
        self.set_button_map(button_map or {})
        with self._lock:
            self.running_state = RUNNING_STATES.STOPPED
            self.input_track = list(input_track)
            self.current_frame = 0
            self._reset_attempt(attempt)
            self.runs = []  # Runs belong to the track they were played against.
            self._set_saved(saved_attempts or [])
            self._fit_notes(notes or [])
            self._fit_key_inputs(key_inputs or [])

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
            self.runs = []
            self.saved = []
            self.notes = []
            self.key_inputs = []
            self.button_map, self._from_player = {}, {}  # A new take is in the player's own buttons.
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
            self._fit_key_inputs(self.key_inputs)

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
            self._grades_version += 1
            self.current_frame = 0
            self._reset_attempt(self.attempt_track)  # Re-score the attempt against the cleaned track.
