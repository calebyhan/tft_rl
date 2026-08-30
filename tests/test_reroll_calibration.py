"""The reroll calibration harness must be paired and reproducible (doc 99 160.67).

A calibration that silently leaked state between branches, or that resampled
its combat seeds, would report a difference that is not the decision's.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.search import best_buy_from_scores  # noqa: E402
from scripts.reroll_target_calibration import (  # noqa: E402
    _qualifies,
    _walk,
    calibrate_state,
    classify,
    find_reroll_state,
    run_branch,
    sample_reroll_state,
)
from tests.paths import REAL_DATA_DIR  # noqa: E402

ARGS = argparse.Namespace(
    trials=2, margin=0.25, max_candidates=5, replicas=4, shop_seed=1, combat_seed=7
)


@pytest.fixture(scope="module")
def reroll_state():
    data = load_all(REAL_DATA_DIR)
    found = find_reroll_state(data, 0, 2)
    if found is None:
        pytest.fail("seed 0 no longer reaches a baseline reroll with a legal END")
    snapshot, match, panel = found
    return data, TFTEnv(data).registry, snapshot, match, panel


def test_calibrate_state_is_reproducible(reroll_state):
    data, registry, snapshot, match, panel = reroll_state
    first = calibrate_state(data, registry, snapshot, match, panel, 0, ARGS)
    second = calibrate_state(data, registry, snapshot, match, panel, 0, ARGS)
    assert first == second


def test_reroll_branches_do_not_leak_into_the_baseline(reroll_state):
    """The END branch must read the same board after the reroll branches ran."""
    data, registry, snapshot, match, panel = reroll_state
    seeds = [[11, 12], [13, 14]][: len(panel)]

    def panel_signature():
        return [
            sorted(
                (hex_.q, hex_.r, unit.champion.id, unit.star_level)
                for hex_, unit in opponent.board.items()
            )
            for opponent in panel
        ]

    panel_before = panel_signature()
    player, pool, _rng = snapshot.restore(data, registry)
    before = run_branch(player, pool, match, panel, seeds, ARGS)

    for replica in range(3):
        rolled, rolled_pool, _ = snapshot.restore(data, registry)
        rolled.reroll(rolled_pool, random.Random(replica))
        run_branch(rolled, rolled_pool, match, panel, seeds, ARGS)

    player, pool, _rng = snapshot.restore(data, registry)
    assert run_branch(player, pool, match, panel, seeds, ARGS) == before
    assert panel_signature() == panel_before


def test_a_sampled_reroll_changes_the_shop_but_not_the_starting_board(reroll_state):
    data, registry, snapshot, match, panel = reroll_state
    baseline, _pool, _rng = snapshot.restore(data, registry)
    rolled, rolled_pool, _rng = snapshot.restore(data, registry)
    rolled.reroll(rolled_pool, random.Random(12345))

    assert rolled.gold == baseline.gold - baseline.config.reroll_cost
    assert sorted(rolled.board) == sorted(baseline.board)
    assert list(rolled.shop.slots) != list(baseline.shop.slots)


@pytest.mark.parametrize(
    "value, expected",
    # Panel of two at margin 0.25 demands a candidate beat the baseline by 0.5.
    [(1.49, None), (1.5, None), (1.51, 3)],
)
def test_buy_acceptance_rule_is_strict(value, expected):
    scored = (1.0, [(3, value, (), ())])
    assert best_buy_from_scores(scored, 0.25, 2) == expected


def test_no_candidates_means_no_buy():
    assert best_buy_from_scores((1.0, []), 0.25, 2) is None


def _state(mean: float, se: float, zero: float = 0.5, legal_buys: int = 0) -> dict:
    return {
        "margin_delta": {"mean": mean, "se": se, "p_zero": zero},
        "margin_per_gold": mean / 2.0,
        "free_bench_slots": 0,
        "end": {"bought_slot": None, "legal_buys": legal_buys},
    }


def test_outcome_a_requires_sharpness_and_disagreement_in_sign():
    """A one-sided result must not be reported as outcome A (doc 99 160.67).

    The first run of this study was sharp on the numeric test while every state
    preferred REROLL, which is a measurement, not a decision rule.
    """
    one_sided = classify([_state(0.1, 0.01), _state(0.9, 0.01)])
    assert one_sided["sharp"] and not one_sided["both_signs"]
    assert one_sided["outcome"].startswith("A-partial")

    two_sided = classify([_state(-0.4, 0.01), _state(0.9, 0.01)])
    assert two_sided["outcome"].startswith("A:")
    assert two_sided["states_with_negative_mean_delta"] == 1


def test_noisy_states_are_outcome_b_even_when_two_sided():
    noisy = classify([_state(-0.4, 0.9), _state(0.4, 0.9)])
    assert not noisy["sharp"]
    assert noisy["outcome"].startswith("B:")


def test_all_zero_deltas_are_outcome_c():
    degenerate = classify([_state(0.0, 0.0, zero=1.0), _state(0.02, 0.01, zero=0.99)])
    assert degenerate["outcome"].startswith("C:")


@pytest.fixture(scope="module")
def real_data():
    return load_all(REAL_DATA_DIR)


def test_legality_sampled_state_has_both_decisions_legal(real_data):
    """160.69's selection must offer a real choice, not just a reroll."""
    sampled = sample_reroll_state(real_data, 0, 2, random.Random(3))
    assert sampled is not None
    snapshot, match, panel, meta = sampled
    assert meta["qualifying_states"] > 0
    assert 0 <= meta["chosen"] < meta["qualifying_states"]
    assert panel and snapshot.board
    # Both branches must be affordable/legal from the restored state itself.
    player, pool, _rng = snapshot.restore(real_data, TFTEnv(real_data).registry)
    assert player.gold >= player.config.reroll_cost


def test_legality_sampling_is_seed_determined_and_not_always_the_same_state(real_data):
    """Reservoir sampling must depend on its seed, or it is not sampling.

    A selection rule that always returned one state per episode would silently
    reproduce 160.68's single-slice distribution under a new name.
    """
    first = sample_reroll_state(real_data, 0, 2, random.Random(3))
    again = sample_reroll_state(real_data, 0, 2, random.Random(3))
    assert first[3] == again[3]
    assert first[0] == again[0]

    chosen = {
        sample_reroll_state(real_data, 0, 2, random.Random(seed))[3]["chosen"]
        for seed in range(8)
    }
    assert len(chosen) > 1


def test_selection_does_not_condition_on_whether_end_could_buy(real_data):
    """The sampled state must not be steered by the sign-determining covariate.

    Conditioning on what the observed shop offers would manufacture
    two-sidedness out of the sampling rule (doc 99 entry 160.69). Asserted
    behaviourally: emptying the shop changes what END can buy and must not
    change whether the state qualifies.
    """
    env, _policy, _count = _walk(real_data, 0, 2, 0)
    assert env is not None
    assert _qualifies(env, env.action_masks(), 2)

    env.player.shop.slots = [None] * len(env.player.shop)
    assert not any(env.player.can_buy(slot) for slot in range(len(env.player.shop)))
    assert _qualifies(env, env.action_masks(), 2)

    # ...while a genuinely illegal REROLL must still disqualify the state, or
    # the check above would pass by ignoring legality altogether.
    env.player.gold = env.player.config.reroll_cost - 1
    assert not _qualifies(env, env.action_masks(), 2)
