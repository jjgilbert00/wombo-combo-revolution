"""Precise timing helpers.

On Windows (Python < 3.11) time.sleep() is only as precise as the system timer, which defaults to
15.6 ms. That alone makes a steady 60 Hz loop impossible, so the app raises the timer resolution at
startup.
"""
import ctypes
import sys

_winmm = None
if sys.platform == "win32":
    _winmm = ctypes.WinDLL("winmm")


def enable_high_resolution_timing():
    # 1 ms system timer so time.sleep() (and Kivy's frame limiter) can actually hit 16.7 ms frames.
    if _winmm:
        _winmm.timeBeginPeriod(1)


def disable_high_resolution_timing():
    if _winmm:
        _winmm.timeEndPeriod(1)
