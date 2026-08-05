"""The critic data-scaling probe (doc 99 entry 59).

This probe's whole value is that a low held-out EV on real data means the *data*
is the constraint. That inference only holds if the fitter demonstrably works,
so it is checked against a problem whose answer is known.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.critic_scaling import explained_variance, fit_value_head  # noqa: E402


def test_explained_variance_endpoints():
    y = np.array([1.0, 2.0, 3.0, 4.0])
    assert explained_variance(y, y) == pytest.approx(1.0)
    assert explained_variance(np.full(4, y.mean()), y) == pytest.approx(0.0)


def test_explained_variance_of_a_constant_target_is_zero():
    """No variance to explain; must not divide by zero."""
    y = np.full(5, 3.0)
    assert explained_variance(np.arange(5.0), y) == 0.0


def test_fitter_recovers_a_learnable_signal():
    """The load-bearing control.

    A low EV on real returns is only evidence about the observation if the
    fitter can reach a high EV when the signal is genuinely present. Without
    this, "the critic tops out at 0.25" and "the probe is broken" produce the
    same number -- and this project has twice mistaken the second for the first
    (doc 99: *a probe that cannot fit its own training set is a statement about
    the feature set, not the model*).
    """
    rng = np.random.default_rng(0)
    x = rng.normal(size=(4000, 20)).astype(np.float32)
    y = (x @ rng.normal(size=20)).astype(np.float32)
    best = fit_value_head((x[:3000], y[:3000]), (x[3000:], y[3000:]), (256, 256), 6)
    assert best["ev_holdout"] > 0.9, (
        f"fitter reached only {best['ev_holdout']:.3f} on a linear signal; "
        "it cannot be used to argue anything about real data"
    )


def test_fitter_finds_no_signal_in_noise():
    """Pure noise must not produce a positive held-out EV.

    The counterpart to the test above: a fitter that reports signal where there
    is none would make every result look data-limited. `best-over-epochs` makes
    this a real risk, since it selects the most favourable epoch.
    """
    rng = np.random.default_rng(1)
    x = rng.normal(size=(2000, 20)).astype(np.float32)
    y = rng.normal(size=2000).astype(np.float32)
    best = fit_value_head((x[:1500], y[:1500]), (x[1500:], y[1500:]), (256, 256), 6)
    assert best["ev_holdout"] < 0.15, (
        f"reported EV {best['ev_holdout']:.3f} on pure noise"
    )
