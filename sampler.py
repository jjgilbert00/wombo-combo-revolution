import threading
import time
import logging

from controller import get_neutral_controller_state
from timing import PreciseSleeper

logger = logging.getLogger(__name__)

FPS = 60


class SamplerStats:
    def __init__(self):
        self.rate = 0.0  # Measured ticks per second over the last second.
        self.late_ticks = 0  # Frames skipped because the sampler woke up too late.
        self.worst_lateness_ms = 0.0


class InputSampler:
    """Polls the controller on a dedicated thread at a fixed rate anchored to wall-clock time.

    Frame n is due at start + n / fps, so timing never drifts and never depends on how fast the UI
    renders. If the thread wakes up late (e.g. a long GIL hold), the missed frames are still
    reported through `ticks` so recordings keep their real-time length.
    """

    def __init__(self, on_tick, fps=FPS):
        self.on_tick = on_tick  # Called on the sampler thread as on_tick(state, ticks).
        self.fps = fps
        self.reader = None  # Swapped by the UI thread; any object with poll() -> dict | None.
        # Optional: extra() -> dict | None of more input to merge in (e.g. the keyboard), and
        # on_menu(name) called when Start or Back is pressed (from the sampler thread).
        self.extra = None
        self.on_menu = None
        self._menu = (False, False)
        self.stats = SamplerStats()
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="InputSampler", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)

    def _poll(self):
        reader = self.reader
        state = (reader.poll() if reader else None) or get_neutral_controller_state()
        menu = getattr(reader, "menu", (False, False)) if reader else (False, False)
        for name, now, before in zip(("start", "back"), menu, self._menu):
            if now and not before and self.on_menu:
                self.on_menu(name)
        self._menu = menu
        extra = self.extra() if self.extra else None
        if extra:
            state = dict(state)
            for key, value in extra.items():
                if key == "direction":
                    if value != 5:
                        state["direction"] = value
                elif value:
                    state[key] = 1
        return state

    def _run(self):
        sleeper = PreciseSleeper()
        period = 1.0 / self.fps
        start = time.perf_counter()
        next_frame = 0
        window_start, window_ticks = start, 0
        try:
            while not self._stop.is_set():
                sleeper.sleep_until(start + next_frame * period)
                now = time.perf_counter()
                due_frame = int((now - start) / period)
                state = self._poll()
                ticks = due_frame - next_frame + 1
                if ticks > 1:
                    self.stats.late_ticks += ticks - 1
                    logger.debug("Sampler woke %.1f ms late, filled %d frame(s)", (now - start - next_frame * period) * 1000, ticks - 1)
                lateness_ms = (now - (start + next_frame * period)) * 1000
                self.stats.worst_lateness_ms = max(self.stats.worst_lateness_ms, lateness_ms)
                try:
                    self.on_tick(state, ticks)
                except Exception:
                    logger.exception("Sampler tick failed")
                next_frame = due_frame + 1

                window_ticks += ticks
                if now - window_start >= 1.0:
                    self.stats.rate = window_ticks / (now - window_start)
                    window_start, window_ticks = now, 0
        finally:
            sleeper.close()
