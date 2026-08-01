"""Derived-stat computation: unit + items + traits (milestone 2, doc 03 sec 2.3).

Every expectation here is hand-calculated from the sample dataset rather than
read back out of the engine, so a change in how stats fold together shows up
as a test failure instead of silently redefining "correct".

Reference values used below (data/champions.json, data/items.json,
data/traits.json):

  Jinx   4-cost Marksman [DarkStar, Sniper]  hp 800/1440/2592  ad 65/98/146
         as 0.75  range 4  mana 0/70 (+12/atk)  crit 0.25 / 1.4  armor/mr 30
  Poppy  1-cost Tank     [Mecha, Vanguard]   hp 650  ad 45  armor/mr 45
  Ornn   5-cost Tank     [Mecha, Vanguard, Brawler]

  B.F. Sword          +10 attack_damage
  Recurve Bow         +10% attack_speed
  Giant's Belt        +150 health
  Sparring Gloves     +0.20 crit_chance
  Tear of the Goddess +15 mana (starting mana)
  Needlessly Large Rod +10 ability_power
  Deathblade          +55 attack_damage
  Infinity Edge       +15 attack_damage, +0.25 crit_chance  (unique)
  Rabadon's Deathcap  +50 ability_power
  Sniper Emblem       +10 attack_damage, grants Sniper

  DarkStar   2/4/6 -> +15/35/70 ability_power (trait members)
  Mecha      2/4/6 -> +15/30/60 armor and MR  (whole team)
  Vanguard   2/4   -> +30/80 armor            (trait members)
  Sniper     2/4   -> +1/+2 attack_range, +0.10/0.25 damage_amp (members)
  Brawler    2/4   -> +200/500 health         (trait members)
"""

from __future__ import annotations

import pytest

from engine.items import ItemError, ItemRegistry, emblem_trait_id, item_bonuses
from engine.loader import load_all
from engine.schema import GameData
from engine.stats import (
    ATTACK_SPEED_CAP,
    BASE_ABILITY_POWER,
    CRIT_CHANCE_CAP,
    StatBonuses,
    UnknownStatKey,
    bonuses_from_params,
    derive_stats,
)
from engine.traits import (
    TraitState,
    active_traits,
    trait_bonuses_for,
    trait_counts,
    unit_traits,
)
from engine.unit import StatusEffect, UnitInstance
from tests.paths import STARTER_DATA_DIR


@pytest.fixture(scope="module")
def data() -> GameData:
    return load_all(STARTER_DATA_DIR)


@pytest.fixture(scope="module")
def registry(data) -> ItemRegistry:
    return ItemRegistry(data.items, data.config.max_items_per_unit)


@pytest.fixture
def make(data, registry):
    def _make(champion_id: str, star: int = 1, item_ids: tuple[str, ...] = (), team: int = 0):
        return UnitInstance(
            data.champions[champion_id],
            star,
            [data.items[i] for i in item_ids],
            team=team,
            registry=registry,
        )

    return _make


# --- base stats ----------------------------------------------------------


def test_base_stats_at_one_star(make):
    s = make("TFT17_Jinx").derived_stats()
    assert s.max_health == 800
    assert s.attack_damage == 65
    assert s.attack_speed == 0.75
    assert s.attack_range == 4
    assert s.armor == 30 and s.magic_resist == 30
    assert s.max_mana == 70 and s.starting_mana == 0
    assert s.mana_per_attack == 12
    assert s.crit_chance == 0.25 and s.crit_damage == 1.4
    assert s.ability_power == BASE_ABILITY_POWER
    assert s.ability_power_multiplier == 1.0
    assert s.damage_amp == 0.0


def test_star_level_scales_health_and_attack_damage(make):
    for star, hp, ad in ((1, 800, 65), (2, 1440, 98), (3, 2592, 146)):
        s = make("TFT17_Jinx", star).derived_stats()
        assert (s.max_health, s.attack_damage) == (hp, ad)
        # Non-scaling stats stay put.
        assert s.attack_speed == 0.75 and s.armor == 30


def test_seconds_per_attack_is_the_inverse_of_attack_speed(make):
    assert make("TFT17_Jinx").derived_stats().seconds_per_attack == pytest.approx(1 / 0.75)


def test_invalid_star_level_rejected(make):
    with pytest.raises(ValueError):
        make("TFT17_Jinx", 4)
    with pytest.raises(ValueError):
        make("TFT17_Jinx", 0)


# --- item stat application ----------------------------------------------


def test_flat_item_stats_add(make):
    """Jinx + Deathblade + B.F. Sword: AD 65 + 55 + 10 = 130."""
    s = make("TFT17_Jinx", 1, ("TFT_Item_Deathblade", "TFT_Item_BFSword")).derived_stats()
    assert s.attack_damage == 130


def test_health_and_resist_items_add(make):
    """Poppy + Giant's Belt: 650 + 150 = 800 hp."""
    s = make("TFT17_Poppy", 1, ("TFT_Item_GiantsBelt",)).derived_stats()
    assert s.max_health == 800
    assert s.armor == 45


def test_attack_speed_item_is_a_percentage_of_base(make):
    """Recurve Bow is +10%: 0.75 * 1.10 = 0.825, not 0.85."""
    s = make("TFT17_Jinx", 1, ("TFT_Item_RecurveBow",)).derived_stats()
    assert s.attack_speed == pytest.approx(0.825)


def test_attack_speed_percentages_stack_additively_before_multiplying(make):
    """Two Recurve Bows: 0.75 * (1 + 0.10 + 0.10) = 0.90."""
    s = make("TFT17_Jinx", 1, ("TFT_Item_RecurveBow", "TFT_Item_RecurveBow")).derived_stats()
    assert s.attack_speed == pytest.approx(0.90)


def test_ability_power_is_additive_on_a_100_baseline(make):
    """Rabadon's +50 AP -> 150 AP -> 1.5x ability scaling."""
    s = make("TFT17_AurelionSol", 1, ("TFT_Item_RabadonsDeathcap",)).derived_stats()
    assert s.ability_power == 150
    assert s.ability_power_multiplier == 1.5


def test_tear_grants_starting_mana_not_max_mana(make):
    s = make("TFT17_Jinx", 1, ("TFT_Item_TearOfTheGoddess",)).derived_stats()
    assert s.starting_mana == 15
    assert s.max_mana == 70


def test_starting_mana_cannot_exceed_max_mana(make):
    """Corki has 0/60 mana; four Tears would be 60, five would overflow."""
    unit = make("TFT17_Corki", 1, ("TFT_Item_TearOfTheGoddess",) * 3)
    unit.registry = None  # bypass the 3-item cap to test the clamp itself
    unit.set_trait_bonuses(StatBonuses({"mana": 100}))
    assert unit.derived_stats().starting_mana == 60


def test_crit_chance_is_capped_at_one(make):
    unit = make("TFT17_Jinx")
    unit.set_trait_bonuses(StatBonuses({"crit_chance": 5.0}))
    assert unit.derived_stats().crit_chance == CRIT_CHANCE_CAP


def test_attack_speed_is_capped(make):
    unit = make("TFT17_Jinx")
    unit.set_trait_bonuses(StatBonuses({"attack_speed_pct": 100.0}))
    assert unit.derived_stats().attack_speed == ATTACK_SPEED_CAP


def test_percentage_attack_damage_multiplies_the_post_flat_value(data):
    """(base 65 + flat 10) * 1.5 = 112.5, not 65*1.5 + 10."""
    bonuses = StatBonuses({"attack_damage": 10, "attack_damage_pct": 0.5})
    s = derive_stats(data.champions["TFT17_Jinx"].stats, 1, bonuses)
    assert s.attack_damage == pytest.approx(112.5)


def test_item_bonuses_sums_a_loadout(data):
    b = item_bonuses(
        [data.items["TFT_Item_BFSword"], data.items["TFT_Item_InfinityEdge"]]
    )
    assert b.get("attack_damage") == 25
    assert b.get("crit_chance") == 0.25


def test_unknown_stat_key_is_rejected():
    with pytest.raises(UnknownStatKey):
        StatBonuses().add("spell_vamp", 1.0)


def test_stats_are_recomputed_after_equipping(make):
    unit = make("TFT17_Jinx")
    assert unit.derived_stats().attack_damage == 65
    unit.equip(unit.registry.get("TFT_Item_Deathblade"))
    assert unit.derived_stats().attack_damage == 120
    unit.unequip("TFT_Item_Deathblade")
    assert unit.derived_stats().attack_damage == 65


def test_derived_stats_are_cached_until_invalidated(make):
    unit = make("TFT17_Jinx")
    assert unit.derived_stats() is unit.derived_stats()
    before = unit.derived_stats()
    unit.star_level = 2
    assert unit.derived_stats() is not before


# --- item combination ----------------------------------------------------


def test_combine_is_order_independent(registry):
    assert (
        registry.combine("TFT_Item_BFSword", "TFT_Item_SparringGloves")
        == registry.combine("TFT_Item_SparringGloves", "TFT_Item_BFSword")
        == "TFT_Item_InfinityEdge"
    )


def test_combine_two_of_the_same_component(registry):
    assert registry.combine("TFT_Item_BFSword", "TFT_Item_BFSword") == "TFT_Item_Deathblade"


def test_combine_returns_none_for_an_unused_pair(registry):
    assert registry.combine("TFT_Item_ChainVest", "TFT_Item_TearOfTheGoddess") is None


def test_combine_rejects_non_components(registry):
    with pytest.raises(ItemError, match="not a component"):
        registry.combine("TFT_Item_Deathblade", "TFT_Item_BFSword")


def test_combine_rejects_unknown_ids(registry):
    with pytest.raises(ItemError, match="unknown item"):
        registry.combine("TFT_Item_Nope", "TFT_Item_BFSword")


def test_emblem_is_craftable_from_a_spatula(registry):
    assert (
        registry.combine("TFT_Item_Spatula", "TFT_Item_RecurveBow")
        == "TFT_Item_SniperEmblem"
    )


def test_radiant_maps_back_to_its_base_item(registry, data):
    assert registry.radiant_version("TFT_Item_InfinityEdge") == "TFT_Item_ZenithEdge"
    assert registry.radiant_version("TFT_Item_Deathblade") is None
    assert data.items["TFT_Item_ZenithEdge"].radiant_version_of == "TFT_Item_InfinityEdge"


def test_radiant_does_not_shadow_its_base_items_recipe(registry):
    """Zenith Edge has no recipe, so BF + Gloves still makes Infinity Edge."""
    assert (
        registry.combine("TFT_Item_BFSword", "TFT_Item_SparringGloves")
        == "TFT_Item_InfinityEdge"
    )


def test_emblem_trait_id_extraction(data):
    assert emblem_trait_id(data.items["TFT_Item_SniperEmblem"]) == "Sniper"
    assert emblem_trait_id(data.items["TFT_Item_Deathblade"]) is None


# --- equip rules ---------------------------------------------------------


def test_item_slot_cap_is_enforced(make, data):
    unit = make("TFT17_Jinx", 1, ("TFT_Item_BFSword",) * 3)
    with pytest.raises(ItemError, match="at most 3 items"):
        unit.equip(data.items["TFT_Item_BFSword"])


def test_unique_items_cannot_be_stacked(make, data):
    unit = make("TFT17_Jinx", 1, ("TFT_Item_InfinityEdge",))
    with pytest.raises(ItemError, match="unique"):
        unit.equip(data.items["TFT_Item_InfinityEdge"])


def test_non_unique_items_can_be_stacked(make):
    unit = make("TFT17_Jinx", 1, ("TFT_Item_Deathblade", "TFT_Item_Deathblade"))
    assert unit.derived_stats().attack_damage == 65 + 110


def test_unequipping_an_item_the_unit_lacks_raises(make):
    with pytest.raises(ItemError, match="not holding"):
        make("TFT17_Jinx").unequip("TFT_Item_BFSword")


# --- trait counting ------------------------------------------------------


def test_trait_counts_distinct_champions_not_copies(make):
    """Two Jinxes are one Sniper, not two (doc 01 sec 6)."""
    board = [make("TFT17_Jinx"), make("TFT17_Jinx", 2)]
    assert trait_counts(board) == {"DarkStar": 1, "Sniper": 1}


def test_trait_counts_across_different_champions(make):
    board = [make("TFT17_Jinx"), make("TFT17_Kindred"), make("TFT17_Corki")]
    counts = trait_counts(board)
    assert counts["Sniper"] == 3
    assert counts["DarkStar"] == 2
    assert counts["SpaceGroove"] == 1


def test_emblem_adds_its_trait_to_the_wearer(make):
    plain = make("TFT17_Poppy")
    assert unit_traits(plain) == {"Mecha", "Vanguard"}
    with_emblem = make("TFT17_Poppy", 1, ("TFT_Item_SniperEmblem",))
    assert unit_traits(with_emblem) == {"Mecha", "Vanguard", "Sniper"}


def test_emblem_counts_toward_activation(make, data):
    board = [make("TFT17_Jinx"), make("TFT17_Poppy", 1, ("TFT_Item_SniperEmblem",))]
    assert trait_counts(board)["Sniper"] == 2
    assert "Sniper" in active_traits(board, data)


def test_emblem_on_a_champion_that_already_has_the_trait_adds_nothing(make):
    """Matches TFT: a redundant emblem does not inflate the count."""
    board = [make("TFT17_Jinx", 1, ("TFT_Item_SniperEmblem",)), make("TFT17_Kindred")]
    assert trait_counts(board)["Sniper"] == 2


# --- trait activation ----------------------------------------------------


def test_trait_below_its_lowest_breakpoint_is_inactive(make, data):
    board = [make("TFT17_Jinx")]
    active = active_traits(board, data)
    assert "Sniper" not in active and "DarkStar" not in active


def test_highest_met_breakpoint_wins(make, data):
    """4 Snipers activates the 4-tier only -- tiers do not stack (doc 01 sec 6)."""
    board = [
        make("TFT17_Jinx"),
        make("TFT17_Kindred"),
        make("TFT17_Corki"),
        make("TFT17_Poppy", 1, ("TFT_Item_SniperEmblem",)),
    ]
    active = active_traits(board, data)
    assert active["Sniper"].count == 4
    assert active["Sniper"].params["damage_amp"] == 0.25


def test_irregular_breakpoints_activate_correctly(make, data):
    """Space Groove is 3/5, not 2/4 -- an explicit list, not a pattern."""
    board = [make("TFT17_Corki"), make("TFT17_Lulu")]
    assert "SpaceGroove" not in active_traits(board, data)
    board.append(make("TFT17_Talon"))
    assert active_traits(board, data)["SpaceGroove"].count == 3


def test_bench_units_do_not_count(make, data):
    """active_traits only ever sees the fielded board, so bench is excluded.

    Fielding the bench unit would push Sniper from 3 to the 4-tier; leaving it
    benched must not.
    """
    fielded = [make("TFT17_Jinx"), make("TFT17_Kindred"), make("TFT17_Corki")]
    benched = make("TFT17_Poppy", 1, ("TFT_Item_SniperEmblem",))
    assert trait_counts(fielded)["Sniper"] == 3
    assert active_traits(fielded, data)["Sniper"].count == 2
    assert active_traits(fielded + [benched], data)["Sniper"].count == 4


# --- trait bonus application --------------------------------------------


def test_trait_bonus_applies_to_members_only(make, data):
    """Vanguard 2 gives +30 armor to Vanguards; Jinx is not one."""
    board = [make("TFT17_Poppy"), make("TFT17_Blitzcrank"), make("TFT17_Jinx")]
    active = active_traits(board, data)
    assert active["Vanguard"].count == 2
    assert trait_bonuses_for(board[0], active).get("armor") == 30 + 15  # +Mecha 2
    assert trait_bonuses_for(board[2], active).get("armor") == 15  # Mecha only


def test_team_targeted_trait_applies_to_everyone(make, data):
    """Mecha is targets=team, so Jinx gets its resists despite not being Mecha."""
    board = [make("TFT17_Poppy"), make("TFT17_Blitzcrank"), make("TFT17_Jinx")]
    active = active_traits(board, data)
    jinx_bonuses = trait_bonuses_for(board[2], active)
    assert jinx_bonuses.get("armor") == 15
    assert jinx_bonuses.get("magic_resist") == 15


def test_full_derived_stats_with_traits_and_items(make, data):
    """End-to-end hand calculation.

    Board: Jinx, Kindred (2 Snipers, 2 Dark Star), Poppy, Blitzcrank (2 Mecha,
    2 Vanguard). Jinx 2-star holding Infinity Edge + B.F. Sword.

      health          1440 (2-star, no health sources)
      attack_damage   98 + 15 (IE) + 10 (BF) = 123
      attack_range    4 + 1 (Sniper 2)        = 5
      armor           30 + 15 (Mecha 2, team) = 45
      magic_resist    30 + 15 (Mecha 2, team) = 45
      crit_chance     0.25 + 0.25 (IE)        = 0.50
      ability_power   100 + 15 (Dark Star 2)  = 115
      damage_amp      0.10 (Sniper 2)
    """
    jinx = make("TFT17_Jinx", 2, ("TFT_Item_InfinityEdge", "TFT_Item_BFSword"))
    board = [jinx, make("TFT17_Kindred"), make("TFT17_Poppy"), make("TFT17_Blitzcrank")]

    state = TraitState(board, data)
    assert state.tier_of("Sniper") == 2
    assert state.tier_of("DarkStar") == 2
    assert state.tier_of("Mecha") == 2
    assert state.tier_of("Vanguard") == 2
    assert state.tier_of("Brawler") == 0

    jinx.set_trait_bonuses(state.bonuses_for(jinx))
    s = jinx.derived_stats()
    assert s.max_health == 1440
    assert s.attack_damage == 123
    assert s.attack_range == 5
    assert s.armor == 45
    assert s.magic_resist == 45
    assert s.crit_chance == 0.50
    assert s.ability_power == 115
    assert s.damage_amp == pytest.approx(0.10)
    # Unaffected by any of the above.
    assert s.attack_speed == 0.75
    assert s.mana_per_attack == 12


def test_poppy_in_the_same_board_gets_a_different_bonus_set(make, data):
    """Same board, different unit: tank traits instead of carry traits."""
    board = [
        make("TFT17_Jinx", 2),
        make("TFT17_Kindred"),
        make("TFT17_Poppy"),
        make("TFT17_Blitzcrank"),
    ]
    poppy = board[2]
    state = TraitState(board, data)
    poppy.set_trait_bonuses(state.bonuses_for(poppy))
    s = poppy.derived_stats()
    # 45 base + 15 Mecha (team) + 30 Vanguard (member) = 90
    assert s.armor == 90
    # 45 base + 15 Mecha; Vanguard grants no MR.
    assert s.magic_resist == 60
    assert s.attack_range == 1  # not a Sniper
    assert s.ability_power == BASE_ABILITY_POWER  # not Dark Star


def test_params_that_are_not_stats_are_left_to_the_effect_hook():
    """Space Groove's heal_per_second is behaviour, not a stat."""
    bonuses = bonuses_from_params({"targets": "team", "heal_per_second": 20, "armor": 5})
    assert bonuses.values == {"armor": 5.0}


def test_trait_state_repr_is_readable(make, data):
    board = [make("TFT17_Jinx"), make("TFT17_Kindred")]
    text = repr(TraitState(board, data))
    assert "DarkStar 2/2" in text and "Sniper 2/2" in text


# --- status effects ------------------------------------------------------


def test_status_effect_bonuses_fold_into_derived_stats(make):
    unit = make("TFT17_Jinx")
    unit.add_status(
        StatusEffect("jinx_get_excited", remaining=6.0, bonuses=StatBonuses({"attack_speed_pct": 0.75}))
    )
    assert unit.derived_stats().attack_speed == pytest.approx(0.75 * 1.75)


def test_expired_status_effects_are_removed_and_stats_revert(make):
    unit = make("TFT17_Jinx")
    unit.add_status(
        StatusEffect("buff", remaining=1.0, bonuses=StatBonuses({"attack_damage": 100}))
    )
    assert unit.derived_stats().attack_damage == 165
    unit.tick_statuses(0.5)
    assert unit.derived_stats().attack_damage == 165
    unit.tick_statuses(0.6)
    assert unit.status_effects == []
    assert unit.derived_stats().attack_damage == 65


def test_permanent_status_effects_never_expire(make):
    unit = make("TFT17_Jinx")
    unit.add_status(StatusEffect("permanent", remaining=None, bonuses=StatBonuses({"armor": 10})))
    unit.tick_statuses(100.0)
    assert len(unit.status_effects) == 1
    assert unit.derived_stats().armor == 40


def test_cc_flags(make):
    unit = make("TFT17_Jinx")
    assert not (unit.is_stunned or unit.is_rooted or unit.is_disarmed)
    unit.add_status(StatusEffect("stun", remaining=1.0, stun=True))
    # A stun implies both root and disarm.
    assert unit.is_stunned and unit.is_rooted and unit.is_disarmed


def test_root_does_not_imply_disarm(make):
    unit = make("TFT17_Jinx")
    unit.add_status(StatusEffect("root", remaining=1.0, root=True))
    assert unit.is_rooted and not unit.is_disarmed and not unit.is_stunned


# --- combat reset --------------------------------------------------------


def test_reset_for_combat_sets_full_hp_and_starting_mana(make):
    unit = make("TFT17_Poppy", 2, ("TFT_Item_TearOfTheGoddess",))
    unit.reset_for_combat()
    assert unit.current_hp == 1170
    assert unit.current_mana == 30 + 15
    assert unit.alive and unit.target_uid is None


def test_reset_for_combat_clears_stale_state(make):
    unit = make("TFT17_Jinx")
    unit.add_status(StatusEffect("stun", remaining=1.0, stun=True))
    unit.current_hp = 1.0
    unit.alive = False
    unit.reset_for_combat()
    assert unit.status_effects == [] and unit.shields == []
    assert unit.current_hp == 800 and unit.alive


def test_health_fraction(make):
    unit = make("TFT17_Jinx")
    unit.reset_for_combat()
    assert unit.health_fraction == 1.0
    unit.current_hp = 200
    assert unit.health_fraction == 0.25


def test_units_have_distinct_ids(make):
    assert make("TFT17_Jinx").uid != make("TFT17_Jinx").uid


# --- sell value (doc 01 sec 4) ------------------------------------------


@pytest.mark.parametrize(
    "champion_id,star,expected",
    [
        ("TFT17_Poppy", 1, 1),  # 1-star 1-cost: no penalty
        ("TFT17_Poppy", 2, 2),  # 3 copies = 3, -1 = 2
        ("TFT17_Poppy", 3, 8),  # 9 copies = 9, -1 = 8
        ("TFT17_Corki", 1, 2),  # 2, -1 = 1, but clamped up to cost 2
        ("TFT17_Corki", 2, 5),  # 6 - 1
        ("TFT17_Lulu", 2, 8),  # 9 - 1
        ("TFT17_Jinx", 1, 4),  # 4 - 1 = 3, clamped up to cost 4
        ("TFT17_Jinx", 2, 11),  # 12 - 1
        ("TFT17_Ornn", 3, 44),  # 45 - 1
    ],
)
def test_sell_value(make, champion_id, star, expected):
    assert make(champion_id, star).sell_value() == expected
