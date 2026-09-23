"""Precise timing helpers.

On Windows (Python < 3.11) time.sleep() is only as precise as the system timer, which defaults to
15.6 ms. That alone makes a steady 60 Hz loop impossible, so the app raises the timer resolution at
startup and the input sampler waits on a high resolution waitable timer instead.
"""
import ctypes
import sys
import time

_winmm = None
_kernel32 = None
if sys.platform == "win32":
    from ctypes import wintypes

    _winmm = ctypes.WinDLL("winmm")
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateWaitableTimerExW.restype = wintypes.HANDLE
    _kernel32.CreateWaitableTimerExW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    _kernel32.SetWaitableTimer.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(ctypes.c_longlong), wintypes.LONG, ctypes.c_void_p, ctypes.c_void_p, wintypes.BOOL,
    ]
    _kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

CREATE_WAITABLE_TIMER_HIGH_RESOLUTION = 0x2
TIMER_ALL_ACCESS = 0x1F0003
INFINITE = 0xFFFFFFFF

# The last stretch before a deadline is spent spinning (yielding the GIL) rather than sleeping.
SPIN_SECONDS = 0.0005


def enable_high_resolution_timing():
    # 1 ms system timer so time.sleep() (and Kivy's frame limiter) can actually hit 16.7 ms frames.
    if _winmm:
        _winmm.timeBeginPeriod(1)
    # Background threads wait at most ~1 ms for the GIL instead of the default 5 ms.
    sys.setswitchinterval(0.001)


def disable_high_resolution_timing():
    if _winmm:
        _winmm.timeEndPeriod(1)


class PreciseSleeper:
    """Sleeps until an absolute time.perf_counter() deadline with sub-millisecond accuracy.

    Owns a waitable timer handle, so create one per thread.
    """

    def __init__(self):
        self.handle = None
        if _kernel32:
            self.handle = _kernel32.CreateWaitableTimerExW(
                None, None, CREATE_WAITABLE_TIMER_HIGH_RESOLUTION, TIMER_ALL_ACCESS
            )

    def sleep(self, seconds):
        if seconds <= 0:
            return
        if self.handle:
            due = ctypes.c_longlong(-int(seconds * 10_000_000))  # Negative = relative, in 100 ns units.
            _kernel32.SetWaitableTimer(self.handle, ctypes.byref(due), 0, None, None, False)
            _kernel32.WaitForSingleObject(self.handle, INFINITE)
        else:
            time.sleep(seconds)

    def sleep_until(self, deadline):
        remaining = deadline - time.perf_counter()
        if remaining > SPIN_SECONDS:
            self.sleep(remaining - SPIN_SECONDS)
        while time.perf_counter() < deadline:
            time.sleep(0)

    def close(self):
        if self.handle:
            _kernel32.CloseHandle(self.handle)
            self.handle = None
