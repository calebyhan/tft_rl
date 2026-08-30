"""The gold dose-response arms must differ only after the grant (doc 99 160.71).

If arms diverged before the intervention, the measured slope would be replay
noise rather than the price of a gold -- that is outcome D, a defect.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loader import load_all  # noqa: E402
from scripts.gold_value_probe import (  # noqa: E402
    _at,
    horizon_view,
    run_arm,
    slope,
)
from scripts.reroll_target_calibration import _walk  # noqa: E402
from tests.paths import REAL_DATA_DIR  # noqa: E402

ARGS = argparse.Namespace(panel_size=2, trials=2, rounds=1, combat_seed=7)


@pytest.fixture(scope="module")
def sampled():
    data = load_all(REAL_DATA_DIR)
    _env, _policy, qualifying = _walk(data, 0, ARGS.panel_size, None)
    assert qualifying, "seed 0 reached no state where both decisions are legal"
    return data, random.Random(3).randrange(qualifying)


def test_every_arm_starts_from_the_same_pre_grant_state(sampled):
    data, chosen = sampled
    befores = [run_arm(data, 0, chosen, grant, ARGS)["before"] for grant in (0, 2, 50)]
    assert befores[0] == befores[1] == befores[2]


def test_the_grant_is_actually_applied_and_replay_is_deterministic(sampled):
    data, chosen = sampled
    control = run_arm(data, 0, chosen, 0, ARGS)
    repeat = run_arm(data, 0, chosen, 0, ARGS)
    assert control == repeat

    # A grant far larger than any state's own gold must change the trajectory,
    # or the intervention is not reaching the player.
    rich = run_arm(data, 0, chosen, 200, ARGS)
    assert rich["before"] == control["before"]
    assert (rich["gold"], rich["level"], rich["board_units"], rich["margin"]) != (
        control["gold"], control["level"], control["board_units"], control["margin"]
    )


def test_arms_resolve_the_requested_horizon(sampled):
    data, chosen = sampled
    record = run_arm(data, 0, chosen, 0, ARGS)
    assert record["rounds_resolved"] == ARGS.rounds or record["episode_ended"]


def test_slope_recovers_a_known_line():
    assert slope([0, 2, 5, 10], [1.0, 2.0, 3.5, 6.0]) == pytest.approx(0.5)
    assert slope([0, 0, 0], [1.0, 2.0, 3.0]) == 0.0


def test_trajectory_has_one_point_per_resolved_round(sampled):
    data, chosen = sampled
    args = argparse.Namespace(panel_size=2, trials=2, rounds=3, combat_seed=7)
    record = run_arm(data, 0, chosen, 0, args)
    rounds = [point["rounds"] for point in record["trajectory"]]
    assert rounds == list(range(1, record["rounds_resolved"] + 1))
    assert _at(record, record["rounds_resolved"])["margin"] == record["margin"]


def _traj(seed: int, grant: int, margins: dict[int, float], golds: dict[int, int]):
    return {
        "episode_seed": seed,
        "grant": grant,
        "trajectory": [
            {"rounds": r, "margin": margins[r], "gold": golds[r],
             "level": 5, "hp": 50, "board_units": 5}
            for r in sorted(margins)
        ],
    }


def test_horizon_view_pairs_within_seed_and_drops_unpaired_seeds():
    by_dose = {
        0: [_traj(1, 0, {1: 1.0, 2: 2.0}, {1: 0, 2: 0}),
            _traj(2, 0, {1: 1.0}, {1: 0})],
        4: [_traj(1, 4, {1: 3.0, 2: 5.0}, {1: 4, 2: 2}),
            _traj(2, 4, {1: 1.0}, {1: 4})],
    }
    first = horizon_view(by_dose, [0, 4], 1)
    assert [row["n"] for row in first["doses"]] == [2, 2]
    assert first["doses"][1]["mean_margin_delta"] == pytest.approx(1.0)
    assert first["doses"][1]["unchanged"] == 1
    assert first["doses"][1]["banked_fraction"] == pytest.approx(1.0)

    # Seed 2 has no round-2 point, so it must drop out of that horizon entirely
    # rather than pair against a different round.
    second = horizon_view(by_dose, [0, 4], 2)
    assert [row["n"] for row in second["doses"]] == [1, 1]
    assert second["doses"][1]["mean_margin_delta"] == pytest.approx(3.0)
    assert second["doses"][1]["banked_fraction"] == pytest.approx(0.5)


def test_banked_diagnostic_does_not_filter_the_estimate():
    """Every paired arm counts, whether or not it spent the grant (160.73)."""
    by_dose = {
        0: [_traj(1, 0, {1: 1.0}, {1: 0}), _traj(2, 0, {1: 1.0}, {1: 0})],
        # Seed 1 banked the whole grant and moved nothing; seed 2 spent it.
        4: [_traj(1, 4, {1: 1.0}, {1: 4}), _traj(2, 4, {1: 9.0}, {1: 0})],
    }
    view = horizon_view(by_dose, [0, 4], 1)
    assert view["doses"][1]["n"] == 2
    assert view["doses"][1]["mean_margin_delta"] == pytest.approx(4.0)
    assert view["doses"][1]["banked_fraction"] == pytest.approx(0.5)
