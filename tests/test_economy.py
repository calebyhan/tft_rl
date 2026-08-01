"""Economy tests (milestone 4, doc 01 sec 4).

Expectations are transcribed from doc 01 sec 4's prose, not read back out of
config.json, so a wrong config value fails a test.
"""

from __future__ import annotations

import pytest

from engine.economy import (
    RoundId,
    apply_xp,
    base_income,
    interest,
    round_damage,
    round_income,
    sell_value,
    streak_bonus,
    xp_cost_to_buy,
    xp_to_next_level,
)
from engine.loader import load_all
from tests.paths import STARTER_DATA_DIR


@pytest.fixture(scope="module")
def config():
    return load_all(STARTER_DATA_DIR).config


# --- round ids -----------------------------------------------------------


def test_round_id_parsing_and_formatting():
    assert RoundId.parse("2-1") == RoundId(2, 1)
    assert str(RoundId(4, 7)) == "4-7"


@pytest.mark.parametrize("bad", ["", "2", "x-1", "2-", None])
def test_malformed_round_id_rejected(bad):
    with pytest.raises(ValueError):
        RoundId.parse(bad)


def test_round_ids_order_by_stage_then_round():
    assert RoundId(2, 7) < RoundId(3, 1)
    assert sorted([RoundId(3, 1), RoundId(2, 2)]) == [RoundId(2, 2), RoundId(3, 1)]


def test_round_advances_and_rolls_over_into_the_next_stage():
    assert RoundId(2, 1).next(7) == RoundId(2, 2)
    assert RoundId(2, 7).next(7) == RoundId(3, 1)


# --- base income (doc 01 sec 4) -----------------------------------------


@pytest.mark.parametrize(
    "round_text,expected",
    [
        ("1-2", 2),
        ("1-3", 2),
        ("1-4", 3),
        ("2-1", 4),
        ("2-2", 5),  # the ramp ends here
        ("2-7", 5),
        ("3-1", 5),
        ("6-4", 5),
    ],
)
def test_base_income_follows_the_stage_one_ramp(config, round_text, expected):
    assert base_income(config, RoundId.parse(round_text)) == expected


# --- interest (doc 01 sec 4) --------------------------------------------


@pytest.mark.parametrize(
    "gold,expected",
    [
        (0, 0),
        (9, 0),
        (10, 1),
        (19, 1),
        (30, 3),
        (49, 4),
        (50, 5),
        (51, 5),
        (100, 5),  # capped at +5
        (999, 5),
    ],
)
def test_interest_is_one_per_ten_capped_at_five(config, gold, expected):
    assert interest(config, gold) == expected


def test_negative_gold_earns_no_interest(config):
    assert interest(config, -5) == 0


# --- streaks (doc 01 sec 4) ---------------------------------------------


@pytest.mark.parametrize(
    "count,expected",
    [(0, 0), (1, 0), (2, 0), (3, 1), (4, 1), (5, 2), (6, 3), (7, 3), (15, 3)],
)
@pytest.mark.parametrize("streak_type", ["win", "loss"])
def test_streak_bonus_thresholds(config, count, expected, streak_type):
    """+1 at 3-4, +2 at 5, +3 at 6+, identical for win and loss streaks."""
    assert streak_bonus(config, count, streak_type) == expected


def test_no_streak_pays_nothing(config):
    assert streak_bonus(config, 8, "none") == 0


# --- combined round income ----------------------------------------------


def test_income_is_base_plus_interest_plus_streak_plus_win_bonus(config):
    breakdown = round_income(
        config, RoundId(3, 2), gold=32, streak_count=5, streak_type="win", won_pvp=True
    )
    assert breakdown.base == 5
    assert breakdown.interest == 3
    assert breakdown.streak == 2
    assert breakdown.win_bonus == 1
    assert breakdown.total == 11


def test_interest_uses_gold_held_before_income_is_added(config):
    """Doc 01 sec 4: interest is computed at end of round, before income."""
    # 48 gold earns 4 interest, not the 5 it would earn after +5 base income.
    assert round_income(config, RoundId(3, 2), gold=48).interest == 4


def test_loss_streak_still_pays_but_wins_no_win_bonus(config):
    breakdown = round_income(
        config, RoundId(3, 2), gold=0, streak_count=6, streak_type="loss", won_pvp=False
    )
    assert breakdown.streak == 3
    assert breakdown.win_bonus == 0
    assert breakdown.total == 8


def test_pve_round_pays_streak_without_a_win_bonus(config):
    """Streak gold is paid every round, including PvE ones (doc 01 sec 4)."""
    breakdown = round_income(
        config, RoundId(2, 4), gold=0, streak_count=3, streak_type="win", won_pvp=False
    )
    assert breakdown.streak == 1 and breakdown.win_bonus == 0


# --- XP and levelling (doc 01 sec 4) ------------------------------------


def test_xp_costs_four_gold_for_four_xp(config):
    assert xp_cost_to_buy(config, 4) == 4
    assert xp_cost_to_buy(config, 8) == 8
    assert xp_cost_to_buy(config, 0) == 0
    # Partial buys round up to a whole purchase.
    assert xp_cost_to_buy(config, 1) == 4
    assert xp_cost_to_buy(config, 5) == 8


def test_levelling_consumes_the_threshold_and_keeps_the_remainder(config):
    level, xp = apply_xp(config, level=3, xp=0, gained=8)
    # Level 3 needs 6 XP; the extra 2 carries into level 4.
    assert (level, xp) == (4, 2)


def test_a_single_grant_can_cross_several_levels(config):
    level, _ = apply_xp(config, level=1, xp=0, gained=4)
    assert level == 3  # 2 XP to reach 2, 2 more to reach 3


def test_xp_stops_accumulating_at_max_level(config):
    level, xp = apply_xp(config, level=config.max_level, xp=0, gained=500)
    assert level == config.max_level and xp == 0


def test_xp_to_next_level_is_none_at_max(config):
    assert xp_to_next_level(config, config.max_level) is None
    assert xp_to_next_level(config, 1) == 2


def test_negative_xp_is_rejected(config):
    with pytest.raises(ValueError):
        apply_xp(config, 3, 0, -1)


def test_xp_thresholds_increase_with_level(config):
    thresholds = [config.xp_to_next_level[lvl] for lvl in sorted(config.xp_to_next_level)]
    assert thresholds == sorted(thresholds)


# --- sell value (doc 01 sec 4) ------------------------------------------


@pytest.mark.parametrize(
    "cost,star,expected",
    [
        (1, 1, 1),  # only a 1-star 1-cost escapes the penalty
        (1, 2, 2),  # 3 combine cost - 1
        (1, 3, 8),  # 9 combine cost - 1
        (2, 1, 2),  # 2 - 1 = 1, floored back up to the champion cost
        (2, 2, 5),  # 6 - 1
        (2, 3, 17),  # 18 - 1
        (3, 1, 3),  # floored
        (3, 2, 8),  # 9 - 1
        (4, 1, 4),  # floored
        (4, 2, 11),  # 12 - 1
        (5, 3, 44),  # 45 - 1
    ],
)
def test_sell_value(cost, star, expected):
    assert sell_value(cost, star) == expected


def test_sell_value_never_drops_below_the_champion_cost():
    for cost in range(1, 6):
        for star in (1, 2, 3):
            assert sell_value(cost, star) >= cost


def test_sell_value_rejects_nonsense():
    with pytest.raises(ValueError):
        sell_value(0, 1)
    with pytest.raises(ValueError):
        sell_value(1, 4)


# --- round damage (doc 01 sec 7) ----------------------------------------


def test_round_damage_is_stage_base_plus_scaled_survivors(config):
    """Stage 3 base 5, plus a 2-star 4-cost (8) and a 1-star 1-cost (1)."""
    damage = round_damage(config, RoundId(3, 2), [(4, 2), (1, 1)])
    assert damage == 5 + 8 + 1


def test_round_damage_grows_with_stage(config):
    empty = []
    by_stage = [round_damage(config, RoundId(s, 1), empty) for s in range(2, 7)]
    assert by_stage == sorted(by_stage)
    assert by_stage[0] < by_stage[-1]


def test_star_level_multiplies_a_survivors_contribution(config):
    one = round_damage(config, RoundId(2, 1), [(3, 1)])
    three = round_damage(config, RoundId(2, 1), [(3, 3)])
    base = round_damage(config, RoundId(2, 1), [])
    assert one - base == 3
    assert three - base == 9


def test_no_survivors_means_only_the_stage_base(config):
    assert round_damage(config, RoundId(4, 1), []) == config.stage_base_damage[4]


def test_very_late_stages_clamp_to_the_last_configured_row(config):
    """A game running past the table's last stage must not KeyError."""
    last = max(config.stage_base_damage)
    assert round_damage(config, RoundId(last + 5, 1), []) == config.stage_base_damage[last]
