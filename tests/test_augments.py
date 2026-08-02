"""Augment system tests (milestone 9, doc 01 sec 8).

These run against the real dataset because the frozen starter fixture predates
augments and deliberately has none -- which is itself worth asserting, since a
dataset without augments must keep working exactly as before.
"""

from __future__ import annotations

import random

import pytest

from engine import augments as augment_hooks
from engine.items import ItemRegistry
from engine.loader import load_all
from engine.match import Match
from engine.player import IllegalAction, PlayerState
from engine.schema import AugmentDef, AugmentSchedule, GameData
from engine.unit import UnitInstance
from rl.opponents import GreedyPolicy, NoOpPolicy
from tests.paths import REAL_DATA_DIR, STARTER_DATA_DIR


@pytest.fixture(scope="module")
def data() -> GameData:
    return load_all(REAL_DATA_DIR)


@pytest.fixture
def player(data) -> PlayerState:
    registry = ItemRegistry(data.items, data.config.max_items_per_unit)
    return PlayerState(data, registry, player_id=0)


def _augment(**kwargs) -> AugmentDef:
    base = {"id": "test_aug", "display_name": "Test", "tier": "silver", "params": {}}
    return AugmentDef(**{**base, **kwargs})


# --- schema --------------------------------------------------------------


def test_schedule_requires_parallel_rounds_and_tiers():
    with pytest.raises(ValueError, match="parallel"):
        AugmentSchedule(rounds=((2, 1), (3, 2)), tiers=("silver",))


def test_schedule_tier_lookup():
    schedule = AugmentSchedule(rounds=((2, 1), (3, 2)), tiers=("silver", "gold"))
    assert schedule.tier_at(2, 1) == "silver"
    assert schedule.tier_at(3, 2) == "gold"
    assert schedule.tier_at(2, 2) is None
    assert schedule.enabled


def test_empty_schedule_is_disabled():
    assert not AugmentSchedule().enabled


# --- data ----------------------------------------------------------------


def test_real_data_ships_augments(data):
    assert data.augments
    assert data.config.augments.enabled
    for tier in data.config.augments.tiers:
        # Every scheduled tier must be able to fill a full offer, or a reveal
        # round would silently present fewer choices than configured.
        assert len(data.augments_of_tier(tier)) >= data.config.augments.choices


def test_starter_fixture_has_no_augments():
    """The frozen fixture predates the feature and must stay unaffected."""
    starter = load_all(STARTER_DATA_DIR)
    assert starter.augments == {}
    assert not starter.config.augments.enabled


def test_every_shipped_augment_does_something(data):
    """No augment may be inert: it grants a stat, or has a known hook."""
    for augment in data.augments.values():
        has_stats = bool(augment_hooks.board_bonuses([augment]).values)
        assert has_stats or augment_hooks.is_implemented(augment.effect_id), (
            f"{augment.id} grants no stat and has no implemented effect"
        )


# --- offering ------------------------------------------------------------


def test_offer_size_matches_config(data):
    offer = augment_hooks.AugmentOffer(data)
    choices = offer.offer("silver", random.Random(0))
    assert len(choices) == data.config.augments.choices
    assert len({a.id for a in choices}) == len(choices)
    assert all(a.tier == "silver" for a in choices)


def test_offer_excludes_already_held(data):
    offer = augment_hooks.AugmentOffer(data)
    silver = data.augments_of_tier("silver")
    held = list(silver[:2])
    for seed in range(20):
        choices = offer.offer("silver", random.Random(seed), exclude=held)
        assert not ({a.id for a in choices} & {a.id for a in held})


def test_offer_is_deterministic_given_a_seed(data):
    offer = augment_hooks.AugmentOffer(data)
    first = offer.offer("gold", random.Random(11))
    second = offer.offer("gold", random.Random(11))
    assert [a.id for a in first] == [a.id for a in second]


def test_offer_shrinks_rather_than_repeating_when_tier_is_exhausted(data):
    offer = augment_hooks.AugmentOffer(data)
    silver = list(data.augments_of_tier("silver"))
    choices = offer.offer("silver", random.Random(0), exclude=silver[:-1])
    assert len(choices) == 1


def test_unknown_tier_offers_nothing(data):
    offer = augment_hooks.AugmentOffer(data)
    assert offer.offer("mythic", random.Random(0)) == ()


# --- picking -------------------------------------------------------------


def test_pick_moves_the_offer_into_held_augments(player, data):
    offered = data.augments_of_tier("silver")[:3]
    player.offer_augments(offered)
    assert player.has_pending_augment
    chosen = player.pick_augment(1)
    assert chosen is offered[1]
    assert player.augments == [offered[1]]
    assert not player.has_pending_augment


def test_pick_without_an_offer_is_illegal(player):
    with pytest.raises(IllegalAction, match="no augment offer"):
        player.pick_augment(0)


def test_pick_out_of_range_is_illegal(player, data):
    player.offer_augments(data.augments_of_tier("silver")[:2])
    with pytest.raises(IllegalAction, match="out of range"):
        player.pick_augment(5)


# --- effects -------------------------------------------------------------


def test_instant_gold_pays_on_pick(player):
    before = player.gold
    player.offer_augments([_augment(effect_id="augment_instant_gold", params={"gold": 12})])
    player.pick_augment(0)
    assert player.gold == before + 12


def test_instant_xp_can_level_the_player(player):
    player.offer_augments([_augment(effect_id="augment_instant_xp", params={"xp": 100})])
    before = player.level
    player.pick_augment(0)
    assert player.level > before


def test_instant_items_land_in_the_bag(player):
    player.offer_augments(
        [
            _augment(
                effect_id="augment_instant_items",
                params={"items": ["TFT_Item_BFSword", "TFT_Item_ChainVest"]},
            )
        ]
    )
    player.pick_augment(0)
    assert [i.id for i in player.item_bag] == [
        "TFT_Item_BFSword",
        "TFT_Item_ChainVest",
    ]


def test_unknown_granted_item_is_skipped_not_fatal(player, caplog):
    """Doc 03 sec 2.4: unmodelled content warns and no-ops, never crashes."""
    player.offer_augments(
        [_augment(effect_id="augment_instant_items", params={"items": ["nope"]})]
    )
    player.pick_augment(0)
    assert player.item_bag == []


def test_bonus_income_pays_every_round(player):
    from engine.economy import RoundId

    player.offer_augments([_augment(effect_id="augment_bonus_income", params={"gold": 3})])
    player.pick_augment(0)
    gold = player.gold
    player.award_income(RoundId(2, 2))
    first = player.gold - gold
    gold = player.gold
    player.award_income(RoundId(2, 3))
    second = player.gold - gold
    # Income itself varies with interest, but the augment's 3 is in both.
    assert first >= 3 and second >= 3


def test_extra_board_slot_raises_the_field_cap(player):
    before = player.max_board_units
    player.offer_augments(
        [_augment(effect_id="augment_extra_board_slot", params={"board_slots": 1})]
    )
    player.pick_augment(0)
    assert player.max_board_units == before + 1


def test_unimplemented_effect_warns_once_and_still_grants_stats(player, caplog):
    """The stat half of a partly-modelled augment must still apply."""
    augment = _augment(effect_id="augment_not_a_real_hook", params={"health": 250})
    player.offer_augments([augment])
    with caplog.at_level("WARNING"):
        player.pick_augment(0)
    assert "no implementation" in caplog.text
    assert player.augment_bonuses().get("health") == 250


# --- application to combat ----------------------------------------------


def test_augment_stats_reach_deployed_units(player, data):
    champion = data.champions[sorted(data.champions)[0]]
    unit = UnitInstance(champion, 1, registry=player.registry)
    player.bench[0] = unit
    player.move_to_board(0, player.free_board_hexes[0])

    baseline = unit.derived_stats().max_health
    player.offer_augments([_augment(params={"health": 500})])
    player.pick_augment(0)
    player.deploy_for_combat(0)
    assert unit.derived_stats().max_health == pytest.approx(baseline + 500)


def test_combat_trait_bonuses_do_not_erase_augment_bonuses(data):
    """Regression: combat overwrites trait bonuses at fight start.

    Augments therefore cannot ride on the trait slot -- they live in a separate
    owner slot, and this asserts a real fight does not clear them.
    """
    registry = ItemRegistry(data.items, data.config.max_items_per_unit)
    match = Match(data, [NoOpPolicy() for _ in range(8)], seed=3, registry=registry)


    attacker, defender = match.players[0], match.players[1]
    champion = data.champions[sorted(data.champions)[0]]
    for player in (attacker, defender):
        unit = UnitInstance(champion, 1, registry=registry)
        player.bench[0] = unit
        player.move_to_board(0, player.free_board_hexes[0])

    attacker.augments.append(_augment(params={"health": 1000}))
    buffed = attacker.board_units[0]
    plain = defender.board_units[0]
    match._resolve_fight(attacker, defender)
    assert buffed.derived_stats().max_health > plain.derived_stats().max_health


def test_ghost_board_carries_the_source_players_augments(data):
    registry = ItemRegistry(data.items, data.config.max_items_per_unit)
    match = Match(data, [NoOpPolicy() for _ in range(8)], seed=5, registry=registry)


    source = match.players[1]
    champion = data.champions[sorted(data.champions)[0]]
    unit = UnitInstance(champion, 1, registry=registry)
    source.bench[0] = unit
    source.move_to_board(0, source.free_board_hexes[0])
    source.augments.append(_augment(params={"health": 750}))

    clones = match._clone_board(source, team=1)
    plain = UnitInstance(champion, 1, registry=registry)
    assert clones[0].derived_stats().max_health == pytest.approx(
        plain.derived_stats().max_health + 750
    )


# --- match integration ---------------------------------------------------


def test_every_living_player_holds_an_augment_after_a_reveal(data):
    registry = ItemRegistry(data.items, data.config.max_items_per_unit)
    match = Match(
        data, [GreedyPolicy(seed=i) for i in range(8)], seed=1, registry=registry
    )
    stage, round_ = data.config.augments.rounds[0]
    while (match.round_id.stage, match.round_id.round) != (stage, round_):
        match.play_round()
    match.play_round()
    for player in match.living_players:
        assert len(player.augments) == 1
        assert not player.has_pending_augment


def test_a_policy_can_choose_its_augment(data):
    """The optional ``choose_augment`` hook is honoured over the default."""

    class Picky(NoOpPolicy):
        def choose_augment(self, player, offers):
            return len(offers) - 1

    registry = ItemRegistry(data.items, data.config.max_items_per_unit)
    match = Match(data, [Picky() for _ in range(8)], seed=2, registry=registry)
    player = match.players[0]
    offered = data.augments_of_tier("silver")[:3]
    player.offer_augments(offered)
    match._resolve_augment_pick(player)
    assert player.augments == [offered[-1]]


def test_a_seat_without_the_hook_takes_the_first_offer(data):
    registry = ItemRegistry(data.items, data.config.max_items_per_unit)
    match = Match(data, [NoOpPolicy() for _ in range(8)], seed=2, registry=registry)
    player = match.players[0]
    offered = data.augments_of_tier("silver")[:3]
    player.offer_augments(offered)
    match._resolve_augment_pick(player)
    assert player.augments == [offered[0]]


@pytest.mark.parametrize("bad_choice", [99, -1, "not an index", None])
def test_bad_policy_choice_falls_back_to_the_first_offer(data, caplog, bad_choice):
    class Broken(NoOpPolicy):
        def choose_augment(self, player, offers):
            return bad_choice

    registry = ItemRegistry(data.items, data.config.max_items_per_unit)
    match = Match(data, [Broken() for _ in range(8)], seed=4, registry=registry)
    player = match.players[0]
    offered = data.augments_of_tier("silver")[:3]
    player.offer_augments(offered)
    with caplog.at_level("WARNING"):
        match._resolve_augment_pick(player)
    assert "first offer" in caplog.text
    assert player.augments == [offered[0]]


def test_a_full_match_gives_everyone_every_reveal(data):
    registry = ItemRegistry(data.items, data.config.max_items_per_unit)
    match = Match(
        data, [GreedyPolicy(seed=i) for i in range(8)], seed=9, registry=registry
    )
    match.run()
    reveals = len(data.config.augments.rounds)
    # A player eliminated early gets fewer, but nobody exceeds the schedule and
    # nobody is offered the same augment twice.
    for player in match.players:
        assert len(player.augments) <= reveals
        assert len({a.id for a in player.augments}) == len(player.augments)
    survivor = max(match.players, key=lambda p: p.hp)
    assert len(survivor.augments) == reveals


def test_matches_stay_deterministic_with_augments(data):
    registry = ItemRegistry(data.items, data.config.max_items_per_unit)

    def play():
        match = Match(
            data, [GreedyPolicy(seed=i) for i in range(8)], seed=42, registry=registry
        )
        result = match.run()
        return result.placements, [
            [a.id for a in p.augments] for p in match.players
        ]

    assert play() == play()


# --- the RL action space -------------------------------------------------


def test_agent_picks_augments_through_its_own_action_space(data):
    """The env seat must not be auto-picked for by the match."""
    from rl.env import TFTEnv
    from rl.evaluate import scripted_policy

    env = TFTEnv(data=data, seed=5)
    policy = scripted_policy(env)
    obs, _ = env.reset(seed=5)
    terminated = False
    while not terminated:
        obs, _, terminated, _, info = env.step(policy(obs, env.action_mask()))

    # An eliminated player misses the reveals after its death, so the target is
    # the reveals it actually lived through -- not the full schedule.
    played = [r.round_id for r in env.match.reports if r.player_id == env.agent_seat]
    last = max((r.stage, r.round) for r in played)
    survived = [r for r in data.config.augments.rounds if r <= last]
    assert survived, "seed died before the first reveal; pick another"
    assert len(env.player.augments) == len(survived)
    assert not env.player.has_pending_augment
    assert info["illegal_action"] is False


def test_end_planning_is_masked_off_while_an_offer_is_pending(data):
    from rl.env import TFTEnv

    env = TFTEnv(data=data, seed=5)
    env.reset(seed=5)
    space = env.action_space_helper
    player = env.player
    # Round 1-1 is a realm round, so clear that forced pick first -- this test
    # is about the augment one.
    if player.has_pending_offering:
        env.step(space.offering_offset)
    player.offer_augments(data.augments_of_tier("silver")[:3])

    mask = env.action_mask()
    assert not mask[space.end_index]
    assert all(mask[space.augment_offset + i] for i in range(3))

    env.step(space.augment_offset + 2)
    assert env.action_mask()[space.end_index]
    assert len(player.augments) == 1


def test_augment_actions_are_illegal_with_no_offer(data):
    from rl.env import TFTEnv

    env = TFTEnv(data=data, seed=5)
    env.reset(seed=5)
    space = env.action_space_helper
    assert not env.player.has_pending_augment
    mask = env.action_mask()
    assert not any(
        mask[space.augment_offset + i] for i in range(space.augment_choices)
    )


def test_exhausting_the_action_budget_still_resolves_the_offer(data):
    """A live offer must never reach combat."""
    from rl.env import TFTEnv

    env = TFTEnv(data=data, max_actions_per_round=2, seed=5)
    env.reset(seed=5)
    space = env.action_space_helper
    env.player.offer_augments(data.augments_of_tier("gold")[:3])
    # Burn the budget on anything but the augment.
    for _ in range(2):
        env.step(space.reroll_index if env.action_mask()[space.reroll_index] else 0)
    assert not env.player.has_pending_augment
    assert len(env.player.augments) == 1


def test_the_observation_shows_held_and_offered_augments(data):
    from rl.env import TFTEnv

    env = TFTEnv(data=data, seed=5)
    env.reset(seed=5)
    spec = env.encoder.spec
    start = spec.offset_of("augments")
    assert spec.augment_width > 0

    offered = data.augments_of_tier("silver")[:3]
    env.player.offer_augments(offered)
    obs = env._observe()

    held = obs[start : start + spec.n_augments]
    assert held.sum() == 0  # nothing held yet
    for choice, augment in enumerate(offered):
        block_start = start + spec.n_augments * (1 + choice)
        block = obs[block_start : block_start + spec.n_augments]
        assert block.sum() == 1
        assert block[env.encoder.augment_ids.index(augment.id)] == 1.0

    env.step(env.action_space_helper.augment_offset)
    obs = env._observe()
    held = obs[start : start + spec.n_augments]
    assert held.sum() == 1
    assert held[env.encoder.augment_ids.index(offered[0].id)] == 1.0


# --- datasets without augments -------------------------------------------


def test_a_dataset_without_augments_drops_the_observation_section():
    """The section vanishes rather than padding the vector with dead floats."""
    from rl.env import TFTEnv

    starter = load_all(STARTER_DATA_DIR)
    env = TFTEnv(data=starter, seed=0)
    assert env.encoder.spec.augment_width == 0
    assert dict(env.encoder.spec.describe())["augments"] == 0
    obs, _ = env.reset(seed=0)
    assert obs.shape == (env.encoder.size,)


def test_augment_actions_exist_but_are_never_legal_without_augments():
    """The action layout must not change shape with a data edit.

    Sizing the block from config rather than from the loaded augments means a
    model trained on one dataset keeps the same action indices on another.
    """
    from rl.env import TFTEnv

    starter = load_all(STARTER_DATA_DIR)
    env = TFTEnv(data=starter, seed=0)
    space = env.action_space_helper
    assert space.augment_choices == 3

    obs, _ = env.reset(seed=0)
    terminated = False
    while not terminated:
        mask = env.action_mask()
        assert not any(
            mask[space.augment_offset + i] for i in range(space.augment_choices)
        )
        assert mask[space.end_index], "END_PLANNING must stay legal with no offers"
        obs, _, terminated, _, _ = env.step(env.sample_legal_action())


def test_a_full_match_runs_on_a_dataset_without_augments():
    starter = load_all(STARTER_DATA_DIR)
    registry = ItemRegistry(starter.items, starter.config.max_items_per_unit)
    match = Match(
        starter, [GreedyPolicy(seed=i) for i in range(8)], seed=3, registry=registry
    )
    match.run()
    assert all(not p.augments for p in match.players)
    assert len(match.placements) == 8
