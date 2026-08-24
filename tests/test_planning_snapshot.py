"""Forkable planning state must reproduce a real legal reroll (doc 99 160.64)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loader import load_all  # noqa: E402
from rl.action import ActionKind  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import greedy_action_policy  # noqa: E402
from rl.opponents import FAST8  # noqa: E402
from rl.planning_snapshot import PlanningSnapshot  # noqa: E402
from tests.paths import REAL_DATA_DIR  # noqa: E402


def test_planning_snapshot_round_trips_a_real_reroll_state():
    data = load_all(REAL_DATA_DIR)
    env = TFTEnv(data, scouting="tokens", max_actions_per_round=600)
    policy = greedy_action_policy(env, econ=FAST8)
    observation, _ = env.reset(seed=0)

    for _step in range(6000):
        action = int(policy(observation, env.action_masks()))
        if env.action_space_helper.decode(action).kind is ActionKind.REROLL:
            break
        observation, _reward, terminated, truncated, _info = env.step(action)
        assert not terminated and not truncated
    else:
        raise AssertionError("seed 0 produced no reroll state")

    assert env.match is not None
    captured = PlanningSnapshot.capture(env.player, env.match.pool, env.match.rng)
    left, left_pool, left_rng = captured.restore(data, env.registry)
    right, right_pool, right_rng = captured.restore(data, env.registry)

    assert PlanningSnapshot.capture(left, left_pool, left_rng) == captured
    assert np.array_equal(env.executor.legal_mask(left), env.executor.legal_mask(right))
    left_mask = env.executor.legal_mask(left)
    right_mask = env.executor.legal_mask(right)
    assert left_mask[env.action_space_helper.reroll_index]
    assert right_mask[env.action_space_helper.reroll_index]

    left.reroll(left_pool, left_rng)
    right.reroll(right_pool, right_rng)
    assert PlanningSnapshot.capture(left, left_pool, left_rng) == PlanningSnapshot.capture(
        right, right_pool, right_rng
    )

    env.player.reroll(env.match.pool, env.match.rng)
    assert PlanningSnapshot.capture(env.player, env.match.pool, env.match.rng) == PlanningSnapshot.capture(
        left, left_pool, left_rng
    )
