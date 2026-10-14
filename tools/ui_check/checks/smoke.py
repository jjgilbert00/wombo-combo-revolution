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
    h.check("Reset puts every key back, and asks again next time",
            keys.current.keys == keys.Bindings().keys and h.app.settings.keys == "" and reset.text == "Reset all to defaults")
    k.dismiss(); yield 0.3
    # Input rules: the game's by default; a character's own moves once it's picked; strict on request.
    c = h.app.playalong_controller
    h.app.set_game("sf6"); yield 0.1
    h.app.edit_game_actions(); yield 0.4
    dialog = popup(h, "GameActionsPopup")
    h.check("Game actions offers SF6's characters", dialog is not None and "Ryu" in dialog.character_spinner.values,
            dialog.character_spinner.values[:4] if dialog else None)
    dialog.character_spinner.text = "Ryu"; yield 0.1
    h.check("picking a character gives its rules", c.get_input_rules()[0] == "ryu"
            and "Ryu" in c.get_input_rules()[2].name, c.get_input_rules()[2].name)
    dialog.dismiss(); yield 0.2
    h.app.toggle_strict_rules(); yield 0.1
    h.check("Strict input rules grades literally", c.get_input_rules()[2].strict)
    h.app.toggle_strict_rules(); yield 0.1
    yield from input_rules_steps(h, c)
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


def press(h, root, text):
    widget = next(w for w in root.walk() if getattr(w, "text", None) == text)
    widget.dispatch("on_release")
    return widget


def input_rules_steps(h, c):
    """Changing the rules: this recording's, the player's for the game and a character, a new rule
    set for a game the app doesn't know, and one key input's own leniency."""
    import input_rules
    from input_rules import RECORDING, YOURS_CHARACTER

    h.app.edit_input_rules(); yield 0.4
    p = popup(h, "InputRulesPopup")
    h.check("Edit > Input rules opens on the recording's rules", p is not None and "Ryu" in p.name_label.text,
            p.name_label.text if p else None)
    h.shot("input_rules"); yield 0.1
    buffer = next(w for w in p.walk() if type(w).__name__ == "Stepper" and w.label.text == "4 frames")
    buffer._step(2); yield 0.2
    h.check("a rule's frames change for this recording", c.get_input_rules()[2].buffer == 6
            and c.get_rule_changes() == {"rules": [{"id": "buffer", "frames": 6}]}, c.get_rule_changes())
    h.check("...and are marked as changed here", any("this recording" in getattr(w, "text", "") for w in p.walk()))
    p.scope = YOURS_CHARACTER; p.refresh(); yield 0.2
    p.new_direction.text, p.new_button.text = "3", "MK"
    press(h, p, "Is its own move"); yield 0.2
    with open(os.path.join(input_rules.USER_PACKS, "sf6.json"), encoding="utf-8") as f:
        saved = f.read()
    h.check("a move of its own for Ryu goes into your rules", '"MK"' in saved and
            c.get_input_rules()[2].press_directions(3, ["B"])[0] == {3}, saved[:120])
    p.add_kind = "Motion"; p.refresh(); yield 0.1
    p.fields["name"].text, p.fields["steps"].text, p.fields["shortcuts"].text = "Hcf", "41236", "426"
    press(h, p, "Add"); yield 0.2
    named = c.get_input_rules()[2].motion_named([4, 1, 2, 3, 6])
    h.check("a motion can be added", named is not None and len(named.shortcuts) == 1, p.message.text)
    p.fields["steps"].text = "236"
    press(h, p, "Add"); yield 0.2
    h.check("...but not one already written that way", "already a motion written 236" in p.message.text, p.message.text)
    next(w for w in p.walk() if type(w).__name__ == "ScrollView").scroll_y = 0; yield 0.3
    h.shot("input_rules_yours"); yield 0.1
    p.scope = RECORDING; p.refresh(); yield 0.1
    press(h, p, "Undo all changes here"); press(h, p, "Sure?"); yield 0.2
    h.check("undoing the recording's changes", c.get_rule_changes() == {} and c.get_input_rules()[2].buffer == 4)
    p.dismiss(); yield 0.2

    # A game the app doesn't know: a rule set of the player's own.
    h.app.set_game(None); yield 0.1
    h.app.edit_input_rules(); yield 0.4
    p = popup(h, "InputRulesPopup")
    p._new_rule_set("Brawler EX"); yield 0.2
    h.check("a new rule set for an unknown game", c.get_rule_changes().get("pack") == "brawler-ex"
            and c.get_input_rules()[2].name == "Brawler EX", c.get_rule_changes())
    p.add_kind = "Input buffer"; p.refresh(); yield 0.1
    press(h, p, "Add"); yield 0.2
    h.check("the generic rules have no buffer; one can be added", c.get_input_rules()[2].buffer == 4)
    p._new_character("Big Guy"); yield 0.2
    h.check("...and characters for it", c.get_input_rules()[0] == "big-guy" and p.scope == YOURS_CHARACTER)
    data = h.app._track_data()
    h.check("the recording carries its rule set", data["input_rules"]["pack_data"]["name"] == "Brawler EX",
            data["input_rules"])
    h.shot("input_rules_custom"); yield 0.1
    p.dismiss(); yield 0.2
    h.app.set_game("sf6"); c.set_rule_changes({}); c.set_input_rules("ryu"); yield 0.1

    # One key input's own leniency.
    h.app.set_selection(40, 46); h.app.mark_key_input(); yield 0.4
    k = popup(h, "KeyInputPopup")
    h.check("the key input editor says what it accepts", k is not None and "early" in k.accepts_label.text,
            k.accepts_label.text if k else None)
    press(h, k, "Change..."); yield 0.4
    a = popup(h, "AcceptPopup")
    a.steppers["buffer"]._step(3); yield 0.1
    h.shot("accept"); yield 0.1
    press(h, a, "Done"); yield 0.2
    h.check("its own buffer", k.key_input.get("accept") == {"buffer": 7}, k.key_input.get("accept"))
    h.check("...shown in the editor", "7f early" in k.accepts_label.text and "changed" in k.accepts_label.text,
            k.accepts_label.text)
    k.dismiss(); yield 0.2
    h.app.set_selection(None)
