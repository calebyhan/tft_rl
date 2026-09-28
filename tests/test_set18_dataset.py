"""Invariants over the Set 18 dataset in `data/set18/` (doc 99 entry 161.12).

Like `test_real_dataset`, nothing here pins a stat that a balance patch moves.
It pins the properties the first real build broke without a single unit test
noticing: live items normalising to `no_effect`, and roles defaulting from
attack range because CDragon ships none.
"""

from __future__ import annotations

import json

import pytest

from engine.loader import load_all
from tests.paths import REAL_DATA_DIR

SET18_DIR = REAL_DATA_DIR / "set18"


@pytest.fixture(scope="module")
def data():
    return load_all(SET18_DIR)


def test_it_is_set_18_on_the_live_id_scheme(data):
    assert json.loads((SET18_DIR / "VERSION.json").read_text())["set"] == 18
    assert len(data.champions) == 65
    assert all(i.startswith("DA_") for i in data.items), "legacy TFT_Item_ twins leaked in"


def test_config_is_the_one_hand_curated_file():
    """A second config would drift; the Set 18 directory links to `data/`'s."""
    link = SET18_DIR / "config.json"
    assert link.is_symlink()
    assert link.resolve() == (REAL_DATA_DIR / "config.json").resolve()


def test_no_live_advanced_item_is_silently_inert(data):
    """36 of 39 were `no_effect` before the twin's passive was kept (161.12)."""
    inert = [i.id for i in data.items.values()
             if i.category == "advanced" and i.effect_id == "no_effect"]
    assert not inert, f"advanced items with nothing to model: {inert}"


def test_every_craftable_emblem_carries_its_stats(data):
    bare = [i.id for i in data.items.values() if i.category == "emblem" and not i.stats]
    assert not bare, f"emblems without their Set 18 stat line: {bare}"


def test_roles_come_from_a_source_not_from_attack_range():
    """CDragon alone gave 32 Fighter / 32 Caster / 1 Tank (161.2)."""
    overlay = json.loads((SET18_DIR / "overlay.json").read_text())
    missing = [cid for cid, c in overlay["champions"].items()
               if cid.startswith(("DA_18_", "DA_")) and not c.get("role")
               and not cid.startswith(("DA_18_Lux_", "DA_Lux18_B"))]
    assert not missing, f"no sourced role: {missing}"


def test_every_champion_has_ability_parameters(data):
    """63 of 65 had none from CDragon; Lux's base form is the one exception."""
    empty = [c.id for c in data.champions.values() if c.ability and not c.ability.params]
    assert empty == ["DA_Lux18_Base"]


def test_every_live_item_behaviour_has_a_hook(data):
    """Item 4a of 161.7: the live ids warned `item_DA_*` until they took their
    twin's behaviour id, which is the one the engine registers."""
    from engine.effects import EFFECT_HOOKS

    unhooked = sorted(i.id for i in data.items.values()
                      if i.category != "emblem" and i.effect_id not in EFFECT_HOOKS)
    assert not unhooked, f"live items whose behaviour warns and no-ops: {unhooked}"


def test_no_live_item_hook_reads_only_absent_keys(data):
    from tests.test_item_effects import item_effects_reading_only_absent_keys

    dead = item_effects_reading_only_absent_keys(data)
    assert not dead, "live item effects reading only absent keys:\n  " + "\n  ".join(dead)


def test_thiefs_gloves_rerolls_on_the_live_id(data):
    """The re-roll matched the legacy item id, so live gloves never fired."""
    import random

    from engine.items import ItemRegistry
    from engine.player import PlayerState
    from engine.unit import UnitInstance

    registry = ItemRegistry(data.items, data.config.max_items_per_unit)
    player = PlayerState(data=data, registry=registry)
    unit = UnitInstance(data.champions[sorted(data.champions)[0]], 1, registry=registry)
    unit.equip(data.items["DA_ThiefsGloves"])
    player.bench[0] = unit

    player.reroll_thiefs_gloves(random.Random(1))
    assert [i.id for i in unit.items][0] == "DA_ThiefsGloves"
    assert len(unit.items) == 3


def test_every_item_passive_delta_reached_the_dataset(data):
    """The twins are pre-18.2; each delta the overlay declares must land.

    Pinned against the builder's own `ITEM_DELTAS`, so a balance patch moves
    the expectation with it rather than breaking a hard-coded number.
    """
    from scripts.build_set18_overlay import ITEM_DELTAS

    stale = [f"{d.item} {d.key}: {data.items[d.item].params.get(d.key)} != {d.new}"
             for d in ITEM_DELTAS
             if data.items[d.item].params.get(d.key) != pytest.approx(d.new)]
    assert not stale, f"18.2 passive changes missing from the dataset: {stale}"


# Set 18 emblems carry a passive beyond their trait (161.13). An `emblem_*` id
# counts as implemented because it grants the trait, so an emblem with passive
# text and no hook would be inert without a single warning. 161.14 modelled
# eight; Sprykin's needs its trait's BFF, which is item 4b.
UNMODELLED_EMBLEM_PASSIVES = 1


def test_unmodelled_emblem_passives_are_counted_and_do_not_grow(data):
    import re

    from engine.effects import EFFECT_HOOKS

    overlay = json.loads((SET18_DIR / "overlay.json").read_text())["emblems"]
    unmodelled = sorted(
        i.display_name for i in data.items.values()
        if i.category == "emblem" and not EFFECT_HOOKS.get(i.effect_id)
        and re.sub(r"^The holder gains the [\w' ]+ trait\.\s*", "",
                   overlay.get(i.display_name, {}).get("desc", "")).strip()
    )
    assert len(unmodelled) <= UNMODELLED_EMBLEM_PASSIVES, f"new unmodelled emblem passives: {unmodelled}"
    assert len(unmodelled) == UNMODELLED_EMBLEM_PASSIVES, (
        f"an emblem passive was modelled or removed; lower the count: {unmodelled}")


def test_every_modelled_emblem_passive_has_its_parameters(data):
    """A hook with no parameters reads 0.0 and silently does nothing."""
    from engine.effects import EFFECT_HOOKS

    bare = sorted(i.id for i in data.items.values()
                  if i.category == "emblem" and EFFECT_HOOKS.get(i.effect_id) and not i.params)
    assert not bare, f"emblem hooks with nothing to read: {bare}"


def test_every_trait_delta_reached_the_dataset(data):
    """CDragon's trait numbers are an older, mixed snapshot (161.15)."""
    from scripts.build_set18_overlay import TRAIT_DELTAS

    stale = []
    for d in TRAIT_DELTAS:
        bp = next(b for b in data.traits[d.trait].breakpoints if b.count == d.count)
        if bp.params.get(d.key) != pytest.approx(d.new):
            stale.append(f"{d.trait} {d.count} {d.key}: {bp.params.get(d.key)} != {d.new}")
    assert not stale, f"patch-note trait changes missing from the dataset: {stale}"


def test_only_elderwood_keeps_hashed_variable_names(data):
    """Its two variables are the only ones its text never names (161.15)."""
    import re

    hashed = sorted({(t.id, k) for t in data.traits.values() for b in t.breakpoints
                     for k in b.params if re.fullmatch(r"\{[0-9a-f]{8}\}", k)})
    assert hashed == [("DA_18_Elderwood", "{0f90e7a4}"), ("DA_18_Elderwood", "{4013f48e}")]


def test_a_higher_tier_inherits_what_it_does_not_restate(data):
    """Executioner's 3- and 4-unit tiers keep the 2-unit crit (161.15)."""
    tiers = {b.count: b.params for b in data.traits["DA_18_Executioner"].breakpoints}
    assert tiers[4]["CritChance"] == tiers[2]["CritChance"] > 0
    assert tiers[4]["BleedDuration"] == tiers[3]["BleedDuration"] > 0
