"""The search teacher's board tie-break must be a visible fact (doc 99 entry 160.156).

Entry 160.155 found `best_swap`, `buy_candidates` and the item search's
finishing rule breaking ties by the board dict's insertion order -- the order
units entered the board, which no observer can see. `BOARD_TIE_BREAK = "hex"`
breaks them by hex order instead. The claim pinned here is exact: in hex mode,
reversing the board's insertion order changes no decision. The legacy mode is
exercised too, so the fixture is shown to contain ties that insertion order
decides -- otherwise the first assertion would hold vacuously.
"""

from __future__ import annotations

import logging
import random
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import rl.search as search_mod  # noqa: E402
from bridge.decide import battle_shim  # noqa: E402
from bridge.state import ObservedSeat, ObservedState, ObservedUnit  # noqa: E402
from engine.hexgrid import Board  # noqa: E402
from engine.items import ItemRegistry  # noqa: E402
from engine.loader import load_all  # noqa: E402
from rl.search import (  # noqa: E402
    best_swap,
    buy_candidates,
    item_candidate_team,
    item_layout_signature,
)
from tests.paths import REAL_DATA_DIR  # noqa: E402
from tests.test_bridge_search_fidelity import FORCE, _planning_states  # noqa: E402


@pytest.fixture(scope="module")
def data():
    logging.disable(logging.WARNING)
    yield load_all(REAL_DATA_DIR)
    logging.disable(logging.NOTSET)


@contextmanager
def _tie_break(mode: str):
    previous = search_mod.BOARD_TIE_BREAK
    search_mod.BOARD_TIE_BREAK = mode
    try:
        yield
    finally:
        search_mod.BOARD_TIE_BREAK = previous


@contextmanager
def _reversed_board(player):
    original = list(player.board.items())
    player.board.clear()
    player.board.update(reversed(original))
    try:
        yield
    finally:
        player.board.clear()
        player.board.update(original)


def _decisions(env):
    live = SimpleNamespace(player=env.player, match=env.match)
    swap = best_swap(live, random.Random(12), max_candidates=4, panel_size=2,
                     trials=2, margin=FORCE)
    buys = tuple(
        (slot,
         tuple((unit.champion.id, unit.star_level, hex_) for unit, hex_ in extra),
         tuple(sorted(drops)))
        for slot, extra, drops in buy_candidates(env.player, env.match)
    )
    team, _remaining = item_candidate_team(env.player, env.match, (), finish=True)
    return swap, buys, item_layout_signature(team)


def test_decisions_do_not_depend_on_board_insertion_order(data):
    states = legacy_differs = 0
    for env in _planning_states(data, seeds=(0, 1, 2, 3), per_seed=3):
        with _tie_break("hex"):
            forward = _decisions(env)
            with _reversed_board(env.player):
                backward = _decisions(env)
        assert forward == backward, (
            f"hex tie-break still depends on insertion order at {env.match.round_id}"
        )
        with _tie_break("insertion"):
            legacy_forward = _decisions(env)
            with _reversed_board(env.player):
                legacy_backward = _decisions(env)
        legacy_differs += legacy_forward != legacy_backward
        states += 1
    assert states >= 8, f"only {states} states"
    assert legacy_differs, (
        "no state where insertion order decided anything -- the fixture cannot "
        "show the repair"
    )


def _shim(data, hero: ObservedSeat, shop=()):
    registry = ItemRegistry(data.items, data.config.max_items_per_unit)
    state = ObservedState(stage=3, round=2, hero=hero, shop=list(shop))
    return battle_shim(state, data, registry)


def _both_orders(player, compute):
    forward = compute()
    with _reversed_board(player):
        backward = compute()
    return forward, backward


def _own(data):
    return [(h.q, h.r) for h in sorted(Board().half_board_hexes(0))]


def test_item_finish_ignores_insertion_order(data):
    """Two equally strong units and one leftover item: a guaranteed tie.

    Captured games contain this tie on about one bag-holding step in ten, but
    not in the few states the fixture above samples, so it is built here.
    """
    own = _own(data)
    cheap = sorted(c.id for c in data.champions.values() if c.cost == 1)
    component = sorted(i.id for i in data.items.values() if i.is_component)[0]
    hero = ObservedSeat(level=5, gold=10, bench_slots=9, item_bag=(component,),
                        board=[ObservedUnit(cheap[0], 1, position=own[0]),
                               ObservedUnit(cheap[1], 1, position=own[5])])
    shim, player = _shim(data, hero)

    def finish():
        team, _remaining = item_candidate_team(player, shim.match, (), finish=True)
        return item_layout_signature(team)

    with _tie_break("hex"):
        forward, backward = _both_orders(player, finish)
    assert forward == backward
    with _tie_break("insertion"):
        forward, backward = _both_orders(player, finish)
    assert forward != backward, "the constructed board holds no item-finish tie"


def test_pair_completion_ignores_insertion_order(data):
    """Three 1-star copies on the board: which two a pair consumes is a tie."""
    own = _own(data)
    champion = sorted(c.id for c in data.champions.values() if c.cost == 1)[0]
    hero = ObservedSeat(level=5, gold=10, bench_slots=9,
                        board=[ObservedUnit(champion, 1, position=hex_)
                               for hex_ in own[:3]])
    shim, player = _shim(data, hero, shop=[champion, None, None, None, None])

    def drops():
        return tuple((slot, tuple(sorted(dropped)))
                     for slot, _extra, dropped in buy_candidates(player, shim.match))

    with _tie_break("hex"):
        forward, backward = _both_orders(player, drops)
    assert forward and forward == backward
    with _tie_break("insertion"):
        forward, backward = _both_orders(player, drops)
    assert forward != backward, "the constructed board holds no pair-drop tie"


def test_an_unknown_tie_break_is_refused():
    with _tie_break("random"):
        with pytest.raises(ValueError):
            search_mod._board_order(SimpleNamespace(board={}))
