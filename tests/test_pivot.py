"""The reroll pivot, and the consumers `test_econ_fields` cannot reach.

Doc 99 entry 111.4: 23.6% of `slowroll6` seats never hit their cost-2 3-star
and place 6.799, about two thirds of the archetype's whole deficit, because the
plan has no clause for not hitting. `pivot_at` adds one.

`test_econ_fields` guards that an `EconStrategy` field reaches the teacher *at
all*. Its docstring records the limitation, and a mutation test confirmed it
again here: deleting the pivot from the teacher's **roll floor** and **level
curve** leaves every case in that file passing, because `reroll_targets` still
consults it and the action sequence still differs. Three consumers, one of
which keeps the guard green on its own.

So these pin the semantics exactly, and then the two uncovered consumers
behaviourally.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.economy import RoundId  # noqa: E402
from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import scripted_policy  # noqa: E402
from rl.opponents import HYPERROLL, SLOWROLL6, reroll_targets  # noqa: E402
from tests.paths import REAL_DATA_DIR  # noqa: E402

FLAGS = dict(sell_bench=True, buy_synergy=True, match_items=True, corner_carry=True)
PIVOTED = dataclasses.replace(SLOWROLL6, pivot_at="4-2")


@pytest.fixture(scope="module")
def data():
    return load_all(REAL_DATA_DIR)


class _FakeUnit:
    def __init__(self, cost: int, star: int):
        self.champion = type("C", (), {"cost": cost, "id": f"c{cost}"})()
        self.star_level = star


class _FakePlayer:
    """Bench and board are distinct here on purpose.

    `board_units` defaults to *empty* so that swapping `has_pivoted` to read it
    fails on an assertion rather than on `AttributeError`. A mutation caught by
    a missing attribute is caught for the wrong reason and would stop catching
    it the moment the fake grew the attribute for some other test.
    """

    def __init__(self, units, board=()):
        self.all_units = units
        self.board_units = list(board)


def test_pivot_is_off_before_its_round(data):
    """A plan mid-line has not abandoned it."""
    bricked = _FakePlayer([_FakeUnit(2, 1)])
    assert not PIVOTED.has_pivoted(bricked, RoundId(4, 1))
    assert PIVOTED.has_pivoted(bricked, RoundId(4, 2))


def test_pivot_needs_zero_hits_not_a_shortfall(data):
    """One 3-star is winning the line; only a total brick abandons.

    If this were keyed on `target_count` (three carries) instead, a seat with
    two of its three 3-stars would abandon at 4-2 -- which is not a slow roll
    that pivoted, it is a slow roll that was deleted.
    """
    one_hit = _FakePlayer([_FakeUnit(2, 3), _FakeUnit(2, 1)])
    assert not PIVOTED.has_pivoted(one_hit, RoundId(5, 1))
    assert PIVOTED.has_pivoted(_FakePlayer([_FakeUnit(2, 2)]), RoundId(5, 1))


def test_a_benched_three_star_counts_as_a_hit(data):
    """`all_units`, not `board_units`.

    A 3-star waiting on the bench for a board slot is a hit; reading the board
    alone would abandon a line that has already succeeded.
    """
    assert not PIVOTED.has_pivoted(
        _FakePlayer([_FakeUnit(2, 3)]), RoundId(5, 1))


def test_pivot_is_inert_by_default(data):
    """Every pre-111 number must reproduce."""
    bricked = _FakePlayer([_FakeUnit(2, 1)])
    assert not SLOWROLL6.has_pivoted(bricked, RoundId(6, 4))


def test_pivot_clears_the_reroll_targets(data):
    """An abandoned line buys on generic strength again."""
    bricked = _FakePlayer([_FakeUnit(2, 2), _FakeUnit(2, 2)])
    assert reroll_targets(bricked, PIVOTED, RoundId(4, 1)), (
        "before the pivot round the plan is still committed to its carries"
    )
    assert not reroll_targets(bricked, PIVOTED, RoundId(4, 2))


def test_pivot_replaces_the_level_curve(data):
    """The consumer `test_econ_fields` cannot see (mutation-confirmed).

    SLOWROLL6 holds level 6 from 3-2 until 5-1. A bricked seat that pivots at
    4-2 must follow the standard curve instead, which is 7 at 4-1 and 8 at 4-5.
    """
    bricked = _FakePlayer([_FakeUnit(2, 1)])
    assert SLOWROLL6.target_level(RoundId(4, 5)) == 6
    assert PIVOTED.level_target_after_pivot(bricked, RoundId(4, 5)) == 8
    # A seat that hit keeps the slow-roll curve.
    hit = _FakePlayer([_FakeUnit(2, 3)])
    assert PIVOTED.level_target_after_pivot(hit, RoundId(4, 5)) == 6


def test_a_pivoted_teacher_actually_out_levels_a_slow_roller(data):
    """End to end, through the teacher, which is the claim that matters.

    Pins the roll-floor and level consumers together: a pivoted seat banks and
    levels, so across a whole game it must reach a higher level than the plain
    slow roll on the same seed. Reads the outcome rather than the action
    sequence, so it cannot pass merely because *something* differed.
    """
    def final_level(econ) -> int:
        env = TFTEnv(data=data)
        policy = scripted_policy(env, econ=econ, **FLAGS)
        obs, _info = env.reset(seed=0)
        best = env.player.level
        for _ in range(5000):
            action = int(policy(obs, env.action_masks()))
            obs, _r, term, trunc, _i = env.step(action)
            best = max(best, env.player.level)
            if term or trunc:
                break
        return best

    plain = final_level(SLOWROLL6)
    pivoted = final_level(PIVOTED)
    assert pivoted > plain, (
        f"pivoted seat reached level {pivoted}, plain slow roll {plain} -- the "
        "pivot's level curve is not reaching the teacher"
    )


# --- commit_level: hold the rolling level until the line hits (entry 119) ---

COMMITTED = dataclasses.replace(HYPERROLL, commit_level=5)


def test_commit_level_caps_the_curve_until_the_line_hits(data):
    """HYPERROLL's curve reaches 6 at 3-2 and 7 at 4-1; the cap holds it at 5.

    This is the regime that distinguishes 119 from entry 73's failed version:
    73 held the level on a *schedule* and never transitioned, reaching level
    6.78 and placing 5.648. The cap releases the moment the seat hits.
    """
    missed = _FakePlayer([_FakeUnit(1, 2)])
    assert HYPERROLL.target_level(RoundId(4, 1)) == 7
    assert COMMITTED.level_target_after_pivot(missed, RoundId(4, 1)) == 5


def test_commit_level_releases_on_completion_not_first_hit(data):
    """Roll low, complete the line, *then* level.

    The threshold is `target_count`, not one, and that is the whole finding of
    doc 99 entry 119.3: releasing on the first 3-star levels the seat out of its
    own shop odds with two carries still at 2-star, and produced **fewer**
    3-stars per seat (1.100) than never releasing (1.248). `has_hit` -- the
    pivot's question, "did anything land?" -- is deliberately a different
    predicate from `line_complete`.
    """
    one = _FakePlayer([_FakeUnit(1, 3)])
    assert COMMITTED.target_count == 3
    assert COMMITTED.level_target_after_pivot(one, RoundId(4, 1)) == 5, (
        "one 3-star of three must NOT release the cap"
    )
    done = _FakePlayer([_FakeUnit(1, 3), _FakeUnit(1, 3), _FakeUnit(1, 3)])
    assert COMMITTED.level_target_after_pivot(done, RoundId(4, 1)) == 7
    assert COMMITTED.level_target_after_pivot(done, RoundId(5, 5)) == 9


def test_commit_level_never_lowers_an_already_higher_curve(data):
    """A cap, not a target: `min(curve, cap)` so it can only hold back."""
    missed = _FakePlayer([_FakeUnit(1, 1)])
    early = dataclasses.replace(HYPERROLL, commit_level=9)
    assert early.level_target_after_pivot(missed, RoundId(2, 1)) == 4


def test_commit_level_is_inert_by_default(data):
    """Every pre-119 field number must reproduce."""
    missed = _FakePlayer([_FakeUnit(1, 1)])
    assert (HYPERROLL.level_target_after_pivot(missed, RoundId(4, 1))
            == HYPERROLL.target_level(RoundId(4, 1)))


def test_pivot_outranks_commit(data):
    """A bricked line abandons; it does not sit at `commit_level` forever.

    Both clauses read "has not hit", so their order is the whole behaviour: a
    seat past its pivot round must follow STANDARD's curve, not the cap.
    """
    both = dataclasses.replace(HYPERROLL, commit_level=5, pivot_at="4-2")
    missed = _FakePlayer([_FakeUnit(1, 1)])
    assert both.level_target_after_pivot(missed, RoundId(4, 1)) == 5
    assert both.level_target_after_pivot(missed, RoundId(4, 5)) == 8
