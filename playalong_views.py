"""What the displays are given to draw, worked out from the playalong controller's state: for the
input list a ListSnapshot (runs around the playhead, key inputs, notes, history rows, verdicts, the
up-next queue), and for the falling displays the upcoming frames.

This is a mixin of PlayalongController (it reads the controller's state under its lock); it's kept
apart so the controller's own file is about playing, recording and scoring, and a drawing bug's data
can be found here.
"""
import time

from collections import namedtuple

from controller import get_neutral_controller_state
from games import GAMES, normal_window, to_actions
from button_map import map_key, map_key_input, map_state
from input_list import LIST_BUTTON_ORDER, input_key, match_runs, runs_in_range
from key_inputs import best_hold, describe, grade_all, result
from sampler import FPS
from playalong_state import RunningState

PLAYALONG_FRAMELENGTH = 120
UPCOMING_LOOKAHEAD = 10 * FPS  # How far ahead the up-next panel looks for inputs.

ListSnapshot = namedtuple(
    "ListSnapshot",
    "live_state frame recording target_runs attempt_runs match_runs notes key_inputs history live_key judgements "
    "last_pass position playing upcoming",
    defaults=(0.0, False, ()),
)
# One earlier attempt in the input list: its label, its key input grades as (start, end, grade, offset),
# when the track has no key inputs its per-frame match runs instead, and whether it's a saved attempt.
HistoryRow = namedtuple("HistoryRow", "label grades match_runs saved")


class PlayalongViews:
    """The display-facing half of PlayalongController (see playalong_views.py's docstring)."""

    def snapshot(self, count=PLAYALONG_FRAMELENGTH):
        """For the ring and arrow lanes displays: (live controller state, the next count frames to
        prompt, how far through the current frame the clock is). During a lead-in the frames start
        with neutral ones for the run-up, so the first inputs scroll in rather than wait."""
        with self._lock:
            if self._running_state == RunningState.RECORDING:
                return self._live_state, [], 0.0
            lead = min(self._lead, count)
            frames = [get_neutral_controller_state() for _ in range(lead)]
            frames += self._input_track[self._current_frame:self._current_frame + count - lead]
            frames += [get_neutral_controller_state() for _ in range(count - len(frames))]
            moving = self._running_state == RunningState.PLAYING
            offset = min(1.0, max(0.0, (time.perf_counter() - self._last_tick) * FPS)) if moving else 0.0
            return self._live_state, [map_state(frame, self._button_map) for frame in frames], offset

    def list_snapshot(self, frames_before, frames_after):
        """Target runs, attempt runs and per-frame matches around the playhead, for the input list.
        Besides the frame at the line, it gives the exact position in time, part way to the next
        frame, so moving lists can be drawn smoothly between ticks."""
        with self._lock:
            snapshot = self._list_snapshot(frames_before, frames_after)
            moving = self._running_state != RunningState.STOPPED
            progress = min(1.0, max(0.0, (time.perf_counter() - self._last_tick) * FPS)) if moving else 0.0
            return snapshot._replace(position=snapshot.frame + progress,
                                     playing=self._running_state == RunningState.PLAYING,
                                     upcoming=self._upcoming(snapshot.frame))

    def _upcoming(self, frame, count=3):
        """The next inputs to make from this frame, as (notation, start, end): the key inputs not yet
        over, or without any, the next changes of input in the recording. For the up-next panel."""
        with self._lock:
            if self._running_state == RunningState.RECORDING or not self._input_track:
                return ()
            if self._key_inputs:
                return tuple((describe(self._shown_key_input(k)), k["start"], k["end"])
                             for k in self._key_inputs if k["end"] >= frame)[:count]
            upcoming = []
            # A few seconds ahead is plenty to find the next few inputs (and keeps a long recording cheap).
            ahead = min(len(self._input_track), max(frame, 0) + UPCOMING_LOOKAHEAD)
            for start, length, key in runs_in_range(self._input_track, max(frame, 0), ahead):
                direction, buttons = self._shown_key(key, self._input_track, start)
                if (direction, buttons) == (5, ()) or start + length <= frame:
                    continue
                notation = ("" if direction == 5 else str(direction)) + "+".join(buttons)
                upcoming.append((notation, start, start + length - 1))
                if len(upcoming) == count:
                    break
            return tuple(upcoming)

    def _list_snapshot(self, frames_before, frames_after):
        with self._lock:
            recording = self._running_state == RunningState.RECORDING
            # During the run-up the view starts before frame 0, so the first inputs scroll in.
            frame = len(self._input_track) if recording else self._current_frame - self._lead
            lo, hi = frame - frames_before, frame + frames_after + 1
            if recording:
                return ListSnapshot(self._live_state, frame, True, self._shown_runs(self._input_track, lo, hi, False),
                                    [], [], [], [], [], self._live_key(), [], None)
            # A demo shows what it's sending where the attempt would go.
            shown = self._demo["track"] if self._demo else self._attempt_track
            return ListSnapshot(
                self._live_state, frame, False,
                self._shown_runs(self._input_track, lo, hi),
                self._shown_runs(shown, lo, hi),
                [] if self._demo else match_runs(self._input_track, self._attempt_track, lo, hi),
                [(i, note["start"], note["end"], note["text"]) for i, note in enumerate(self._notes)
                 if note["start"] < hi and note["end"] >= lo],
                [(i, self._shown_key_input(k), result(k, self._attempt_track, self._input_track),
                  best_hold(k, self._attempt_track) if k["hold"] and not k["exact"] else None)
                 for i, k in enumerate(self._key_inputs)
                 if k["start"] < hi and k["end"] >= lo],
                self._history_rows(lo, hi),
                self._live_key(),
                self._recent_judgements(),
                dict(self._last_pass) if self._last_pass else None,
            )

    def feedback(self):
        """(recent verdicts, the last pass) for displays that don't take a list snapshot."""
        with self._lock:
            return self._recent_judgements(), dict(self._last_pass) if self._last_pass else None

    def _recent_judgements(self, seconds=1.2):
        """(grade, offset, notation, age from 0 to 1) for judgements made in the last moment."""
        now = time.monotonic()
        return [(grade, offset, describe(self._shown_key_input(self._key_inputs[i])), (now - at) / seconds)
                for at, i, grade, offset in self._judgements if now - at < seconds and i < len(self._key_inputs)]

    def _actions_on(self):
        return self._show_actions and self._game in GAMES

    def _shown_key(self, key, track=None, start=0):
        """A run's (direction, buttons) as shown: the game's actions, or the player's buttons."""
        if not self._actions_on():
            return map_key(key, self._button_map)
        direction, pressed = key
        actions = to_actions(self._game, self._action_layout, pressed)
        window = normal_window(self._game)
        if window and track is not None and actions != to_actions(self._game, self._action_layout, pressed, True):
            actions = to_actions(self._game, self._action_layout, pressed, self._normal_before(track, start, window))
        return direction, tuple(actions)

    def _normal_before(self, track, frame, window):
        """Whether a normal attack (one of the game's single actions) was newly pressed in the frames
        just before this one. The last two frames don't count: pressing two buttons a frame apart is
        still pressing them together."""
        for f in range(max(1, frame - window), min(frame - 2, len(track))):
            now, before = track[f], track[f - 1]
            if now is not None and any(now[b] and not (before and before[b]) and b in self._action_layout
                                       for b in LIST_BUTTON_ORDER):
                return True
        return False

    def _shown_runs(self, track, lo, hi, with_context=True):
        return [(start, length, self._shown_key(key, track if with_context else None, start))
                for start, length, key in runs_in_range(track, lo, hi)]

    def _shown_key_input(self, key_input):
        if self._actions_on():
            return dict(key_input, buttons=to_actions(self._game, self._action_layout, key_input.get("buttons", [])))
        return map_key_input(key_input, self._button_map)

    def _live_key(self):
        """The player's live input as shown: their own buttons, or as the game's actions."""
        if not self._actions_on():
            return input_key(self._live_state)
        return self._shown_key(input_key(map_state(self._live_state, self._from_player)))

    def _grades(self, run):
        """The run's key input grades, cached until the key inputs or target change."""
        if run.get("_grades", (None,))[0] != self._grades_version:
            run["_grades"] = (self._grades_version, grade_all(self._key_inputs, run["attempt"], self._input_track))
        return run["_grades"][1]

    def _history_row(self, run, label, saved, lo, hi):
        if not self._key_inputs:
            return HistoryRow(label, [], match_runs(self._input_track, run["attempt"], lo, hi), saved)
        grades = [(k["start"], k["end"], grade, offset) for k, (grade, offset) in zip(self._key_inputs, self._grades(run))
                  if k["start"] < hi and k["end"] >= lo]
        return HistoryRow(label, grades, [], saved)

    def _history_rows(self, lo, hi):
        """Shown saved attempts, then the most recent history_count runs newest first, trimmed to
        frames lo..hi."""
        rows = [self._history_row(saved, saved["name"], True, lo, hi) for saved in self._saved if saved["shown"]]
        for run in reversed(self._runs[-self._history_count:] if self._history_count else []):
            rows.append(self._history_row(run, f"Run {run['id']}", False, lo, hi))
        return rows

