"""Regenerates the user guide's screenshots in docs/images."""
import glob
import os
from PIL import Image
from kivy.core.window import Window
from kivy.uix.dropdown import DropDown
from kivy.uix.modalview import ModalView
from pads import WarmUpPad, use_pad

OUT = os.path.join(os.getcwd(), "docs", "images")
SHOTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shots")


def save(h, name, box=None, widget=None, pad=0):
    """Screenshot, cropped to box (x0, top, x1, bottom in Kivy window coords) or a widget's rect."""
    h.shot("doc_" + name)
    image = Image.open(os.path.join(SHOTS, "doc_" + name + ".png"))
    W, H = image.size
    if widget is not None:
        x, y = widget.to_window(widget.x, widget.y)
        box = (x - pad, y + widget.height + pad, x + widget.width + pad, y - pad)
    x0, top, x1, bottom = box
    image.crop((max(0, int(x0)), max(0, int(H - top)), min(W, int(x1)), min(H, int(H - bottom)))).save(
        os.path.join(OUT, name + ".png"))


def close_popups():
    for w in list(Window.children):
        if isinstance(w, (ModalView, DropDown)):
            w.dismiss()


def steps(h):
    c = h.app.playalong_controller
    W, H = Window.size
    yield 0.6
    # Start screen: nothing loaded.
    h.app.clear_track(); yield 0.5
    card = h.app.card_layer.card
    save(h, "start-screen", (card.x - 260, card.top + 60, card.right + 260, card.y - 110))
    # First go at the warm-up, played by a scripted pad, then its result.
    h.app.open_track(glob.glob(os.path.join(os.getcwd(), "samples", "Warm-up*.json"))[0]); yield 0.4
    use_pad(h.app, WarmUpPad(c))
    h.app.coaching = False
    h.app.play()
    while c.get_lead() or c.get_current_frame() < 95:
        yield 0.005
    L = h.app.input_list_layout
    save(h, "first-go", (0, H, W * 0.62, H - 520))
    run = c.get_last_pass()["run"] if c.get_last_pass() else 0
    while not c.get_last_pass() or c.get_last_pass()["run"] == run:
        yield 0.005
    h.app.pause(); yield 0.3
    banner = L.banner
    save(h, "pass-result", (0, H, W * 0.75, banner.y - 24))
    # Practising Guile's combo.
    h.app.open_track(glob.glob(os.path.join(os.getcwd(), "samples", "SF6 Guile*.json"))[0]); yield 0.4
    h.app.coaching = False
    h.app.play()
    while c.get_lead() or c.get_current_frame() < 40:
        yield 0.005
    h.app.pause(); yield 0.3
    save(h, "practice-screen", (0, H, W * 0.72, 0))
    # The key input editor.
    h.app.edit_key_input(0); yield 0.5
    popup = next(w for w in Window.children if isinstance(w, ModalView))
    save(h, "key-input-editor", widget=popup.children[0], pad=2)
    close_popups(); yield 0.3
    # Right-click menu.
    h.app.set_selection(20, 26); yield 0.2
    h.app.open_context_menu(23, (L._line_x() + 200, L.top - 200)); yield 0.5
    menu = next(w for w in Window.children if isinstance(w, DropDown))
    x, y = menu.to_window(menu.x, menu.y)
    save(h, "right-click-menu", (x - 260, y + menu.height + 60, x + menu.width + 30, y - 20))
    close_popups(); yield 0.3
    # Attempts.
    h.app.open_attempts(); yield 0.5
    popup = next(w for w in Window.children if isinstance(w, ModalView))
    save(h, "attempts-manager", widget=popup.children[0], pad=2)
    close_popups(); yield 0.2
