"""Input rules: what counts as the same input in a game (see docs/design/INPUT_RULES.md).

key_inputs.py interprets recordings (derive, describe, demo_track) and grades attempts (result,
grade) under an InputRules. STRICT is the literal reading the app always used: a press needs the
exact direction recorded, a motion every direction that was seen, and buttons pressed on the same
frame. A game's rules are more lenient, in the ways its rule pack says:

- direction classes: directions that do the same thing with a button (1, 2 and 3 for a crouching
  normal), minus a character's own moves on them (exceptions: a 3HK of its own);
- neutral presses: a standing normal recorded at 5 needs 5 (or its class), not any direction;
- simultaneous presses: buttons pressed within a few frames of each other count as together;
- motions: named motions (236, 623, 360...) recognised by pattern, with their shortcuts and time
  limits, instead of every direction seen;
- a buffer: a press a few frames before its window still counts.

Rule packs are JSON files in rule_packs/ (generic.json for any game without one). A pack has the
game's rules, then control schemes and characters that change them; a recording and a single key
input can change them again. resolve() layers them into one InputRules.

Every match can say why (explain()), so a lenient grade, or a near miss, can be traced to its rule.
"""
import json
import os
from dataclasses import dataclass, field, replace

PACKS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rule_packs")
DIRECTIONS = frozenset(range(1, 10))


@dataclass(frozen=True)
class DirectionClass:
    """Directions that do the same with a button, e.g. 1, 2 and 3 for crouching normals. The first
    is how it's written. except_ holds (direction, button) pairs that are moves of their own."""
    id: str
    name: str
    directions: tuple
    except_: frozenset = frozenset()

    @property
    def representative(self):
        return self.directions[0]


@dataclass(frozen=True)
class Charge:
    """A charge motion's first step is held: for frames frames (with two buttons, frames_two), and the
    charge lasts keep frames (keep_two) after it's let go."""
    frames: int
    keep: int
    frames_two: int = 0
    keep_two: int = 0

    def needs(self, buttons):
        two = len(buttons) >= 2
        return (self.frames_two if two and self.frames_two else self.frames,
                self.keep_two if two and self.keep_two else self.keep)


@dataclass(frozen=True)
class Motion:
    """A named motion as steps, each a set of acceptable directions in order (the first of each is
    how it's written): 623 is ((6,), (2, 1), (3,)). shortcuts are other step sequences that do it.
    Other directions may come between steps. max_frames limits the whole motion up to the press,
    max_step_gap the frames between one step and the next (0: no limit). written overrides how it's
    written ([2, 2] for 22, whose steps need something else between the two downs). A charge motion
    ([4]6) holds its first step (see Charge)."""
    id: str
    name: str
    steps: tuple
    shortcuts: tuple = ()
    max_frames: int = 0
    max_step_gap: int = 0
    written_as: tuple = ()
    charge: Charge = None

    @property
    def written(self):
        return list(self.written_as) if self.written_as else [step[0] for step in self.steps]

    def notation(self):
        written = "".join(str(d) for d in self.written)
        return f"[{written[0]}]{written[1:]}" if self.charge else written


@dataclass(frozen=True)
class InputRules:
    name: str = "Strict"
    strict: bool = True
    neutral_is_neutral: bool = False
    direction_classes: tuple = ()
    multi_press_window: int = 0
    buffer: int = 0
    motions: tuple = ()
    unverified: frozenset = frozenset()  # Rule ids whose frame values nobody has confirmed yet.
    sources: tuple = field(default=(), compare=False)  # The packs and layers it was made from.
    # Which recorded button is which of the game's actions ({"Y": "MP"}): exceptions name actions.
    layout: tuple = ()

    def _action(self, button):
        return dict(self.layout).get(button, button)

    # --- Presses --------------------------------------------------------------------------------

    def press_directions(self, direction, buttons):
        """The directions that do the same press as direction + buttons, and the class that says so
        (None if only the direction itself)."""
        if direction is None:
            return DIRECTIONS, None
        if self.strict or not buttons:
            return frozenset([direction]), None
        for cls in self.direction_classes:
            if direction not in cls.directions:
                continue
            actions = [self._action(button) for button in buttons]
            if any((direction, action) in cls.except_ for action in actions):
                return frozenset([direction]), None  # A move of its own (a character's 3HK).
            same = frozenset(d for d in cls.directions
                             if not any((d, action) in cls.except_ for action in actions))
            return same, cls
        return frozenset([direction]), None

    def written_direction(self, direction, buttons):
        """How a press is written: its class's representative (1HK as 2HK), unless it's a move of
        its own."""
        same, cls = self.press_directions(direction, buttons)
        return cls.representative if cls and cls.representative in same else direction

    # --- Motions --------------------------------------------------------------------------------

    def motion_named(self, motion):
        """The named motion a key input's motion is written as, or None."""
        if self.strict or not motion:
            return None
        return next((m for m in self.motions if m.written == list(motion)), None)

    def is_unverified(self, rule_id):
        return rule_id in self.unverified


STRICT = InputRules()


# --- Rule packs -----------------------------------------------------------------------------------

def load_pack(game):
    """A game's rule pack (the generic one if it has none), as loaded from JSON."""
    for name in ([game] if game else []) + ["generic"]:
        path = os.path.join(PACKS, f"{name}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError("rule_packs/generic.json is missing")


def pack_characters(game):
    """{character key: name} that a game's pack has rules for."""
    return {key: c.get("name", key) for key, c in load_pack(game).get("characters", {}).items()}


def _apply(rules, layer):
    """Applies one layer of rule entries (a list of {"id", "type", ...} or changes by id) to a dict
    of rules by id."""
    for entry in layer:
        rule_id = entry["id"]
        if entry.get("remove"):
            rules.pop(rule_id, None)
        elif rule_id in rules:
            rules[rule_id] = {**rules[rule_id], **entry}
        else:
            rules[rule_id] = dict(entry)


def resolve(game=None, scheme=None, character=None, recording=None, strict=False, pack=None, layout=None):
    """The rules for a recording: the game's pack, then its control scheme, then the character
    (exceptions), then the recording's own changes ({"rules": [...]}). strict, or a recording that
    asks for it, gives STRICT. pack: a pack to use instead of the game's file (for tests). layout:
    which recorded button is which action, for exceptions that name actions.

    A character can list the motions it has ("motions": ids from the game's), so its inputs are only
    read as motions it can do, and add its own (charge motions, with their timings)."""
    recording = recording or {}
    if strict or recording.get("strict"):
        return STRICT
    pack = pack if pack is not None else load_pack(game)
    rules = {}
    _apply(rules, pack.get("rules", []))
    sources = [pack.get("name", game or "generic")]
    if scheme and scheme in pack.get("schemes", {}):
        _apply(rules, pack["schemes"][scheme].get("rules", []))
        sources.append(scheme)
    exceptions = {}
    char = pack.get("characters", {}).get(character) if character else None
    if char:
        if "motions" in char:
            keep = set(char["motions"])
            for rule_id in [i for i, r in rules.items() if r["type"] == "motion" and i not in keep]:
                del rules[rule_id]
        _apply(rules, char.get("rules", []))
        for exception in char.get("except", []):
            exceptions.setdefault(exception["rule"], set()).add((exception["direction"], exception["button"]))
        sources.append(char.get("name", character))
    elif character is None:
        # No character: a pair stays exact if any character has a move of its own on it, so nothing
        # that could be a different move is treated as the same.
        for other in pack.get("characters", {}).values():
            for exception in other.get("except", []):
                exceptions.setdefault(exception["rule"], set()).add((exception["direction"], exception["button"]))
    _apply(rules, recording.get("rules", []))
    built = _build(rules, exceptions, " + ".join(sources))
    return replace(built, layout=tuple(sorted((layout or {}).items())))


def _build(rules, exceptions, name):
    on = [r for r in rules.values() if r.get("enabled", True)]
    classes, motions, unverified = [], [], set()
    neutral = False
    window = buffer = 0
    for rule in on:
        kind = rule["type"]
        if not rule.get("source", {}).get("verified", True):
            unverified.add(rule["id"])
        if kind == "direction_classes":
            for directions in rule["classes"]:
                classes.append(DirectionClass(rule["id"], rule.get("name", rule["id"]), tuple(directions),
                                              frozenset(exceptions.get(rule["id"], ()))))
        elif kind == "neutral":
            neutral = True
        elif kind == "multi_press":
            window = int(rule["window"])
        elif kind == "buffer":
            buffer = int(rule["frames"])
        elif kind == "motion":
            charge = rule.get("charge")
            motions.append(Motion(rule["id"], rule.get("name", rule["id"]), _steps(rule["steps"]),
                                  tuple(_steps(s) for s in rule.get("shortcuts", [])),
                                  int(rule.get("max_frames", 0)), int(rule.get("max_step_gap", 0)),
                                  tuple(rule.get("written", ())),
                                  Charge(**charge) if charge else None))
        else:
            raise ValueError(f"Unknown rule type {kind!r} ({rule['id']})")
    return InputRules(name=name, strict=False, neutral_is_neutral=neutral, direction_classes=tuple(classes),
                      multi_press_window=window, buffer=buffer, motions=tuple(motions),
                      unverified=frozenset(unverified), sources=(name,))


def _steps(steps):
    return tuple(tuple(step) for step in steps)


def with_key_input_overrides(rules, key_input):
    """A key input's own changes: {"accept": {"directions": [3]}} narrows what its press accepts
    (handled by the matcher); {"accept": {"strict": true}} grades it literally."""
    accept = key_input.get("accept") or {}
    if accept.get("strict"):
        return STRICT
    return rules


# --- Matching motions -----------------------------------------------------------------------------

def match_steps(steps, track, first, last, max_step_gap=0):
    """Frames (one per step, in order) where track frames first..last pass through steps, ending as
    late as possible; None if they don't. Other directions may come between steps; with
    max_step_gap, each step must come within that many frames of the one before."""
    # Work back from the end: the latest frame for the last step, then the latest before it for the
    # step before, and so on, keeping the earliest-ending alternatives when a gap rules one out.
    def search(step_index, before, after_limit):
        if step_index < 0:
            return []
        wanted = steps[step_index]
        frame = before
        while frame >= first:
            state = track[frame]
            if state is not None and state["direction"] in wanted:
                if after_limit is not None and after_limit - frame > max_step_gap:
                    return None  # Too long before the next step, and earlier frames are further.
                rest = search(step_index - 1, frame - 1, frame if max_step_gap else None)
                if rest is not None:
                    return rest + [frame]
            frame -= 1
        return None

    return search(len(steps) - 1, last, None)


def charge_done(named, track, first, frame, buttons=()):
    """For a charge motion: the frame its release step comes (from first to this frame), with the
    first step held long enough before it and let go no more than the charge keeps; else None. The
    charge itself can be built before the window starts (it usually is)."""
    frames, keep = named.charge.needs(buttons)
    held, release = set(named.steps[0]), set(named.steps[1])
    for f2 in range(frame, first - 1, -1):
        state = track[f2]
        if state is None or state["direction"] not in release:
            continue
        # The last frame of charge before the release, and how long it was held.
        last = next((g for g in range(f2 - 1, max(-1, f2 - keep - 2), -1)
                     if track[g] is not None and track[g]["direction"] in held), None)
        if last is None or f2 - last > keep:
            continue
        length = 0
        g = last
        while g >= 0 and track[g] is not None and track[g]["direction"] in held:
            length, g = length + 1, g - 1
        if length >= frames:
            return f2
    return None


def motion_done(motion, track, first, frame, rules=STRICT, buttons=()):
    """(done, how) for a key input's motion, completed by this frame. Under a game's rules, a named
    motion matches by its pattern and shortcuts, within its time limit (a charge motion by its charge:
    see charge_done); otherwise every direction in order, from the window's first frame (the literal
    reading). buttons: the key input's, for charges that differ with two buttons."""
    named = rules.motion_named(motion)
    if named is None:
        steps = [(direction,) for direction in motion]
        return match_steps(steps, track, first, frame) is not None, None
    if named.charge:
        release = charge_done(named, track, first, frame, buttons)
        return release is not None, (named, "charge" if release is not None else "missed", [release])
    lo = max(first, frame - named.max_frames) if named.max_frames else first
    for steps, how in [(named.steps, None)] + [(s, "shortcut") for s in named.shortcuts]:
        frames = match_steps(steps, track, lo, frame, named.max_step_gap)
        if frames is not None:
            return True, (named, how, frames)
    return False, (named, "missed", None)


def recognise_motion(track, first, last, press_direction, rules):
    """The named motion the directions in frames first..last make, for derive: preferring one whose
    last step is the press's direction (6236+P pressed at 6 is a fireball, 6323+P at 3 a DP), then
    the one listed first. None under STRICT or if none fits."""
    if rules.strict:
        return None
    fits = []
    for order, named in enumerate(rules.motions):
        if named.charge:
            if charge_done(named, track, first, last) is not None:
                fits.append((press_direction not in named.steps[1], -len(named.steps), order, named))
            continue
        for steps in (named.steps,) + named.shortcuts:
            frames = match_steps(steps, track, max(first, last - named.max_frames) if named.max_frames else first,
                                 last, named.max_step_gap)
            if frames is not None:
                ends_at_press = press_direction in steps[-1]
                fits.append((not ends_at_press, -len(steps), order, named))
                break
    return min(fits)[3] if fits else None
