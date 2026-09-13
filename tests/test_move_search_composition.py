"""Positioning search inside the composed teacher (doc 99 entry 160.147).

``best_move`` itself is covered in ``tests/test_search.py``: it never mutates
the live board, never loses a unit and only emits legal actions. What is new
is the composition, so these tests pin only that: the move fires once per
phase *after* the item plan, its budget reaches the search, its diagnostics
count what happened, and a teacher that does not ask for it never calls it.
"""

from __future__ import annotations

import pytest

import rl.search as search_mod
from engine.loader import load_all
from engine.unit import UnitInstance
from rl.action import ActionKind
from rl.env import TFTEnv
from rl.search import search_item_greedy_policy
from tests.paths import STARTER_DATA_DIR

MOVE_KWARGS = {"max_candidates": 6, "panel_size": 2, "trials": 2, "margin": 0.5}


def _move_env(**policy_kwargs):
    """Two fielded units, a free hex, two bag items and nothing to buy.

    The bench is empty so neither the greedy fielding stage nor the swap has
    anything to do; any SELECT in the emitted stream must be the move.
    """
    data = load_all(STARTER_DATA_DIR)
    env = TFTEnv(data, max_actions_per_round=50)
    policy = search_item_greedy_policy(env, rng_seed=0, **policy_kwargs)
    observation, _ = env.reset(seed=4)
    player = env.player
    player.shop.slots = [None] * player.config.shop_slots
    player.gold = 0
    player.level = 2
    player.board.clear()
    player.bench = [None] * player.config.bench_size

    carry_hex = player.hex_board.to_combat(0, 0, 0)
    tank_hex = player.hex_board.to_combat(0, 0, 1)
    carry = UnitInstance(data.champions["TFT17_Jinx"], registry=player.registry)
    tank = UnitInstance(data.champions["TFT17_Poppy"], registry=player.registry)
    player.board[carry_hex] = carry
    player.board[tank_hex] = tank
    player.item_bag[:] = [
        data.items["TFT_Item_Deathblade"],
        data.items["TFT_Item_SparringGloves"],
    ]
    free_hex = next(
        h for h in sorted(player._own_hexes) if h not in player.board
    )
    return env, policy, observation, carry, carry_hex, free_hex


def _drive(env, policy, observation, limit: int = 30):
    emitted = []
    for _ in range(limit):
        action = policy(observation, env.action_masks())
        decoded = env.action_space_helper.decode(action)
        emitted.append(decoded)
        if decoded.kind is ActionKind.END_PLANNING:
            break
        observation, _reward, terminated, truncated, _info = env.step(action)
        assert not (terminated or truncated)
    return emitted


def _stub(monkeypatch, answer, calls):
    def recording(env_, rng, **kwargs):
        calls.append({"kwargs": kwargs, "bag": [i.id for i in env_.player.item_bag]})
        return answer[0] if answer else None

    monkeypatch.setattr(search_mod, "best_move", recording)


def test_move_fires_once_after_the_item_plan_and_reaches_the_world(monkeypatch):
    calls: list = []
    answer: list = []
    _stub(monkeypatch, answer, calls)
    env, policy, observation, carry, carry_hex, free_hex = _move_env(
        move_search=True, move_kwargs=dict(MOVE_KWARGS)
    )
    answer.append((carry_hex, free_hex))

    emitted = _drive(env, policy, observation)
    kinds = [action.kind for action in emitted]

    assert len(calls) == 1, "one positioning search per planning phase"
    assert ActionKind.EQUIP in kinds, "the fixture must reach an item decision"
    select = kinds.index(ActionKind.SELECT)
    assert all(
        index < select
        for index, kind in enumerate(kinds)
        if kind is ActionKind.EQUIP
    ), "the move must follow every item assignment"
    assert calls[0]["bag"] == [], "the item plan had already emptied the bag"
    assert kinds[select + 1] is ActionKind.PLACE
    assert kinds[-1] is ActionKind.END_PLANNING
    assert env.player.board[free_hex] is carry
    assert carry_hex not in env.player.board


def test_move_budget_reaches_best_move_rather_than_its_defaults(monkeypatch):
    """``best_move`` ships panel 1 / trials 3; losing the budget changes the rule."""
    calls: list = []
    _stub(monkeypatch, [], calls)
    env, policy, observation, *_ = _move_env(
        move_search=True, move_kwargs=dict(MOVE_KWARGS)
    )

    _drive(env, policy, observation)

    assert [call["kwargs"] for call in calls] == [MOVE_KWARGS]


def test_move_diagnostics_count_decisions_and_accepted_moves(monkeypatch):
    calls: list = []
    answer: list = []
    _stub(monkeypatch, answer, calls)
    env, policy, observation, _carry, carry_hex, free_hex = _move_env(
        move_search=True, move_kwargs=dict(MOVE_KWARGS)
    )
    answer.append((carry_hex, free_hex))
    _drive(env, policy, observation)
    assert policy.move_search_stats == {"search_decisions": 1, "accepted_moves": 1}

    declined_calls: list = []
    _stub(monkeypatch, [], declined_calls)
    env, policy, observation, *_ = _move_env(
        move_search=True, move_kwargs=dict(MOVE_KWARGS)
    )
    emitted = _drive(env, policy, observation)
    assert policy.move_search_stats == {"search_decisions": 1, "accepted_moves": 0}
    assert not any(action.kind is ActionKind.SELECT for action in emitted)


@pytest.mark.parametrize("buy_search", [False, True])
def test_a_teacher_without_move_search_never_positions(monkeypatch, buy_search):
    """The control arm must not reach ``best_move`` by any path."""

    def forbidden(*_args, **_kwargs):
        raise AssertionError("control arm called best_move")

    monkeypatch.setattr(search_mod, "best_move", forbidden)
    env, policy, observation, *_ = _move_env(buy_search=buy_search)

    emitted = _drive(env, policy, observation)

    assert emitted[-1].kind is ActionKind.END_PLANNING
    assert policy.move_search_stats == {"search_decisions": 0, "accepted_moves": 0}
