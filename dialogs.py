"""Native Windows file dialogs.

These replace tkinter, which was being created on the hotkey listener thread (never destroyed and
not thread safe). Call from the Kivy main thread; rendering pauses while the dialog is open, but
input sampling and recording keep running on their own thread.
"""
import pywintypes
import win32con
import win32gui
from kivy.core.window import Window

FLAGS = win32con.OFN_EXPLORER | win32con.OFN_NOCHANGEDIR


def _owner():
    try:
        return Window.get_window_info().window
    except Exception:
        return None


def _run(dialog, **kwargs):
    try:
        path, _, _ = dialog(hwndOwner=_owner(), **kwargs)
        return path
    except pywintypes.error as e:
        if e.winerror == 0:  # Cancelled.
            return None
        raise


def open_file(title, filter_name, pattern):
    """pattern may list several, e.g. "*.json;*.mp4"."""
    return _run(win32gui.GetOpenFileNameW, Title=title, Filter=f"{filter_name}\0{pattern}\0",
                Flags=FLAGS | win32con.OFN_FILEMUSTEXIST)


def save_file(title, filter_name, pattern, default_extension, file_name=""):
    return _run(win32gui.GetSaveFileNameW, Title=title, Filter=f"{filter_name}\0{pattern}\0",
                DefExt=default_extension, File=file_name, Flags=FLAGS | win32con.OFN_OVERWRITEPROMPT)
