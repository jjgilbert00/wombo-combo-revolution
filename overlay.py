"""Overlay mode: the app's window on top of the game, borderless and see-through.

Everything about the window itself in overlay mode lives here: keeping it on top, its opacity, the
see-through background (a colour key Windows makes transparent), fitting its height to what the
input list draws, and putting it back exactly where it was afterwards. The window is moved through
Win32 directly; Kivy follows along.
"""
import win32api
import win32con
import win32gui
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp

import theme


def _hwnd():
    return Window.get_window_info().window


def _place(left, top, width, height):
    """Moves and sizes the window (in screen pixels), on top."""
    win32gui.SetWindowPos(_hwnd(), win32con.HWND_TOPMOST, left, top, width, height, win32con.SWP_NOACTIVATE)


def _set_on_top(on_top):
    flags = win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE
    win32gui.SetWindowPos(_hwnd(), win32con.HWND_TOPMOST if on_top else win32con.HWND_NOTOPMOST, 0, 0, 0, 0, flags)


class Overlay:
    """Overlay mode for the app's window.

    app provides: settings (opacity, see_through), input_list_layout, the current display (display),
    playalong_controller (for whether there are notes), set_bars_visible(visible) and
    set_background(rgb) (the window's background colour, for whatever follows it)."""

    def __init__(self, app):
        self.app = app
        self.active = False
        self._placement = None  # Windows' record of the normal window, to put it back exactly.
        self._origin = None  # (left, top, width) in screen pixels, while active.
        self._full_height = 0  # The window's height as it entered overlay mode.
        self._note_rows = 0  # Rows of notes the fitted window has room for (it only grows).

    # ---- Entering and leaving ------------------------------------------------------------------

    def toggle(self):
        self.leave() if self.active else self.enter()

    def enter(self):
        app, hwnd = self.app, _hwnd()
        self.active = True
        self._placement = win32gui.GetWindowPlacement(hwnd)
        left, top = win32gui.ClientToScreen(hwnd, (0, 0))
        _, _, width, height = win32gui.GetClientRect(hwnd)
        # The overlay sits where the window's content was, at the same width; fit() (every frame)
        # trims its height and puts it back there if the style change nudged it. Set before anything
        # below, which can run frames from inside Windows' message handling.
        self._origin = (left, top, width)
        self._full_height = height
        self._note_rows = 0
        # The window fits the list from here on, so the list keeps the size it has now.
        app.input_list_layout.freeze_scale = True
        if self._placement[1] == win32con.SW_SHOWMAXIMIZED:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)  # A maximized window can't be resized.
        Window.borderless = True
        self._apply_background()
        app.set_bars_visible(False)
        _place(left, top, width, height)
        Window.bind(on_draw=self._keep_on_top)
        self.preview_opacity(False)

    def leave(self):
        app, hwnd = self.app, _hwnd()
        self.active = False
        Window.unbind(on_draw=self._keep_on_top)
        Window.borderless = False
        app.set_bars_visible(True)
        _set_on_top(False)
        self._origin = None
        self._apply_background()
        app.input_list_layout.freeze_scale = False
        Clock.schedule_once(lambda dt: app.input_list_layout.rescale(), 0.3)
        # Put back exactly where it was. Again shortly after, as the border comes back after a delay
        # and would otherwise grow the window by its own size.
        placement = self._placement
        win32gui.SetWindowPlacement(hwnd, placement)
        Clock.schedule_once(lambda dt: self.active or win32gui.SetWindowPlacement(hwnd, placement), 0.15)
        self.preview_opacity(False)

    def _keep_on_top(self, *args):
        """Checked every frame, since changing the window (e.g. borderless) can drop it, but only
        reapplied when it has been dropped."""
        if not win32gui.GetWindowLong(_hwnd(), win32con.GWL_EXSTYLE) & win32con.WS_EX_TOPMOST:
            _set_on_top(True)

    # ---- Opacity and the see-through background ------------------------------------------------

    @property
    def see_through(self):
        return self.active and self.app.settings.see_through

    def set_opacity(self, opacity):
        self.app.settings.set("opacity", round(opacity, 2))
        self._apply_alpha(opacity)

    def preview_opacity(self, previewing):
        """The window is only see-through in overlay mode; the slider previews it while adjusting."""
        self._apply_alpha(self.app.settings.opacity if previewing or self.active else 1)

    def toggle_see_through(self):
        self.app.settings.toggle("see_through")
        if self.active:
            self._apply_background()
            if not self.see_through:  # Back to plain opacity.
                win32gui.SetLayeredWindowAttributes(_hwnd(), 0, round(self.app.settings.opacity * 255),
                                                    win32con.LWA_ALPHA)
            self.preview_opacity(False)

    def _apply_alpha(self, alpha):
        """The window's opacity, and when see-through, the background colour made transparent."""
        Window.opacity = alpha
        if not self.see_through:
            return
        hwnd = _hwnd()
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        if not style & win32con.WS_EX_LAYERED:
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style | win32con.WS_EX_LAYERED)
        key = win32api.RGB(*(round(c * 255) for c in theme.OVERLAY_KEY))
        win32gui.SetLayeredWindowAttributes(hwnd, key, round(alpha * 255), win32con.LWA_COLORKEY | win32con.LWA_ALPHA)

    def _apply_background(self):
        """See-through: the background is the colour key and the list drops its lane names and
        backgrounds. Otherwise the usual grey."""
        see_through = self.see_through
        background = theme.OVERLAY_KEY if see_through else theme.BACKGROUND
        Window.clearcolor = (*background, 1 if see_through else 0.5)
        self.app.set_background(background)
        self.app.input_list_layout.minimal = see_through

    # ---- Fitting the window --------------------------------------------------------------------

    def fit(self):
        """Every frame while active: trims the window to what the input list draws, so no empty space
        covers the game. It keeps its top edge, and grows again when more is shown (e.g. another
        attempt row). The arrow lanes and ring, and the getting-started card, keep the full height."""
        if not self._origin:
            return  # Still being set up (or torn down).
        left, top, width = self._origin
        layout = self.app.input_list_layout
        if self.app.display is not layout or layout.content_height(0) is None:
            self._keep(left, top, width, self._full_height)
            return
        # Room for as many rows of notes as have been needed so far: one to start with if there are
        # notes, more only if overlapping notes stack up. It doesn't shrink back, so the window
        # doesn't jump as notes scroll by.
        if layout.show_notes:
            wanted = 1 if self.app.playalong_controller.notes else 0
            self._note_rows = max(self._note_rows, wanted, layout.note_rows_used)
        else:
            self._note_rows = 0
        # Kivy measures in its own units; scale to pixels by the width, which doesn't change. In
        # overlay mode the list is the whole window (no bars), so its content is the window's height.
        # (Window and list sizes can disagree for a frame while the style changes; going by the
        # content alone keeps that from flinging the window to a huge size.)
        pixels = width / Window.width if Window.width else 1
        height = round(layout.content_height(self._note_rows) * pixels)
        self._keep(left, top, width, max(dp(60), min(height, win32api.GetSystemMetrics(1))))

    @staticmethod
    def _keep(left, top, width, height):
        """Moves the window there unless it's already (near enough) there."""
        actual = win32gui.GetWindowRect(_hwnd())
        if max(abs(a - b) for a, b in zip(actual, (left, top, left + width, top + height))) > 2:
            _place(left, top, width, height)
