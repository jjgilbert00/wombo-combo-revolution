"""Overlay mode: the window's size across displays and with the card, and the see-through background."""
import ctypes
import os
from ctypes import wintypes

import win32gui
from kivy.core.window import Window


def rect():
    left, top, right, bottom = win32gui.GetWindowRect(Window.get_window_info().window)
    return left, top, right - left, bottom - top


def layered_flags():
    key, alpha, flags = wintypes.DWORD(), ctypes.c_ubyte(), wintypes.DWORD()
    ctypes.windll.user32.GetLayeredWindowAttributes(Window.get_window_info().window, ctypes.byref(key),
                                                    ctypes.byref(alpha), ctypes.byref(flags))
    return flags.value


def steps(h):
    h.app.open_track(os.path.join(os.getcwd(), "samples", "SF6 Ryu - st.MP, cr.MP, MK Tatsumaki.json")); yield 0.5
    normal = rect()
    h.app.toggle_overlay(); yield 0.6
    full = rect()
    h.check("with the card up, the overlay keeps the full height", full[3] > 500, full)
    h.check("the overlay is see-through (colour key)", layered_flags() & 1, layered_flags())
    h.app.coaching = False; yield 0.6
    fitted = rect()
    h.check("without it, the list's overlay fits its content", 200 < fitted[3] < full[3], fitted)
    for mode in ("lanes", "ring"):
        h.app.show_display(mode); yield 0.5
        h.check(f"{mode}: the overlay keeps the full height", rect()[3] == full[3], rect())
    h.app.show_display("list"); yield 0.5
    h.check("back to the list, it fits again", rect()[3] == fitted[3], rect())
    h.app.toggle_overlay(); yield 0.6
    h.check("leaving overlay puts the window back", rect() == normal, (rect(), normal))
    h.check("and it's no longer see-through", not layered_flags() & 1, layered_flags())
