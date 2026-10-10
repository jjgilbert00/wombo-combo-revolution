"""A tour of the main features: a scored pass, the editors, attempts, overlay mode and help."""
import os
import shutil

from pads import WarmUpPad, popup, use_pad

HERE = os.path.dirname(os.path.abspath(__file__))


def steps(h):
    c = h.app.playalong_controller
    # Work on a copy, so nothing is saved into the real samples.
    path = os.path.join(HERE, "..", "shots", "smoke_warmup.json")
    shutil.copy(os.path.join(os.getcwd(), "samples", "Warm-up - LP, MP, HP, Hadoken.json"), path)
    h.app.open_track(path); yield 0.3
    use_pad(h.app, WarmUpPad(c))
    h.app.play()
    while c.get_last_pass() is None:
        yield 0.05
    h.check("a perfect pass scores 4/4", (c.get_last_pass()["hits"], c.get_last_pass()["total"]) == (4, 4),
            (c.get_last_pass()["hits"], c.get_last_pass()["total"]))
    h.app.pause(); yield 0.2
    h.app.set_selection(40, 46); h.key(107, "k"); yield 0.4
    p = popup(h, "KeyInputPopup")
    h.check("K opens the key input editor on the selection", p is not None and p.key_input["buttons"] == ["X"])
    p.dismiss(); yield 0.2
    notes_before = len(c.get_notes())
    h.app.set_selection(70, 72); h.key(110, "n"); yield 0.4
    p = popup(h, "NotePopup")
    h.check("N opens the note editor", p is not None)
    p.input.text = "smoke test note"
    next(w for w in p.walk() if getattr(w, "text", None) == "Save").dispatch("on_release"); yield 0.2
    h.check("saving it adds the note", len(c.get_notes()) == notes_before + 1, len(c.get_notes()))
    h.app.set_selection(None)
    h.app.remap_buttons(); yield 0.3
    p = popup(h, "ButtonMapPopup")
    p.spinners["X"].text = "LB"; yield 0.1
    h.check("remapping swaps buttons", c.get_button_map() == {"X": "LB", "LB": "X"}, c.get_button_map())
    p.dismiss(); yield 0.2
    h.app.set_button_map({}); yield 0.1
    h.app.edit_game_actions(); yield 0.3
    p = popup(h, "GameActionsPopup")
    h.check("game actions dialog opens", p is not None)
    p.dismiss(); yield 0.2
    h.key(115, "s"); yield 0.3
    h.app.open_attempts(); yield 0.3
    p = popup(h, "AttemptsPopup")
    h.check("S saves the attempt", len(c.get_saved_attempts()) == 1 and p is not None)
    p.dismiss(); yield 0.2
    h.app.toggle_overlay(); yield 0.5
    h.check("F2 enters overlay mode", h.app.overlay.active)
    h.app.toggle_overlay(); yield 0.5
    h.check("F2 again leaves it", not h.app.overlay.active)
    h.app.open_settings_popup(); yield 0.4
    p = popup(h, "SettingsPopup")
    h.check("Settings opens", p is not None)
    stepper = next(w for w in p.walk() if type(w).__name__ == "Stepper" and "ahead" in w.label.text)
    stepper._step(1); yield 0.1
    h.check("a setting changed there is saved and applied",
            h.app.settings.lookahead == 2.0 and h.app.input_list_layout.lookahead == 2.0,
            (h.app.settings.lookahead, h.app.input_list_layout.lookahead))
    # The grade popups can be turned off there, in every display.
    row = next(w for w in p.walk() if any(getattr(c, "text", "") == "Grade popups" for c in w.children))
    switch = next(w for w in row.walk() if type(w).__name__ == "OnOffSwitch")
    switch.active = False; yield 0.1
    feedback = [display.feedback for display in h.app.displays.values()]
    feedback[0].draw([("hit", 0, "5LP", 0.1)], None)
    h.check("Grade popups off hides the grades in every display",
            not h.app.settings.show_verdicts and not any(f.show_verdicts for f in feedback)
            and all(color.a == 0 for color, _ in feedback[0].verdicts))
    switch.active = True; yield 0.1
    feedback[0].draw([("hit", 0, "5LP", 0.1)], None)
    h.check("and on shows them again", h.app.settings.show_verdicts and feedback[0].verdicts[0][0].a > 0)
    p.dismiss(); yield 0.2
    # Changing keys: click a key, press the new one.
    import keys
    from kivy.core.window import Window
    h.app.open_keys(); yield 0.4
    k = popup(h, "KeysPopup")
    h.check("Change keys opens", k is not None)
    k.cells[(keys.SHORTCUT, "add_note")].dispatch("on_release"); yield 0.1
    h.check("clicking a key waits for the new one, holding the hotkeys",
            k.waiting == (keys.SHORTCUT, "add_note") and h.app.waiting_for_key)
    Window.dispatch("on_key_down", 109, 0, "m", []); yield 0.1  # M
    h.check("pressing a key makes it the shortcut, saved and used",
            keys.window_shortcut(109, []) == "add_note" and keys.window_shortcut(110, []) is None
            and "shortcut.add_note=M" in h.app.settings.keys and not h.app.waiting_for_key,
            h.app.settings.keys)
    k.cells[(keys.HOTKEY, "play")].dispatch("on_release"); yield 0.1
    Window.dispatch("on_key_down", 112, 0, "p", []); yield 0.1  # A plain P
    h.check("a plain letter is refused as a hotkey, and it keeps waiting",
            keys.hotkey("play") == "F6" and k.waiting == (keys.HOTKEY, "play") and "F key" in k.message.text,
            k.message.text)
    Window.dispatch("on_key_down", 27, 0, None, []); yield 0.1  # Esc: a key like any other while waiting.
    h.check("Esc can be taken while waiting (it doesn't close the dialog)", k.parent is not None)
    Window.dispatch("on_key_down", 112, 0, "p", ["ctrl"]); yield 0.1
    h.check("Ctrl+P is a fine hotkey", keys.hotkey("play") == "Ctrl+P", keys.hotkey("play"))
    k.cells[(keys.SHORTCUT, "add_note")].dispatch("on_release"); yield 0.1
    Window.dispatch("on_key_down", 107, 0, "k", []); yield 0.1  # K, which Mark key input had
    h.check("a key another action had moves over",
            keys.shortcut("add_note") == "K" and keys.shortcut("mark_key_input") == ""
            and "Mark the selection" in k.message.text, k.message.text)
    h.check("the menus and help follow the keys",
            "Ctrl+P" in keys.fill("{hot_play}") and any(row[0] == "K" and "note" in row[1]
                                                        for column in __import__("help_content").key_columns()
                                                        for _, rows in column for row in rows))
    reset = next(w for w in k.walk() if getattr(w, "text", "") == "Reset all to defaults")
    reset.dispatch("on_release"); reset.dispatch("on_release"); yield 0.1
    h.check("Reset puts every key back", keys.current.keys == keys.Bindings().keys and h.app.settings.keys == "")
    k.dismiss(); yield 0.3
    # Hovering over a lane's name shows what the lane is.
    from kivy.core.window import Window
    from layouts.ui_kit import Tooltip
    hit = next(hit for hit in h.app.input_list_layout._label_hits if hit[4].startswith("Frame meter"))
    x, y = h.app.input_list_layout.to_window(hit[0] + 10, hit[1] + hit[3] / 2)
    Window.mouse_pos = (x, y); yield 0.8
    h.check("hovering over a lane name shows its tooltip", Tooltip.get().parent is not None and "Frame meter" in
            Tooltip.get().text, Tooltip.get().text[:40])
    Window.mouse_pos = (5, 5); yield 0.2
    h.app.show_help(); yield 0.3
    h.check("F1 opens help", popup(h, "HelpPopup") is not None)
    popup(h, "HelpPopup").dismiss(); yield 0.2
    order = []
    for _ in range(3):
        h.app.toggle_display(); yield 0.2
        order.append(type(h.app.display).__name__)
    h.check("F3 cycles the three displays", order == ["ArrowLanesLayout", "RingLayout", "InputListLayout"],
            order)
