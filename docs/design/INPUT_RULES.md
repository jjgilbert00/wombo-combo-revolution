# Input rules: how each game reads inputs (design)

Status: built so far: the engine (`input_rules.py`), the generic pack, the SF6 pack for Classic
controls (every character's command normals, motions and charge timings), and the player's own
rules: *Edit > Input rules...* (rule edits for the recording, the game or a character, custom rule
sets for games without a pack) and the key input editor's *Accepts* (one input's own leniency). Not
yet: SF6 Modern controls, the other games' packs, hub-hosted packs, side-switch markers and the
calibration mode.

## The problem

Two parts of the app decide what an input *means*:

- **The interpreter** turns raw frames into a move: `derive` guesses a key input from a selection,
  `describe` writes it in notation, `demo_track` plays it back clean.
- **The grader** decides whether an attempt did that move: `satisfied_at`, `_motion_done`,
  `_pressed_at` and the hold checks in `key_inputs.py`.

Both are literal today: a press needs the exact direction recorded, a motion needs every direction
that was seen, and buttons count only if they're pressed on the same frame. Games are more lenient,
and differently lenient: in Street Fighter 6, 1HK, 2HK and 3HK all do the sweep, unless the
character has a 3HK of their own; in Tekken, d+1, df+1 and db+1 are three different moves for almost
everyone. So what counts as the same input depends on the game, the control scheme and the character,
and sometimes on the move.

This document lists those rules across the games the hub covers, and designs a system that applies
them to both the interpreter and the grader, which users can see, switch and tune.

## Goals

1. One description of each game's input rules, used by the interpreter, the grader and the demo.
2. Rules at the right level: game, control scheme, character, recording, single key input. A lower
   level can switch off or adjust anything above it (Ken's 3HK isn't a sweep).
3. Every decision explainable: "your 1HK counted as 2HK (crouching normals)", "a gap of 4 frames
   between MP and MK; this game allows 2".
4. Data, not code: adding a game, a character or a patch change means editing a rule pack, not
   Python. Packs can be shared through the hub.
5. **Game rules by default** (decided): recordings are interpreted and graded with their game's rules
   unless the user turns on *Strict*, which is today's literal behaviour, for a recording or for a game.

## Rule catalog

Confidence says how sure this document is that the game works this way. **Known**: well documented.
**Likely**: how these games usually work; confirm. **Verify**: plausible, check against the game
before shipping the default. Frame values in packs should come from each game's own documentation or
frame-data sites, never from this table.

Games: **SF6** Street Fighter 6, **T8** Tekken 8, **GGST** Guilty Gear -Strive-, **GBVSR**
Granblue Fantasy Versus: Rising, **MK1** Mortal Kombat 1, **COTW** Fatal Fury: City of the Wolves.

### A. Which direction a button press needs

| # | Rule | Games | Scope | Confidence | Interpreter | Grader |
|---|---|---|---|---|---|---|
| A1 | **Crouching normals**: any down direction (1, 2, 3) plus a button is the same crouching normal, except a character's own command normals on 1 or 3. | SF6, GGST, GBVSR, COTW | Game default, character exceptions | Known (SF6); Likely (others) | Writes 1HK and 3HK as `2HK` | 1/2/3 + button satisfy a `2X` key input |
| A2 | **Standing normals**: back or forward plus a button is the standing normal, except command normals. | SF6, GBVSR, COTW | Game default, character exceptions (e.g. SF6 Ryu's 6MP, Collarbone Breaker, is a different move) | Known (SF6) | Writes 4MP as `5MP` / `MP` | 4/5/6 + button satisfy a `5X` |
| A3 | **Forward + button is usually its own move**: so A2 is off by default. | GGST (6P for everyone, 6H for most), MK1 (F+button, B+button strings), T8 | Game default | Known (GGST 6P, T8); Likely (MK1) | Keeps 6P distinct | Exact direction |
| A4 | **Every direction is its own move**: d, df, db, f, b, u, uf, ub + button all differ. | T8 | Game default | Known | Keeps all 8 | Exact direction |
| A5 | **Neutral is neutral**: a standing normal recorded at 5 needs 5 (or A2's set), not *any* direction. Today a neutral press accepts any direction, so a command normal passes. | All | Game default | Known (it's a bug fix) | `MP` stores direction 5, not "any" | 5 (plus A2's set if on) |
| A6 | **Air normals**: in the air, the direction usually doesn't change the attack, except air command normals (j.2H and the like). | SF6, GGST, GBVSR, COTW | Game default, character exceptions | Likely | Writes j.X | Jump direction ignored for air normals |
| A7 | **Jump direction**: 7, 8 and 9 all jump; the direction only changes the arc. | 2D games | Game default | Known | Collapses a jump's frames to 7/8/9 | Lenient on the arc only if the key input says so |

### B. Buttons

| # | Rule | Games | Scope | Confidence | Interpreter | Grader |
|---|---|---|---|---|---|---|
| B1 | **Simultaneous-press window**: buttons pressed within N frames of each other count as one press. | All (N differs) | Game, scheme | Known that it exists; Verify N | `derive` gathers presses within N frames (today: only the first frame) | Accepts presses up to N frames apart |
| B2 | **Button classes**: "P" is any punch, "K" any kick, for moves whose strength doesn't matter to the combo. | SF6 (P/K), COTW (Likely) | Game; per key input | Known (SF6 notation) | Writes `236P` when the key input allows any strength | Any button in the class |
| B3 | **Two of a class** (EX / OD style): any two punches, or any two kicks. | SF6 (OD), others | Game | Known (SF6 OD) | Writes `236PP` | Any two of the class within B1's window |
| B4 | **Named combinations**: fixed buttons pressed together (SF6: HP+HK Drive Impact, MP+MK Drive Parry, LP+LK throw). | SF6, GGST (Roman Cancel: any three attack buttons, Verify), T8 (Heat, Verify) | Game | Known (SF6) | Names the move (already in `games.py`) | Uses B1's window |
| B5 | **Negative edge**: releasing a button can complete a special. | Verify per game | Game | Verify | No change | A release counts as the press for specials |
| B6 | **Mash**: N presses within W frames. | Some moves in several games | Move (key input) | Known that they exist | New key input type | Counts presses |
| B7 | **Hold a button**: hold for N frames, then release (charge or hold attacks). | GGST, SF6, MK1 (some moves) | Move | Known that they exist | Already: hold key inputs | Already: hold key inputs |

### C. Motions

| # | Rule | Games | Scope | Confidence | Interpreter | Grader |
|---|---|---|---|---|---|---|
| C1 | **Named motions**: 236, 214, 623, 421, 41236, 63214, 236236, 214214, 360, 720. | SF6, GGST, GBVSR, COTW; T8 uses some (qcf, hcf) | Game | Known | Reduces raw directions to the named motion (`6323` to `623`) | Matches the motion's pattern, not every direction seen |
| C2 | **Extra directions are allowed** between a motion's steps. | All motion-based games | Game | Likely | — | Allowed (today's behaviour) |
| C3 | **Skipped diagonals**: e.g. 2 then 6 as a quarter circle. | Verify per game | Game | Verify | — | Optional per motion |
| C4 | **Shortcuts**: e.g. the DP motion accepting 6-2-3, 6-3-2-3, 3-2-3. | SF6 and others | Game, per motion | Verify the exact set per game | Recognises them as 623 | Accepts the listed variants |
| C5 | **Motion time limit**: the motion must be done within N frames of the button (overall, and between steps). | All | Game, per motion | Known that it exists; Verify N | — | Rejects a slow motion (today: anything since the window started) |
| C6 | **360 / 720**: a full turn, accepting fewer than all eight directions, and an up direction that the move's startup absorbs. | SF6 grapplers, COTW, GGST (Potemkin) | Game, character | Likely | Recognises as 360 | Turn-based pattern |
| C7 | **Charge**: hold back (or down) for N frames, then forward (or up) plus a button; charge kept for a few frames after release. | SF6 (charge characters), COTW (charge characters, Likely) | Character, per move | Known (SF6) | Writes `[4]6P` | Needs N frames of charge, with the after-release buffer |
| C8 | **Charge directions**: holding 1 charges both back and down. | SF6 | Game | Known | — | Already: charge-style directions in hold key inputs |
| C9 | **Taps**: a dash is 66 or 44 within N frames; Tekken's f,f, b,b; MK1's F,F (Likely). | All | Game | Known | Writes `66` | Two taps within N frames |
| C10 | **Tap vs hold**: f (tapped) and F (held) are different inputs in Tekken. | T8 | Game | Known | Writes `f` or `F` | Uses the hold length |
| C11 | **Just frame**: a step must land on one exact frame (Electric Wind God Fist: f,n,d,df+2). | T8 | Character, per move | Known | Marks the move as exact | Already: exact key inputs; the rule supplies the timing |
| C12 | **Input buffer**: a press made up to N frames before the move can come out still comes out. | All (N differs, and by situation) | Game | Known that it exists; Verify N | — | A press within N frames before the window is HIT, not EARLY |

### D. Control schemes and the controller

| # | Rule | Games | Scope | Confidence | Interpreter | Grader |
|---|---|---|---|---|---|---|
| D1 | **Simplified schemes**: a special button plus a direction does a special; an assist button auto-combos. | SF6 Modern, GBVSR Assisted, T8 Special Style, COTW Smart Style (Likely) | Scheme | Known (SF6, GBVSR, T8) | Names SP+6 as the move it does | A key input can accept either scheme's input for the same move |
| D2 | **SOCD**: what left+right and up+down at once become. SF6's tournament standard is left+right = neutral, up+down = up. | All (differs) | Game | Known (SF6 standard); Verify others | Applied when reading frames | Same |
| D3 | **Facing and side switches**: directions are relative to facing; a cross-up switches it mid-combo. | All | Recording (side markers) | Known | Side markers in the recording (one side per recording today) | Mirrors after a marker |

### Character-specific rules (examples of the shape)

- **Command normals** that break A1 or A2: SF6 Ryu's 6MP (Collarbone Breaker) isn't his standing MP,
  and the 3HK you mentioned for some SF6 characters isn't their sweep. A character file lists them;
  the game's equivalence rules then leave those direction-and-button pairs exact.
- **Charge moves** (C7) and **360s** (C6) belong to particular characters.
- **Just frames** (C11) belong to particular moves (Tekken's Mishimas).
- **Special motions** some characters have that others don't (e.g. 214214, 632146).

Which characters have which command normals should be read from each game's move list or a frame-data
site when a character file is written. (The SF6 pack's come from SuperCombo's Data pages: see
rule_packs/sf6.json.)

## Design

### Layers

A rule set is resolved from layers, each able to switch rules on or off, change their parameters,
and add exceptions. Lower layers win:

1. **Game pack**: the game's defaults (rules A–D with its parameters).
2. **Control scheme**: Classic / Modern, Technical / Assisted, and so on (D1, button names).
3. **Character**: exceptions (command normals), charge moves, special motions, just frames.
4. **Patch**: a game version can change any of the above (games are patched; the hub already tracks
   versions).
5. **Recording**: the user's choices for this recording ("treat this as strict").
6. **Key input**: per-move overrides in the key input editor (accept only 3HK here; any punch here).

As built, the player's own rules sit between the pack and the recording: the pack (and scheme), then
**your rules** for the game, the pack's character, **your rules** for that character, then the
recording's changes, then the key input's. Your rules are files in the settings folder
(`%APPDATA%\wombocomboule_packs\<game>.json`), the same shape as a recording's changes:

```json
{"rules": [{"id": "buffer", "frames": 6}, {"id": "dp", "enabled": false},
           {"id": "my-hcf", "type": "motion", "name": "41236", "steps": [[4], [1], [2], [3], [6]]}],
 "except": [{"rule": "crouching", "direction": 3, "button": "HK"}],
 "allow": [{"rule": "standing", "direction": 6, "button": "MP"}],
 "characters": {"ryu": {"name": "Ryu", "rules": [], "except": [], "allow": []}}}
```

A change names a rule by id and gives only what differs; a whole rule (with `type`) adds one; `allow`
undoes an exception from a layer below. For a game with no pack, a **custom rule set** is such a
file with `"custom": true` and a name, built on the generic pack; a recording using one names it
(`"pack"`) and carries a copy (`"pack_data"`), used where the set isn't installed. Motions a player
adds survive a character's motion list (which only filters the pack's own).

Without a character, the app uses only the rules that hold for **every** character in the game pack
(computed: a direction-and-button pair stays exact if any character has a command normal on it) and
suggests picking the character. That's safe by construction: it never accepts an input as equivalent
when it could be a different move.

### Rule types

Rule packs are JSON (no new dependency; Python 3.10 has no TOML reader). Each rule has an `id`, a
`type`, `enabled`, its parameters, and optional `except` entries. The types, and the engine part that
uses each:

| Type | Parameters | Used by |
|---|---|---|
| `direction_classes` | `button_scope` (ground / air / all), `classes` (e.g. `[[1,2,3],[4,5,6]]`), `except` (pairs like `{"direction": 3, "button": "HK"}`) | Press matcher |
| `button_classes` | `classes` (`{"P": ["LP","MP","HP"]}`) | Press matcher, notation |
| `multi_press` | `window` (frames) | Press matcher, `derive` |
| `named_buttons` | `name`, `buttons`, `count` (any N of a class) | Press matcher, notation (extends `games.py`) |
| `motion` | `name` (623), `pattern` (steps, see below), `max_frames`, `max_step_gap`, `skip_diagonals`, `shortcuts` | Motion recogniser |
| `charge` | `direction` (with charge-style equivalents), `frames`, `keep_after_release` | Charge tracker |
| `tap` | `direction`, `count`, `window`, `max_hold` (for tap vs hold) | Tap recogniser |
| `buffer` | `frames` (before the window) | Grader |
| `negative_edge` | `enabled`, `for` (specials) | Press matcher |
| `socd` | `left_right`, `up_down` (neutral / first / last / up) | Frame normaliser |
| `just_frame` | per move: step timing | Grader (exact key inputs) |

**Motion patterns** are sequences of steps, each step a set of acceptable directions, matched in
order against the frames before the press: 623 is `[{6}, {2,1,3}, {3}]` with `shortcuts:
[[{3},{2},{3}]]`; a step set like `{2,1,3}` is how "any down" is said. `skip_diagonals` lets a
diagonal step be missed. The recogniser is a small automaton per pattern, run over the direction
stream with the time limits: no regular expressions over strings.

### Example pack (abridged)

```json
{
  "game": "sf6",
  "version": "2026.09",
  "rules": [
    {"id": "crouching-normals", "type": "direction_classes", "button_scope": "ground",
     "classes": [[1, 2, 3]], "enabled": true},
    {"id": "standing-normals", "type": "direction_classes", "button_scope": "ground",
     "classes": [[4, 5, 6]], "enabled": true},
    {"id": "simultaneous", "type": "multi_press", "window": 2,
     "source": {"verified": false, "note": "placeholder until measured"}},
    {"id": "punches", "type": "button_classes", "classes": {"P": ["LP", "MP", "HP"], "K": ["LK", "MK", "HK"]}},
    {"id": "dp", "type": "motion", "name": "623", "pattern": [[6], [1, 2, 3], [3]],
     "shortcuts": [[[3], [2], [3]]], "max_frames": 15},
    {"id": "socd", "type": "socd", "left_right": "neutral", "up_down": "up"}
  ],
  "schemes": {"modern": {"rules": [{"id": "sp-specials", "type": "named_buttons", "name": "SP", "buttons": ["RB"]}]}},
  "characters": {
    "ryu": {"except": [{"rule": "standing-normals", "direction": 6, "button": "MP", "move": "Collarbone Breaker"}]}
  }
}
```

(The frame values above are placeholders, not SF6's real numbers.)

### Where rules apply

A resolved `InputRules` object is passed into the functions that interpret and grade. They stay pure
(a track and rules in, a result out), so they stay testable:

- **Frame normaliser** (SOCD), when frames are read.
- **`derive`**: collects presses within the multi-press window; reduces the directions before a press
  to a named motion or charge; stores the press direction as its class's representative (1HK becomes
  `2HK`), unless an exception applies.
- **`describe`**: writes canonical notation using the classes (`2HK`, `236P`, `[4]6P`, `623HP`).
- **Grader**: `satisfied_at` asks the press matcher (direction classes, button classes, multi-press,
  negative edge) and the motion or charge recogniser (patterns, time limits), and applies the buffer
  to early presses.
- **`demo_track`**: plays each move's cleanest input (the pattern's main form, the class's
  representative), so demos stay clean.

### Explanations

Every match returns why it matched or didn't: `Match(ok=True, rule="crouching-normals", detail="1HK
counted as 2HK")`. The verdict popup's tooltip and the attempt rows show it, and a MISS says what
almost happened ("MP and MK 4 frames apart; allowed: 2"). This is how a rule's effect, or a missing
character exception, gets noticed.

### Recording file and hub

- The recording gains `character`, `scheme` and `rules` (the recording-level overrides), and each key
  input an optional `accept` block (key-input overrides, e.g. `{"directions": [3]}` for "only 3HK").
  Recordings name the pack version they were made with, so they grade the same way later.
- The hub already has games, characters, control schemes and versions: rule packs can be hosted there
  (one per game, characters inside), downloaded by the app, and edited by moderators, with the pack's
  tests run on upload.

### UI

- **Settings > Input rules**: per game, the rules with switches and their parameters (frames as
  steppers), and presets: *Game rules* (the pack), *Strict* (today's behaviour), *Lenient* (wider
  windows, for learning).
- **Edit > Game actions...** gains **Character** and **Control scheme**, which pick the layers.
- **Key input editor**: "Accepts: 1HK 2HK 3HK" as chips that can be switched off one by one; the motion
  shown with its accepted forms; "any strength" for B2. Changes there are key-input overrides.
  As built: an *Accepts* line and a dialog with the directions as a numpad, the simultaneous-press
  window, the buffer, the motion's time limit, the charge and strict; "any strength" isn't built.
- As built, **Edit > Input rules...** (rather than Settings) shows the recording's rules layer by
  layer with where each came from, and edits them in a chosen scope: this recording, all recordings
  of the game, or all of the character's.
- **Grades**: the explanation on hover, as above.

### Testing

- Each pack has **golden cases**: a few frames of input and the expected interpretation and grade
  ("6,3,2,3,3+HP is 623HP"; "for Ryu, 6+HP is not 5HP"). The app's tests run every pack's cases, and
  the hub runs a pack's cases before accepting a change.
- Property tests for the engine: with every rule off, results equal today's literal behaviour.

## Plan

1. **Engine with today's behaviour**: `InputRules`, the press matcher and the motion recogniser, with
   the *Strict* preset reproducing today's results (all current tests pass unchanged).
2. **Rules that need no game knowledge to be right**: A5 (neutral is neutral, a bug fix), B1
   (multi-press window, fixing `derive`'s first-frame-only buttons), C1/C4 (named motions and
   shortcuts), C5 (time limits), explanations.
3. **SF6 pack** with its character files (command normals, charges), Classic and Modern; character and
   scheme pickers; the key input editor's chips.
4. **Packs for the other hub games**, starting with T8 (mostly exact: little to add) and GGST.
5. **Hub-hosted packs**, side-switch markers (D3), and B5/B6 where games use them.
6. **Calibration mode** for measuring frame values with the virtual controller.

## Decisions

- **Defaults**: the game's rules, with *Strict* (today's behaviour) available per recording and per
  game.
- **Frame values** (the timing numbers in rules: simultaneous-press windows, motion time limits and
  step gaps, charge times and how long charge lasts after release, dash windows, tap-vs-hold
  thresholds, input buffers, just-frame timing, mash counts) come from, in order of preference:
  1. the developers' own documentation and patch notes;
  2. community frame-data resources (SuperCombo, Dustloop and similar);
  3. measuring them with the app: a calibration mode uses the virtual controller to send a move with
     a 1, 2, 3... frame gap while the user watches in training mode and marks which attempts came
     out, which finds the real window for their game version.

  Every value in a pack records its source and the game version it applies to. A value nobody has
  confirmed yet uses a cautious default and is marked **unverified**, and grade explanations say so
  ("allowed: 2 frames (unverified)"), so a doubtful grade can be traced to the number behind it.

## Open questions

- Should the interpreter rename moves ("Collarbone Breaker") once character files list them? Cheap
  once character files exist, but a lot of data.
