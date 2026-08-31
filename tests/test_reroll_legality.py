"""The reroll mask must ask the engine, not restate its rule (doc 99 160.86).

CLAUDE.md: if the action mask and the executor disagree, the mask is the bug.
Free rerolls are the case that separates them -- a seat with no gold and a
trait-granted reroll is legal to the engine and was illegal to the mask.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loader import load_all  # noqa: E402
from engine.player import IllegalAction  # noqa: E402
from rl.action import ActionKind  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from tests.paths import REAL_DATA_DIR  # noqa: E402


@pytest.fixture(scope="module")
def data():
    return load_all(REAL_DATA_DIR)


@pytest.mark.parametrize(
    "gold, free, legal",
    [(10, 0, True), (0, 0, False), (0, 1, True), (0, 3, True), (1, 1, True)],
)
def test_mask_and_engine_agree_on_reroll(data, gold, free, legal):
    env = TFTEnv(data, max_actions_per_round=600)
    env.reset(seed=0)
    env.player.gold = gold
    env.player.free_rerolls = free
    space = env.action_space_helper

    assert env.player.can_reroll() is legal
    assert bool(env.action_masks()[space.reroll_index]) is legal

    action = space.encode_kind(ActionKind.REROLL) if hasattr(
        space, "encode_kind") else space.reroll_index
    if legal:
        env.step(action)
    else:
        with pytest.raises(IllegalAction):
            env.executor.apply(
                env.player, action, env.match.pool, env.match.rng
            )


def test_a_free_reroll_is_spent_before_gold(data):
    env = TFTEnv(data, max_actions_per_round=600)
    env.reset(seed=0)
    env.player.gold = 7
    env.player.free_rerolls = 2
    space = env.action_space_helper

    env.step(space.reroll_index)
    assert (env.player.gold, env.player.free_rerolls) == (7, 1)
    env.step(space.reroll_index)
    assert (env.player.gold, env.player.free_rerolls) == (7, 0)
    env.step(space.reroll_index)
    assert (env.player.gold, env.player.free_rerolls) == (5, 0)
