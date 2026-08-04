"""The 29 per-champion abilities and the engine systems they needed.

These were blocked for most of the project's life because `fetch_cdragon.py`
refuses to guess which variable belongs to an ability's passive and which to
its active (doc 99 entries 11.2, 16). The implementations read Riot's prose to
resolve that split per champion.

An unimplemented ability warns once and no-ops, so "does nothing" and "works"
look identical from outside. Every test here asserts the ability *changed the
fight* -- damage landed, a status appeared, a unit moved, a summon exists.
"""

from __future__ import annotations

import pytest

from engine.combat import CombatSimulator, EffectContext, EventKind
from engine.effects import EFFECTS, EffectTrigger, hooks_for
from engine.hexgrid import Board, Hex, cone, distance
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


def _by_name(data, name):
    return next(c for c in data.champions.values() if c.display_name == name)


def _fight(data, registry, caster_name, *, enemies=1, star=1, enemy_star=1):
    """One caster against ``enemies`` filler units, positioned in range."""
    board = Board()
    hexes = sorted(board.hexes)
    caster = UnitInstance(_by_name(data, caster_name), star, registry=registry)
    caster.position, caster.team = hexes[0], 0
    foes = []
    filler = sorted(data.champions.values(), key=lambda c: c.id)
    for i in range(enemies):
        foe = UnitInstance(filler[i], enemy_star, registry=registry)
        # Adjacent-ish so melee casters connect without a long walk.
        foe.position, foe.team = hexes[i + 1], 1
        foes.append(foe)
    sim = CombatSimulator([caster], foes, data, seed=1, board=board)
    return sim, caster, foes


def _cast(sim, caster, target):
    """Invoke a champion's ON_CAST hook directly, bypassing the mana gate."""
    ability = caster.champion.ability
    fired = hooks_for(ability.effect_id, EffectTrigger.ON_CAST)
    assert fired, f"{caster.champion.display_name} has no ON_CAST hook"
    for fn in fired:
        fn(
            EffectContext(
                sim=sim, source=caster, target=target,
                params=ability.params, star_level=caster.star_level,
            )
        )


def _fire(sim, caster, target, trigger, **kw):
    ability = caster.champion.ability
    for fn in hooks_for(ability.effect_id, trigger):
        fn(
            EffectContext(
                sim=sim, source=caster, target=target,
                params=ability.params, star_level=caster.star_level, **kw
            )
        )


# --- coverage -------------------------------------------------------------


def test_every_champion_ability_is_implemented(data):
    missing = [
        c.display_name
        for c in data.champions.values()
        if c.ability and c.ability.effect_id not in EFFECTS
    ]
    assert not missing, f"unimplemented abilities: {missing}"


def test_registered_ability_ids_all_belong_to_a_champion(data):
    """A hook on an id no champion carries is dead code that looks alive."""
    registered = {e for e in EFFECTS if e.startswith("ability_TFT17_")}
    real = {c.ability.effect_id for c in data.champions.values() if c.ability}
    real |= {c.ability.effect_id for c in data.summons.values() if c.ability}
    assert registered <= real, f"registered but unused: {registered - real}"


# --- the new engine systems ----------------------------------------------


def test_cone_widens_with_distance_and_excludes_the_origin():
    origin = Hex(0, 0)
    wedge = cone(origin, Hex(4, 0), 4, half_angle=2)
    assert origin not in wedge
    assert all(distance(origin, h) <= 4 for h in wedge)
    near = [h for h in wedge if distance(origin, h) == 1]
    far = [h for h in wedge if distance(origin, h) == 4]
    assert len(far) > len(near), "the cone did not widen with distance"


def test_cone_is_directional():
    """A cone pointing one way must not contain the opposite direction."""
    origin = Hex(0, 0)
    east = set(cone(origin, Hex(3, 0), 3, half_angle=1))
    west = set(cone(origin, Hex(-3, 0), 3, half_angle=1))
    assert east and west
    assert not (east & west), "opposing cones overlap"


def test_untargetable_units_are_skipped_by_targeting(data, registry):
    from engine.unit import StatusEffect

    sim, caster, foes = _fight(data, registry, "Teemo", enemies=2)
    assert len(sim.targetable(1)) == 2
    foes[0].add_status(StatusEffect("hidden", remaining=None, untargetable=True))
    remaining = sim.targetable(1)
    assert len(remaining) == 1 and remaining[0].uid == foes[1].uid
    # ...but it is still alive and still takes area damage.
    assert foes[0] in sim.living(1)


def test_untargetable_target_is_dropped_by_the_selector(data, registry):
    from engine.unit import StatusEffect

    sim, caster, foes = _fight(data, registry, "Teemo", enemies=2)
    caster.target_uid = foes[0].uid
    foes[0].add_status(StatusEffect("hidden", remaining=None, untargetable=True))
    chosen = sim._select_target(caster)
    assert chosen is not None and chosen.uid != foes[0].uid


def test_summon_creates_a_unit_that_is_flagged_and_fights(data, registry):
    sim, caster, foes = _fight(data, registry, "Teemo")
    champion = data.summon_for("shepherd")
    assert champion is not None
    before = len(sim.living(0))
    summoned = sim.summon(champion, 0, caster.position)
    assert summoned is not None
    assert summoned.is_summon
    assert len(sim.living(0)) == before + 1
    assert summoned.uid in sim.by_uid
    assert summoned.current_hp > 0


def test_summons_never_enter_the_champion_pool(data):
    """The pool is built from `champions`; a summon there would leak copies."""
    assert data.summons
    assert not (set(data.summons) & set(data.champions))


def test_summon_declares_no_traits(data):
    """Shepherd's own summons must not raise the Shepherd breakpoint."""
    for champion in data.summons.values():
        assert champion.traits == ()


def test_reposition_moves_toward_a_hex_without_overlapping(data, registry):
    sim, caster, foes = _fight(data, registry, "Talon", enemies=2)
    caster.position = sorted(sim.board.hexes)[0]
    goal = foes[-1].position
    before = distance(caster.position, goal)
    moved = sim.reposition(caster, goal, max_hexes=2)
    assert moved
    assert distance(caster.position, goal) < before
    assert caster.position not in {f.position for f in foes}


def test_rooted_units_cannot_be_repositioned(data, registry):
    from engine.unit import StatusEffect

    sim, caster, foes = _fight(data, registry, "Talon")
    caster.add_status(StatusEffect("root", remaining=5.0, root=True))
    where = caster.position
    assert not sim.reposition(caster, foes[0].position, 3)
    assert caster.position == where


def test_lucky_roll_is_never_worse_than_an_unlucky_one(data, registry):
    sim, _, _ = _fight(data, registry, "Teemo")
    plain = sum(sim.lucky_roll(0.3, False) for _ in range(2000))
    lucky = sum(sim.lucky_roll(0.3, True) for _ in range(2000))
    assert lucky > plain, f"lucky={lucky} plain={plain}"


def test_counters_and_marks_reset_between_combats(data, registry):
    sim, caster, foes = _fight(data, registry, "Master Yi")
    caster.bump_counter("probe")
    foes[0].add_mark("probe", caster.uid)
    assert caster.counter("probe") == 1
    caster.reset_for_combat()
    assert caster.counter("probe") == 0
    assert caster.marks == {}


def test_marks_are_keyed_by_the_unit_that_placed_them(data, registry):
    sim, caster, foes = _fight(data, registry, "Kindred", enemies=1)
    victim = foes[0]
    victim.add_mark("kindred", 1)
    victim.add_mark("kindred", 2)
    assert victim.mark_count("kindred", 1) == 1
    assert victim.mark_count("kindred", 2) == 1


# --- abilities: each must change the fight -------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "Lulu", "Twisted Fate", "Pyke", "Graves", "Maokai", "Ornn",
        "Master Yi", "Samira", "Urgot", "The Mighty Mech", "Tahm Kench",
        "Vex", "Jhin", "LeBlanc", "Kindred", "Bard", "Blitzcrank",
        "Fiora", "Gwen", "Fizz", "Sona", "Riven", "Shen", "Miss Fortune",
    ],
)
def test_damage_abilities_deal_damage(data, registry, name):
    """One cast, and the enemy team must have lost effective health.

    Shields are cleared first: the filler enemies field real Set 17 champions,
    and some of them activate traits that shield the board at combat start
    (N.O.V.A., Voyager, Vanguard). Without this, a working ability reads as
    dealing nothing because a trait absorbed all of it.
    """
    sim, caster, foes = _fight(data, registry, name, enemies=3, enemy_star=1)
    for foe in foes:
        foe.shields.clear()
        foe.current_hp = foe.derived_stats().max_health
    total_before = sum(f.current_hp for f in foes)
    _cast(sim, caster, foes[0])
    total_after = sum(f.current_hp for f in foes)
    assert total_after < total_before, f"{name}'s cast dealt no damage"


def test_ability_passives_fire_from_a_real_fight(data, registry):
    """Calling the hook by hand proves the hook, not the wiring.

    Champion passives are registered on ON_ATTACK against the same effect_id as
    the active, and nothing dispatched ability hooks on non-cast triggers until
    `_fire_ability_triggers` existed. Running an actual fight is the only way
    to show that dispatch happens.
    """
    sim, caster, foes = _fight(data, registry, "Teemo", enemy_star=3)
    sim.run()
    poisoned = [
        e for e in sim.log.events if e.detail.get("via") in ("teemo_poison", "teemo_hit")
    ]
    assert poisoned, "Teemo's on-attack passive never fired in a real fight"


def test_ability_periodic_passives_fire_from_the_tick_loop(data, registry):
    sim, caster, foes = _fight(data, registry, "Blitzcrank", enemy_star=3)
    sim.run()
    bolts = [e for e in sim.log.events if e.detail.get("via") == "blitzcrank_bolt"]
    assert bolts, "Blitzcrank's periodic bolt never fired"


def test_talon_applies_a_bleed_rather_than_instant_damage(data, registry):
    sim, caster, foes = _fight(data, registry, "Talon", enemy_star=3)
    foes[0].current_hp = foes[0].derived_stats().max_health
    _cast(sim, caster, foes[0])
    assert foes[0].uid in sim.burns, "Talon's bleed was not applied"


def test_teemo_poisons_on_attack(data, registry):
    sim, caster, foes = _fight(data, registry, "Teemo", enemy_star=3)
    _fire(sim, caster, foes[0], EffectTrigger.ON_ATTACK)
    assert foes[0].uid in sim.burns, "Teemo's poison was not applied"


def test_zed_summons_a_clone_once(data, registry):
    sim, caster, foes = _fight(data, registry, "Zed")
    _cast(sim, caster, foes[0])
    clones = [u for u in sim.living(0) if u.is_summon]
    assert len(clones) == 1
    _cast(sim, caster, foes[0])
    assert len([u for u in sim.living(0) if u.is_summon]) == 1, "Zed cloned twice"


def test_zed_clone_inherits_stats_at_reduced_health(data, registry):
    sim, caster, foes = _fight(data, registry, "Zed")
    _cast(sim, caster, foes[0])
    clone = next(u for u in sim.living(0) if u.is_summon)
    assert clone.champion.id == caster.champion.id
    assert clone.current_hp < caster.derived_stats().max_health


def test_master_yi_doubleslash_only_on_every_third_attack(data, registry):
    sim, caster, foes = _fight(data, registry, "Master Yi", enemy_star=3)
    hits = []
    for _ in range(6):
        before = len(sim.log.of_kind(EventKind.DAMAGE))
        _fire(sim, caster, foes[0], EffectTrigger.ON_ATTACK)
        hits.append(len(sim.log.of_kind(EventKind.DAMAGE)) > before)
    assert hits == [False, False, True, False, False, True], hits


def test_riven_third_cast_uses_the_wave(data, registry):
    sim, caster, foes = _fight(data, registry, "Riven", enemies=3, enemy_star=3)
    labels = []
    for _ in range(3):
        before = len(sim.log.events)
        _cast(sim, caster, foes[0])
        labels.append(
            {e.detail.get("via") for e in sim.log.events[before:]}
        )
    assert "riven_slash" in labels[0]
    assert "riven_wave" in labels[2], "the third cast did not fire the wave"


def test_sona_rips_debris_on_the_fifth_cast(data, registry):
    sim, caster, foes = _fight(data, registry, "Sona", enemies=3, enemy_star=3)
    seen = []
    for _ in range(5):
        before = len(sim.log.events)
        _cast(sim, caster, foes[0])
        seen.append({e.detail.get("via") for e in sim.log.events[before:]})
    assert "sona_debris" in seen[0]
    assert "sona_slam" in seen[4], "the fifth cast did not slam"


def test_caitlyn_headshot_can_fire_and_is_probabilistic(data, registry):
    sim, caster, foes = _fight(data, registry, "Caitlyn", enemy_star=3)
    foes[0].current_hp = foes[0].derived_stats().max_health
    fired = 0
    for _ in range(200):
        before = foes[0].current_hp
        _fire(sim, caster, foes[0], EffectTrigger.ON_ATTACK)
        if foes[0].current_hp < before:
            fired += 1
        foes[0].current_hp = foes[0].derived_stats().max_health
    assert 0 < fired < 200, f"headshot fired {fired}/200 times"


def test_tahm_kench_shields_from_healing_received(data, registry):
    sim, caster, foes = _fight(data, registry, "Tahm Kench", enemy_star=3)
    caster.current_hp = caster.derived_stats().max_health * 0.2
    _cast(sim, caster, foes[0])          # heals, recording the amount
    assert caster.counter("tk_healing") > 0, "the heal was not recorded"

    # The cast's own heal lifts him back over the passive's threshold, so drop
    # him under it again -- the passive keys on health, not on the cast.
    caster.current_hp = caster.derived_stats().max_health * 0.1
    _fire(sim, caster, foes[0], EffectTrigger.ON_DAMAGED)
    assert caster.shield_amount > 0, "the passive shield never formed"


def test_tahm_kench_passive_does_not_fire_above_its_threshold(data, registry):
    sim, caster, foes = _fight(data, registry, "Tahm Kench", enemy_star=3)
    _cast(sim, caster, foes[0])
    caster.current_hp = caster.derived_stats().max_health
    caster.shields.clear()
    _fire(sim, caster, foes[0], EffectTrigger.ON_DAMAGED)
    assert caster.shield_amount == 0


def test_maokai_stuns_what_it_hits(data, registry):
    sim, caster, foes = _fight(data, registry, "Maokai", enemy_star=3)
    _cast(sim, caster, foes[0])
    assert foes[0].is_stunned


def test_galio_gains_durability_then_shocks(data, registry):
    sim, caster, foes = _fight(data, registry, "The Mighty Mech", enemy_star=3)
    _cast(sim, caster, foes[0])
    assert caster.derived_stats().durability > 0


def test_jhin_passive_pins_attack_speed(data, registry):
    sim, caster, foes = _fight(data, registry, "Jhin")
    _fire(sim, caster, None, EffectTrigger.ON_COMBAT_START)
    fixed = caster.champion.ability.params["FixedAS"]
    expected = fixed[caster.star_level - 1] if isinstance(fixed, list) else fixed
    assert caster.derived_stats().attack_speed == pytest.approx(expected, rel=0.02)


def test_kindred_wolf_consumes_marks_at_the_cap(data, registry):
    sim, caster, foes = _fight(data, registry, "Kindred", enemy_star=3)
    foes[0].current_hp = foes[0].derived_stats().max_health
    for _ in range(2):
        _fire(sim, caster, foes[0], EffectTrigger.ON_ATTACK)
    before = foes[0].current_hp
    _fire(sim, caster, foes[0], EffectTrigger.ON_ATTACK)  # third mark
    assert foes[0].current_hp < before, "Wolf never consumed the marks"
    assert foes[0].mark_count("kindred", caster.uid) == 0
