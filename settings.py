"""The app's settings: every one named once here, with its default and type.

Settings live in Kivy's config file, in the [wombo] section. Read and change them through
Settings, by name: settings.lookahead, settings.set("lookahead", 2.0). A name that isn't listed here
is an error, rather than a silent fallback to a default.
"""

SECTION = "wombo"

# name: (default, comment)
DEFAULTS = {
    "controller": ("auto", "Which controller to read: a reader's name, or the first connected."),
    "capture_video": (True, "Capture the screen while recording inputs."),
    "display": (0, "Which screen to capture."),
    "video_height": (1080, "Captured video's height (0 keeps the screen's own)."),
    "encoder": ("auto", "Video encoder: auto, x264 or nvenc."),
    "overlay_delay": (4, "Frames to delay drawn inputs in overlay videos."),
    "export_overlay_on_save": (True, "Also write name_overlay.mp4 when saving a recording."),
    "opacity": (0.5, "How opaque overlay mode is."),
    "see_through": (True, "Overlay mode: only what's drawn covers the game, not the background."),
    "hit_sound": (False, "A tick for each key input hit while practising."),
    "loop": (True, "Playback repeats."),
    "practice": (True, "Playing scores the player (off: it replays their attempt)."),
    "lookahead": (1.5, "Seconds of input shown ahead of the line: the scroll speed."),
    "input_display": ("list", "The display showing: list, lanes or ring."),
    "show_notes": (True, "Notes show as cards (off: just bars over their frames)."),
    "show_actions": (True, "Show a game's actions (a medium punch, a Drive Impact) instead of buttons."),
    "show_next": (True, "The up-next panel left of the hit line."),
    "default_game": ("sf6", "Game for new recordings, and old ones that don't say."),
    "first_run": (True, "Opens the warm-up the first time the app starts."),
    "lanes": ("meter,target,keys,attempt,saved,recent", "Input list lanes shown, comma-separated."),
    "recent": ("", "Recently opened recordings (.json paths), newest first, separated by |."),
    "recent_attempts": (5, "Recent runs shown in the input list."),
    "lead_in": (60, "Frames of run-up before practice playback, to get ready."),
    "demo_countdown": (180, "Frames before a demo starts, to switch to the game."),
}


class Settings:
    """Typed access to the settings in a Kivy config: each comes back as its default's type."""

    def __init__(self, config):
        self.config = config

    @staticmethod
    def defaults():
        """For Kivy's build_config: the config file's defaults (bools as 0/1)."""
        return {name: int(default) if isinstance(default, bool) else default
                for name, (default, _) in DEFAULTS.items()}

    def __getattr__(self, name):
        if name not in DEFAULTS:
            raise AttributeError(f"No setting called {name!r}")
        default = DEFAULTS[name][0]
        if isinstance(default, bool):
            return self.config.getboolean(SECTION, name)
        if isinstance(default, int):
            return self.config.getint(SECTION, name)
        if isinstance(default, float):
            return self.config.getfloat(SECTION, name)
        return self.config.get(SECTION, name)

    def set(self, name, value, write=False):
        if name not in DEFAULTS:
            raise AttributeError(f"No setting called {name!r}")
        self.config.set(SECTION, name, int(value) if isinstance(value, bool) else value)
        if write:
            self.config.write()

    def toggle(self, name):
        """Flips an on/off setting; returns the new value."""
        value = not getattr(self, name)
        self.set(name, value)
        return value


# ---- The Settings dialog ------------------------------------------------------------------------

VIDEO_HEIGHTS = [("Native", 0), ("1080p", 1080), ("720p", 720)]
ENCODERS = [("Auto", "auto"), ("CPU (x264)", "x264"), ("NVIDIA (NVENC)", "nvenc")]


def dialog_columns(app, readers, displays, games):
    """The Settings dialog's contents (see SettingsPopup): sections of rows, in two columns. Each
    change is saved at once and applied through the app. readers are the controllers found,
    displays the screens [(index, size)], games the game profiles."""
    settings = app.settings

    def setter(name, apply=None):
        def on_change(value):
            settings.set(name, value, write=True)
            if apply:
                apply()
        return on_change

    def row(label, kind, choices, name, apply=None):
        current = getattr(settings, name)
        return label, kind, choices, current if kind == "switch" else str(current), setter(name, apply)

    practice = [
        row("Scroll speed", "step", [("Fast: 0.75 s ahead", "0.75"), ("1 s ahead", "1.0"), ("1.5 s ahead", "1.5"),
                                     ("2 s ahead", "2.0"), ("Slow: 3 s ahead", "3.0")],
            "lookahead", lambda: app.input_list_layout.set_lookahead(settings.lookahead)),
        row("Lead-in", "step", [("Off", "0"), ("0.5 s", "30"), ("1 s", "60"), ("2 s", "120")],
            "lead_in", lambda: setattr(app.playalong_controller, "lead_in", settings.lead_in)),
        row("Recent attempts shown", "step", [(str(n), str(n)) for n in (0, 1, 2, 3, 5, 8, 10, 15, 20)],
            "recent_attempts", lambda: app.playalong_controller.set_history_count(settings.recent_attempts)),
    ]
    controller = [
        row("Controller", "pick", [("First connected", "auto")] + [(r.name, r.name) for r in readers],
            "controller", app.select_controller),
        row("Game for new recordings", "pick", [("None", "")] + [(game["name"], key) for key, game in games.items()],
            "default_game"),
    ]
    sound_and_demo = [
        row("Hit sound", "switch", None, "hit_sound"),
        row("Demo countdown", "step", [("1 s", "60"), ("2 s", "120"), ("3 s", "180"), ("5 s", "300")],
            "demo_countdown"),
    ]
    recording = [
        row("Record video", "switch", None, "capture_video"),
        row("Capture display", "pick", [(f"Display {i + 1}  {size}", str(i)) for i, size in displays], "display"),
        row("Video size", "pick", [(label, str(h)) for label, h in VIDEO_HEIGHTS], "video_height"),
        row("Encoder", "pick", ENCODERS, "encoder"),
        row("Overlay input delay", "step", [(f"{n} frames", str(n)) for n in range(13)], "overlay_delay"),
        row("Export overlay on save", "switch", None, "export_overlay_on_save"),
    ]
    return [[("Practice", practice), ("Controller and game", controller), ("Sound and demo", sound_and_demo)],
            [("Recording and video", recording)]]
