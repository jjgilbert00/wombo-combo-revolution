# Wombo Combo

Practise fighting game combos frame by frame. Record a combo from your controller (with a video of
the screen), mark the inputs that matter, then play along: the inputs scroll toward a line, you
press them as they arrive, and it shows exactly how early or late you were.

- **Three displays** to practise with: an input list like a training mode's, arrow lanes like a
  dance game, and a ring. **F3** switches.
- **Key inputs**: mark what must be pressed and when (presses, motions, holds such as a charge,
  exact spans). Only those are scored, each as hit, early, late or missed by so many frames.
- **Attempts**: every pass is kept and graded; save the ones worth keeping and replay them.
- **Overlay mode** (**F2**) puts the display over the game itself, see-through around what's drawn.
- **Demos**: a virtual controller plays the combo in game, as recorded or cleaned down to its key
  inputs.
- **Videos**: export the inputs on their own, or drawn over the recording's video.
- Notes, button remapping per recording, customisable keys, Street Fighter 6 actions (Drive Impact, Drive Parry...),
  sample combos, and keyboard play when there's no controller.

## Getting it

Download the latest release's `WomboCombo-windows.zip`, unzip it anywhere with a short path
(Downloads or the desktop are fine) and run `WomboCombo.exe`. No Python needed. The first time, it
opens a ten-second warm-up.

## Running from source

Windows, Python 3.10:

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

Demos in game also need `vgamepad` (`pip install vgamepad`), which installs the ViGEmBus driver.

## Documentation

- [User guide](docs/USER_GUIDE.md): everything the app does, and troubleshooting. **F1** in the app
  shows the keys.
- [Developing](docs/DEVELOPING.md): where things live in the code, and how to check changes
  (`python tools/check_all.py`).
- [Building a release](docs/BUILDING.md).
