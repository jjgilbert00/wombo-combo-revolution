"""Golden cases for the SF6 rule pack (rule_packs/sf6.json): what the game counts as the same input,
character by character. The facts come from SuperCombo's SF6 Data pages (patch 2.05)."""
import unittest

from helpers import key_input, track

from games import GAMES
from input_rules import resolve
from key_inputs import HIT, MISS, derive, describe, explain, result

# Classic controls on an Xbox pad, as recorded: X=LP Y=MP RB=HP A=LK B=MK RT=HK.
LAYOUT = GAMES["sf6"]["default_layout"]
BUTTON = {action: button for button, action in LAYOUT.items()}


def sf6(character=None):
    return resolve("sf6", character=character, layout=LAYOUT)


def press(direction, action, before=5, after=5):
    """A press of an SF6 action (by name) with a direction, held 2 frames, with neutral around it."""
    return track((before, 5), (2, direction, BUTTON[action]), (after, 5))


class Normals(unittest.TestCase):
    def test_any_down_direction_is_the_sweep_for_ken(self):
        rules = sf6("ken")
        k = derive(press(1, "HK"), 0, 11, rules)
        self.assertEqual(describe(k), "2" + BUTTON["HK"])  # Written as the crouching normal.
        for direction in (1, 2, 3):
            self.assertEqual(result(k, press(direction, "HK"), press(2, "HK"), rules), HIT, direction)
        self.assertIn("counted as", explain(k, press(3, "HK"), press(2, "HK"), rules, names=LAYOUT))

    def test_chun_lis_3hk_is_her_own_move(self):
        rules = sf6("chun-li")
        sweep = derive(press(2, "HK"), 0, 11, rules)
        self.assertEqual(result(sweep, press(1, "HK"), press(2, "HK"), rules), HIT)
        self.assertEqual(result(sweep, press(3, "HK"), press(2, "HK"), rules), MISS)
        own = derive(press(3, "HK"), 0, 11, rules)
        self.assertEqual(own["direction"], 3)
        self.assertEqual(result(own, press(2, "HK"), press(3, "HK"), rules), MISS)
        self.assertIn("needs direction 3", explain(own, press(2, "HK"), press(3, "HK"), rules, names=LAYOUT))

    def test_ryus_6mp_isnt_his_standing_mp(self):
        rules = sf6("ryu")
        standing = derive(press(5, "MP"), 0, 11, rules)
        self.assertEqual(result(standing, press(4, "MP"), press(5, "MP"), rules), HIT)  # Back + MP is 5MP.
        self.assertEqual(result(standing, press(6, "MP"), press(5, "MP"), rules), MISS)  # Collarbone Breaker.
        ken = sf6("ken")
        self.assertEqual(result(derive(press(5, "MP"), 0, 11, ken), press(6, "MP"), press(5, "MP"), ken), HIT)

    def test_without_a_character_nothing_that_could_be_a_command_normal_counts(self):
        rules = sf6()
        self.assertEqual(rules.press_directions(5, [BUTTON["MP"]])[0], {5})  # Someone has 4MP and 6MP.
        self.assertEqual(rules.press_directions(5, [BUTTON["LP"]])[0], {4, 5, 6})  # Nobody has 4LP or 6LP.
        self.assertEqual(rules.press_directions(2, [BUTTON["HK"]])[0], {2})  # Someone has 1HK; others 3HK.
        self.assertEqual(rules.press_directions(2, [BUTTON["LP"]])[0], {1, 2, 3})

    def test_the_input_buffer_is_4_frames(self):
        rules = sf6("ken")
        k = key_input(10, 12, buttons=[BUTTON["LP"]])
        for early, expected in ((4, HIT), (5, MISS)):
            attempt = track((10 - early, 5), (2, 5, BUTTON["LP"]), (10, 5))
            self.assertEqual(result(k, attempt, attempt, rules), expected, early)


class Motions(unittest.TestCase):
    def test_a_dp_through_down_forward_is_a_dp(self):
        rules = sf6("ken")
        target = track((3, 5), (1, 6), (1, 3), (1, 2), (1, 3), (2, 3, BUTTON["HP"]), (3, 5))
        k = derive(target, 0, 11, rules)
        self.assertEqual(describe(k), "623" + BUTTON["HP"])

    def test_motions_a_character_doesnt_have_arent_read_into_its_inputs(self):
        # Guile has no 236: a walk forward, then down, down-forward, forward + punch stays as recorded
        # for him; for Ryu it's a fireball, and the walk isn't part of it.
        inputs = track((3, 5), (2, 6), (1, 2), (1, 3), (2, 6, BUTTON["LP"]), (3, 5))
        self.assertEqual(derive(inputs, 0, 11, sf6("guile"))["motion"], [6, 2, 3, 6])
        self.assertEqual(describe(derive(inputs, 0, 11, sf6("ryu"))), "236" + BUTTON["LP"])

    def test_a_360_either_way_round(self):
        rules = sf6("zangief")
        clockwise = track((2, 5), (1, 6), (1, 2), (1, 4), (1, 8), (2, 5, BUTTON["LP"]), (2, 5))
        k = derive(clockwise, 0, 9, rules)
        self.assertEqual(describe(k), "360+" + BUTTON["LP"])
        other_way = track((2, 5), (1, 4), (1, 2), (1, 6), (1, 9), (2, 5, BUTTON["LP"]), (2, 5))
        self.assertEqual(result(k, other_way, clockwise, rules), HIT)


class Charge(unittest.TestCase):
    """Guile's Sonic Boom: 45 frames of back, kept 10 frames after letting go; two buttons keep 13."""

    def sonic_boom(self, charge, gap=0, buttons=("LP",)):
        return track((2, 5), (charge, 4), *([(gap, 5)] if gap else []), (2, 6, *(BUTTON[b] for b in buttons)), (4, 5))

    def test_recorded_as_a_charge_and_written_so(self):
        rules = sf6("guile")
        k = derive(self.sonic_boom(50), 40, 57, rules)
        self.assertTrue(k.get("charge"))
        self.assertEqual(describe(k), "[4]6" + BUTTON["LP"])

    def test_45_frames_of_back_are_needed(self):
        rules = sf6("guile")
        k = derive(self.sonic_boom(50), 40, 57, rules)
        target = self.sonic_boom(50)
        self.assertEqual(result(dict(k, start=40, end=len(self.sonic_boom(45)) - 1), self.sonic_boom(45), target, rules), HIT)
        short = self.sonic_boom(44)
        k44 = dict(k, start=30, end=len(short) - 1)
        self.assertEqual(result(k44, short, target, rules), MISS)
        self.assertIn("Not enough charge", explain(k44, short, target, rules, names=LAYOUT))

    def test_charge_lasts_10_frames_after_letting_go_or_13_with_two_buttons(self):
        rules = sf6("guile")
        k = dict(derive(self.sonic_boom(50), 40, 57, rules), start=40)
        for gap, expected in ((9, HIT), (11, MISS)):
            attempt = self.sonic_boom(50, gap)
            self.assertEqual(result(dict(k, end=len(attempt) - 1), attempt, attempt, rules), expected, gap)
        od = dict(k, buttons=[BUTTON["LP"], BUTTON["MP"]])
        attempt = self.sonic_boom(50, 12, ("LP", "MP"))
        self.assertEqual(result(dict(od, end=len(attempt) - 1), attempt, attempt, rules), HIT)

    def test_down_back_charges_both_ways(self):
        rules = sf6("guile")
        k = dict(derive(self.sonic_boom(50), 40, 57, rules), start=40)
        attempt = track((2, 5), (50, 1), (2, 6, BUTTON["LP"]), (4, 5))
        self.assertEqual(result(dict(k, end=len(attempt) - 1), attempt, attempt, rules), HIT)

    def test_chun_li_needs_50_frames_but_45_for_od(self):
        rules = sf6("chun-li")
        k = dict(derive(self.sonic_boom(55), 45, 62, rules), start=40)
        attempt = self.sonic_boom(47)
        self.assertEqual(result(dict(k, end=len(attempt) - 1), attempt, attempt, rules), MISS)
        od = dict(k, buttons=[BUTTON["LP"], BUTTON["MP"]])
        attempt = self.sonic_boom(47, buttons=("LP", "MP"))
        self.assertEqual(result(dict(od, end=len(attempt) - 1), attempt, attempt, rules), HIT)


class Pack(unittest.TestCase):
    def test_the_roster(self):
        from input_rules import pack_characters

        names = pack_characters("sf6")
        self.assertEqual(len(names), 32)
        self.assertIn("ryu", names)
        self.assertEqual(names["m-bison"], "M. Bison")

    def test_undocumented_values_are_marked_unverified(self):
        rules = sf6("ken")
        self.assertIn("simultaneous", rules.unverified)
        self.assertNotIn("buffer", rules.unverified)  # The 4-frame buffer is documented.


if __name__ == "__main__":
    unittest.main()
