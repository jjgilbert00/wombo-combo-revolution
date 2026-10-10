"""A practice pass in each display, with screenshots, and the hit feedback."""
import os

from pads import WarmUpPad, use_pad


def steps(h):
    c = h.app.playalong_controller
    h.app.open_track(os.path.join(os.getcwd(), "samples", "Warm-up - LP, MP, HP, Hadoken.json")); yield 0.3
    use_pad(h.app, WarmUpPad(c))
    h.app.coaching = False
    for mode in ("lanes", "ring", "list"):
        h.app.show_display(mode); yield 0.2
        h.app.restart_playback(); h.app.play()
        run = c.last_pass["run"] if c.last_pass else 0
        widest_line = 0
        while c.get_lead() or c.get_current_frame() < 75:
            widest_line = max(widest_line, h.app.input_list_layout.line.size[0])
            yield 0.01
        h.shot(f"{mode}_playing")
        while not c.last_pass or c.last_pass["run"] == run:
            yield 0.02
        yield 0.1
        h.shot(f"{mode}_result")
        banner = h.app.display.feedback.banner
        h.check(f"{mode}: the pass is perfect and its banner shows", banner.opacity and "PERFECT" in banner.text,
                banner.text[-30:])
        if mode == "list":
            h.check("list: the line flares on a hit", widest_line > 3, widest_line)
        h.app.pause(); yield 0.2
