"""The real-TFT reference reduction, for doc 99 entry 97's fidelity comparison.

Two things here are load-bearing and would fail silently if wrong.

**The round mapping.** Riot reports `last_round` as a flat index; every window
conclusion is keyed by the `stage-round` label it maps to. An off-by-one still
produces a full, plausible table -- it just attributes every elimination to the
wrong round. The strongest available check is structural rather than arithmetic
and is asserted below: real TFT has no combat on the carousel round (`x-4`), so
a correct mapping puts a hard zero there and a wrong one does not.

**Non-champion units.** Riot's per-participant `units` list carries summons and
PvE monsters with junk `rarity` values. An early `rarity + 1` fallback turned
them into cost-7 and cost-10 champions and reported "17 holders of a cost-10
3-star" without any error.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from reference_profile import (  # noqa: E402
    label_sort_key,
    last_round_to_label,
    reduce_matches,
    round_structure,
    summarise_rows,
    unit_cost,
    validate_round_labels,
)

STAGE_ONE, PER_STAGE = 4, 7


@pytest.mark.parametrize("index,label", [
    (1, "1-1"),
    (4, "1-4"),      # last round of the short opening stage
    (5, "2-1"),      # first round of the first full stage
    (11, "2-7"),
    (12, "3-1"),
    (32, "5-7"),
    (33, "6-1"),
    (34, "6-2"),
])
def test_last_round_maps_to_stage_round(index, label):
    assert last_round_to_label(index, STAGE_ONE, PER_STAGE) == label


def test_mapping_is_contiguous_and_ordered():
    """Consecutive indices give consecutive labels, with no gap or repeat."""
    labels = [last_round_to_label(i, STAGE_ONE, PER_STAGE) for i in range(1, 60)]
    assert len(set(labels)) == len(labels)
    assert labels == sorted(labels, key=label_sort_key)


def test_mapping_uses_the_configured_structure():
    """The stage shape comes from config.json, not from a literal in the code."""
    stage_one, per_stage = round_structure()
    assert (stage_one, per_stage) == (STAGE_ONE, PER_STAGE)
    assert last_round_to_label(stage_one + 1, stage_one, per_stage) == "2-1"


def test_index_below_one_is_rejected():
    with pytest.raises(ValueError):
        last_round_to_label(0, STAGE_ONE, PER_STAGE)


def test_validate_flags_an_impossible_origin():
    """Eliminations inside stage 1 mean the index origin is wrong."""
    problems = validate_round_labels([2, 3, 4], STAGE_ONE, PER_STAGE)
    assert problems and "stage 1" in problems[0]


def test_validate_is_quiet_on_plausible_data():
    assert validate_round_labels([12, 20, 34], STAGE_ONE, PER_STAGE) == []


# --------------------------------------------------------------------------
# The structural check on real data: carousel rounds cannot eliminate anyone.
# --------------------------------------------------------------------------

REFERENCE_FILES = sorted(
    (Path(__file__).resolve().parent.parent / "data" / "reference")
    .glob("matches_*.json")
)


@pytest.mark.skipif(not REFERENCE_FILES, reason="no reference sample fetched")
def test_carousel_rounds_are_a_structural_trough():
    """`x-4` is a carousel: no combat, so essentially no eliminations.

    This validates the round mapping against reality rather than against its
    own arithmetic. If `last_round_to_label` were off by one, the trough would
    land on an ordinary combat round and this fails.

    Not a hard zero: 4 of ~3,800 eliminations in the first challenger sample
    did land on a carousel, which is what leaving the game (surrender, AFK)
    looks like -- it is not gated on combat. The signal is the ~100x gap
    against the neighbouring rounds, so that is what gets asserted.
    """
    import json

    payload = json.loads(REFERENCE_FILES[0].read_text())
    profile = reduce_matches(payload["matches"])
    counts = profile["elimination_round"]
    total = sum(counts.values())
    assert total > 500, f"reference sample too small to test shape (n={total})"

    for stage in (4, 5, 6):
        carousel = counts.get(f"{stage}-4", 0)
        neighbours = [counts.get(f"{stage}-{r}", 0) for r in (3, 5)]
        # Absolute floor first, so the ratio below cannot be satisfied by two
        # empty neighbours -- a trough between nothing and nothing is vacuous.
        assert min(neighbours) >= 20, (
            f"rounds {stage}-3/{stage}-5 hold {neighbours} eliminations; too "
            "few for the trough test to mean anything"
        )
        assert carousel * 10 <= min(neighbours), (
            f"round {stage}-4 holds {carousel} eliminations against "
            f"{neighbours} on either side; a carousel round should be an order "
            "of magnitude quieter -- the mapping is misaligned"
        )


# --------------------------------------------------------------------------
# Non-champion units
# --------------------------------------------------------------------------

def _participant(units, placement=1, last_round=34, level=9, gold=5):
    return {
        "placement": placement, "last_round": last_round, "level": level,
        "gold_left": gold, "units": units,
    }


def _match(participants):
    return {"match_id": "T1", "participants": participants}


def test_summons_are_dropped_not_given_an_invented_cost():
    """A 3-star summon must not appear as a cost-10 champion."""
    match = _match([
        _participant([
            {"character_id": "TFT17_Akali", "tier": 3, "rarity": 1},
            {"character_id": "TFT17_Summon", "tier": 3, "rarity": 9},
            {"character_id": "TFT17_PVE_ElderDragon", "tier": 3, "rarity": 9},
        ], placement=1),
        _participant([], placement=2),
    ])
    profile = reduce_matches([match])
    three = profile["three_star"]

    assert set(three["placement_by_cost"]) == {"2"}, (
        f"non-champion units leaked into the cost table: "
        f"{three['placement_by_cost']}"
    )
    assert three["unknown_units"] == 2
    assert three["non_champion_ids"]["TFT17_Summon"] == 1


def test_unit_cost_resolves_from_our_own_data():
    costs = {"TFT17_Akali": 2}
    assert unit_cost({"character_id": "TFT17_Akali", "rarity": 1}, costs) == 2
    # rarity is deliberately NOT used as a fallback
    assert unit_cost({"character_id": "TFT17_Summon", "rarity": 9}, costs) is None


def test_board_size_excludes_summons():
    match = _match([
        _participant([
            {"character_id": "TFT17_Akali", "tier": 2, "rarity": 1},
            {"character_id": "TFT17_Summon", "tier": 1, "rarity": 9},
        ], placement=8, last_round=20),
        _participant([], placement=1, last_round=20),
    ])
    profile = reduce_matches([match])
    label = last_round_to_label(20, STAGE_ONE, PER_STAGE)
    assert profile["at_elimination"][label]["units"] == 1


# --------------------------------------------------------------------------
# Conditioning
# --------------------------------------------------------------------------

def test_the_winner_is_not_counted_as_eliminated():
    """Placement 1 reaches the last round without dying there.

    Counting them would put a spike at the final round of every game in a
    distribution meant to describe how long *losing* seats survive.
    """
    match = _match([
        _participant([], placement=1, last_round=34),
        _participant([], placement=2, last_round=34),
    ])
    profile = reduce_matches([match])
    assert profile["elimination_round"] == {"6-2": 1}
    assert profile["n_participants"] == 2


def test_a_player_holding_two_three_stars_counts_once_as_a_holder():
    """...but once per distinct cost in the by-cost table."""
    match = _match([
        _participant([
            {"character_id": "TFT17_Akali", "tier": 3, "rarity": 1},
            {"character_id": "TFT17_Aatrox", "tier": 3, "rarity": 0},
        ], placement=3),
    ])
    three = reduce_matches([match])["three_star"]
    assert three["n_holders"] == 1
    assert three["holders_by_cost"] == {"1": 1, "2": 1}


def test_summarise_rows_reports_spread():
    cell = summarise_rows([
        {"level": 8, "gold": 10, "units": 8},
        {"level": 6, "gold": 30, "units": 6},
    ])
    assert cell["n"] == 2
    assert cell["level"] == 7.0
    assert cell["level_sd"] == pytest.approx(1.4142, abs=1e-3)
