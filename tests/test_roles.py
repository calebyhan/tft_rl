"""Per-role mechanics from Riot's role revamp (doc 99 entry 9.2).

Riot documents six team roles, each with a mana-per-attack value and, for some,
an extra perk:

    Tank 5 (also builds mana from damage taken), Fighter 10 (+10% omnivamp),
    Assassin 10, Marksman 10, Caster 7 (+2 mana/second), Specialist unique.

Doc 01 sec 3.2 listed only five, omitting Specialist, and modelled none of the
perks. These tests pin the two perks that are numerically specified, plus the
Specialist role's existence.
"""

from __future__ import annotations

import pytest

from engine.combat import CombatSimulator, DamageType, place_team
from engine.hexgrid import Board
from engine.items import ItemRegistry
from engine.loader import load_all
from engine.schema import ROLES
from engine.unit import UnitInstance
from tests.paths import REAL_DATA_DIR, STARTER_DATA_DIR


@pytest.fixture(scope="module")
def data():
    return load_all(STARTER_DATA_DIR)


@pytest.fixture(scope="module")
def registry(data):
    return ItemRegistry(data.items, data.config.max_items_per_unit)


@pytest.fixture(scope="module")
def real():
    return load_all(REAL_DATA_DIR)


def duel(data, registry, a_id, b_id, a_star=1):
    board = Board()
    a = UnitInstance(data.champions[a_id], a_star, [], registry=registry)
    b = UnitInstance(data.champions[b_id], 1, [], registry=registry)
    place_team([a], [(0, 3)], team=0, board=board)
    place_team([b], [(0, 3)], team=1, board=board)
    sim = CombatSimulator([a], [b], data, seed=1, board=board)
    return sim, a, b


def champion_with_role(data, role):
    for champion in sorted(data.champions.values(), key=lambda c: c.id):
        if champion.role == role:
            return champion.id
    return None


# --- taxonomy ------------------------------------------------------------


def test_specialist_is_a_modelled_role():
    """Riot's sixth team role; omitting it forced those champions elsewhere."""
    assert "Specialist" in ROLES
    assert len(ROLES) == 6


def test_config_assigns_mana_per_attack_to_every_role(data):
    for role in ROLES:
        assert role in data.config.role_mana_per_attack


def test_documented_mana_per_attack_values(data):
    """Straight from Riot's role revamp article."""
    mana = data.config.role_mana_per_attack
    assert mana["Tank"] == 5
    assert mana["Caster"] == 7
    for role in ("Fighter", "Assassin", "Marksman"):
        assert mana[role] == 10


def test_real_dataset_uses_the_specialist_role(real):
    """Set 17 ships two ADSpecialist champions; they must not read as Casters."""
    specialists = [c.id for c in real.champions.values() if c.role == "Specialist"]
    assert specialists, "expected Specialists in the real dataset"
    for cid in specialists:
        assert real.champions[cid].stats.mana_per_attack == 0


# --- Caster mana regeneration -------------------------------------------


def test_casters_regenerate_mana_over_time(data, registry):
    caster = champion_with_role(data, "Caster")
    if caster is None:
        pytest.skip("no Caster in the dataset")
    sim, unit, _ = duel(data, registry, caster, caster)
    sim.step(sim.config.tick_seconds)
    unit.current_mana = 0.0
    dt = sim.config.tick_seconds
    for _ in range(20):
        sim.step(dt)
    expected = sim.config.mana_per_second("Caster") * dt * 20
    assert unit.current_mana >= expected * 0.9, "caster should regenerate mana"


def test_non_casters_do_not_regenerate_mana(data, registry):
    tank = champion_with_role(data, "Tank")
    if tank is None:
        pytest.skip("no Tank in the dataset")
    assert data.config.combat.mana_per_second("Tank") == 0.0


def test_mana_regeneration_continues_while_stunned(data, registry):
    """It is a passive, not an on-action effect."""
    caster = champion_with_role(data, "Caster")
    if caster is None:
        pytest.skip("no Caster in the dataset")
    sim, unit, _ = duel(data, registry, caster, caster)
    sim.step(sim.config.tick_seconds)
    unit.current_mana = 0.0
    sim.apply_stun(unit, 5.0, source_label="test")
    for _ in range(10):
        sim.step(sim.config.tick_seconds)
    assert unit.current_mana > 0


# --- omnivamp ------------------------------------------------------------


def test_fighters_heal_for_a_share_of_damage_dealt(data, registry):
    fighter = champion_with_role(data, "Fighter")
    tank = champion_with_role(data, "Tank")
    if fighter is None or tank is None:
        pytest.skip("dataset lacks a Fighter or Tank")
    sim, attacker, victim = duel(data, registry, fighter, tank)
    sim.step(sim.config.tick_seconds)
    attacker.current_hp = attacker.derived_stats().max_health / 2
    before = attacker.current_hp
    sim.deal_damage(attacker, victim, 200.0, DamageType.TRUE, source_label="test")
    share = sim.config.omnivamp_for("Fighter")
    assert share > 0
    assert attacker.current_hp == pytest.approx(before + 200.0 * share, rel=1e-6)


def test_roles_without_omnivamp_do_not_heal(data, registry):
    tank = champion_with_role(data, "Tank")
    if tank is None:
        pytest.skip("no Tank in the dataset")
    sim, attacker, victim = duel(data, registry, tank, tank)
    sim.step(sim.config.tick_seconds)
    attacker.current_hp = attacker.derived_stats().max_health / 2
    before = attacker.current_hp
    sim.deal_damage(attacker, victim, 200.0, DamageType.TRUE, source_label="test")
    assert attacker.current_hp == before


def test_omnivamp_heals_nothing_when_a_shield_absorbs_the_hit(data, registry):
    """Measured on damage that landed, so an absorbed hit sustains nobody."""
    fighter = champion_with_role(data, "Fighter")
    tank = champion_with_role(data, "Tank")
    if fighter is None or tank is None:
        pytest.skip("dataset lacks a Fighter or Tank")
    sim, attacker, victim = duel(data, registry, fighter, tank)
    sim.step(sim.config.tick_seconds)
    sim.apply_shield(victim, 10_000.0, None, source_label="test")
    attacker.current_hp = attacker.derived_stats().max_health / 2
    before = attacker.current_hp
    sim.deal_damage(attacker, victim, 200.0, DamageType.TRUE, source_label="test")
    assert attacker.current_hp == before


def test_omnivamp_cannot_overheal(data, registry):
    fighter = champion_with_role(data, "Fighter")
    tank = champion_with_role(data, "Tank")
    if fighter is None or tank is None:
        pytest.skip("dataset lacks a Fighter or Tank")
    sim, attacker, victim = duel(data, registry, fighter, tank)
    sim.step(sim.config.tick_seconds)
    cap = attacker.derived_stats().max_health
    sim.deal_damage(attacker, victim, 5000.0, DamageType.TRUE, source_label="test")
    assert attacker.current_hp <= cap
