"""Unit tests for the CDragon normaliser (milestone 8, doc 02 sec 1.1).

These drive the pure ``normalise_*`` functions from a small synthetic payload
shaped like Riot's real one, so they run without network access. Each case
below encodes something that was discovered empirically from the live Set 17
payload -- the comments say which, because Riot's shape is undocumented and a
future patch changing it is exactly what these tests exist to catch.
"""

from __future__ import annotations

import json

import pytest

from scripts.fetch_cdragon import (
    ROLE_MAP,
    STAR_ATTACK_DAMAGE_MULTIPLIER,
    STAR_HEALTH_MULTIPLIER,
    FetchError,
    _ability_params,
    _split_item_effects,
    build_dataset,
    normalise_champion,
    normalise_trait,
    playable_champion_ids,
    select_set,
    trait_name_to_id,
)
from tests.paths import STARTER_DATA_DIR

ROLE_MANA = json.loads((STARTER_DATA_DIR / "config.json").read_text())["role_mana_per_attack"]


def _champion(api_name="TFT17_Jinx", **overrides):
    entry = {
        "apiName": api_name,
        "name": "Jinx",
        "cost": 2,
        "role": "ADCarry",
        "traits": ["Anima", "Challenger"],
        "stats": {
            "hp": 550.0, "armor": 20.0, "magicResist": 20.0, "damage": 55.0,
            "attackSpeed": 0.75, "range": 4.0, "initialMana": 20.0,
            "mana": 80.0, "critChance": 0.25, "critMultiplier": 1.4,
        },
        "ability": {
            "name": "Explosive Attitude",
            "variables": [
                {"name": "ADDamage", "value": [3.0, 29.0, 44.0, 70.0, 110.0, 3.0, 3.0]},
                {"name": "Flat", "value": [1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0]},
            ],
        },
    }
    entry.update(overrides)
    return entry


TRAIT_IDS = {"Anima": "TFT17_AnimaSquad", "Challenger": "TFT17_ASTrait"}


# --------------------------------------------------------------------------
# Ability variables
# --------------------------------------------------------------------------


def test_ability_variables_use_indices_one_through_three():
    """Stars 1-3 live at indices 1..3; 0 is a placeholder and 4+ is padding.

    Verified against the live payload: Jinx's ADDamage is
    [3, 29, 44, 70, 110, 3, 3] and the real per-star values are 29/44/70.
    """
    params = _ability_params(
        [{"name": "ADDamage", "value": [3.0, 29.0, 44.0, 70.0, 110.0, 3.0, 3.0]}]
    )
    assert params["ADDamage"] == [29.0, 44.0, 70.0]


def test_non_scaling_ability_variable_collapses_to_a_scalar():
    params = _ability_params([{"name": "Flat", "value": [1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0]}])
    assert params["Flat"] == 2.0


def test_ability_variable_with_null_star_values_is_dropped():
    params = _ability_params([{"name": "X", "value": [1.0, None, 2.0, 3.0, 4.0, 0.0, 0.0]}])
    assert "X" not in params


def test_short_ability_variable_array_is_ignored():
    """A future shape change must not raise -- it should degrade to no params."""
    assert _ability_params([{"name": "X", "value": [1.0, 2.0]}]) == {}


# --------------------------------------------------------------------------
# Champions
# --------------------------------------------------------------------------


def test_star_scaling_uses_the_documented_multipliers():
    """Riot ships one scalar; per-star arrays are derived (wiki: HP 1.8, AD 1.5)."""
    champ = normalise_champion(
        _champion(), cost=2, trait_ids=TRAIT_IDS, role_mana=ROLE_MANA
    )
    hp = champ["stats"]["health"]
    ad = champ["stats"]["attack_damage"]
    assert hp[0] == 550.0
    assert hp[1] == pytest.approx(550.0 * STAR_HEALTH_MULTIPLIER)
    assert hp[2] == pytest.approx(550.0 * STAR_HEALTH_MULTIPLIER**2)
    assert ad[1] == pytest.approx(55.0 * STAR_ATTACK_DAMAGE_MULTIPLIER)


def test_traits_are_mapped_from_display_name_to_api_id():
    champ = normalise_champion(
        _champion(), cost=2, trait_ids=TRAIT_IDS, role_mana=ROLE_MANA
    )
    assert champ["traits"] == ["TFT17_AnimaSquad", "TFT17_ASTrait"]


def test_role_maps_to_our_taxonomy_and_drives_mana_per_attack():
    champ = normalise_champion(
        _champion(), cost=2, trait_ids=TRAIT_IDS, role_mana=ROLE_MANA
    )
    assert champ["role"] == "Marksman"
    assert champ["stats"]["mana_per_attack"] == ROLE_MANA["Marksman"]


@pytest.mark.parametrize("riot_role", sorted(ROLE_MAP))
def test_every_known_riot_role_maps_to_a_role_with_mana(riot_role):
    """A role we cannot map would crash on the role_mana lookup."""
    champ = normalise_champion(
        _champion(role=riot_role), cost=2, trait_ids=TRAIT_IDS, role_mana=ROLE_MANA
    )
    assert champ["stats"]["mana_per_attack"] == ROLE_MANA[champ["role"]]


def test_null_role_falls_back_on_attack_range():
    """Set 17's Miss Fortune ships role: null."""
    melee = normalise_champion(
        _champion(role=None, stats={**_champion()["stats"], "range": 1.0}),
        cost=2, trait_ids=TRAIT_IDS, role_mana=ROLE_MANA,
    )
    ranged = normalise_champion(
        _champion(role=None), cost=2, trait_ids=TRAIT_IDS, role_mana=ROLE_MANA
    )
    assert melee["role"] == "Fighter"
    assert ranged["role"] == "Caster"


def test_null_stats_do_not_crash():
    """Miss Fortune ships an explicit null damage, so .get(k, default) is not enough."""
    champ = normalise_champion(
        _champion(stats={**_champion()["stats"], "damage": None, "hp": None}),
        cost=2, trait_ids=TRAIT_IDS, role_mana=ROLE_MANA,
    )
    assert all(v > 0 for v in champ["stats"]["attack_damage"])
    assert all(v > 0 for v in champ["stats"]["health"])


def test_zero_max_mana_falls_back_to_a_positive_pool():
    """Set 17's Caitlyn ships mana 0, which the schema rejects."""
    champ = normalise_champion(
        _champion(stats={**_champion()["stats"], "mana": 0.0}),
        cost=2, trait_ids=TRAIT_IDS, role_mana=ROLE_MANA,
    )
    assert champ["stats"]["max_mana"] == 100.0


def test_unknown_trait_reference_is_dropped_not_fatal():
    champ = normalise_champion(
        _champion(traits=["Anima", "NoSuchTrait"]),
        cost=2, trait_ids=TRAIT_IDS, role_mana=ROLE_MANA,
    )
    assert champ["traits"] == ["TFT17_AnimaSquad"]


# --------------------------------------------------------------------------
# Traits
# --------------------------------------------------------------------------


def test_trait_breakpoints_come_from_min_units_and_are_sorted():
    trait = normalise_trait(
        {
            "apiName": "TFT17_ASTrait",
            "name": "Challenger",
            "effects": [
                {"minUnits": 4, "variables": {"AS": 0.5}},
                {"minUnits": 2, "variables": {"AS": 0.25, "Unused": None}},
            ],
        }
    )
    assert [b["count"] for b in trait["breakpoints"]] == [2, 4]
    assert trait["breakpoints"][0]["params"] == {"AS": 0.25}
    assert trait["category"] == "class"


def test_trait_category_defaults_to_origin():
    trait = normalise_trait(
        {"apiName": "TFT17_AnimaSquad", "name": "Anima",
         "effects": [{"minUnits": 2, "variables": {}}]}
    )
    assert trait["category"] == "origin"


def test_placeholder_trait_yields_no_breakpoints():
    """Set 17's 'Choose Trait' marker has an empty effects list."""
    trait = normalise_trait({"apiName": "TFT17_X", "name": "Choose Trait", "effects": []})
    assert trait["breakpoints"] == []


# --------------------------------------------------------------------------
# Items
# --------------------------------------------------------------------------


def test_item_effects_split_into_stats_and_leftovers_with_correct_units():
    """Riot mixes units: AD is a fraction, AS and CritChance are percentages."""
    stats, leftovers = _split_item_effects(
        {"AD": 0.35, "AS": 20.0, "CritChance": 35.0, "Health": 150.0,
         "SomeProcChance": 0.5, "Nulled": None}
    )
    assert stats["attack_damage_pct"] == pytest.approx(0.35)
    assert stats["attack_speed_pct"] == pytest.approx(0.20)
    assert stats["crit_chance"] == pytest.approx(0.35)
    assert stats["health"] == pytest.approx(150.0)
    assert leftovers == {"SomeProcChance": 0.5}


def test_unmapped_effect_keys_never_become_stats():
    """Guessing an unknown key's units would silently corrupt derived stats."""
    stats, leftovers = _split_item_effects({"ManaRegen": 1.0, "{fe9818ef}": 5.0})
    assert stats == {}
    assert set(leftovers) == {"ManaRegen", "{fe9818ef}"}


# --------------------------------------------------------------------------
# Payload selection
# --------------------------------------------------------------------------


def _payload():
    return {
        "items": [
            {"apiName": "TFT_Item_BFSword", "name": "B.F. Sword", "tags": ["component"],
             "composition": [], "unique": False, "effects": {"AD": 0.1}},
            {"apiName": "TFT_Item_Spatula", "name": "Spatula", "tags": ["component"],
             "composition": [], "unique": False, "effects": {}},
            {"apiName": "TFT_Item_Deathblade", "name": "Deathblade", "tags": [],
             "composition": ["TFT_Item_BFSword", "TFT_Item_BFSword"],
             "unique": False, "effects": {"AD": 0.55}},
            {"apiName": "TFT17_Item_FavoredEmblemItem", "name": "Arbiter Emblem",
             "tags": [], "composition": ["TFT_Item_Spatula", "TFT_Item_BFSword"],
             "unique": True, "effects": {"Armor": 10.0}, "associatedTraits": []},
        ],
        "setData": [
            {"mutator": "TFTSet17_PVEMODE", "number": 17, "champions": [], "traits": []},
            {
                "mutator": "TFTSet17", "number": 17,
                "champions": [
                    _champion(),
                    _champion("TFT17_Enemy_Aatrox", name="Apex Primordian", traits=[]),
                ],
                "traits": [
                    {"apiName": "TFT17_AnimaSquad", "name": "Anima",
                     "effects": [{"minUnits": 2, "variables": {}}]},
                    {"apiName": "TFT17_ASTrait", "name": "Challenger",
                     "effects": [{"minUnits": 2, "variables": {}}]},
                    {"apiName": "TFT17_ADMIN", "name": "Arbiter",
                     "effects": [{"minUnits": 2, "variables": {}}]},
                    {"apiName": "TFT17_Dead", "name": "Choose Trait", "effects": []},
                ],
                "items": ["TFT_Item_BFSword", "TFT_Item_Spatula",
                          "TFT_Item_Deathblade", "TFT17_Item_FavoredEmblemItem"],
            },
        ],
    }


def _teamplanner():
    return {
        "TFTSet17": [
            {"character_id": "TFT17_Jinx", "tier": 2, "traits": [
                {"name": "Anima", "id": "TFT17_AnimaSquad"},
                {"name": "Challenger", "id": "TFT17_ASTrait"},
                {"name": "Arbiter", "id": "TFT17_ADMIN"},
            ]},
            {"character_id": "TFT17_Enemy_Aatrox", "tier": 5, "traits": []},
        ]
    }


def test_select_set_prefers_the_base_mutator_over_game_mode_variants():
    entry = select_set(_payload(), 17)
    assert entry["mutator"] == "TFTSet17"


def test_select_set_reports_available_mutators_when_missing():
    with pytest.raises(FetchError, match="TFTSet99"):
        select_set(_payload(), 99)


def test_playable_ids_and_trait_map_come_from_the_team_planner():
    assert playable_champion_ids(_teamplanner(), 17)["TFT17_Jinx"] == 2
    assert trait_name_to_id(_teamplanner(), 17)["Arbiter"] == "TFT17_ADMIN"


def test_build_dataset_filters_pve_units_and_placeholder_traits():
    data = build_dataset(_payload(), _teamplanner(), 17, ROLE_MANA)
    assert [c["id"] for c in data["champions"]] == ["TFT17_Jinx"]
    # Arbiter is unused by any shop unit's trait list, Choose Trait has no
    # breakpoints; both must be pruned.
    assert {t["id"] for t in data["traits"]} == {"TFT17_AnimaSquad", "TFT17_ASTrait"}


def test_emblem_resolves_its_trait_by_display_name():
    """FavoredEmblemItem is the *Arbiter* emblem -- the apiName does not say so."""
    data = build_dataset(_payload(), _teamplanner(), 17, ROLE_MANA)
    emblem = next(i for i in data["items"] if i["category"] == "emblem")
    assert emblem["effect_id"] == "emblem_TFT17_ADMIN"


def test_item_without_modelled_stats_gets_an_explicit_no_effect():
    """Otherwise the loader rejects it as granting neither stats nor an effect."""
    data = build_dataset(_payload(), _teamplanner(), 17, ROLE_MANA)
    spatula = next(i for i in data["items"] if i["id"] == "TFT_Item_Spatula")
    assert spatula["effect_id"] == "no_effect"
    assert spatula["is_component"] is True
