"""Tank damage-mana and the shield ambiguity (doc 99 entry 5.4).

Doc 01 sec 3.2 gives 1% of pre-mitigation plus 3% of post-mitigation damage,
capped at 42.5 per instance. "Post-mitigation" is unambiguous only when no
shield is involved: sources confirm the numbers but never say whether damage a
shield absorbed still counts. Both readings are implemented and selected by
``combat.damage_mana_post_mitigation_basis``.

These tests pin the numbers *and* prove the two readings genuinely differ, so
the config option cannot quietly become dead weight.
"""

from __future__ import annotations

import dataclasses

import pytest

from engine.combat import CombatSimulator, DamageType, place_team
from engine.hexgrid import Board
from engine.items import ItemRegistry
from engine.loader import load_all
from engine.unit import UnitInstance
from tests.paths import STARTER_DATA_DIR


@pytest.fixture(scope="module")
def data():
    return load_all(STARTER_DATA_DIR)


@pytest.fixture(scope="module")
def registry(data):
    return ItemRegistry(data.items, data.config.max_items_per_unit)


def tank_id(data):
    """A champion whose role generates mana from damage taken."""
    for champion in sorted(data.champions.values(), key=lambda c: c.id):
        if data.config.combat.generates_mana_from_damage(champion.role):
            return champion.id
    pytest.skip("no damage-mana role in the dataset")


def build(data, registry, *, basis="hp_lost", shield=0.0):
    """A tank alone against one attacker, optionally pre-shielded."""
    config = data.config.combat
    if basis != config.damage_mana_post_mitigation_basis:
        config = dataclasses.replace(config, damage_mana_post_mitigation_basis=basis)

    board = Board()
    tank = UnitInstance(data.champions[tank_id(data)], 1, [], registry=registry)
    foe = UnitInstance(data.champions[tank_id(data)], 1, [], registry=registry)
    place_team([tank], [(0, 3)], team=0, board=board)
    place_team([foe], [(0, 3)], team=1, board=board)
    sim = CombatSimulator([tank], [foe], data, seed=1, board=board, config=config)
    sim.step(config.tick_seconds)
    tank.current_mana = 0.0
    if shield:
        sim.apply_shield(tank, shield, None, source_label="test")
    return sim, tank, foe


def test_tank_gains_mana_from_unshielded_damage(data, registry):
    sim, tank, foe = build(data, registry)
    sim.deal_damage(foe, tank, 200.0, DamageType.TRUE, source_label="test")
    assert tank.current_mana > 0


def test_mana_follows_the_one_and_three_percent_formula(data, registry):
    """True damage skips mitigation, so pre-mitigation == hp lost."""
    sim, tank, foe = build(data, registry)
    sim.deal_damage(foe, tank, 200.0, DamageType.TRUE, source_label="test")
    cfg = data.config.combat
    expected = 200.0 * cfg.damage_mana_pre_mitigation_pct + 200.0 * cfg.damage_mana_post_mitigation_pct
    assert tank.current_mana == pytest.approx(expected, rel=1e-6)


def test_mana_gain_is_capped_per_instance(data, registry):
    sim, tank, foe = build(data, registry)
    sim.deal_damage(foe, tank, 100_000.0, DamageType.TRUE, source_label="test")
    assert tank.current_mana == pytest.approx(
        data.config.combat.damage_mana_cap_per_instance
    )


def test_non_tank_roles_gain_no_mana_from_damage(data, registry):
    sim, tank, foe = build(data, registry)
    non_tank = next(
        c for c in data.champions.values()
        if not data.config.combat.generates_mana_from_damage(c.role)
    )
    victim = UnitInstance(non_tank, 1, [], registry=registry)
    victim.position = tank.position
    victim.team = 0
    before = victim.current_mana
    sim._mana_from_damage_taken(victim, 500.0, 500.0, 500.0)
    assert victim.current_mana == before


# --- the ambiguity itself ------------------------------------------------


def test_hp_lost_basis_suppresses_the_post_mitigation_term_behind_a_shield(data, registry):
    """Default reading: a fully-absorbed hit only pays the 1% pre-mitigation term."""
    sim, tank, foe = build(data, registry, basis="hp_lost", shield=10_000.0)
    sim.deal_damage(foe, tank, 200.0, DamageType.TRUE, source_label="test")
    assert tank.current_hp == tank.derived_stats().max_health, "shield should absorb it"
    expected = 200.0 * data.config.combat.damage_mana_pre_mitigation_pct
    assert tank.current_mana == pytest.approx(expected, rel=1e-6)


def test_after_resists_basis_pays_the_full_term_behind_a_shield(data, registry):
    """Alternative reading: absorbed damage still counts as damage taken."""
    sim, tank, foe = build(data, registry, basis="after_resists", shield=10_000.0)
    sim.deal_damage(foe, tank, 200.0, DamageType.TRUE, source_label="test")
    cfg = data.config.combat
    expected = 200.0 * cfg.damage_mana_pre_mitigation_pct + 200.0 * cfg.damage_mana_post_mitigation_pct
    assert tank.current_mana == pytest.approx(expected, rel=1e-6)


def test_the_two_bases_differ_only_when_a_shield_is_present(data, registry):
    """Without a shield the readings must agree, or one of them is wrong."""
    results = {}
    for basis in ("hp_lost", "after_resists"):
        sim, tank, foe = build(data, registry, basis=basis)
        sim.deal_damage(foe, tank, 200.0, DamageType.TRUE, source_label="test")
        results[basis] = tank.current_mana
    assert results["hp_lost"] == pytest.approx(results["after_resists"])


def test_shielded_tank_still_generates_some_mana_under_either_basis(data, registry):
    """A fully-shielded tank is never cut off entirely -- the 1% term applies."""
    for basis in ("hp_lost", "after_resists"):
        sim, tank, foe = build(data, registry, basis=basis, shield=10_000.0)
        sim.deal_damage(foe, tank, 200.0, DamageType.TRUE, source_label="test")
        assert tank.current_mana > 0, basis
