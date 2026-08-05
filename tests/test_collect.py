"""Parallel expert collection must be byte-identical to serial (doc 99 48).

Behaviour cloning's dataset is not just a set of correct rows -- its *order*
sets minibatch composition during fitting, so a dataset assembled in completion
order would still be individually correct while making every clone
unreproducible. These tests pin both properties.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loader import load_all  # noqa: E402
from rl.collect import collect_parallel, discounted_returns  # noqa: E402
from scripts.train_ppo import collect_expert_data  # noqa: E402
from tests.paths import STARTER_DATA_DIR  # noqa: E402

EXPERT = dict(sell_bench=True, buy_synergy=True, match_items=True, corner_carry=True)


@pytest.fixture(scope="module")
def data():
    return load_all(STARTER_DATA_DIR)


def test_discounted_returns_accumulate_backwards():
    assert discounted_returns([0.0, 0.0, 5.0], 0.9) == pytest.approx(
        [0.9 * 0.9 * 5.0, 0.9 * 5.0, 5.0]
    )


def test_parallel_collection_is_identical_to_serial(data):
    """The claim the whole change rests on.

    Four episodes over three workers, so at least one worker takes two and the
    blocks genuinely come back interleaved rather than in a trivially correct
    order.
    """
    serial = collect_expert_data(data, 4, expert_kwargs=EXPERT, workers=1)
    parallel = collect_parallel(
        [10_000 + i for i in range(4)],
        gamma=0.999,
        workers=3,
        data_dir=STARTER_DATA_DIR,
        expert_kwargs=EXPERT,
    )
    names = ("observations", "masks", "actions", "returns")
    for name, want, got in zip(names, serial, parallel, strict=True):
        assert want.shape == got.shape, name
        assert np.array_equal(want, got), f"{name} differ between serial and parallel"


def test_collection_is_not_trivially_empty(data):
    """Guards the equivalence test above from passing on two empty arrays."""
    observations, masks, actions, returns = collect_expert_data(
        data, 2, expert_kwargs=EXPERT, workers=1
    )
    assert len(observations) > 50
    assert len(observations) == len(masks) == len(actions) == len(returns)
    # A constant return column would make the value target vacuous.
    assert len(set(returns.tolist())) > 1


def test_seeds_are_reassembled_in_order_not_completion_order(data):
    """Row order must follow the seed list even when workers finish out of turn.

    Collecting the seeds reversed must produce the reversed *blocks*, not the
    same array -- if the implementation ignored the requested order and sorted
    by seed internally, both calls would return identical arrays and this
    would fail.
    """
    seeds = [10_000, 10_001]
    forward = collect_parallel(
        seeds, gamma=0.999, workers=2,
        data_dir=STARTER_DATA_DIR, expert_kwargs=EXPERT,
    )
    backward = collect_parallel(
        list(reversed(seeds)), gamma=0.999, workers=2,
        data_dir=STARTER_DATA_DIR, expert_kwargs=EXPERT,
    )
    assert forward[0].shape == backward[0].shape
    assert not np.array_equal(forward[0], backward[0]), (
        "reversing the seed list changed nothing -- row order does not follow "
        "the requested seeds"
    )
