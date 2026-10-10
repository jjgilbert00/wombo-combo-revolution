"""Runs the app in-process and drives it from a check script, without real OS input.

usage: python tools/ui_check/harness.py tools/ui_check/checks/<check>.py [repository dir]

A check defines `def steps(h):`, a generator yielding seconds to wait between actions. `h` is this
Harness: h.app, h.click(x, y), h.drag(...), h.wheel(n), h.key(code, codepoint, modifiers), h.text(s),
h.shot(name), h.find(text), h.walk_all(), h.log(...) and h.check(label, ok, detail). Coordinates are
window pixels with y from the TOP (like screenshots). Logs go to shots/log.txt, screenshots to
shots/<name>.png. Settings come from a fresh harness.ini next to this file each run, so your real
settings are never touched. The exit code is the number of failed checks.
"""
import os
import runpy
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
STEPS = os.path.abspath(sys.argv[1])
WORKTREE = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.dirname(os.path.dirname(HERE))
SHOTS = os.path.join(HERE, "shots")
os.makedirs(SHOTS, exist_ok=True)
if os.path.exists(os.path.join(HERE, "harness.ini")):
    os.remove(os.path.join(HERE, "harness.ini"))  # Every run starts from the default settings.
os.chdir(WORKTREE)
sys.path.insert(0, WORKTREE)
sys.path.insert(1, HERE)
sys.path.insert(2, os.path.join(HERE, "checks"))

import main  # noqa: E402
from kivy.base import EventLoop  # noqa: E402
from kivy.clock import Clock  # noqa: E402
from kivy.core.window import Window  # noqa: E402
from kivy.input.motionevent import MotionEvent  # noqa: E402
from kivy.uix.textinput import TextInput  # noqa: E402
import layouts.input_list_layout as input_list_layout  # noqa: E402

_ids = iter(range(1000, 10**6))


class FakeTouch(MotionEvent):
    """A mouse event fed straight into Kivy; x/y are window pixels from the bottom-left."""

    def depack(self, args):
        self.is_touch = True
        self.sx = args["x"] / Window.width
        self.sy = args["y"] / Window.height
        self.button = args.get("button", "left")
        self.profile = ["pos", "button"]
        super().depack(args)


class Harness:
    def __init__(self, app):
        self.app = app
        self.modifiers = set()
        # The app asks Windows for Shift/Ctrl; answer from the harness instead.
        input_list_layout._modifier_held = lambda name: name in self.modifiers
        self.out = open(os.path.join(SHOTS, "log.txt"), "w")
        self.failures = 0

    def log(self, *args):
        print(*args, file=self.out, flush=True)
        print(*args, flush=True)

    def check(self, label, ok, detail=""):
        """Records a check: PASS or FAIL, with what was seen."""
        self.failures += not ok
        self.log("PASS" if ok else "FAIL", label, detail)

    def _touch(self, x, y, button="left"):
        return FakeTouch("harness", next(_ids), {"x": x, "y": Window.height - y, "button": button})

    def _dispatch(self, kind, touch):
        EventLoop.post_dispatch_input(kind, touch)

    def click(self, x, y):
        touch = self._touch(x, y)
        self._dispatch("begin", touch)
        self._dispatch("end", touch)

    def drag(self, x0, y0, x1, y1, steps=10):
        touch = self._touch(x0, y0)
        self._dispatch("begin", touch)
        for i in range(1, steps + 1):
            x = x0 + (x1 - x0) * i / steps
            y = y0 + (y1 - y0) * i / steps
            touch.move({"x": x, "y": Window.height - y, "button": "left"})
            self._dispatch("update", touch)
        self._dispatch("end", touch)

    def wheel(self, notches, x=900, y=300):
        button = "scrolldown" if notches > 0 else "scrollup"
        for _ in range(abs(notches)):
            touch = self._touch(x, y, button)
            self._dispatch("begin", touch)
            self._dispatch("end", touch)

    def key(self, code, codepoint="", modifiers=None):
        Window.dispatch("on_key_down", code, 0, codepoint, modifiers or [])
        Window.dispatch("on_key_up", code, 0)

    def text(self, value):
        """Types into whatever TextInput has focus."""
        for widget in self.walk_all():
            if isinstance(widget, TextInput) and widget.focus:
                widget.insert_text(value)
                return

    def walk_all(self):
        for child in list(Window.children):
            yield from child.walk()

    def find(self, text):
        return next((w for w in self.walk_all() if getattr(w, "text", None) == text), None)

    def shot(self, name):
        path = os.path.join(SHOTS, f"{name}.png")
        if os.path.exists(path):
            os.remove(path)  # Kivy won't overwrite: it would number a new file instead.
        made = Window.screenshot(name=path.replace("{", "{{").replace("}", "}}"))
        if made and os.path.abspath(made) != os.path.abspath(path):
            os.replace(made, path)  # Kivy numbers its screenshots; keep the name asked for.
        self.log("shot", path)


class HarnessApp(main.WomboComboApp):
    def get_application_config(self, *args):
        return os.path.join(HERE, "harness.ini")  # Keep the user's real settings untouched.

    def on_start(self):
        super().on_start()
        Window.size = (1880, 960)
        self.harness = Harness(self)
        self._steps = runpy.run_path(STEPS)["steps"](self.harness)
        Clock.schedule_once(self._advance, 0.5)

    def _advance(self, dt):
        try:
            wait = next(self._steps)
        except StopIteration:
            self.harness.log(f"done: {self.harness.failures} failed")
            self.stop()
            return
        except Exception:
            self.harness.failures += 1
            self.harness.log(traceback.format_exc())
            self.stop()
            return
        Clock.schedule_once(self._advance, wait or 0)


if __name__ == "__main__":
    app = HarnessApp()
    app.run()
    sys.exit(min(app.harness.failures, 100))
