"""A recording's game, and which recorded button is which of its actions."""
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.widget import Widget

import theme
from layouts.ui_kit import (
    DIM_TEXT_COLOR, FONT_SIZE, PANEL_COLOR, TEXT_COLOR, Dialog, button, dropdown, paint_background
)


NO_ACTION = "None"


class GameActionsPopup(Dialog):
    """Picks the recording's game and which recorded button is which of its actions, so the input
    list can show actions (a medium punch, a Drive Impact) instead of buttons. Changes apply at once
    through on_change(game, layout)."""

    ROW_HEIGHT = dp(34)

    def __init__(self, game_names, game, layout, actions, default_layouts, used, on_change, **kwargs):
        from images import get_standard_button_icon
        super().__init__(size_hint=(None, None), size=(dp(520), dp(200) + self.ROW_HEIGHT * 8),
                         background="", background_color=(0, 0, 0, 0.5), **kwargs)
        self.game_names, self.actions, self.default_layouts = game_names, actions, default_layouts
        self.game, self.layout = game, dict(layout)
        self.on_change = on_change
        self.spinners = {}
        self._updating = False
        panel = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(6))
        paint_background(panel, PANEL_COLOR)
        panel.add_widget(Label(text="Game actions for this recording", font_size=theme.TITLE, bold=True, color=TEXT_COLOR,
                               size_hint_y=None, height=dp(24), halign="left", text_size=(dp(488), None)))
        panel.add_widget(Label(text="Which action each recorded button is, in the layout it was recorded with. "
                                    "View > Show game actions switches the list to them.", font_size=theme.CAPTION,
                               color=DIM_TEXT_COLOR, size_hint_y=None, height=dp(32), halign="left", valign="middle",
                               text_size=(dp(488), dp(32))))
        names = [NO_ACTION] + list(game_names.values())
        row = BoxLayout(size_hint_y=None, height=self.ROW_HEIGHT, spacing=dp(10))
        row.add_widget(Label(text="Game", font_size=FONT_SIZE, color=TEXT_COLOR, halign="left", valign="middle",
                             size_hint_x=None, width=dp(120), text_size=(dp(120), self.ROW_HEIGHT)))
        self.game_spinner = dropdown(names, game_names.get(game, NO_ACTION), self._choose_game)
        self.game_spinner.size_hint_y = 1
        row.add_widget(self.game_spinner)
        panel.add_widget(row)
        for recorded in ("X", "Y", "A", "B", "LB", "RB", "LT", "RT"):
            row = BoxLayout(size_hint_y=None, height=self.ROW_HEIGHT, spacing=dp(10))
            row.add_widget(Image(source=get_standard_button_icon("XGamepad", "Alt", recorded), size_hint_x=None,
                                 width=dp(26)))
            count = used.get(recorded, 0)
            row.add_widget(Label(text=f"Recorded {recorded}", font_size=FONT_SIZE,
                                 color=TEXT_COLOR if count else DIM_TEXT_COLOR, halign="left", valign="middle",
                                 size_hint_x=None, width=dp(120), text_size=(dp(120), self.ROW_HEIGHT)))
            row.add_widget(Label(text=f"pressed {count}x" if count else "not used", font_size=theme.CAPTION,
                                 color=DIM_TEXT_COLOR, halign="left", valign="middle", size_hint_x=None, width=dp(80),
                                 text_size=(dp(80), self.ROW_HEIGHT)))
            spinner = dropdown([NO_ACTION], NO_ACTION, lambda action, recorded=recorded: self._choose(recorded, action))
            spinner.size_hint_y = 1
            self.spinners[recorded] = spinner
            row.add_widget(spinner)
            panel.add_widget(row)
        actions_row = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(8))
        actions_row.add_widget(button("Default layout", self._reset))
        actions_row.add_widget(Widget())
        actions_row.add_widget(button("Done", self.dismiss, "primary"))
        panel.add_widget(actions_row)
        self.add_widget(panel)
        self._refresh()

    def _refresh(self):
        self._updating = True
        choices = [NO_ACTION] + (self.actions[self.game] if self.game else [])
        for recorded, spinner in self.spinners.items():
            spinner.values = choices
            spinner.text = self.layout.get(recorded, NO_ACTION)
            spinner.disabled = not self.game
        self._updating = False

    def _choose_game(self, name):
        if self._updating:
            return
        game = next((key for key, value in self.game_names.items() if value == name), None)
        if game != self.game:
            self.game = game
            self.layout = dict(self.default_layouts.get(game, {}))
            self._changed()

    def _choose(self, recorded, action):
        if self._updating:
            return
        self.layout.pop(recorded, None)
        if action != NO_ACTION:
            # An action belongs to one button; the button that had it is left without one.
            for holder in [b for b, a in self.layout.items() if a == action]:
                del self.layout[holder]
            self.layout[recorded] = action
        self._changed()

    def _reset(self):
        self.layout = dict(self.default_layouts.get(self.game, {}))
        self._changed()

    def _changed(self):
        self._refresh()
        self.on_change(self.game, dict(self.layout))
