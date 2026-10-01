"""Set 18 combat traits, tranche 4b-1 (doc 99 entry 161.16).

Every expectation is derived from the trait's own breakpoint params, never a
hard-coded balance number, so a patch moves the expectation with the data.
Each test builds a real fight on Set 18 data with enough distinct champions to
reach the tier under test, and compares a member against a non-member (or a
unit with no trait) so the change is attributable to the trait.
"""

from __future__ import annotations

import pytest

from engine.combat import CombatSimulator, DamageType, EventKind
from engine.hexgrid import Board, distance
from engine.items import ItemRegistry
from engine.loader import load_all
from engine.unit import UnitInstance
from tests.paths import REAL_DATA_DIR

SET18_DIR = REAL_DATA_DIR / "set18"


@pytest.fixture(scope="module")
def data():
    return load_all(SET18_DIR)


@pytest.fixture(scope="module")
def registry(data):
    return ItemRegistry(data.items, data.config.max_items_per_unit)


def _carrying(data, trait):
    return [c for c in sorted(data.champions) if trait in data.champions[c].traits]


def _without(data, *traits):
    return [c for c in sorted(data.champions)
            if not set(traits) & set(data.champions[c].traits)]


def _fight(data, registry, trait, members, *, others=1, enemies=1, star=1, layout=None):
    """``members`` distinct carriers of ``trait`` plus ``others`` non-carriers,
    against ``enemies``. Returns the simulator (combat start has run)."""
    board = Board()
    hexes = sorted(board.hexes)
    carriers = _carrying(data, trait)[:members]
    assert len(carriers) == members, f"only {len(carriers)} carriers of {trait}"
    plain = [c for c in _without(data, trait) if c not in carriers]
    team0 = [UnitInstance(data.champions[c], star, registry=registry) for c in carriers]
    team0 += [UnitInstance(data.champions[c], star, registry=registry) for c in plain[:others]]
    team1 = [UnitInstance(data.champions[c], 1, registry=registry)
             for c in plain[others:others + enemies]]
    spots = layout or hexes
    for i, unit in enumerate(team0):
        unit.position, unit.team = spots[i], 0
    for i, unit in enumerate(team1):
        unit.position, unit.team = hexes[-1 - i], 1
    sim = CombatSimulator(team0, team1, data, seed=1, board=board)
    return sim, team0[:members], team0[members:], team1


def _tier(data, trait, members):
    bp = data.traits[trait].active_breakpoint(members)
    assert bp is not None
    return bp.params


def _base(data, registry, unit):
    """The same champion and star with no traits, items or statuses."""
    return UnitInstance(unit.champion, unit.star_level, registry=registry).derived_stats()


def _step(sim, n=1):
    for _ in range(n):
        sim.step(sim.config.tick_seconds)


# --- flat stat classes: team value, members' own value instead ---------------


def test_brawler_team_health_plus_a_member_share(data, registry):
    sim, (member, *_), (other,), _ = _fight(data, registry, "DA_18_Brawler", 2)
    p = _tier(data, "DA_18_Brawler", 2)
    assert other.derived_stats().max_health == pytest.approx(
        _base(data, registry, other).max_health + p["BrawlerTeamHealth"])
    assert member.derived_stats().max_health == pytest.approx(
        (_base(data, registry, member).max_health + p["BrawlerTeamHealth"])
        * (1 + p["BrawlerHealthPercent"]))
    assert member.current_hp == pytest.approx(member.derived_stats().max_health)


@pytest.mark.parametrize("members", [2, 6])
def test_defenders_take_their_own_value_instead_of_the_teams(data, registry, members):
    sim, (member, *_), (other,), _ = _fight(data, registry, "DA_18_Defender", members)
    p = _tier(data, "DA_18_Defender", members)
    for stat in ("armor", "magic_resist"):
        assert getattr(other.derived_stats(), stat) == pytest.approx(
            getattr(_base(data, registry, other), stat) + p["NonDefenderDefenseGain"])
        assert getattr(member.derived_stats(), stat) == pytest.approx(
            getattr(_base(data, registry, member), stat) + p["DefenderDefenseGain"])


def test_invokers_take_their_own_mana_regen(data, registry):
    sim, (member, *_), (other,), _ = _fight(data, registry, "DA_18_Invoker", 2)
    p = _tier(data, "DA_18_Invoker", 2)
    assert other.derived_stats().mana_regen == pytest.approx(
        _base(data, registry, other).mana_regen + p["TeamManaRegen"])
    assert member.derived_stats().mana_regen == pytest.approx(
        _base(data, registry, member).mana_regen + p["InvokerManaBonus"])


def test_juggernauts_take_their_own_durability(data, registry):
    sim, (member, *_), (other,), _ = _fight(data, registry, "DA_Juggernaut18", 2)
    p = _tier(data, "DA_Juggernaut18", 2)
    assert other.derived_stats().durability == pytest.approx(p["TeamDurability"])
    assert member.derived_stats().durability == pytest.approx(p["JuggernautDurability"])


def test_spellweavers_take_their_own_ap_and_gain_more_per_cast(data, registry):
    sim, (member, *_), (other,), (enemy,) = _fight(data, registry, "DA_18_Spellweaver", 2)
    p = _tier(data, "DA_18_Spellweaver", 2)
    assert other.derived_stats().ability_power == pytest.approx(100 + 100 * p["TeamwideAP"])
    before = member.derived_stats().ability_power
    assert before == pytest.approx(100 + 100 * p["SpellweaverAP"])
    member.current_mana = member.derived_stats().max_mana
    member.mana_locked_until = 0.0
    sim._try_cast(member, enemy)  # resolved or skipped, a cast is a cast
    assert member.derived_stats().ability_power == pytest.approx(before + 100 * p["APPerCast"])


# --- conditional stats -----------------------------------------------------


def test_adaptor_takes_ad_on_a_tie_and_ap_when_ap_is_higher(data, registry):
    sim, (plain, holder), _, _ = _fight(data, registry, "DA_18_Adaptor", 2, others=0)
    p = _tier(data, "DA_18_Adaptor", 2)
    base = _base(data, registry, plain)
    assert plain.derived_stats().ability_power == pytest.approx(base.ability_power)
    assert plain.derived_stats().attack_damage == pytest.approx(
        base.attack_damage * (1 + p["ADAPGain"]))

    # Same board with Rabadon's on the second Adaptor: its AP is now higher.
    board = Board()
    hexes = sorted(board.hexes)
    team0 = [UnitInstance(u.champion, 1, registry=registry) for u in (plain, holder)]
    team0[1].equip(data.items["DA_RabadonsDeathcap"])
    enemy = UnitInstance(data.champions[_without(data, "DA_18_Adaptor")[0]], 1, registry=registry)
    for i, unit in enumerate(team0):
        unit.position = hexes[i]
    enemy.position = hexes[-1]
    CombatSimulator(team0, [enemy], data, seed=1, board=board)
    with_item = UnitInstance(holder.champion, 1, registry=registry)
    with_item.equip(data.items["DA_RabadonsDeathcap"])
    assert team0[1].derived_stats().ability_power == pytest.approx(
        with_item.derived_stats().ability_power + 100 * p["ADAPGain"])


def test_monolith_gains_resists_per_enemy_targeting_it(data, registry):
    sim, (member,), _, enemies = _fight(data, registry, "DA_18_Battlemage", 1, others=0, enemies=3)
    p = _tier(data, "DA_18_Battlemage", 1)
    base = member.derived_stats().armor
    for enemy in enemies[:2]:
        enemy.target_uid = member.uid
    enemies[2].target_uid = None
    sim._fire_trait_triggers(0, sim_trigger("PERIODIC"))
    assert member.derived_stats().armor == pytest.approx(base + 2 * p["Resists"])
    for enemy in enemies:
        enemy.target_uid = None
    sim._fire_trait_triggers(0, sim_trigger("PERIODIC"))
    assert member.derived_stats().armor == pytest.approx(base)


def sim_trigger(name):
    from engine.effects import EffectTrigger

    return EffectTrigger[name]


def test_hunter_ad_and_amp_after_holding_a_target(data, registry):
    sim, (member, *_), (other,), (enemy,) = _fight(data, registry, "DA_18_Hunter", 2)
    p = _tier(data, "DA_18_Hunter", 2)
    assert member.derived_stats().attack_damage == pytest.approx(
        _base(data, registry, member).attack_damage * (1 + p["HunterAD"]))
    assert other.derived_stats().attack_damage == pytest.approx(
        _base(data, registry, other).attack_damage)
    member.target_uid = enemy.uid
    sim._fire_trait_triggers(0, sim_trigger("PERIODIC"))
    assert member.derived_stats().damage_amp == pytest.approx(0.0)
    sim.t += p["HunterDuration"] / 2  # held, but not yet long enough
    sim._fire_trait_triggers(0, sim_trigger("PERIODIC"))
    assert member.derived_stats().damage_amp == pytest.approx(0.0)
    sim.t += p["HunterDuration"] / 2
    sim._fire_trait_triggers(0, sim_trigger("PERIODIC"))
    assert member.derived_stats().damage_amp == pytest.approx(p["DamageAmp"])
    member.target_uid = other.uid  # a swap resets it
    sim._fire_trait_triggers(0, sim_trigger("PERIODIC"))
    assert member.derived_stats().damage_amp == pytest.approx(0.0)


def test_lunar_buffs_members_more_and_only_adjacent_allies(data, registry):
    board = Board()
    hexes = sorted(board.hexes)
    first = hexes[0]
    near = next(h for h in hexes if distance(h, first) == 1)
    far = next(h for h in hexes if distance(h, first) >= 3 and distance(h, near) >= 2)
    second = next(h for h in hexes if distance(h, far) >= 2 and distance(h, near) >= 2
                  and h not in (first, near, far))
    sim, (lunar, _), (adjacent, distant), _ = _fight(
        data, registry, "DA_18_Lunar", 2, others=2, layout=[first, second, near, far])
    p = _tier(data, "DA_18_Lunar", 2)
    ap = 100 * p["AbilityPower"]
    # Measured as Lunar's own statuses: Alune and Ahri also activate
    # Spellweaver here, which moves every AP total by the same 10.
    assert _from(adjacent, "lunar") == pytest.approx(ap)
    assert _from(distant, "lunar") == 0
    assert _from(lunar, "lunar") == pytest.approx(ap * (1 + p["LunarMultiplier"]))
    assert adjacent.derived_stats().ability_power - distant.derived_stats().ability_power \
        == pytest.approx(ap)


def _from(unit, prefix, stat="ability_power"):
    return sum(s.bonuses.get(stat) for s in unit.status_effects if s.source.startswith(prefix))


# --- per-hit and per-attack --------------------------------------------------


def test_rapidfire_team_speed_and_member_stacks_per_attack(data, registry):
    sim, (member, *_), (other,), (enemy,) = _fight(data, registry, "DA_18_Rapidfire", 2)
    p = _tier(data, "DA_18_Rapidfire", 2)
    base_other = _base(data, registry, other).attack_speed
    assert other.derived_stats().attack_speed == pytest.approx(base_other * (1 + p["TeamAS"]))
    start = member.derived_stats().attack_speed
    for _ in range(int(p["MaxStacks"]) + 3):
        sim._land_attack(member, enemy, 1.0, DamageType.PHYSICAL, False)
    base = _base(data, registry, member).attack_speed
    expected = base * (1 + p["TeamAS"] + p["MaxStacks"] * p["ASperAttack"])
    assert member.derived_stats().attack_speed == pytest.approx(min(expected, 5.0))
    assert member.derived_stats().attack_speed > start
    sim._land_attack(other, enemy, 1.0, DamageType.PHYSICAL, False)
    assert other.derived_stats().attack_speed == pytest.approx(base_other * (1 + p["TeamAS"]))


def test_ravager_omnivamp_and_bonus_damage_doubled_on_the_wounded(data, registry):
    sim, (member, *_), _, (enemy,) = _fight(data, registry, "DA_18_Slayer", 2)
    p = _tier(data, "DA_18_Slayer", 2)
    assert member.derived_stats().omnivamp == pytest.approx(
        _base(data, registry, member).omnivamp + p["Omnivamp"])
    healthy = sim._damage_multiplier_from_items(member, enemy)
    assert healthy == pytest.approx(1 + p["BonusDamagePercentBase"])
    enemy.current_hp = enemy.derived_stats().max_health * p["EnemyHealthThreshold"] * 0.9
    assert sim._damage_multiplier_from_items(member, enemy) == pytest.approx(
        1 + 2 * p["BonusDamagePercentBase"])


def test_caustic_damage_shreds_and_sunders(data, registry):
    sim, (member,), _, (enemy,) = _fight(data, registry, "DA_18_Caustic", 1, others=0)
    p = _tier(data, "DA_18_Caustic", 1)
    armor, mr = enemy.derived_stats().armor, enemy.derived_stats().magic_resist
    sim.deal_damage(member, enemy, 10.0, DamageType.PHYSICAL, source_label="auto")
    assert enemy.derived_stats().armor == pytest.approx(armor * (1 - p["ShredPercent"] / 100))
    assert enemy.derived_stats().magic_resist == pytest.approx(mr * (1 - p["ShredPercent"] / 100))


def test_executioners_gain_precision_and_crit(data, registry):
    sim, (member, *_), (other,), _ = _fight(data, registry, "DA_18_Executioner", 2)
    p = _tier(data, "DA_18_Executioner", 2)
    assert member.has_precision and not other.has_precision
    assert member.derived_stats().crit_chance == pytest.approx(
        _base(data, registry, member).crit_chance + p["CritChance"])


def test_executioner_crits_bleed_from_three(data, registry):
    sim, (member, *_), _, (enemy,) = _fight(data, registry, "DA_18_Executioner", 3)
    p = _tier(data, "DA_18_Executioner", 3)
    sim.deal_damage(member, enemy, 100.0, DamageType.TRUE, is_crit=True, source_label="auto")
    # The share is of the hit's post-mitigation amount, which the member's
    # other traits' damage amp has already raised.
    dealt = next(e.detail["amount"] for e in sim.log.of_kind(EventKind.DAMAGE)
                 if e.detail.get("via") == "auto")
    before = enemy.current_hp
    _step(sim, int(p["BleedDuration"] / sim.config.tick_seconds) + 2)
    bled = sum(e.detail["hp_lost"] for e in sim.log.of_kind(EventKind.DAMAGE)
               if e.detail.get("via") == "executioner_bleed")
    assert bled == pytest.approx(p["BonusBleedPercent"] * dealt, rel=0.02)
    assert enemy.current_hp < before


def test_a_non_crit_does_not_bleed(data, registry):
    sim, (member, *_), _, (enemy,) = _fight(data, registry, "DA_18_Executioner", 3)
    sim.deal_damage(member, enemy, 100.0, DamageType.TRUE, is_crit=False, source_label="auto")
    assert not sim.stacking_burns


def test_inferno_burns_and_wounds_and_stacks_with_other_burns(data, registry):
    sim, (member, *_), _, (enemy,) = _fight(data, registry, "DA_18_Inferno", 2)
    p = _tier(data, "DA_18_Inferno", 2)
    sim.apply_burn(None, enemy, 0.5, 10.0, source_label="other")
    sim.deal_damage(member, enemy, 10.0, DamageType.PHYSICAL, source_label="auto")
    assert enemy.uid in sim.burns, "the other burn must survive"
    inferno = sim.stacking_burns[(enemy.uid, "inferno_burn")]
    assert inferno.pct_max_hp_per_tick == pytest.approx(p["HPBurnPerSecond"] / 100)
    assert enemy.healing_reduction == pytest.approx(p["WoundPercent"] / 100)


def test_vanguard_shields_at_start_and_again_below_the_threshold(data, registry):
    sim, (member, *_), (other,), _ = _fight(data, registry, "DA_18_Vanguard", 2)
    p = _tier(data, "DA_18_Vanguard", 2)
    shield = member.derived_stats().max_health * p["MaxHealthShield"]
    assert member.shield_amount == pytest.approx(shield)
    assert other.shield_amount == 0
    member.shields.clear()
    member.current_hp = member.derived_stats().max_health * p["HealthThreshold"] * 0.9
    sim._fire_trait_triggers(0, sim_trigger("PERIODIC"))
    assert member.shield_amount == pytest.approx(shield)
    member.shields.clear()
    sim._fire_trait_triggers(0, sim_trigger("PERIODIC"))
    assert member.shield_amount == 0, "the threshold shield is once per combat"


def test_six_vanguards_gain_durability_while_shielded(data, registry):
    sim, (member, *_), _, _ = _fight(data, registry, "DA_18_Vanguard", 6)
    p = _tier(data, "DA_18_Vanguard", 6)
    sim._fire_trait_triggers(0, sim_trigger("PERIODIC"))
    assert member.derived_stats().durability == pytest.approx(p["DurabilityIncrease"])
    member.shields.clear()
    sim._fire_trait_triggers(0, sim_trigger("PERIODIC"))
    assert member.derived_stats().durability == pytest.approx(0.0)


def test_flora_fatalis_takedowns_grant_mana_and_heal_the_lowest_ally(data, registry):
    sim, (member, second), (other,), (enemy,) = _fight(data, registry, "DA_FloraFatalis18", 2)
    p = _tier(data, "DA_FloraFatalis18", 2)
    member.current_mana = 0.0
    other.current_hp = other.derived_stats().max_health * 0.3
    hurt = other.current_hp
    sim.deal_damage(member, enemy, enemy.current_hp * 10, DamageType.TRUE, source_label="auto")
    assert not enemy.alive
    assert member.current_mana == pytest.approx(p["Mana"])
    assert other.current_hp == pytest.approx(hurt + p["PercentHeal"] * other.derived_stats().max_health)


def test_solar_shields_the_team_and_adds_magic_damage(data, registry):
    sim, (member, *_), (other,), (enemy,) = _fight(data, registry, "DA_18_Solar", 3)
    p = _tier(data, "DA_18_Solar", 3)
    for unit in (member, other):
        assert unit.shield_amount == pytest.approx(unit.derived_stats().max_health * p["ShieldRatio"])
    dealt = sim.deal_damage(other, enemy, 100.0, DamageType.TRUE, source_label="auto")
    bonus = [e for e in sim.log.of_kind(EventKind.DAMAGE) if e.detail.get("via") == "solar"]
    assert [b.detail["type"] for b in bonus] == ["magic"]
    assert bonus[0].detail["pre_mitigation"] == pytest.approx(p["BonusMagicDamage"] * dealt, rel=1e-3)


def test_solar_three_star_bonuses_scale_with_unique_three_stars(data, registry):
    p = _tier(data, "DA_18_Solar", 3)
    need = int(p["NumThreeStarThreshold1"])
    sim, members, others, _ = _fight(data, registry, "DA_18_Solar", 3, others=need, star=3)
    # 3 Solars + `need` others, all 3-star and distinct: at least `need` unique 3-stars.
    count = 3 + need
    unit = others[0]
    expected_ratio = p["ShieldRatio"] + p["PercentIncreasePer3Star"] * count
    assert unit.shield_amount == pytest.approx(unit.derived_stats().max_health * expected_ratio)
    assert unit.derived_stats().armor == pytest.approx(
        _base(data, registry, unit).armor + p["Threshold1ArmorMagicResist"])

    # From `NumThreeStarThreshold2` unique 3-stars, part of the bonus is true.
    assert count >= p["NumThreeStarThreshold2"]
    enemy = sim.teams[1][0]
    sim.deal_damage(unit, enemy, 100.0, DamageType.TRUE, source_label="auto")
    hit = next(e.detail["amount"] for e in sim.log.of_kind(EventKind.DAMAGE)
               if e.detail.get("via") == "auto")
    bonus = (p["BonusMagicDamage"] + p["PercentIncreasePer3Star"] * count) * hit
    true = [e for e in sim.log.of_kind(EventKind.DAMAGE) if e.detail.get("via") == "solar_true"]
    assert true[0].detail["pre_mitigation"] == pytest.approx(
        bonus * p["Threshold2TrueDamageConversion"], rel=1e-3)


def test_thornmaiden_base_durability(data, registry):
    sim, (member,), (other,), _ = _fight(data, registry, "DA_18_ZyraUniqueTrait", 1)
    p = _tier(data, "DA_18_ZyraUniqueTrait", 1)
    assert other.derived_stats().durability == pytest.approx(p["BaseDurability"])


# --- the tranche as a whole -----------------------------------------------------

TRANCHE = (
    "DA_18_Adaptor", "DA_18_Battlemage", "DA_18_Brawler", "DA_18_Caustic",
    "DA_18_Defender", "DA_18_Executioner", "DA_18_Hunter", "DA_18_Inferno",
    "DA_18_Invoker", "DA_18_Lunar", "DA_18_Rapidfire", "DA_18_Slayer",
    "DA_18_Solar", "DA_18_Spellweaver", "DA_18_Vanguard", "DA_18_ZyraUniqueTrait",
    "DA_FloraFatalis18", "DA_Juggernaut18",
)


def test_every_trait_in_the_tranche_is_implemented():
    from engine.trait_effects import is_trait_implemented

    assert [t for t in TRANCHE if not is_trait_implemented(t)] == []


def test_partial_traits_are_named_not_silent():
    """A hook that models half a trait reads as whole to `is_trait_implemented`."""
    from engine.trait_effects import PARTIAL_TRAITS

    assert set(PARTIAL_TRAITS) == {"DA_18_Inferno", "DA_18_Solar", "DA_18_ZyraUniqueTrait"}
    assert all(PARTIAL_TRAITS.values())
