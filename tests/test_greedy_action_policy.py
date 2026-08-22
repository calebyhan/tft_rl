"""Regression for the production direct-teacher action scheduler (entry 155)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loader import load_all  # noqa: E402
from rl.opponents import FAST8  # noqa: E402
from scripts.policy_conformance import run_round  # noqa: E402
from tests.paths import REAL_DATA_DIR  # noqa: E402


def test_greedy_action_policy_matches_late_direct_econ_phase():
    """A late reroll phase exercises buys, XP, sells, fielding, and items."""
    row = run_round(load_all(REAL_DATA_DIR), 9, 25, FAST8, "greedy")
    assert row["same_state"], row
    assert not row["hit_action_cap"], row
