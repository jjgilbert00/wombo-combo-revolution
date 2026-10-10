"""Input-list representation: a track as runs of "direction + buttons, held for N frames".

This is the fighting-game training-mode style of showing inputs. A new run starts whenever the
direction or any button changes.
"""

# Order buttons appear in within a run.
LIST_BUTTON_ORDER = ["X", "Y", "A", "B", "LB", "RB", "LT", "RT"]


# Runs are only followed this far past the visible range; longer holds are labelled "999+".
MAX_COUNT = 999


def input_key(state):
    return state["direction"], tuple(button for button in LIST_BUTTON_ORDER if state[button])


def runs_in_range(track, lo, hi):
    """Runs of identical input overlapping frames [lo, hi), as [(start, length, key), ...].

    Frames that are None (no data, e.g. parts of an attempt not played yet) are skipped. Runs are
    followed past the range so held counts stay correct.
    """
    lo, hi = max(lo, 0), min(hi, len(track))
    first, last = max(0, lo - MAX_COUNT), min(len(track), hi + MAX_COUNT)
    runs = []
    frame = lo
    while frame < hi:
        state = track[frame]
        if state is None:
            frame += 1
            continue
        start, end = frame, frame + 1
        if frame == lo:
            while start > first and track[start - 1] == state:
                start -= 1
        while end < last and track[end] == state:
            end += 1
        runs.append((start, end - start, input_key(state)))
        frame = end
    return runs


def match_runs(target, attempt, lo, hi):
    """Runs of frames where the attempt did or didn't match the target: [(start, length, matched)]."""
    lo, hi = max(lo, 0), min(hi, len(target), len(attempt))
    runs = []
    for frame in range(lo, hi):
        if attempt[frame] is None:
            continue
        matched = attempt[frame] == target[frame]
        if runs and runs[-1][0] + runs[-1][1] == frame and runs[-1][2] == matched:
            runs[-1] = (runs[-1][0], runs[-1][1] + 1, matched)
        else:
            runs.append((frame, 1, matched))
    return runs
