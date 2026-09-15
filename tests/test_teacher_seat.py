"""An action-space teacher playing a non-agent seat must play the agent's game.

The stronger-field test puts the search teacher into opponent seats. That is
only a stronger field if the seat adapter reproduces the teacher exactly: doc
99 entry 160.101 found a shadow env that silently resolved items differently
and played a different game. So the contract here is byte-level: seat 0 driven
through ``TFTEnv`` and seat 0 driven by :class:`TeacherSeat` inside a plain
``Match`` must leave every player in the same state after every round.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loader import load_all  # noqa: E402
from engine.match import Match  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import SEARCH_SEED_OFFSET, greedy_action_policy  # noqa: E402
from rl.opponents import FAST8, default_opponent  # noqa: E402
from rl.search import search_item_greedy_policy  # noqa: E402
from rl.teacher_seat import TeacherSeat  # noqa: E402
from tests.paths import REAL_DATA_DIR  # noqa: E402


@pytest.fixture(scope="module")
def data():
    logging.disable(logging.WARNING)
    yield load_all(REAL_DATA_DIR)
    logging.disable(logging.NOTSET)


def _greedy(env, seed):
    return greedy_action_policy(env, econ=FAST8)


def _buy_and_item_search(env, seed):
    # Buy search is the component that registers a ``choose_component`` hook
    # on its own rng, so it is the one that can desync item resolution.
    return search_item_greedy_policy(
        env, econ=FAST8, rng_seed=seed + SEARCH_SEED_OFFSET,
        depth=1, panel_size=1, trials=1, margin=0.25, buy_search=True,
    )


def _snapshot(match):
    rows = []
    for player in match.players:
        board = sorted(
            (str(hex_), unit.champion.id, unit.star_level,
             tuple(i.id for i in unit.items))
            for hex_, unit in player.board.items()
        )
        bench = [
            None if unit is None
            else (unit.champion.id, unit.star_level, tuple(i.id for i in unit.items))
            for unit in player.bench
        ]
        rows.append((
            player.hp, player.level, player.xp, player.gold, player.alive,
            tuple(board), tuple(bench), tuple(i.id for i in player.item_bag),
            tuple(getattr(a, "id", a) for a in player.augments),
        ))
    return str(match.round_id), tuple(rows)


def _env_trace(data, build, seed, max_rounds):
    env = TFTEnv(data, max_actions_per_round=600)
    policy = build(env, seed)
    observation, _ = env.reset(seed=seed)
    trace, last_round = [], str(env.match.round_id)
    while len(trace) < max_rounds:
        action = int(policy(observation, env.action_masks()))
        observation, _, terminated, truncated, _ = env.step(action)
        if str(env.match.round_id) != last_round:
            last_round = str(env.match.round_id)
            # Entering a carousel round, TFTEnv has already run the draft up
            # to the agent's pick, while Match.play_round has not started it.
            # Snapshotting there compares a half-drafted lobby with an
            # undrafted one. A real carousel desync still shows one round on.
            if not env.match.is_realm_round:
                trace.append(_snapshot(env.match))
        if terminated or truncated:
            break
    return trace


def _seat_trace(data, build, seed, max_rounds):
    env = TFTEnv(data, max_actions_per_round=600)
    seat = TeacherSeat(data, lambda view: build(view, seed), seat=0)
    policies = [seat] + [default_opponent(i) for i in range(1, env.n_players)]
    match = Match(data, policies, seed=seed, registry=env.registry)
    trace = []
    while (
        len(trace) < max_rounds
        and not match.finished
        and match.players[0].alive
    ):
        match.play_round()
        if not match.is_realm_round:
            trace.append(_snapshot(match))
    return trace


@pytest.mark.parametrize("seed", [1, 2, 7])
def test_greedy_teacher_seat_replays_the_agent_game(data, seed):
    env_trace = _env_trace(data, _greedy, seed, max_rounds=10_000)
    seat_trace = _seat_trace(data, _greedy, seed, max_rounds=10_000)
    assert len(env_trace) > 20, "the game ended too early to exercise realm rounds"
    assert seat_trace == env_trace


def test_search_teacher_seat_replays_the_agent_game(data):
    seed = 3
    env_trace = _env_trace(data, _buy_and_item_search, seed, max_rounds=18)
    seat_trace = _seat_trace(data, _buy_and_item_search, seed, max_rounds=18)
    assert len(env_trace) == 18
    assert seat_trace == env_trace


def test_teacher_seat_can_fill_a_non_agent_seat(data):
    """Seat 5 exercises the seat index everywhere seat 0 would hide a bug."""
    env = TFTEnv(data, max_actions_per_round=600)
    policies = [default_opponent(i) for i in range(env.n_players)]
    seat = TeacherSeat(data, lambda view: _greedy(view, 0), seat=5)
    policies[5] = seat
    result = Match(data, policies, seed=11, registry=env.registry).run()
    assert sorted(result.placements.values()) == list(range(1, 9))
    assert seat.actions_taken > 0
