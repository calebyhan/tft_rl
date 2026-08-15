"""The bridge adapter must be faithful through the *observation* (doc 04 m1).

Doc 04 sec 4: an adapter that is not provably faithful makes every measurement
downstream of it meaningless. So the assertion is not field-by-field -- that
would pass while silently dropping whatever the encoder reads and the
comparison forgot to check -- but on the encoded vector the policy actually
consumes.

The states are taken from real engine games rather than hand-built, so the
fixtures include the cases a constructed one omits: partly-filled benches,
items on units, multi-star units, and mid-game rounds.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bridge.adapter import from_player_state, to_player_state  # noqa: E402
from bridge.state import ObservedState  # noqa: E402
from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from tests.paths import REAL_DATA_DIR  # noqa: E402


@pytest.fixture(scope="module")
def data():
    return load_all(REAL_DATA_DIR)


def _snapshots(data, seed: int, wanted: int = 6):
    """Mid-game states from a real game, with their encoded observations."""
    from rl.evaluate import scripted_policy

    env = TFTEnv(data=data)
    policy = scripted_policy(env, sell_bench=True, buy_synergy=True,
                             match_items=True, corner_carry=True)
    obs, _info = env.reset(seed=seed)
    out = []
    for step in range(4000):
        # Sample states with something on the board, not the empty opening.
        if step % 37 == 0 and env.player.board:
            out.append((env.player, env.match.round_id,
                        [p for p in env.match.players
                         if p.player_id != env.player.player_id]))
            if len(out) >= wanted:
                break
        action = int(policy(obs, env.action_masks()))
        obs, _r, term, trunc, _i = env.step(action)
        if term or trunc:
            break
    return env, out


def _encode(env, player, round_id, opponents):
    return env.encoder.encode(
        player, round_id, opponents, env._board_hexes,
    )


def test_round_trip_through_json_preserves_the_observation(data):
    """The whole claim of milestone 1, end to end."""
    env, snapshots = _snapshots(data, seed=0)
    assert snapshots, "no mid-game states captured -- the probe is asserting nothing"

    for player, round_id, opponents in snapshots:
        before = _encode(env, player, round_id, opponents)
        state = from_player_state(player, round_id, opponents)
        # Through JSON, not just through the dataclass: serialisation is where
        # tuples become lists and `None` positions can quietly become [0, 0].
        rebuilt = ObservedState.from_json(state.to_json())
        hero, rt_round, rt_opponents = to_player_state(
            rebuilt, data, env.player.registry)
        after = _encode(env, hero, rt_round, rt_opponents)
        assert rt_round == round_id
        np.testing.assert_array_equal(before, after)


def test_items_and_stars_survive(data):
    """Named separately: these are the fields a positional test would miss."""
    env, snapshots = _snapshots(data, seed=3)
    seen_items = seen_star = False
    for player, round_id, opponents in snapshots:
        state = from_player_state(player, round_id, opponents)
        hero, _r, _o = to_player_state(state, data, env.player.registry)
        assert state.hero.augments == tuple(a.id for a in player.augments), (
            "augments are their own observation section and must round-trip"
        )
        original = sorted((u.champion.id, u.star_level,
                           tuple(sorted(i.id for i in u.items)))
                          for u in player.board.values())
        rebuilt = sorted((u.champion.id, u.star_level,
                          tuple(sorted(i.id for i in u.items)))
                         for u in hero.board.values())
        assert original == rebuilt
        seen_items |= any(row[2] for row in original)
        seen_star |= any(row[1] > 1 for row in original)
    assert seen_star, "no multi-star unit in any fixture -- star level untested"
    assert seen_items, "no item on any unit in any fixture -- items untested"


def test_unobserved_position_is_distinct_from_a_real_one(data):
    """`None` must survive JSON, or milestone 2 cannot tell invented from real.

    Real match data carries no hex positions (doc 04 sec 3), so the adapter
    fabricates them. A caller measuring positional features has to be able to
    tell which. If `None` round-tripped to `[0, 0]` this would still "work" and
    would silently report fabricated geometry as observed.
    """
    state = ObservedState.from_json(ObservedState().to_json())
    assert state.hero.board == []

    env, snapshots = _snapshots(data, seed=1)
    player, round_id, opponents = snapshots[0]
    captured = from_player_state(player, round_id, opponents)
    assert captured.hero.board, "fixture has no board units"
    assert all(u.position is not None for u in captured.hero.board), (
        "captured board units must carry real coordinates"
    )
    assert all(u is None or u.position is None for u in captured.hero.bench), (
        "bench units have no board coordinate and must not acquire one"
    )
    through = ObservedState.from_json(captured.to_json())
    # Bench holes are positional (`ObservedSeat.bench`), so `None` slots must
    # survive JSON in place -- collapsing them shifts every later slot and
    # changes the encoded vector, which is the bug this file first caught.
    assert [None if u is None else u.position for u in through.hero.bench] == \
           [None if u is None else u.position for u in captured.hero.bench]
    assert len(through.hero.bench) == len(captured.hero.bench)
