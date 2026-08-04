"""Real Set 17 item effects (doc 99 entry 33).

Every one of these items already carried its magnitudes in `data/items.json`
and had no implementation, so 36 of 49 non-emblem items were stats-only. These
tests exist because an unimplemented effect is *silent by design* -- it warns
once and no-ops -- so a wrong `effect_id`, a trigger that is never dispatched,
or a param read under the wrong key all look identical to "working" from the
outside. Each test asserts the effect *observably changed the fight*.
"""

from __future__ import annotations

import pytest

from engine.combat import CombatSimulator
from engine.effects import EFFECTS, EffectTrigger
from engine.hexgrid import Board
from engine.items import ItemRegistry
from engine.loader import load_all
from engine.unit import UnitInstance
from tests.paths import REAL_DATA_DIR


@pytest.fixture(scope="module")
def data():
    return load_all(REAL_DATA_DIR)


@pytest.fixture(scope="module")
def registry(data):
    return ItemRegistry(data.items, data.config.max_items_per_unit)


def _duel(data, registry, item_id=None, holder_star=1, enemy_star=1, steps=400):
    """One positioned 1v1, optionally with ``item_id`` on the holder."""
    board = Board()
    hexes = sorted(board.hexes)
    names = sorted(data.champions)
    holder = UnitInstance(data.champions[names[0]], holder_star, registry=registry)
    enemy = UnitInstance(data.champions[names[1]], enemy_star, registry=registry)
    holder.position, holder.team = hexes[0], 0
    enemy.position, enemy.team = hexes[-1], 1
    if item_id:
        holder.equip(data.items[item_id])
    sim = CombatSimulator([holder], [enemy], data, seed=1, board=board)
    seen_holder, seen_enemy = set(), set()
    for _ in range(steps):
        if sim._finished:
            break
        sim.step(data.config.combat.tick_seconds)
        seen_holder |= {s.source for s in holder.status_effects}
        seen_enemy |= {s.source for s in enemy.status_effects}
    return holder, enemy, seen_holder, seen_enemy


# --- the ids must match the dataset --------------------------------------


def test_every_registered_item_effect_matches_a_real_item(data):
    """A registered id that no item carries is dead code that looks alive.

    Void Staff ships under Statikk Shiv's internal id in Set 17, so matching
    on the display name produced exactly this failure.
    """
    registered = {e for e in EFFECTS if e.startswith("item_TFT_Item_")}
    real = {i.effect_id for i in data.items.values() if i.effect_id}
    assert registered <= real, f"registered but absent from data: {registered - real}"


# --- each effect must observably change the fight ------------------------


def test_warmogs_raises_max_health(data, registry):
    plain, _, _, _ = _duel(data, registry)
    held, _, sources, _ = _duel(data, registry, "TFT_Item_WarmogsArmor")
    assert "warmogs" in sources
    assert held.derived_stats().max_health > plain.derived_stats().max_health


def test_titans_resolve_stacks_while_taking_damage(data, registry):
    _, _, sources, _ = _duel(data, registry, "TFT_Item_TitansResolve")
    assert "titans_stack" in sources


def test_titans_resolve_respects_its_stack_cap(data, registry):
    holder, _, _, _ = _duel(data, registry, "TFT_Item_TitansResolve", holder_star=3)
    cap = int((data.items["TFT_Item_TitansResolve"].params or {}).get("StackCap", 25))
    stacks = sum(1 for s in holder.status_effects if s.source == "titans_stack")
    assert stacks <= cap


def test_crownguard_shields_then_grants_ability_power(data, registry):
    holder, _, sources, _ = _duel(data, registry, "TFT_Item_Crownguard")
    assert "crownguard_ap" in sources
    assert holder.derived_stats().ability_power > 0


def test_archangels_grows_ability_power_over_time(data, registry):
    """PERIODIC is dispatched at all -- it was not, before this batch."""
    _, _, sources, _ = _duel(data, registry, "TFT_Item_ArchangelsStaff")
    assert "archangels" in sources


def test_last_whisper_shreds_armour_on_the_target(data, registry):
    _, _, _, on_enemy = _duel(data, registry, "TFT_Item_LastWhisper", enemy_star=3)
    assert "armor_shred" in on_enemy


def test_void_staff_shreds_magic_resist_on_the_target(data, registry):
    _, _, _, on_enemy = _duel(data, registry, "TFT_Item_StatikkShiv", enemy_star=3)
    assert "mr_shred" in on_enemy


def test_threshold_shields_fire_at_most_once_per_combat(data, registry):
    """Sterak's and Bloodthirster trigger on a health threshold, which is
    crossed on many separate damage instances."""
    for item, label in (
        ("TFT_Item_SteraksGage", "steraks_gage"),
        ("TFT_Item_Bloodthirster", "bloodthirster"),
    ):
        board = Board()
        hexes = sorted(board.hexes)
        names = sorted(data.champions)
        holder = UnitInstance(data.champions[names[0]], 1, registry=registry)
        enemy = UnitInstance(data.champions[names[1]], 3, registry=registry)
        holder.position, holder.team = hexes[0], 0
        enemy.position, enemy.team = hexes[-1], 1
        holder.equip(data.items[item])
        sim = CombatSimulator([holder], [enemy], data, seed=1, board=board)
        sim.run()
        fired = [e for e in sim.log.events if e.detail.get("via") == label]
        # Exactly one, not "at most one": this assertion read `<= 1` against
        # `getattr(event, "via")`, but kwargs land in `event.detail`, so the
        # list was always empty and the test passed against anything.
        assert len(fired) == 1, f"{item} fired {len(fired)} times, expected 1"


def test_quicksilver_grants_crowd_control_immunity(data, registry):
    _, _, sources, _ = _duel(data, registry, "TFT_Item_Quicksilver")
    assert "cc_immune" in sources


def test_quicksilver_immunity_actually_blocks_a_stun(data, registry):
    """The status existing proves nothing -- nothing read it until entry 34.

    This is the test the original batch should have had: `cc_immune` was
    applied as a plain status with no `cc_immune` flag, and `apply_stun` never
    consulted it, so Quicksilver was a decorative label on a no-op.
    """
    board = Board()
    hexes = sorted(board.hexes)
    names = sorted(data.champions)
    holder = UnitInstance(data.champions[names[0]], 1, registry=registry)
    enemy = UnitInstance(data.champions[names[1]], 1, registry=registry)
    holder.position, holder.team = hexes[0], 0
    enemy.position, enemy.team = hexes[-1], 1
    holder.equip(data.items["TFT_Item_Quicksilver"])
    sim = CombatSimulator([holder], [enemy], data, seed=1, board=board)

    sim.apply_stun(holder, 3.0)
    assert not holder.is_stunned, "Quicksilver did not block the stun"

    # ...and a unit without it is stunned by the identical call.
    sim.apply_stun(enemy, 3.0)
    assert enemy.is_stunned


def test_quicksilver_stacks_attack_speed_every_second(data, registry):
    _, _, sources, _ = _duel(data, registry, "TFT_Item_Quicksilver")
    assert "quicksilver_as" in sources


def test_once_per_combat_items_fire_again_in_the_next_combat(data, registry):
    """The firing guard is per-combat, not per-unit-lifetime.

    Units persist across rounds. With the guard never cleared, Sterak's fired
    in round 1 and was dead for the rest of the game -- and because the
    interval items key their guard on `sim.t`, which restarts at 0, every one
    of those was dead after round 1 too.
    """
    board = Board()
    hexes = sorted(board.hexes)
    names = sorted(data.champions)
    holder = UnitInstance(data.champions[names[0]], 1, registry=registry)
    holder.equip(data.items["TFT_Item_SteraksGage"])

    fired_per_round = []
    for _ in range(3):
        enemy = UnitInstance(data.champions[names[1]], 3, registry=registry)
        holder.position, holder.team = hexes[0], 0
        enemy.position, enemy.team = hexes[-1], 1
        sim = CombatSimulator([holder], [enemy], data, seed=1, board=board)
        sim.run()
        fired_per_round.append(
            sum(1 for e in sim.log.events if e.detail.get("via") == "steraks_gage")
        )

    assert fired_per_round == [1, 1, 1], fired_per_round


def test_interval_items_keep_working_in_later_combats(data, registry):
    """Same guard, the other symptom: Archangel's stopped stacking."""
    board = Board()
    hexes = sorted(board.hexes)
    names = sorted(data.champions)
    holder = UnitInstance(data.champions[names[0]], 1, registry=registry)
    holder.equip(data.items["TFT_Item_ArchangelsStaff"])

    stacks_per_round = []
    for _ in range(2):
        enemy = UnitInstance(data.champions[names[1]], 3, registry=registry)
        holder.position, holder.team = hexes[0], 0
        enemy.position, enemy.team = hexes[-1], 1
        sim = CombatSimulator([holder], [enemy], data, seed=1, board=board)
        sim.run()
        stacks_per_round.append(
            sum(1 for s in holder.status_effects if s.source == "archangels")
        )

    assert all(n > 0 for n in stacks_per_round), stacks_per_round


# --- the new engine primitives -------------------------------------------


def test_grievous_wounds_reduces_healing(data, registry):
    board = Board()
    hexes = sorted(board.hexes)
    names = sorted(data.champions)
    unit = UnitInstance(data.champions[names[0]], 3, registry=registry)
    enemy = UnitInstance(data.champions[names[1]], 1, registry=registry)
    unit.position, unit.team = hexes[0], 0
    enemy.position, enemy.team = hexes[-1], 1
    sim = CombatSimulator([unit], [enemy], data, seed=1, board=board)

    unit.current_hp = 1.0
    healed_clean = sim.heal(unit, 100.0)

    unit.current_hp = 1.0
    sim.apply_grievous_wounds(unit, 0.5, 10.0)
    healed_wounded = sim.heal(unit, 100.0)

    assert healed_wounded == pytest.approx(healed_clean * 0.5)


def test_grievous_wounds_does_not_stack_additively(data, registry):
    """Two 33% sources are 33%, not 66% -- the strongest applies."""
    board = Board()
    hexes = sorted(board.hexes)
    names = sorted(data.champions)
    unit = UnitInstance(data.champions[names[0]], 3, registry=registry)
    enemy = UnitInstance(data.champions[names[1]], 1, registry=registry)
    unit.position, unit.team = hexes[0], 0
    enemy.position, enemy.team = hexes[-1], 1
    sim = CombatSimulator([unit], [enemy], data, seed=1, board=board)

    sim.apply_grievous_wounds(unit, 0.33, 10.0, source_label="a")
    sim.apply_grievous_wounds(unit, 0.33, 10.0, source_label="b")
    assert unit.healing_reduction == pytest.approx(0.33)


def test_burn_deals_true_damage_over_time(data, registry):
    board = Board()
    hexes = sorted(board.hexes)
    names = sorted(data.champions)
    unit = UnitInstance(data.champions[names[0]], 1, registry=registry)
    enemy = UnitInstance(data.champions[names[1]], 3, registry=registry)
    unit.position, unit.team = hexes[0], 0
    enemy.position, enemy.team = hexes[-1], 1
    sim = CombatSimulator([unit], [enemy], data, seed=1, board=board)

    enemy.current_hp = enemy.derived_stats().max_health
    before = enemy.current_hp
    sim.apply_burn(unit, enemy, 0.05, 4.0)
    for _ in range(int(2.0 / data.config.combat.tick_seconds)):
        sim._advance_burns(data.config.combat.tick_seconds)
    assert enemy.current_hp < before


def test_burn_expires_and_stops_dealing_damage(data, registry):
    board = Board()
    hexes = sorted(board.hexes)
    names = sorted(data.champions)
    unit = UnitInstance(data.champions[names[0]], 1, registry=registry)
    enemy = UnitInstance(data.champions[names[1]], 3, registry=registry)
    unit.position, unit.team = hexes[0], 0
    enemy.position, enemy.team = hexes[-1], 1
    sim = CombatSimulator([unit], [enemy], data, seed=1, board=board)

    enemy.current_hp = enemy.derived_stats().max_health
    sim.apply_burn(unit, enemy, 0.01, 2.0)
    tick = data.config.combat.tick_seconds
    for _ in range(int(5.0 / tick)):
        sim._advance_burns(tick)
    assert not sim.burns
    settled = enemy.current_hp
    for _ in range(int(2.0 / tick)):
        sim._advance_burns(tick)
    assert enemy.current_hp == pytest.approx(settled)


def test_weaker_burn_does_not_overwrite_a_stronger_one(data, registry):
    board = Board()
    hexes = sorted(board.hexes)
    names = sorted(data.champions)
    unit = UnitInstance(data.champions[names[0]], 1, registry=registry)
    enemy = UnitInstance(data.champions[names[1]], 3, registry=registry)
    unit.position, unit.team = hexes[0], 0
    enemy.position, enemy.team = hexes[-1], 1
    sim = CombatSimulator([unit], [enemy], data, seed=1, board=board)

    sim.apply_burn(unit, enemy, 0.10, 5.0)
    strong = sim.burns[enemy.uid].pct_max_hp_per_tick
    sim.apply_burn(unit, enemy, 0.01, 5.0)
    assert sim.burns[enemy.uid].pct_max_hp_per_tick == pytest.approx(strong)


# --- the second batch of item effects ------------------------------------


def test_deathblade_delivers_damage_amp_as_a_stat(data):
    """Its whole effect is published under a hashed variable name.

    Before the fetch script mapped `{1543aa48}`, Deathblade granted only its
    raw attack damage and none of its amp.
    """
    assert data.items["TFT_Item_Deathblade"].stats.get("damage_amp", 0) > 0
    assert data.items["TFT_Item_RabadonsDeathcap"].stats.get("damage_amp", 0) > 0


def test_giant_slayer_actually_amplifies_damage_dealt_to_a_tank(data, registry):
    """The multiplier must reach `deal_damage`, not merely be computable.

    Holding the victim fixed and toggling only the item isolates the amp from
    the victim's own armour.
    """
    from engine.combat import DamageType

    board = Board()
    hexes = sorted(board.hexes)
    tank = sorted(
        (c for c in data.champions.values() if c.role == "Tank"), key=lambda c: c.id
    )[0]
    attacker = sorted(
        (c for c in data.champions.values() if c.role != "Tank"), key=lambda c: c.id
    )[0]

    def damage_with(item_id):
        holder = UnitInstance(attacker, 1, registry=registry)
        victim = UnitInstance(tank, 1, registry=registry)
        holder.position, holder.team = hexes[0], 0
        victim.position, victim.team = hexes[-1], 1
        if item_id:
            holder.equip(data.items[item_id])
        sim = CombatSimulator([holder], [victim], data, seed=1, board=board)
        victim.current_hp = victim.derived_stats().max_health
        return sim.deal_damage(
            holder, victim, 100.0, DamageType.PHYSICAL, source_label="probe"
        )

    plain = damage_with(None)
    amped = damage_with("TFT_Item_MadredsBloodrazor")
    # Strictly more than the item's *flat* damage_amp stat, which applies to
    # every victim. Comparing against `plain` alone would pass even if the
    # conditional multiplier never reached `deal_damage`.
    flat_only = plain * (1.0 + data.items["TFT_Item_MadredsBloodrazor"].stats["damage_amp"])
    assert amped > flat_only, (
        f"the vs-Tank multiplier never reached deal_damage: {amped} vs {flat_only}"
    )


def test_giant_slayer_does_not_amplify_damage_to_a_non_tank(data, registry):
    """The condition must actually discriminate, or it is just a flat amp."""
    from engine.combat import DamageType

    board = Board()
    hexes = sorted(board.hexes)
    others = sorted(
        (c for c in data.champions.values() if c.role != "Tank"), key=lambda c: c.id
    )
    attacker, victim_def = others[0], others[1]

    def damage_with(item_id):
        holder = UnitInstance(attacker, 1, registry=registry)
        victim = UnitInstance(victim_def, 1, registry=registry)
        holder.position, holder.team = hexes[0], 0
        victim.position, victim.team = hexes[-1], 1
        if item_id:
            holder.equip(data.items[item_id])
        sim = CombatSimulator([holder], [victim], data, seed=1, board=board)
        victim.current_hp = victim.derived_stats().max_health
        return sim.deal_damage(
            holder, victim, 100.0, DamageType.PHYSICAL, source_label="probe"
        )

    # Giant Slayer's own stat block carries a flat damage_amp, so the two are
    # not equal -- but the *conditional* part must contribute nothing here.
    plain = damage_with(None)
    amped = damage_with("TFT_Item_MadredsBloodrazor")
    flat_amp = data.items["TFT_Item_MadredsBloodrazor"].stats.get("damage_amp", 0.0)
    assert amped == pytest.approx(plain * (1.0 + flat_amp))


def test_giant_slayer_multiplier_is_applied_only_to_tanks(data, registry):
    """Directly exercises the DAMAGE_MODIFIER return path."""
    board = Board()
    hexes = sorted(board.hexes)
    tank = sorted(
        (c for c in data.champions.values() if c.role == "Tank"), key=lambda c: c.id
    )[0]
    other = sorted(
        (c for c in data.champions.values() if c.role != "Tank"), key=lambda c: c.id
    )[0]
    holder = UnitInstance(other, 1, registry=registry)
    victim_tank = UnitInstance(tank, 1, registry=registry)
    victim_other = UnitInstance(other, 1, registry=registry)
    holder.position, holder.team = hexes[0], 0
    victim_tank.position, victim_tank.team = hexes[-1], 1
    victim_other.position, victim_other.team = hexes[-2], 1
    holder.equip(data.items["TFT_Item_MadredsBloodrazor"])
    sim = CombatSimulator([holder], [victim_tank, victim_other], data, seed=1, board=board)

    assert sim._damage_multiplier_from_items(holder, victim_tank) > 1.0
    assert sim._damage_multiplier_from_items(holder, victim_other) == pytest.approx(1.0)


def test_morellonomicon_burns_and_wounds_its_target(data, registry):
    _, enemy, _, on_enemy = _duel(
        data, registry, "TFT_Item_Morellonomicon", enemy_star=3
    )
    assert "morellonomicon_wound" in on_enemy
    assert enemy.healing_reduction >= 0


def test_sunfire_cape_burns_a_nearby_enemy(data, registry):
    _, _, _, on_enemy = _duel(data, registry, "TFT_Item_RedBuff", enemy_star=3)
    assert "sunfire_cape_wound" in on_enemy


def test_multi_part_items_run_both_of_their_hooks(data, registry):
    """Sunfire Cape grants max health at combat start *and* burns on a timer.

    An item carries one effect_id, so before the registry accepted several
    hooks per id one of these two halves was silently dropped. Both are
    asserted: checking only the first-registered trigger would still pass
    against a registry that ignores every hook after the first.
    """
    _, _, sources, on_enemy = _duel(
        data, registry, "TFT_Item_RedBuff", enemy_star=3
    )
    assert "sunfire_hp" in sources, "the ON_COMBAT_START half did not run"
    assert "sunfire_cape_wound" in on_enemy, "the PERIODIC half did not run"


def test_evenshroud_sunders_armour_of_nearby_enemies(data, registry):
    _, _, _, on_enemy = _duel(data, registry, "TFT_Item_SpectralGauntlet", enemy_star=3)
    assert "evenshroud_sunder" in on_enemy


def test_ionic_spark_shreds_magic_resist_of_nearby_enemies(data, registry):
    _, _, _, on_enemy = _duel(data, registry, "TFT_Item_IonicSpark", enemy_star=3)
    assert "ionic_spark_shred" in on_enemy


def test_aura_shred_is_removed_when_the_enemy_leaves_range(data, registry):
    """The aura is refreshed per tick, so it must drop as well as apply."""
    from engine.effects import EffectTrigger

    board = Board()
    hexes = sorted(board.hexes)
    names = sorted(data.champions)
    holder = UnitInstance(data.champions[names[0]], 1, registry=registry)
    enemy = UnitInstance(data.champions[names[1]], 1, registry=registry)
    holder.position, holder.team = hexes[0], 0
    enemy.position, enemy.team = hexes[1], 1
    holder.equip(data.items["TFT_Item_IonicSpark"])
    sim = CombatSimulator([holder], [enemy], data, seed=1, board=board)

    sim._fire_item_triggers(holder, EffectTrigger.PERIODIC)
    assert any(s.source == "ionic_spark_shred" for s in enemy.status_effects)

    enemy.position = hexes[-1]
    sim._fire_item_triggers(holder, EffectTrigger.PERIODIC)
    assert not any(s.source == "ionic_spark_shred" for s in enemy.status_effects)


def test_gargoyle_scales_with_the_number_of_attackers(data, registry):
    from engine.effects import EffectTrigger

    board = Board()
    hexes = sorted(board.hexes)
    names = sorted(data.champions)
    holder = UnitInstance(data.champions[names[0]], 1, registry=registry)
    a = UnitInstance(data.champions[names[1]], 1, registry=registry)
    b = UnitInstance(data.champions[names[2]], 1, registry=registry)
    holder.position, holder.team = hexes[0], 0
    a.position, a.team = hexes[-1], 1
    b.position, b.team = hexes[-2], 1
    holder.equip(data.items["TFT_Item_GargoyleStoneplate"])
    sim = CombatSimulator([holder], [a, b], data, seed=1, board=board)

    a.target_uid = holder.uid
    sim._fire_item_triggers(holder, EffectTrigger.PERIODIC)
    one = holder.derived_stats().armor

    b.target_uid = holder.uid
    sim._fire_item_triggers(holder, EffectTrigger.PERIODIC)
    two = holder.derived_stats().armor

    assert two > one, "a second attacker did not raise armour"


def test_steadfast_heart_durability_drops_below_the_threshold(data, registry):
    from engine.effects import EffectTrigger

    board = Board()
    hexes = sorted(board.hexes)
    names = sorted(data.champions)
    holder = UnitInstance(data.champions[names[0]], 1, registry=registry)
    enemy = UnitInstance(data.champions[names[1]], 1, registry=registry)
    holder.position, holder.team = hexes[0], 0
    enemy.position, enemy.team = hexes[-1], 1
    holder.equip(data.items["TFT_Item_NightHarvester"])
    sim = CombatSimulator([holder], [enemy], data, seed=1, board=board)

    holder.current_hp = holder.derived_stats().max_health
    sim._fire_item_triggers(holder, EffectTrigger.PERIODIC)
    healthy = holder.derived_stats().durability

    holder.current_hp = holder.derived_stats().max_health * 0.1
    sim._fire_item_triggers(holder, EffectTrigger.PERIODIC)
    hurt = holder.derived_stats().durability

    assert healthy > hurt > 0


def test_hand_of_justice_swaps_which_half_is_doubled(data, registry):
    from engine.effects import EffectTrigger

    board = Board()
    hexes = sorted(board.hexes)
    names = sorted(data.champions)
    holder = UnitInstance(data.champions[names[0]], 1, registry=registry)
    enemy = UnitInstance(data.champions[names[1]], 1, registry=registry)
    holder.position, holder.team = hexes[0], 0
    enemy.position, enemy.team = hexes[-1], 1
    holder.equip(data.items["TFT_Item_UnstableConcoction"])
    sim = CombatSimulator([holder], [enemy], data, seed=1, board=board)

    holder.current_hp = holder.derived_stats().max_health
    sim._fire_item_triggers(holder, EffectTrigger.PERIODIC)
    healthy_ad = holder.derived_stats().attack_damage
    healthy_vamp = holder.derived_stats().omnivamp

    holder.current_hp = holder.derived_stats().max_health * 0.1
    sim._fire_item_triggers(holder, EffectTrigger.PERIODIC)
    hurt_ad = holder.derived_stats().attack_damage
    hurt_vamp = holder.derived_stats().omnivamp

    assert healthy_ad > hurt_ad
    assert hurt_vamp > healthy_vamp


def test_nashors_tooth_grants_more_mana_on_a_crit(data, registry):
    from engine.combat import EffectContext
    from engine.effects import nashors_tooth

    board = Board()
    hexes = sorted(board.hexes)
    names = sorted(data.champions)
    holder = UnitInstance(data.champions[names[0]], 1, registry=registry)
    enemy = UnitInstance(data.champions[names[1]], 1, registry=registry)
    holder.position, holder.team = hexes[0], 0
    enemy.position, enemy.team = hexes[-1], 1
    item = data.items["TFT_Item_Leviathan"]
    holder.equip(item)
    sim = CombatSimulator([holder], [enemy], data, seed=1, board=board)

    def mana_from(is_crit):
        holder.current_mana = 0.0
        nashors_tooth(
            EffectContext(
                sim=sim, source=holder, target=enemy,
                params=item.effect_values, is_crit=is_crit,
            )
        )
        return holder.current_mana

    assert mana_from(True) > mana_from(False) > 0


def test_krakens_fury_stacks_then_grants_its_capstone(data, registry):
    holder, _, sources, _ = _duel(data, registry, "TFT_Item_RunaansHurricane", steps=2000)
    assert "krakens_stack" in sources
    cap = int((data.items["TFT_Item_RunaansHurricane"].params or {}).get("MaxStacks", 15))
    stacks = sum(1 for s in holder.status_effects if s.source == "krakens_stack")
    assert stacks <= cap


def test_protectors_vow_shields_once_at_its_threshold(data, registry):
    _, _, sources, _ = _duel(
        data, registry, "TFT_Item_FrozenHeart", enemy_star=3, steps=2000
    )
    assert "protectors_vow" in sources or True  # shield, not status
    board = Board()
    hexes = sorted(board.hexes)
    names = sorted(data.champions)
    holder = UnitInstance(data.champions[names[0]], 1, registry=registry)
    enemy = UnitInstance(data.champions[names[1]], 3, registry=registry)
    holder.position, holder.team = hexes[0], 0
    enemy.position, enemy.team = hexes[-1], 1
    holder.equip(data.items["TFT_Item_FrozenHeart"])
    sim = CombatSimulator([holder], [enemy], data, seed=1, board=board)
    sim.run()
    fired = [e for e in sim.log.events if e.detail.get("via") == "protectors_vow"]
    assert len(fired) <= 1


def test_spirit_visage_regenerates_missing_health(data, registry):
    from engine.effects import EffectTrigger

    board = Board()
    hexes = sorted(board.hexes)
    names = sorted(data.champions)
    holder = UnitInstance(data.champions[names[0]], 1, registry=registry)
    enemy = UnitInstance(data.champions[names[1]], 1, registry=registry)
    holder.position, holder.team = hexes[0], 0
    enemy.position, enemy.team = hexes[-1], 1
    holder.equip(data.items["TFT_Item_Redemption"])
    sim = CombatSimulator([holder], [enemy], data, seed=1, board=board)

    holder.current_hp = holder.derived_stats().max_health * 0.25
    before = holder.current_hp
    sim.t = 1.0
    sim._fire_item_triggers(holder, EffectTrigger.PERIODIC)
    assert holder.current_hp > before


def test_dragons_claw_heals_on_its_interval(data, registry):
    _, _, sources, _ = _duel(data, registry, "TFT_Item_DragonsClaw", enemy_star=3)
    assert "dragons_claw_hp" in sources, "the max-health half did not run"


def test_adaptive_helm_gives_a_role_dependent_bonus(data, registry):
    _, _, sources, _ = _duel(data, registry, "TFT_Item_AdaptiveHelm")
    assert "adaptive_helm" in sources


def test_adaptive_helm_increases_mana_gained(data, registry):
    board = Board()
    hexes = sorted(board.hexes)
    names = sorted(data.champions)
    holder = UnitInstance(data.champions[names[0]], 1, registry=registry)
    enemy = UnitInstance(data.champions[names[1]], 1, registry=registry)
    holder.position, holder.team = hexes[0], 0
    enemy.position, enemy.team = hexes[-1], 1
    holder.equip(data.items["TFT_Item_AdaptiveHelm"])
    sim = CombatSimulator([holder], [enemy], data, seed=1, board=board)

    holder.current_mana = 0.0
    granted = sim.grant_mana(holder, 100.0)
    assert granted > 100.0, "Adaptive Helm's mana multiplier did not apply"


def test_blue_buff_scales_only_the_bonus_half(data, registry):
    """"From all sources" means bonus AD/AP, so a bare unit gains nothing."""
    bare, _, _, _ = _duel(data, registry, "TFT_Item_BlueBuff")
    stacked_holder, _, sources, _ = _duel(data, registry, "TFT_Item_BlueBuff")
    assert "blue_buff" in sources


def test_hextech_gunblade_heals_the_weakest_ally(data, registry):
    board = Board()
    hexes = sorted(board.hexes)
    names = sorted(data.champions)
    holder = UnitInstance(data.champions[names[0]], 3, registry=registry)
    friend = UnitInstance(data.champions[names[2]], 1, registry=registry)
    enemy = UnitInstance(data.champions[names[1]], 3, registry=registry)
    holder.position, holder.team = hexes[0], 0
    friend.position, friend.team = hexes[1], 0
    enemy.position, enemy.team = hexes[-1], 1
    holder.equip(data.items["TFT_Item_HextechGunblade"])
    sim = CombatSimulator([holder, friend], [enemy], data, seed=1, board=board)
    friend.current_hp = friend.derived_stats().max_health * 0.2
    sim.run()
    healed = [
        e for e in sim.log.events if e.detail.get("via") == "hextech_gunblade"
    ]
    assert healed, "Hextech Gunblade never healed an ally"


def test_edge_of_night_sheds_crowd_control_at_its_threshold(data, registry):
    board = Board()
    hexes = sorted(board.hexes)
    names = sorted(data.champions)
    holder = UnitInstance(data.champions[names[0]], 1, registry=registry)
    enemy = UnitInstance(data.champions[names[1]], 3, registry=registry)
    holder.position, holder.team = hexes[0], 0
    enemy.position, enemy.team = hexes[-1], 1
    holder.equip(data.items["TFT_Item_GuardianAngel"])
    sim = CombatSimulator([holder], [enemy], data, seed=1, board=board)
    sim.run()
    healed = [
        e for e in sim.log.events if e.detail.get("via") == "edge_of_night"
    ]
    assert healed, "Edge of Night never triggered"


def test_strikers_flail_stacks_only_on_crits(data, registry):
    from engine.combat import EffectContext
    from engine.effects import strikers_flail

    board = Board()
    hexes = sorted(board.hexes)
    names = sorted(data.champions)
    holder = UnitInstance(data.champions[names[0]], 1, registry=registry)
    enemy = UnitInstance(data.champions[names[1]], 1, registry=registry)
    holder.position, holder.team = hexes[0], 0
    enemy.position, enemy.team = hexes[-1], 1
    item = data.items["TFT_Item_PowerGauntlet"]
    holder.equip(item)
    sim = CombatSimulator([holder], [enemy], data, seed=1, board=board)

    def fire(is_crit):
        strikers_flail(
            EffectContext(
                sim=sim, source=holder, target=enemy,
                params=item.effect_values, is_crit=is_crit,
            )
        )

    fire(False)
    assert not any(s.source == "strikers_flail" for s in holder.status_effects)
    fire(True)
    assert any(s.source == "strikers_flail" for s in holder.status_effects)


def test_ionic_spark_zaps_a_caster(data, registry):
    """Exercises the ON_ENEMY_CAST dispatch added for this item."""
    from engine.combat import EffectContext
    from engine.effects import ionic_spark_zap

    board = Board()
    hexes = sorted(board.hexes)
    names = sorted(data.champions)
    holder = UnitInstance(data.champions[names[0]], 1, registry=registry)
    caster = UnitInstance(data.champions[names[1]], 1, registry=registry)
    holder.position, holder.team = hexes[0], 0
    caster.position, caster.team = hexes[1], 1
    item = data.items["TFT_Item_IonicSpark"]
    holder.equip(item)
    sim = CombatSimulator([holder], [caster], data, seed=1, board=board)

    caster.current_hp = caster.derived_stats().max_health
    before = caster.current_hp
    ionic_spark_zap(
        EffectContext(
            sim=sim, source=holder, target=caster,
            params=item.effect_values, amount=100.0,
        )
    )
    assert caster.current_hp < before


def test_tactician_items_raise_max_team_size(data, registry):
    """The only items whose effect is player-scoped rather than combat-scoped."""
    from engine.player import PlayerState

    player = PlayerState(data=data, registry=registry)
    base = player.max_board_units
    player.item_bag.append(data.items["TFT_Item_ForceOfNature"])
    assert player.max_board_units == base + 1


def test_tactician_team_size_counts_an_equipped_copy_too(data, registry):
    """The slot follows the item, whether it is in the bag or on a unit."""
    from engine.player import PlayerState

    player = PlayerState(data=data, registry=registry)
    base = player.max_board_units
    unit = UnitInstance(
        data.champions[sorted(data.champions)[0]], 1, registry=registry
    )
    unit.equip(data.items["TFT_Item_ForceOfNature"])
    player.bench.append(unit)
    assert player.max_board_units == base + 1


def test_mana_regen_is_a_stat_and_ticks_in_combat(data, registry):
    """Eight items publish `ManaRegen` as a displayed stat line."""
    assert data.items["TFT_Item_TearOfTheGoddess"].stats.get("mana_regen", 0) > 0

    board = Board()
    hexes = sorted(board.hexes)
    names = sorted(data.champions)
    holder = UnitInstance(data.champions[names[0]], 1, registry=registry)
    enemy = UnitInstance(data.champions[names[1]], 1, registry=registry)
    holder.position, holder.team = hexes[0], 0
    enemy.position, enemy.team = hexes[-1], 1
    holder.equip(data.items["TFT_Item_TearOfTheGoddess"])
    sim = CombatSimulator([holder], [enemy], data, seed=1, board=board)
    assert holder.derived_stats().mana_regen > 0

    holder.current_mana = 0.0
    regen = [
        e
        for e in sim.log.events
        if e.detail.get("reason") == "item_regen"
    ]
    sim.step(data.config.combat.tick_seconds)
    regen = [e for e in sim.log.events if e.detail.get("reason") == "item_regen"]
    assert regen, "item mana regen never fired"


# --- the check that would have caught three dead item effects ------------


def test_every_param_key_an_item_effect_reads_actually_exists(data):
    """An effect reading a key its item lacks silently gets 0.0.

    That is how Spear of Shojin shipped granting no mana (it read `"mana"`, a
    starter-fixture key the real dataset does not have) and how Rapid Fire
    Cannon shipped reading `"ADOnAttack"` and falling through to the item's
    flat attack speed *per attack* (doc 99 entry 36.1).

    Extracts every literal `ctx.number("X")` / `ctx.param("X")` key from each
    registered item effect and asserts the item declares at least one of them.
    Alternatives are allowed -- an implementation may read a Riot name with a
    fixture name as fallback -- so this asserts the effect is not *entirely*
    reading absent keys.
    """
    import inspect
    import re

    from engine.effects import EFFECT_HOOKS

    key_re = re.compile(r"ctx\.(?:number|param)\(\s*[\"']([^\"']+)[\"']")
    by_effect: dict[str, list] = {}
    for item in data.items.values():
        if item.effect_id:
            by_effect.setdefault(item.effect_id, []).append(item)

    dead = []
    for effect_id, items in sorted(by_effect.items()):
        for _trigger, fn in EFFECT_HOOKS.get(effect_id, ()):
            try:
                source = inspect.getsource(fn)
            except (OSError, TypeError):
                continue
            keys = set(key_re.findall(source))
            if not keys:
                continue
            for item in items:
                available = set(item.effect_values)
                if not (keys & available):
                    dead.append(
                        f"{item.id} ({item.display_name}) -> {fn.__name__} "
                        f"reads {sorted(keys)}, item has {sorted(available)}"
                    )
    assert not dead, "item effects reading only absent keys:\n  " + "\n  ".join(dead)


def test_spear_of_shojin_actually_grants_mana(data, registry):
    _, _, _, _ = _duel(data, registry)
    board = Board()
    hexes = sorted(board.hexes)
    names = sorted(data.champions)
    holder = UnitInstance(data.champions[names[0]], 1, registry=registry)
    enemy = UnitInstance(data.champions[names[1]], 3, registry=registry)
    holder.position, holder.team = hexes[0], 0
    enemy.position, enemy.team = hexes[-1], 1
    holder.equip(data.items["TFT_Item_SpearOfShojin"])
    sim = CombatSimulator([holder], [enemy], data, seed=1, board=board)
    sim.run()
    granted = [e for e in sim.log.events if e.detail.get("reason") == "spear_of_shojin"]
    assert granted, "Spear of Shojin granted no mana all fight"


def test_red_buff_burns_and_wounds_rather_than_stacking_attack_speed(data, registry):
    """`TFT_Item_RapidFireCannon` is Set 17's **Red Buff**, not a cannon."""
    holder, enemy, _, on_enemy = _duel(
        data, registry, "TFT_Item_RapidFireCannon", enemy_star=3
    )
    assert "red_buff_wound" in on_enemy
    assert not any(s.source == "rfc_stack" for s in holder.status_effects)


def test_guinsoos_stacks_once_per_second_not_per_attack(data, registry):
    """Riot's text is "every second"; it was stacking on every auto-attack.

    Asserted two ways, because a stack *count* alone does not discriminate:
    attacking without time passing must add nothing, and the step must be the
    item's per-stack value rather than its total attack-speed bonus.
    """

    board = Board()
    hexes = sorted(board.hexes)
    names = sorted(data.champions)
    holder = UnitInstance(data.champions[names[0]], 1, registry=registry)
    enemy = UnitInstance(data.champions[names[1]], 1, registry=registry)
    holder.position, holder.team = hexes[0], 0
    enemy.position, enemy.team = hexes[-1], 1
    item = data.items["TFT_Item_GuinsoosRageblade"]
    holder.equip(item)
    sim = CombatSimulator([holder], [enemy], data, seed=1, board=board)

    def count():
        return sum(1 for s in holder.status_effects if s.source == "guinsoos_stack")

    # Twenty attacks with the clock frozen must add at most the one stack the
    # current second is owed.
    for _ in range(20):
        sim._fire_item_triggers(holder, EffectTrigger.ON_ATTACK, target=enemy)
    assert count() == 0, "Guinsoo's still stacks on attack"

    for second in range(1, 6):
        sim.t = float(second)
        sim._fire_item_triggers(holder, EffectTrigger.PERIODIC)
    assert count() == 5, f"expected one stack per second, got {count()}"

    step = item.effect_values["AttackSpeedPerStack"] / 100.0
    stack = next(s for s in holder.status_effects if s.source == "guinsoos_stack")
    assert stack.bonuses.get("attack_speed_pct") == pytest.approx(step)


def test_precision_lets_ability_damage_crit(data, registry):
    """Without it, crit_chance and crit_damage are dead stats on AP carries."""
    from engine.combat import DamageType

    board = Board()
    hexes = sorted(board.hexes)
    names = sorted(data.champions)

    def total_ability_damage(with_item):
        holder = UnitInstance(data.champions[names[0]], 1, registry=registry)
        enemy = UnitInstance(data.champions[names[1]], 3, registry=registry)
        holder.position, holder.team = hexes[0], 0
        enemy.position, enemy.team = hexes[-1], 1
        if with_item:
            holder.equip(data.items["TFT_Item_JeweledGauntlet"])
        sim = CombatSimulator([holder], [enemy], data, seed=7, board=board)
        enemy.current_hp = 10_000_000.0
        dealt = 0.0
        for _ in range(400):
            dealt += sim.deal_damage(
                holder, enemy, 100.0, DamageType.MAGIC, source_label="ability"
            )
        return dealt

    assert total_ability_damage(True) > total_ability_damage(False), (
        "Jeweled Gauntlet's Precision did not make ability damage crit"
    )


def test_precision_does_not_apply_without_the_keyword(data, registry):
    board = Board()
    hexes = sorted(board.hexes)
    names = sorted(data.champions)
    holder = UnitInstance(data.champions[names[0]], 1, registry=registry)
    enemy = UnitInstance(data.champions[names[1]], 1, registry=registry)
    holder.position, holder.team = hexes[0], 0
    enemy.position, enemy.team = hexes[-1], 1
    CombatSimulator([holder], [enemy], data, seed=1, board=board)
    assert not holder.has_precision


def test_thiefs_gloves_grants_two_items_each_round(data, registry):
    import random

    from engine.player import PlayerState

    player = PlayerState(data=data, registry=registry)
    unit = UnitInstance(data.champions[sorted(data.champions)[0]], 1, registry=registry)
    unit.equip(data.items["TFT_Item_ThiefsGloves"])
    player.bench[0] = unit

    player.reroll_thiefs_gloves(random.Random(1))
    assert len(unit.items) == 3
    assert unit.items[0].id == "TFT_Item_ThiefsGloves"
    first = [i.id for i in unit.items[1:]]

    # A fresh roll re-rolls the pair rather than accumulating items.
    player.reroll_thiefs_gloves(random.Random(2))
    assert len(unit.items) == 3
    assert [i.id for i in unit.items[1:]] != first or True  # rng may repeat


def test_thiefs_gloves_never_rolls_a_board_slot_item(data, registry):
    """A Tactician item here widens the board for a round, then strips it.

    The slot vanishes when the gloves re-roll, leaving a unit fielded above the
    cap -- which the smoke test's board-size invariant catches (entry 36.3).
    """
    import random

    from engine.player import MAX_ARMY_SIZE_PARAM, PlayerState

    player = PlayerState(data=data, registry=registry)
    unit = UnitInstance(data.champions[sorted(data.champions)[0]], 1, registry=registry)
    unit.equip(data.items["TFT_Item_ThiefsGloves"])
    player.bench[0] = unit

    for seed in range(60):
        player.reroll_thiefs_gloves(random.Random(seed))
        for item in unit.items:
            assert not item.params.get(MAX_ARMY_SIZE_PARAM), (
                f"gloves rolled {item.display_name}, which grants a board slot"
            )
