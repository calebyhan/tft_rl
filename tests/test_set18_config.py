"""`data/config.json` carries the Set 18 constants doc 99 entry 161.11 sourced.

Unlike `test_real_dataset`, which pins nothing because fetched data moves with
every patch, `config.json` is hand-curated, so each constant is pinned to the
source that justified it. Values the sources dispute are pinned as *flagged*,
not as correct: they must stay visible in `unverified` until a source settles
them.
"""

from __future__ import annotations

import pytest

from engine.economy import RoundId, round_damage, streak_bonus
from engine.loader import load_all
from tests.paths import REAL_DATA_DIR


@pytest.fixture(scope="module")
def config():
    return load_all(REAL_DATA_DIR).config


def test_level_7_odds_are_set_18s(config):
    """tftflow (18.2) and esportstales agree; 19/30/40/10/1 was the old row."""
    assert config.shop_odds_for_level(7) == (0.16, 0.30, 0.43, 0.10, 0.01)


def test_unchanged_odds_rows_still_hold(config):
    assert config.shop_odds_for_level(6) == (0.30, 0.40, 0.25, 0.05, 0.0)
    assert config.shop_odds_for_level(8) == (0.15, 0.20, 0.32, 0.30, 0.03)
    assert config.pool_sizes == {1: 30, 2: 25, 3: 18, 4: 10, 5: 9}


def test_xp_table_carries_the_18_2_cuts(config):
    """Official 18.2 notes: 7->8 60=>56, 8->9 68=>64, 9->10 68=>64."""
    assert [config.xp_to_next_level[lvl] for lvl in range(1, 10)] == [
        2, 2, 6, 10, 20, 36, 56, 64, 64,
    ]


@pytest.mark.parametrize(
    "count,expected",
    [(1, 0), (2, 1), (3, 1), (4, 1), (5, 2), (6, 3), (9, 3)],
)
def test_a_two_streak_pays(config, count, expected):
    """op.gg and tft-lab agree: 2-4 pay +1, 5 pays +2, 6+ pays +3."""
    assert streak_bonus(config, count, "win") == expected
    assert streak_bonus(config, count, "loss") == expected


def test_stage_5_and_6_damage_are_set_18s(config):
    """Both Set 18 sources give 10 and 12; stages 2 and 7 were never disputed."""
    by_stage = {s: round_damage(config, RoundId(s, 1), []) for s in (2, 5, 6, 7)}
    assert by_stage == {2: 2, 5: 10, 6: 12, 7: 17}


def test_disputed_constants_stay_flagged(config):
    """Stage 3, 4 and 8+ damage and the level cap have conflicting sources."""
    joined = " ".join(config.unverified)
    assert "stage_base_damage" in joined
    assert "max_level" in joined


def test_economy_sources_confirmed_unchanged(config):
    """Income ramp, interest and PvP gold match both Set 18 sources as shipped."""
    assert config.base_income == 5
    assert config.income_ramp == {"1-1": 0, "1-2": 2, "1-3": 2, "1-4": 3, "2-1": 4}
    assert (config.interest_per_gold, config.interest_cap) == (10, 5)
    assert config.pvp_win_gold == 1
