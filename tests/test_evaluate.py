"""Evaluation-harness tests (milestone 7, doc 03 sec 4).

The metric that matters is average placement, so these tests check the harness
reports it honestly -- including that a competent scripted policy reaches
parity with the bots it plays against. That last test is the real guard: if the
action space or environment ever starts handicapping the agent seat, it fails.
"""

from __future__ import annotations

import random

import pytest

from engine.loader import load_all
from engine.schema import GameData
from rl.env import TFTEnv
from rl.evaluate import (
    EvalResult,
    compare,
    end_planning_policy,
    evaluate,
    random_policy,
    scripted_policy,
)
from tests.paths import STARTER_DATA_DIR


@pytest.fixture(scope="module")
def data() -> GameData:
    return load_all(STARTER_DATA_DIR)


@pytest.fixture
def env(data) -> TFTEnv:
    return TFTEnv(data=data)


# --- result aggregation --------------------------------------------------


def test_metrics_are_computed_from_placements():
    result = EvalResult(episodes=8, placements=[1, 1, 3, 4, 5, 6, 8, 8])
    assert result.avg_placement == pytest.approx(4.5)
    assert result.win_rate == pytest.approx(0.25)
    assert result.top4_rate == pytest.approx(0.5)
    assert result.distribution == {1: 2, 3: 1, 4: 1, 5: 1, 6: 1, 8: 2}


def test_empty_results_do_not_divide_by_zero():
    result = EvalResult(episodes=0)
    assert result.avg_placement == 0.0
    assert result.win_rate == 0.0
    assert result.top4_rate == 0.0


def test_summary_and_dict_are_serialisable():
    result = EvalResult(episodes=2, placements=[1, 8], rewards=[1.0, 0.125])
    assert "avg_placement" in result.summary()
    payload = result.as_dict()
    assert payload["avg_placement"] == 4.5
    assert payload["distribution"] == {1: 1, 8: 1}


# --- running evaluations -------------------------------------------------


def test_evaluate_plays_the_requested_episodes(env):
    result = evaluate(env, end_planning_policy(env), seeds=range(3))
    assert result.episodes == 3
    assert len(result.placements) == 3
    assert all(1 <= p <= 8 for p in result.placements)


def test_evaluation_is_reproducible_on_fixed_seeds(env):
    policy = end_planning_policy(env)
    first = evaluate(env, policy, seeds=range(4))
    second = evaluate(env, policy, seeds=range(4))
    assert first.placements == second.placements
    assert first.rewards == second.rewards


def test_compare_uses_identical_seeds_for_every_policy(env):
    rng = random.Random(0)
    results = compare(
        env,
        {"nothing": end_planning_policy(env), "random": random_policy(rng)},
        episodes=3,
    )
    assert set(results) == {"nothing", "random"}
    assert all(r.episodes == 3 for r in results.values())


def test_a_runaway_episode_is_caught(env):
    with pytest.raises(RuntimeError, match="exceeded"):
        evaluate(env, end_planning_policy(env), seeds=[0], max_steps=3)


# --- baselines -----------------------------------------------------------


def test_doing_nothing_places_last(env):
    """The floor: an agent that never acts loses every game."""
    result = evaluate(env, end_planning_policy(env), seeds=range(5))
    assert result.avg_placement == 8.0
    assert result.win_rate == 0.0


def test_random_legal_actions_are_no_better_than_doing_nothing(env):
    """Documents why terminal-only reward gives PPO no gradient to start from."""
    rng = random.Random(0)
    result = evaluate(env, random_policy(rng), seeds=range(5))
    assert result.avg_placement > 6.0


def test_baseline_policies_never_take_an_illegal_action(env):
    rng = random.Random(1)
    for policy in (end_planning_policy(env), random_policy(rng), scripted_policy(env)):
        result = evaluate(env, policy, seeds=range(3))
        assert result.illegal_actions == 0


# --- the ceiling check ---------------------------------------------------


@pytest.mark.slow
def test_a_scripted_policy_reaches_parity_with_the_bots(env):
    """The environment must not handicap the agent seat.

    A heuristic driving the action space should place about average (4.5)
    against seven copies of the same heuristic. Materially worse means the
    action space cannot express competent play, and no learned policy could
    do better either.
    """
    result = evaluate(env, scripted_policy(env), seeds=range(30))
    assert result.avg_placement < 5.5, (
        f"scripted play only reached {result.avg_placement:.2f}; "
        "the action space or env is handicapping the agent seat"
    )
    assert result.win_rate > 0.10


def test_the_scripted_policy_actually_builds_a_board(env):
    """Regression: it used to place every unit on one hex, swapping endlessly,
    so the board never grew past a single unit."""
    policy = scripted_policy(env)
    obs, _ = env.reset(seed=0)
    peak_board = 0
    terminated = False
    steps = 0
    while not terminated and steps < 400:
        obs, _, terminated, _, _ = env.step(policy(obs, env.action_mask()))
        peak_board = max(peak_board, len(env.player.board))
        steps += 1
    assert peak_board >= 4, f"scripted play only ever fielded {peak_board} units"


def test_the_scripted_policy_beats_random(env):
    scripted = evaluate(env, scripted_policy(env), seeds=range(10))
    baseline = evaluate(env, random_policy(random.Random(0)), seeds=range(10))
    assert scripted.avg_placement < baseline.avg_placement
