"""Button remapping: a recording's buttons shown and played in the player's own layout. A map is
{recorded button: player's button}, one-to-one; buttons it leaves out map to themselves.
"""
from input_list import LIST_BUTTON_ORDER


def full_map(mapping):
    """The map for every button, with unmapped ones mapping to themselves."""
    return {button: (mapping or {}).get(button, button) for button in LIST_BUTTON_ORDER}


def inverse_map(mapping):
    return {theirs: recorded for recorded, theirs in full_map(mapping).items()}


def map_state(state, mapping):
    """The state with its buttons renamed through mapping (None stays None)."""
    if state is None or not mapping:
        return state
    mapped = {"direction": state["direction"], **{button: 0 for button in LIST_BUTTON_ORDER}}
    for recorded, theirs in full_map(mapping).items():
        if state.get(recorded):
            mapped[theirs] = 1
    return mapped


def map_key(key, mapping):
    """An input_key() (direction, pressed buttons) with its buttons renamed, in the usual order."""
    if not mapping:
        return key
    direction, pressed = key
    renamed = {full_map(mapping)[button] for button in pressed}
    return direction, tuple(button for button in LIST_BUTTON_ORDER if button in renamed)


def map_key_input(key_input, mapping):
    """A key input with its required buttons renamed. (An exact span compares whole frames, which
    are translated anyway.)"""
    if not mapping:
        return dict(key_input)
    table = full_map(mapping)
    return dict(key_input, buttons=[table[button] for button in key_input.get("buttons", [])])
