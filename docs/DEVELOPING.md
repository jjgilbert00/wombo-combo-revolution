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
