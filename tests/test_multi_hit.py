"""Multi-hit ability effects (doc 99 entry 11.3).

Real abilities frequently fire a volley -- "@NumRockets@ rockets, each dealing
X" -- and modelling that as a single hit understates a carry's output by the
volley size. Verified against Riot's own text: Bel'Veth throws 12 slashes,
Kai'Sa fires 16 missiles.

These drive the effects directly with explicit params, so they test the effect
rather than any particular champion's data.
"""

from __future__ import annotations

import pytest

from engine import effects
from engine.combat import CombatSimulator, EffectContext, EventKind, place_team
from engine.hexgrid import Board
from engine.items import ItemRegistry
from engine.loader import load_all
from engine.unit import UnitInstance
from tests.paths import STARTER_DATA_DIR

VOLLEY = "ability_volley"


@pytest.fixture(scope="module")
def data():
    return load_all(STARTER_DATA_DIR)


@pytest.fixture(scope="module")
def registry(data):
    return ItemRegistry(data.items, data.config.max_items_per_unit)


@pytest.fixture
def make(data, registry):
    def _make(champion_id, star=1):
        return UnitInstance(data.champions[champion_id], star, [], registry=registry)

    return _make


@pytest.fixture
def arena(data, make):
    """Build a fight: ``arena(attacker_id, [victim_slots])`` -> (sim, attacker, victims)."""

    def _arena(attacker_id, victim_slots, *, attacker_star=1, victim_id="TFT17_Poppy"):
        board = Board()
        attacker = make(attacker_id, attacker_star)
        victims = [make(victim_id, 1) for _ in victim_slots]
        place_team([attacker], [(0, 3)], team=0, board=board)
        place_team(victims, list(victim_slots), team=1, board=board)
        sim = CombatSimulator([attacker], victims, data, seed=1, board=board)
        # One tick so the simulator is prepared (units acquire targets).
        sim.step(data.config.combat.tick_seconds)
        return sim, attacker, victims

    return _arena


def cast(sim, source, target, effect_id, params, star=1):
    effects.EFFECTS[effect_id](
        EffectContext(
            sim=sim, source=source, target=target, params=params, star_level=star
        )
    )


def volley_hits(sim):
    return [
        e
        for e in sim.log.events
        if e.kind is EventKind.DAMAGE and e.detail.get("via") == VOLLEY
    ]


def test_one_damage_instance_per_hit(arena):
    sim, attacker, victims = arena("TFT17_Jinx", [(0, 3)])
    before = victims[0].current_hp
    cast(sim, attacker, victims[0], "multi_hit_physical_damage",
         {"ad_ratio": 0.5, "hits": 4})
    assert len(volley_hits(sim)) == 4
    assert victims[0].current_hp < before


def test_total_damage_scales_with_the_hit_count(arena):
    """The whole point of the fix: four hits must hurt four times as much."""

    def total(hits):
        sim, attacker, victims = arena("TFT17_Jinx", [(0, 3)])
        before = victims[0].current_hp
        cast(sim, attacker, victims[0], "multi_hit_physical_damage",
             {"ad_ratio": 0.2, "hits": hits})
        return before - victims[0].current_hp

    assert total(4) == pytest.approx(total(1) * 4, rel=0.02)


def test_defaults_to_a_single_hit(arena):
    """An ability declaring no count must behave like the single-hit effect."""
    sim, attacker, victims = arena("TFT17_Jinx", [(0, 3)])
    cast(sim, attacker, victims[0], "multi_hit_physical_damage", {"ad_ratio": 0.5})
    assert len(volley_hits(sim)) == 1


def test_volley_spreads_across_targets(arena):
    sim, attacker, victims = arena("TFT17_Jinx", [(0, 3), (0, 4)])
    cast(sim, attacker, victims[0], "multi_hit_physical_damage",
         {"ad_ratio": 0.5, "hits": 4, "targets": 2})
    struck = {e.target for e in volley_hits(sim)}
    assert struck == {victims[0].uid, victims[1].uid}


def test_single_target_volley_hits_only_the_primary(arena):
    sim, attacker, victims = arena("TFT17_Jinx", [(0, 3), (0, 4)])
    cast(sim, attacker, victims[0], "multi_hit_physical_damage",
         {"ad_ratio": 0.5, "hits": 4})
    assert {e.target for e in volley_hits(sim)} == {victims[0].uid}


def test_volley_is_not_wasted_on_a_dead_target(arena):
    """A killed target must not silently absorb the rest of the volley."""
    sim, attacker, victims = arena("TFT17_Jinx", [(0, 3), (0, 4)], attacker_star=3)
    victims[0].current_hp = 1.0
    cast(sim, attacker, victims[0], "multi_hit_physical_damage",
         {"ad_ratio": 5.0, "hits": 6, "targets": 2}, star=3)
    assert not victims[0].alive
    assert victims[1].current_hp < victims[1].derived_stats().max_health


def test_magic_volley_uses_flat_damage(arena):
    sim, attacker, victims = arena("TFT17_Jinx", [(0, 3)])
    before = victims[0].current_hp
    cast(sim, attacker, victims[0], "multi_hit_magic_damage",
         {"damage": 50.0, "hits": 3})
    assert len(volley_hits(sim)) == 3
    assert victims[0].current_hp < before


def test_no_target_is_a_no_op(arena):
    """Effects must never crash on a missing target (doc 03 sec 2.4)."""
    sim, attacker, _ = arena("TFT17_Jinx", [(0, 3)])
    cast(sim, attacker, None, "multi_hit_physical_damage", {"ad_ratio": 0.5, "hits": 3})
    assert volley_hits(sim) == []


def test_zero_ratio_deals_nothing(arena):
    sim, attacker, victims = arena("TFT17_Jinx", [(0, 3)])
    before = victims[0].current_hp
    cast(sim, attacker, victims[0], "multi_hit_physical_damage",
         {"ad_ratio": 0.0, "hits": 5})
    assert volley_hits(sim) == []
    assert victims[0].current_hp == before
