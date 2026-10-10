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
    p.dismiss(); yield 0.2
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
