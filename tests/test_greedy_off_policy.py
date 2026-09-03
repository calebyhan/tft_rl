"""Driving the greedy scheduler on somebody else's actions (doc 99 entry 160.98)."""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest as _pytest  # noqa: E402

from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import greedy_action_policy  # noqa: E402
from rl.opponents import STRATEGIES  # noqa: E402
from tests.paths import REAL_DATA_DIR  # noqa: E402


@_pytest.fixture(scope="module")
def real_data():
    # The starter fixture's 13 champions cannot fill a shop deep enough for the
    # scheduler to reach its fielding stage, which is where the stranded plan
    # lives.
    return load_all(REAL_DATA_DIR)


def drive_on_foreign_stream(data, off_policy: bool, steps: int = 400) -> int:
    """Advance the world with random legal actions, querying greedy each step.

    This is the lockstep pattern every counterfactual harness in `scripts/`
    uses: the teacher watches a trajectory it did not choose. Returns the
    number of steps survived; raises whatever the scheduler raises.
    """
    env = TFTEnv(data=data)
    tenv = TFTEnv(data=data)
    teacher = greedy_action_policy(
        tenv, econ=STRATEGIES["fast8"], off_policy=off_policy)
    rng = random.Random(7)
    obs, _ = env.reset(seed=11)
    tobs, _ = tenv.reset(seed=11)
    for step in range(steps):
        teacher(tobs, tenv.action_masks())
        mask = env.action_masks()
        action = rng.choice([i for i, m in enumerate(mask) if m])
        obs, _r, term, trunc, _i = env.step(action)
        tobs, _tr, tterm, ttrunc, _ti = tenv.step(action)
        if term or trunc or tterm or ttrunc:
            return step
    return steps


def test_default_scheduler_refuses_a_foreign_stream(real_data):
    """The assertion is load-bearing on-policy and must stay the default."""
    with pytest.raises(AssertionError, match="emitted masked action"):
        drive_on_foreign_stream(real_data, off_policy=False)


def test_off_policy_scheduler_survives_a_foreign_stream(real_data):
    assert drive_on_foreign_stream(real_data, off_policy=True) > 100


def test_invalidate_plan_keeps_the_round_reroll_budget(real_data):
    """`_rolls` is a per-round budget, not plan state.

    Clearing it on every replan would let an off-policy teacher roll past
    `MAX_ROLLS_PER_ROUND`, which is a different policy, not a resynced one.
    """
    env = TFTEnv(data=real_data)
    policy = greedy_action_policy(env, econ=STRATEGIES["fast8"], off_policy=True)
    env.reset(seed=3)
    policy._rolls = 2
    policy._pending_place = 999
    policy._invalidate_plan()
    assert policy._rolls == 2
    assert policy._pending_place is None
