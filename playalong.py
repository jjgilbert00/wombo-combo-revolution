import threading
import time

from controller import get_neutral_controller_state
from games import GAMES
from button_map import full_map, inverse_map, map_state
from key_inputs import GRADE_REACH, HIT, PENDING, describe, grade_all, normalized, result
from playalong_state import PlayalongStatus, RunningState
from playalong_views import PlayalongViews

MAX_RUNS = 50  # Recent attempts kept in memory.


class PlayalongController(PlayalongViews):
    """Owns the input track and playhead.

    tick() runs on the sampler thread once per 60 Hz frame; everything else is called from the UI
    thread. All state is private and guarded by a lock: the UI reads it through status() (one
    consistent view of the transport, score and flags), the get_ methods (copies), and the
    snapshots for drawing (playalong_views.py), and changes it only through methods.

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

    While practising, each key input is judged as soon as it's settled (hit straight away; early,
    late or missed once the window and the frames after it have gone by), for instant feedback,
    and each finished pass leaves a summary: its score, what went wrong, the best score and the
    streak of perfect passes.

    Saved attempts are ones the player chose to keep with the track (they're saved in its file):
    {"id", "name", "created", "attempt", "shown"}, where shown puts them in the input list.
    """

    def __init__(self, input_track=None):
        self._lock = threading.RLock()
        self._running_state = RunningState.STOPPED
        self._input_track = list(input_track or [])
        self._current_frame = 0
        self._loop = False
        self._live_state = get_neutral_controller_state()
        # Called with the tick count after each recorded frame (e.g. to grab a matching video frame).
        self._frame_sink = None
        self._filled_frames = 0  # Recorded frames that repeat the previous one because the sampler ran late.
        self._practice = True  # Playing records the player's attempt; off, playback just replays it.
        self._reset_attempt()
        self._notes = []
        self._key_inputs = []
        self._runs = []
        self._next_run_id = 1
        self._saved = []
        self._next_saved_id = 1
        self._history_count = 5  # Recent runs shown in the input list.
        self._lead_in = 60  # Frames of run-up before practice playback starts, to get ready.
        self._lead = 0  # Run-up frames left before the playhead moves.
        self._demo = None  # {"track", "output", "kind"} while a demo plays.
        self._last_tick = time.perf_counter()  # When the last frame was sampled.
        self._judgements = []  # (time, key input index, grade, offset), newest last.
        self._last_pass = None  # Summary of the last finished pass (see _summarise).
        self._best = 0  # Most key inputs hit in one pass of this track.
        self._streak = 0  # Perfect passes in a row.
        self._button_map = {}  # Recorded button -> the player's; only buttons that differ.
        self._from_player = {}
        self._game = None  # A key of games.GAMES, or None.
        self._action_layout = {}  # Recorded button -> the game's action.
        self._show_actions = False  # Set by the app: show actions instead of buttons.
        self._grades_version = 0  # Bumped when key inputs or the target change, invalidating cached grades.

    def _fit_key_inputs(self, key_inputs):
        """Drops key inputs that start past the end of the track and trims ones that run off it.
        Every change to the key inputs comes through here: it invalidates cached grades, and verdicts
        and judged key inputs (which refer to key inputs by position) start afresh."""
        last = len(self._input_track) - 1
        fitted = [normalized(dict(k, end=min(k["end"], last))) for k in key_inputs if k["start"] <= last]
        self._key_inputs = sorted(fitted, key=lambda k: (k["start"], k["end"]))
        self._grades_version += 1
        self._judgements = []
        self._judged = set()

    def _fit_notes(self, notes):
        """Drops notes that start past the end of the track and trims ones that run off it."""
        last = len(self._input_track) - 1
        fitted = [dict(note, end=min(note["end"], last)) for note in notes if note["start"] <= last]
        self._notes = sorted(fitted, key=lambda note: (note["start"], note["end"]))

    def _reset_attempt(self, attempt=None):
        self._attempt_track = list(attempt) if attempt else [None] * len(self._input_track)
        self._attempt_track += [None] * (len(self._input_track) - len(self._attempt_track))
        del self._attempt_track[len(self._input_track):]
        self._attempted_frames = sum(frame is not None for frame in self._attempt_track)
        self._matched_frames = sum(
            attempt is not None and attempt == target for attempt, target in zip(self._attempt_track, self._input_track)
        )
        self._attempt_archived = True  # Nothing new to archive until the player plays a frame.
        self._judged = set()  # Key inputs already judged in this pass.

    def _judge(self, frame, final=False):
        """Judges the key inputs settled by this frame (all of them if final)."""
        grades = None
        for i, key_input in enumerate(self._key_inputs):
            if i in self._judged:
                continue
            if result(key_input, self._attempt_track, self._input_track) == HIT:
                verdict = (HIT, 0)
            elif final or frame > key_input["end"] + GRADE_REACH:
                grades = grades or grade_all(self._key_inputs, self._attempt_track, self._input_track)
                verdict = grades[i]
                if verdict[0] == PENDING:
                    continue  # Never reached this pass.
            else:
                continue
            self._judged.add(i)
            self._judgements.append((time.monotonic(), i) + tuple(verdict))
        del self._judgements[:-20]

    def _summarise(self, run_id):
        """The finished pass: {"run", "hits", "total", "problems": [(notation, grade, offset)],
        "best", "streak", "match", "time"}. Without key inputs, "match" is the share of frames matched."""
        summary = {"run": run_id, "time": time.monotonic(), "hits": 0, "total": 0, "problems": [], "match": None}
        if self._key_inputs:
            grades = grade_all(self._key_inputs, self._attempt_track, self._input_track)
            played = [(k, g) for k, g in zip(self._key_inputs, grades) if g[0] != PENDING]
            summary["hits"] = sum(grade == HIT for _, (grade, _) in played)
            summary["total"] = len(self._key_inputs)
            summary["problems"] = [(describe(self._shown_key_input(k)), grade, offset)
                                   for k, (grade, offset) in played if grade != HIT]
            perfect = summary["hits"] == summary["total"]
            self._streak = self._streak + 1 if perfect else 0
            self._best = max(self._best, summary["hits"])
        elif self._attempted_frames:
            summary["match"] = self._matched_frames / self._attempted_frames
        summary.update(best=self._best, streak=self._streak)
        return summary

    def _archive_attempt(self):
        """Keeps the attempt as a recent run, unless it's empty or already kept, and sums it up."""
        if self._attempt_archived or not self._attempted_frames:
            return
        self._judge(len(self._input_track), final=True)
        self._last_pass = self._summarise(self._next_run_id)
        self._runs.append({"id": self._next_run_id, "created": time.time(), "attempt": list(self._attempt_track)})
        self._next_run_id += 1
        del self._runs[:-MAX_RUNS]
        self._attempt_archived = True

    def _start_over(self):
        """Archives the attempt and clears it for a fresh pass."""
        self._archive_attempt()
        self._reset_attempt()

    def _record_attempt(self, frame, state):
        previous = self._attempt_track[frame]
        if previous is not None:
            self._attempted_frames -= 1
            self._matched_frames -= previous == self._input_track[frame]
        self._attempt_track[frame] = state
        self._attempt_archived = False
        self._attempted_frames += 1
        self._matched_frames += state == self._input_track[frame]

    def tick(self, controller_state, ticks=1):
        sink = None
        demo_output = demo_state = None
        with self._lock:
            self._live_state = controller_state
            self._last_tick = time.perf_counter()
            if self._running_state == RunningState.PLAYING and self._demo:
                demo_output = self._demo["output"]
                demo_state = self._demo_frame(ticks)
            elif self._running_state == RunningState.PLAYING:
                if self._lead:
                    used = min(ticks, self._lead)
                    self._lead -= used
                    ticks -= used
                if ticks and self._practice:
                    # This tick's input answers the frame at the line (and any frames skipped by a late tick).
                    for offset in range(ticks):
                        frame = self._current_frame + offset
                        if frame < len(self._input_track):
                            self._record_attempt(frame, map_state(controller_state, self._from_player))
                    if self._key_inputs:
                        self._judge(self._current_frame + ticks - 1)
                if ticks:
                    self._advance(ticks)
            elif self._running_state == RunningState.RECORDING:
                if not self._input_track:
                    ticks = 1  # Anything missed before recording started isn't part of the take.
                # Frames the sampler missed repeat the last known state so timing stays intact.
                self._filled_frames += ticks - 1
                self._input_track.extend(self._input_track[-1] for _ in range(ticks - 1))
                self._input_track.append(controller_state)
                sink = self._frame_sink
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
        track = self._demo["track"]
        frame = self._current_frame + ticks - 1
        if frame >= len(track):
            self._end_demo()
            return None
        self._current_frame = frame + 1
        return track[frame]

    def _end_demo(self):
        self._demo = None
        self._lead = 0
        self._running_state = RunningState.STOPPED
        self._current_frame = max(0, min(self._current_frame, len(self._input_track) - 1))

    def start_demo(self, track, output, countdown, kind):
        """Plays track out through output(state) from the first frame, after countdown frames of
        neutral. kind names what's being demoed, for the display."""
        with self._lock:
            if self._running_state == RunningState.RECORDING or not track:
                return
            self._demo = {"track": list(track), "output": output, "kind": kind}
            self._current_frame = 0
            self._lead = countdown
            self._running_state = RunningState.PLAYING

    def stop_demo(self):
        """Stops a demo and releases everything on the controller."""
        with self._lock:
            output = self._demo["output"] if self._demo else None
            if self._demo:
                self._end_demo()
        if output:
            output(None)

    def demo_kind(self):
        with self._lock:
            return self._demo["kind"] if self._demo else None

    def _advance(self, ticks):
        self._current_frame += ticks
        if self._current_frame >= len(self._input_track):
            if self._loop and self._input_track:
                self._current_frame %= len(self._input_track)
                if self._practice:
                    self._start_over()
                    self._lead = self._lead_in
            else:
                self._current_frame = max(0, len(self._input_track) - 1)
                self._running_state = RunningState.STOPPED
                self._archive_attempt()  # Kept on screen to review, and in the history.

    # ---- Reading the state (all under the lock) -------------------------------------------------

    def status(self):
        """A consistent view of where things are, for the status bar, hints and menus."""
        with self._lock:
            hits, total = self._key_input_score()
            return PlayalongStatus(
                recording=self._running_state == RunningState.RECORDING,
                playing=self._running_state == RunningState.PLAYING,
                practice=self._practice, loop=self._loop,
                demo=self._demo["kind"] if self._demo else None, lead=self._lead,
                frame=self._current_frame, length=len(self._input_track),
                hits=hits, key_inputs=total, notes=len(self._notes),
                attempted=self._attempted_frames, matched=self._matched_frames, filled=self._filled_frames,
                remapped=bool(self._button_map), game=self._game, show_actions=self._show_actions)

    def track_length(self):
        with self._lock:
            return len(self._input_track)

    def is_practicing(self):
        with self._lock:
            return self._practice

    def is_looping(self):
        with self._lock:
            return self._loop

    def get_game(self):
        """(the recording's game or None, its action layout)."""
        with self._lock:
            return self._game, dict(self._action_layout)

    def get_last_pass(self):
        with self._lock:
            return dict(self._last_pass) if self._last_pass else None

    def has_key_inputs(self):
        with self._lock:
            return bool(self._key_inputs)

    def has_notes(self):
        with self._lock:
            return bool(self._notes)

    def get_judgements(self):
        """[(time, key input index, grade, offset)], newest last."""
        with self._lock:
            return list(self._judgements)

    def set_lead_in(self, frames):
        with self._lock:
            self._lead_in = frames

    def set_show_actions(self, show):
        with self._lock:
            self._show_actions = show

    def is_showing_actions(self):
        with self._lock:
            return self._show_actions

    def set_game(self, game, action_layout=None):
        """The recording's game (or None) and which recorded button is which action (default: the
        game's usual layout)."""
        with self._lock:
            self._game = game if game in GAMES else None
            layout = action_layout if action_layout is not None else (GAMES[game]["default_layout"] if self._game else {})
            self._action_layout = {button: action for button, action in layout.items()
                                  if self._game and action in GAMES[self._game]["actions"]}

    def score(self, attempt):
        """(hits, total) against the key inputs, or with none, (matched frames, played frames)."""
        with self._lock:
            if self._key_inputs:
                grades = grade_all(self._key_inputs, attempt, self._input_track)
                return sum(grade == HIT for grade, _ in grades), len(grades)
            played = [(a, t) for a, t in zip(attempt, self._input_track) if a is not None]
            return sum(a == t for a, t in played), len(played)

    def remove_run(self, run_id):
        with self._lock:
            self._runs = [run for run in self._runs if run["id"] != run_id]

    def save_attempt(self, run_id=None, name=None):
        """Saves a recent run, or with no run_id the attempt on screen (or failing that, the latest
        run). Returns the saved attempt, or None if there's nothing to save."""
        with self._lock:
            if run_id is not None:
                attempt = next((run["attempt"] for run in self._runs if run["id"] == run_id), None)
            elif self._attempted_frames:
                attempt = self._attempt_track
            else:
                attempt = self._runs[-1]["attempt"] if self._runs else None
            if attempt is None:
                return None
            saved = {"id": self._next_saved_id, "name": name or f"Saved {self._next_saved_id}",
                     "created": time.time(), "attempt": list(attempt), "shown": True}
            self._next_saved_id += 1
            self._saved.append(saved)
            return dict(saved)

    def get_saved(self):
        """Saved attempts without their ids or cached grades, as they're written to the track file."""
        with self._lock:
            return [{key: saved[key] for key in ("name", "created", "attempt", "shown")} for saved in self._saved]

    def get_saved_attempts(self):
        with self._lock:
            return [dict(saved) for saved in self._saved]

    def update_saved(self, saved_id, **fields):
        """Renames (name=) or shows/hides (shown=) a saved attempt."""
        with self._lock:
            for saved in self._saved:
                if saved["id"] == saved_id:
                    saved.update(fields)

    def remove_saved(self, saved_id):
        with self._lock:
            self._saved = [saved for saved in self._saved if saved["id"] != saved_id]

    def _set_saved(self, saved_attempts):
        self._saved = []
        for saved in saved_attempts:
            attempt = list(saved["attempt"])[:len(self._input_track)]
            attempt += [None] * (len(self._input_track) - len(attempt))
            self._saved.append({"id": self._next_saved_id, "name": saved.get("name") or f"Saved {self._next_saved_id}",
                               "created": saved.get("created", 0), "attempt": attempt,
                               "shown": saved.get("shown", True)})
            self._next_saved_id += 1

    def get_runs(self):
        with self._lock:
            return [dict(run) for run in self._runs]

    def set_history_count(self, count):
        with self._lock:
            self._history_count = count

    def restart(self):
        """Back to the first frame. In practice mode that starts a fresh attempt, keeping the
        current one in the history."""
        with self._lock:
            if self._practice:
                self._start_over()
                if self._running_state == RunningState.PLAYING:
                    self._lead = self._lead_in
            self._current_frame = 0

    def get_key_inputs(self):
        with self._lock:
            return [dict(k) for k in self._key_inputs]

    def set_key_input(self, index, key_input):
        """Adds a key input (index None) or replaces the one at index. Returns its new index."""
        with self._lock:
            key_inputs = [dict(k) for k in self._key_inputs]
            key_input = dict(key_input, start=min(key_input["start"], key_input["end"]),
                             end=max(key_input["start"], key_input["end"]))
            if index is None:
                key_inputs.append(key_input)
            else:
                key_inputs[index] = key_input
            self._fit_key_inputs(key_inputs)
            key_input = normalized(key_input)
            return self._key_inputs.index(key_input) if key_input in self._key_inputs else None

    def remove_key_input(self, index):
        with self._lock:
            self._fit_key_inputs(self._key_inputs[:index] + self._key_inputs[index + 1:])

    def key_input_score(self):
        """(hits, total) for the attempt against the key inputs."""
        with self._lock:
            return self._key_input_score()

    def _key_input_score(self):
        results = [result(k, self._attempt_track, self._input_track) for k in self._key_inputs]
        return sum(r == HIT for r in results), len(results)

    def get_notes(self):
        with self._lock:
            return [dict(note) for note in self._notes]

    def set_note(self, index, start, end, text):
        """Adds a note (index None) or replaces the note at index. Returns the note's new index."""
        with self._lock:
            notes = [dict(note) for note in self._notes]
            note = {"start": min(start, end), "end": max(start, end), "text": text}
            if index is None:
                notes.append(note)
            else:
                notes[index] = note
            self._fit_notes(notes)
            return self._notes.index(note) if note in self._notes else None

    def remove_note(self, index):
        with self._lock:
            del self._notes[index]

    def get_attempt_track(self):
        with self._lock:
            return list(self._attempt_track)

    def set_attempt_track(self, attempt):
        """Shows the given attempt (e.g. a run to replay); it isn't archived again."""
        with self._lock:
            self._reset_attempt(attempt)

    def clear_attempt(self):
        self.set_attempt_track(None)

    def set_practice(self, practice):
        with self._lock:
            self._practice = practice

    def get_lead(self):
        """Run-up frames left before practice playback starts."""
        with self._lock:
            return self._lead

    def set_frame(self, frame):
        with self._lock:
            self._lead = 0
            self._current_frame = max(0, min(frame, len(self._input_track) - 1))

    def play(self):
        with self._lock:
            if self._demo:
                return
            if self._running_state == RunningState.STOPPED and self._input_track:
                if self._current_frame >= len(self._input_track) - 1:
                    self._current_frame = 0
                    if self._practice:
                        self._start_over()
                if self._practice:
                    self._lead = self._lead_in  # Time to get ready, whenever practice (re)starts.
                self._running_state = RunningState.PLAYING

    def pause(self):
        self.stop_demo()
        with self._lock:
            self._running_state = RunningState.STOPPED
            self._lead = 0

    def set_looping(self, loop):
        with self._lock:
            self._loop = loop

    def is_playing(self):
        with self._lock:
            return self._running_state == RunningState.PLAYING

    def is_recording(self):
        with self._lock:
            return self._running_state == RunningState.RECORDING

    def get_current_frame(self):
        with self._lock:
            return self._current_frame

    def get_input_track(self):
        with self._lock:
            return list(self._input_track)

    def get_button_map(self):
        with self._lock:
            return dict(self._button_map)

    def set_button_map(self, mapping):
        """Sets {recorded button: player's button}; it must be one-to-one."""
        table = full_map(mapping)
        if len(set(table.values())) != len(table):
            raise ValueError(f"Button map isn't one-to-one: {mapping}")
        with self._lock:
            self._button_map = {recorded: theirs for recorded, theirs in table.items() if recorded != theirs}
            self._from_player = {theirs: recorded for theirs, recorded in inverse_map(self._button_map).items()
                                 if theirs != recorded}

    def set_input_track(self, input_track, attempt=None, notes=None, key_inputs=None, saved_attempts=None,
                        button_map=None):
        self.set_button_map(button_map or {})
        with self._lock:
            self._running_state = RunningState.STOPPED
            self._input_track = list(input_track)
            self._current_frame = 0
            self._reset_attempt(attempt)
            self._runs = []  # Runs belong to the track they were played against.
            self._judgements, self._last_pass, self._best, self._streak = [], None, 0, 0
            self._set_saved(saved_attempts or [])
            self._fit_notes(notes or [])
            self._fit_key_inputs(key_inputs or [])

    def clear_track(self):
        self.set_input_track([])

    def start_recording(self, frame_sink=None):
        with self._lock:
            self._frame_sink = frame_sink
            self._filled_frames = 0
            self._input_track = []
            self._current_frame = 0
            self._reset_attempt()
            self._runs = []
            self._saved = []
            self._notes = []
            self._key_inputs = []
            self._button_map, self._from_player = {}, {}  # A new take is in the player's own buttons.
            self._running_state = RunningState.RECORDING

    def stop_recording(self):
        with self._lock:
            self._running_state = RunningState.STOPPED
            self._frame_sink = None
            self._current_frame = 0
            self._reset_attempt()

    def truncate(self, frame_count):
        """Drops trailing frames, e.g. one recorded after the video capture had already stopped."""
        with self._lock:
            del self._input_track[frame_count:]
            self._reset_attempt(self._attempt_track)
            self._fit_notes(self._notes)
            self._fit_key_inputs(self._key_inputs)

    def clean_track(self):
        """Reduces held buttons to their first frame so prompts show presses, not holds."""
        with self._lock:
            self._running_state = RunningState.STOPPED
            cleaned = [dict(frame) for frame in self._input_track]
            for i in range(len(cleaned) - 1, 0, -1):
                for button in cleaned[i]:
                    if button == "direction":
                        continue
                    if self._input_track[i][button] == self._input_track[i - 1][button]:
                        cleaned[i][button] = 0
            self._input_track = cleaned
            self._grades_version += 1
            self._current_frame = 0
            self._reset_attempt(self._attempt_track)  # Re-score the attempt against the cleaned track.
