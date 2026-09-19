"""The sub-block calibration test must measure what doc 99 entry 160.158 says.

The stored run files are gitignored, so everything here is synthetic. The
claims pinned are the ones the verdict rests on: the χ² tail is right, Q/df
sits at 1 when seed ranges are exchangeable and rises when they are not, and
paired differences line up by seed rather than by record order.
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.block_calibration import (  # noqa: E402
    chi2_sf,
    paired_differences,
    power,
    sub_block_q,
)


def test_chi2_tail_matches_closed_forms():
    # Even df has a finite sum; df=1 is the two-sided normal tail.
    for x in (0.5, 2.0, 7.3, 30.0):
        assert chi2_sf(x, 2) == pytest.approx(math.exp(-x / 2), rel=1e-9)
        m = 18
        closed = math.exp(-x / 2) * sum((x / 2) ** k / math.factorial(k) for k in range(m))
        assert chi2_sf(x, 2 * m) == pytest.approx(closed, rel=1e-9)
    assert chi2_sf(3.841459, 1) == pytest.approx(0.05, abs=1e-6)
    assert chi2_sf(11.0705, 5) == pytest.approx(0.05, abs=1e-5)


def _block(rng: random.Random, n: int, shift_sd: float, size: int = 100):
    diffs = []
    for _ in range(n // size):
        shift = rng.gauss(0.0, shift_sd)
        diffs.extend(rng.gauss(shift, 1.0) for _ in range(size))
    return diffs


def test_q_is_calibrated_on_exchangeable_blocks():
    rng = random.Random(5)
    total_q = total_df = 0
    for _ in range(400):
        q, df = sub_block_q(_block(rng, 600, shift_sd=0.0))
        total_q += q
        total_df += df
    assert total_q / total_df == pytest.approx(1.0, abs=0.08)


def test_q_detects_a_seed_range_shift():
    # A sub-block shift of 0.3 SD at size 100 gives E[Q/df] near 1 + 9 = 10.
    rng = random.Random(6)
    q, df = sub_block_q(_block(rng, 600, shift_sd=0.3))
    assert q / df > 3


def test_sub_blocks_must_tile_the_block():
    with pytest.raises(ValueError):
        sub_block_q([0.0] * 250)


def test_paired_differences_follow_seed_not_record_order():
    # Both arms appear with seed 2 first, so only an explicit sort by seed
    # returns seed 1's difference first.
    records = [
        {"arm": "a", "seed": 2, "placement": 5},
        {"arm": "b", "seed": 2, "placement": 1},
        {"arm": "b", "seed": 1, "placement": 8},
        {"arm": "a", "seed": 1, "placement": 4},
    ]
    assert paired_differences(records, "a", "b") == [4, -4]


def test_paired_differences_refuse_unmatched_seeds():
    records = [
        {"arm": "a", "seed": 1, "placement": 4},
        {"arm": "b", "seed": 2, "placement": 3},
    ]
    with pytest.raises(ValueError):
        paired_differences(records, "a", "b")


def test_power_is_alpha_under_the_null_and_high_under_a_large_shift():
    blocks = [(2.0, 6)] * 6 + [(2.0, 3)] * 3
    assert power(blocks, tau=0.0, alpha=0.05) == pytest.approx(0.05, abs=0.015)
    assert power(blocks, tau=0.6, alpha=0.05) > 0.99
