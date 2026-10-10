"""Remapping buttons for a recording: which of the player's buttons does what each recorded one did."""
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.widget import Widget

import theme
from layouts.ui_kit import (
    DIM_TEXT_COLOR, FONT_SIZE, PANEL_COLOR, TEXT_COLOR, Dialog, button, dropdown, paint_background
)


class ButtonMapPopup(Dialog):
    """Maps each recorded button to one of the player's. Picking a button that another recorded
    button already uses swaps the two, so the map stays one-to-one. Changes apply at once through
    on_change(mapping); used is how many times each recorded button is pressed in the recording."""

    ROW_HEIGHT = dp(36)

    def __init__(self, mapping, used, on_change, icon=None, **kwargs):
        from images import get_standard_button_icon
        icon = icon or (lambda name: get_standard_button_icon("XGamepad", "Alt", name))
        super().__init__(size_hint=(None, None), size=(dp(520), dp(150) + self.ROW_HEIGHT * len(mapping)),
                         background="", background_color=(0, 0, 0, 0.5), **kwargs)
        self.mapping = dict(mapping)
        self.on_change = on_change
        self.spinners = {}
        self._updating = False
        panel = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(6))
        paint_background(panel, PANEL_COLOR)
        panel.add_widget(Label(text="Remap buttons for this recording", font_size=theme.TITLE, bold=True, color=TEXT_COLOR,
                               size_hint_y=None, height=dp(24), halign="left", text_size=(dp(488), None)))
        panel.add_widget(Label(text="Pick the button you press for each recorded one. The list, scoring and demos "
                                    "follow your buttons.", font_size=theme.CAPTION, color=DIM_TEXT_COLOR, size_hint_y=None,
                               height=dp(32), halign="left", valign="middle", text_size=(dp(488), dp(32))))
        for recorded in mapping:
            row = BoxLayout(size_hint_y=None, height=self.ROW_HEIGHT, spacing=dp(10))
            row.add_widget(Image(source=icon(recorded), size_hint_x=None, width=dp(28)))
            count = used.get(recorded, 0)
            row.add_widget(Label(text=f"Recorded {recorded}", font_size=FONT_SIZE, color=TEXT_COLOR if count else
                                 DIM_TEXT_COLOR, halign="left", valign="middle", size_hint_x=None, width=dp(120),
                                 text_size=(dp(120), self.ROW_HEIGHT)))
            row.add_widget(Label(text=f"pressed {count}x" if count else "not used", font_size=theme.CAPTION,
                                 color=DIM_TEXT_COLOR, halign="left", valign="middle", size_hint_x=None, width=dp(80),
                                 text_size=(dp(80), self.ROW_HEIGHT)))
            row.add_widget(Label(text="->", font_size=FONT_SIZE, color=DIM_TEXT_COLOR, size_hint_x=None,
                                 width=dp(24)))
            spinner = dropdown(list(mapping), self.mapping[recorded],
                               lambda theirs, recorded=recorded: self._choose(recorded, theirs))
            spinner.size_hint_y = 1
            self.spinners[recorded] = spinner
            row.add_widget(spinner)
            panel.add_widget(row)
        actions = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(8))
        actions.add_widget(button("Reset to recorded", self._reset))
        actions.add_widget(Widget())
        actions.add_widget(button("Done", self.dismiss, "primary"))
        panel.add_widget(actions)
        self.add_widget(panel)

    def _choose(self, recorded, theirs):
        if self._updating or self.mapping[recorded] == theirs:
            return
        # Whichever recorded button had this one takes over the button being replaced.
        other = next(button for button, mapped in self.mapping.items() if mapped == theirs)
        self.mapping[other], self.mapping[recorded] = self.mapping[recorded], theirs
        self._apply()

    def _reset(self):
        self.mapping = {button: button for button in self.mapping}
        self._apply()

    def _apply(self):
        self._updating = True
        for recorded, spinner in self.spinners.items():
            spinner.text = self.mapping[recorded]
        self._updating = False
        self.on_change(dict(self.mapping))
