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
    while c.last_pass is None:
        yield 0.05
    h.check("a perfect pass scores 4/4", (c.last_pass["hits"], c.last_pass["total"]) == (4, 4),
            (c.last_pass["hits"], c.last_pass["total"]))
    h.app.pause(); yield 0.2
    h.app.set_selection(40, 46); h.key(107, "k"); yield 0.4
    p = popup(h, "KeyInputPopup")
    h.check("K opens the key input editor on the selection", p is not None and p.key_input["buttons"] == ["X"])
    p.dismiss(); yield 0.2
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
    h.check("F2 enters overlay mode", h.app.topmost)
    h.app.toggle_overlay(); yield 0.5
    h.check("F2 again leaves it", not h.app.topmost)
    h.app.show_help(); yield 0.3
    h.check("F1 opens help", popup(h, "HelpPopup") is not None)
    popup(h, "HelpPopup").dismiss(); yield 0.2
    order = []
    for _ in range(3):
        h.app.toggle_display(); yield 0.2
        order.append(type(h.app.display).__name__)
    h.check("F3 cycles the three displays", order == ["ArrowLanesLayout", "PlayAlongLayout", "InputListLayout"],
            order)
