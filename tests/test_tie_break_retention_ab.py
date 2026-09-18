"""The tie-break retention driver's arithmetic and gate (doc 99 entry 160.156)."""

from __future__ import annotations

import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import rl.search as search_mod  # noqa: E402
from scripts.tie_break_retention_ab import (  # noqa: E402
    ARMS,
    EQUIVALENCE_MARGIN,
    equivalent,
    paired,
    summarise,
)


def _records(legacy, visible):
    return [
        {"arm": arm, "seed": seed, "placement": p, "cpu_seconds": 0.0,
         "fight_calls": 0, "accepted_swaps": 0, "item_changes": 0,
         "accepted_moves": 0}
        for arm, column in (("insertion", legacy), ("hex", visible))
        for seed, p in enumerate(column)
    ]


def test_every_arm_is_a_real_tie_break_mode():
    empty = SimpleNamespace(board={})
    previous = search_mod.BOARD_TIE_BREAK
    try:
        for arm in ARMS:
            search_mod.BOARD_TIE_BREAK = arm
            assert search_mod._board_order(empty) == []
    finally:
        search_mod.BOARD_TIE_BREAK = previous


def test_identical_arms_are_equivalent_and_counted():
    column = [1, 4, 6, 2, 8, 3]
    _, comparisons = summarise(_records(column, column))
    contrast = comparisons["hex minus insertion"]
    assert contrast["delta"] == 0
    assert contrast["equivalent"]
    assert comparisons["identical placements"] == len(column)


def test_a_shift_beyond_the_margin_is_not_equivalent():
    legacy = [2, 3, 4, 5, 2, 3]
    visible = [p + 1 for p in legacy]
    _, comparisons = summarise(_records(legacy, visible))
    contrast = comparisons["hex minus insertion"]
    assert contrast["delta"] == pytest.approx(1.0)
    assert not contrast["equivalent"]


def test_the_gate_is_the_ninety_percent_interval_inside_the_margin():
    inside = {"se": 0.05, "ci90_low": -0.1, "ci90_high": EQUIVALENCE_MARGIN - 1e-9}
    straddling = {"se": 0.05, "ci90_low": -0.1, "ci90_high": EQUIVALENCE_MARGIN + 1e-9}
    assert equivalent(inside)
    assert not equivalent(straddling)


def test_one_game_does_not_crash_and_is_never_equivalent():
    contrast = paired([3], [3])
    assert math.isnan(contrast["se"])
    assert not equivalent(contrast)
