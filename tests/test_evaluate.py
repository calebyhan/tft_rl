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
    LP_BY_PLACEMENT,
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


# --- floor-effect guardrail (doc 99 entry 18.3/18.4) --------------------


def _result(placements):
    from rl.evaluate import EvalResult

    return EvalResult(episodes=len(placements), placements=list(placements))


def test_floor_rate_counts_last_place():
    assert _result([8] * 84 + [4, 5, 6, 7] * 4).floor_rate == pytest.approx(0.84)


def test_a_pinned_policy_is_flagged_as_on_the_floor():
    """The 150-episode warm start that wasted four experiments."""
    result = _result([8] * 84 + [4] * 3 + [5] * 4 + [6] * 2 + [7] * 7)
    assert result.on_the_floor
    assert "FLOOR EFFECT" in result.summary()


def test_a_spread_policy_is_not_flagged():
    """The 400-episode warm start: 33% last place, usable."""
    spread = [1] * 2 + [2] * 1 + [3] * 8 + [4] * 7 + [5] * 12 + [6] * 14 + [7] * 23 + [8] * 33
    result = _result(spread)
    assert not result.on_the_floor
    assert "FLOOR EFFECT" not in result.summary()


def test_scripted_baseline_is_not_flagged():
    """A competent policy still finishes last sometimes; that is not a floor."""
    scripted = (
        [1] * 10 + [2] * 13 + [3] * 11 + [4] * 10
        + [5] * 13 + [6] * 11 + [7] * 10 + [8] * 22
    )
    assert not _result(scripted).on_the_floor


def test_ci95_shrinks_with_more_episodes():
    tight = _result([4, 5] * 200)
    loose = _result([4, 5] * 5)
    assert tight.ci95 < loose.ci95


def test_ci95_is_zero_for_a_constant_result():
    assert _result([8] * 50).ci95 == pytest.approx(0.0)


def test_ci95_undefined_for_a_single_episode():
    assert _result([3]).ci95 == 0.0


def test_floor_rate_of_an_empty_result_is_zero():
    assert _result([]).floor_rate == 0.0


def test_as_dict_carries_the_diagnostics():
    d = _result([8] * 10).as_dict()
    assert "ci95" in d and "floor_rate" in d


# --- LP scoring (doc 99 entry 31/32) -------------------------------------
#
# Average placement is linear; ranked TFT is not. These pin the properties that
# make LP a *different* metric rather than a rescaling of the same one -- if it
# were monotone-equivalent to placement it would add nothing and every past
# verdict would carry over unchanged.


def _result(placements):
    return EvalResult(episodes=len(placements), placements=list(placements))


def test_lp_rewards_the_top_half_and_punishes_the_bottom():
    assert _result([1]).avg_lp > 0
    assert _result([4]).avg_lp > 0
    assert _result([5]).avg_lp < 0
    assert _result([8]).avg_lp < 0


def test_lp_is_convex_toward_first():
    """1st->2nd must be worth more than 3rd->4th; placement says they are equal."""
    first_to_second = LP_BY_PLACEMENT[1] - LP_BY_PLACEMENT[2]
    third_to_fourth = LP_BY_PLACEMENT[3] - LP_BY_PLACEMENT[4]
    assert first_to_second > third_to_fourth


def test_lp_can_disagree_with_average_placement():
    """The reason the metric exists.

    Two distributions with identical mean placement, one weighted to the tails.
    If LP ranked them the same, it would be a rescaling and doc 99 31.3's
    finding would be an artefact of arithmetic rather than a real ambiguity.
    """
    flat = _result([4, 4, 5, 5])
    tails = _result([1, 1, 8, 8])
    assert flat.avg_placement == pytest.approx(tails.avg_placement)
    assert flat.avg_lp != pytest.approx(tails.avg_lp)


def test_lp_ci_widens_with_spread():
    tight = _result([4, 4, 5, 5] * 10)
    wide = _result([1, 1, 8, 8] * 10)
    assert wide.lp_ci95 > tight.lp_ci95


def test_lp_is_zero_for_no_episodes():
    assert _result([]).avg_lp == 0.0
    assert _result([]).lp_ci95 == 0.0


def test_summary_reports_lp_alongside_placement():
    """Never instead of: the project's history is measured on placement."""
    text = _result([1, 2, 3, 4, 5, 6, 7, 8]).summary()
    assert "avg_placement=" in text
    assert "lp=" in text
