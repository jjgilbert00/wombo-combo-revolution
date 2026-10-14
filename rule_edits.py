"""Changes the player makes to input rules, as edits to one layer (see input_rules.layered): the
recording's own changes, the player's rules for a game, or for one of its characters.

Every edit takes a layer (a dict, changed in place) and keeps it minimal: a rule the layer added is
edited or removed where it is; a rule from below is changed by an entry of just the fields that
differ ({"id": "buffer", "frames": 6}); an exception from below is undone with an "allow" entry.
"""
import copy

import input_rules
from input_list import LIST_BUTTON_ORDER
from input_rules import LAYER_PARTS, RECORDING, YOURS, YOURS_CHARACTER

# The rules the editor can add, by type, with their starting values.
SIMPLE_RULES = {
    "neutral": {"id": "neutral", "type": "neutral", "name": "Neutral is neutral"},
    "multi_press": {"id": "simultaneous", "type": "multi_press", "window": 2, "name": "Simultaneous presses"},
    "buffer": {"id": "buffer", "type": "buffer", "frames": 4, "name": "Input buffer"},
}


def _entries(layer, part):
    return layer.setdefault(part, [])


def _tidy(layer):
    for part in LAYER_PARTS:
        if part in layer and not layer[part]:
            del layer[part]


def added_here(layer, rule_id):
    """Whether this layer added the rule (rather than changing one from below)."""
    return any(e["id"] == rule_id and "type" in e for e in layer.get("rules", []))


def change_rule(layer, rule_id, **fields):
    """Changes fields of a rule (enabled, window, frames, max_frames, charge...)."""
    rules = _entries(layer, "rules")
    entry = next((e for e in rules if e["id"] == rule_id), None)
    if entry is None:
        rules.append({"id": rule_id, **fields})
    else:
        entry.update(fields)
        entry.pop("remove", None)
    _tidy(layer)


def add_rule(layer, rule):
    """Adds a whole rule ({"id", "type", ...}); one with the same id in this layer is replaced."""
    remove_rule(layer, rule["id"])
    _entries(layer, "rules").append(dict(rule))


def remove_rule(layer, rule_id):
    """Takes this layer's entry for a rule away: a rule it added goes, a change it made is undone."""
    if "rules" in layer:
        layer["rules"] = [e for e in layer["rules"] if e["id"] != rule_id]
    _tidy(layer)


def _same(entry, rule, direction, button):
    return entry["rule"] == rule and int(entry["direction"]) == direction and entry["button"] == button


def add_exception(layer, rule, direction, button):
    """Makes direction + button a move of its own, not part of a rule's direction group (a 3HK of a
    character's own)."""
    exception = {"rule": rule, "direction": int(direction), "button": button}
    if "allow" in layer:
        layer["allow"] = [e for e in layer["allow"] if not _same(e, rule, int(direction), button)]
    if not any(_same(e, rule, int(direction), button) for e in layer.get("except", [])):
        _entries(layer, "except").append(exception)
    _tidy(layer)


def drop_exception(layer, rule, direction, button):
    """Makes direction + button part of the rule's group again: this layer's exception goes, or one
    from below is allowed."""
    direction = int(direction)
    mine = [e for e in layer.get("except", []) if _same(e, rule, direction, button)]
    if mine:
        layer["except"] = [e for e in layer["except"] if not _same(e, rule, direction, button)]
    elif not any(_same(e, rule, direction, button) for e in layer.get("allow", [])):
        _entries(layer, "allow").append({"rule": rule, "direction": direction, "button": button})
    _tidy(layer)


def parse_steps(text):
    """Steps from how a player types them: "236" is three steps; spaces separate steps that accept
    more than one direction, the first written: "6 21 3" is 6, then 2 or 1, then 3. None if it
    isn't one."""
    text = text.strip()
    if not text or any(c not in "123456789 " for c in text):
        return None
    parts = text.split() if " " in text else list(text)
    steps = [[int(c) for c in part] for part in parts]
    return steps if all(len(set(step)) == len(step) for step in steps) else None


def steps_text(steps):
    """parse_steps backwards."""
    if all(len(step) == 1 for step in steps):
        return "".join(str(step[0]) for step in steps)
    return " ".join("".join(str(d) for d in step) for step in steps)


def new_id(rules, name):
    """An id for a new rule, from its name, that no rule has."""
    base = "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-") or "rule"
    rule_id, n = f"my-{base}", 2
    while rule_id in rules:
        rule_id, n = f"my-{base}-{n}", n + 1
    return rule_id


def direction_group(rules, name, directions):
    """A rule making directions (a list, the first how it's written) the same with a button."""
    return {"id": new_id(rules, name), "type": "direction_classes", "name": name, "classes": [list(directions)]}


def motion(rules, name, steps, shortcuts=(), max_frames=0):
    return {"id": new_id(rules, name), "type": "motion", "name": name, "steps": steps,
            **({"shortcuts": list(shortcuts)} if shortcuts else {}), **({"max_frames": max_frames} if max_frames else {})}


def charge_motion(rules, name, held, release, frames, keep):
    """A charge motion: held (directions that charge, e.g. [4, 1, 7]) for frames, then release
    (e.g. [6]) within keep frames of letting go."""
    return {"id": new_id(rules, name), "type": "motion", "name": name, "written": [held[0], release[0]],
            "steps": [list(held), list(release)], "charge": {"frames": int(frames), "keep": int(keep)}}


# --- The open recording's rules -------------------------------------------------------------------

SCOPES = (RECORDING, YOURS, YOURS_CHARACTER)


class RulesSession:
    """The open recording's rules as the Input rules dialog sees and edits them. Edits go to one
    scope: the recording's own changes (saved with it), the player's rules for its game (or custom
    rule set), or for its character there; the player's rules are saved at once. The controller is
    a PlayalongController; on_recording_changed() is called when the recording itself changed."""

    def __init__(self, controller, actions=None, on_recording_changed=lambda: None):
        self.controller = controller
        self.actions = actions or {}  # {game: [action names]}, for naming buttons in exceptions.
        self.on_recording_changed = on_recording_changed

    # ---- What there is ----------------------------------------------------------------------

    @property
    def game(self):
        return self.controller.get_game()[0]

    @property
    def key(self):
        """Which rules the player's own go with: the game's key, or a custom rule set's (or None)."""
        return self.game or self.controller.get_rule_changes().get("pack")

    def character(self):
        return self.controller.get_input_rules()[0]

    def strict(self):
        return self.controller.get_input_rules()[1]

    def characters(self):
        return input_rules.pack_characters(self.key) if self.key else {}

    def layers(self):
        """The rules layer by layer (input_rules.Layered), whatever strict says."""
        return input_rules.layered(self.game, character=self.character(), recording=self.controller.get_rule_changes())

    def button_names(self):
        """What exceptions name buttons by: the game's actions, or the recorded buttons."""
        return list(self.actions.get(self.game) or []) or list(LIST_BUTTON_ORDER)

    def scopes(self):
        """The scopes edits can go to now."""
        return [RECORDING] + ([YOURS] if self.key else []) + ([YOURS_CHARACTER] if self.key and self.character() else [])

    def layer(self, scope):
        """A copy of a scope's layer."""
        if scope == RECORDING:
            return copy.deepcopy(self.controller.get_rule_changes())
        pack = input_rules.load_user_pack(self.key)
        if scope == YOURS:
            return pack
        return pack.get("characters", {}).get(self.character(), {})

    # ---- Changes ----------------------------------------------------------------------------

    def edit(self, scope, change):
        """Applies change(layer) to a scope's layer and saves it."""
        if scope == RECORDING:
            changes = copy.deepcopy(self.controller.get_rule_changes())
            change(changes)
            self.controller.set_rule_changes(changes)
            self.on_recording_changed()
            return
        pack = input_rules.load_user_pack(self.key)
        if not pack and not self.game:
            pack = self._custom_pack_copy()
        if scope == YOURS:
            change(pack)
        else:
            character = self.character()
            target = pack.setdefault("characters", {}).setdefault(
                character, {"name": self.characters().get(character, character)})
            change(target)
        input_rules.save_user_pack(self.key, pack)
        self.controller.reload_rules()

    def _custom_pack_copy(self):
        """A custom rule set this recording carries but the player doesn't have yet."""
        changes = self.controller.get_rule_changes()
        return copy.deepcopy(changes.get("pack_data") or {"name": changes.get("pack"), "custom": True})

    def reset(self, scope):
        """Undoes every change in a scope (a custom rule set keeps its name and characters' names)."""
        def clear(layer):
            for part in LAYER_PARTS:
                layer.pop(part, None)
            if scope == YOURS:
                for character in layer.get("characters", {}).values():
                    clear(character)
        self.edit(scope, clear)

    def set_strict(self, strict):
        self.controller.set_input_rules(self.character(), strict)
        self.on_recording_changed()

    def set_character(self, character):
        self.controller.set_input_rules(character, self.strict())
        self.on_recording_changed()

    def new_character(self, name):
        """Adds a character to the player's rules for this game or rule set, and picks it."""
        key = input_rules.new_key(name, set(self.characters()))
        pack = input_rules.load_user_pack(self.key) or (self._custom_pack_copy() if not self.game else {})
        pack.setdefault("characters", {})[key] = {"name": name}
        input_rules.save_user_pack(self.key, pack)
        self.set_character(key)
        return key

    def custom_rule_sets(self):
        return input_rules.custom_rule_sets()

    def use_rule_set(self, key):
        """For a recording without a game the app knows: the player's custom rule set it uses (None:
        the generic rules)."""
        changes = self.controller.get_rule_changes()
        if key == changes.get("pack"):
            return
        changes.pop("pack_data", None)
        changes["pack"] = key
        self.controller.set_input_rules(None, self.strict())  # Characters belong to a rule set.
        self.controller.set_rule_changes(changes)
        self.on_recording_changed()

    def new_rule_set(self, name):
        key = input_rules.new_key(name, set(self.custom_rule_sets()))
        input_rules.save_user_pack(key, {"name": name, "custom": True})
        self.use_rule_set(key)
        return key
