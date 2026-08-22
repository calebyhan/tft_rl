"""Regression for the direct-teacher/action-space conformance seam (entry 154)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loader import load_all  # noqa: E402
from rl.opponents import FAST8  # noqa: E402
from scripts.greedy_trace_replay import run  # noqa: E402
from tests.paths import REAL_DATA_DIR  # noqa: E402


def test_direct_greedy_trace_replays_through_match_rng():
    """The late reroll state that failed before the shared-RNG correction.

    Seed 9 / phase 25 reaches BUY -> REROLL.  Before entry 154,
    ``GreedyPolicy`` used its own RNG for that roll while ``ActionExecutor``
    used Match.rng, yielding a different shop and failing on the next BUY.
    The full player/shop/pool snapshot is the assertion; action agreement
    alone would not see the stochastic divergence.
    """
    row = run(load_all(REAL_DATA_DIR), 9, 25, FAST8, "match")
    assert row["same_state"], row
    assert row["legal_failure"] is None
