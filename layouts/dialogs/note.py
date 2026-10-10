"""The note editor: a note's text, for the frames it annotates."""
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

import theme
from layouts.ui_kit import FONT_SIZE, PANEL_COLOR, TEXT_COLOR, Dialog, button, confirm_button, paint_background


class NotePopup(Dialog):
    """Edits a note's text. on_save(text) is called with the new text; saving empty text counts as a
    delete. on_delete is only offered when editing an existing note."""

    def __init__(self, title, text, on_save, on_delete=None, **kwargs):
        super().__init__(size_hint=(None, None), size=(dp(420), dp(150)), background="",
                         background_color=(0, 0, 0, 0.5), **kwargs)
        panel = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))
        paint_background(panel, PANEL_COLOR)
        panel.add_widget(Label(text=title, font_size=theme.TITLE, bold=True, color=TEXT_COLOR, size_hint_y=None,
                               height=dp(22), halign="left", text_size=(dp(388), None)))
        self.input = TextInput(text=text, multiline=False, size_hint_y=None, height=dp(34), font_size=FONT_SIZE,
                               background_color=(1, 1, 1, 0.08), foreground_color=TEXT_COLOR,
                               cursor_color=TEXT_COLOR, hint_text="e.g. hit confirm here")
        self.input.bind(on_text_validate=lambda *_: self._save(on_save))
        panel.add_widget(self.input)

        buttons = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(8))
        if on_delete:
            buttons.add_widget(confirm_button("Delete", lambda: (self.dismiss(), on_delete())))
        buttons.add_widget(Widget())
        cancel = button("Cancel", self.dismiss, "ghost")
        save = button("Save", lambda: self._save(on_save), "primary")
        buttons.add_widget(cancel)
        buttons.add_widget(save)
        panel.add_widget(buttons)
        self.add_widget(panel)
        self.bind(on_open=lambda *_: setattr(self.input, "focus", True))

    def _save(self, on_save):
        self.dismiss()
        on_save(self.input.text.strip())
