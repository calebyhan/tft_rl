"""Set 18 emblem passives (doc 99 entry 161.14).

A Set 18 emblem grants its trait *and* a passive. The `emblem_*` id counts as
implemented because it grants the trait, so an unmodelled passive is silent:
no warning, no missing-effect count. Each test here drives the passive through
the simulator's own entry points -- a landed attack, `deal_damage`, `heal`, a
kill, a cast -- and asserts the fight observably changed, with a control
where one is needed to show the change is the emblem's.
"""

from __future__ import annotations

import pytest

from engine.combat import CombatSimulator, DamageType, EventKind
from engine.hexgrid import Board
from engine.items import ItemRegistry
from engine.loader import load_all
from engine.unit import UnitInstance
from tests.paths import REAL_DATA_DIR

SET18_DIR = REAL_DATA_DIR / "set18"
# A Set 18 champion whose ability is implemented, so a cast actually resolves.
CASTER = "DA_18_Ornn"


@pytest.fixture(scope="module")
def data():
    return load_all(SET18_DIR)


@pytest.fixture(scope="module")
def registry(data):
    return ItemRegistry(data.items, data.config.max_items_per_unit)


def _emblem(data, display_name):
    return next(i for i in data.items.values() if i.display_name == display_name)


def _fight(data, registry, emblem=None, *, allies=0, enemies=1, holder=CASTER, star=1):
    """Holder (plus allies) against enemies, positioned; nothing stepped yet."""
    board = Board()
    hexes = sorted(board.hexes)
    names = sorted(data.champions)
    team0 = [UnitInstance(data.champions[holder], star, registry=registry)]
    team0 += [UnitInstance(data.champions[CASTER], 1, registry=registry) for _ in range(allies)]
    team1 = [UnitInstance(data.champions[names[i]], 1, registry=registry) for i in range(enemies)]
    for i, unit in enumerate(team0):
        unit.position, unit.team = hexes[i], 0
    for i, unit in enumerate(team1):
        unit.position, unit.team = hexes[-1 - i], 1
    if emblem is not None:
        team0[0].equip(_emblem(data, emblem))
    sim = CombatSimulator(team0, team1, data, seed=1, board=board)
    return sim, team0, team1


def _damage_via(sim, label):
    return [e for e in sim.log.of_kind(EventKind.DAMAGE) if e.detail.get("via") == label]


# --- on a landed attack ------------------------------------------------------


def test_brawler_attacks_deal_a_share_of_the_holders_max_health(data, registry):
    # 2-star: a 1-star holder's 700 + the emblem's 150 equals the enemy's 850,
    # which let a mutant reading the *target's* health pass.
    sim, (holder,), (enemy,) = _fight(data, registry, "Brawler Emblem", star=2)
    assert holder.derived_stats().max_health != enemy.derived_stats().max_health
    sim._land_attack(holder, enemy, 10.0, DamageType.PHYSICAL, False)
    hits = _damage_via(sim, "brawler_emblem")
    assert len(hits) == 1
    assert hits[0].detail["type"] == "magic"
    assert hits[0].detail["pre_mitigation"] == pytest.approx(
        0.025 * holder.derived_stats().max_health, abs=1e-3)


def test_rapidfire_attacks_deal_a_share_of_the_targets_max_health(data, registry):
    sim, (holder,), (enemy,) = _fight(data, registry, "Rapidfire Emblem")
    sim._land_attack(holder, enemy, 10.0, DamageType.PHYSICAL, False)
    hits = _damage_via(sim, "rapidfire_emblem")
    assert [h.detail["type"] for h in hits] == ["true"]
    assert hits[0].detail["pre_mitigation"] == pytest.approx(
        0.01 * enemy.derived_stats().max_health, abs=1e-3)


def test_an_ability_hit_is_not_an_attack(data, registry):
    """Both passives say "Attacks"; ON_HIT would have fired them on spells too."""
    sim, (holder,), (enemy,) = _fight(data, registry, "Rapidfire Emblem")
    sim.deal_damage(holder, enemy, 10.0, DamageType.MAGIC, source_label="ability")
    assert not _damage_via(sim, "rapidfire_emblem")


# --- on damage dealt -----------------------------------------------------------


@pytest.mark.parametrize("emblem,dies", [("Executioner Emblem", True), (None, False)])
def test_executioner_executes_below_its_threshold(data, registry, emblem, dies):
    sim, (holder,), (enemy,) = _fight(data, registry, emblem)
    enemy.current_hp = 0.07 * enemy.derived_stats().max_health + 5.0
    sim.deal_damage(holder, enemy, 1.0, DamageType.TRUE, source_label="ability")
    assert enemy.alive is not dies


def test_executioner_spares_an_enemy_above_its_threshold(data, registry):
    sim, (holder,), (enemy,) = _fight(data, registry, "Executioner Emblem")
    enemy.current_hp = 0.10 * enemy.derived_stats().max_health
    sim.deal_damage(holder, enemy, 1.0, DamageType.TRUE, source_label="ability")
    assert enemy.alive


# --- on a takedown -----------------------------------------------------------


def test_hunter_takedowns_stack_attack_damage(data, registry):
    sim, (holder,), enemies = _fight(data, registry, "Hunter Emblem", enemies=3)
    base = holder.derived_stats().attack_damage
    ad = holder.champion.stats.attack_damage_at(holder.star_level)
    for kills, enemy in enumerate(enemies[:2], start=1):
        sim.deal_damage(holder, enemy, enemy.current_hp * 10, DamageType.TRUE, source_label="ability")
        assert not enemy.alive
        assert holder.derived_stats().attack_damage == pytest.approx(base + kills * 0.15 * ad)


# --- on a cast -----------------------------------------------------------------


def _cast(sim, unit, target):
    unit.current_mana = unit.derived_stats().max_mana
    unit.mana_locked_until = 0.0
    assert sim._try_cast(unit, target), "the ability must resolve for a cast to count"


def test_invoker_casts_grant_ability_power_from_mana_spent(data, registry):
    sim, (holder,), (enemy,) = _fight(data, registry, "Invoker Emblem")
    before = holder.derived_stats().ability_power
    spent = holder.derived_stats().max_mana
    _cast(sim, holder, enemy)
    assert holder.derived_stats().ability_power == pytest.approx(before + 0.08 * spent)
    _cast(sim, holder, enemy)
    assert holder.derived_stats().ability_power == pytest.approx(before + 2 * 0.08 * spent)


def test_a_cast_whose_ability_is_unimplemented_still_counts(data, registry):
    """The mana is spent either way; 55 of 65 Set 18 abilities are unimplemented
    (item 4c), and Invoker never fired in 20 smoke games until this counted."""
    from engine.effects import EFFECTS

    blank = next(c.id for c in sorted(data.champions.values(), key=lambda c: c.id)
                 if c.ability and c.ability.effect_id not in EFFECTS
                 and c.ability.cast_mode == "mana")
    sim, (holder,), (enemy,) = _fight(data, registry, "Invoker Emblem", holder=blank)
    before = holder.derived_stats().ability_power
    holder.current_mana = holder.derived_stats().max_mana
    assert not sim._try_cast(holder, enemy), "the ability is unimplemented"
    assert holder.derived_stats().ability_power > before


def test_spellweaver_gains_mana_when_an_ally_casts(data, registry):
    sim, (holder, ally), (enemy,) = _fight(data, registry, "Spellweaver Emblem", allies=1)
    holder.current_mana = 0.0
    _cast(sim, ally, enemy)
    assert holder.current_mana == pytest.approx(2.0)


def test_ally_cast_dispatch_skips_the_caster(data, registry, monkeypatch):
    """Recorded at dispatch: the caster's own mana lock would hide the bug."""
    from engine import effects

    calls = []
    monkeypatch.setitem(effects.EFFECT_HOOKS, "emblem_DA_18_Spellweaver",
                        [(effects.EffectTrigger.ON_ALLY_CAST, lambda ctx: calls.append(ctx.target))])
    monkeypatch.setattr(effects, "_HOOK_CACHE", {})
    sim, (holder, ally), (enemy,) = _fight(data, registry, "Spellweaver Emblem", allies=1)
    _cast(sim, holder, enemy)
    assert calls == []
    _cast(sim, ally, enemy)
    assert calls == [ally]


# --- on healing received -------------------------------------------------------


def test_ravager_gains_damage_amp_per_step_of_health_restored(data, registry):
    sim, (holder,), _ = _fight(data, registry, "Ravager Emblem", star=2)
    base = holder.derived_stats().damage_amp
    holder.current_hp = 1.0
    sim.heal(holder, 250.0)
    assert holder.derived_stats().damage_amp == pytest.approx(base), "below one step"
    sim.heal(holder, 400.0)  # 650 restored: two full steps
    assert holder.derived_stats().damage_amp == pytest.approx(base + 0.06)


# --- in player combat ----------------------------------------------------------


def test_vanguard_earns_player_health_for_surviving(data, registry):
    sim, (holder,), _ = _fight(data, registry, "Vanguard Emblem")
    assert sim.player_health_earned == [0, 0]
    sim.t = 21.9
    sim.step(data.config.combat.tick_seconds)
    assert sim.player_health_earned == [0, 0], "not yet 22 seconds"
    for _ in range(3):
        sim.t = max(sim.t, 22.0)
        sim.step(data.config.combat.tick_seconds)
    assert sim.player_health_earned == [1, 0], "once per combat, to the holder's side"
    assert sim._finish(False).player_health_earned == (1, 0), "the result must carry it"


def test_a_dead_holder_earns_nothing(data, registry):
    sim, (holder,), _ = _fight(data, registry, "Vanguard Emblem")
    sim._kill(holder, None)
    sim.t = 23.0
    sim.step(data.config.combat.tick_seconds)
    assert sim.player_health_earned == [0, 0]


def test_player_health_is_capped_and_never_revives(data):
    from engine.player import PlayerState

    player = PlayerState(data=data, registry=ItemRegistry(data.items, 3))
    start = data.config.starting_hp
    player.gain_hp(5)
    assert player.hp == start
    player.hp = 40
    player.gain_hp(1)
    assert player.hp == 41
    player.hp = 0
    player.gain_hp(1)
    assert player.hp == 0


def _fixed_result(winner, earned):
    from engine.combat import CombatLog, CombatResult

    return CombatResult(winner=winner, survivors=(), duration=30.0, ticks=1,
                        log=CombatLog(), timed_out=False, player_health_earned=earned)


def test_a_player_fight_pays_each_side_its_earned_health(data, monkeypatch):
    from engine.match import Match
    from rl.opponents import NoOpPolicy

    match = Match(data, [NoOpPolicy() for _ in range(8)], seed=3)
    monkeypatch.setattr(match, "_simulate", lambda *_: _fixed_result(0, (2, 1)))
    winner, loser = match.players[0], match.players[1]
    winner.hp = loser.hp = 50
    reports = match._resolve_fight(winner, loser)
    assert winner.hp == 52
    assert loser.hp == 50 - reports[1].damage_taken + 1


def test_a_ghost_fight_pays_the_player_too(data, monkeypatch):
    from engine.match import Match
    from rl.opponents import NoOpPolicy

    match = Match(data, [NoOpPolicy() for _ in range(8)], seed=3)
    monkeypatch.setattr(match, "_simulate", lambda *_: _fixed_result(0, (3, 0)))
    player = match.players[0]
    player.hp = 50
    match._fight_ghost(player)
    assert player.hp == 53
