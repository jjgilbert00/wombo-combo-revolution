"""Game profiles: a game's actions, so inputs can be shown as what they do in that game (a medium
punch, a Drive Impact) instead of which controller buttons were pressed.

A profile has single-button actions (each drawn as an icon) and combinations: buttons pressed
together that do something of their own, drawn as a labelled badge in place of their buttons. A
recording picks a profile and says which of its recorded buttons is which action (its "action
layout"); the profile's default layout is the game's usual one for an Xbox controller.

The icons are drawn here, not taken from the game.
"""
from PIL import Image, ImageDraw, ImageFont

LIGHT = (86, 190, 255)
MEDIUM = (255, 204, 51)
HEAVY = (255, 82, 82)
DRIVE = (92, 214, 118)
NEUTRAL = (160, 160, 170)

GAMES = {
    "sf6": {
        "name": "Street Fighter 6",
        "actions": {  # name: (kind, colour), in display order
            "LP": ("punch", LIGHT), "MP": ("punch", MEDIUM), "HP": ("punch", HEAVY),
            "LK": ("kick", LIGHT), "MK": ("kick", MEDIUM), "HK": ("kick", HEAVY),
        },
        # (actions pressed together, name, colour). Checked in order; each button counts once.
        "combos": [
            (("HP", "HK"), "DI", DRIVE),  # Drive Impact
            (("MP", "MK"), "DP", DRIVE),  # Drive Parry, or a Drive Rush Cancel when it cancels a normal
            (("LP", "LK"), "THROW", NEUTRAL),
        ],
        # MP+MK straight after a normal is a Drive Rush Cancel rather than a Drive Parry.
        "after_normal": {"DP": ("DRC", 20)},  # name: (name instead, within this many frames of a normal)
        "default_layout": {"X": "LP", "Y": "MP", "RB": "HP", "A": "LK", "B": "MK", "RT": "HK"},
    },
}

COMBO_NAMES = {name for game in GAMES.values() for _, name, _ in game["combos"]} | {
    alt for game in GAMES.values() for alt, _ in game["after_normal"].values()}


def action_names(game):
    return list(GAMES[game]["actions"])


def to_actions(game, layout, buttons, after_normal=False):
    """The actions for recorded buttons pressed together: combinations first (each button used
    once), then single actions, in the game's order. Buttons with no action in the layout are
    left out. after_normal says a normal attack was just pressed (for context-dependent names)."""
    profile = GAMES[game]
    actions = {layout[button] for button in buttons if button in layout}
    shown = []
    for parts, name, _ in profile["combos"]:
        if all(part in actions for part in parts):
            actions -= set(parts)
            if after_normal and name in profile["after_normal"]:
                name = profile["after_normal"][name][0]
            shown.append(name)
    return shown + [name for name in profile["actions"] if name in actions]


def normal_window(game):
    """How far back to look for a normal attack, for names that depend on it (0 if none do)."""
    return max((frames for _, frames in GAMES[game]["after_normal"].values()), default=0)


def _colour_of(game, name):
    profile = GAMES[game]
    if name in profile["actions"]:
        return profile["actions"][name][1]
    for _, combo, colour in profile["combos"]:
        if combo == name:
            return colour
    for base, (alt, _) in profile["after_normal"].items():
        if alt == name:
            return _colour_of(game, base)
    return NEUTRAL


DARK = (30, 30, 36, 255)


def _fist(draw, s, colour):
    """A fist seen from the front: four knuckles along the top, fingers folded, the thumb across."""
    line = max(2, s // 40)
    draw.rounded_rectangle([s * 0.24, s * 0.3, s * 0.78, s * 0.72], radius=s * 0.1, fill=colour)
    for i in range(4):  # Knuckles
        x = s * 0.25 + i * s * 0.132
        draw.ellipse([x, s * 0.22, x + s * 0.13, s * 0.36], fill=colour)
    for i in range(1, 4):  # Gaps between the folded fingers
        x = s * 0.25 + i * s * 0.132
        draw.line([x, s * 0.3, x, s * 0.46], fill=DARK, width=line)
    draw.rounded_rectangle([s * 0.2, s * 0.5, s * 0.64, s * 0.64], radius=s * 0.07, fill=colour, outline=DARK,
                           width=line)  # Thumb
    draw.rectangle([s * 0.36, s * 0.72, s * 0.68, s * 0.82], fill=colour)  # Wrist


def _foot(draw, s, colour):
    """A shoe from the side, toe forward: the kick icon."""
    line = max(2, s // 40)
    points = [(0.2, 0.7), (0.2, 0.3), (0.42, 0.3), (0.46, 0.44), (0.62, 0.5), (0.8, 0.54), (0.84, 0.7)]
    draw.polygon([(x * s, y * s) for x, y in points], fill=colour)
    draw.ellipse([s * 0.7, s * 0.52, s * 0.88, s * 0.72], fill=colour)  # Rounded toe
    draw.rounded_rectangle([s * 0.16, s * 0.68, s * 0.88, s * 0.8], radius=s * 0.05, fill=colour, outline=DARK,
                           width=line)  # Sole
    for i in range(3):  # Laces
        x = s * (0.47 + i * 0.08)
        draw.line([x, s * (0.46 + i * 0.02), x + s * 0.03, s * (0.53 + i * 0.02)], fill=DARK, width=line)


def draw_action_icon(game, name, size, font_path):
    """An RGBA icon for an action: a fist or foot in its strength's colour on a dark disc, or for a
    combination, its name on a badge in its colour."""
    scale = 4
    s = size * scale
    image = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    colour = _colour_of(game, name)
    profile = GAMES[game]
    if name in profile["actions"]:
        draw.ellipse([s * 0.02, s * 0.02, s * 0.98, s * 0.98], fill=DARK, outline=colour + (255,),
                     width=max(2, s // 16))
        (_fist if profile["actions"][name][0] == "punch" else _foot)(draw, s, colour + (255,))
    else:
        draw.rounded_rectangle([s * 0.02, s * 0.14, s * 0.98, s * 0.86], radius=s * 0.18, fill=colour + (255,),
                               outline=(20, 20, 24, 255), width=max(2, s // 20))
        font_size = int(s * (0.5 if len(name) <= 2 else 0.38 if len(name) == 3 else 0.24))
        font = ImageFont.truetype(font_path, font_size)
        draw.text((s / 2, s / 2), name, font=font, fill=(20, 20, 24, 255), anchor="mm")
    return image.resize((size, size), Image.LANCZOS)
