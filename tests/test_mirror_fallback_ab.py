"""The mirror arm must play what the advisor would advise (doc 99 entry 160.160).

The arm is only a measurement of ``plan_advice``'s fallback if the four
searches, run in a live game with the patched panel, decide exactly as they do
on the advisor's own mirrored state. That is pinned first, at forced margins so
the whole ranking is compared. The rest pins the patch's scope, when its
reflection is taken, the scaled arm's budgets, and the retention arithmetic.
"""

from __future__ import annotations

import logging
import math
import random
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import rl.search as search_mod  # noqa: E402
import scripts.mirror_fallback_ab as driver  # noqa: E402
from bridge.decide import battle_shim, mirror_state  # noqa: E402
from engine.loader import load_all  # noqa: E402
from rl.search import best_buy, best_item_prefix, best_move, best_swap  # noqa: E402
from tests.paths import REAL_DATA_DIR  # noqa: E402
from tests.test_bridge_search_fidelity import (  # noqa: E402
    FORCE,
    _observed,
    _states_for_fidelity,
)


@pytest.fixture(scope="module")
def data():
    logging.disable(logging.WARNING)
    yield load_all(REAL_DATA_DIR)
    logging.disable(logging.NOTSET)


@pytest.fixture
def patched_panel():
    original = search_mod.opponent_panel

    def install(env, data):
        search_mod.opponent_panel = driver.mirror_panel_fn(env, data, original)
        return search_mod.opponent_panel

    yield install
    search_mod.opponent_panel = original


def _board(player):
    return sorted(
        (hex_.q, hex_.r, unit.champion.id, unit.star_level,
         tuple(item.id for item in unit.items))
        for hex_, unit in player.board.items()
    )


def _decide(live_or_shim, player, match, slots):
    buy = best_buy(live_or_shim, random.Random(11), panel_size=2, trials=2, margin=FORCE)
    swap = best_swap(live_or_shim, random.Random(12), max_candidates=4, panel_size=2,
                     trials=2, margin=FORCE)
    item_trace = []
    items = best_item_prefix(player, match, random.Random(13), depth=1, panel_size=2,
                             trials=2, max_items=slots, margin=FORCE,
                             trace_callback=item_trace.extend)
    move_trace = []
    move = best_move(live_or_shim, random.Random(14), max_candidates=6, panel_size=2,
                     trials=2, margin=FORCE, trace_callback=move_trace.append)
    return {"buy": buy, "swap": swap, "items": (items, item_trace),
            "move": (move, move_trace)}


def test_the_mirror_arm_decides_as_the_advisor_would(data, patched_panel):
    answered = {"buy": 0, "swap": 0, "move": 0}
    states = 0
    for env in _states_for_fidelity(data):
        patched_panel(env, data)
        live = SimpleNamespace(player=env.player, match=env.match)
        slots = env.action_space_helper.item_bag_slots
        in_game = _decide(live, env.player, env.match, slots)

        shim, hero = battle_shim(mirror_state(_observed(env)), data, env.registry)
        advised = _decide(shim, hero, shim.match, slots)

        for name in in_game:
            assert in_game[name] == advised[name], (
                f"{name} differs from the advisor's mirror at {env.match.round_id}"
            )
        answered["buy"] += in_game["buy"] is not None
        answered["swap"] += in_game["swap"] is not None
        answered["move"] += in_game["move"][0] is not None
        states += 1
    assert states >= 6, f"only {states} states"
    assert all(answered.values()), f"a search never answered: {answered}"


def _one_state(data):
    return next(iter(_states_for_fidelity(data)))


def test_the_reflection_is_held_for_the_round(data, patched_panel):
    env = _one_state(data)
    panel = patched_panel(env, data)
    first = panel(env.match, env.player, 2)
    assert len(first) == 1 and first[0] is not env.player
    assert _board(first[0]) == _board(env.player)
    before = _board(env.player)

    removed = env.player.board.popitem()
    try:
        again = panel(env.match, env.player, 2)
    finally:
        env.player.board[removed[0]] = removed[1]
    assert again[0] is first[0]
    assert _board(again[0]) == before

    env.match.round_id = SimpleNamespace(stage=env.match.round_id.stage + 1, round=1)
    assert panel(env.match, env.player, 2)[0] is not first[0]


_REAL_PANEL = search_mod.opponent_panel


def test_other_seats_still_get_the_real_panel(data, patched_panel):
    env = _one_state(data)
    panel = patched_panel(env, data)
    other = next(p for p in env.match.players
                 if p is not env.player and p.alive and p.board)
    expected = [p.player_id for p in _REAL_PANEL(env.match, other, 2)]
    assert expected, "the real panel is empty -- the comparison is vacuous"
    assert [p.player_id for p in panel(env.match, other, 2)] == expected


def test_an_empty_board_gets_no_panel(data, patched_panel):
    env = _one_state(data)
    panel = patched_panel(env, data)
    saved = dict(env.player.board)
    env.player.board.clear()
    try:
        assert panel(env.match, env.player, 2) == []
    finally:
        env.player.board.update(saved)


def test_the_scaled_arm_halves_only_swap_and_move(monkeypatch):
    seen = {}

    def capture(env, **kwargs):
        seen[kwargs["swap_kwargs"]["margin"], kwargs["move_kwargs"]["margin"]] = kwargs
        return object()

    monkeypatch.setattr(driver, "search_item_greedy_policy", capture)
    driver.teacher(None, 0, "mirror")
    driver.teacher(None, 0, "mirror_scaled")
    shipped, scaled = seen[(0.5, 0.5)], seen[(0.25, 0.25)]
    for key in ("margin", "panel_size", "trials", "depth", "buy_search"):
        assert shipped[key] == scaled[key]
    assert shipped["margin"] == 0.25


def test_retention_arithmetic():
    floor, full, half = [5.0] * 4, [3.0] * 4, [4.0] * 4
    result = driver.retention(floor, full, half, resamples=200)
    assert result["retention"] == pytest.approx(0.5)
    assert result["ci_low"] == pytest.approx(0.5)
    assert result["ci_high"] == pytest.approx(0.5)

    rng = random.Random(3)
    floor = [rng.choice(range(1, 9)) for _ in range(400)]
    full = [max(1, f - rng.choice((0, 1, 2, 3))) for f in floor]
    test = [max(1, f - rng.choice((0, 1))) for f in floor]
    result = driver.retention(floor, full, test, resamples=500)
    assert result["ci_low"] < result["retention"] < result["ci_high"]

    with pytest.raises(ValueError):
        driver.retention([1.0], [1.0, 2.0], [1.0])


def test_paired_guards_a_single_game():
    result = driver.paired([3.0], [2.0])
    assert result["delta"] == -1.0 and math.isnan(result["se"])
