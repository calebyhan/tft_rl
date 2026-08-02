"""PvE creep rounds and loot (doc 01 sec 1/5/7, milestone 10).

Before this existed, ``_fight_creeps`` returned an unconditional free win and
nothing ever granted items, which left the entire item system unreachable in a
real game: measured across 80 player-games, **zero** items were ever equipped.
These tests exist to keep both halves honest -- creeps must be beatable *and*
losable, and beating them must actually pay.
"""

from __future__ import annotations

import random

import pytest

from engine.items import ItemRegistry
from engine.loader import load_all
from engine.match import Match
from engine.schema import CreepPlacement, CreepWave, LootOption
from engine.unit import UnitInstance
from rl.opponents import GreedyPolicy, NoOpPolicy
from tests.paths import REAL_DATA_DIR, STARTER_DATA_DIR


@pytest.fixture(scope="module")
def data():
    return load_all(REAL_DATA_DIR)


@pytest.fixture
def registry(data):
    return ItemRegistry(data.items, data.config.max_items_per_unit)


# --- data ----------------------------------------------------------------


def test_creeps_load_and_stay_out_of_the_champion_pool(data):
    """A creep in ``champions`` would become purchasable in the shop."""
    assert data.creeps
    assert not (set(data.creeps) & set(data.champions))
    from engine.shop import SharedPool, ShopError

    pool = SharedPool(data)
    for creep_id in data.creeps:
        # Not merely absent from the pool -- entirely unknown to it.
        with pytest.raises(ShopError, match="unknown champion id"):
            pool.remaining(creep_id)


def test_creeps_have_no_traits(data):
    """A creep with a trait would join trait counts during its own fight."""
    for creep in data.creeps.values():
        assert creep.traits == ()


def test_creeps_never_cast(data):
    """Riot ships PvE monsters with 0 mana and a placeholder ability."""
    for creep in data.creeps.values():
        assert creep.stats.max_mana == 0
        assert creep.ability is None


def test_waves_only_land_on_pve_rounds(data):
    structure = data.config.round_structure
    for wave in data.creep_waves:
        assert structure.is_pve(wave.stage, wave.round), (
            f"wave {wave.stage}-{wave.round} is not a PvE round"
        )


def test_every_wave_drops_something(data):
    for wave in data.creep_waves:
        assert wave.loot, f"wave {wave.stage}-{wave.round} drops nothing"
        for option in wave.loot:
            assert option.gold or option.components


def test_wave_lookup_falls_back_to_the_last_defined(data):
    """A long game must not silently revert to a free win."""
    last = max(data.creep_waves, key=lambda w: (w.stage, w.round))
    assert data.wave_for(last.stage + 3, 7) is last


def test_no_wave_before_the_first_one(data):
    """1-1 is the Realm of the Gods round, not a fight."""
    first = min(data.creep_waves, key=lambda w: (w.stage, w.round))
    assert data.wave_for(1, 1) is None
    assert first.round > 1


def test_wave_units_do_not_overlap(data):
    for wave in data.creep_waves:
        hexes = {(p.row, p.col) for p in wave.units}
        assert len(hexes) == len(wave.units)


# --- loot selection ------------------------------------------------------


def _wave(**kwargs) -> CreepWave:
    base = {
        "stage": 2,
        "round": 7,
        "display_name": "test",
        "units": (CreepPlacement("x", 0, 0),),
        "loot": (),
    }
    return CreepWave(**{**base, **kwargs})


def test_no_loot_options_yields_nothing():
    assert _wave().pick_loot(random.Random(0)) is None


def test_single_option_is_always_picked():
    only = LootOption(weight=1, gold=5)
    assert _wave(loot=(only,)).pick_loot(random.Random(3)) is only


def test_weights_are_respected():
    common = LootOption(weight=9, components=1)
    rare = LootOption(weight=1, gold=5)
    wave = _wave(loot=(common, rare))
    rng = random.Random(0)
    picks = [wave.pick_loot(rng) for _ in range(2000)]
    share = picks.count(rare) / len(picks)
    assert 0.05 < share < 0.15, f"rare option came up {share:.1%} of the time"


def test_loot_choice_is_deterministic_given_a_seed():
    wave = _wave(loot=(LootOption(2, components=1), LootOption(1, gold=5)))
    a = [wave.pick_loot(random.Random(7)) for _ in range(5)]
    b = [wave.pick_loot(random.Random(7)) for _ in range(5)]
    assert a == b


# --- fighting ------------------------------------------------------------


def test_an_empty_board_loses_the_creep_round(data, registry):
    """The whole point: a weak board must be punishable."""
    match = Match(data, [NoOpPolicy() for _ in range(8)], seed=1, registry=registry)
    match.round_id = type(match.round_id)(2, 7)
    player = match.players[0]
    assert not player.board

    report = match._fight_creeps(player)
    assert not report.won
    assert report.damage_taken > 0
    assert player.hp < data.config.starting_hp


def test_losing_a_creep_round_grants_no_loot(data, registry):
    match = Match(data, [NoOpPolicy() for _ in range(8)], seed=1, registry=registry)
    match.round_id = type(match.round_id)(2, 7)
    player = match.players[0]
    gold_before = player.gold
    match._fight_creeps(player)
    assert player.item_bag == []
    assert player.gold == gold_before


def test_a_strong_board_beats_the_creeps_and_is_paid(data, registry):
    match = Match(data, [NoOpPolicy() for _ in range(8)], seed=1, registry=registry)
    match.round_id = type(match.round_id)(2, 7)
    player = match.players[0]
    # Six 3-star five-costs comfortably clears the wave.
    best = max(data.champions.values(), key=lambda c: c.cost)
    for hex_ in player.free_board_hexes[:6]:
        player.board[hex_] = UnitInstance(best, 3, registry=registry)

    gold_before = player.gold
    report = match._fight_creeps(player)
    assert report.won
    assert report.damage_taken == 0
    assert player.item_bag or player.gold > gold_before


def test_pve_damage_is_flat_not_survivor_scaled(data, registry):
    """Doc 01 sec 7: PvE loss damage is 'smaller/fixed'.

    Reusing the PvP survivor formula would be badly wrong here -- creeps carry
    a nominal cost, so it would scale damage off a meaningless number.
    """
    match = Match(data, [NoOpPolicy() for _ in range(8)], seed=1, registry=registry)
    match.round_id = type(match.round_id)(2, 7)
    expected = data.config.stage_base_damage[2]
    report = match._fight_creeps(match.players[0])
    assert report.damage_taken == expected


def test_creep_rounds_are_deterministic(data, registry):
    def play():
        match = Match(
            data, [GreedyPolicy(seed=i) for i in range(8)], seed=99, registry=registry
        )
        match.run()
        return [
            (r.player_id, str(r.round_id), r.won, r.damage_taken)
            for r in match.reports if r.is_pve
        ]

    assert play() == play()


# --- integration ---------------------------------------------------------


def test_items_actually_reach_units_over_a_full_game(data, registry):
    """The regression this milestone exists for.

    Before creep loot and the equip phase, this number was exactly zero over
    80 player-games.
    """
    equipped = 0
    for seed in range(3):
        match = Match(
            data, [GreedyPolicy(seed=i) for i in range(8)], seed=seed, registry=registry
        )
        match.run()
        equipped += sum(len(u.items) for p in match.players for u in p.all_units)
    assert equipped > 0


def test_components_combine_into_completed_items(data, registry):
    """Two components on one unit must become one completed item."""
    completed = 0
    for seed in range(5):
        match = Match(
            data, [GreedyPolicy(seed=i) for i in range(8)], seed=seed, registry=registry
        )
        match.run()
        completed += sum(
            1
            for p in match.players
            for u in p.all_units
            for i in u.items
            if not i.is_component
        )
    assert completed > 0


def test_some_creep_rounds_are_lost_across_many_games(data, registry):
    """If nothing ever loses, the wave is a free win wearing a costume."""
    lost = total = 0
    for seed in range(5):
        match = Match(
            data, [GreedyPolicy(seed=i) for i in range(8)], seed=seed, registry=registry
        )
        match.run()
        pve = [r for r in match.reports if r.is_pve and r.combat_duration > 0]
        total += len(pve)
        lost += sum(1 for r in pve if not r.won)
    assert total > 0
    assert 0 < lost < total, f"lost {lost} of {total} creep rounds"


def test_a_dataset_without_creeps_keeps_the_free_win(data):
    """The starter fixture predates creeps and must still run."""
    starter = load_all(STARTER_DATA_DIR)
    assert starter.creeps == {}
    assert starter.creep_waves == ()

    registry = ItemRegistry(starter.items, starter.config.max_items_per_unit)
    match = Match(
        starter, [GreedyPolicy(seed=i) for i in range(8)], seed=2, registry=registry
    )
    match.run()
    pve = [r for r in match.reports if r.is_pve]
    assert pve and all(r.won and r.damage_taken == 0 for r in pve)


# --- anvil catch-up ------------------------------------------------------


def test_low_hp_players_get_anvil_priority(data, registry):
    match = Match(data, [NoOpPolicy() for _ in range(8)], seed=1, registry=registry)
    for i, player in enumerate(match.players):
        player.hp = 10 + i * 10
    # Bottom half by HP: seats 0-3.
    assert match._has_anvil_priority(match.players[0])
    assert match._has_anvil_priority(match.players[3])
    assert not match._has_anvil_priority(match.players[4])
    assert not match._has_anvil_priority(match.players[7])


def test_anvil_lets_the_policy_choose_its_component(data, registry):
    chosen = "TFT_Item_BFSword"

    class Picky(NoOpPolicy):
        def choose_component(self, player, offered):
            return chosen

    match = Match(data, [Picky() for _ in range(8)], seed=1, registry=registry)
    for i, player in enumerate(match.players):
        player.hp = 10 + i * 10
    components = tuple(sorted(i.id for i in registry.components))
    assert match._pick_component(match.players[0], components, anvil=True) == chosen


def test_a_bad_component_choice_falls_back_to_random(data, registry, caplog):
    class Broken(NoOpPolicy):
        def choose_component(self, player, offered):
            return "not_a_component"

    match = Match(data, [Broken() for _ in range(8)], seed=1, registry=registry)
    components = tuple(sorted(i.id for i in registry.components))
    with caplog.at_level("WARNING"):
        picked = match._pick_component(match.players[0], components, anvil=True)
    assert picked in components
    assert "not on offer" in caplog.text


def test_without_anvil_priority_the_policy_is_not_consulted(data, registry):
    class Picky(NoOpPolicy):
        def choose_component(self, player, offered):
            raise AssertionError("should not be consulted without anvil priority")

    match = Match(data, [Picky() for _ in range(8)], seed=1, registry=registry)
    components = tuple(sorted(i.id for i in registry.components))
    assert match._pick_component(match.players[0], components, anvil=False) in components


def test_greedy_anvil_pick_completes_an_item_when_it_can(data, registry):
    """The catch-up should be used well, not just consumed."""
    match = Match(data, [NoOpPolicy() for _ in range(8)], seed=1, registry=registry)
    player = match.players[0]
    champion = max(data.champions.values(), key=lambda c: c.cost)
    unit = UnitInstance(champion, 2, registry=registry)
    player.board[player.free_board_hexes[0]] = unit
    unit.equip(registry.get("TFT_Item_BFSword"))

    policy = GreedyPolicy(seed=0)
    components = tuple(sorted(i.id for i in registry.components))
    picked = policy.choose_component(player, components)
    assert registry.combine("TFT_Item_BFSword", picked) is not None
