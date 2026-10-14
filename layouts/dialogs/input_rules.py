"""The open recording's input rules: what counts as the same input, and the player's changes to it."""
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

import rule_edits
import theme
from input_rules import BUILT_IN, RECORDING, YOURS, YOURS_CHARACTER, is_empty
from layouts.dialogs.accept import frame_choices
from layouts.dialogs.note import NotePopup
from layouts.ui_kit import (
    DIM_TEXT_COLOR, FONT_SIZE, PANEL_COLOR, TEXT_COLOR, Dialog, OnOffSwitch, Stepper, Toggle, button, confirm_button,
    dropdown, paint_background, section_title
)

GENERIC = "Generic (any game)"
NEW_RULE_SET = "New rule set..."
NO_CHARACTER = "Not set"
NEW_CHARACTER = "New character..."
ORIGIN_TEXT = {BUILT_IN: "built in", YOURS: "your rules", YOURS_CHARACTER: "your character rules",
               RECORDING: "this recording"}
ADD_KINDS = {"Direction group": "direction_classes", "Motion": "motion", "Charge motion": "charge"}
SIMPLE_NAMES = {"neutral": "Neutral is neutral", "multi_press": "Simultaneous presses", "buffer": "Input buffer"}


def _numbers(text):
    return [int(c) for c in text if c in "123456789"]


def rule_summary(rule):
    """What a rule does, in a line."""
    kind = rule["type"]
    if kind == "direction_classes":
        groups = "; ".join(", ".join(str(d) for d in c) for c in rule["classes"])
        return f"{groups} + a button are the same press (written {rule['classes'][0][0]})"
    if kind == "neutral":
        return "A press at neutral needs neutral (or its group), not any direction"
    if kind == "multi_press":
        return "Buttons pressed this many frames apart count as together"
    if kind == "buffer":
        return "A press this many frames before its window still counts"
    steps = rule_edits.steps_text(rule["steps"])
    if rule.get("charge"):
        held, release = rule["steps"]
        return f"Hold {''.join(map(str, held))} to charge, then {''.join(map(str, release))}"
    shortcuts = rule.get("shortcuts", [])
    return f"Steps {steps}" + (f"; or {len(shortcuts)} other way{'s' * (len(shortcuts) != 1)}" if shortcuts else "")


class InputRulesPopup(Dialog):
    """Shows the recording's rules, layer by layer, and changes them in one scope at a time: the
    recording (saved with it), the player's rules for its game, or for its character. Rules can be
    switched off, have their frames changed, and be added (direction groups, motions, charge
    motions); exceptions (a character's own 3HK) can be added or undone. session is a
    rule_edits.RulesSession; on_message(text) shows a message in the app."""

    ROW = dp(32)
    WIDTH = dp(780)

    def __init__(self, session, game_name, on_message=lambda text: None, **kwargs):
        height = min(dp(720), Window.height * 0.92)
        super().__init__(size_hint=(None, None), size=(self.WIDTH, height), background="",
                         background_color=(0, 0, 0, 0.5), **kwargs)
        self.session, self.game_name, self.on_message = session, game_name, on_message
        self.scope = RECORDING
        self.add_kind = "Direction group"
        self.inner = self.WIDTH - dp(40)
        panel = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(6))
        paint_background(panel, PANEL_COLOR)
        header = BoxLayout(size_hint_y=None, height=dp(28))
        header.add_widget(Label(text="Input rules", font_size=theme.TITLE, bold=True, color=TEXT_COLOR,
                                size_hint_x=None, width=dp(160), halign="left", valign="middle",
                                text_size=(dp(160), dp(28))))
        self.name_label = Label(font_size=FONT_SIZE, color=(*theme.ACCENT, 1), halign="right", valign="middle",
                                shorten=True)
        self.name_label.bind(size=lambda label, size: setattr(label, "text_size", size))
        header.add_widget(self.name_label)
        panel.add_widget(header)
        panel.add_widget(Label(
            text="What counts as the same input when this recording is read and graded. Built-in rules come from "
                 "the game's rule pack; your rules go on top of them for every recording of the game, and this "
                 "recording's changes on top of those.", font_size=theme.CAPTION, color=DIM_TEXT_COLOR,
            size_hint_y=None, height=dp(34), halign="left", valign="top", text_size=(self.inner, dp(34))))
        self.settings_rows = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
        self.settings_rows.bind(minimum_height=self.settings_rows.setter("height"))
        panel.add_widget(self.settings_rows)
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(6), scroll_type=["bars", "content"])
        self.body = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(2), padding=(0, 0, dp(10), 0))
        self.body.bind(minimum_height=self.body.setter("height"))
        scroll.add_widget(self.body)
        panel.add_widget(scroll)
        footer = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(8))
        self.reset_button = confirm_button("Undo all changes here", self._reset)
        footer.add_widget(self.reset_button)
        self.message = Label(font_size=theme.CAPTION, color=DIM_TEXT_COLOR, halign="left", valign="middle")
        self.message.bind(size=lambda label, size: setattr(label, "text_size", size))
        footer.add_widget(self.message)
        footer.add_widget(button("Done", self.dismiss, "primary"))
        panel.add_widget(footer)
        self.add_widget(panel)
        self.refresh()

    # ---- Building -----------------------------------------------------------------------------

    def refresh(self):
        session = self.session
        if self.scope not in session.scopes():
            self.scope = RECORDING
        self.layers = session.layers()
        self.scope_layer = session.layer(self.scope)
        self.name_label.text = "Strict (graded literally)" if session.strict() else self.layers.name
        self.settings_rows.clear_widgets()
        self._build_top()
        self.body.clear_widgets()
        self._build_rules()
        self._build_exceptions()
        self._build_add()
        self.reset_button.disabled = not self.scope_layer or is_empty(self.scope_layer)

    def _row(self, label, *widgets, height=None):
        row = BoxLayout(size_hint_y=None, height=height or self.ROW, spacing=dp(8))
        row.add_widget(Label(text=label, font_size=FONT_SIZE, color=TEXT_COLOR, halign="left", valign="middle",
                             size_hint_x=None, width=dp(110), text_size=(dp(110), height or self.ROW)))
        for widget in widgets:
            row.add_widget(widget)
        return row

    @staticmethod
    def _text(text, width=None, dim=False, **kwargs):
        label = Label(text=text, font_size=theme.CAPTION if dim else FONT_SIZE, color=DIM_TEXT_COLOR if dim else TEXT_COLOR,
                      halign="left", valign="middle", **kwargs)
        if width:
            label.size_hint_x, label.width = None, width
        label.bind(size=lambda l, size: setattr(l, "text_size", size))
        return label

    def _build_top(self):
        session = self.session
        if session.game:
            source = self._text(f"{self.game_name} (pick the game in Edit > Game actions and character)")
        else:
            sets = session.custom_rule_sets()
            current = session.controller.get_rule_changes().get("pack")
            names = [GENERIC] + list(sets.values()) + [NEW_RULE_SET]
            shown = sets.get(current) or (session.controller.get_rule_changes().get("pack_data", {}).get("name")
                                          if current else None) or GENERIC
            if shown not in names:
                names.insert(1, shown)  # A rule set this recording carries, not installed here.
            source = dropdown(names, shown, lambda name: self._choose_rule_set(name, sets))
            source.size_hint_y = 1
        self.settings_rows.add_widget(self._row("Rules for", source))

        characters = session.characters()
        names = [NO_CHARACTER] + sorted(characters.values()) + ([NEW_CHARACTER] if session.key else [])
        picker = dropdown(names, characters.get(session.character(), NO_CHARACTER),
                          lambda name: self._choose_character(name, characters))
        picker.size_hint_y = 1
        picker.disabled = len(names) == 1
        hint = self._text("A character's own moves stay exact" if session.key else
                          "Make a rule set for this game to add characters", dim=True)
        self.settings_rows.add_widget(self._row("Character", picker, hint))

        switch = OnOffSwitch(session.strict(), self._set_strict)
        box = BoxLayout(size_hint_x=None, width=switch.width, padding=(0, dp(4)))
        box.add_widget(switch)
        self.settings_rows.add_widget(self._row("Strict", box, self._text(
            "Graded literally: exact directions, every direction of a motion, buttons on the same frame",
            dim=True)))

        scopes = BoxLayout(spacing=dp(4))
        character_name = characters.get(session.character(), "")
        labels = {RECORDING: "This recording", YOURS: f"All {self._key_name()} recordings",
                  YOURS_CHARACTER: f"All {character_name} recordings"}
        for scope in (RECORDING, YOURS, YOURS_CHARACTER):
            toggle = Toggle(text=labels[scope], group="rules-scope", allow_no_selection=False,
                            state="down" if scope == self.scope else "normal")
            toggle.disabled = scope not in session.scopes()
            toggle.bind(state=lambda t, state, scope=scope: state == "down" and self._set_scope(scope))
            scopes.add_widget(toggle)
        self.settings_rows.add_widget(self._row("Changes go to", scopes))

    def _key_name(self):
        if self.session.game:
            return self.game_name
        sets = self.session.custom_rule_sets()
        return sets.get(self.session.key, self.session.key or "")

    def _build_rules(self):
        self.body.add_widget(section_title("Rules", self.inner - dp(10)))
        for rule_id, rule in self.layers.rules.items():
            self.body.add_widget(self._rule_row(rule_id, rule))

    def _origin(self, origins):
        return ", ".join(ORIGIN_TEXT[o] for o in origins)

    def _rule_row(self, rule_id, rule):
        row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        enabled = rule.get("enabled", True)
        # The switch reports its starting state too: only a change is an edit.
        switch = OnOffSwitch(enabled, lambda on: on != enabled and self._edit(rule_edits.change_rule, rule_id, enabled=on))
        box = BoxLayout(size_hint_x=None, width=switch.width, padding=(0, dp(11)))
        box.add_widget(switch)
        row.add_widget(box)
        unverified = "  [color=#e0a040]unverified[/color]" if not rule.get("source", {}).get("verified", True) else ""
        text = (f"{rule.get('name', rule_id)}  [size={int(theme.CAPTION)}][color=#8a8a96]"
                f"{self._origin(self.layers.origins.get(rule_id, []))}[/color]{unverified}[/size]\n"
                f"[size={int(theme.CAPTION)}][color=#8a8a96]{rule_summary(rule)}[/color][/size]")
        row.add_widget(self._text(text, markup=True))
        for widget in self._rule_values(rule_id, rule):
            row.add_widget(widget)
        own = next((e for e in self.scope_layer.get("rules", []) if e["id"] == rule_id), None)
        if own is not None:
            added = "type" in own
            row.add_widget(button("Remove" if added else "Undo", lambda: self._edit(rule_edits.remove_rule, rule_id),
                                  size_hint_x=None, width=dp(70),
                                  tooltip="Take this rule away" if added else "Undo the change made here"))
        else:
            row.add_widget(Widget(size_hint_x=None, width=dp(70)))
        return row

    def _rule_values(self, rule_id, rule):
        """Steppers for a rule's frame values."""
        def stepper(choices, value, field, width=dp(150), wrap=None):
            change = (lambda v: self._edit(rule_edits.change_rule, rule_id, **{field: wrap(v) if wrap else v}))
            widget = Stepper(choices, value, change, size_hint_x=None, width=width)
            box = BoxLayout(size_hint_x=None, width=width, padding=(0, dp(7)))
            box.add_widget(widget)
            return box

        kind = rule["type"]
        if kind == "multi_press":
            return [stepper(frame_choices(10, "same frame"), int(rule["window"]), "window")]
        if kind == "buffer":
            return [stepper(frame_choices(15, "none"), int(rule["frames"]), "frames")]
        if kind == "motion" and rule.get("charge"):
            charge = rule["charge"]
            return [stepper(frame_choices(120, "", 1, 1), int(charge["frames"]), "charge", dp(120),
                            lambda v: {**charge, "frames": v, "frames_two": 0}),
                    stepper(frame_choices(30, "not kept"), int(charge["keep"]), "charge", dp(120),
                            lambda v: {**charge, "keep": v, "keep_two": 0})]
        if kind == "motion":
            return [stepper(frame_choices(60, "any time"), int(rule.get("max_frames", 0)), "max_frames")]
        return []

    def _build_exceptions(self):
        self.body.add_widget(section_title("Moves of their own", self.inner - dp(10)))
        self.body.add_widget(self._text(
            "A direction and button that do something else, so the rest of their direction group doesn't count "
            "for them (Chun-Li's 3HK isn't her sweep).", dim=True, size_hint_y=None, height=dp(30)))
        groups = {rule_id: rule for rule_id, rule in self.layers.rules.items() if rule["type"] == "direction_classes"}
        for rule_id, pairs in sorted(self.layers.exceptions.items()):
            if rule_id not in groups:
                continue
            for direction, button_name in sorted(pairs):
                origin = self.layers.exception_origins.get((rule_id, direction, button_name), BUILT_IN)
                row = BoxLayout(size_hint_y=None, height=dp(30), spacing=dp(8))
                row.add_widget(self._text(f"{direction}{button_name}", width=dp(70)))
                row.add_widget(self._text(f"its own move, not {groups[rule_id].get('name', rule_id)}  "
                                          f"[color=#8a8a96]{ORIGIN_TEXT[origin]}[/color]", markup=True))
                row.add_widget(button("Same as its group", lambda r=rule_id, d=direction, b=button_name:
                                      self._edit(rule_edits.drop_exception, r, d, b), size_hint_x=None, width=dp(150)))
                self.body.add_widget(row)
        directions = sorted({d for rule in groups.values() for c in rule["classes"] for d in c})
        if not directions:
            self.body.add_widget(self._text("No direction groups: add one below first.", dim=True, size_hint_y=None,
                                            height=dp(30)))
            return
        self.new_direction = dropdown([str(d) for d in directions], str(directions[0]), lambda _: None)
        self.new_direction.size_hint_x, self.new_direction.width = None, dp(70)
        names = self.session.button_names()
        self.new_button = dropdown(names, names[0], lambda _: None)
        self.new_button.size_hint_x, self.new_button.width = None, dp(110)
        row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8), padding=(0, dp(2)))
        row.add_widget(self._text("Add:", width=dp(40)))
        row.add_widget(self.new_direction)
        row.add_widget(self._text("+", width=dp(14)))
        row.add_widget(self.new_button)
        row.add_widget(button("Is its own move", self._add_exception))
        row.add_widget(Widget())
        self.body.add_widget(row)

    def _build_add(self):
        self.body.add_widget(section_title("Add a rule", self.inner - dp(10)))
        missing = [name for kind, name in SIMPLE_NAMES.items()
                   if not any(r["type"] == kind for r in self.layers.rules.values())]
        kinds = list(ADD_KINDS) + missing
        if self.add_kind not in kinds:
            self.add_kind = kinds[0]
        picker = dropdown(kinds, self.add_kind, self._choose_add_kind)
        picker.size_hint_x, picker.width = None, dp(160)
        self.fields = {}
        row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8), padding=(0, dp(2)))
        row.add_widget(picker)
        kind = ADD_KINDS.get(self.add_kind)
        hint = ""
        if kind:
            row.add_widget(self._field("name", "Name", dp(120)))
        if kind == "direction_classes":
            row.add_widget(self._field("directions", "Directions, e.g. 213", dp(170), digits=True))
            hint = "Directions that do the same press with a button; the first is how it's written."
        elif kind == "motion":
            row.add_widget(self._field("steps", "Steps, e.g. 6 21 3", dp(160), digits=True))
            row.add_widget(self._field("shortcuts", "Other ways, e.g. 26, 3236", dp(170), digits=True, commas=True))
            hint = ("Directions in order; other directions may come between them. Spaces separate steps that take "
                    "more than one direction (6 21 3: 6, then 2 or 1, then 3). A key input written as the steps "
                    "(236) is then matched by them.")
        elif kind == "charge":
            row.add_widget(self._field("held", "Hold, e.g. 417", dp(110), digits=True))
            row.add_widget(self._field("release", "Then, e.g. 6", dp(90), digits=True))
            row.add_widget(self._field("frames", "Frames", dp(70), digits=True, numbers=True))
            row.add_widget(self._field("keep", "Kept", dp(60), digits=True, numbers=True))
            hint = ("Hold any of the first directions for the frames, then go to the second within the kept frames "
                    "of letting go. Written [4]6.")
        row.add_widget(button("Add", self._add_rule, "primary"))
        row.add_widget(Widget())
        self.body.add_widget(row)
        if hint:
            self.body.add_widget(self._text(hint, dim=True, size_hint_y=None, height=dp(34)))

    def _field(self, name, hint, width, digits=False, numbers=False, commas=False):
        allowed = "0123456789" if numbers else "123456789 " + ("," if commas else "")
        field = TextInput(multiline=False, font_size=FONT_SIZE, size_hint_x=None, width=width, hint_text=hint,
                          background_color=(1, 1, 1, 0.08), foreground_color=TEXT_COLOR, cursor_color=TEXT_COLOR,
                          hint_text_color=DIM_TEXT_COLOR, write_tab=False,
                          input_filter=(lambda text, undo: "".join(c for c in text if c in allowed)) if digits else None)
        self.fields[name] = field
        return field

    # ---- Changes ------------------------------------------------------------------------------

    def _say(self, text):
        self.message.text = text

    def _edit(self, change, *args, **kwargs):
        self.session.edit(self.scope, lambda layer: change(layer, *args, **kwargs))
        self.refresh()

    def _set_scope(self, scope):
        if scope != self.scope:
            self.scope = scope
            self.refresh()

    def _set_strict(self, strict):
        if strict != self.session.strict():
            self.session.set_strict(strict)
            self.refresh()

    def _choose_character(self, name, characters):
        if name == NEW_CHARACTER:
            NotePopup("New character", "", self._new_character, hint="The character's name").open()
            self.refresh()  # The picker goes back to the character until one is made.
            return
        key = next((k for k, v in characters.items() if v == name), None)
        if key != self.session.character():
            self.session.set_character(key)
            self.refresh()

    def _new_character(self, name):
        if name:
            self.session.new_character(name)
            self.scope = YOURS_CHARACTER
            self._say(f"Added {name}. Changes to their rules now go to all {name} recordings.")
            self.refresh()

    def _choose_rule_set(self, name, sets):
        if name == NEW_RULE_SET:
            NotePopup("New rule set", "", self._new_rule_set, hint="The game's name").open()
            self.refresh()
            return
        key = next((k for k, v in sets.items() if v == name), None)
        if name == GENERIC:
            key = None
        elif key is None:
            return  # The one the recording carries: already in use.
        self.session.use_rule_set(key)
        self.refresh()

    def _new_rule_set(self, name):
        if name:
            self.session.new_rule_set(name)
            self.scope = YOURS
            self._say(f"Made the {name} rule set from the generic rules. Your changes go to all {name} recordings.")
            self.refresh()

    def _choose_add_kind(self, kind):
        if kind != self.add_kind:
            self.add_kind = kind
            self.refresh()

    def _add_exception(self):
        direction = int(self.new_direction.text)
        group = next((rule_id for rule_id, rule in self.layers.rules.items() if rule["type"] == "direction_classes"
                      and rule.get("enabled", True) and any(direction in c for c in rule["classes"])), None)
        if group is None:
            self._say(f"No direction group takes {direction}")
            return
        self._edit(rule_edits.add_exception, group, direction, self.new_button.text)
        self._say(f"{direction}{self.new_button.text} is now a move of its own")

    def _add_rule(self):
        rule = self._new_rule()
        if isinstance(rule, str):
            self._say(rule)
            return
        self._edit(rule_edits.add_rule, rule)
        self._say(f"Added {rule.get('name', rule['id'])}")

    def _new_rule(self):
        """The rule the add row describes, or what's wrong with it."""
        rules = self.layers.rules
        kind = ADD_KINDS.get(self.add_kind)
        if kind is None:
            kind = next(k for k, name in SIMPLE_NAMES.items() if name == self.add_kind)
            rule = dict(rule_edits.SIMPLE_RULES[kind])
            if rule["id"] in rules:
                rule["id"] = rule_edits.new_id(rules, rule["name"])
            return rule
        values = {name: field.text.strip() for name, field in self.fields.items()}
        name = values["name"]
        if kind == "direction_classes":
            directions = _numbers(values["directions"])
            if len(directions) < 2 or len(set(directions)) != len(directions):
                return "A direction group needs two or more different directions"
            return rule_edits.direction_group(rules, name or "Direction group", directions)
        if kind == "motion":
            steps = rule_edits.parse_steps(values["steps"])
            if not steps or len(steps) < 2:
                return "A motion needs two or more steps, e.g. 236"
            shortcuts = []
            for text in filter(None, (t.strip() for t in values["shortcuts"].split(","))):
                shortcut = rule_edits.parse_steps(text)
                if not shortcut:
                    return f"Not a way to do it: {text}"
                shortcuts.append(shortcut)
            written = [s[0] for s in steps]
            clash = next((r for r in rules.values() if r["type"] == "motion" and r.get("enabled", True)
                          and (r.get("written") or [s[0] for s in r["steps"]]) == written), None)
            if clash:
                return (f"There's already a motion written {rule_edits.steps_text([[d] for d in written])} "
                        f"({clash.get('name', clash['id'])}): change that one instead")
            return rule_edits.motion(rules, name or rule_edits.steps_text(steps), steps, shortcuts)
        held, release = _numbers(values["held"]), _numbers(values["release"])
        if not held or not release or set(held) & set(release):
            return "A charge needs directions to hold and different ones to go to"
        if not values["frames"]:
            return "How many frames does the charge take?"
        return rule_edits.charge_motion(rules, name or f"[{held[0]}]{release[0]}", held, release,
                                        int(values["frames"]), int(values["keep"] or 0))

    def _reset(self):
        self.session.reset(self.scope)
        self._say("Changes undone")
        self.refresh()
