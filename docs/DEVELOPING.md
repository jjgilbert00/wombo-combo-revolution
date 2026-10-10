# Developing Wombo Combo

## Checking your changes

```
python tools/check_all.py
```

runs everything: the unit tests, then three UI checks that each open the app for a couple of minutes
(leave the mouse and keyboard alone while they run). It ends with "All checks passed." or a list
of what failed. `--unit` runs just the unit tests, which take about a second.

**Unit tests** (`tests/`) cover the rules with no UI: grading key inputs (`test_key_inputs.py`),
runs, matching, button maps and game actions (`test_input_list.py`), and the playalong controller
driven tick by tick, the way the sampler thread drives it (`test_playalong.py`). They use the
standard library's `unittest`; `tests/helpers.py` has builders such as `track((10, 5), (2, 2, "Y"))`
(ten neutral frames, then two of down + Y). Run one file with
`python -m unittest discover -s tests -t tests -p test_key_inputs.py`.

**UI checks** (`tools/ui_check/`) run the real app in-process and drive it from a script:
`harness.py` feeds it clicks and keys, stands in for the controller (`checks/pads.py`), takes
screenshots, and records PASS/FAIL lines. Settings start from defaults every run and are kept apart
from your own. Screenshots and the log land in `tools/ui_check/shots/`.

| Check | What it covers |
|---|---|
| `smoke` | A scored pass, the key input editor, remapping, game actions, saving attempts, overlay mode, help, cycling displays |
| `displays` | A practice pass in each of the three displays, the score banner, the hit flare |
| `overlay` | Overlay mode's window size with and without the card, across displays, the see-through background, and putting the window back |
| `docshots` | Not a check: regenerates the user guide's screenshots in `docs/images/` |

Run one with `python tools/ui_check/harness.py tools/ui_check/checks/overlay.py`. To write a new
one, copy a check: `steps(h)` is a generator that yields how long to wait between actions.

## Where things live

**The rules** (no UI; covered by the unit tests):

| File | What's in it |
|---|---|
| `key_inputs.py` | What a key input is, whether an attempt does it, and grading (hit, early, late, miss) |
| `input_list.py` | A track as runs of held input, and frame-by-frame matching |
| `button_map.py` | Remapping a recording's buttons to the player's |
| `games.py` | Game profiles: actions, combinations, layouts, and their icons |
| `playalong.py` | The controller: playing, recording, practice scoring, runs and saved attempts, demos. Its state is private behind a lock |
| `playalong_views.py` | What the displays are given to draw, from the controller's state |
| `playalong_state.py` | `RunningState`, and `PlayalongStatus` (the controller's `status()`) |
| `track_file.py` | Reading and writing recordings (the `.json` format, versioned) |

**Input and output:** `sampler.py` (the 60 Hz input thread) and `timing.py`, `controller.py`
(reading pads), `virtual_pad.py` (demos), `screen_capture.py` and `video_writer.py` (recording and
exporting video), `file_dialogs.py` (Windows' open and save pickers).

**The app:**

| File | What's in it |
|---|---|
| `main.py` | The app: builds the window and wires everything together; actions the menus, keys and dialogs call |
| `settings.py` | Every setting with its default and type, and the Settings dialog's contents |
| `keys.py` | Hotkeys, the window's shortcuts, and playing on the keyboard |
| `overlay.py` | Overlay mode's window: on top, opacity, see-through, fitting, putting it back |
| `guidance.py` | What the card, hint line and status bar say |
| `help_content.py` | What the Help dialog says |
| `theme.py` | Colours and type sizes |
| `glyphs.py` | The direction arrows, drawn |

**On screen** (`layouts/`):

| File | What's in it |
|---|---|
| `input_list_layout.py` | The input list display |
| `arrow_lanes_layout.py` | The arrow lanes display |
| `ring_layout.py` | The ring display |
| `falling.py` | Prompts falling down columns, with hold lines (arrow lanes, ring buttons) |
| `feedback.py` | Verdicts, the pass banner and the getting-started card, for every display |
| `menu_bar.py` | The menu bar |
| `dialogs/` | One module per dialog |
| `ui_kit.py` | The app's own buttons, toggles, pickers, menus, tooltips, status bar, and `Dialog` |
| `drawing.py` | Texture helpers shared by the displays |
