"""Which side of the screen the player is on, and mirroring inputs between the two sides.

Fighting games read directions relative to the way the character faces: forward is toward the
opponent. Recordings are kept as if the character faces right (from the left side, player 1's usual
side), which is also how combo notation is written: 6 is forward, 4 is back, 236 a fireball.

The app mirrors at its edges, so the same recording works from either side: when the player is on
the right side (facing left), what they do is mirrored as it comes in (so pressing toward the
opponent still reads as 6, and an attempt is graded against the recording the right way round), and
demos are mirrored back as they go out to the game. A recording made from the right side is stored
mirrored too, so it's written the usual way. One made before the app knew which side the player was
on can be flipped once from the Edit menu.

Characters can switch sides mid-combo (a cross-up); a recording keeps the side it started on.
"""

LEFT, RIGHT = "left", "right"
SIDE_NAMES = {LEFT: "Left side (facing right)", RIGHT: "Right side (facing left)"}

# Numpad directions swapped left for right: up and down stay.
MIRROR = {1: 3, 2: 2, 3: 1, 4: 6, 5: 5, 6: 4, 7: 9, 8: 8, 9: 7}


def mirror_direction(direction):
    return MIRROR[direction]


def mirror_state(state):
    """A controller state mirrored left for right (None, an unplayed frame, stays None)."""
    if state is None:
        return None
    return dict(state, direction=MIRROR[state["direction"]])


def mirror_track(track):
    return [mirror_state(state) for state in track]


def mirror_key_input(key_input):
    """A key input mirrored: its motion and direction (None, any direction, stays None)."""
    direction = key_input.get("direction")
    return dict(key_input, motion=[MIRROR[d] for d in key_input.get("motion", [])],
                direction=None if direction is None else MIRROR[direction])
