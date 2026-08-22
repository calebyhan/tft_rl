"""Regression for the common-base search-buy action port (entry 157)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loader import load_all  # noqa: E402
from rl.opponents import FAST8  # noqa: E402
from scripts.policy_conformance import run_round  # noqa: E402
from tests.paths import REAL_DATA_DIR  # noqa: E402


def test_search_buy_action_policy_matches_direct_late_phase():
    row = run_round(
        load_all(REAL_DATA_DIR), 9, 15, FAST8, "search_buy", "search_buy"
    )
    assert row["same_state"], row
    assert not row["hit_action_cap"], row


def test_search_buy_action_policy_defers_augment_until_after_planning():
    """2-1 exposes the Match order: plan first, resolve augment second."""
    row = run_round(
        load_all(REAL_DATA_DIR), 7, 6, FAST8, "search_buy", "search_buy"
    )
    assert row["same_state"], row
    assert not row["hit_action_cap"], row
