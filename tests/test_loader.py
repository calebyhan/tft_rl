"""Tests for engine.schema + engine.loader (doc 02 sec 2, doc 03 sec 2.2).

Covers both "the shipped starter dataset loads and is internally consistent"
and "malformed data fails loudly with every problem listed".
"""

from __future__ import annotations

import dataclasses
import json
import shutil
from pathlib import Path
from typing import Any, Callable

import pytest

from engine.loader import DataValidationError, load_all
from engine.schema import (
    ITEM_CATEGORIES,
    ITEM_STAT_KEYS,
    ROLES,
    STAR_LEVELS,
    TRAIT_CATEGORIES,
    GameData,
    TraitBreakpoint,
    TraitDef,
)
from tests.paths import STARTER_DATA_DIR


@pytest.fixture(scope="module")
def data() -> GameData:
    return load_all(STARTER_DATA_DIR)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A writable copy of the shipped dataset, for corruption tests."""
    dest = tmp_path / "data"
    shutil.copytree(STARTER_DATA_DIR, dest)
    return dest


def edit(path: Path, mutate: Callable[[Any], Any]) -> None:
    """Apply ``mutate`` to a JSON file in place."""
    raw = json.loads(path.read_text())
    path.write_text(json.dumps(mutate(raw)))


def find(entries: list[dict], entry_id: str) -> dict:
    return next(e for e in entries if e["id"] == entry_id)


# --- the shipped starter dataset -----------------------------------------


def test_starter_dataset_loads(data):
    assert data.champions and data.traits and data.items
    assert data.version.set == 17
    assert data.version.patch == "17.8"


def test_starter_dataset_meets_doc_02_sec_5_coverage_requirements(data):
    """The hand-authored slice must cover every cost tier and enough traits."""
    assert 10 <= len(data.champions) <= 15
    for cost in (1, 2, 3, 4, 5):
        assert len(data.champions_by_cost(cost)) >= 2, f"cost {cost} under-covered"
    assert len(data.traits) >= 4
    # At least one trait with a 2-unit breakpoint and one with a 4-unit one.
    counts = {bp.count for t in data.traits.values() for bp in t.breakpoints}
    assert {2, 4} <= counts
    assert len(data.items) >= 5
    categories = {i.category for i in data.items.values()}
    assert {"component", "advanced"} <= categories
    # A mix of stat-only and effect-hook items.
    assert any(i.effect_id is None and i.stats for i in data.items.values())
    assert any(i.effect_id is not None for i in data.items.values())


def test_every_champion_trait_resolves(data):
    for champ in data.champions.values():
        for trait_id in champ.traits:
            assert trait_id in data.traits


def test_every_recipe_resolves_to_components(data):
    for item in data.items.values():
        for component_id in item.recipe:
            assert data.items[component_id].is_component


def test_ids_are_keyed_consistently(data):
    for registry in (data.champions, data.traits, data.items):
        for key, value in registry.items():
            assert key == value.id


def test_schema_vocabulary_is_respected(data):
    for champ in data.champions.values():
        assert champ.role in ROLES
        assert len(champ.stats.health) == STAR_LEVELS
        assert len(champ.stats.attack_damage) == STAR_LEVELS
    for trait in data.traits.values():
        assert trait.category in TRAIT_CATEGORIES
    for item in data.items.values():
        assert item.category in ITEM_CATEGORIES
        assert set(item.stats) <= ITEM_STAT_KEYS


def test_per_star_stats_are_monotonically_increasing(data):
    for champ in data.champions.values():
        hp = champ.stats.health
        ad = champ.stats.attack_damage
        assert hp[0] <= hp[1] <= hp[2], champ.id
        assert ad[0] <= ad[1] <= ad[2], champ.id


def test_mana_per_attack_is_role_derived_unless_overridden(data):
    role_mana = data.config.role_mana_per_attack
    jinx = data.champions["TFT17_Jinx"]
    assert jinx.stats.mana_per_attack == 12, "explicit override should win"
    for champ in data.champions.values():
        if champ.id == "TFT17_Jinx":
            continue
        assert champ.stats.mana_per_attack == role_mana[champ.role], champ.id


def test_tanks_generate_less_mana_per_attack_than_carries(data):
    """Doc 01 sec 3.2: 10 for Assassin/Marksman/Fighter, 7 Caster, 5 Tank."""
    role_mana = data.config.role_mana_per_attack
    assert role_mana["Tank"] == 5
    assert role_mana["Caster"] == 7
    assert role_mana["Assassin"] == role_mana["Marksman"] == role_mana["Fighter"] == 10


def test_config_matches_doc_01_economy_numbers(data):
    cfg = data.config
    assert cfg.base_income == 5
    assert cfg.interest_per_gold == 10
    assert cfg.interest_cap == 5
    assert cfg.reroll_cost == 2
    assert cfg.bench_size == 9
    assert cfg.max_items_per_unit == 3
    assert cfg.starting_hp == 100
    assert cfg.pvp_win_gold == 1
    assert (cfg.xp_purchase_gold, cfg.xp_purchase_amount) == (4, 4)
    assert cfg.passive_xp_per_round == 2
    assert cfg.streak_bonus == ((3, 1), (5, 2), (6, 3))
    assert cfg.income_ramp == {"1-1": 0, "1-2": 2, "1-3": 2, "1-4": 3, "2-1": 4}


def test_config_matches_doc_01_shop_odds_and_pool_sizes(data):
    cfg = data.config
    assert cfg.pool_sizes == {1: 30, 2: 25, 3: 18, 4: 10, 5: 9}
    assert cfg.shop_odds_for_level(1) == (1.0, 0.0, 0.0, 0.0, 0.0)
    assert cfg.shop_odds_for_level(7) == (0.19, 0.30, 0.40, 0.10, 0.01)
    assert cfg.shop_odds_for_level(10) == (0.05, 0.10, 0.20, 0.40, 0.25)
    for level in range(1, cfg.max_level + 1):
        row = cfg.shop_odds_for_level(level)
        assert len(row) == len(cfg.pool_sizes)
        assert abs(sum(row) - 1.0) < 1e-9


def test_higher_levels_shift_odds_toward_expensive_units(data):
    """Sanity check on the odds table's shape, not just its row sums."""
    cfg = data.config
    def expected_cost(level: int) -> float:
        return sum((i + 1) * p for i, p in enumerate(cfg.shop_odds_for_level(level)))

    by_level = [expected_cost(lvl) for lvl in range(1, cfg.max_level + 1)]
    assert by_level == sorted(by_level)


def test_board_size_equals_level(data):
    assert data.config.board_size_for_level(8) == 8


def test_unverified_tables_are_flagged(data):
    """Doc 01 sec 9 items must stay visible rather than passing as verified."""
    assert data.config.unverified
    joined = " ".join(data.config.unverified)
    assert "xp_to_next_level" in joined
    assert "stage_base_damage" in joined


# --- schema helpers ------------------------------------------------------


def test_active_breakpoint_returns_highest_tier_met():
    trait = TraitDef(
        id="T",
        display_name="T",
        category="class",
        breakpoints=(
            TraitBreakpoint(2, "a"),
            TraitBreakpoint(4, "b"),
            TraitBreakpoint(6, "c"),
        ),
    )
    assert trait.active_breakpoint(1) is None
    assert trait.active_breakpoint(2).effect_id == "a"
    assert trait.active_breakpoint(3).effect_id == "a"
    assert trait.active_breakpoint(5).effect_id == "b"
    assert trait.active_breakpoint(99).effect_id == "c"


def test_breakpoints_are_sorted_on_load(data_dir):
    edit(
        data_dir / "traits.json",
        lambda raw: [
            {**t, "breakpoints": list(reversed(t["breakpoints"]))} if t["id"] == "DarkStar" else t
            for t in raw
        ],
    )
    trait = load_all(data_dir).traits["DarkStar"]
    assert [bp.count for bp in trait.breakpoints] == [2, 4, 6]


def test_per_star_stat_accessors(data):
    stats = data.champions["TFT17_Jinx"].stats
    assert stats.health_at(1) == 800
    assert stats.health_at(3) == 2592
    assert stats.attack_damage_at(2) == 98
    with pytest.raises(ValueError):
        stats.health_at(0)
    with pytest.raises(ValueError):
        stats.health_at(4)


def test_ability_param_indexes_per_star_lists(data):
    ability = data.champions["TFT17_Jinx"].ability
    assert ability.param_at("damage", 1) == 180
    assert ability.param_at("damage", 3) == 2000
    # Scalars apply to every star level.
    assert ability.param_at("attack_speed_bonus", 1) == 0.75
    assert ability.param_at("attack_speed_bonus", 3) == 0.75
    assert ability.param_at("nonexistent", 1, default=7) == 7


def test_both_cast_modes_are_represented_in_the_sample(data):
    modes = {c.ability.cast_mode for c in data.champions.values() if c.ability}
    assert modes == {"mana", "cooldown"}
    talon = data.champions["TFT17_Talon"].ability
    assert talon.cast_mode == "cooldown" and talon.cooldown_seconds == 6.0


def test_definitions_are_immutable(data):
    champ = data.champions["TFT17_Jinx"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        champ.cost = 1
    with pytest.raises(TypeError):
        champ.ability.params["damage"] = [0, 0, 0]
    with pytest.raises(TypeError):
        data.items["TFT_Item_BFSword"].stats["attack_damage"] = 999


# --- validation failures -------------------------------------------------


def test_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_all(tmp_path)


def test_malformed_json_is_reported(data_dir):
    (data_dir / "items.json").write_text("{not json")
    with pytest.raises(DataValidationError, match="invalid JSON"):
        load_all(data_dir)


def test_unknown_trait_reference_is_rejected(data_dir):
    edit(
        data_dir / "champions.json",
        lambda raw: [
            {**c, "traits": ["NotARealTrait"]} if c["id"] == "TFT17_Jinx" else c
            for c in raw
        ],
    )
    with pytest.raises(DataValidationError, match="unknown trait 'NotARealTrait'"):
        load_all(data_dir)


def test_unknown_recipe_component_is_rejected(data_dir):
    edit(
        data_dir / "items.json",
        lambda raw: [
            {**i, "recipe": ["TFT_Item_BFSword", "TFT_Item_Nope"]}
            if i["id"] == "TFT_Item_Deathblade"
            else i
            for i in raw
        ],
    )
    with pytest.raises(DataValidationError, match="unknown item 'TFT_Item_Nope'"):
        load_all(data_dir)


def test_recipe_of_non_component_is_rejected(data_dir):
    edit(
        data_dir / "items.json",
        lambda raw: [
            {**i, "recipe": ["TFT_Item_BFSword", "TFT_Item_Deathblade"]}
            if i["id"] == "TFT_Item_InfinityEdge"
            else i
            for i in raw
        ],
    )
    with pytest.raises(DataValidationError, match="not a component"):
        load_all(data_dir)


def test_duplicate_recipe_is_rejected(data_dir):
    """Two items from the same pair would make items.combine() ambiguous."""
    edit(
        data_dir / "items.json",
        lambda raw: [
            {**i, "recipe": ["TFT_Item_BFSword", "TFT_Item_BFSword"]}
            if i["id"] == "TFT_Item_InfinityEdge"
            else i
            for i in raw
        ],
    )
    with pytest.raises(DataValidationError, match="produces multiple items"):
        load_all(data_dir)


def test_recipe_must_have_exactly_two_components(data_dir):
    edit(
        data_dir / "items.json",
        lambda raw: [
            {**i, "recipe": ["TFT_Item_BFSword"]} if i["id"] == "TFT_Item_Deathblade" else i
            for i in raw
        ],
    )
    with pytest.raises(DataValidationError, match="exactly 2 components"):
        load_all(data_dir)


def test_invalid_role_is_rejected(data_dir):
    edit(
        data_dir / "champions.json",
        lambda raw: [{**c, "role": "Wizard"} if c["id"] == "TFT17_Lulu" else c for c in raw],
    )
    with pytest.raises(DataValidationError, match="role must be one of"):
        load_all(data_dir)


def test_wrong_length_per_star_stat_is_rejected(data_dir):
    def mutate(raw):
        champ = find(raw, "TFT17_Jinx")
        champ["stats"] = {**champ["stats"], "health": [800, 1440]}
        return raw

    edit(data_dir / "champions.json", mutate)
    with pytest.raises(DataValidationError, match="exactly 3 entries"):
        load_all(data_dir)


def test_scalar_per_star_stat_is_broadcast(data_dir):
    """A champion whose AD does not scale may give a single value (doc 02 sec 2)."""

    def mutate(raw):
        champ = find(raw, "TFT17_Jinx")
        champ["stats"] = {**champ["stats"], "attack_damage": 65}
        return raw

    edit(data_dir / "champions.json", mutate)
    stats = load_all(data_dir).champions["TFT17_Jinx"].stats
    assert stats.attack_damage == (65.0, 65.0, 65.0)


def test_unknown_field_is_rejected(data_dir):
    edit(
        data_dir / "champions.json",
        lambda raw: [{**c, "hp": 999} if c["id"] == "TFT17_Ornn" else c for c in raw],
    )
    with pytest.raises(DataValidationError, match="unknown field 'hp'"):
        load_all(data_dir)


def test_missing_required_field_is_rejected(data_dir):
    def mutate(raw):
        champ = find(raw, "TFT17_Ornn")
        del champ["cost"]
        return raw

    edit(data_dir / "champions.json", mutate)
    with pytest.raises(DataValidationError, match="missing required field 'cost'"):
        load_all(data_dir)


def test_unknown_item_stat_key_is_rejected(data_dir):
    edit(
        data_dir / "items.json",
        lambda raw: [
            {**i, "stats": {"attack_dmg": 55}} if i["id"] == "TFT_Item_Deathblade" else i
            for i in raw
        ],
    )
    with pytest.raises(DataValidationError, match="unknown stat key 'attack_dmg'"):
        load_all(data_dir)


def test_duplicate_id_is_rejected(data_dir):
    edit(data_dir / "champions.json", lambda raw: raw + [find(raw, "TFT17_Jinx")])
    with pytest.raises(DataValidationError, match="duplicate id"):
        load_all(data_dir)


def test_cooldown_ability_without_cooldown_is_rejected(data_dir):
    def mutate(raw):
        champ = find(raw, "TFT17_Talon")
        champ["ability"] = {**champ["ability"], "cooldown_seconds": None}
        return raw

    edit(data_dir / "champions.json", mutate)
    with pytest.raises(DataValidationError, match="cooldown_seconds must be a positive"):
        load_all(data_dir)


def test_mana_ability_with_cooldown_is_rejected(data_dir):
    def mutate(raw):
        champ = find(raw, "TFT17_Jinx")
        champ["ability"] = {**champ["ability"], "cooldown_seconds": 5.0}
        return raw

    edit(data_dir / "champions.json", mutate)
    with pytest.raises(DataValidationError, match="must be null when cast_mode is 'mana'"):
        load_all(data_dir)


def test_starting_mana_above_max_is_rejected(data_dir):
    def mutate(raw):
        champ = find(raw, "TFT17_Jinx")
        champ["stats"] = {**champ["stats"], "starting_mana": 500}
        return raw

    edit(data_dir / "champions.json", mutate)
    with pytest.raises(DataValidationError, match="exceeds max_mana"):
        load_all(data_dir)


def test_shop_odds_row_must_sum_to_one(data_dir):
    def mutate(raw):
        raw["shop_odds"]["5"] = [0.5, 0.3, 0.2, 0.2, 0.0]
        return raw

    edit(data_dir / "config.json", mutate)
    with pytest.raises(DataValidationError, match="must sum to 1.0"):
        load_all(data_dir)


def test_shop_odds_must_cover_every_level(data_dir):
    def mutate(raw):
        del raw["shop_odds"]["9"]
        return raw

    edit(data_dir / "config.json", mutate)
    with pytest.raises(DataValidationError, match=r"missing rows for level\(s\) \[9\]"):
        load_all(data_dir)


def test_champion_cost_without_a_pool_size_is_rejected(data_dir):
    edit(
        data_dir / "champions.json",
        lambda raw: [{**c, "cost": 6} if c["id"] == "TFT17_Ornn" else c for c in raw],
    )
    with pytest.raises(DataValidationError, match="no pool size configured"):
        load_all(data_dir)


def test_rollable_tier_with_no_champions_is_rejected(data_dir):
    """Shop odds that can roll a tier the dataset cannot fill would hang draws."""
    edit(
        data_dir / "champions.json",
        lambda raw: [c for c in raw if c["cost"] != 5],
    )
    with pytest.raises(DataValidationError, match="no champion has that cost"):
        load_all(data_dir)


def test_all_problems_are_reported_together(data_dir):
    """One bad file should not mask the rest -- the whole list surfaces at once."""
    edit(
        data_dir / "champions.json",
        lambda raw: [
            {**c, "role": "Wizard"} if c["id"] == "TFT17_Lulu"
            else {**c, "traits": ["Nope"]} if c["id"] == "TFT17_Jinx"
            else c
            for c in raw
        ],
    )
    edit(
        data_dir / "items.json",
        lambda raw: [
            {**i, "stats": {"bogus": 1}} if i["id"] == "TFT_Item_Deathblade" else i
            for i in raw
        ],
    )
    with pytest.raises(DataValidationError) as exc:
        load_all(data_dir)
    joined = " ".join(exc.value.problems)
    assert "Wizard" in joined
    assert "Nope" in joined
    assert "bogus" in joined
    assert len(exc.value.problems) >= 3


def test_item_params_without_an_effect_id_are_rejected(data_dir):
    """params with no effect to read them is a data mistake, not a no-op."""
    edit(
        data_dir / "items.json",
        lambda raw: [
            {**i, "params": {"reflect": 10}} if i["id"] == "TFT_Item_Deathblade" else i
            for i in raw
        ],
    )
    with pytest.raises(DataValidationError, match="nothing would read them"):
        load_all(data_dir)


def test_items_without_params_default_to_empty(data):
    assert data.items["TFT_Item_Deathblade"].params == {}
    assert dict(data.items["TFT_Item_Deathblade"].effect_values) == {"attack_damage": 55.0}


def test_radiant_item_must_point_at_its_base(data_dir):
    edit(
        data_dir / "items.json",
        lambda raw: [
            {**i, "radiant_version_of": None} if i["id"] == "TFT_Item_ZenithEdge" else i
            for i in raw
        ],
    )
    with pytest.raises(DataValidationError, match="must set radiant_version_of"):
        load_all(data_dir)


def test_component_flag_must_match_category(data_dir):
    edit(
        data_dir / "items.json",
        lambda raw: [
            {**i, "is_component": True} if i["id"] == "TFT_Item_Deathblade" else i
            for i in raw
        ],
    )
    with pytest.raises(DataValidationError, match="contradicts category"):
        load_all(data_dir)
