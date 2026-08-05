"""Reward shaping (doc 99 entry 6c.3).

The earlier ``"bonus"`` shaping paid the agent every round for holding a strong
board. Measured over a 150k-step run, that let episode reward rise 22% while
average placement stayed flat -- 77% of the gain came from shaping rather than
from placing better. It was optimising the proxy, not the objective.

``"potential"`` shaping uses ``F = gamma * phi(s') - phi(s)`` (Ng, Harada &
Russell 1999). The per-round terms telescope, so total shaping over an episode
collapses to a boundary term and cannot change which policy is optimal. These
tests pin that property, because it is the entire justification for the change.
"""

from __future__ import annotations

import numpy as np
import pytest

from engine.loader import load_all
from rl.env import SHAPING_MODES, TFTEnv
from rl.evaluate import scripted_policy
from tests.paths import STARTER_DATA_DIR


@pytest.fixture(scope="module")
def data():
    return load_all(STARTER_DATA_DIR)


def rollout(env, seed, limit=4000):
    """Play to termination taking the first legal action; return the pieces."""
    env.reset(seed=seed)
    shaped_total = 0.0
    terminal = 0.0
    steps = 0
    while steps < limit:
        mask = env.action_mask()
        legal = np.flatnonzero(mask)
        if legal.size == 0:
            break
        _, reward, terminated, _, _ = env.step(int(legal[0]))
        shaped_total += reward
        steps += 1
        if terminated:
            terminal = env._terminal_reward()
            break
    return shaped_total, terminal, steps


def test_shaping_mode_is_validated(data):
    with pytest.raises(ValueError, match="shaping_mode"):
        TFTEnv(data=data, shaping_mode="magic")


@pytest.mark.parametrize("mode", SHAPING_MODES)
def test_both_modes_run_to_termination(data, mode):
    env = TFTEnv(data=data, reward_shaping=True, shaping_mode=mode)
    _, _, steps = rollout(env, seed=3)
    assert steps > 0


def shaping_total(env, seed):
    """Sum only the shaping component of an episode's reward."""
    env.reset(seed=seed)
    shaped = 0.0
    steps = 0
    while steps < 4000:
        mask = env.action_mask()
        legal = np.flatnonzero(mask)
        if legal.size == 0:
            break
        _, reward, terminated, _, _ = env.step(int(legal[0]))
        steps += 1
        # Strip the terminal component so only shaping is summed.
        shaped += reward - (env._terminal_reward() if terminated else 0.0)
        if terminated:
            break
    return shaped, steps


def max_potential(env):
    """The largest value phi can take: capped board term plus full HP."""
    return env.board_reward_weight * 1.5 + env.survival_reward_weight


def test_potential_shaping_cannot_be_farmed(data):
    """The property that makes it policy-invariant.

    The per-round terms telescope to a boundary term, so total shaping stays
    bounded by the potential's own range no matter how long the episode runs.
    An agent therefore cannot accumulate reward simply by surviving -- which
    is exactly how the bonus form was exploited.

    (The bound is not exactly -phi_0 because gamma < 1 leaves a residual
    ``(gamma - 1) * sum(phi)`` term; it is still bounded, which is the point.)
    """
    env = TFTEnv(data=data, reward_shaping=True, shaping_mode="potential")
    limit = max_potential(env) * 2
    for seed in (0, 1, 2, 5):
        shaped, _ = shaping_total(env, seed)
        assert abs(shaped) < limit, f"seed {seed}: shaping accumulated to {shaped}"


def test_potential_shaping_does_not_grow_with_episode_length(data):
    """Directly contrasts a short episode against a long one."""
    env = TFTEnv(data=data, reward_shaping=True, shaping_mode="potential")
    results = [shaping_total(env, seed) for seed in (0, 1, 2, 5, 7)]
    shortest = min(results, key=lambda r: r[1])
    longest = max(results, key=lambda r: r[1])
    if longest[1] > shortest[1]:
        assert abs(longest[0]) < max_potential(env) * 2
        assert abs(longest[0] - shortest[0]) < max_potential(env)


def test_bonus_shaping_accumulates_and_rivals_the_terminal_reward(data):
    """Contrast, and the measured reason the default changed.

    The old form pays every round, so it grows with episode length until it is
    comparable to the entire terminal reward -- at which point the agent is
    being graded mostly on the proxy.
    """
    env = TFTEnv(data=data, reward_shaping=True, shaping_mode="bonus")
    shaped, _ = shaping_total(env, seed=0)
    assert shaped > max_potential(env) * 2, "bonus shaping should accumulate"


def test_potential_falls_when_the_board_is_emptied(data):
    """Losing board strength must be penalised, not merely un-rewarded."""
    env = TFTEnv(data=data, reward_shaping=True, shaping_mode="potential")
    obs, _ = env.reset(seed=0)
    # Driven by the scripted policy rather than by the lowest legal action.
    # Taking `legal[0]` never fielded a unit, so this test skipped on every run
    # and asserted nothing at all -- the one claim it exists to pin, that
    # losing board strength is penalised, was unchecked. An empty board is now
    # a failure rather than a skip, because a test that cannot build its own
    # precondition is not coverage.
    policy = scripted_policy(env)
    for _ in range(200):
        mask = env.action_mask()
        if not mask.any():
            break
        obs, _, terminated, _, _ = env.step(int(policy(obs, mask)))
        if env.player.board or terminated:
            break
    assert env.player.board, "scripted policy fielded no unit; cannot test potential"
    before = env._potential()
    for hex_ in list(env.player.board):
        env.player.move_to_bench(hex_)
    assert env._potential() < before


def test_shaping_is_off_by_default(data):
    """Doc 03 sec 3.3: start without shaping; it is easy to get subtly wrong."""
    env = TFTEnv(data=data)
    assert env.reward_shaping is False
    env.reset(seed=0)
    mask = env.action_mask()
    _, reward, terminated, _, _ = env.step(int(np.flatnonzero(mask)[0]))
    if not terminated:
        assert reward == 0.0
