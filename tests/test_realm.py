"""Realm of the Gods: the HP-ordered contested draft (doc 01 sec 1, milestone 11).

This is the only mechanic in the engine where seats **compete for a shared
resource in a fixed order** -- every other planning action is independent per
seat. The ordering is a comeback mechanic, so the tests that matter are the
ones proving an early picker genuinely denies a later one.
"""

from __future__ import annotations

import pytest

from engine.economy import RoundId
from engine.items import ItemRegistry
from engine.loader import load_all
from engine.match import Match
from engine.player import IllegalAction
from engine.schema import RealmOffering, RealmSchedule
from rl.opponents import GreedyPolicy, NoOpPolicy
from tests.paths import REAL_DATA_DIR, STARTER_DATA_DIR


@pytest.fixture(scope="module")
def data():
    return load_all(REAL_DATA_DIR)


@pytest.fixture
def registry(data):
    return ItemRegistry(data.items, data.config.max_items_per_unit)


def _match(data, registry, policies=None, seed=1, at=(2, 4)):
    policies = policies or [NoOpPolicy() for _ in range(8)]
    match = Match(data, policies, seed=seed, registry=registry)
    match.round_id = RoundId(*at)
    return match


# --- schedule ------------------------------------------------------------


def test_schedule_requires_parallel_rounds_and_tiers():
    with pytest.raises(ValueError, match="parallel"):
        RealmSchedule(rounds=((2, 4), (3, 4)), cost_tiers=(1,))


def test_schedule_rejects_negative_extra_offerings():
    with pytest.raises(ValueError, match="extra_offerings"):
        RealmSchedule(extra_offerings=-1)


def test_empty_schedule_is_disabled():
    assert not RealmSchedule().enabled


def test_real_config_schedules_the_draft(data):
    realm = data.config.realm
    assert realm.enabled
    assert realm.is_realm_round(2, 4)
    assert not realm.is_realm_round(2, 5)
    assert realm.cost_tier_at(2, 4) in data.config.pool_sizes


# --- pick order ----------------------------------------------------------


def test_lowest_hp_picks_first(data, registry):
    """The mechanic this milestone exists for."""
    match = _match(data, registry)
    for i, player in enumerate(match.players):
        player.hp = 80 - i * 10  # seat 7 lowest, seat 0 highest
    match._realm_phase()
    # Everyone picked (no deferring seats), so verify by pool order instead:
    # rebuild and inspect the queue before any pick happens.
    match2 = _match(data, registry, policies=[_Deferring() for _ in range(8)])
    for i, player in enumerate(match2.players):
        player.hp = 80 - i * 10
    match2._realm_phase()
    assert match2._realm_queue == [7, 6, 5, 4, 3, 2, 1, 0]


def test_ties_break_by_seat_deterministically(data, registry):
    match = _match(data, registry, policies=[_Deferring() for _ in range(8)])
    for player in match.players:
        player.hp = 50
    match._realm_phase()
    assert match._realm_queue == [0, 1, 2, 3, 4, 5, 6, 7]


def test_dead_players_do_not_draft(data, registry):
    match = _match(data, registry, policies=[_Deferring() for _ in range(8)])
    for player in match.players[:3]:
        player.hp = 0
    match._realm_phase()
    assert set(match._realm_queue).isdisjoint({0, 1, 2})


class _Deferring(NoOpPolicy):
    """Stands in for the RL seat: never resolves its own pick."""

    defers_realm_pick = True


# --- contention ----------------------------------------------------------


def test_an_early_picker_denies_a_later_one(data, registry):
    """Offerings are a shared, shrinking line-up, not per-player menus.

    The seat that picks second must be shown one fewer offering than the seat
    that picked first, and must not be shown what was taken.
    """
    match = _match(data, registry, policies=[_Deferring() for _ in range(8)])
    for i, player in enumerate(match.players):
        player.hp = 80 - i * 10
    match._realm_phase()

    first = match.players[match._realm_queue[0]]
    offered_to_first = list(first.realm_offer)
    taken = offered_to_first[0]
    first.pick_offering(0)
    match.resume_realm()

    second = match.players[match._realm_queue[0]]
    offered_to_second = list(second.realm_offer)
    assert len(offered_to_second) == len(offered_to_first) - 1
    assert taken not in offered_to_second


def test_offerings_outnumber_seats(data, registry):
    """The last picker must still have a choice, not a leftover."""
    match = _match(data, registry, policies=[_Deferring() for _ in range(8)])
    match._realm_phase()
    expected = len(match.living_players) + data.config.realm.extra_offerings
    assert len(match._realm_offerings) == expected


def test_drafted_champions_come_out_of_the_shared_pool(data, registry):
    """A drafted unit is one fewer copy in everyone's shop."""
    match = _match(data, registry, policies=[_Deferring() for _ in range(8)])
    tier = data.config.realm.cost_tier_at(2, 4)
    before = sum(match.pool.remaining(c.id) for c in data.champions.values() if c.cost == tier)
    match._realm_phase()
    after = sum(match.pool.remaining(c.id) for c in data.champions.values() if c.cost == tier)
    assert after == before - len(match._realm_offerings)


def test_every_offering_carries_a_component(data, registry):
    match = _match(data, registry, policies=[_Deferring() for _ in range(8)])
    match._realm_phase()
    assert all(o.component_id is not None for o in match._realm_offerings)


# --- taking an offering --------------------------------------------------


def test_picking_grants_the_champion_and_the_component(data, registry):
    match = _match(data, registry, policies=[_Deferring() for _ in range(8)])
    match._realm_phase()
    player = match.players[match._realm_queue[0]]
    offering = player.realm_offer[0]

    player.pick_offering(0)
    assert any(u.champion.id == offering.champion_id for u in player.all_units)
    assert [i.id for i in player.item_bag] == [offering.component_id]
    assert not player.has_pending_offering


def test_picking_without_an_offer_is_illegal(data, registry):
    match = _match(data, registry)
    with pytest.raises(IllegalAction, match="no realm offering"):
        match.players[0].pick_offering(0)


def test_picking_out_of_range_is_illegal(data, registry):
    match = _match(data, registry, policies=[_Deferring() for _ in range(8)])
    match._realm_phase()
    player = match.players[match._realm_queue[0]]
    with pytest.raises(IllegalAction, match="out of range"):
        player.pick_offering(99)


def test_a_full_bench_converts_the_champion_to_gold(data, registry):
    """Real TFT always hands you the unit; losing the pick would be worse."""
    match = _match(data, registry, policies=[_Deferring() for _ in range(8)])
    match._realm_phase()
    player = match.players[match._realm_queue[0]]
    champion = next(iter(data.champions.values()))
    from engine.unit import UnitInstance

    player.bench = [
        UnitInstance(champion, 1, registry=registry)
        for _ in range(data.config.bench_size)
    ]
    gold_before = player.gold
    player.pick_offering(0)
    assert player.gold > gold_before
    assert player.item_bag  # the component still lands


def test_a_bad_policy_choice_falls_back_to_the_first(data, registry, caplog):
    class Broken(NoOpPolicy):
        def choose_offering(self, player, offerings):
            return 99

    match = _match(data, registry, policies=[Broken() for _ in range(8)])
    with caplog.at_level("WARNING"):
        match._realm_phase()
    assert "taking the first" in caplog.text


# --- round structure -----------------------------------------------------


def test_a_realm_round_has_no_combat(data, registry):
    """2-4 sits between fights: nobody takes damage, no streak moves."""
    match = _match(data, registry, policies=[GreedyPolicy(seed=i) for i in range(8)])
    hp_before = [p.hp for p in match.players]
    streaks = [(p.streak_type, p.streak_count) for p in match.players]

    reports = match.play_round()
    assert reports == []
    assert [p.hp for p in match.players] == hp_before
    assert [(p.streak_type, p.streak_count) for p in match.players] == streaks


def test_a_realm_round_still_pays_income(data, registry):
    match = _match(data, registry, policies=[NoOpPolicy() for _ in range(8)])
    gold_before = [p.gold for p in match.players]
    match.play_round()
    after = [p.gold for p in match.players]
    assert all(a > b for a, b in zip(after, gold_before, strict=True))


def test_the_round_advances_past_a_realm_round(data, registry):
    match = _match(data, registry, policies=[NoOpPolicy() for _ in range(8)])
    match.play_round()
    assert (match.round_id.stage, match.round_id.round) == (2, 5)


# --- integration ---------------------------------------------------------


def test_a_full_match_drafts_at_every_realm_round(data, registry):
    match = Match(
        data, [GreedyPolicy(seed=i) for i in range(8)], seed=4, registry=registry
    )
    match.run()
    # The winner survived every draft, so it should hold units it never bought.
    assert match.placements
    assert not match._realm_queue


def test_matches_stay_deterministic_with_the_draft(data, registry):
    def play():
        match = Match(
            data, [GreedyPolicy(seed=i) for i in range(8)], seed=77, registry=registry
        )
        result = match.run()
        return result.placements

    assert play() == play()


def test_a_dataset_without_a_realm_schedule_skips_the_draft():
    starter = load_all(STARTER_DATA_DIR)
    assert not starter.config.realm.enabled
    registry = ItemRegistry(starter.items, starter.config.max_items_per_unit)
    match = Match(
        starter, [GreedyPolicy(seed=i) for i in range(8)], seed=2, registry=registry
    )
    match.run()
    assert all(not p.has_pending_offering for p in match.players)


# --- the RL seat ---------------------------------------------------------


def test_the_agent_drafts_through_its_own_action_space(data):
    from rl.env import TFTEnv
    from rl.evaluate import scripted_policy

    env = TFTEnv(data=data, seed=5)
    policy = scripted_policy(env)
    space = env.action_space_helper
    obs, _ = env.reset(seed=5)

    drafts = 0
    terminated = False
    while not terminated:
        action = policy(obs, env.action_mask())
        if space.decode(action).kind.name == "PICK_OFFERING":
            drafts += 1
        obs, _, terminated, _, info = env.step(action)
    assert drafts > 0
    assert not info.get("illegal_action")


def test_end_planning_is_blocked_while_an_offering_is_pending(data):
    from rl.env import TFTEnv

    env = TFTEnv(data=data, seed=5)
    env.reset(seed=5)
    space = env.action_space_helper
    assert env.player.has_pending_offering, "1-1 should open with a draft"
    assert not env.action_mask()[space.end_index]

    env.step(space.offering_offset)
    assert not env.player.has_pending_offering


def test_the_draft_resumes_for_seats_above_the_agent(data):
    """Seats with more HP than the agent must still get their pick."""
    from rl.env import TFTEnv

    env = TFTEnv(data=data, seed=5)
    env.reset(seed=5)
    space = env.action_space_helper
    env.step(space.offering_offset)
    # Finish the round so resume_realm() runs.
    while env.action_mask()[space.end_index] is False:
        env.step(space.offering_offset)
    env.step(space.end_index)
    assert not env.match._realm_queue


def test_exhausting_the_budget_still_resolves_the_offering(data):
    from rl.env import TFTEnv

    env = TFTEnv(data=data, max_actions_per_round=2, seed=5)
    env.reset(seed=5)
    space = env.action_space_helper
    assert env.player.has_pending_offering
    for _ in range(2):
        env.step(space.reroll_index if env.action_mask()[space.reroll_index] else 0)
    assert not env.player.has_pending_offering


def test_offering_actions_are_illegal_with_no_draft(data):
    from rl.env import TFTEnv

    env = TFTEnv(data=data, seed=5)
    env.reset(seed=5)
    space = env.action_space_helper
    env.step(space.offering_offset)
    mask = env.action_mask()
    assert not any(
        mask[space.offering_offset + i] for i in range(space.realm_offerings)
    )


def test_offering_is_encoded_and_decoded_symmetrically(data):
    from engine.hexgrid import Board
    from rl.action import Action, ActionKind, ActionSpace

    space = ActionSpace(data.config)
    space.bind_board(tuple(sorted(Board().half_board_hexes(0))))
    for choice in range(space.realm_offerings):
        action = Action(ActionKind.PICK_OFFERING, choice)
        assert space.decode(space.encode(action)) == action


def test_offering_block_is_absent_when_the_realm_is_disabled():
    from engine.hexgrid import Board
    from rl.action import ActionSpace

    starter = load_all(STARTER_DATA_DIR)
    space = ActionSpace(starter.config)
    space.bind_board(tuple(sorted(Board().half_board_hexes(0))))
    assert space.realm_offerings == 0
    assert space.offering_offset == space.reroll_index


def test_a_realm_offering_is_a_frozen_value():
    a = RealmOffering("x", "y")
    assert a == RealmOffering("x", "y")
    with pytest.raises(AttributeError):
        a.champion_id = "z"


def test_undrafted_offerings_return_to_the_pool(data, registry):
    """Regression: the spare offerings leaked one champion per realm round.

    The smoke test's pool-conservation invariant caught this; the unit suite
    did not, because no test had checked the pool across a whole draft.
    """
    match = _match(data, registry, policies=[NoOpPolicy() for _ in range(8)])
    tier = data.config.realm.cost_tier_at(2, 4)
    tier_ids = [c.id for c in data.champions.values() if c.cost == tier]
    before = sum(match.pool.remaining(cid) for cid in tier_ids)

    match._realm_phase()
    after = sum(match.pool.remaining(cid) for cid in tier_ids)

    # Exactly one champion left the pool per seat that drafted -- the spares
    # went back.
    drafted = sum(len(p.bench_units) for p in match.players)
    assert before - after == drafted
    assert match._realm_offerings == []


def test_a_whole_game_conserves_the_champion_pool(data, registry):
    """The invariant the leak violated, asserted directly."""
    match = Match(
        data, [GreedyPolicy(seed=i) for i in range(8)], seed=17, registry=registry
    )
    match.run()

    total = sum(data.config.pool_sizes[c.cost] for c in data.champions.values())
    free = sum(match.pool.remaining(c.id) for c in data.champions.values())
    held = sum(u.pool_copies for p in match.players for u in p.all_units)
    in_shops = sum(
        1 for p in match.players for slot in p.shop.slots if slot is not None
    )
    assert free + held + in_shops == total
