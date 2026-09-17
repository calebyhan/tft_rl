"""The established searches must decide identically on an observed state.

Doc 04 milestone 1 proved the adapter faithful through the *observation*. The
advisor now runs the four searches of the established teacher (doc 99 entry
160.152) on a reconstructed state, and those read things the encoder never
did: bench indices, the item bag, opponent boards and their order. So the bar
is re-stated for them, at the level of the decision: a search run on the live
match and the same search run on that state after capture, JSON and
reconstruction must return the same answer from the same rng.

Margins are forced far below zero so every call returns its best candidate.
That compares the whole ranking, not just the "no change" threshold, and it
stops the test passing on ``None == None``.

**The live board is compared exactly as the game left it.** Entry 160.155
found ``best_swap``, ``buy_candidates`` and the item finish breaking ties by
the board dict's insertion order, which no observer can see, and this harness
used to re-sort the live board to paper over it. Entry 160.156 made the
tie-break visible, so the harness no longer re-sorts: any remaining dependence
on hidden board order fails here.
"""

from __future__ import annotations

import copy
import logging
import random
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bridge.adapter import from_player_state, to_player_state, validate  # noqa: E402
from bridge.decide import battle_shim  # noqa: E402
from bridge.state import ObservedState  # noqa: E402
from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import greedy_action_policy  # noqa: E402
from rl.opponents import FAST8  # noqa: E402
from rl.search import best_buy, best_item_prefix, best_move, best_swap  # noqa: E402
from tests.paths import REAL_DATA_DIR  # noqa: E402

FORCE = -1e9


@pytest.fixture(scope="module")
def data():
    logging.disable(logging.WARNING)
    yield load_all(REAL_DATA_DIR)
    logging.disable(logging.NOTSET)


def _planning_states(data, seeds, *, every=17, per_seed=4, need_bag=False):
    """Yield a live env mid-planning. Consume each before asking for the next.

    The env keeps stepping after a yield, so anything compared must be computed
    while the generator is suspended -- a stored ``env.player`` would describe
    the end of the game, not the captured moment.
    """
    for seed in seeds:
        env = TFTEnv(data, max_actions_per_round=600)
        policy = greedy_action_policy(env, econ=FAST8)
        observation, _ = env.reset(seed=seed)
        taken = 0
        for step in range(20_000):
            player = env.player
            interesting = (
                env.match.round_id.stage >= 2
                and player.board
                and (player.item_bag if need_bag
                     else any(u is not None for u in player.bench) or player.item_bag)
            )
            if step % every == 0 and interesting:
                yield env
                taken += 1
                if taken >= per_seed:
                    break
            observation, _, terminated, truncated, _ = env.step(
                int(policy(observation, env.action_masks()))
            )
            if terminated or truncated:
                break


def _observed(env):
    opponents = [p for p in env.match.players if p.player_id != env.player.player_id]
    state = from_player_state(env.player, env.match.round_id, opponents)
    return ObservedState.from_json(state.to_json())


def test_hero_item_bag_survives_json_and_the_adapter(data):
    found = False
    for env in _planning_states(data, seeds=range(6), per_seed=1, need_bag=True):
        state = _observed(env)
        hero, _round, _opponents = to_player_state(state, data, env.registry)
        assert [i.id for i in hero.item_bag] == [i.id for i in env.player.item_bag]
        found = True
    assert found, "no captured state held an item bag -- the round trip is untested"


def test_board_order_in_the_file_does_not_change_the_reconstruction(data):
    checked = False
    for env in _planning_states(data, seeds=range(4), per_seed=1):
        state = _observed(env)
        if len(state.hero.board) < 2:
            continue
        reordered = copy.deepcopy(state)
        reordered.hero.board = list(reversed(state.hero.board))
        forward, _r, _o = to_player_state(state, data, env.registry)
        backward, _r, _o = to_player_state(reordered, data, env.registry)
        assert list(forward.board) == list(backward.board) == sorted(forward.board)
        checked = True
    assert checked, "no captured board had two units -- ordering untested"


def test_validate_names_an_unknown_bag_item(data):
    state = ObservedState()
    state.hero.item_bag = ("TFT_Item_NotARealItem",)
    problems = validate(state, data)
    assert any("NotARealItem" in problem for problem in problems), problems


def _compare_searches(env, data) -> dict[str, bool]:
    """Run each search on both sides; return which ones gave a real answer."""
    where = env.match.round_id
    live = SimpleNamespace(player=env.player, match=env.match)
    shim, hero = battle_shim(_observed(env), data, env.registry)

    buy = [best_buy(side, random.Random(11), panel_size=2, trials=2, margin=FORCE)
           for side in (live, shim)]
    assert buy[0] == buy[1], f"best_buy diverged at {where}"

    swap = [best_swap(side, random.Random(12), max_candidates=4, panel_size=2,
                      trials=2, margin=FORCE)
            for side in (live, shim)]
    assert swap[0] == swap[1], f"best_swap diverged at {where}"

    slots = env.action_space_helper.item_bag_slots
    items = []
    for player, match in ((env.player, env.match), (hero, shim.match)):
        trace = []
        prefix, diagnostics = best_item_prefix(
            player, match, random.Random(13), depth=1, panel_size=2, trials=2,
            max_items=slots, margin=FORCE, trace_callback=trace.extend,
        )
        items.append((prefix, diagnostics, trace))
    assert items[0] == items[1], f"best_item_prefix diverged at {where}"

    moves = []
    for side in (live, shim):
        trace = []
        found = best_move(side, random.Random(14), max_candidates=6, panel_size=2,
                          trials=2, margin=FORCE, trace_callback=trace.append)
        moves.append((found, trace))
    assert moves[0] == moves[1], f"best_move diverged at {where}"

    return {
        "buy": buy[0] is not None,
        "swap": swap[0] is not None,
        # An empty prefix can be the genuine best, so "exercised" means the
        # search compared at least two layouts -- that is what the trace
        # equality above actually tests.
        "items": items[0][1]["candidate_boards"] > 1,
        "move": moves[0][0] is not None,
    }


def _states_for_fidelity(data):
    yield from _planning_states(data, seeds=(0, 1, 2), per_seed=3)
    # Mid-phase states rarely hold a bag -- the scheduler equips early -- so
    # the item search needs states selected for one, or it is never compared.
    yield from _planning_states(data, seeds=range(3, 9), per_seed=1, need_bag=True)


def test_the_four_searches_decide_identically_on_the_observed_state(data):
    answered = {"buy": 0, "swap": 0, "items": 0, "move": 0}
    states = 0
    for env in _states_for_fidelity(data):
        states += 1
        for name, gave_answer in _compare_searches(env, data).items():
            answered[name] += gave_answer

    assert states >= 6, f"only {states} states captured"
    silent = [name for name, count in answered.items() if count == 0]
    assert not silent, f"never exercised with a real answer: {silent} ({answered})"
