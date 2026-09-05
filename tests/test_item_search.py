"""Regression tests for item-search candidate semantics (doc 99 entry 160.108)."""

from __future__ import annotations

import random

import torch

from engine.items import ItemRegistry
from engine.loader import load_all
from engine.match import Match
from engine.unit import UnitInstance
from rl.action import ActionKind
from rl.env import TFTEnv
from rl.evaluate import greedy_action_policy
from rl.opponents import NoOpPolicy
from rl.search import (
    best_item_prefix,
    item_candidate_layouts,
    item_search_state_seed,
    opponent_panel,
    search_item_greedy_policy,
)
from scripts.item_dense_placement_ab import distilled_item_policy
from scripts.search_item_value_probe import _candidate_board
from tests.paths import STARTER_DATA_DIR


def test_candidate_board_combines_components_without_mutating_live_board():
    data = load_all(STARTER_DATA_DIR)
    registry = ItemRegistry(data.items, data.config.max_items_per_unit)
    policies = [NoOpPolicy() for _ in range(data.config.round_structure.players)]
    match = Match(data, policies, registry=registry)
    player = match.players[0]
    own_hex = player.hex_board.to_combat(0, 0, 0)
    live = UnitInstance(data.champions["TFT17_Jinx"], registry=registry)
    live.equip(data.items["TFT_Item_BFSword"])
    player.board[own_hex] = live

    candidate = _candidate_board(
        match,
        player,
        data.items["TFT_Item_SparringGloves"],
        own_hex,
    )

    assert [item.id for item in candidate[0].items] == ["TFT_Item_InfinityEdge"]
    assert [item.id for item in live.items] == ["TFT_Item_BFSword"]


def test_headroom_candidates_include_real_completion_and_an_alternative_target():
    data = load_all(STARTER_DATA_DIR)
    registry = ItemRegistry(data.items, data.config.max_items_per_unit)
    policies = [NoOpPolicy() for _ in range(data.config.round_structure.players)]
    match = Match(data, policies, registry=registry)
    player = match.players[0]
    carry_hex = player.hex_board.to_combat(0, 0, 0)
    other_hex = player.hex_board.to_combat(0, 0, 1)
    carry = UnitInstance(data.champions["TFT17_Jinx"], registry=registry)
    carry.equip(data.items["TFT_Item_BFSword"])
    player.board[carry_hex] = carry
    player.board[other_hex] = UnitInstance(
        data.champions["TFT17_Poppy"], registry=registry
    )
    player.item_bag.append(data.items["TFT_Item_SparringGloves"])

    layouts, completion_candidates = item_candidate_layouts(player, match, depth=1)

    assert completion_candidates > 0
    assert len(layouts) >= 2
    assert any(
        "TFT_Item_InfinityEdge" in unit_items
        for layout in layouts
        for unit_items in layout
    )
    assert [item.id for item in carry.items] == ["TFT_Item_BFSword"]
    assert [item.id for item in player.item_bag] == ["TFT_Item_SparringGloves"]


def test_item_search_seed_uses_visible_item_and_augment_state_only():
    data = load_all(STARTER_DATA_DIR)
    registry = ItemRegistry(data.items, data.config.max_items_per_unit)
    policies = [NoOpPolicy() for _ in range(data.config.round_structure.players)]
    match = Match(data, policies, registry=registry)
    player, opponent = match.players[:2]
    own_hex = sorted(player._own_hexes)[0]
    player.board[own_hex] = UnitInstance(
        data.champions["TFT17_Jinx"], registry=registry
    )
    opponent.board[own_hex] = UnitInstance(
        data.champions["TFT17_Poppy"], registry=registry
    )
    player.item_bag[:] = [data.items["TFT_Item_BFSword"]]
    panel = opponent_panel(match, player, 1)
    baseline = item_search_state_seed(player, panel)
    assert baseline == item_search_state_seed(player, panel)

    player.item_bag[0] = data.items["TFT_Item_SparringGloves"]
    assert item_search_state_seed(player, panel) != baseline

    player.item_bag[0] = data.items["TFT_Item_BFSword"]
    player.board[own_hex].equip(data.items["TFT_Item_ChainVest"])
    assert item_search_state_seed(player, panel) != baseline


def test_item_search_trace_exposes_every_scored_prefix_without_changing_choice():
    data = load_all(STARTER_DATA_DIR)
    registry = ItemRegistry(data.items, data.config.max_items_per_unit)
    policies = [NoOpPolicy() for _ in range(data.config.round_structure.players)]
    match = Match(data, policies, registry=registry)
    player, opponent = match.players[:2]
    own_hexes = sorted(player._own_hexes)
    player.board[own_hexes[0]] = UnitInstance(
        data.champions["TFT17_Jinx"], registry=registry
    )
    player.board[own_hexes[1]] = UnitInstance(
        data.champions["TFT17_Poppy"], registry=registry
    )
    opponent.board[own_hexes[0]] = UnitInstance(
        data.champions["TFT17_Jinx"], registry=registry
    )
    player.item_bag[:] = [data.items["TFT_Item_Deathblade"]]
    trace = []

    chosen, diagnostics = best_item_prefix(
        player,
        match,
        random.Random(9),
        panel_size=1,
        trials=1,
        trace_callback=trace.extend,
    )

    assert len(trace) == diagnostics["candidate_boards"]
    best_value = max(value for _prefix, value in trace)
    assert any(prefix == chosen and value == best_value for prefix, value in trace)


def test_item_search_margin_keeps_shipped_for_a_small_sampled_edge(monkeypatch):
    data = load_all(STARTER_DATA_DIR)
    registry = ItemRegistry(data.items, data.config.max_items_per_unit)
    policies = [NoOpPolicy() for _ in range(data.config.round_structure.players)]
    match = Match(data, policies, registry=registry)
    player = match.players[0]
    own_hexes = sorted(player._own_hexes)
    player.board[own_hexes[0]] = UnitInstance(
        data.champions["TFT17_Jinx"], registry=registry
    )
    player.board[own_hexes[1]] = UnitInstance(
        data.champions["TFT17_Poppy"], registry=registry
    )
    match.players[1].board[own_hexes[0]] = UnitInstance(
        data.champions["TFT17_Poppy"], registry=registry
    )
    player.item_bag[:] = [data.items["TFT_Item_Deathblade"]]

    def small_target_edge(_data, _board, ours, _theirs, _seed):
        return 0.1 if ours[1].items else 0.0

    monkeypatch.setattr("rl.search.fight_value", small_target_edge)
    permissive, _ = best_item_prefix(
        player, match, random.Random(1), panel_size=1, trials=1
    )
    conservative, _ = best_item_prefix(
        player,
        match,
        random.Random(1),
        panel_size=1,
        trials=1,
        margin=0.25,
    )

    assert permissive
    assert conservative == ()


def _action_env(item_planner):
    data = load_all(STARTER_DATA_DIR)
    env = TFTEnv(data, max_actions_per_round=50)
    policy = greedy_action_policy(env, item_planner=item_planner)
    observation, _ = env.reset(seed=4)
    player = env.player
    player.shop.slots = [None] * player.config.shop_slots
    player.gold = 0
    player.level = 1
    player.board.clear()
    player.bench = [None] * player.config.bench_size

    weak_hex = player.hex_board.to_combat(0, 0, 0)
    weak = UnitInstance(data.champions["TFT17_Poppy"], registry=player.registry)
    carry = UnitInstance(data.champions["TFT17_Jinx"], registry=player.registry)
    carry.equip(data.items["TFT_Item_BFSword"])
    player.board[weak_hex] = weak
    player.bench[0] = carry
    player.item_bag[:] = [
        data.items["TFT_Item_Deathblade"],
        data.items["TFT_Item_SparringGloves"],
    ]
    return env, policy, observation, carry, weak


def test_action_item_plan_runs_after_fielding_and_resolves_the_live_bag_index():
    called = []
    holder = {}

    def planner():
        env, carry, weak = holder["state"]
        called.append(1)
        assert carry in env.player.board_units
        assert weak in env.player.bench_units
        carry_hex = next(
            own_hex for own_hex, unit in env.player.board.items() if unit is carry
        )
        return [("TFT_Item_SparringGloves", carry_hex)]

    env, policy, observation, carry, weak = _action_env(planner)
    holder["state"] = (env, carry, weak)

    first_equip = None
    for _ in range(20):
        action = policy(observation, env.action_masks())
        decoded = env.action_space_helper.decode(action)
        if decoded.kind is ActionKind.EQUIP:
            first_equip = decoded
            break
        observation, _reward, terminated, truncated, _info = env.step(action)
        assert not (terminated or truncated)

    assert called == [1]
    assert first_equip is not None
    assert first_equip.a == 1, "the plan chose the second bag item"
    observation, *_ = env.step(env.action_space_helper.encode(first_equip))
    assert [item.id for item in carry.items] == ["TFT_Item_InfinityEdge"]

    # The planned equip removed bag slot 1. The unchanged historical loop now
    # resumes at the shifted slot 0, and the planner is not called twice.
    second = env.action_space_helper.decode(
        policy(observation, env.action_masks())
    )
    assert second.kind is ActionKind.EQUIP
    assert second.a == 0
    assert called == [1]


def test_control_scheduler_keeps_the_historical_first_bag_item():
    env, policy, observation, _carry, _weak = _action_env(None)
    for _ in range(20):
        action = policy(observation, env.action_masks())
        decoded = env.action_space_helper.decode(action)
        if decoded.kind is ActionKind.EQUIP:
            assert decoded.a == 0
            return
        observation, _reward, terminated, truncated, _info = env.step(action)
        assert not (terminated or truncated)
    raise AssertionError("control scheduler never reached its equip phase")


def test_combined_buy_item_policy_preserves_item_and_resolution_hooks():
    data = load_all(STARTER_DATA_DIR)
    env = TFTEnv(data, max_actions_per_round=50)

    policy = search_item_greedy_policy(env, buy_search=True)

    assert env._external_policy is policy
    assert policy.item_search_stats["fight_calls"] == 0
    assert policy.item_search_trace == []
    assert callable(policy.choose_component)


def test_distilled_item_policy_can_wrap_buy_and_preserve_resolution_hook():
    data = load_all(STARTER_DATA_DIR)
    env = TFTEnv(data, max_actions_per_round=50)

    policy = distilled_item_policy(env, [], threshold=0.0, buy_search=True)

    assert env._external_policy is policy
    assert policy.item_distill_stats["fight_calls"] == 0
    assert callable(policy.choose_component)


def test_combined_distilled_item_policy_preserves_item_and_resolution_hooks():
    data = load_all(STARTER_DATA_DIR)
    env = TFTEnv(data, max_actions_per_round=50)

    policy = distilled_item_policy(
        env, models=[], threshold=0.0, buy_search=True
    )

    assert env._external_policy is policy
    assert policy.item_distill_stats["fight_calls"] == 0
    assert policy.item_distill_models == []
    assert callable(policy.choose_component)


def test_distilled_item_policy_emits_ensemble_override_as_real_equip_action():
    data = load_all(STARTER_DATA_DIR)
    env = TFTEnv(data, scouting="tokens", max_actions_per_round=50)
    observation, _ = env.reset(seed=4)
    player = env.player
    player.shop.slots = [None] * player.config.shop_slots
    player.gold = 0
    player.level = 2
    player.board.clear()
    player.bench = [None] * player.config.bench_size
    own_hexes = sorted(player._own_hexes)
    player.board[own_hexes[0]] = UnitInstance(
        data.champions["TFT17_Jinx"], registry=player.registry
    )
    player.board[own_hexes[1]] = UnitInstance(
        data.champions["TFT17_Poppy"], registry=player.registry
    )
    player.item_bag[:] = [
        data.items["TFT_Item_Deathblade"],
        data.items["TFT_Item_WarmogsArmor"],
    ]
    space = env.action_space_helper
    wanted = space.unit_slots + space.slot_for_hex(own_hexes[1])

    class FixedHead(torch.nn.Module):
        def forward(self, observations):
            batch = next(iter(observations.values())).shape[0]
            scores = torch.zeros(batch, space.item_bag_slots * space.unit_slots)
            scores[:, wanted] = 10.0
            return scores

    policy = distilled_item_policy(env, [FixedHead()], threshold=0.0)
    for _step in range(30):
        action = int(policy(observation, env.action_masks()))
        decoded = space.decode(action)
        if decoded.kind is ActionKind.EQUIP:
            assert decoded.a == 1
            assert decoded.b == space.slot_for_hex(own_hexes[1])
            assert policy.item_distill_stats["overrides"] == 1
            return
        observation, _reward, terminated, truncated, _info = env.step(action)
        assert not (terminated or truncated)
    raise AssertionError("distilled policy never emitted its EQUIP override")
