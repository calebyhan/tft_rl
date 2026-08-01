"""Combat simulator tests (milestone 3, doc 01 sec 3).

Each mechanic from doc 01 sec 3 is asserted against the structured combat log
rather than against final HP totals alone, so a failure points at the specific
step of the tick loop that broke.
"""

from __future__ import annotations

import math

import pytest

from engine import effects
from engine.combat import (
    DEFAULT_TARGETING_RULE,
    CombatSimulator,
    DamageType,
    EventKind,
    place_team,
)
from engine.hexgrid import Board, distance
from engine.items import ItemRegistry
from engine.loader import load_all
from engine.schema import GameData
from engine.stats import StatBonuses
from engine.unit import StatusEffect, UnitInstance
from tests.paths import STARTER_DATA_DIR


@pytest.fixture(scope="module")
def data() -> GameData:
    return load_all(STARTER_DATA_DIR)


@pytest.fixture(scope="module")
def registry(data) -> ItemRegistry:
    return ItemRegistry(data.items, data.config.max_items_per_unit)


@pytest.fixture
def make(data, registry):
    def _make(champion_id, star=1, item_ids=()):
        return UnitInstance(
            data.champions[champion_id],
            star,
            [data.items[i] for i in item_ids],
            registry=registry,
        )

    return _make


@pytest.fixture
def duel(data, make):
    """Build a 1v1: ``duel(a_id, b_id)`` -> (sim, unit_a, unit_b).

    Both units are placed on the centre column of their own front row, so they
    start adjacent across the centre line.
    """

    def _duel(a_id, b_id, *, a_star=1, b_star=1, a_items=(), b_items=(), seed=1,
              a_slot=(0, 3), b_slot=(0, 3), board=None):
        board = board or Board()
        a = make(a_id, a_star, a_items)
        b = make(b_id, b_star, b_items)
        place_team([a], [a_slot], team=0, board=board)
        place_team([b], [b_slot], team=1, board=board)
        sim = CombatSimulator([a], [b], data, seed=seed, board=board)
        return sim, a, b

    return _duel


def kinds(log, *wanted):
    return [e for e in log.events if e.kind in set(wanted)]


# --- setup and determinism ----------------------------------------------


def test_combat_start_is_logged_for_both_teams(duel):
    sim, a, b = duel("TFT17_Poppy", "TFT17_Poppy")
    sim.run()
    starts = kinds(sim.log, EventKind.COMBAT_START)
    assert len(starts) == 2
    assert {s.detail["team"] for s in starts} == {0, 1}


def test_units_start_at_full_hp_and_starting_mana(duel):
    sim, a, b = duel("TFT17_Poppy", "TFT17_Jinx")
    assert a.current_hp == 650 and a.current_mana == 30
    assert b.current_hp == 800 and b.current_mana == 0


def test_unplaced_unit_is_rejected(data, make):
    a, b = make("TFT17_Jinx"), make("TFT17_Poppy")
    place_team([b], [(0, 0)], team=1)
    with pytest.raises(ValueError, match="no position"):
        CombatSimulator([a], [b], data)


def test_overlapping_units_are_rejected(data, make):
    board = Board()
    a, b = make("TFT17_Jinx"), make("TFT17_Poppy")
    a.position = b.position = board.to_combat(0, 0, 3)
    a.team, b.team = 0, 0
    with pytest.raises(ValueError, match="two units occupy"):
        CombatSimulator([a], [b], data)


def test_same_seed_gives_an_identical_fight(duel):
    """Same seed, same build order -> identical decision stream.

    Compared on (time, kind, detail) rather than rendered text, since unit
    uids come from a process-global counter and differ between fights.
    """

    # These details embed the display name, which carries the uid.
    name_bearing = {"killed_by", "survivors"}

    def run(seed):
        sim, _, _ = duel("TFT17_Jinx", "TFT17_Leona", seed=seed)
        result = sim.run()
        base = min(u.uid for u in sim.units)
        rel = lambda uid: None if uid is None else uid - base  # noqa: E731
        stream = [
            (
                e.t,
                e.kind,
                rel(e.actor),
                rel(e.target),
                sorted(
                    (k, v) for k, v in e.detail.items() if k not in name_bearing
                ),
            )
            for e in sim.log.events
        ]
        return result.winner, result.duration, stream

    assert run(7) == run(7)


def test_different_seeds_diverge(duel):
    """Crit rolls differ, so fights of the same matchup should not be identical."""
    renders = set()
    for seed in range(6):
        sim, _, _ = duel("TFT17_Jinx", "TFT17_Leona", seed=seed)
        sim.run()
        renders.add(sim.log.render())
    assert len(renders) > 1


def test_simulator_does_not_touch_global_random(duel):
    import random as global_random

    global_random.seed(1234)
    expected = [global_random.random() for _ in range(3)]

    global_random.seed(1234)
    sim, _, _ = duel("TFT17_Jinx", "TFT17_Leona", seed=99)
    sim.run()
    assert [global_random.random() for _ in range(3)] == expected


# --- targeting (doc 01 sec 3.1 step 3) ----------------------------------


def test_default_targeting_rule_is_nearest(duel):
    sim, a, b = duel("TFT17_Poppy", "TFT17_Poppy")
    assert getattr(a, "targeting_rule", DEFAULT_TARGETING_RULE) == "nearest"


def test_unit_targets_the_nearest_enemy(data, make):
    """Three enemies at different distances: the closest is picked."""
    board = Board()
    hero = make("TFT17_Jinx")
    near = make("TFT17_Poppy")
    far = make("TFT17_Blitzcrank")
    place_team([hero], [(0, 3)], team=0, board=board)
    place_team([near, far], [(0, 3), (3, 0)], team=1, board=board)
    sim = CombatSimulator([hero], [near, far], data, seed=0, board=board)
    sim.step(sim.config.tick_seconds)
    assert hero.target_uid == near.uid


def test_target_switches_when_the_current_target_dies(data, make):
    board = Board()
    hero = make("TFT17_Ornn", 3)
    weak = make("TFT17_Kindred")
    other = make("TFT17_Kindred")
    place_team([hero], [(0, 3)], team=0, board=board)
    place_team([weak, other], [(0, 3), (0, 4)], team=1, board=board)
    sim = CombatSimulator([hero], [weak, other], data, seed=0, board=board)
    sim.run()
    targets = [e.target for e in kinds(sim.log, EventKind.TARGET) if e.actor == hero.uid]
    assert weak.uid in targets and other.uid in targets


def test_targeting_is_sticky_while_chasing(data, make):
    """A unit commits to its target rather than flipping to whatever is nearest.

    The chaser starts nearest to `first`; `second` is placed so it becomes the
    closer enemy partway through the chase. Sticky targeting must ignore that.
    """
    board = Board()
    chaser = make("TFT17_Poppy")          # melee, must walk
    first = make("TFT17_Kindred")
    second = make("TFT17_Kindred")
    place_team([chaser], [(3, 0)], team=0, board=board)
    place_team([first, second], [(3, 0), (3, 6)], team=1, board=board)
    sim = CombatSimulator([chaser], [first, second], data, seed=0, board=board)

    sim.step(sim.config.tick_seconds)
    locked = chaser.target_uid
    assert locked is not None

    for _ in range(40):
        if not sim.by_uid[locked].alive:
            break
        sim.step(sim.config.tick_seconds)
        assert chaser.target_uid == locked, "target switched mid-chase"


def test_target_is_dropped_when_it_becomes_unreachable(data, make):
    """Sticky targeting must not deadlock on a target with no path to it."""
    board = Board()
    chaser = make("TFT17_Poppy")
    walled_off = make("TFT17_Kindred")
    reachable = make("TFT17_Kindred")
    # A full wall of enemies between the chaser and `walled_off`.
    wall = [make("TFT17_Ornn") for _ in range(7)]
    place_team([chaser], [(3, 3)], team=0, board=board)
    place_team(
        [walled_off, reachable, *wall],
        [(3, 3), (3, 0)] + [(0, c) for c in range(7)],
        team=1,
        board=board,
    )
    sim = CombatSimulator([chaser], [walled_off, reachable, *wall], data, seed=0, board=board)
    chaser.target_uid = walled_off.uid
    for _ in range(30):
        sim.step(sim.config.tick_seconds)
    # It must have engaged *something* rather than standing still forever.
    assert chaser.target_uid is not None


def test_alternative_targeting_rule_is_honoured(data, make):
    board = Board()
    hero = make("TFT17_Jinx")
    hero.targeting_rule = "lowest_health"
    tanky = make("TFT17_Ornn")
    squishy = make("TFT17_Kindred")
    place_team([hero], [(0, 3)], team=0, board=board)
    # The tanky unit is placed closer, so "nearest" would pick it instead.
    place_team([tanky, squishy], [(0, 3), (2, 0)], team=1, board=board)
    sim = CombatSimulator([hero], [tanky, squishy], data, seed=0, board=board)
    sim.step(sim.config.tick_seconds)
    assert hero.target_uid == squishy.uid


def test_unknown_targeting_rule_falls_back_instead_of_crashing(data, make, caplog):
    board = Board()
    hero = make("TFT17_Jinx")
    hero.targeting_rule = "nonsense"
    foe = make("TFT17_Poppy")
    place_team([hero], [(0, 3)], team=0, board=board)
    place_team([foe], [(0, 3)], team=1, board=board)
    sim = CombatSimulator([hero], [foe], data, seed=0, board=board)
    with caplog.at_level("WARNING"):
        sim.step(sim.config.tick_seconds)
    assert hero.target_uid == foe.uid
    assert "nonsense" in caplog.text


# --- movement (doc 01 sec 3.1 step 4) ------------------------------------


def test_melee_unit_moves_toward_a_distant_target(duel):
    sim, a, b = duel("TFT17_Poppy", "TFT17_Poppy", a_slot=(3, 0), b_slot=(3, 0))
    start_gap = distance(a.position, b.position)
    assert start_gap > 1
    sim.run()
    moves = [e for e in kinds(sim.log, EventKind.MOVE) if e.actor == a.uid]
    assert moves, "melee unit should have had to walk"


def test_each_move_advances_exactly_one_hex(duel):
    sim, a, b = duel("TFT17_Poppy", "TFT17_Poppy", a_slot=(3, 0), b_slot=(3, 6))
    sim.run()
    for event in kinds(sim.log, EventKind.MOVE):
        assert distance(
            _parse_hex(event.detail["from"]), _parse_hex(event.detail["to"])
        ) == 1


def _parse_hex(text):
    from engine.hexgrid import Hex

    q, r = text.removeprefix("Hex(").removesuffix(")").split(",")
    return Hex(int(q), int(r))


def test_movement_rate_matches_the_configured_speed(duel):
    """One hex per ``1 / movement_hexes_per_second``, not one hex per tick."""
    sim, a, b = duel("TFT17_Poppy", "TFT17_Poppy", a_slot=(3, 0), b_slot=(3, 6))
    for _ in range(40):
        sim.step(sim.config.tick_seconds)
    moves = [e for e in kinds(sim.log, EventKind.MOVE) if e.actor == a.uid]
    assert len(moves) >= 3
    gaps = [round(moves[i + 1].t - moves[i].t, 6) for i in range(len(moves) - 1)]
    assert gaps and all(
        math.isclose(g, sim.config.seconds_per_hex, abs_tol=sim.config.tick_seconds)
        for g in gaps
    )


def test_ranged_unit_in_range_never_moves(duel):
    """Jinx has 4 range and starts adjacent, so she should stand still."""
    sim, jinx, foe = duel("TFT17_Jinx", "TFT17_Leona")
    start = jinx.position
    sim.run()
    assert jinx.position == start
    assert not [e for e in kinds(sim.log, EventKind.MOVE) if e.actor == jinx.uid]


def test_rooted_unit_cannot_move(duel):
    sim, a, b = duel("TFT17_Poppy", "TFT17_Poppy", a_slot=(3, 0), b_slot=(3, 6))
    a.add_status(StatusEffect("root", remaining=None, root=True))
    start = a.position
    for _ in range(30):
        sim.step(sim.config.tick_seconds)
    assert a.position == start


def test_units_do_not_walk_through_each_other(data, make):
    board = Board()
    walker = make("TFT17_Poppy")
    blocker_a = make("TFT17_Ornn")
    target = make("TFT17_Kindred")
    place_team([walker], [(3, 3)], team=0, board=board)
    place_team([blocker_a, target], [(0, 3), (3, 3)], team=1, board=board)
    sim = CombatSimulator([walker], [blocker_a, target], data, seed=0, board=board)
    occupied_positions = set()
    for _ in range(60):
        sim.step(sim.config.tick_seconds)
        living = [u.position for u in sim.units if u.alive]
        assert len(living) == len(set(living)), "two units share a hex"
        occupied_positions.update(living)


# --- attack timers (doc 01 sec 3.1 step 5) ------------------------------


def test_attack_interval_matches_attack_speed(duel):
    """Jinx at 0.75 attacks/sec should fire every ~1.333s."""
    sim, jinx, foe = duel("TFT17_Jinx", "TFT17_Ornn", b_star=3)
    for _ in range(120):
        sim.step(sim.config.tick_seconds)
    attacks = [e for e in kinds(sim.log, EventKind.ATTACK) if e.actor == jinx.uid]
    assert len(attacks) >= 3
    gaps = [attacks[i + 1].t - attacks[i].t for i in range(len(attacks) - 1)]
    expected = 1 / 0.75
    assert all(
        math.isclose(g, expected, abs_tol=sim.config.tick_seconds * 1.01) for g in gaps
    ), gaps


def test_attack_speed_buff_shortens_the_interval(duel):
    slow_sim, slow, _ = duel("TFT17_Jinx", "TFT17_Ornn", b_star=3, seed=3)
    fast_sim, fast, _ = duel("TFT17_Jinx", "TFT17_Ornn", b_star=3, seed=3)
    fast.add_status(
        StatusEffect("buff", remaining=None, bonuses=StatBonuses({"attack_speed_pct": 1.0}))
    )
    for _ in range(80):
        slow_sim.step(slow_sim.config.tick_seconds)
        fast_sim.step(fast_sim.config.tick_seconds)
    slow_attacks = len([e for e in kinds(slow_sim.log, EventKind.ATTACK) if e.actor == slow.uid])
    fast_attacks = len([e for e in kinds(fast_sim.log, EventKind.ATTACK) if e.actor == fast.uid])
    assert fast_attacks > slow_attacks


def test_disarmed_unit_does_not_attack(duel):
    sim, a, b = duel("TFT17_Poppy", "TFT17_Ornn", b_star=3)
    a.add_status(StatusEffect("disarm", remaining=None, disarm=True))
    for _ in range(60):
        sim.step(sim.config.tick_seconds)
    assert not [e for e in kinds(sim.log, EventKind.ATTACK) if e.actor == a.uid]


def test_stunned_unit_does_nothing(duel):
    sim, a, b = duel("TFT17_Poppy", "TFT17_Ornn", a_slot=(3, 0), b_star=3)
    a.add_status(StatusEffect("stun", remaining=None, stun=True))
    start = a.position
    for _ in range(60):
        sim.step(sim.config.tick_seconds)
    assert a.position == start
    assert not [e for e in kinds(sim.log, EventKind.ATTACK) if e.actor == a.uid]


def test_ranged_attack_spawns_a_projectile_melee_does_not(duel):
    ranged_sim, jinx, _ = duel("TFT17_Jinx", "TFT17_Ornn", b_star=3)
    for _ in range(60):
        ranged_sim.step(ranged_sim.config.tick_seconds)
    assert kinds(ranged_sim.log, EventKind.PROJECTILE_LAUNCH)

    melee_sim, poppy, _ = duel("TFT17_Poppy", "TFT17_Ornn", b_star=3)
    for _ in range(60):
        melee_sim.step(melee_sim.config.tick_seconds)
    assert kinds(melee_sim.log, EventKind.ATTACK)
    assert not kinds(melee_sim.log, EventKind.PROJECTILE_LAUNCH)


def test_projectile_damage_lands_after_its_travel_time(duel):
    sim, jinx, foe = duel("TFT17_Jinx", "TFT17_Ornn", b_star=3)
    for _ in range(60):
        sim.step(sim.config.tick_seconds)
    launch = kinds(sim.log, EventKind.PROJECTILE_LAUNCH)[0]
    damage = [
        e for e in kinds(sim.log, EventKind.DAMAGE)
        if e.actor == jinx.uid and e.detail["via"] == "auto"
    ][0]
    assert damage.t > launch.t
    assert math.isclose(
        damage.t - launch.t, launch.detail["travel"], abs_tol=sim.config.tick_seconds * 1.01
    )


def test_projectile_fizzles_if_its_target_dies_in_flight(data, make):
    """A shot at an already-dead unit deals no damage and grants no mana."""
    board = Board()
    sniper = make("TFT17_Jinx", 3)
    victim = make("TFT17_Kindred")
    place_team([sniper], [(3, 3)], team=0, board=board)
    place_team([victim], [(3, 3)], team=1, board=board)
    sim = CombatSimulator([sniper], [victim], data, seed=0, board=board)
    # Kill the target while a projectile is mid-flight.
    while not sim.projectiles and sim.tick_index < 200:
        sim.step(sim.config.tick_seconds)
    assert sim.projectiles
    victim.alive = False
    mana_before = sniper.current_mana
    for _ in range(20):
        sim.step(sim.config.tick_seconds)
    assert kinds(sim.log, EventKind.PROJECTILE_FIZZLE)
    assert sniper.current_mana == mana_before


# --- mana (doc 01 sec 3.2) -----------------------------------------------


def test_mana_per_attack_is_role_based(duel):
    """Jinx grants 12/attack (explicit override); Poppy, a Tank, grants 5."""
    sim, jinx, _ = duel("TFT17_Jinx", "TFT17_Ornn", b_star=3)
    for _ in range(60):
        sim.step(sim.config.tick_seconds)
    gains = [
        e for e in kinds(sim.log, EventKind.MANA)
        if e.actor == jinx.uid and e.detail["reason"] == "attack"
    ]
    assert gains and all(g.detail["amount"] == 12 for g in gains)

    sim2, poppy, _ = duel("TFT17_Poppy", "TFT17_Ornn", b_star=3)
    for _ in range(60):
        sim2.step(sim2.config.tick_seconds)
    poppy_gains = [
        e for e in kinds(sim2.log, EventKind.MANA)
        if e.actor == poppy.uid and e.detail["reason"] == "attack"
    ]
    assert poppy_gains and all(g.detail["amount"] == 5 for g in poppy_gains)


def test_tanks_gain_mana_from_damage_taken(duel):
    sim, tank, attacker = duel("TFT17_Poppy", "TFT17_Jinx")
    for _ in range(60):
        sim.step(sim.config.tick_seconds)
    assert [
        e for e in kinds(sim.log, EventKind.MANA)
        if e.actor == tank.uid and e.detail["reason"] == "damage_taken"
    ]


def test_non_tanks_do_not_gain_mana_from_damage_taken(duel):
    """Doc 01 sec 3.2: only Tanks convert damage taken into mana."""
    sim, marksman, attacker = duel("TFT17_Kindred", "TFT17_Ornn", b_star=3)
    for _ in range(60):
        sim.step(sim.config.tick_seconds)
    assert not [
        e for e in kinds(sim.log, EventKind.MANA)
        if e.actor == marksman.uid and e.detail["reason"] == "damage_taken"
    ]


def test_damage_mana_formula_and_cap(duel):
    """1% pre-mitigation + 3% HP lost, capped per instance."""
    sim, tank, _ = duel("TFT17_Poppy", "TFT17_Jinx")
    cfg = sim.config
    before = tank.current_mana
    hp_lost = sim.deal_damage(None, tank, 1000.0, DamageType.TRUE)
    expected = min(
        1000.0 * cfg.damage_mana_pre_mitigation_pct
        + hp_lost * cfg.damage_mana_post_mitigation_pct,
        cfg.damage_mana_cap_per_instance,
    )
    assert tank.current_mana - before == pytest.approx(expected)


def test_huge_hit_is_capped_at_the_configured_ceiling(duel):
    sim, tank, _ = duel("TFT17_Ornn", "TFT17_Jinx", a_star=3)
    before = tank.current_mana
    sim.deal_damage(None, tank, 100000.0, DamageType.TRUE)
    assert tank.current_mana - before == pytest.approx(
        sim.config.damage_mana_cap_per_instance
    )


def test_cast_consumes_max_mana_and_carries_overflow(duel):
    """Doc 01 sec 3.2: mana above the cap carries into the next bar."""
    sim, caster, foe = duel("TFT17_Kindred", "TFT17_Ornn", b_star=3)
    caster.current_mana = caster.derived_stats().max_mana + 13
    sim.step(sim.config.tick_seconds)
    assert kinds(sim.log, EventKind.CAST)
    assert caster.current_mana == pytest.approx(13)


def test_mana_casters_do_not_cast_below_full(duel):
    sim, caster, foe = duel("TFT17_Kindred", "TFT17_Ornn", b_star=3)
    caster.current_mana = caster.derived_stats().max_mana - 1
    sim.step(sim.config.tick_seconds)
    assert not kinds(sim.log, EventKind.CAST)


# --- casting (doc 01 sec 3.1 step 6) ------------------------------------


def test_cooldown_caster_fires_on_a_timer_not_on_mana(duel):
    """Talon casts every 6s regardless of mana."""
    sim, talon, foe = duel("TFT17_Talon", "TFT17_Ornn", b_star=3)
    for _ in range(int(14 / sim.config.tick_seconds)):
        sim.step(sim.config.tick_seconds)
    casts = [e for e in kinds(sim.log, EventKind.CAST) if e.actor == talon.uid]
    assert len(casts) >= 2
    gap = casts[1].t - casts[0].t
    assert math.isclose(gap, 6.0, abs_tol=sim.config.tick_seconds * 2)


def test_cast_deals_ability_damage(duel):
    sim, caster, foe = duel("TFT17_Kindred", "TFT17_Ornn", b_star=3)
    caster.current_mana = caster.derived_stats().max_mana
    sim.step(sim.config.tick_seconds)
    ability_damage = [
        e for e in kinds(sim.log, EventKind.DAMAGE) if e.detail["via"] == "ability"
    ]
    assert ability_damage
    assert ability_damage[0].detail["type"] == "magic"


def test_ability_damage_scales_with_ability_power(duel):
    """Kindred's 180 base at 1.0 AP ratio: +50 AP means 1.5x."""
    plain_sim, plain, _ = duel("TFT17_Kindred", "TFT17_Ornn", b_star=3, seed=5)
    buffed_sim, buffed, _ = duel(
        "TFT17_Kindred", "TFT17_Ornn", b_star=3, seed=5,
        a_items=("TFT_Item_RabadonsDeathcap",),
    )
    for sim, unit in ((plain_sim, plain), (buffed_sim, buffed)):
        unit.current_mana = unit.derived_stats().max_mana
        sim.step(sim.config.tick_seconds)

    def ability_pre_mitigation(sim):
        return [
            e.detail["pre_mitigation"]
            for e in kinds(sim.log, EventKind.DAMAGE)
            if e.detail["via"] == "ability"
        ][0]

    assert ability_pre_mitigation(plain_sim) == pytest.approx(180)
    assert ability_pre_mitigation(buffed_sim) == pytest.approx(270)


def test_ability_damage_scales_with_star_level(duel):
    """Kindred: 180 / 270 / 405 across star levels."""
    for star, expected in ((1, 180), (2, 270), (3, 405)):
        sim, caster, _ = duel("TFT17_Kindred", "TFT17_Ornn", a_star=star, b_star=3)
        caster.current_mana = caster.derived_stats().max_mana
        sim.step(sim.config.tick_seconds)
        dmg = [
            e.detail["pre_mitigation"]
            for e in kinds(sim.log, EventKind.DAMAGE)
            if e.detail["via"] == "ability"
        ][0]
        assert dmg == pytest.approx(expected)


def test_shield_ability_absorbs_damage_before_hp(duel):
    sim, poppy, foe = duel("TFT17_Poppy", "TFT17_Jinx")
    poppy.current_mana = poppy.derived_stats().max_mana
    sim.step(sim.config.tick_seconds)
    assert kinds(sim.log, EventKind.SHIELD)
    assert poppy.shield_amount == 200

    hp_before = poppy.current_hp
    sim.deal_damage(None, poppy, 100.0, DamageType.TRUE)
    assert poppy.current_hp == hp_before
    assert poppy.shield_amount == 100


def test_stun_ability_applies_cc(duel):
    sim, blitz, foe = duel("TFT17_Blitzcrank", "TFT17_Ornn", b_star=3)
    blitz.current_mana = blitz.derived_stats().max_mana
    sim.step(sim.config.tick_seconds)
    assert foe.is_stunned
    status = kinds(sim.log, EventKind.STATUS)[0]
    assert status.detail["duration"] == 1.5


def test_splash_ability_hits_neighbours(data, make):
    board = Board()
    caster = make("TFT17_Diana")
    victims = [make("TFT17_Kindred"), make("TFT17_Corki"), make("TFT17_Talon")]
    place_team([caster], [(0, 3)], team=0, board=board)
    place_team(victims, [(0, 2), (0, 3), (0, 4)], team=1, board=board)
    sim = CombatSimulator([caster], victims, data, seed=0, board=board)
    caster.current_mana = caster.derived_stats().max_mana
    sim.step(sim.config.tick_seconds)
    splashed = {
        e.target for e in kinds(sim.log, EventKind.DAMAGE)
        if e.detail["via"] == "ability_splash"
    }
    assert len(splashed) >= 2


def test_unimplemented_ability_logs_and_does_not_crash(duel, caplog):
    """Ornn's effect_id has no implementation: warn once, no-op, keep fighting."""
    effects.reset_missing_warnings()
    sim, ornn, foe = duel("TFT17_Ornn", "TFT17_Jinx", a_star=3)
    ornn.current_mana = ornn.derived_stats().max_mana
    with caplog.at_level("WARNING"):
        sim.step(sim.config.tick_seconds)
    skipped = kinds(sim.log, EventKind.CAST_SKIPPED)
    assert skipped and skipped[0].detail["effect_id"] == "ornn_volcanic_rupture"
    assert "no implementation" in caplog.text
    # The mana was still consumed, so the unit does not retry every tick.
    assert ornn.current_mana < ornn.derived_stats().max_mana
    sim.run()  # must still complete


def test_unimplemented_effect_warns_only_once(duel, caplog):
    effects.reset_missing_warnings()
    with caplog.at_level("WARNING"):
        for _ in range(3):
            sim, ornn, _ = duel("TFT17_Ornn", "TFT17_Jinx", a_star=3)
            ornn.current_mana = ornn.derived_stats().max_mana
            sim.step(sim.config.tick_seconds)
    assert caplog.text.count("ornn_volcanic_rupture") == 1


# --- damage and mitigation (doc 01 sec 3.3) ------------------------------


def test_physical_mitigation_curve(duel):
    """K / (K + armor); Ornn 3-star has 70 armor -> 100/170."""
    sim, _, ornn = duel("TFT17_Jinx", "TFT17_Ornn", b_star=3)
    k = sim.config.armor_mitigation_constant
    assert sim.mitigation_multiplier(ornn, DamageType.PHYSICAL) == pytest.approx(
        k / (k + 70)
    )


def test_magic_mitigation_uses_magic_resist(duel):
    sim, _, ornn = duel("TFT17_Jinx", "TFT17_Ornn", b_star=3)
    k = sim.config.armor_mitigation_constant
    assert sim.mitigation_multiplier(ornn, DamageType.MAGIC) == pytest.approx(k / (k + 70))


def test_true_damage_ignores_mitigation(duel):
    sim, _, ornn = duel("TFT17_Jinx", "TFT17_Ornn", b_star=3)
    assert sim.mitigation_multiplier(ornn, DamageType.TRUE) == 1.0
    before = ornn.current_hp
    sim.deal_damage(None, ornn, 500.0, DamageType.TRUE)
    assert before - ornn.current_hp == pytest.approx(500.0)


def test_mitigation_never_reaches_full_immunity(duel):
    """The curve approaches but never reaches 100% reduction (doc 01 sec 3.3)."""
    sim, _, ornn = duel("TFT17_Jinx", "TFT17_Ornn", b_star=3)
    ornn.set_trait_bonuses(StatBonuses({"armor": 100000}))
    m = sim.mitigation_multiplier(ornn, DamageType.PHYSICAL)
    assert 0 < m < 0.01


def test_damage_amp_applies_after_mitigation(duel):
    sim, attacker, victim = duel("TFT17_Jinx", "TFT17_Ornn", b_star=3)
    attacker.set_trait_bonuses(StatBonuses({"damage_amp": 0.5}))
    mitigation = sim.mitigation_multiplier(victim, DamageType.PHYSICAL)
    lost = sim.deal_damage(attacker, victim, 100.0, DamageType.PHYSICAL)
    assert lost == pytest.approx(100.0 * mitigation * 1.5)


def test_durability_reduces_damage_taken(duel):
    sim, attacker, victim = duel("TFT17_Jinx", "TFT17_Ornn", b_star=3)
    victim.set_trait_bonuses(StatBonuses({"durability": 0.25}))
    lost = sim.deal_damage(attacker, victim, 100.0, DamageType.TRUE)
    assert lost == pytest.approx(75.0)


def test_crits_multiply_damage(duel):
    """A guaranteed-crit unit hits for crit_damage times its normal damage."""
    normal_sim, normal, foe_a = duel("TFT17_Jinx", "TFT17_Ornn", b_star=3, seed=11)
    normal.set_trait_bonuses(StatBonuses({"crit_chance": -1.0}))
    crit_sim, critter, foe_b = duel("TFT17_Jinx", "TFT17_Ornn", b_star=3, seed=11)
    critter.set_trait_bonuses(StatBonuses({"crit_chance": 1.0}))

    for sim in (normal_sim, crit_sim):
        for _ in range(60):
            sim.step(sim.config.tick_seconds)

    def first_auto_raw(sim, uid):
        return [e for e in kinds(sim.log, EventKind.ATTACK) if e.actor == uid][0].detail

    plain = first_auto_raw(normal_sim, normal.uid)
    crit = first_auto_raw(crit_sim, critter.uid)
    assert plain["crit"] is False and crit["crit"] is True
    assert crit["raw"] == pytest.approx(plain["raw"] * 1.4)


def test_shields_absorb_before_hp_and_type_specific_shields_are_selective(duel):
    from engine.unit import Shield

    sim, unit, _ = duel("TFT17_Poppy", "TFT17_Jinx")
    unit.shields.append(Shield(amount=50, damage_type="magic"))
    hp_before = unit.current_hp
    # Physical damage ignores a magic-only shield.
    sim.deal_damage(None, unit, 30.0, DamageType.TRUE)
    assert unit.current_hp == pytest.approx(hp_before - 30.0)
    assert unit.shield_amount == 50


def test_damage_cannot_push_hp_below_zero(duel):
    sim, unit, _ = duel("TFT17_Poppy", "TFT17_Jinx")
    sim.deal_damage(None, unit, 1e9, DamageType.TRUE)
    assert unit.current_hp == 0.0 and not unit.alive


def test_healing_is_capped_at_max_health(duel):
    sim, unit, _ = duel("TFT17_Poppy", "TFT17_Jinx")
    unit.current_hp = 100
    healed = sim.heal(unit, 1e6)
    assert unit.current_hp == unit.derived_stats().max_health
    assert healed == pytest.approx(unit.derived_stats().max_health - 100)


# --- item effect triggers ------------------------------------------------


def test_spear_of_shojin_grants_bonus_mana_on_attack(duel):
    sim, unit, _ = duel(
        "TFT17_Poppy", "TFT17_Ornn", b_star=3, a_items=("TFT_Item_SpearOfShojin",)
    )
    for _ in range(60):
        sim.step(sim.config.tick_seconds)
    bonus = [
        e for e in kinds(sim.log, EventKind.MANA)
        if e.actor == unit.uid and e.detail["reason"] == "spear_of_shojin"
    ]
    assert bonus and all(b.detail["amount"] == 15 for b in bonus)


def test_guinsoos_stacks_attack_speed_each_attack(duel):
    sim, unit, _ = duel(
        "TFT17_Poppy", "TFT17_Ornn", b_star=3, a_items=("TFT_Item_GuinsoosRageblade",)
    )
    base = unit.derived_stats().attack_speed
    for _ in range(120):
        sim.step(sim.config.tick_seconds)
    attacks = len([e for e in kinds(sim.log, EventKind.ATTACK) if e.actor == unit.uid])
    assert attacks >= 2
    assert unit.derived_stats().attack_speed > base


def test_bramble_vest_reflects_damage_to_a_melee_attacker(duel):
    """Exercises ItemDef.params: the reflect magnitude is not a stat the item
    grants, so it can only come from params."""
    sim, wearer, attacker = duel(
        "TFT17_Ornn", "TFT17_Poppy", a_star=3, a_items=("TFT_Item_BrambleVest",)
    )
    for _ in range(80):
        sim.step(sim.config.tick_seconds)
    reflected = [
        e for e in kinds(sim.log, EventKind.DAMAGE) if e.detail["via"] == "bramble_vest"
    ]
    assert reflected, "thorns should have fired on being auto-attacked"
    assert all(e.target == attacker.uid for e in reflected)
    assert all(e.detail["pre_mitigation"] == 80 for e in reflected)
    assert all(e.detail["type"] == "magic" for e in reflected)


def test_bramble_vest_ignores_ranged_attackers(duel):
    sim, wearer, attacker = duel(
        "TFT17_Ornn", "TFT17_Jinx", a_star=3, a_items=("TFT_Item_BrambleVest",)
    )
    for _ in range(80):
        sim.step(sim.config.tick_seconds)
    assert not [
        e for e in kinds(sim.log, EventKind.DAMAGE) if e.detail["via"] == "bramble_vest"
    ]


def test_two_thorns_carriers_do_not_reflect_forever(data, make):
    """Reflect damage must not re-trigger ON_DAMAGED, or it would recurse."""
    board = Board()
    a = make("TFT17_Ornn", 3, ("TFT_Item_BrambleVest",))
    b = make("TFT17_Ornn", 3, ("TFT_Item_BrambleVest",))
    place_team([a], [(0, 3)], team=0, board=board)
    place_team([b], [(0, 3)], team=1, board=board)
    sim = CombatSimulator([a], [b], data, seed=0, board=board)
    result = sim.run()  # must terminate rather than recurse
    assert result.winner in (0, 1, None)


def test_item_params_are_visible_to_effects(data):
    """params overlay stats, so an effect can read both."""
    bramble = data.items["TFT_Item_BrambleVest"]
    assert bramble.params["reflect"] == 80
    assert bramble.effect_values["reflect"] == 80
    assert bramble.effect_values["armor"] == 65, "stats stay readable"


def test_item_effect_without_a_matching_trigger_is_not_fired(duel):
    """Bramble Vest is ON_DAMAGED-shaped but unimplemented -- must not crash."""
    sim, unit, _ = duel(
        "TFT17_Poppy", "TFT17_Jinx", a_items=("TFT_Item_BrambleVest",)
    )
    result = sim.run()
    assert result.winner in (0, 1, None)


# --- trait integration ---------------------------------------------------


def test_trait_bonuses_are_applied_at_combat_start(data, make):
    board = Board()
    snipers = [make("TFT17_Jinx"), make("TFT17_Kindred")]
    foe = [make("TFT17_Ornn", 3)]
    place_team(snipers, [(0, 2), (0, 4)], team=0, board=board)
    place_team(foe, [(0, 3)], team=1, board=board)
    sim = CombatSimulator(snipers, foe, data, seed=0, board=board)
    # Sniper 2 grants +1 attack range and +10% damage amp.
    assert snipers[0].derived_stats().attack_range == 5
    assert snipers[0].derived_stats().damage_amp == pytest.approx(0.10)
    start = [e for e in kinds(sim.log, EventKind.COMBAT_START) if e.detail["team"] == 0][0]
    assert start.detail["traits"]["Sniper"] == 2


# --- termination ---------------------------------------------------------


def test_fight_ends_with_a_winner_and_survivors(duel):
    sim, jinx, poppy = duel("TFT17_Jinx", "TFT17_Poppy")
    result = sim.run()
    assert result.winner in (0, 1)
    assert result.survivors
    assert all(u.alive for u in result.survivors)
    assert kinds(sim.log, EventKind.DEATH)
    assert sim.log.events[-1].kind is EventKind.COMBAT_END


def test_death_is_logged_and_the_unit_stops_acting(duel):
    sim, jinx, poppy = duel("TFT17_Jinx", "TFT17_Poppy")
    sim.run()
    dead = next(u for u in (jinx, poppy) if not u.alive)
    deaths = [e for e in kinds(sim.log, EventKind.DEATH) if e.actor == dead.uid]
    assert len(deaths) == 1
    death_t = deaths[0].t
    assert not [
        e for e in kinds(sim.log, EventKind.ATTACK) if e.actor == dead.uid and e.t > death_t
    ]


def test_stalled_fight_terminates_via_sudden_death(data, make):
    """Two units that cannot meaningfully hurt each other must still resolve."""
    board = Board()
    a, b = make("TFT17_Ornn", 3), make("TFT17_Ornn", 3)
    place_team([a], [(0, 3)], team=0, board=board)
    place_team([b], [(0, 3)], team=1, board=board)
    sim = CombatSimulator([a], [b], data, seed=0, board=board)
    # Applied after construction: _prepare() installs trait bonuses itself and
    # would otherwise overwrite these.
    for unit in (a, b):
        unit.set_trait_bonuses(StatBonuses({"armor": 100000, "magic_resist": 100000}))
    result = sim.run()
    assert result.duration <= sim.config.max_duration_seconds + 1
    ramp = [e for e in kinds(sim.log, EventKind.SUDDEN_DEATH)
            if e.detail["reason"] == "ramp_started"]
    assert ramp, "stall-breaker should have engaged"
    assert kinds(sim.log, EventKind.DEATH), "the burn should have resolved the fight"


def test_result_reports_a_timeout(data, make):
    board = Board()
    a, b = make("TFT17_Ornn", 3), make("TFT17_Ornn", 3)
    place_team([a], [(0, 3)], team=0, board=board)
    place_team([b], [(0, 3)], team=1, board=board)
    sim = CombatSimulator([a], [b], data, seed=0, board=board)
    result = sim.run()
    assert isinstance(result.timed_out, bool)
    assert result.ticks > 0


@pytest.mark.parametrize("seed", range(12))
def test_many_seeds_all_terminate_cleanly(data, make, seed):
    """Fuzz across seeds: every fight must end, with no crash and sane state."""
    board = Board()
    rng_ids = sorted(data.champions)
    team0 = [make(rng_ids[seed % len(rng_ids)]), make(rng_ids[(seed + 3) % len(rng_ids)])]
    team1 = [make(rng_ids[(seed + 5) % len(rng_ids)]), make(rng_ids[(seed + 7) % len(rng_ids)])]
    place_team(team0, [(0, 2), (1, 3)], team=0, board=board)
    place_team(team1, [(0, 2), (1, 3)], team=1, board=board)
    sim = CombatSimulator(team0, team1, data, seed=seed, board=board)
    result = sim.run()
    assert result.duration <= sim.config.max_duration_seconds + 1
    assert result.winner in (0, 1, None)
    for unit in team0 + team1:
        assert unit.current_hp >= 0
        assert unit.alive == (unit.current_hp > 0)


# --- combat log ----------------------------------------------------------


def test_log_events_are_time_ordered(duel):
    sim, _, _ = duel("TFT17_Jinx", "TFT17_Poppy")
    sim.run()
    times = [e.t for e in sim.log.events]
    assert times == sorted(times)


def test_log_renders_readable_lines(duel):
    sim, jinx, poppy = duel("TFT17_Jinx", "TFT17_Poppy")
    sim.run()
    text = sim.log.render()
    assert "Jinx" in text and "Poppy" in text
    assert "combat_start" in text and "combat_end" in text
    assert all(line.startswith("[") for line in text.splitlines())


def test_log_can_be_filtered_by_kind_and_unit(duel):
    sim, jinx, poppy = duel("TFT17_Jinx", "TFT17_Poppy")
    sim.run()
    assert all(e.kind is EventKind.DAMAGE for e in sim.log.of_kind(EventKind.DAMAGE))
    assert all(
        e.actor == jinx.uid or e.target == jinx.uid for e in sim.log.for_unit(jinx.uid)
    )
