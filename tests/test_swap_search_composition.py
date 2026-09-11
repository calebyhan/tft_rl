"""The injected board search: emission, ordering and control equivalence.

Doc 99 entry 160.139 composes ``best_swap`` with the established exact
buy-plus-item teacher. Two things have to hold before any placement number is
readable: the swap must reach the world as real ``SELECT``/``PLACE`` actions,
and the arm that does not ask for it must be byte-identical to the policy the
earlier blocks measured.
"""

from __future__ import annotations

import pytest

from engine.loader import load_all
from engine.unit import UnitInstance
from rl.action import ActionKind
from rl.env import TFTEnv
from rl.evaluate import greedy_action_policy
from rl.opponents import FAST8
from rl.search import search_item_greedy_policy
from tests.paths import REAL_DATA_DIR, STARTER_DATA_DIR


def _swap_env(board_planner, *, board_planner_first: bool = True):
    """A board the greedy scheduler will not touch, and a bench unit it rejects.

    ``_next_field_action`` only swaps when the best benched unit out-scores the
    weakest fielded one, so a weak bench unit leaves the field stage inert and
    any swap in the emitted stream must have come from the injected planner.
    """
    data = load_all(STARTER_DATA_DIR)
    env = TFTEnv(data, max_actions_per_round=50)
    policy = greedy_action_policy(
        env,
        board_planner=board_planner,
        board_planner_first=board_planner_first,
    )
    observation, _ = env.reset(seed=4)
    player = env.player
    player.shop.slots = [None] * player.config.shop_slots
    player.gold = 0
    player.level = 1
    player.board.clear()
    player.bench = [None] * player.config.bench_size

    carry_hex = player.hex_board.to_combat(0, 0, 0)
    carry = UnitInstance(data.champions["TFT17_Jinx"], registry=player.registry)
    weak = UnitInstance(data.champions["TFT17_Poppy"], registry=player.registry)
    player.board[carry_hex] = carry
    player.bench[2] = weak
    player.item_bag[:] = [
        data.items["TFT_Item_Deathblade"],
        data.items["TFT_Item_SparringGloves"],
    ]
    return env, policy, observation, carry, weak, carry_hex


def _drive(env, policy, observation, limit: int = 20):
    """Play one planning phase, returning the decoded actions it emitted."""
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


def test_board_plan_reaches_the_world_as_a_select_then_place():
    holder = {}

    def planner():
        env, weak, carry_hex = holder["state"]
        assert weak in env.player.bench_units, "planner runs before the swap"
        return [(weak, carry_hex)]

    env, policy, observation, carry, weak, carry_hex = _swap_env(planner)
    holder["state"] = (env, weak, carry_hex)

    emitted = _drive(env, policy, observation)
    kinds = [action.kind for action in emitted]

    assert ActionKind.SELECT in kinds and ActionKind.PLACE in kinds
    assert kinds.index(ActionKind.PLACE) == kinds.index(ActionKind.SELECT) + 1
    # The swap actually happened: PLACE onto an occupied own hex exchanges the
    # two units rather than being refused.
    assert env.player.board[carry_hex] is weak
    assert carry in env.player.bench_units


def test_board_plan_runs_before_the_item_phase_by_default():
    weak_ref: list = []
    hex_ref: list = []
    env, policy, observation, _carry, weak, carry_hex = _swap_env(
        lambda: [(weak_ref[0], hex_ref[0])]
    )
    weak_ref.append(weak)
    hex_ref.append(carry_hex)

    emitted = _drive(env, policy, observation)
    kinds = [action.kind for action in emitted]

    assert ActionKind.EQUIP in kinds, "the fixture must reach an item decision"
    assert kinds.index(ActionKind.SELECT) < kinds.index(ActionKind.EQUIP)


def test_board_plan_runs_after_the_item_phase_when_ordered_last():
    weak_ref: list = []
    hex_ref: list = []
    env, policy, observation, _carry, weak, carry_hex = _swap_env(
        lambda: [(weak_ref[0], hex_ref[0])], board_planner_first=False
    )
    weak_ref.append(weak)
    hex_ref.append(carry_hex)

    emitted = _drive(env, policy, observation)
    kinds = [action.kind for action in emitted]

    assert ActionKind.EQUIP in kinds
    assert kinds.index(ActionKind.EQUIP) < kinds.index(ActionKind.SELECT)


def test_board_plan_resolves_the_bench_index_at_emission_time():
    """A stale index is the failure mode the unit-keyed contract exists for."""
    weak_ref: list = []
    hex_ref: list = []
    env, policy, observation, _carry, weak, carry_hex = _swap_env(
        lambda: [(weak_ref[0], hex_ref[0])]
    )
    weak_ref.append(weak)
    hex_ref.append(carry_hex)
    player = env.player
    # Renumber the bench under the plan: the unit the planner named moves from
    # slot 2 to slot 0, so an index captured at plan time would select nothing.
    player.bench[2] = None
    player.bench[0] = weak

    emitted = _drive(env, policy, observation)
    select = next(a for a in emitted if a.kind is ActionKind.SELECT)

    assert select.a == env.action_space_helper.slot_for_bench(0)
    assert env.player.board[carry_hex] is weak


def test_board_plan_is_skipped_when_its_unit_has_left_the_bench():
    other = UnitInstance(
        load_all(STARTER_DATA_DIR).champions["TFT17_Poppy"], registry=None
    )
    hex_ref: list = []
    env, policy, observation, carry, _weak, carry_hex = _swap_env(
        lambda: [(other, hex_ref[0])]
    )
    hex_ref.append(carry_hex)

    emitted = _drive(env, policy, observation)

    assert not any(action.kind is ActionKind.SELECT for action in emitted)
    assert env.player.board[carry_hex] is carry


def test_absent_board_planner_leaves_the_action_stream_untouched():
    """The control arm must be the policy the earlier seed blocks measured.

    Pinned against a literal, not against a second run of the same new code
    path: comparing two ``board_planner=None`` policies passes even when the
    added stage emits something of its own, which is the mutation this guards.
    """
    control_env, control_policy, control_obs, *_ = _swap_env(None)
    control = [a.kind for a in _drive(control_env, control_policy, control_obs)]

    assert control == [ActionKind.EQUIP, ActionKind.EQUIP, ActionKind.END_PLANNING]

    data = load_all(STARTER_DATA_DIR)
    env = TFTEnv(data, max_actions_per_round=50)
    plain = greedy_action_policy(env)
    observation, _ = env.reset(seed=4)
    player = env.player
    player.shop.slots = [None] * player.config.shop_slots
    player.gold = 0
    player.level = 1
    player.board.clear()
    player.bench = [None] * player.config.bench_size
    carry_hex = player.hex_board.to_combat(0, 0, 0)
    player.board[carry_hex] = UnitInstance(
        data.champions["TFT17_Jinx"], registry=player.registry
    )
    player.bench[2] = UnitInstance(
        data.champions["TFT17_Poppy"], registry=player.registry
    )
    player.item_bag[:] = [
        data.items["TFT_Item_Deathblade"],
        data.items["TFT_Item_SparringGloves"],
    ]

    assert control == [a.kind for a in _drive(env, plain, observation)]


@pytest.mark.slow
def test_composed_teacher_runs_the_swap_search_through_the_action_space():
    data = load_all(REAL_DATA_DIR)
    env = TFTEnv(data, scouting="tokens", max_actions_per_round=600)
    policy = search_item_greedy_policy(
        env,
        econ=FAST8,
        rng_seed=1,
        margin=0.25,
        buy_search=True,
        swap_search=True,
        swap_kwargs={"panel_size": 2, "trials": 2},
    )
    observation, _ = env.reset(seed=91_000)
    for _ in range(4_000):
        observation, _reward, terminated, truncated, _info = env.step(
            int(policy(observation, env.action_masks()))
        )
        if terminated or truncated:
            break

    assert policy.swap_search_stats["search_decisions"] > 0
    assert policy.item_search_stats["search_decisions"] > 0


def test_swap_budget_reaches_best_swap_rather_than_falling_back_to_defaults():
    """A silently dropped ``swap_kwargs`` would run a different search.

    ``best_swap`` ships ``trials=3``; the composed teacher of doc 99 entry
    160.139 spends ``trials=2`` so all three components share one estimator
    budget. Nothing else in the run would fail if the budget were lost, so it
    is pinned here.
    """
    import rl.search as search_mod

    data = load_all(STARTER_DATA_DIR)
    env = TFTEnv(data, max_actions_per_round=50)
    seen: list[dict] = []
    original = search_mod.best_swap

    def recording(env_, rng, **kwargs):
        seen.append(kwargs)
        return original(env_, rng, **kwargs)

    search_mod.best_swap = recording
    try:
        policy = search_item_greedy_policy(
            env,
            rng_seed=0,
            swap_search=True,
            swap_kwargs={"max_candidates": 4, "panel_size": 2, "trials": 2,
                         "margin": 0.5},
        )
        observation, _ = env.reset(seed=4)
        for _ in range(60):
            observation, _reward, terminated, truncated, _info = env.step(
                int(policy(observation, env.action_masks()))
            )
            if terminated or truncated:
                break
    finally:
        search_mod.best_swap = original

    assert seen, "the board planner never called best_swap"
    assert all(
        call == {"max_candidates": 4, "panel_size": 2, "trials": 2, "margin": 0.5}
        for call in seen
    )


def test_blind_swap_shares_every_gate_and_target_rule_with_the_exact_search():
    """The control must differ only in choice and acceptance, not in scope."""
    import inspect

    from rl.search import best_swap, blind_swap

    exact = inspect.getsource(best_swap)
    blind = inspect.getsource(blind_swap)
    for shared in (
        "if match is None or not player.board:",
        "benched.sort(key=lambda pair: (-pair[1].star_level, -pair[1].champion.cost))",
        "benched = benched[:max_candidates]",
        "free_hexes = [h for h in sorted(player._own_hexes) if h not in player.board]",
    ):
        assert shared in exact and shared in blind, shared


@pytest.mark.slow
def test_blind_swap_matches_volume_at_zero_simulation_cost():
    """Same board churn, no ``fight_value`` calls: the control's whole point.

    The swap's fights are isolated from the item search's by counting inside
    the chooser rather than over the whole episode -- the composed teacher
    simulates for its items too, so an episode-wide count says nothing about
    which component spent it.
    """
    import rl.search as search_mod

    data = load_all(REAL_DATA_DIR)
    results = {}
    for mode in ("exact", "blind"):
        env = TFTEnv(data, scouting="tokens", max_actions_per_round=600)
        kwargs = {"max_candidates": 4, "panel_size": 2}
        kwargs.update(
            {"trials": 2, "margin": 0.5} if mode == "exact"
            else {"accept_rate": 0.353}
        )
        chooser_name = "best_swap" if mode == "exact" else "blind_swap"
        original_chooser = getattr(search_mod, chooser_name)
        original_fight = search_mod.fight_value
        swap_fights = [0]
        inside = [False]

        def counted_fight(*args, _o=original_fight, _in=inside, _n=swap_fights, **kw):
            if _in[0]:
                _n[0] += 1
            return _o(*args, **kw)

        def traced(*args, _o=original_chooser, _in=inside, **kw):
            _in[0] = True
            try:
                return _o(*args, **kw)
            finally:
                _in[0] = False

        setattr(search_mod, chooser_name, traced)
        search_mod.fight_value = counted_fight
        try:
            policy = search_item_greedy_policy(
                env,
                econ=FAST8,
                rng_seed=7,
                margin=0.25,
                buy_search=False,
                swap_search=True,
                swap_mode=mode,
                swap_kwargs=kwargs,
            )
            observation, _ = env.reset(seed=92_000)
            for _ in range(20_000):
                observation, _r, term, trunc, _i = env.step(
                    int(policy(observation, env.action_masks()))
                )
                if term or trunc:
                    break
        finally:
            setattr(search_mod, chooser_name, original_chooser)
            search_mod.fight_value = original_fight
        results[mode] = (dict(policy.swap_search_stats), swap_fights[0])

    exact_stats, exact_fights = results["exact"]
    blind_stats, blind_fights = results["blind"]

    assert blind_fights == 0, "the control simulated a fight"
    assert exact_fights > 0, "the exact arm did not simulate"
    assert blind_stats["search_decisions"] > 0
    # Same opportunity set: both are asked on essentially every planning phase.
    assert abs(
        blind_stats["search_decisions"] - exact_stats["search_decisions"]
    ) <= 8
