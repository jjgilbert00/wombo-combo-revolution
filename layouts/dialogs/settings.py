"""The Settings dialog: sections of steppers, pickers and switches (its rows come from
settings.dialog_columns).
"""
from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget

import theme
from layouts.ui_kit import (
    DIM_TEXT_COLOR, FONT_SIZE, PANEL_COLOR, TEXT_COLOR, Dialog, Stepper, OnOffSwitch, button, paint_background,
    dropdown, section_title
)


class SettingsPopup(Dialog):
    """Settings in sections, laid out in columns. columns is [[(section title, rows)]]; a row is
    (label, kind, choices, current value, on_change) where kind is "pick" (a dropdown, for named
    choices), "step" (‹ value ›, for ordered ones) or "switch" (on/off; choices unused)."""

    ROW = dp(40)
    COLUMN_WIDTH = dp(400)
    LABEL_WIDTH = dp(170)

    def __init__(self, columns, extra_buttons=(), **kwargs):
        """extra_buttons: (text, callback) for buttons beside Done, each closing the dialog first."""
        rows_height = max(sum(dp(30) + self.ROW * len(rows) for _, rows in column) for column in columns)
        super().__init__(size_hint=(None, None),
                         size=(self.COLUMN_WIDTH * len(columns) + dp(32) * len(columns) + dp(8),
                               rows_height + dp(130)),
                         background="", background_color=(0, 0, 0, 0.5), **kwargs)
        panel = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(8))
        paint_background(panel, PANEL_COLOR)
        panel.add_widget(Label(text="Settings", font_size=theme.TITLE, bold=True, color=TEXT_COLOR, size_hint_y=None,
                               height=dp(28), halign="left", valign="middle", text_size=(self.width - dp(40), dp(28))))
        body = BoxLayout(spacing=dp(32))
        for column in columns:
            box = BoxLayout(orientation="vertical", size_hint_x=None, width=self.COLUMN_WIDTH)
            for title, rows in column:
                box.add_widget(section_title(title, self.COLUMN_WIDTH))
                for label, kind, choices, current, on_change in rows:
                    box.add_widget(self._row(label, kind, choices, current, on_change))
            box.add_widget(Widget())
            body.add_widget(box)
        panel.add_widget(body)
        actions = BoxLayout(size_hint_y=None, height=dp(34))
        actions.add_widget(Label(text="Changes apply right away.", font_size=theme.CAPTION, color=DIM_TEXT_COLOR,
                                 halign="left", valign="middle", size_hint_x=None, width=dp(300),
                                 text_size=(dp(300), dp(34))))
        actions.add_widget(Widget())
        for text, callback in extra_buttons:
            actions.add_widget(button(text, lambda callback=callback: (self.dismiss(), callback())))
        actions.add_widget(button("Done", self.dismiss, "primary"))
        panel.add_widget(actions)
        self.add_widget(panel)

    def _row(self, label, kind, choices, current, on_change):
        row = BoxLayout(size_hint_y=None, height=self.ROW, padding=(0, dp(4)), spacing=dp(12))
        row.add_widget(Label(text=label, font_size=FONT_SIZE, color=TEXT_COLOR, halign="left", valign="middle",
                             size_hint_x=None, width=self.LABEL_WIDTH, text_size=(self.LABEL_WIDTH, None)))
        if kind == "switch":
            holder = AnchorLayout(anchor_x="left", anchor_y="center")
            holder.add_widget(OnOffSwitch(current, on_change))
            row.add_widget(holder)
        elif kind == "step":
            row.add_widget(Stepper(choices, current, on_change))
        else:
            labels = [text for text, _ in choices]
            values = dict(choices)
            selected = next((text for text, value in choices if value == current), labels[0])
            picker = dropdown(labels, selected, lambda text, cb=on_change, v=values: cb(v[text]))
            picker.size_hint_y = 1
            row.add_widget(picker)
        return row
