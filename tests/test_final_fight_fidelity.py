"""The final-fight harness must measure what doc 99 entry 160.162 says it does.

Pinned: which boards are paired and what is dropped, where units stand, that
the real winner alternates sides, that the ceiling C is estimated without
bias, and that S reads 1 for an engine whose odds are the truth and 0 for one
whose odds are unrelated to it.
"""

from __future__ import annotations

import json
import logging
import math
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.final_fight_fidelity as harness  # noqa: E402
from engine.hexgrid import Board  # noqa: E402
from engine.items import ItemRegistry  # noqa: E402
from engine.loader import load_all  # noqa: E402
from tests.paths import REAL_DATA_DIR  # noqa: E402

REFERENCE = Path(__file__).resolve().parent.parent / "data" / "reference"


@pytest.fixture(scope="module")
def data():
    logging.disable(logging.WARNING)
    yield load_all(REAL_DATA_DIR)
    logging.disable(logging.NOTSET)


def _melee_and_ranged(data):
    ordered = sorted(data.champions.values(), key=lambda c: c.id)
    melee = next(c.id for c in ordered if c.stats.attack_range <= 1)
    ranged = next(c.id for c in ordered if c.stats.attack_range > 1)
    return melee, ranged


def _seat(placement, last_round, units):
    return {"placement": placement, "last_round": last_round, "units": units}


def test_pairs_take_first_as_winner_and_count_every_drop(data):
    melee, ranged = _melee_and_ranged(data)
    item = sorted(i.id for i in data.items.values())[0]
    matches = [
        {"match_id": "kept", "participants": [
            _seat(2, 30, [{"character_id": ranged, "tier": 2}]),
            _seat(1, 30, [
                {"character_id": melee, "tier": 4, "items": [item, "TFT_Item_Fake"]},
                {"character_id": "TFT17_Summon", "tier": 1},
            ]),
        ]},
        {"match_id": "split", "participants": [
            _seat(1, 31, [{"character_id": melee, "tier": 1}]),
            _seat(2, 30, [{"character_id": ranged, "tier": 1}]),
        ]},
    ]
    pairs, counts = harness.final_pairs(matches, data)
    assert [p["match_id"] for p in pairs] == ["kept"]
    assert pairs[0]["winner"] == [(melee, 3, (item,))]
    assert pairs[0]["loser"] == [(ranged, 2, ())]
    assert counts["unequal_last_round"] == 1
    assert counts["unknown_units"] == 1
    assert counts["clamped_4_stars"] == 1
    assert counts["dropped_items"] == 1 and counts["kept_items"] == 1


def test_items_are_capped_per_unit(data):
    melee, _ranged = _melee_and_ranged(data)
    cap = data.config.max_items_per_unit
    items = sorted(i.id for i in data.items.values())[: cap + 1]
    counts = dict.fromkeys(
        ("unknown_units", "clamped_4_stars", "dropped_items", "kept_items"), 0)
    spec = harness.spec_of({"units": [{"character_id": melee, "tier": 1, "items": items}]},
                           data, counts)
    assert len(spec[0][2]) == cap and counts["dropped_items"] == 1


def test_melee_stands_in_front_and_ranged_behind(data):
    melee, ranged = _melee_and_ranged(data)
    board = Board()
    registry = ItemRegistry(data.items, data.config.max_items_per_unit)
    for team in (0, 1):
        front_unit, back_unit = harness.build(
            [(melee, 1, ()), (ranged, 1, ())], data, registry, board, team)
        assert front_unit.position == board.to_combat(team, 0, 0)
        assert back_unit.position == board.to_combat(team, 1, 0)


def test_the_real_winner_alternates_sides(monkeypatch):
    calls = []

    def fake(data, left, right, seed):
        calls.append((left, seed))
        return 1.0

    monkeypatch.setattr(harness, "fight", fake)
    results = harness.judge(None, "W", "L", trials=4, seed=10)
    assert [left for left, _seed in calls] == ["W", "L", "W", "L"]
    assert [seed for _left, seed in calls] == [10, 11, 12, 13]
    assert results == [1.0, 0.0, 1.0, 0.0]


def test_unbiased_square():
    assert harness.unbiased_square([1.0, 0.0]) == 0.0
    assert harness.unbiased_square([1.0, 1.0, 1.0]) == 1.0
    rng = random.Random(4)
    p = 0.3
    estimates = [harness.unbiased_square([float(rng.random() < p) for _ in range(20)])
                 for _ in range(4000)]
    assert sum(estimates) / len(estimates) == pytest.approx(p * p, abs=0.01)
    with pytest.raises(ValueError):
        harness.unbiased_square([1.0])


def _synthetic(truthful: bool, n: int = 1500, trials: int = 20, seed: int = 5):
    """Engine odds p per match; the real winner drawn from p or from a coin."""
    rng = random.Random(seed)
    outcomes = []
    for _ in range(n):
        p = rng.choice((0.1, 0.3, 0.5, 0.7, 0.9))
        left_won = rng.random() < (p if truthful else 0.5)
        winner_p = p if left_won else 1 - p
        outcomes.append([float(rng.random() < winner_p) for _ in range(trials)])
    return outcomes


def test_skill_is_one_when_the_engine_is_the_truth():
    result = harness.skill(_synthetic(truthful=True), resamples=200)
    assert result["S_ci_low"] < 1.0 < result["S_ci_high"]
    assert result["S"] == pytest.approx(1.0, abs=0.12)


def test_skill_is_zero_when_the_engine_knows_nothing():
    result = harness.skill(_synthetic(truthful=False), resamples=200)
    assert result["S_ci_low"] < 0.0 < result["S_ci_high"]
    assert result["A"] == pytest.approx(0.5, abs=0.03)


def test_the_stored_sample_yields_pairs(data):
    matches = json.loads((REFERENCE / "matches_challenger_2026-08-09.json").read_text())
    pairs, counts = harness.final_pairs(matches["matches"], data)
    assert len(pairs) >= 900, counts
    assert counts["pairs"] + counts["unequal_last_round"] + counts["empty_or_oversized"] \
        <= counts["matches"]


def test_a_fight_is_deterministic_in_its_seed(data):
    matches = json.loads((REFERENCE / "matches_challenger_2026-08-09.json").read_text())
    pair = harness.final_pairs(matches["matches"][:5], data)[0][0]
    first = harness.fight(data, pair["winner"], pair["loser"], 7)
    assert first == harness.fight(data, pair["winner"], pair["loser"], 7)
    assert not math.isnan(first)
