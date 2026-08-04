"""Trait behaviours (doc 99 entry 34.9).

All 86 breakpoints were inert before this: `engine.traits` applied any params
that happened to name a modelled stat and nothing dispatched the rest, so
composition -- the thing TFT is about -- barely moved a fight.

The same hazard as the item effects applies, doubled: a trait that does nothing
looks exactly like a trait whose params were read under the wrong key, and both
look like a trait that is merely weak. Every test here asserts a fielded board
*differs measurably* from the same board below the breakpoint.
"""

from __future__ import annotations

import pytest

from engine.combat import CombatSimulator, DamageType
from engine.effects import EffectTrigger
from engine.hexgrid import Board
from engine.items import ItemRegistry
from engine.loader import load_all
from engine.trait_effects import TRAIT_HOOKS, trait_id_of
from engine.unit import UnitInstance
from tests.paths import REAL_DATA_DIR


@pytest.fixture(scope="module")
def data():
    return load_all(REAL_DATA_DIR)


@pytest.fixture(scope="module")
def registry(data):
    return ItemRegistry(data.items, data.config.max_items_per_unit)


def _champions_with(data, trait_id, count):
    """``count`` distinct champions carrying ``trait_id``, deterministically."""
    found = [c for c in data.champions.values() if trait_id in c.traits]
    return sorted(found, key=lambda c: c.id)[:count]


def _board(data, registry, champions, enemy_count=1, star=1):
    """Field ``champions`` on team 0 against filler enemies on team 1."""
    board = Board()
    hexes = sorted(board.hexes)
    ours, theirs = [], []
    for i, champ in enumerate(champions):
        u = UnitInstance(champ, star, registry=registry)
        u.position, u.team = hexes[i], 0
        ours.append(u)
    filler = sorted(data.champions.values(), key=lambda c: c.id)
    for i in range(enemy_count):
        u = UnitInstance(filler[i], star, registry=registry)
        u.position, u.team = hexes[-(i + 1)], 1
        theirs.append(u)
    sim = CombatSimulator(ours, theirs, data, seed=1, board=board)
    return sim, ours, theirs


# --- the registry must line up with the data -----------------------------


def test_trait_id_is_parsed_out_of_the_breakpoint_effect_id():
    """Breakpoints ship as `trait_<Id>_<tier>`; hooks register on `<Id>`."""
    assert trait_id_of("trait_TFT17_HPTank_4") == "TFT17_HPTank"
    assert trait_id_of("trait_TFT17_ADMIN_2") == "TFT17_ADMIN"
    assert trait_id_of("item_TFT_Item_Deathblade") is None
    assert trait_id_of(None) is None


def test_every_registered_trait_exists_in_the_data(data):
    """A hook on a trait id no board can field is dead code that looks alive."""
    unknown = set(TRAIT_HOOKS) - set(data.traits)
    assert not unknown, f"registered but absent from data: {unknown}"


def test_breakpoint_effect_ids_resolve_to_registered_traits(data):
    """Guards against the tier-suffix parser silently mismatching."""
    implemented = set(TRAIT_HOOKS)
    resolved = set()
    for trait in data.traits.values():
        for bp in trait.breakpoints:
            parsed = trait_id_of(bp.effect_id)
            if parsed in implemented:
                resolved.add(parsed)
    assert resolved == implemented, f"never resolved: {implemented - resolved}"


# --- each implemented trait must change the fight ------------------------


def test_brawler_raises_team_health_and_members_more(data, registry):
    champs = _champions_with(data, "TFT17_HPTank", 2)
    if len(champs) < 2:
        pytest.skip("not enough Brawlers in the dataset")

    # Below the breakpoint: one Brawler plus a non-Brawler.
    other = next(
        c
        for c in sorted(data.champions.values(), key=lambda c: c.id)
        if "TFT17_HPTank" not in c.traits
    )
    _, below, _ = _board(data, registry, [champs[0], other])
    _, above, _ = _board(data, registry, champs)

    assert above[0].derived_stats().max_health > below[0].derived_stats().max_health


def test_percentage_health_grants_carry_current_hp(data, registry):
    """A max-health grant that leaves current HP alone is a stealth nerf."""
    champs = _champions_with(data, "TFT17_HPTank", 2)
    if len(champs) < 2:
        pytest.skip("not enough Brawlers in the dataset")
    _, ours, _ = _board(data, registry, champs)
    for unit in ours:
        assert unit.current_hp == pytest.approx(unit.derived_stats().max_health)


def test_challenger_grants_attack_speed_to_the_whole_team(data, registry):
    champs = _champions_with(data, "TFT17_ASTrait", 2)
    if len(champs) < 2:
        pytest.skip("not enough Challengers")
    other = next(
        c
        for c in sorted(data.champions.values(), key=lambda c: c.id)
        if "TFT17_ASTrait" not in c.traits
    )
    _, below, _ = _board(data, registry, [champs[0], other])
    _, above, _ = _board(data, registry, [*champs, other])

    # The non-Challenger benefits too -- that is the teamwide half.
    assert above[-1].derived_stats().attack_speed > below[-1].derived_stats().attack_speed


def test_bastion_doubles_its_resists_for_the_opening_seconds(data, registry):
    champs = _champions_with(data, "TFT17_ResistTank", 2)
    if len(champs) < 2:
        pytest.skip("not enough Bastions")
    sim, ours, _ = _board(data, registry, champs)

    opening = ours[0].derived_stats().armor
    for _ in range(int(12.0 / data.config.combat.tick_seconds)):
        ours[0].tick_statuses(data.config.combat.tick_seconds)
    settled = ours[0].derived_stats().armor

    assert opening > settled, "the opening double never expired"
    assert settled > 0, "the base Bastion resists vanished with it"


def test_sniper_amp_grows_with_distance(data, registry):
    champs = _champions_with(data, "TFT17_RangedTrait", 2)
    if len(champs) < 2:
        pytest.skip("not enough Snipers")
    sim, ours, theirs = _board(data, registry, champs, enemy_count=1)
    hexes = sorted(sim.board.hexes)

    shooter, victim = ours[0], theirs[0]
    shooter.position = hexes[0]

    victim.position = hexes[1]
    near = sim._damage_multiplier_from_items(shooter, victim)
    victim.position = hexes[-1]
    far = sim._damage_multiplier_from_items(shooter, victim)

    assert far > near > 1.0, f"near={near} far={far}"


def test_conduit_grants_mana_regen_to_the_team(data, registry):
    champs = _champions_with(data, "TFT17_ManaTrait", 2)
    if len(champs) < 2:
        pytest.skip("not enough Conduits")
    _, ours, _ = _board(data, registry, champs)
    assert ours[0].derived_stats().mana_regen > 0


def test_vanguard_shields_at_combat_start(data, registry):
    champs = _champions_with(data, "TFT17_ShieldTank", 2)
    if len(champs) < 2:
        pytest.skip("not enough Vanguards")
    _, ours, _ = _board(data, registry, champs)
    assert ours[0].shield_amount > 0


def test_vanguard_durability_applies_only_while_shielded(data, registry):
    champs = _champions_with(data, "TFT17_ShieldTank", 2)
    if len(champs) < 2:
        pytest.skip("not enough Vanguards")
    sim, ours, _ = _board(data, registry, champs)
    unit = ours[0]

    sim._fire_trait_triggers(0, EffectTrigger.PERIODIC)
    shielded = unit.derived_stats().durability
    assert shielded > 0

    unit.shields.clear()
    sim._fire_trait_triggers(0, EffectTrigger.PERIODIC)
    assert unit.derived_stats().durability < shielded


def test_periodic_trait_hooks_run_from_the_tick_loop(data, registry):
    """Calling `_fire_trait_triggers` by hand proves the hook, not the wiring.

    Vanguard's durability is applied by a PERIODIC hook; stepping the simulator
    is the only way to show the tick loop actually dispatches trait triggers.
    """
    champs = _champions_with(data, "TFT17_ShieldTank", 2)
    if len(champs) < 2:
        pytest.skip("not enough Vanguards")
    sim, ours, _ = _board(data, registry, champs)
    unit = ours[0]
    assert not any(s.source == "vanguard_durability" for s in unit.status_effects)

    sim.step(data.config.combat.tick_seconds)
    assert any(
        s.source == "vanguard_durability" for s in unit.status_effects
    ), "the tick loop never dispatched a PERIODIC trait hook"


def test_member_only_bonuses_do_not_reach_non_members(data, registry):
    """"Your team gains X. Challengers gain more" is two different bonuses.

    If `members` were computed as the whole team, both halves would land on
    everyone and the trait would be silently twice as strong.
    """
    champs = _champions_with(data, "TFT17_ASTrait", 2)
    if len(champs) < 2:
        pytest.skip("not enough Challengers")
    other = next(
        c
        for c in sorted(data.champions.values(), key=lambda c: c.id)
        if "TFT17_ASTrait" not in c.traits
    )
    _, ours, _ = _board(data, registry, [*champs, other])
    outsider = ours[-1]
    sources = {s.source for s in outsider.status_effects}

    assert "challenger_team" in sources, "the teamwide half did not reach them"
    assert "challenger" not in sources, "the member-only half leaked to a non-member"


def test_marauder_grants_omnivamp_to_the_team(data, registry):
    champs = _champions_with(data, "TFT17_MeleeTrait", 2)
    if len(champs) < 2:
        pytest.skip("not enough Marauders")
    _, ours, _ = _board(data, registry, champs)
    assert ours[0].derived_stats().omnivamp > 0


def test_eradicator_lowers_enemy_resists(data, registry):
    champs = _champions_with(data, "TFT17_JhinUniqueTrait", 1)
    if not champs:
        pytest.skip("Eradicator not in the dataset")
    filler = sorted(data.champions.values(), key=lambda c: c.id)[0]
    _, _, theirs_without = _board(data, registry, [filler])
    _, _, theirs_with = _board(data, registry, champs)

    # Same enemy champion either way, so the resists are comparable.
    assert theirs_with[0].champion.id == theirs_without[0].champion.id
    assert (
        theirs_with[0].derived_stats().armor < theirs_without[0].derived_stats().armor
    )


def test_voyager_shields_tanks_and_amps_everyone_else(data, registry):
    champs = _champions_with(data, "TFT17_FlexTrait", 2)
    if len(champs) < 2:
        pytest.skip("not enough Voyagers")
    _, ours, _ = _board(data, registry, champs)
    for unit in ours:
        if unit.champion.role == "Tank":
            assert unit.shield_amount > 0
        else:
            assert unit.derived_stats().damage_amp > 0


def test_doomer_moves_power_from_enemies_to_the_best_vex(data, registry):
    champs = _champions_with(data, "TFT17_VexUniqueTrait", 1)
    if not champs:
        pytest.skip("Doomer not in the dataset")
    filler = sorted(data.champions.values(), key=lambda c: c.id)[0]
    _, _, plain_enemies = _board(data, registry, [filler], enemy_count=2)
    _, ours, doomed = _board(data, registry, champs, enemy_count=2)

    assert (
        doomed[0].derived_stats().attack_damage
        < plain_enemies[0].derived_stats().attack_damage
    ), "the enemy lost no attack damage"


def test_unimplemented_traits_do_not_crash_a_fight(data, registry):
    """A trait with no hook must still field, fight and finish."""
    unimplemented = sorted(set(data.traits) - set(TRAIT_HOOKS))
    assert unimplemented, "this test is meaningless if everything is implemented"
    for trait_id in unimplemented[:4]:
        champs = _champions_with(data, trait_id, 2)
        if not champs:
            continue
        sim, _, _ = _board(data, registry, champs)
        result = sim.run()
        assert result is not None


def test_trait_hooks_only_fire_for_teams_that_field_the_trait(data, registry):
    """A trait bonus leaking onto the opposing board would be invisible."""
    champs = _champions_with(data, "TFT17_ASTrait", 2)
    if len(champs) < 2:
        pytest.skip("not enough Challengers")
    _, ours, theirs = _board(data, registry, champs, enemy_count=1)
    assert not any(
        s.source.startswith("challenger") for s in theirs[0].status_effects
    )


def test_traits_resolve_after_items(data, registry):
    """Brawler's percentage health must see health items have already added."""
    champs = _champions_with(data, "TFT17_HPTank", 2)
    if len(champs) < 2:
        pytest.skip("not enough Brawlers")

    board = Board()
    hexes = sorted(board.hexes)
    plain, itemised = [], []
    for target, item in ((plain, None), (itemised, "TFT_Item_WarmogsArmor")):
        units = []
        for i, champ in enumerate(champs):
            u = UnitInstance(champ, 1, registry=registry)
            u.position, u.team = hexes[i], 0
            units.append(u)
        if item:
            units[0].equip(data.items[item])
        enemy = UnitInstance(
            sorted(data.champions.values(), key=lambda c: c.id)[0], 1, registry=registry
        )
        enemy.position, enemy.team = hexes[-1], 1
        CombatSimulator(units, [enemy], data, seed=1, board=board)
        target.extend(units)

    brawler_bonus = [s for s in itemised[0].status_effects if s.source == "brawler"]
    plain_bonus = [s for s in plain[0].status_effects if s.source == "brawler"]
    assert brawler_bonus and plain_bonus
    assert brawler_bonus[0].bonuses.get("health") > plain_bonus[0].bonuses.get("health")


def test_a_deeper_board_beats_a_shallower_one(data, registry):
    """The point of the whole batch: composition must beat raw unit count.

    Four Bastions against four unrelated champions of the same cost. Before
    traits dispatched, these two boards fought almost identically.
    """
    trait_id = "TFT17_ResistTank"
    champs = _champions_with(data, trait_id, 4)
    if len(champs) < 4:
        pytest.skip("not enough Bastions")
    costs = sorted(c.cost for c in champs)
    mixed = [
        c
        for c in sorted(data.champions.values(), key=lambda c: c.id)
        if trait_id not in c.traits and c.cost in costs
    ][:4]
    if len(mixed) < 4:
        pytest.skip("no comparable mixed board")

    board = Board()
    hexes = sorted(board.hexes)

    def resists(champions):
        units = []
        for i, champ in enumerate(champions):
            u = UnitInstance(champ, 1, registry=registry)
            u.position, u.team = hexes[i], 0
            units.append(u)
        enemy = UnitInstance(mixed[0], 1, registry=registry)
        enemy.position, enemy.team = hexes[-1], 1
        CombatSimulator(units, [enemy], data, seed=1, board=board)
        return sum(u.derived_stats().armor for u in units)

    assert resists(champs) > resists(mixed)


def test_damage_actually_lands_differently_with_a_trait_active(data, registry):
    """End to end: the trait must reach `deal_damage`, not just the stat block."""
    champs = _champions_with(data, "TFT17_RangedTrait", 2)
    if len(champs) < 2:
        pytest.skip("not enough Snipers")

    board = Board()
    hexes = sorted(board.hexes)

    def hit(champions):
        units = []
        for i, champ in enumerate(champions):
            u = UnitInstance(champ, 1, registry=registry)
            u.position, u.team = hexes[i], 0
            units.append(u)
        victim = UnitInstance(
            sorted(data.champions.values(), key=lambda c: c.id)[0], 1, registry=registry
        )
        victim.position, victim.team = hexes[-1], 1
        sim = CombatSimulator(units, [victim], data, seed=1, board=board)
        victim.current_hp = victim.derived_stats().max_health
        return sim.deal_damage(units[0], victim, 100.0, DamageType.PHYSICAL)

    other = next(
        c
        for c in sorted(data.champions.values(), key=lambda c: c.id)
        if "TFT17_RangedTrait" not in c.traits
    )
    with_trait = hit(champs)
    without = hit([champs[0], other])
    assert with_trait > without, f"{with_trait} vs {without}"


# --- the traits that needed new engine systems (doc 99 entry 35.3) --------


def test_every_trait_now_has_an_implementation(data):
    """Combat-scoped or round-scoped -- but no trait may be inert."""
    from engine.trait_effects import PLAYER_TRAIT_HOOKS

    implemented = set(TRAIT_HOOKS) | set(PLAYER_TRAIT_HOOKS)
    missing = sorted(set(data.traits) - implemented)
    assert not missing, f"traits with no behaviour: {missing}"


def test_shepherd_summons_a_unit(data, registry):
    champs = _champions_with(data, "TFT17_SummonTrait", 3)
    if len(champs) < 3:
        pytest.skip("not enough Shepherds")
    sim, ours, _ = _board(data, registry, champs)
    summons = [u for u in sim.living(0) if u.is_summon]
    assert summons, "Shepherd summoned nothing"
    assert summons[0].champion.id == data.summon_for("shepherd").id


def test_shepherd_summons_do_not_raise_the_shepherd_tier(data, registry):
    """A summon with the trait would let the trait summon its way upward."""
    champs = _champions_with(data, "TFT17_SummonTrait", 3)
    if len(champs) < 3:
        pytest.skip("not enough Shepherds")
    sim, ours, _ = _board(data, registry, champs)
    tier_before = sim.trait_states[0].tier_of("TFT17_SummonTrait")
    summons = [u for u in sim.living(0) if u.is_summon]
    assert summons
    assert all(u.champion.traits == () for u in summons)
    from engine.traits import trait_counts

    counts = trait_counts(sim.living(0))
    assert counts.get("TFT17_SummonTrait", 0) == tier_before


def test_dark_star_executes_low_health_enemies(data, registry):
    champs = _champions_with(data, "TFT17_DarkStar", 2)
    if len(champs) < 2:
        pytest.skip("not enough Dark Stars")
    sim, ours, theirs = _board(data, registry, champs, enemy_count=1)
    victim = theirs[0]
    victim.current_hp = victim.derived_stats().max_health * 0.01
    sim._fire_trait_triggers(0, EffectTrigger.PERIODIC)
    assert not victim.alive, "the black hole did not execute"


def test_dark_star_does_not_execute_a_healthy_enemy(data, registry):
    champs = _champions_with(data, "TFT17_DarkStar", 2)
    if len(champs) < 2:
        pytest.skip("not enough Dark Stars")
    sim, ours, theirs = _board(data, registry, champs, enemy_count=1)
    theirs[0].current_hp = theirs[0].derived_stats().max_health
    sim._fire_trait_triggers(0, EffectTrigger.PERIODIC)
    assert theirs[0].alive


def test_replicator_recasts_the_ability(data, registry):
    """The second casting must actually deal damage, not merely be scheduled."""
    champs = _champions_with(data, "TFT17_APTrait", 2)
    if len(champs) < 2:
        pytest.skip("not enough Replicators")
    caster = next(
        (c for c in champs if c.ability and c.ability.effect_id), None
    )
    if caster is None:
        pytest.skip("no Replicator with an ability")
    sim, ours, theirs = _board(data, registry, champs, enemy_count=2, star=1)
    unit = next(u for u in ours if u.champion.id == caster.id)
    for foe in theirs:
        foe.shields.clear()
        foe.current_hp = foe.derived_stats().max_health
    before = sum(f.current_hp for f in theirs)
    unit.target_uid = theirs[0].uid
    sim._fire_trait_triggers(0, EffectTrigger.ON_CAST, unit=unit, target=theirs[0])
    assert sum(f.current_hp for f in theirs) < before, "the replica never fired"


def test_eradicator_and_nova_do_not_apply_to_the_wrong_team(data, registry):
    champs = _champions_with(data, "TFT17_DRX", 2)
    if len(champs) < 2:
        pytest.skip("not enough N.O.V.A.")
    _, ours, theirs = _board(data, registry, champs, enemy_count=1)
    assert not any(s.source == "nova_surge" for s in theirs[0].status_effects)


def test_round_end_traits_run_and_accumulate(data, registry):
    """Anima banks Tech across rounds and eventually pays out an item."""
    from engine.player import PlayerState
    from engine.trait_effects import apply_round_end

    champs = _champions_with(data, "TFT17_AnimaSquad", 3)
    if len(champs) < 3:
        pytest.skip("not enough Anima")
    player = PlayerState(data=data, registry=registry)
    hexes = sorted(player.hex_board.half_board_hexes(0))
    for i, champ in enumerate(champs):
        player.board[hexes[i]] = UnitInstance(champ, 1, registry=registry)

    bag_before = len(player.item_bag)
    for _ in range(30):
        apply_round_end(player)
    assert player.trait_progress.get("anima_tech") is not None
    assert len(player.item_bag) > bag_before, "Anima never paid out"


def test_round_end_traits_do_not_run_for_a_benched_board(data, registry):
    """Traits count fielded units, so a benched trait must pay nothing."""
    from engine.player import PlayerState
    from engine.trait_effects import apply_round_end

    champs = _champions_with(data, "TFT17_AnimaSquad", 3)
    if len(champs) < 3:
        pytest.skip("not enough Anima")
    player = PlayerState(data=data, registry=registry)
    for champ in champs:
        player.bench[player.free_bench_slots[0]] = UnitInstance(
            champ, 1, registry=registry
        )
    for _ in range(30):
        apply_round_end(player)
    assert not player.trait_progress.get("anima_tech")
    assert not player.item_bag


def test_timebreaker_grants_free_rerolls_on_a_loss_streak(data, registry):
    from engine.player import PlayerState
    from engine.trait_effects import apply_round_end

    champs = _champions_with(data, "TFT17_Timebreaker", 3)
    if len(champs) < 3:
        pytest.skip("not enough Timebreakers")
    player = PlayerState(data=data, registry=registry)
    hexes = sorted(player.hex_board.half_board_hexes(0))
    for i, champ in enumerate(champs):
        player.board[hexes[i]] = UnitInstance(champ, 1, registry=registry)
    player.streak_type, player.streak_count = "loss", 2
    apply_round_end(player)
    assert player.free_rerolls == 1
