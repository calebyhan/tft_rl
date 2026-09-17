"""The advisor's plan: the established teacher's four searches, in phase order.

The teacher of doc 99 entry 160.152 searches the buy first, then one fielding
swap, then the item prefix, then one positioning move. ``plan_advice`` runs
the same four searches at the same budgets on an observed state, applying
each accepted step before the next search sees the board.

Three contracts, in the style of doc 04 milestone 3:

* every step is legal by the engine's mask and actually executes;
* the plan on a live match and on the same state after observation stay in
  lockstep, step for step (per-search fidelity is pinned separately in
  ``test_bridge_search_fidelity.py``);
* the board stays in canonical hex order after every applied step, because
  the searches' tie-breaks iterate it.
"""

from __future__ import annotations

import dataclasses
import logging
import random
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import bridge.decide as decide_mod  # noqa: E402
from bridge.adapter import canonicalize_board, pool_for, to_player_state  # noqa: E402
from bridge.decide import (  # noqa: E402
    PLAN_PHASES,
    Advisor,
    battle_shim,
    plan_advice,
    plan_on,
)
from bridge.state import ObservedSeat, ObservedState, ObservedUnit  # noqa: E402
from engine.hexgrid import Board  # noqa: E402
from engine.items import ItemRegistry  # noqa: E402
from engine.loader import load_all  # noqa: E402
from tests.paths import REAL_DATA_DIR  # noqa: E402
from tests.test_bridge_search_fidelity import (  # noqa: E402
    _observed,
    _planning_states,
    _states_for_fidelity,
)

FORCED = {phase: {"margin": -1e9} for phase in PLAN_PHASES}


@pytest.fixture(scope="module")
def data():
    logging.disable(logging.WARNING)
    yield load_all(REAL_DATA_DIR)
    logging.disable(logging.NOTSET)


def _registry(data):
    return ItemRegistry(data.items, data.config.max_items_per_unit)


def test_every_plan_step_is_legal_and_executes(data):
    advisor = Advisor(data)
    phases_seen: set[str] = set()
    plans = 0
    for env in _states_for_fidelity(data):
        state = _observed(env)
        plan = plan_advice(state, data, env.registry, seed=0, budgets=FORCED)
        assert not plan.problems, plan.problems
        plans += 1

        player, _round, _opponents = to_player_state(state, data, env.registry)
        pool = pool_for(state, data)
        for step in plan.steps:
            advisor.executor.reset()
            for action in step.actions:
                mask = advisor.executor.legal_mask(player)
                assert mask[action], f"{step.phase} step not legal: {step.detail}"
                advisor.executor.apply(player, action, pool, random.Random(0))
            canonicalize_board(player)
            phases_seen.add(step.phase)

    assert plans >= 6, f"only {plans} states planned"
    assert phases_seen == set(PLAN_PHASES), f"phases never planned: {set(PLAN_PHASES) - phases_seen}"


def test_plan_keeps_live_and_observed_in_lockstep(data):
    space = Advisor(data).space
    compared = 0
    for seed, need_bag in ((0, False), (1, False), (3, True), (4, True)):
        states = _planning_states(data, seeds=(seed,), per_seed=1, need_bag=need_bag)
        env = next(states, None)
        if env is None:
            continue
        state = _observed(env)
        shim, hero = battle_shim(state, data, env.registry)

        canonicalize_board(env.player)
        live = plan_on(SimpleNamespace(player=env.player, match=env.match),
                       space, env.match.pool, seed=0, budgets=FORCED)
        observed = plan_on(shim, space, pool_for(state, data), seed=0, budgets=FORCED)

        assert not live.problems and not observed.problems
        assert (live.steps, live.declined) == (observed.steps, observed.declined), (
            f"plans diverged at {env.match.round_id}"
        )
        assert list(hero.board) == sorted(hero.board), "board left out of hex order"
        compared += 1
        states.close()
    assert compared >= 3, f"only {compared} states compared"


def test_the_plan_advises_the_loadout_the_search_scored(data):
    """Item search scores its prefix *plus* the default rule for the rest.

    Advising only the prefix would advise a loadout nobody scored, and every
    other test here would still pass, so the finishing equips are pinned.
    """
    space = Advisor(data).space
    finished = plans = 0
    for env in _planning_states(data, seeds=range(3, 11), per_seed=1, need_bag=True):
        state = _observed(env)
        shim, _hero = battle_shim(state, data, env.registry)
        plan = plan_on(shim, space, pool_for(state, data), seed=0)
        assert not plan.problems, plan.problems
        plans += 1
        finished += any(step.detail.endswith("(default rule)") for step in plan.steps)
    assert plans >= 3, f"only {plans} bag-holding states"
    assert finished, "no plan finished a bag with the default rule -- untested"


def _obvious_state(data, *, with_opponents: bool) -> ObservedState:
    """Two 1-cost 1-stars fielded, two 5-cost 3-stars benched."""
    own = sorted((h.q, h.r) for h in Board().half_board_hexes(0))
    cheap = sorted(c.id for c in data.champions.values() if c.cost == 1)
    strong = sorted(c.id for c in data.champions.values() if c.cost == 5)
    hero = ObservedSeat(
        player_id=0, gold=50, level=8, hp=80,
        board=[ObservedUnit(cheap[0], 1, position=own[0]),
               ObservedUnit(cheap[1], 1, position=own[1])],
        bench=[ObservedUnit(strong[0], 3), ObservedUnit(strong[1], 3)],
        bench_slots=9)
    opponent = ObservedSeat(player_id=1, level=8, hp=80,
                            board=[ObservedUnit(cheap[2], 1, position=own[0])])
    opponents = [dataclasses.replace(opponent, player_id=i) for i in (1, 2, 3)]
    return ObservedState(stage=4, round=2, hero=hero,
                         opponents=opponents if with_opponents else [])


def _fielded(plan) -> list[str]:
    return [step.detail for step in plan.steps if step.phase == "swap"]


def test_plan_fields_an_obviously_better_unit(data):
    state = _obvious_state(data, with_opponents=True)
    strong = {u.champion_id for u in state.hero.bench}
    plan = plan_advice(state, data, _registry(data))
    assert not plan.mirror
    assert any(any(s in detail for s in strong) for detail in _fielded(plan)), plan


def test_plan_with_no_opponents_fights_a_mirror_and_says_so(data):
    state = _obvious_state(data, with_opponents=False)
    strong = {u.champion_id for u in state.hero.bench}
    plan = plan_advice(state, data, _registry(data))
    assert plan.mirror
    assert any(any(s in detail for s in strong) for detail in _fielded(plan)), plan


def test_the_cli_prints_a_plan_for_a_captured_state():
    shown = subprocess.run(
        [sys.executable, "scripts/advise.py", "--capture", "--plan"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert shown.returncode == 0, shown.stderr[-2000:]
    assert "four searches" in shown.stdout
    assert "not advised" in shown.stdout


def _budgets_passed(monkeypatch, state, data, budgets=None):
    seen = {}

    def capture(shim, space, pool, *, seed=0, budgets=None):
        seen["budgets"] = budgets
        return decide_mod.Plan((), (), ())

    monkeypatch.setattr(decide_mod, "plan_on", capture)
    plan_advice(state, data, _registry(data), budgets=budgets)
    return seen["budgets"]


def test_the_mirror_plans_at_per_opponent_margins(data, monkeypatch):
    """Swap and move sum over the panel; a one-member mirror must not double
    their per-fight threshold (doc 99 entries 160.160, 160.161)."""
    env = next(iter(_planning_states(data, seeds=(0,), per_seed=1)))
    observed = _observed(env)
    alone = dataclasses.replace(observed, opponents=[])

    mirrored = _budgets_passed(monkeypatch, alone, data)
    assert mirrored["swap"]["margin"] == pytest.approx(0.25)
    assert mirrored["move"]["margin"] == pytest.approx(0.25)
    assert "margin" not in mirrored["buy"] and "margin" not in mirrored["items"]

    overridden = _budgets_passed(monkeypatch, alone, data,
                                 budgets={"swap": {"margin": 0.9}})
    assert overridden["swap"]["margin"] == 0.9
    assert overridden["move"]["margin"] == pytest.approx(0.25)

    assert observed.opponents and any(seat.board for seat in observed.opponents)
    assert _budgets_passed(monkeypatch, observed, data) is None
