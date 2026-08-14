"""`roll_buys` gates what the roll loop's buy phase may spend on (entry 121.4).

The roll loop calls `_buy_phase(budget="all")` after every single roll, so
rolling competes with its own buying. Measured over 120 games, a hyperroll seat
rolling from 5-1 spends **50.0g on non-target units and 2.8g on target copies**
-- it outbids itself, 18 units to 2.8.

`roll_buys="targets"` narrows that one call site. These pin the behaviour where
it is actually observable: a whole game, counting what gets bought while the
roll loop is running. A unit test on `_buy_phase` alone would pass on an
implementation that never reaches it.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import player as player_mod  # noqa: E402
from engine.loader import load_all  # noqa: E402
from engine.match import Match  # noqa: E402
from rl.opponents import (  # noqa: E402
    DEFAULT_FIELD,
    HYPERROLL,
    GreedyPolicy,
    reroll_targets,
)
from tests.paths import REAL_DATA_DIR  # noqa: E402

# The arm entry 121 measured: roll the surplus from 5-1 rather than banking.
ROLLING = dataclasses.replace(
    HYPERROLL, roll_floors={"2-3": 0, "3-2": 50, "5-1": 0}
)


@pytest.fixture(scope="module")
def data():
    return load_all(REAL_DATA_DIR)


def buys_by_kind(data, roll_buys: str, games: int = 8) -> dict[str, int]:
    """Hyperroll seats' buys, split by target membership **and by phase**.

    The phase split is load-bearing, and a mutation test is why. `_econ_plan`
    runs buy, level, buy, then the roll loop, so a buy before that round's first
    reroll is board-building and a buy after it is the roll loop. Aggregating
    the two hides the regression that matters: flipping `_buy_phase`'s
    `targets_only` default to True silently filters the *board-building* phases
    -- leaving the seat unable to build a board at all -- while the roll loop,
    which passes the argument explicitly, carries on unchanged. All four cases
    here passed against that mutation until the counts were split.

    Keys are `{phase}_{kind}`: `build_other`, `roll_target`, and so on.
    """
    econs = [DEFAULT_FIELD[s % len(DEFAULT_FIELD)] for s in range(8)]
    hyper = [i for i, e in enumerate(econs) if e.name == "hyperroll"]
    econs = [ROLLING if i in hyper else e for i, e in enumerate(econs)]

    counts = {f"{phase}_{kind}": 0
              for phase in ("build", "roll") for kind in ("target", "other")}
    state: dict = {"rid": None, "rolled": set()}
    real_buy = player_mod.PlayerState.buy
    real_reroll = player_mod.PlayerState.reroll

    def counting_buy(self, slot, pool=None):
        if self.player_id in hyper:
            champion_id = self.shop.slots[slot]
            targets = reroll_targets(self, ROLLING, state["rid"])
            phase = "roll" if self.player_id in state["rolled"] else "build"
            kind = "target" if champion_id in targets else "other"
            counts[f"{phase}_{kind}"] += 1
        return real_buy(self, slot, pool)

    def marking_reroll(self, *a, **kw):
        state["rolled"].add(self.player_id)
        return real_reroll(self, *a, **kw)

    player_mod.PlayerState.buy = counting_buy
    player_mod.PlayerState.reroll = marking_reroll
    try:
        for game in range(games):
            policies = [
                GreedyPolicy(seed=seat, econ=econs[seat],
                             roll_buys=roll_buys if seat in hyper else "all")
                for seat in range(8)
            ]
            match = Match(data, policies, seed=game)
            while not match.finished:
                state["rid"] = match.round_id
                state["rolled"] = set()
                match.play_round()
    finally:
        player_mod.PlayerState.buy = real_buy
        player_mod.PlayerState.reroll = real_reroll
    return counts


def test_rolling_seat_buys_mostly_non_targets_by_default(data):
    """The defect 121.4 measured, pinned so a fix cannot silently regress.

    This is the *baseline*: it must keep buying non-targets, because that is
    the shipped behaviour every pre-121 number was measured against.
    """
    counts = buys_by_kind(data, "all")
    assert counts["roll_other"] > counts["roll_target"], (
        f"expected the default roll loop to buy mostly non-targets, got {counts}"
    )


def test_targets_only_stops_the_roll_loop_outbidding_itself(data):
    """Fewer non-target buys **in the roll loop only**.

    Both halves matter, and the second is the one a mutation defeated. Narrowing
    must bite inside the roll loop and leave board-building untouched: a
    `targets_only` that leaked into the other buy phases would look like a
    bigger success on the first assertion while leaving the seat with no board.
    """
    default = buys_by_kind(data, "all")
    narrowed = buys_by_kind(data, "targets")
    assert narrowed["roll_other"] < default["roll_other"], (
        f"targets-only bought as many non-targets in the roll loop as the "
        f"default: {narrowed} vs {default}"
    )
    assert narrowed["build_other"] > 0, (
        "targets-only stopped the board-building buy phases buying anything "
        f"off-plan -- it has leaked outside the roll loop: {narrowed}"
    )


def test_roll_buys_is_inert_by_default(data):
    """Every pre-121 number must reproduce."""
    assert GreedyPolicy(seed=0).roll_buys == "all"


def test_an_unknown_roll_buys_is_rejected(data):
    """A typo must not silently select the shipped default."""
    with pytest.raises(ValueError, match="roll_buys"):
        GreedyPolicy(seed=0, roll_buys="target")   # note: singular
