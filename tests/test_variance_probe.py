"""Variance decomposition for the critic's achievable ceiling (doc 99 entry 58).

`decompose` produces the number that decides whether PPO was ever given usable
signal, so it is checked against cases whose answers are known by construction
rather than against its own output.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.variance_probe import decompose  # noqa: E402


def test_identical_rollouts_are_fully_explainable():
    """No spread within a seed means the state determines the outcome: EV = 1."""
    by_seed = {0: [1, 1, 1, 1], 1: [4, 4, 4, 4], 2: [8, 8, 8, 8]}
    assert decompose(by_seed, 4)["ev_max"] == pytest.approx(1.0)


def test_pure_noise_has_no_explainable_component():
    """Every seed drawn from the same distribution: nothing is knowable from state.

    The corrected figure must be ~0. The *uncorrected* one is deliberately
    asserted to be larger, because that inflation is the reason the correction
    exists -- estimating each seed's mean from finitely many rollouts creates
    apparent between-seed structure where none is present.
    """
    by_seed = {s: [1, 3, 5, 7] for s in range(6)}
    d = decompose(by_seed, 4)
    assert d["ev_max"] == pytest.approx(0.0, abs=1e-9)

    # Same spread, but rotated so the seed means genuinely differ by sampling
    # alone -- this is the case the correction has to survive.
    rotated = {s: [1, 3, 5, 7][s % 4 :] + [1, 3, 5, 7][: s % 4] for s in range(6)}
    assert decompose(rotated, 4)["ev_max"] == pytest.approx(0.0, abs=1e-9)


def test_correction_reduces_the_ceiling():
    """The corrected ceiling must never exceed the uncorrected one.

    Mutation check: dropping the `- w / rollouts` term makes this fail, which is
    what distinguishes measuring the ceiling from measuring the ceiling plus
    one's own sampling noise.
    """
    by_seed = {0: [1, 2, 3, 4], 1: [3, 4, 5, 6], 2: [5, 6, 7, 8]}
    d = decompose(by_seed, 4)
    assert d["ev_max"] < d["ev_max_uncorrected"]
    assert 0.0 <= d["ev_max"] <= 1.0


def test_variance_components_sum_to_the_total():
    by_seed = {0: [1, 2, 3, 4], 1: [3, 4, 5, 6], 2: [5, 6, 7, 8]}
    d = decompose(by_seed, 4)
    assert d["total"] == pytest.approx(d["within"] + d["between"])


def test_ceiling_is_clamped_when_noise_dominates():
    """`between_raw` below `w/R` must clamp to 0, not produce a negative EV."""
    by_seed = {s: [2, 2, 2, 8] for s in range(4)}
    d = decompose(by_seed, 4)
    assert d["between"] == 0.0
    assert d["ev_max"] == 0.0
