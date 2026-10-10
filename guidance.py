"""What the app tells the player, worked out from where they are: the getting-started and coach
cards, the hint line, and the status bar's state.

Each function reads the app (it changes nothing), so the wording lives in one place, apart from the
code that does things.
"""
import time

import theme
from sampler import FPS
from theme import markup

WELCOME = (
    "[size=22sp][b]Wombo Combo[/b][/size]\n\n"
    "Practise fighting game combos frame by frame. The inputs scroll toward a line, you press them as they "
    "arrive, and it shows exactly how early or late you were.\n\n"
    "New here? The warm-up takes ten seconds."
)

COACH = (
    "[size=20sp][b]Ready when you are[/b][/size]\n\n"
    "Press [b]Space[/b] (or [b]Start[/b] on your controller). After a second to get ready, press each input "
    "as it reaches the white line.\n\n"
    "{controller}"
)

KEYBOARD_HINT = "[b]WASD[/b] moves, [b]U I O[/b] punch, [b]J K L[/b] kick"


def format_time(frames):
    seconds = frames / FPS
    return f"{int(seconds // 60)}:{seconds % 60:05.2f}"


def _has_controller(app):
    reader = app.sampler.reader
    return reader is not None and reader.connected


def card(app):
    """The card over the display: getting started with nothing loaded, or a first go at the warm-up
    until the player starts playing. Returns (text, buttons) with buttons as (label, callback,
    primary); ("", ()) for no card."""
    status = app.playalong_controller.status()
    if status.recording:
        return "", ()
    if not status.length:
        return WELCOME, (("Try the warm-up", app.try_warm_up, True),
                         ("Open a recording...", app.open_track, False),
                         ("Record your own (F8)", app.toggle_recording, False))
    if app.coaching and not status.playing:
        if _has_controller(app):
            note = f"Using [b]{app.sampler.reader.name}[/b]: press a button and it shows up under the line."
        else:
            note = (f"{markup('No controller found.', theme.WARNING, bold=True)} Plug one in (it's picked up by "
                    "itself), or play on the keyboard: [b]WASD[/b] to move, [b]U I O[/b] punches, [b]J K L[/b] kicks.")
        return COACH.format(controller=note), (("Start", app.play, True), ("Not now", app.skip_coaching, False))
    return "", ()


def hint(app):
    """One line on what to do next, for where the player is right now."""
    status = app.playalong_controller.status()
    if status.recording:
        return ("[b]Recording.[/b] Perform the combo, then press [b]F8[/b] (or Stop) to finish. "
                "F-key hotkeys work while the game has focus.")
    if not status.length:
        return ""
    demo, lead = status.demo, status.lead
    if demo:
        if lead:
            return (f"[b]Demo of the {demo}[/b] starts in {lead / FPS:.1f}s. Switch to the game: the virtual "
                    "controller has to be the one playing your character. [b]Space[/b] / [b]F7[/b] stops.")
        return (f"[b]Demo:[/b] the virtual controller is playing the {demo}; the You lane shows what it presses. "
                "[b]Space[/b] / [b]F7[/b] stops.")
    if app.selection:
        return ("[b]Frames selected.[/b] [b]N[/b] adds a note, [b]K[/b] marks what must be pressed there "
                "(a key input), right-click for more, [b]Esc[/b] clears.")
    if lead:
        return f"[b]Get ready.[/b] The first input reaches the line in {lead / FPS:.1f}s."
    if status.playing:
        if status.practice:
            keys = "" if _has_controller(app) else f" No controller: {KEYBOARD_HINT}."
            return ("[b]Practising.[/b] Press each input as it reaches the line. [b]Start[/b] / [b]Space[/b] "
                    "pauses, [b]Back[/b] / [b]Home[/b] starts over." + keys)
        return "[b]Reviewing[/b] your attempt against the recording. [b]F4[/b] goes back to practice."
    if status.attempted:
        return ("Scroll or drag to look back at your attempt. [b]S[/b] saves it, [b]A[/b] lists all "
                "attempts, [b]Space[/b] practises again.")
    if not status.key_inputs:
        return ("Press [b]Space[/b] (or [b]F6[/b] in game) to practise. Tip: drag in the frame meter to select "
                "frames and press [b]K[/b] to mark what really matters; only those are scored then.")
    return ("Press [b]Space[/b] (or [b]F6[/b] in game) to practise. Hit the key inputs (outlined) as they "
            "reach the line.")


def status(app):
    """The status bar's right side: the mode and time, the score, flags, messages and the controller."""
    status = app.playalong_controller.status()
    frames = status.length
    parts = []
    if status.recording:
        parts.append(f"{markup('REC', theme.DANGER, bold=True)} {format_time(frames)}")
        if status.filled:
            parts.append(markup(f"{status.filled} late frames", theme.WARNING))
        backlog = app.screen_recorder.backlog() if app.screen_recorder else 0
        if backlog > FPS // 2:
            parts.append(markup(f"encoder {backlog / FPS:.1f}s behind", theme.WARNING))
    elif frames:
        demo, lead = status.demo, status.lead
        if demo:
            state = f"DEMO IN {lead / FPS:.1f}s" if lead else f"DEMO ({demo})"
        elif lead:
            state = "GET READY"
        elif status.playing:
            state = "PRACTICE" if status.practice else "REVIEW"
        else:
            state = "PAUSED"
        parts.append(f"{state} {format_time(status.frame)} / {format_time(frames)}")
        hits, total = status.hits, status.key_inputs
        attempted, matched = status.attempted, status.matched
        if total:
            parts.append(f"Key inputs {hits}/{total}")  # With key inputs marked, only they count.
        elif attempted:
            parts.append(f"Match {matched / attempted:.0%} of {attempted}f")
        if status.remapped:
            parts.append(markup("Buttons remapped", theme.INFO))
        if app.unsaved_take or app.unsaved_edits:
            parts.append(markup("Unsaved", theme.WARNING))
    else:
        parts.append("No track")
    if app.job_label:
        progress = f" {int(app.job_progress * 100)}%" if app.job_progress is not None else "..."
        parts.append(f"{app.job_label}{progress}")
    if app.selection:
        start, end = app.selection
        span = f"frame {start}" if start == end else f"frames {start}-{end} ({end - start + 1}f)"
        parts.append(markup(f"Selected {span}", theme.INFO))
    if app.message and time.time() < app.message[1]:
        parts.append(app.message[0])
    parts.append(app.sampler.reader.name if _has_controller(app) else markup("No controller", theme.WARNING))
    rate = app.sampler.stats.rate
    if rate and abs(rate - FPS) > 2:  # Only when input timing is off.
        parts.append(markup(f"Input at {rate:.0f} Hz", theme.WARNING))
    return markup("  ·  ", theme.TEXT_FAINT).join(parts)
