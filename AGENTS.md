# Wombo Combo

A Windows practice tool for fighting games (Python and Kivy). It records controller input 60 times a
second, alongside a screen capture. It plays recordings back as an input display, scores attempts
against their key inputs, and demos them through a virtual pad. Recordings are shared on Wombo Combo
Hub (`../wombo-combo-hub`). `docs/DEVELOPING.md` maps the code; `docs/USER_GUIDE.md` is what players
read.

## Who does what here

Code and designs in this repository are written with **Claude Code**, on `claude/...` branches
merged through pull requests. **Cursor's job here is adversarial review**: finding what's wrong
with that work before it merges. So in Cursor:

- **Don't edit code, commit or push** unless the user asks you to in that conversation. Claude Code
  sessions may be working in this checkout and on these branches.
- **Review with** `/adversarial-review <PR number>` (code) and `/design-review <PR number | file>`
  (designs). See `.cursor/skills/`.
- **Post findings on the pull request** (when the user agrees), so Claude Code can read and answer them
  there.

## Checking things

- **Static checks and unit tests,** for any PR's code without touching the checkout:
  `powershell -ExecutionPolicy Bypass -File .cursor/skills/adversarial-review/scripts/test-pr.ps1 <PR> [test file pattern]`.
  - It uses this checkout's `.venv`.
  - `-Keep` keeps the copy, for adding a test that proves a bug; then run the script with the copy's
    path instead of the PR number.
  - Tests are in `tests/`, and `tests/helpers.py` builds tracks.
- **Don't run the UI checks** (`tools/ui_check/`, or `tools/check_all.py` without `--unit`). They open
  the app's window on the user's display for minutes, and that screen is shared.

## What's easy to get wrong here

- **Two threads share the controller's state:** the sampler thread (`sampler.py`, 60 Hz) and the Kivy
  UI thread. That state is private behind a lock in `playalong.py`.
- **A frame is 1/60 s:** off-by-one frame errors are real bugs here, as is a sampler tick that takes
  too long.
- **Recordings are kept as if facing right** (`facing.py`), and a file says which side it was recorded
  from.
- **The file format is versioned** (`track_file.py`): older files must still open, and the hub reads
  the same format.
- **Recording files come from strangers** via the hub: opening one must never crash the app or do
  anything but load a recording.
