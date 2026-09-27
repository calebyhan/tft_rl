"""The Set 18 magnitude overlay (doc 99 entry 161.12).

CommunityDragon ships Set 18's roster and ids but not its magnitudes (161.2),
so they come from three sources that each miss something (161.10, 161.11):
tftraits' 18.3 tooltip text, tactics.tools' 18.2 named variables, and the
official 18.3/18.3b notes. The parsers are driven from trimmed copies of the
real pages in `tests/fixtures/set18_sources/`; the reconciliation is pinned on
the four cases the prototype run actually met.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import build_set18_overlay as overlay  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "set18_sources"


@pytest.fixture(scope="module")
def tftraits():
    return (FIXTURES / "tftraits.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def champions(tftraits):
    return overlay.parse_tftraits_champions(tftraits)


@pytest.fixture(scope="module")
def units():
    return overlay.parse_tactics_units((FIXTURES / "tactics_units.html").read_text(encoding="utf-8"))


# --- parsers ---------------------------------------------------------------


def test_tftraits_champion_is_keyed_by_its_cdragon_id(champions):
    """The image name is the CDragon apiName, lower-cased: the join key."""
    assert set(champions) == {"da_18_warwick", "da_18_cassiopeia", "da_18_rengar"}
    warwick = champions["da_18_warwick"]
    assert warwick["ability"] == "Jaws of The Beast"
    assert warwick["mana"] == [0, 40]
    assert "230/345/535% AD" in warwick["text"]


def test_tftraits_role_is_in_riots_role_vocabulary(champions):
    """The fetcher's ROLE_MAP is keyed by Riot's `ADFighter`, not `AD Fighter`."""
    assert champions["da_18_warwick"]["role"] == "ADFighter"
    assert champions["da_18_cassiopeia"]["role"] == "APCaster"


def test_tftraits_trait_carries_category_and_tiers(tftraits):
    traits = overlay.parse_tftraits_traits(tftraits)
    hunter = traits["da_18_hunter"]
    assert hunter["category"] == "class"
    assert hunter["tiers"] == {2: "20% AD", 3: "30% AD", 4: "40% AD", 5: "60% AD"}


def test_tactics_units_keep_variable_names_and_scaling(units):
    warwick = units["DA_18_Warwick"]
    assert warwick["variables"] == [
        {"name": "Damage", "stars": [215.0, 325.0, 500.0], "scales": ["Attack damage"]},
        {"name": "Heal", "stars": [0.2, 0.2, 0.2], "scales": ["Ability power"]},
    ]


def test_tactics_items_become_riot_effect_keys():
    """Riot's own units, so `_split_item_effects` consumes them unchanged."""
    items = overlay.parse_tactics_items((FIXTURES / "tactics_items.html").read_text(encoding="utf-8"))
    bt = items["DA_Bloodthirster"]
    assert bt["effects"] == {"AD": 0.18, "AP": 18.0, "MagicResist": 20.0, "StatOmnivamp": 0.2}
    assert "50% Health" in bt["desc"] and "30% max Health Shield" in bt["desc"]
    assert items["DA_WarmogsArmor"]["effects"] == {"Health": 500.0}


# --- reconciliation ----------------------------------------------------------


@pytest.fixture(scope="module")
def reconciled(units, champions):
    return overlay.reconcile(units, champions, overlay.NOTE_DELTAS)


def test_a_value_both_sources_print_is_confirmed(reconciled):
    damage = reconciled["DA_18_Rengar"]["Damage"]
    assert (damage["stars"], damage["source"]) == ([255.0, 385.0, 615.0], "both")


def test_the_notes_win_over_a_disagreeing_tooltip(reconciled):
    """Cassiopeia: 18.2 400/600/950, notes 425/630/1020, tftraits 420/630/1020."""
    damage = reconciled["DA_18_Cassiopeia"]["Damage"]
    assert damage["stars"] == [425.0, 630.0, 1020.0]
    assert damage["source"] == "notes 18.3"


def test_a_fractional_delta_is_applied(reconciled):
    """The prototype missed this: Warwick's heal is a ratio, 20% => 25% in 18.3."""
    heal = reconciled["DA_18_Warwick"]["Heal"]
    assert (heal["stars"], heal["source"]) == ([0.25, 0.25, 0.25], "notes 18.3")
    damage = reconciled["DA_18_Warwick"]["Damage"]
    assert (damage["stars"], damage["source"]) == ([230.0, 345.0, 535.0], "notes 18.3")


def test_an_unsettled_disagreement_is_flagged_not_resolved(reconciled):
    """Rengar's 3-star heal: 150 (tactics.tools) vs 90 (tftraits), no note."""
    low = reconciled["DA_18_Rengar"]["Minimum Heal"]
    assert low["source"] == "disagree"
    assert low["stars"] == [60.0, 90.0, 150.0]
    assert low["alternative"] == [60.0, 90.0, 90.0]


@pytest.mark.parametrize(
    "stars,text",
    [
        ([0.5, 0.75, 1.2], "deal 50/75/120% Armor physical damage"),  # a ratio as a %
        ([0.2, 0.2, 0.2], "gain 20% Attack Speed"),  # constant, printed once
    ],
)
def test_a_ratio_is_recognised_in_its_percentage_form(stars, text):
    """Mutation-found: the fixtures above never exercised either rendering."""
    units = {"DA_X": {"variables": [{"name": "V", "stars": stars, "scales": []}]}}
    result = overlay.reconcile(units, {"da_x": {"text": text}}, ())
    assert result["DA_X"]["V"]["source"] == "both"


def test_a_near_number_is_not_a_confirmation():
    """`20` inside `120` must not confirm a 20."""
    units = {"DA_X": {"variables": [{"name": "V", "stars": [20, 20, 20], "scales": []}]}}
    result = overlay.reconcile(units, {"da_x": {"text": "deal 120 damage"}}, ())
    assert result["DA_X"]["V"]["source"] == "single source"


# --- emblems (vntft: an 18.2 snapshot, doc 99 entry 161.11) -------------------


@pytest.fixture(scope="module")
def emblems():
    page = (FIXTURES / "vntft_emblems.html").read_text(encoding="utf-8")
    return overlay.parse_vntft_emblems(page)


def test_emblem_stat_lines_become_riot_effect_keys(emblems):
    assert emblems["Brawler Emblem"]["effects"] == {"Health": 150.0}
    assert emblems["Elderwood Emblem"]["effects"] == {
        "Armor": 35.0, "MagicResist": 35.0, "AS": 25.0,
    }


def test_run_together_stat_lines_parse(emblems):
    """The real page writes `+20%AD` and `+20&nbsp;MR`."""
    assert emblems["Ravager Emblem"]["effects"] == {
        "AD": 0.2, "AP": 20.0, "Armor": 20.0, "MagicResist": 20.0,
    }


def test_the_emblem_passive_is_kept_as_text(emblems):
    assert "2.5% of the holder's max Health" in emblems["Brawler Emblem"]["desc"]


def test_an_18_3_emblem_delta_is_applied(emblems):
    """Invoker Emblem mana regen 3 => 2 in 18.3; vntft still shows 3."""
    reconciled = overlay.apply_emblem_deltas(emblems, overlay.EMBLEM_DELTAS)
    assert reconciled["Invoker Emblem"]["effects"]["ManaRegen"] == 2.0
    assert reconciled["Invoker Emblem"]["source"] == "notes 18.3"
    assert reconciled["Brawler Emblem"]["source"] == "vntft 18.2"


def test_every_delta_names_its_patch():
    assert all(d.patch in {"18.3", "18.3b"} for d in overlay.NOTE_DELTAS)


# --- item passives (the twins are pre-18.2, doc 99 entry 161.12) --------------


@pytest.fixture(scope="module")
def items():
    return overlay.parse_tactics_items((FIXTURES / "tactics_items.html").read_text(encoding="utf-8"))


def test_an_item_passive_delta_is_applied(items):
    """Bloodthirster: 40% => 50% threshold and 25% => 30% shield in 18.2."""
    dated = overlay.apply_item_deltas(items, overlay.ITEM_DELTAS)
    bt = dated["DA_Bloodthirster"]
    assert bt["effects"]["HealthThreshold"] == 50.0
    assert bt["effects"]["ShieldHealthPercent"] == 30.0
    assert bt["effects"]["AD"] == 0.18, "the stat line is untouched"
    assert bt["passive_source"] == "notes 18.2"
    assert "passive_source" not in dated["DA_WarmogsArmor"]


def test_an_item_delta_the_current_text_contradicts_is_not_applied(items):
    """Two sources or none: a note the live tooltip does not print is suspect."""
    wrong = (overlay.ItemDelta("DA_Bloodthirster", "HealthThreshold", 40.0, 45.0, "18.2"),)
    dated = overlay.apply_item_deltas(items, wrong)
    assert "HealthThreshold" not in dated["DA_Bloodthirster"]["effects"]


def test_a_ratio_delta_is_checked_as_a_percentage():
    """Hand of Justice's AD is a ratio, 0.18, printed as `18%`."""
    items = {"DA_X": {"effects": {}, "desc": "Gain 18% Attack Damage."}}
    delta = overlay.ItemDelta("DA_X", "AD_NotStatBar", 0.15, 0.18, "18.2")
    assert overlay.apply_item_deltas(items, (delta,))["DA_X"]["effects"] == {"AD_NotStatBar": 0.18}


def test_every_item_delta_names_its_patch():
    assert all(d.patch == "18.2" for d in overlay.ITEM_DELTAS)


def test_the_built_overlay_carries_the_item_deltas():
    """The wiring, not just the function: `build` must date the items forward."""
    names = ("tftraits", "tactics_units", "tactics_items", "vntft_emblems")
    pages = {n: (FIXTURES / f"{n}.html").read_text(encoding="utf-8") for n in names}
    built = overlay.build(pages)
    assert built["items"]["DA_Bloodthirster"]["effects"]["HealthThreshold"] == 50.0
    assert len(built["provenance"]["item_deltas"]) == len(overlay.ITEM_DELTAS)
    assert {d["key"] for d in built["traits"]["da_18_hunter"]["deltas"]} == {"HunterAD"}


# --- emblem passives (doc 99 entry 161.14) -----------------------------------


def test_an_emblem_passive_becomes_parameters(emblems):
    """vntft prints the passive as text; the engine needs its numbers."""
    with_passives = overlay.add_emblem_passives(emblems, overlay.EMBLEM_PASSIVES)
    assert with_passives["Brawler Emblem"]["effects"] == {
        "Health": 150.0, "MaxHealthMagicDamage": 0.025,
    }
    assert with_passives["Ravager Emblem"]["effects"]["HealingPerStep"] == 300.0
    assert with_passives["Elderwood Emblem"]["effects"] == emblems["Elderwood Emblem"]["effects"]


def test_an_emblem_passive_the_text_does_not_print_is_skipped(emblems):
    wrong = {"Brawler Emblem": {"MaxHealthMagicDamage": 0.04}}
    assert "MaxHealthMagicDamage" not in (
        overlay.add_emblem_passives(emblems, wrong)["Brawler Emblem"]["effects"])


def test_an_18_3_passive_delta_dates_the_18_2_text_forward():
    """Hunter's per-takedown AD is 18% in vntft's 18.2 text and 15% in 18.3."""
    hunter = {"Hunter Emblem": {"effects": {"AD": 0.2},
                                "desc": "Takedowns grant 18% Attack Damage."}}
    dated = overlay.apply_emblem_deltas(
        overlay.add_emblem_passives(hunter, overlay.EMBLEM_PASSIVES), overlay.EMBLEM_DELTAS)
    assert dated["Hunter Emblem"]["effects"]["TakedownAD"] == 0.15
    assert dated["Hunter Emblem"]["source"] == "notes 18.3"


# --- trait deltas (doc 99 entry 161.15) -------------------------------------


def test_a_trait_delta_is_applied_where_the_18_3_text_agrees(tftraits):
    traits = overlay.apply_trait_deltas(overlay.parse_tftraits_traits(tftraits), overlay.TRAIT_DELTAS)
    hunter = traits["da_18_hunter"]
    assert {(d["count"], d["key"], d["new"]) for d in hunter["deltas"]} == {
        (4, "HunterAD", 0.40), (5, "HunterAD", 0.60)}
    assert all(d["source"] == "notes 18.3" for d in hunter["deltas"])


def test_a_trait_delta_the_tier_text_does_not_print_is_skipped(tftraits):
    wrong = (overlay.TraitDelta("DA_18_Hunter", 4, "HunterAD", 0.45, 0.42, "18.3"),)
    traits = overlay.apply_trait_deltas(overlay.parse_tftraits_traits(tftraits), wrong)
    assert "deltas" not in traits["da_18_hunter"]


def test_every_trait_delta_and_dispute_names_its_source():
    assert all(d.patch in {"18.2", "18.3"} for d in overlay.TRAIT_DELTAS)
    assert all(reason for *_, reason in overlay.TRAIT_DISPUTES)
