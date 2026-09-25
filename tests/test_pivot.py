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


@dataclasses.dataclass(frozen=True)
class _Step:
    round: str
    level: int
    gold_before: int
    rerolled: bool
    pivoted: bool


def _play(data, econ) -> list[_Step]:
    """One scripted-teacher game on seed 0, one record per action."""
    env = TFTEnv(data=data)
    policy = scripted_policy(env, econ=econ, **FLAGS)
    reroll = env.action_space_helper.reroll_index
    obs, _info = env.reset(seed=0)
    steps = []
    for _ in range(5000):
        now, gold = env.match.round_id, env.player.gold
        pivoted = econ.has_pivoted(env.player, now)
        action = int(policy(obs, env.action_masks()))
        obs, _r, term, trunc, _i = env.step(action)
        steps.append(_Step(str(now), env.player.level, gold, action == reroll, pivoted))
        if term or trunc:
            break
    return steps


def _first_pivot(steps: list[_Step]) -> str:
    """The round the seat abandoned its line.

    The case must actually occur: a seed whose seat hits its 3-star never
    pivots, and every comparison after it would pass or fail for nothing.
    """
    first = next((s.round for s in steps if s.pivoted), None)
    assert first is not None, "seed 0 no longer bricks; pick a seed that does"
    return first


def test_a_pivoted_teacher_stops_rolling_into_its_bank(data):
    """The roll-floor consumer, which the level test above cannot see.

    Not pinnable with `PIVOTED` as defined. SLOWROLL6's own roll floor is 50
    from 3-2 and `pivot_floor` defaults to 50, so deleting `pivot_floor` from
    the scripted teacher's roll branch is an *equivalent* mutant there: the
    floor stays at 50 either way (doc 99 entry 161.9). A bank above the plan's
    floor is the case that tells the consumer apart, so this uses one.

    Once pivoted, no reroll may take the seat below its bank. The plain slow
    roll on the same seed must roll below that line after the same round, or
    the bank never binds in this game and the check would hold for nothing.
    """
    banker = dataclasses.replace(PIVOTED, pivot_floor=80)
    steps = _play(data, banker)
    pivot_round = banker._key(_first_pivot(steps))
    cost = data.config.reroll_cost
    into_bank = [
        s for s in steps
        if s.pivoted and s.rerolled and s.gold_before - cost < banker.pivot_floor
    ]
    assert not into_bank, (
        f"pivoted seat rerolled below its {banker.pivot_floor}g bank at "
        f"{[(s.round, s.gold_before) for s in into_bank][:5]}"
    )
    plain_below = [
        s for s in _play(data, SLOWROLL6)
        if s.rerolled
        and banker._key(s.round) >= pivot_round
        and s.gold_before - cost < banker.pivot_floor
    ]
    assert plain_below, (
        "the plain slow roll never rolls below the pivot floor after the pivot "
        "round on seed 0, so this game cannot show the floor binding"
    )


def test_a_pivoted_teacher_actually_out_levels_a_slow_roller(data):
    """End to end, through the teacher, which is the claim that matters.

    A pivoted seat banks and levels, so on the same seed it must stand at a
    higher level than the plain slow roll. Reads the outcome rather than the
    action sequence, so it cannot pass merely because *something* differed.

    Compared round by round over the rounds both seats are alive, not as a
    whole-game maximum. The maximum mixes in survival: on seed 0 the pivoted
    seat was level 7 from 4-3 while the plain one held 6, then died at 5-2, one
    round before the plain seat's own curve reached 7 -- a tie at 7 that read as
    the pivot not levelling (doc 99 entry 161.9).
    """
    plain = {s.round: s.level for s in _play(data, SLOWROLL6)}
    steps = _play(data, PIVOTED)
    pivoted = {s.round: s.level for s in steps}
    pivoted_at = _first_pivot(steps)
    common = [r for r in pivoted if r in plain]
    ahead = [r for r in common if pivoted[r] > plain[r]]
    assert ahead, (
        f"pivot fired at {pivoted_at} but the pivoted seat never stood above "
        f"the plain slow roll at any shared round -- the pivot's level curve is "
        "not reaching the teacher"
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
