"""The recording file: a track and everything made for it, as a .json file next to its .mp4.

    {"version": 2,
     "fps": 60,
     "inputs": [frame, ...],              # the recording: one controller state per frame
     "attempt": [frame or null, ...],     # the player's last attempt, if any
     "notes": [...],                      # see PlayalongController
     "key_inputs": [...],                 # see key_inputs.py
     "saved_attempts": [...],             # attempts the player kept
     "button_map": {...},                 # recorded button -> the player's
     "game": "sf6", "action_layout": {...}}

Only "inputs" is required; empty parts are left out. Version 1 files are the same without
"version"; the oldest saves are a bare list of frames. load() reads all of them.

Reading and writing the file happens here and only here.
"""
import json

from sampler import FPS

VERSION = 2
PARTS = ("attempt", "notes", "key_inputs", "saved_attempts", "button_map", "game", "action_layout")


class TrackFileError(ValueError):
    """The file isn't a recording this app can read."""


def load(path):
    """The recording in a file, as a dict with "inputs" and whichever parts it has. Raises OSError if
    it can't be read, TrackFileError if it isn't a recording."""
    with open(path, "r") as fin:
        try:
            data = json.load(fin)
        except ValueError as e:
            raise TrackFileError(f"not a recording ({e})") from e
    if isinstance(data, list):  # The oldest saves: just the frames.
        data = {"inputs": data}
    if not isinstance(data, dict) or not isinstance(data.get("inputs"), list):
        raise TrackFileError("not a recording (no inputs)")
    if data.get("version", 1) > VERSION:
        raise TrackFileError(f"made by a newer version of the app (format {data['version']})")
    return data


def save(path, data):
    """Writes a recording: a dict with "inputs" and any parts (empty ones are left out)."""
    out = {"version": VERSION, "fps": FPS, "inputs": data["inputs"]}
    out.update({part: data[part] for part in PARTS if data.get(part)})
    with open(path, "w") as fout:
        json.dump(out, fout, indent=1, sort_keys=True)


def update(path, **parts):
    """Rewrites some parts of a saved recording (e.g. saved_attempts=...), keeping the rest."""
    data = load(path)
    data.update(parts)
    save(path, data)
