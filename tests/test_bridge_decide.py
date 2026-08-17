"""The decision service must only ever recommend legal, executable actions.

Doc 04 milestone 3. Advice a person cannot carry out is worse than no advice,
so the assertions are: every recommendation is legal by the *engine's* mask
(never a re-implementation of the rules -- doc 03 sec 2.10 says the mask is the
authority), every recommendation actually executes, and probabilities are a
distribution over legal actions only.

The no-model path is asserted to be uniform *on purpose*: a silent fallback
that looked like a policy would be worse than none, so the test pins that it is
visibly not one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import random  # noqa: E402

from bridge.adapter import (  # noqa: E402
    from_player_state,
    pool_for,
    to_player_state,
)
from bridge.decide import Advisor  # noqa: E402
from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from tests.paths import REAL_DATA_DIR  # noqa: E402


@pytest.fixture(scope="module")
def data():
    return load_all(REAL_DATA_DIR)


@pytest.fixture(scope="module")
def states(data):
    """Mid-game observations captured from real engine games."""
    from rl.evaluate import scripted_policy

    out = []
    for seed in (0, 3, 7):
        env = TFTEnv(data=data)
        policy = scripted_policy(env, sell_bench=True, buy_synergy=True,
                                 match_items=True, corner_carry=True)
        obs, _info = env.reset(seed=seed)
        for _ in range(6000):
            rid = env.match.round_id
            if rid.stage >= 3 and env.player.board:
                out.append(from_player_state(
                    env.player, rid,
                    [p for p in env.match.players
                     if p.player_id != env.player.player_id]))
                break
            action = int(policy(obs, env.action_masks()))
            obs, _r, term, trunc, _i = env.step(action)
            if term or trunc:
                break
    assert out, "no states captured -- the whole file would assert nothing"
    return out


def test_every_recommendation_is_legal_and_executes(data, states):
    """The claim that matters: advice is executable, not merely plausible.

    Legality is checked against the engine mask, then each recommendation is
    actually *run* through the executor on a fresh copy of the state. A mask
    that says yes while the executor raises is the exact divergence doc 03
    sec 2.10 forbids, and only executing catches it.
    """
    advisor = Advisor(data)
    for state in states:
        recs = advisor.recommend(state, top_k=8)
        assert recs, "no legal action offered for a mid-game state"
        for rec in recs:
            player, _rid, _opps = to_player_state(
                state, data, advisor.registry)
            mask = advisor.executor.legal_mask(player)
            assert mask[rec.index], (
                f"{rec.kind} recommended but the engine mask says illegal"
            )
            # Executes without raising IllegalAction on a fresh state.
            # `apply` needs a pool (BUY draws from it) and an rng; the
            # executor's selection state is reset so one recommendation
            # cannot leave a partial SELECT behind for the next.
            advisor.executor.reset()
            advisor.executor.apply(player, rec.index,
                                   pool_for(state, data), random.Random(0))


def test_probabilities_cover_only_legal_actions(data, states):
    """An illegal action must never carry probability mass."""
    advisor = Advisor(data)
    for state in states:
        player, round_id, opponents = to_player_state(
            state, data, advisor.registry or _reg(data))
        mask = np.asarray(advisor.executor.legal_mask(player), dtype=bool)
        obs = advisor.encoder.encode(player, round_id, opponents,
                                     advisor.board_hexes)
        scores = advisor._scores(obs, mask)
        assert scores[~mask].sum() == pytest.approx(0.0), (
            "illegal actions carry probability mass"
        )
        assert scores.sum() == pytest.approx(1.0, abs=1e-5)


def test_without_a_model_the_advice_is_visibly_uniform(data, states):
    """Not a silent fallback: it must be obvious there is no policy."""
    advisor = Advisor(data)
    recs = advisor.recommend(states[0], top_k=5)
    probabilities = {round(r.probability, 9) for r in recs}
    assert len(probabilities) == 1, (
        f"no-model advisor produced non-uniform scores {probabilities} -- it "
        "is pretending to be a policy"
    )


def test_recommendations_name_champions_not_slot_numbers(data, states):
    """A recommendation has to be actionable by a human reading their screen."""
    advisor = Advisor(data)
    for state in states:
        for rec in advisor.recommend(state, top_k=8):
            if rec.kind in ("BUY", "SELL", "SELECT"):
                assert "TFT" in rec.detail or "empty" in rec.detail, (
                    f"{rec.kind} detail {rec.detail!r} names no champion"
                )


def _reg(data):
    from engine.items import ItemRegistry

    return ItemRegistry(data.items, data.config.max_items_per_unit)
