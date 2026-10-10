"""Changing the keys: each action's hotkey (works in game too) and shortcut (works in this window)."""
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget

import keys
import theme
from layouts.ui_kit import (
    DIM_TEXT_COLOR, FONT_SIZE, PANEL_COLOR, TEXT_COLOR, Dialog, button, confirm_button, paint_background,
    section_title
)

KIND_NAMES = {keys.HOTKEY: "hotkey", keys.SHORTCUT: "shortcut"}
NO_KEY = "-"
# Kivy's codes for Shift, Ctrl, Alt and the Windows keys: pressed on their own, they wait for the key.
MODIFIER_CODES = range(303, 314)
GAME_LETTERS = {"W", "A", "S", "D", "U", "I", "O", "J", "K", "L"}


class KeysPopup(Dialog):
    """The actions in groups, two columns of them, each with its hotkey and shortcut. Clicking one
    waits for the new key (any key, Esc included: clicking it again cancels); a key another action
    had moves here. Changes apply at once through on_change(bindings); on_capture(waiting) says
    when it's waiting for a key, so the app can hold its hotkeys meanwhile."""

    ROW = dp(30)
    ACTION_WIDTH = dp(270)
    KEY_WIDTH = dp(104)
    COLUMN_WIDTH = ACTION_WIDTH + 2 * (KEY_WIDTH + dp(8))

    def __init__(self, bindings, on_change, on_capture=lambda waiting: None, **kwargs):
        columns = [keys.ACTION_GROUPS[:2], keys.ACTION_GROUPS[2:]]
        rows_height = max(sum(dp(30) + self.ROW * len(actions) for _, actions in column) for column in columns)
        width = self.COLUMN_WIDTH * 2 + dp(32) + dp(40)
        super().__init__(size_hint=(None, None), size=(width, rows_height + dp(200)),
                         background="", background_color=(0, 0, 0, 0.5), **kwargs)
        self.bindings = bindings
        self.on_change = on_change
        self.on_capture = on_capture
        self.waiting = None  # The (kind, method) waiting for a key.
        self.cells = {}
        panel = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(8))
        paint_background(panel, PANEL_COLOR)
        text_width = width - dp(40)
        panel.add_widget(Label(text="Keys", font_size=theme.TITLE, bold=True, color=TEXT_COLOR, size_hint_y=None,
                               height=dp(28), halign="left", valign="middle", text_size=(text_width, dp(28))))
        panel.add_widget(Label(
            text="Click a key to change it, then press the new one (with Ctrl, Shift or Alt if you like). "
                 "[b]Hotkeys[/b] work even while the game has focus; [b]shortcuts[/b] work in this window.",
            markup=True, font_size=theme.CAPTION, color=DIM_TEXT_COLOR, size_hint_y=None, height=dp(34),
            halign="left", valign="middle", text_size=(text_width, dp(34))))
        body = BoxLayout(spacing=dp(32))
        for column in columns:
            box = BoxLayout(orientation="vertical", spacing=dp(2), size_hint_x=None, width=self.COLUMN_WIDTH)
            for title, actions in column:
                box.add_widget(self._group_header(title))
                for method, description, _, _ in actions:
                    box.add_widget(self._row(method, description))
            box.add_widget(Widget())
            body.add_widget(box)
        panel.add_widget(body)
        self.message = Label(text="", markup=True, font_size=FONT_SIZE, color=TEXT_COLOR, size_hint_y=None,
                             height=dp(28), halign="left", valign="middle", text_size=(text_width, dp(28)))
        panel.add_widget(self.message)
        actions = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(8))
        actions.add_widget(confirm_button("Reset all to defaults", self._reset))
        actions.add_widget(Widget())
        self.clear_button = button("No key", self._clear)
        self.clear_button.disabled = True
        actions.add_widget(self.clear_button)
        actions.add_widget(button("Done", self.dismiss, "primary"))
        panel.add_widget(actions)
        self.add_widget(panel)
        self._show_message("")

    def _group_header(self, title):
        header = BoxLayout(size_hint_y=None, height=dp(30))
        header.add_widget(section_title(title, self.ACTION_WIDTH))
        for text in ("Hotkey", "Shortcut"):
            header.add_widget(Label(text=text, font_size=theme.CAPTION, color=DIM_TEXT_COLOR, size_hint_x=None,
                                    width=self.KEY_WIDTH + dp(8), valign="bottom", text_size=(self.KEY_WIDTH, dp(30))))
        return header

    def _row(self, method, description):
        row = BoxLayout(size_hint_y=None, height=self.ROW, spacing=dp(8))
        row.add_widget(Label(text=description, font_size=FONT_SIZE, color=TEXT_COLOR, halign="left", valign="middle",
                             size_hint_x=None, width=self.ACTION_WIDTH - dp(8), shorten=True,
                             text_size=(self.ACTION_WIDTH - dp(8), self.ROW)))
        for kind in (keys.HOTKEY, keys.SHORTCUT):
            cell = button(NO_KEY, lambda kind=kind: self._click(kind, method), size_hint_x=None, width=self.KEY_WIDTH)
            self.cells[(kind, method)] = cell
            row.add_widget(cell)
        self._refresh_cells(row_only=(method,))
        return row

    # ---- Waiting for a key -------------------------------------------------------------------

    def on_open(self):
        Window.bind(on_key_down=self._on_key_down)

    def on_dismiss(self):
        Window.unbind(on_key_down=self._on_key_down)
        self._stop_waiting()

    def _click(self, kind, method):
        if self.waiting == (kind, method):
            self._stop_waiting()
            self._show_message("")
            return
        self._stop_waiting()
        self.waiting = (kind, method)
        self.on_capture(True)
        self.clear_button.disabled = False
        cell = self.cells[self.waiting]
        cell.text, cell.kind = "Press a key", "primary"
        self._show_message(f"Press the new {KIND_NAMES[kind]} for [b]{keys.DESCRIPTIONS[method]}[/b]. "
                           "Click it again to cancel.")

    def _stop_waiting(self):
        if self.waiting:
            self.waiting = None
            self.on_capture(False)
        self.clear_button.disabled = True
        self._refresh_cells()

    def _on_key_down(self, window, key, scancode, codepoint, modifiers):
        """While waiting, every key is the new one (returning True keeps it from anything else, Esc
        closing the dialog included)."""
        if not self.waiting:
            return False
        if key in MODIFIER_CODES:
            return True  # Wait for the key itself.
        name = keys.key_name(key, [m for m in modifiers if m not in keys.LOCKS])
        kind, method = self.waiting
        if name is None:
            self._show_message("That key can't be used for an action: try a letter, number, F key or "
                               "Space, Esc, Home and so on.", warning=True)
            return True
        problem = keys.problem(kind, name)
        if problem:
            self._show_message(f"{problem}.", warning=True)
            return True
        self._assign(kind, method, name)
        return True

    def _clear(self):
        if self.waiting:
            self._assign(*self.waiting, "")

    def _assign(self, kind, method, name):
        self.bindings, moved = self.bindings.assign(kind, method, name)
        self._stop_waiting()
        what = f"[b]{keys.DESCRIPTIONS[method]}[/b]"
        if not name:
            message = f"{what} has no {KIND_NAMES[kind]} now."
        else:
            message = f"[b]{name}[/b] is now the {KIND_NAMES[kind]} for {what}."
        if moved:
            message += f" It was the {KIND_NAMES[moved[0]]} for [b]{keys.DESCRIPTIONS[moved[1]]}[/b], which has none now."
        if kind == keys.SHORTCUT and name in GAME_LETTERS:
            message += f" While you practise on the keyboard, {name} plays instead."
        self._show_message(message)
        self.on_change(self.bindings)

    def _reset(self):
        self.bindings = keys.Bindings()
        self._stop_waiting()
        self._show_message("All keys are back to their defaults.")
        self.on_change(self.bindings)

    # ---- Showing -----------------------------------------------------------------------------

    def _refresh_cells(self, row_only=None):
        for (kind, method), cell in self.cells.items():
            if row_only and method not in row_only:
                continue
            name = self.bindings.get(kind, method)
            cell.text = name or NO_KEY
            cell.kind = "secondary"

    def _show_message(self, text, warning=False):
        self.message.text = text or "Click a key to change it."
        self.message.color = (*theme.WARNING, 1) if warning else (TEXT_COLOR if text else DIM_TEXT_COLOR)
