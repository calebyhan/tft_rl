"""The fetcher on a Set 18-shaped payload (doc 99 entries 161.2, 161.12).

Set 18's payload keeps Set 17's layout but not its content: roles are null,
ability variables are empty, and every live item is a `DA_*` entry with no
effects that sits beside a stale `TFT_Item_*` twin (161.2, 161.5). These pin
how an overlay fills those gaps without letting it overrule anything CDragon
does ship.
"""

from __future__ import annotations

import json

from scripts import fetch_cdragon as fetch
from tests.paths import STARTER_DATA_DIR

ROLE_MANA = json.loads((STARTER_DATA_DIR / "config.json").read_text())["role_mana_per_attack"]


def _unit(api, traits, *, role=None, variables=(), desc="Deal magic damage."):
    return {
        "apiName": api, "name": api.split("_")[-1], "cost": 1, "role": role,
        "traits": list(traits),
        "stats": {"hp": 700.0, "armor": 40.0, "magicResist": 40.0, "damage": 40.0,
                  "attackSpeed": 0.6, "range": 1.0, "initialMana": 30.0, "mana": 90.0,
                  "critChance": 0.25, "critMultiplier": 1.4},
        "ability": {"name": "Ability", "desc": desc, "variables": list(variables)},
    }


def _item(api, name, *, recipe=(), effects=None, tags=()):
    return {"apiName": api, "name": name, "tags": list(tags), "composition": list(recipe),
            "unique": False, "effects": effects or {}, "associatedTraits": []}


def _payload():
    items = [
        # Legacy twins: numbers, but not the ids live games use (161.5).
        _item("TFT_Item_BFSword", "B.F. Sword", effects={"AD": 0.1}, tags=["component"]),
        _item("TFT_Item_Spatula", "Spatula", tags=["component"]),
        _item("TFT_Item_Deathblade", "Deathblade", recipe=["TFT_Item_BFSword"] * 2,
              effects={"AD": 0.55}),
        # The live ids: right recipes, empty effects.
        _item("DA_Component_BFSword", "B.F. Sword", tags=["component"]),
        _item("DA_Component_Spatula", "Spatula", tags=["component"]),
        _item("DA_Deathblade", "Deathblade", recipe=["DA_Component_BFSword"] * 2),
        _item("DA_Bloodthirster", "Bloodthirster", recipe=["DA_Component_BFSword"] * 2),
        _item("DA_Mystery", "Mystery", recipe=["DA_Component_BFSword", "DA_Component_Spatula"]),
        _item("DA_18_EmblemHunter", "Hunter Emblem",
              recipe=["DA_Component_Spatula", "DA_Component_BFSword"]),
    ]
    return {
        "items": items,
        "setData": [{
            "mutator": "TFTSet18", "number": 18,
            "champions": [
                _unit("DA_18_Warwick", ["Hunter"]),
                _unit("DA_18_Kobuko", ["Hunter"], role="APTank",
                      variables=[{"name": "Heal", "value": [0, 350, 400, 475, 0, 0, 0]}]),
            ],
            "traits": [{"apiName": "DA_18_Hunter", "name": "Hunter",
                        "effects": [{"minUnits": 2, "variables": {}}]}],
            "items": [i["apiName"] for i in items],
        }],
    }


def _teamplanner():
    hunter = [{"name": "Hunter", "id": "DA_18_Hunter"}]
    return {"TFTSet18": [
        {"character_id": "DA_18_Warwick", "tier": 2, "traits": hunter},
        {"character_id": "DA_18_Kobuko", "tier": 1, "traits": hunter},
    ]}


OVERLAY = {
    "champions": {
        "DA_18_Warwick": {"role": "APTank", "variables": {
            "Damage": {"stars": [230.0, 345.0, 535.0], "scales": ["Attack damage"],
                       "source": "notes 18.3"},
            "Minimum Heal": {"stars": [0.25, 0.25, 0.25], "scales": [], "source": "both"},
        }},
        "DA_18_Kobuko": {"role": "ADCarry", "variables": {
            "Heal": {"stars": [1.0, 2.0, 3.0], "scales": [], "source": "both"},
        }},
    },
    "traits": {"da_18_hunter": {"category": "class", "tiers": {}}},
    "items": {"DA_Bloodthirster": {"effects": {"AD": 0.18, "MagicResist": 20.0}, "desc": ""}},
}


def _build(**kwargs):
    return fetch.build_dataset(_payload(), _teamplanner(), 18, ROLE_MANA, **kwargs)


def _by_id(rows):
    return {r["id"]: r for r in rows}


def test_overlay_fills_a_null_role():
    """Tank, which the range fallback (melee -> Fighter) cannot produce.

    Mutation-found: with a Fighter overlay role, ignoring the overlay passed.
    """
    data = _build(overlay=OVERLAY)
    warwick = _by_id(data["champions"])["DA_18_Warwick"]
    assert warwick["role"] == "Tank"
    assert warwick["stats"]["mana_per_attack"] == ROLE_MANA["Tank"]


def test_a_role_cdragon_ships_is_not_overruled():
    kobuko = _by_id(_build(overlay=OVERLAY)["champions"])["DA_18_Kobuko"]
    assert kobuko["role"] == "Tank"


def test_overlay_fills_empty_ability_variables_under_compact_names():
    params = _by_id(_build(overlay=OVERLAY)["champions"])["DA_18_Warwick"]["ability"]["params"]
    assert params["Damage"] == [230.0, 345.0, 535.0]
    assert params["MinimumHeal"] == 0.25


def test_a_variable_cdragon_ships_is_not_overruled():
    params = _by_id(_build(overlay=OVERLAY)["champions"])["DA_18_Kobuko"]["ability"]["params"]
    assert params["Heal"] == [350.0, 400.0, 475.0]


def test_overlay_sets_the_trait_category():
    assert _build(overlay=OVERLAY)["traits"][0]["category"] == "class"
    assert _build()["traits"][0]["category"] == "origin"


def test_item_prefix_keeps_only_the_live_ids():
    items = _by_id(_build(overlay=OVERLAY, item_prefix="DA_")["items"])
    assert all(i.startswith("DA_") for i in items)
    assert items["DA_Deathblade"]["recipe"] == ["DA_Component_BFSword"] * 2
    assert items["DA_18_EmblemHunter"]["effect_id"] == "emblem_DA_18_Hunter"


def test_live_item_stats_come_from_the_overlay_first():
    items = _by_id(_build(overlay=OVERLAY, item_prefix="DA_")["items"])
    assert items["DA_Bloodthirster"]["stats"]["attack_damage_pct"] == 0.18
    assert items["DA_Bloodthirster"]["stats"]["magic_resist"] == 20.0


def test_live_item_falls_back_to_its_same_named_legacy_twin():
    """161.11: legacy base stats equal the live ones on every unchanged item."""
    items = _by_id(_build(overlay=OVERLAY, item_prefix="DA_")["items"])
    assert items["DA_Deathblade"]["stats"]["attack_damage_pct"] == 0.55
    assert items["DA_Component_BFSword"]["stats"]["attack_damage_pct"] == 0.1


def test_live_item_with_no_source_is_an_explicit_no_effect():
    items = _by_id(_build(overlay=OVERLAY, item_prefix="DA_")["items"])
    assert items["DA_Mystery"]["stats"] == {}
    assert items["DA_Mystery"]["effect_id"] == "no_effect"


def test_fetching_into_an_empty_directory_reads_the_repo_config(tmp_path):
    """161.2: `main()` read config.json from `--out`, so a fresh directory failed."""
    source, planner, out = tmp_path / "p.json", tmp_path / "tp.json", tmp_path / "out"
    source.write_text(json.dumps(_payload()))
    planner.write_text(json.dumps(_teamplanner()))
    out.mkdir()
    code = fetch.main(["--set", "18", "--source", str(source), "--teamplanner", str(planner),
                       "--out", str(out), "--config", str(STARTER_DATA_DIR / "config.json")])
    assert code == 0
    assert not (out / "config.json").exists(), "the fetcher must never write a config"
    assert json.loads((out / "VERSION.json").read_text())["set"] == 18


def test_twin_names_match_across_case_and_punctuation():
    """Real payload: `Tear Of The Goddess` (DA_) beside `Tear of the Goddess`."""
    payload = _payload()
    live = next(i for i in payload["items"] if i["apiName"] == "DA_Component_BFSword")
    live["name"] = "B.F. SWORD"
    items = _by_id(fetch.build_dataset(payload, _teamplanner(), 18, ROLE_MANA,
                                       overlay=OVERLAY, item_prefix="DA_")["items"])
    assert items["DA_Component_BFSword"]["stats"]["attack_damage_pct"] == 0.1


def test_a_category_outside_the_schema_falls_back():
    """tftraits labels one-unit traits `unique`; the schema knows class/origin.

    Found by loading the first real build: five champions lost a trait to it.
    """
    overlay = {**OVERLAY, "traits": {"da_18_hunter": {"category": "unique", "tiers": {}}}}
    assert _build(overlay=overlay)["traits"][0]["category"] == "origin"


def test_an_overlay_item_keeps_its_twins_passive_so_the_gap_is_named():
    """Found on the first real build: 36 of 39 live items came out `no_effect`.

    tactics.tools gives the stat line but not the passive's parameters, so an
    overlay-only item read as having nothing to model -- silently inert. Stats
    now come from the overlay (current) and the passive's parameters from the
    twin, and the behaviour id is the twin's, which is what the engine's hook
    is registered under (item 4a of 161.7).
    """
    payload = _payload()
    payload["items"].append(_item("TFT_Item_Bloodthirster", "Bloodthirster",
                                  effects={"AD": 0.15, "HealthThreshold": 40.0}))
    payload["setData"][0]["items"].append("TFT_Item_Bloodthirster")
    items = _by_id(fetch.build_dataset(payload, _teamplanner(), 18, ROLE_MANA,
                                       overlay=OVERLAY, item_prefix="DA_")["items"])
    bt = items["DA_Bloodthirster"]
    assert bt["stats"]["attack_damage_pct"] == 0.18, "the overlay's current stat must win"
    assert bt["params"] == {"HealthThreshold": 40.0}
    assert bt["effect_id"] == "item_TFT_Item_Bloodthirster"


def test_an_overlay_passive_value_overrules_the_twins():
    """The twins are pre-18.2: Bloodthirster's threshold moved 40% => 50%."""
    payload = _payload()
    payload["items"].append(_item("TFT_Item_Bloodthirster", "Bloodthirster",
                                  effects={"AD": 0.15, "HealthThreshold": 40.0,
                                           "ShieldDuration": 5.0}))
    payload["setData"][0]["items"].append("TFT_Item_Bloodthirster")
    overlay = {**OVERLAY, "items": {"DA_Bloodthirster": {
        "effects": {"AD": 0.18, "HealthThreshold": 50.0}}}}
    items = _by_id(fetch.build_dataset(payload, _teamplanner(), 18, ROLE_MANA,
                                       overlay=overlay, item_prefix="DA_")["items"])
    assert items["DA_Bloodthirster"]["params"] == {"HealthThreshold": 50.0, "ShieldDuration": 5.0}


def test_a_twins_known_behaviour_carries_to_the_live_id():
    """Infinity Edge's behaviour is a keyword known by its *legacy* id and has
    no leftover parameters, so the live id normalised to `no_effect` (161.12)."""
    payload = _payload()
    payload["items"] += [
        _item("TFT_Item_InfinityEdge", "Infinity Edge", effects={"AD": 0.35}),
        _item("DA_InfinityEdge", "Infinity Edge", recipe=["DA_Component_BFSword"] * 2),
        _item("TFT_Item_SpearOfShojin", "Spear of Shojin", effects={"AP": 20.0}),
        _item("DA_SpearOfShojin", "Spear of Shojin", recipe=["DA_Component_BFSword"] * 2),
    ]
    payload["setData"][0]["items"] += ["TFT_Item_InfinityEdge", "DA_InfinityEdge",
                                       "TFT_Item_SpearOfShojin", "DA_SpearOfShojin"]
    items = _by_id(fetch.build_dataset(payload, _teamplanner(), 18, ROLE_MANA,
                                       overlay=OVERLAY, item_prefix="DA_")["items"])
    assert items["DA_InfinityEdge"]["effect_id"] == "item_TFT_Item_InfinityEdge"
    # A behaviour registered by *name* keeps that name: the hook is not id-keyed.
    assert items["DA_SpearOfShojin"]["effect_id"] == "spear_of_shojin_bonus_mana_on_attack"


def test_an_emblem_takes_its_stats_from_the_overlay_by_display_name():
    """Set 18 emblems carry stats (161.11); the live `DA_` entry ships none."""
    overlay = {**OVERLAY, "emblems": {"Hunter Emblem": {"effects": {"AD": 0.25}}}}
    items = _by_id(_build(overlay=overlay, item_prefix="DA_")["items"])
    emblem = items["DA_18_EmblemHunter"]
    assert emblem["stats"] == {"attack_damage_pct": 0.25}
    assert emblem["effect_id"] == "emblem_DA_18_Hunter"


def test_an_emblem_keeps_its_passive_parameters():
    """Set 18 emblems grant a passive beyond the trait (161.14); its numbers
    were dropped because Set 17 emblems never had any."""
    overlay = {**OVERLAY, "emblems": {"Hunter Emblem": {
        "effects": {"AD": 0.25, "TakedownAD": 0.15}}}}
    emblem = _by_id(_build(overlay=overlay, item_prefix="DA_")["items"])["DA_18_EmblemHunter"]
    assert emblem["stats"] == {"attack_damage_pct": 0.25}
    assert emblem["params"] == {"TakedownAD": 0.15}
    assert emblem["effect_id"] == "emblem_DA_18_Hunter"


# --- hashed variable names (doc 99 entry 161.15) ------------------------------


def _hunter(desc, variables, set_number=18):
    payload = _payload()
    payload["setData"][0]["traits"] = [{
        "apiName": "DA_18_Hunter", "name": "Hunter", "desc": desc,
        "effects": [{"minUnits": 2, "variables": variables}],
    }]
    payload["setData"][0].update(mutator=f"TFTSet{set_number}", number=set_number)
    teamplanner = {f"TFTSet{set_number}": _teamplanner()["TFTSet18"]}
    return fetch.build_dataset(payload, teamplanner, set_number, ROLE_MANA)["traits"][0]


def test_a_hashed_trait_variable_gets_the_name_its_description_prints():
    """Riot's `{xxxxxxxx}` is FNV-1a of the lower-cased name, and the name is
    in the trait's own text: `{641254b6}` is `@HunterAD*100@`."""
    trait = _hunter("Hunters gain <row>@HunterAD*100@% AD</row> for @HunterDuration@s",
                    {"{641254b6}": 0.2, "{83011ee7}": 3.0, "DamageAmp": 0.1})
    assert trait["breakpoints"][0]["params"] == {
        "HunterAD": 0.2, "HunterDuration": 3.0, "DamageAmp": 0.1}


def test_a_hash_no_printed_name_explains_is_kept():
    trait = _hunter("Hunters gain AD.", {"{641254b6}": 0.2})
    assert trait["breakpoints"][0]["params"] == {"{641254b6}": 0.2}


def test_set_17_keeps_its_hashes_because_its_hooks_read_them():
    """Voyager reads `{2ad3e251}`; renaming on a Set 17 refetch would break it."""
    trait = _hunter("@HunterAD@", {"{641254b6}": 0.2}, set_number=17)
    assert trait["breakpoints"][0]["params"] == {"{641254b6}": 0.2}


def _trait(effects, set_number=18):
    payload = _payload()
    payload["setData"][0]["traits"] = [{"apiName": "DA_18_Hunter", "name": "Hunter",
                                       "desc": "", "effects": effects}]
    payload["setData"][0].update(mutator=f"TFTSet{set_number}", number=set_number)
    teamplanner = {f"TFTSet{set_number}": _teamplanner()["TFTSet18"]}
    return fetch.build_dataset(payload, teamplanner, set_number, ROLE_MANA)["traits"][0]


def test_a_set_18_breakpoint_inherits_the_variables_it_does_not_restate():
    """Executioner's 3-unit tier ships only its bleed; its text says the crit
    carries on ("Additionally"). Only the highest tier's params apply, so
    without inheritance a 3-Executioner board lost its crit (161.15)."""
    trait = _trait([
        {"minUnits": 2, "variables": {"CritChance": 0.15}},
        {"minUnits": 3, "variables": {"BleedDuration": 3.0, "BonusBleedPercent": 0.3}},
        {"minUnits": 4, "variables": {"BonusBleedPercent": 0.4}},
    ])
    assert [b["params"] for b in trait["breakpoints"]] == [
        {"CritChance": 0.15},
        {"CritChance": 0.15, "BleedDuration": 3.0, "BonusBleedPercent": 0.3},
        {"CritChance": 0.15, "BleedDuration": 3.0, "BonusBleedPercent": 0.4},
    ]


def test_set_17_breakpoints_are_left_as_shipped():
    trait = _trait([{"minUnits": 2, "variables": {"A": 1.0}},
                    {"minUnits": 3, "variables": {"B": 2.0}}], set_number=17)
    assert [b["params"] for b in trait["breakpoints"]] == [{"A": 1.0}, {"B": 2.0}]


def _hunter_with_deltas(deltas, caplog=None):
    payload = _payload()
    payload["setData"][0]["traits"] = [{"apiName": "DA_18_Hunter", "name": "Hunter", "desc": "",
        "effects": [{"minUnits": 2, "variables": {"HunterAD": 0.2, "Duration": 3.0}},
                    {"minUnits": 4, "variables": {"HunterAD": 0.45}},
                    {"minUnits": 5, "variables": {}}]}]
    overlay = {**OVERLAY, "traits": {"da_18_hunter": {"category": "class", "deltas": deltas}}}
    return fetch.build_dataset(payload, _teamplanner(), 18, ROLE_MANA, overlay=overlay)["traits"][0]


def test_an_overlay_trait_delta_lands_before_inheritance():
    """CDragon's trait numbers are a mixed, older snapshot (161.15); the notes win,
    and a tier above inherits the corrected value, not the stale one."""
    trait = _hunter_with_deltas([{"count": 4, "key": "HunterAD", "old": 0.45, "new": 0.40,
                                  "source": "notes 18.3"}])
    assert [b["params"]["HunterAD"] for b in trait["breakpoints"]] == [0.2, 0.40, 0.40]


def test_a_trait_delta_whose_old_value_cdragon_does_not_have_is_refused(caplog):
    trait = _hunter_with_deltas([{"count": 4, "key": "HunterAD", "old": 0.5, "new": 0.40,
                                  "source": "notes 18.3"}])
    assert trait["breakpoints"][1]["params"]["HunterAD"] == 0.45
    assert "HunterAD" in caplog.text
