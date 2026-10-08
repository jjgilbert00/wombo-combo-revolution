"""The app's colours and type, in one place.

Colour roles are kept apart so each colour means one thing:

- Grades (hit, early, late, miss, not reached) are used for nothing else.
- Gold is the accent: key inputs, the primary button in a dialog, selected options.
- Key inputs that are holds or exact spans have their own hues (violet, cyan).
- Warnings are pink, so they never read as "late".
- The frame meter uses its own muted set; the selection is plain white.

Text colours are chosen for contrast on the app's dark surfaces: TEXT and TEXT_DIM are at least
4.5:1 on every background here; TEXT_FAINT is for things that don't need reading (placeholders).

Sizes come from one type scale: CAPTION, BODY, LARGE, TITLE and DISPLAY.
"""
from kivy.metrics import sp

# ---- Surfaces ---------------------------------------------------------------------------------
BACKGROUND = (0.2, 0.2, 0.2)  # The window's.
BAR = (0.10, 0.10, 0.12)  # Menu and status bars.
SURFACE = (0.14, 0.14, 0.17)  # Dialogs, menus.
SURFACE_RAISED = (0.19, 0.19, 0.23)  # Inputs, rows inside dialogs.
GUTTER = (0.08, 0.08, 0.1)  # The input list's lane names.
SCRIM = (0.05, 0.05, 0.06, 0.62)  # Behind cards and dialogs.
# The background in a see-through overlay: Windows makes exactly this colour transparent, so the
# game shows through everywhere nothing is drawn. Near black, so edges blending into it read as a
# dark outline; not pure black, so black drawn on purpose (text outlines) stays.
OVERLAY_KEY = (1 / 255, 1 / 255, 2 / 255)

# ---- Text -------------------------------------------------------------------------------------
TEXT = (0.93, 0.93, 0.95, 1)
TEXT_DIM = (0.72, 0.72, 0.76, 1)
TEXT_FAINT = (0.55, 0.55, 0.6, 1)
TEXT_ON_ACCENT = (0.1, 0.08, 0.02, 1)  # Dark text on gold.

# ---- Roles ------------------------------------------------------------------------------------
ACCENT = (1.0, 0.8, 0.22)  # Gold: key inputs, primary actions, selected options.
HOLD = (0.72, 0.55, 1.0)  # Hold key inputs.
EXACT = (0.35, 0.85, 1.0)  # Exact-span key inputs.
WARNING = (1.0, 0.55, 0.75)  # Pink: no controller, unsaved changes, timing trouble.
INFO = (0.75, 0.82, 0.95)  # Neutral status, e.g. the selection's span.
DANGER = (0.86, 0.24, 0.24)  # Destructive actions, once confirmed; recording.
SELECTION = (1.0, 1.0, 1.0)

# ---- Grades: only ever used for how an input went. ---------------------------------------------
HIT = (0.45, 0.9, 0.5)
EARLY = (0.42, 0.58, 1.0)
LATE = (1.0, 0.58, 0.18)
MISS = (1.0, 0.42, 0.42)
PENDING = (0.45, 0.45, 0.5)
GRADES = {"hit": HIT, "early": EARLY, "late": LATE, "miss": MISS, "pending": PENDING}

# ---- Frame meter: muted, so it doesn't compete with grades or key inputs. -----------------------
METER_NEUTRAL = (0.34, 0.34, 0.38)
METER_DIRECTION = (0.48, 0.56, 0.7)
METER_BUTTON = (0.86, 0.86, 0.9)

# ---- Type scale -------------------------------------------------------------------------------
CAPTION = sp(12)
BODY = sp(14)
LARGE = sp(16)
TITLE = sp(20)
DISPLAY = sp(32)


def hex_of(rgb):
    """"rrggbb" for Kivy markup."""
    return "".join(f"{round(c * 255):02x}" for c in rgb[:3])


def markup(text, rgb, bold=False):
    text = f"[b]{text}[/b]" if bold else text
    return f"[color={hex_of(rgb)}]{text}[/color]"
