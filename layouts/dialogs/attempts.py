"""The attempts manager: saved attempts and recent runs, to rename, show, replay or delete."""
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

import theme
from layouts.ui_kit import (
    DIM_TEXT_COLOR, FONT_SIZE, PANEL_COLOR, TEXT_COLOR, Dialog, Toggle, button, confirm_button,
    paint_background
)


class AttemptsPopup(Dialog):
    """Manages saved attempts and recent runs: rename, show or hide saved ones in the input list,
    save a recent run, replay any of them against the target, or delete. Deleting takes a second
    click. `app` provides attempts_overview() and the actions; the list is rebuilt after each one."""

    ROW_HEIGHT = dp(32)

    def __init__(self, app, **kwargs):
        super().__init__(size_hint=(None, None), size=(dp(760), dp(560)), background="",
                         background_color=(0, 0, 0, 0.5), **kwargs)
        self.app = app
        panel = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))
        paint_background(panel, PANEL_COLOR)
        header = BoxLayout(size_hint_y=None, height=dp(24))
        header.add_widget(Label(text="Attempts", font_size=theme.TITLE, bold=True, color=TEXT_COLOR, halign="left",
                                valign="middle", size_hint_x=None, width=dp(120), text_size=(dp(120), dp(24))))
        header.add_widget(Label(text="Saved attempts are kept in the track's file. Replay plays one against the "
                                     "recording; F4 goes back to practice.", font_size=theme.CAPTION, color=DIM_TEXT_COLOR,
                                halign="right", valign="middle", text_size=(dp(600), dp(24))))
        panel.add_widget(header)
        self.rows = GridLayout(cols=1, size_hint_y=None, spacing=dp(4))
        self.rows.bind(minimum_height=self.rows.setter("height"))
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(6))
        scroll.add_widget(self.rows)
        panel.add_widget(scroll)
        actions = BoxLayout(size_hint_y=None, height=self.ROW_HEIGHT)
        actions.add_widget(Widget())
        actions.add_widget(button("Close", self.dismiss, "primary"))
        panel.add_widget(actions)
        self.add_widget(panel)
        self.refresh()

    def refresh(self):
        self.rows.clear_widgets()
        overview = self.app.attempts_overview()
        self._section("Saved", overview["saved"], "Nothing saved yet: press S to save the attempt on screen.")
        self._section("Recent (this session, newest first)", overview["recent"],
                      "No runs yet: practice (F4) and play; each pass is kept here.")

    def _section(self, title, attempts, empty_text):
        self.rows.add_widget(Label(text=title, font_size=FONT_SIZE, bold=True, color=TEXT_COLOR, halign="left",
                                   valign="bottom", size_hint_y=None, height=dp(28), text_size=(dp(720), dp(28))))
        if not attempts:
            empty = self._text(empty_text, DIM_TEXT_COLOR, None)
            empty.size_hint_y, empty.height = None, self.ROW_HEIGHT
            self.rows.add_widget(empty)
        for attempt in attempts:
            self.rows.add_widget(self._row(attempt))

    def _text(self, text, color, width):
        label = Label(text=text, font_size=FONT_SIZE, color=color, halign="left", valign="middle",
                      size_hint_x=None if width else 1, width=width or 100, shorten=True)
        label.bind(size=lambda l, size: setattr(l, "text_size", size))
        return label

    def _button(self, text, callback):
        return button(text, callback)

    def _row(self, attempt):
        kind, attempt_id = attempt["kind"], attempt["id"]
        row = BoxLayout(size_hint_y=None, height=self.ROW_HEIGHT, spacing=dp(8))
        if kind == "saved":
            name = TextInput(text=attempt["name"], multiline=False, font_size=FONT_SIZE, size_hint_x=None,
                             width=dp(220), background_color=(1, 1, 1, 0.08), foreground_color=TEXT_COLOR,
                             cursor_color=TEXT_COLOR, padding=(dp(6), dp(7)))
            rename = lambda *_: self.app.rename_saved(attempt_id, name.text) if name.text.strip() else None
            name.bind(on_text_validate=rename, focus=lambda _, focused: None if focused else rename())
            row.add_widget(name)
        else:
            row.add_widget(self._text(attempt["name"], TEXT_COLOR, dp(220)))
        row.add_widget(self._text(attempt["score"], TEXT_COLOR, dp(110)))
        row.add_widget(self._text(attempt["when"], DIM_TEXT_COLOR, dp(110)))
        row.add_widget(Widget())
        if kind == "saved":
            shown = Toggle(text="Shown" if attempt["shown"] else "Hidden", size_hint_x=None, width=dp(70),
                            state="down" if attempt["shown"] else "normal")
            shown.bind(state=lambda t, state: (self.app.show_saved(attempt_id, state == "down"),
                                               setattr(t, "text", "Shown" if state == "down" else "Hidden")))
            row.add_widget(shown)
        else:
            row.add_widget(self._button("Save", lambda: (self.app.save_run(attempt_id), self.refresh())))
        row.add_widget(self._button("Replay", lambda: (self.dismiss(), self.app.replay_attempt(kind, attempt_id))))
        row.add_widget(confirm_button("Delete", lambda: (self.app.delete_attempt(kind, attempt_id), self.refresh())))
        return row
