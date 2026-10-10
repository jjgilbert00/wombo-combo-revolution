"""The Help dialog (F1): getting started and the keys, in two tabs (its content comes from
help_content.py).
"""
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget

import theme
from layouts.ui_kit import (
    DIM_TEXT_COLOR, FONT_SIZE, PANEL_COLOR, TEXT_COLOR, Chip, Dialog, button, paint_background, section_title
)


class HelpPopup(Dialog):
    """Help in two tabs. Getting started: the steps, then legends for what the colours mean. Keys:
    groups of (key, what it does, works in game) in columns. on_manual opens the user guide."""

    KEY_WIDTH = dp(110)
    COLUMN_WIDTH = dp(440)
    ROW = dp(26)

    def __init__(self, steps, legends, key_columns, on_manual, **kwargs):
        rows = max(sum(len(group) + 1.5 for _, group in column) for column in key_columns)
        super().__init__(size_hint=(None, None), size=(dp(960), dp(150) + self.ROW * rows),
                         background="", background_color=(0, 0, 0, 0.5), **kwargs)
        panel = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(10))
        paint_background(panel, PANEL_COLOR)
        tabs = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(4))
        self.pages = {"Getting started": self._getting_started(steps, legends), "Keys": self._keys(key_columns)}
        self.tab_buttons = {}
        for name in self.pages:
            tab = Chip(text=name)
            tab.bind(on_release=lambda *_, name=name: self.show(name))
            self.tab_buttons[name] = tab
            tabs.add_widget(tab)
        tabs.add_widget(Widget())
        panel.add_widget(tabs)
        self.page_holder = BoxLayout()
        panel.add_widget(self.page_holder)
        actions = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(8))
        actions.add_widget(self._label("Hover over any button for a tip. The user guide covers everything in detail.",
                                       theme.CAPTION, DIM_TEXT_COLOR, dp(34)))
        actions.add_widget(button("Open user guide", lambda: (self.dismiss(), on_manual())))
        actions.add_widget(button("Close", self.dismiss, "primary"))
        panel.add_widget(actions)
        self.add_widget(panel)
        self.show("Getting started")

    def show(self, name):
        self.page_holder.clear_widgets()
        self.page_holder.add_widget(self.pages[name])
        for tab_name, tab in self.tab_buttons.items():
            tab.active = tab_name == name

    def _getting_started(self, steps, legends):
        page = BoxLayout(orientation="vertical", spacing=dp(6))
        for number, step in enumerate(steps, 1):
            page.add_widget(self._label(f"[b]{number}.[/b]  {step}", FONT_SIZE, TEXT_COLOR, dp(30), markup=True))
        body = BoxLayout(spacing=dp(32), padding=(0, dp(8), 0, 0))
        for title, items in legends:
            box = BoxLayout(orientation="vertical", spacing=dp(2))
            box.add_widget(section_title(title, self.COLUMN_WIDTH))
            for color, name, description in items:
                row = BoxLayout(size_hint_y=None, height=self.ROW, spacing=dp(10))
                swatch = Widget(size_hint=(None, None), size=(dp(28), dp(14)))
                with swatch.canvas:
                    Color(*color[:3])
                    rect = Rectangle(size=swatch.size)
                swatch.bind(pos=lambda w, pos, r=rect: setattr(r, "pos", pos),
                            size=lambda w, size, r=rect: setattr(r, "size", size))
                holder = AnchorLayout(size_hint_x=None, width=dp(28))
                holder.add_widget(swatch)
                row.add_widget(holder)
                row.add_widget(Label(text=name, font_size=FONT_SIZE, bold=True, color=TEXT_COLOR, halign="left",
                                     valign="middle", size_hint_x=None, width=dp(90), text_size=(dp(90), self.ROW)))
                row.add_widget(self._label(description, FONT_SIZE, DIM_TEXT_COLOR, self.ROW))
                box.add_widget(row)
            box.add_widget(Widget())
            body.add_widget(box)
        page.add_widget(body)
        return page

    def _keys(self, key_columns):
        page = BoxLayout(spacing=dp(32))
        for column in key_columns:
            box = BoxLayout(orientation="vertical", spacing=dp(1))
            for title, group in column:
                box.add_widget(section_title(title, self.COLUMN_WIDTH))
                for key, description, in_game in group:
                    row = BoxLayout(size_hint_y=None, height=self.ROW)
                    row.add_widget(Label(text=key, font_size=FONT_SIZE, bold=True, color=(*theme.ACCENT, 1),
                                         size_hint_x=None, width=self.KEY_WIDTH, halign="left", valign="middle",
                                         text_size=(self.KEY_WIDTH, self.ROW)))
                    text = description + ("   " + theme.markup("in game too", theme.TEXT_FAINT) if in_game else "")
                    row.add_widget(self._label(text, FONT_SIZE, TEXT_COLOR, self.ROW, markup=True))
                    box.add_widget(row)
            box.add_widget(Widget())
            page.add_widget(box)
        return page

    @staticmethod
    def _label(text, font_size, color, height, bold=False, markup=False, valign="middle"):
        label = Label(text=text, font_size=font_size, color=color, bold=bold, markup=markup, size_hint_y=None,
                      height=height, halign="left", valign=valign, shorten=True)
        label.bind(size=lambda l, size: setattr(l, "text_size", size))
        return label
