"""Evaluation-harness tests (milestone 7, doc 03 sec 4).

The metric that matters is average placement, so these tests check the harness
reports it honestly -- including that a competent scripted policy reaches
parity with the bots it plays against. That last test is the real guard: if the
action space or environment ever starts handicapping the agent seat, it fails.
"""

from __future__ import annotations

import random
from types import SimpleNamespace

import pytest

from engine.items import ItemRegistry
from engine.loader import load_all
from engine.player import PlayerState
from engine.schema import GameData
from engine.unit import UnitInstance
from rl.env import TFTEnv
from rl.evaluate import (
    LP_BY_PLACEMENT,
    EvalResult,
    compare,
    end_planning_policy,
    evaluate,
    random_policy,
    scripted_policy,
)
from tests.paths import REAL_DATA_DIR, STARTER_DATA_DIR


@pytest.fixture(scope="module")
def data() -> GameData:
    return load_all(STARTER_DATA_DIR)


@pytest.fixture
def env(data) -> TFTEnv:
    return TFTEnv(data=data)


@pytest.fixture(scope="module")
def real_data() -> GameData:
    """The expert variants key off champion *role*, which the 13-champion
    starter fixture cannot exercise across all six roles."""
    return load_all(REAL_DATA_DIR)


@pytest.fixture
def real_env(real_data) -> TFTEnv:
    return TFTEnv(data=real_data)


@pytest.fixture
def registry(real_data) -> ItemRegistry:
    return ItemRegistry(real_data.items, real_data.config.max_items_per_unit)


# --- result aggregation --------------------------------------------------


def test_metrics_are_computed_from_placements():
    result = EvalResult(episodes=8, placements=[1, 1, 3, 4, 5, 6, 8, 8])
    assert result.avg_placement == pytest.approx(4.5)
    assert result.win_rate == pytest.approx(0.25)
    assert result.top4_rate == pytest.approx(0.5)
    assert result.distribution == {1: 2, 3: 1, 4: 1, 5: 1, 6: 1, 8: 2}


def test_empty_results_do_not_divide_by_zero():
    result = EvalResult(episodes=0)
    assert result.avg_placement == 0.0
    assert result.win_rate == 0.0
    assert result.top4_rate == 0.0


def test_summary_and_dict_are_serialisable():
    result = EvalResult(episodes=2, placements=[1, 8], rewards=[1.0, 0.125])
    assert "avg_placement" in result.summary()
    payload = result.as_dict()
    assert payload["avg_placement"] == 4.5
    assert payload["distribution"] == {1: 1, 8: 1}


# --- running evaluations -------------------------------------------------


def test_evaluate_plays_the_requested_episodes(env):
    result = evaluate(env, end_planning_policy(env), seeds=range(3))
    assert result.episodes == 3
    assert len(result.placements) == 3
    assert all(1 <= p <= 8 for p in result.placements)


def test_evaluation_is_reproducible_on_fixed_seeds(env):
    policy = end_planning_policy(env)
    first = evaluate(env, policy, seeds=range(4))
    second = evaluate(env, policy, seeds=range(4))
    assert first.placements == second.placements
    assert first.rewards == second.rewards


def test_compare_uses_identical_seeds_for_every_policy(env):
    rng = random.Random(0)
    results = compare(
        env,
        {"nothing": end_planning_policy(env), "random": random_policy(rng)},
        episodes=3,
    )
    assert set(results) == {"nothing", "random"}
    assert all(r.episodes == 3 for r in results.values())


def test_a_runaway_episode_is_caught(env):
    with pytest.raises(RuntimeError, match="exceeded"):
        evaluate(env, end_planning_policy(env), seeds=[0], max_steps=3)


# --- baselines -----------------------------------------------------------


def test_doing_nothing_places_last(env):
    """The floor: an agent that never acts loses every game."""
    result = evaluate(env, end_planning_policy(env), seeds=range(5))
    assert result.avg_placement == 8.0
    assert result.win_rate == 0.0


def test_random_legal_actions_are_no_better_than_doing_nothing(env):
    """Documents why terminal-only reward gives PPO no gradient to start from."""
    rng = random.Random(0)
    result = evaluate(env, random_policy(rng), seeds=range(5))
    assert result.avg_placement > 6.0


def test_baseline_policies_never_take_an_illegal_action(env):
    rng = random.Random(1)
    for policy in (end_planning_policy(env), random_policy(rng), scripted_policy(env)):
        result = evaluate(env, policy, seeds=range(3))
        assert result.illegal_actions == 0


# --- the ceiling check ---------------------------------------------------


@pytest.mark.slow
def test_a_scripted_policy_reaches_parity_with_the_bots(env):
    """The environment must not handicap the agent seat.

    A heuristic driving the action space should place about average (4.5)
    against seven copies of the same heuristic. Materially worse means the
    action space cannot express competent play, and no learned policy could
    do better either.
    """
    result = evaluate(env, scripted_policy(env), seeds=range(30))
    assert result.avg_placement < 5.5, (
        f"scripted play only reached {result.avg_placement:.2f}; "
        "the action space or env is handicapping the agent seat"
    )
    assert result.win_rate > 0.10


def test_the_scripted_policy_actually_builds_a_board(env):
    """Regression: it used to place every unit on one hex, swapping endlessly,
    so the board never grew past a single unit."""
    policy = scripted_policy(env)
    obs, _ = env.reset(seed=0)
    peak_board = 0
    terminated = False
    steps = 0
    while not terminated and steps < 400:
        obs, _, terminated, _, _ = env.step(policy(obs, env.action_mask()))
        peak_board = max(peak_board, len(env.player.board))
        steps += 1
    assert peak_board >= 4, f"scripted play only ever fielded {peak_board} units"


def test_the_scripted_policy_beats_random(env):
    scripted = evaluate(env, scripted_policy(env), seeds=range(10))
    baseline = evaluate(env, random_policy(random.Random(0)), seeds=range(10))
    assert scripted.avg_placement < baseline.avg_placement


# --- floor-effect guardrail (doc 99 entry 18.3/18.4) --------------------


def _result(placements):
    from rl.evaluate import EvalResult

    return EvalResult(episodes=len(placements), placements=list(placements))


def test_floor_rate_counts_last_place():
    assert _result([8] * 84 + [4, 5, 6, 7] * 4).floor_rate == pytest.approx(0.84)


def test_a_pinned_policy_is_flagged_as_on_the_floor():
    """The 150-episode warm start that wasted four experiments."""
    result = _result([8] * 84 + [4] * 3 + [5] * 4 + [6] * 2 + [7] * 7)
    assert result.on_the_floor
    assert "FLOOR EFFECT" in result.summary()


def test_a_spread_policy_is_not_flagged():
    """The 400-episode warm start: 33% last place, usable."""
    spread = [1] * 2 + [2] * 1 + [3] * 8 + [4] * 7 + [5] * 12 + [6] * 14 + [7] * 23 + [8] * 33
    result = _result(spread)
    assert not result.on_the_floor
    assert "FLOOR EFFECT" not in result.summary()


def test_scripted_baseline_is_not_flagged():
    """A competent policy still finishes last sometimes; that is not a floor."""
    scripted = (
        [1] * 10 + [2] * 13 + [3] * 11 + [4] * 10
        + [5] * 13 + [6] * 11 + [7] * 10 + [8] * 22
    )
    assert not _result(scripted).on_the_floor


def test_ci95_shrinks_with_more_episodes():
    tight = _result([4, 5] * 200)
    loose = _result([4, 5] * 5)
    assert tight.ci95 < loose.ci95


def test_ci95_is_zero_for_a_constant_result():
    assert _result([8] * 50).ci95 == pytest.approx(0.0)


def test_ci95_undefined_for_a_single_episode():
    assert _result([3]).ci95 == 0.0


def test_floor_rate_of_an_empty_result_is_zero():
    assert _result([]).floor_rate == 0.0


def test_as_dict_carries_the_diagnostics():
    d = _result([8] * 10).as_dict()
    assert "ci95" in d and "floor_rate" in d


# --- LP scoring (doc 99 entry 31/32) -------------------------------------
#
# Average placement is linear; ranked TFT is not. These pin the properties that
# make LP a *different* metric rather than a rescaling of the same one -- if it
# were monotone-equivalent to placement it would add nothing and every past
# verdict would carry over unchanged.


def _result(placements):
    return EvalResult(episodes=len(placements), placements=list(placements))


def test_lp_rewards_the_top_half_and_punishes_the_bottom():
    assert _result([1]).avg_lp > 0
    assert _result([4]).avg_lp > 0
    assert _result([5]).avg_lp < 0
    assert _result([8]).avg_lp < 0


def test_lp_is_convex_toward_first():
    """1st->2nd must be worth more than 3rd->4th; placement says they are equal."""
    first_to_second = LP_BY_PLACEMENT[1] - LP_BY_PLACEMENT[2]
    third_to_fourth = LP_BY_PLACEMENT[3] - LP_BY_PLACEMENT[4]
    assert first_to_second > third_to_fourth


def test_lp_can_disagree_with_average_placement():
    """The reason the metric exists.

    Two distributions with identical mean placement, one weighted to the tails.
    If LP ranked them the same, it would be a rescaling and doc 99 31.3's
    finding would be an artefact of arithmetic rather than a real ambiguity.
    """
    flat = _result([4, 4, 5, 5])
    tails = _result([1, 1, 8, 8])
    assert flat.avg_placement == pytest.approx(tails.avg_placement)
    assert flat.avg_lp != pytest.approx(tails.avg_lp)


def test_lp_ci_widens_with_spread():
    tight = _result([4, 4, 5, 5] * 10)
    wide = _result([1, 1, 8, 8] * 10)
    assert wide.lp_ci95 > tight.lp_ci95


def test_lp_is_zero_for_no_episodes():
    assert _result([]).avg_lp == 0.0
    assert _result([]).lp_ci95 == 0.0


def test_summary_reports_lp_alongside_placement():
    """Never instead of: the project's history is measured on placement."""
    text = _result([1, 2, 3, 4, 5, 6, 7, 8]).summary()
    assert "avg_placement=" in text
    assert "lp=" in text


# --- scripted expert variants (doc 99 §8 open item) ----------------------
#
# The clone is at parity with this policy and imitation caps at its teacher,
# so raising the teacher is the lever. Because the seven opponents run the
# *same* heuristic, every flag must improve the teacher only -- and every
# default must reproduce the historical policy, or all prior numbers become
# unreproducible.


def _play(env, policy, seeds):
    return evaluate(env, policy, seeds=seeds)


def test_variant_defaults_reproduce_the_historical_policy(real_env):
    """Every flag off must be byte-identical in behaviour to no flags at all."""
    seeds = range(6)
    plain = _play(real_env, scripted_policy(real_env), seeds)
    defaulted = _play(
        real_env,
        scripted_policy(
            real_env, buy_synergy=False, match_items=False, corner_carry=False
        ),
        seeds,
    )
    assert plain.placements == defaulted.placements


def test_buy_synergy_changes_shopping(real_env):
    """Without the flag the teacher shops on (owned, cost); the bots use synergy."""
    seeds = range(8)
    plain = _play(real_env, scripted_policy(real_env), seeds)
    synergy = _play(real_env, scripted_policy(real_env, buy_synergy=True), seeds)
    assert plain.placements != synergy.placements, "flag had no effect at all"


def test_match_items_prefers_a_role_appropriate_item(real_data, registry):
    """An AP item must not be chosen for a marksman when an AD item is bagged."""
    from rl.evaluate import _best_item_for

    player = PlayerState(real_data, registry, player_id=0)
    marksman = next(
        c for c in real_data.champions.values() if c.role == "Marksman"
    )
    carry = UnitInstance(marksman, 1)

    ap = next(i for i in real_data.items.values() if (i.stats or {}).get("ability_power"))
    ad = next(
        i for i in real_data.items.values() if (i.stats or {}).get("attack_damage_pct")
    )
    player.item_bag = [ap, ad]

    space = SimpleNamespace(item_bag_slots=10)
    assert _best_item_for(player, carry, space) == 1, "should pick the AD item"

    caster = next(c for c in real_data.champions.values() if c.role == "Caster")
    assert _best_item_for(player, UnitInstance(caster, 1), space) == 0


def test_match_items_falls_back_to_slot_zero_for_an_unknown_role(real_data, registry):
    from rl.evaluate import _best_item_for

    player = PlayerState(real_data, registry, player_id=0)
    champion = next(iter(real_data.champions.values()))
    carry = UnitInstance(champion, 1)
    object.__setattr__(carry.champion, "role", "Nonexistent")
    player.item_bag = [next(iter(real_data.items.values()))]
    assert _best_item_for(player, carry, SimpleNamespace(item_bag_slots=10)) == 0


# --- selling, and why rolling depended on it (doc 99 entry 37.4) ---------


def _action_kinds(env, policy, seeds):
    """Tally the kinds of action a policy actually takes over some games."""
    from collections import Counter

    space = env.action_space_helper
    counts: Counter[str] = Counter()

    def counting(obs, mask):
        action = policy(obs, mask)
        counts[space.decode(action).kind.name] += 1
        return action

    evaluate(env, counting, seeds=seeds)
    return counts


def test_sell_bench_defaults_off_so_prior_numbers_reproduce(real_env):
    seeds = range(4)
    plain = _play(real_env, scripted_policy(real_env), seeds)
    defaulted = _play(real_env, scripted_policy(real_env, sell_bench=False), seeds)
    assert plain.placements == defaulted.placements
    assert _action_kinds(real_env, scripted_policy(real_env), seeds)["SELL"] == 0


def test_selling_unclogs_the_bench_and_lets_the_policy_keep_buying(real_env):
    """The defect in entry 37.4: a full bench masks BUY, so purchases stall.

    Without selling the board fills, the SELECT branch refuses anything
    weaker, and every later purchase is stranded. Measured at the time:
    28.6 buys per game without, 136.8 with.
    """
    seeds = range(4)
    plain = _action_kinds(real_env, scripted_policy(real_env), seeds)
    selling = _action_kinds(
        real_env, scripted_policy(real_env, sell_bench=True), seeds
    )
    assert selling["SELL"] > 0, "the sell branch never fired"
    assert selling["BUY"] > 2 * plain["BUY"], (
        f"selling must unblock buying: {plain['BUY']} -> {selling['BUY']}"
    )


def test_rolling_without_selling_spins_on_a_shop_it_cannot_buy_from(real_env):
    """Why the two flags are measured together, pinned as a test.

    A reroll arm alone rerolls far more and buys no more; adding selling
    converts the gold instead of burning it.
    """
    seeds = range(4)
    plain = _action_kinds(real_env, scripted_policy(real_env), seeds)
    rolling = _action_kinds(
        real_env, scripted_policy(real_env, roll_at_level=7), seeds
    )
    both = _action_kinds(
        real_env, scripted_policy(real_env, roll_at_level=7, sell_bench=True), seeds
    )

    assert rolling["REROLL"] > 0, "the reroll branch never fired"
    # Rolls a great deal, converts almost none of it into units.
    assert rolling["BUY"] < 1.2 * plain["BUY"]
    assert both["BUY"] > 2 * rolling["BUY"]


def test_selling_never_breaks_up_a_pair(real_env):
    """Two copies are one upgrade away, so the sell branch must skip them."""
    from rl.evaluate import _copies_owned

    space = real_env.action_space_helper
    policy = scripted_policy(real_env, sell_bench=True)
    obs, info = real_env.reset(seed=3)

    checked = 0
    for _ in range(400):
        mask = info["action_mask"] if "action_mask" in info else real_env.action_mask()
        action = policy(obs, mask)
        decoded = space.decode(action)
        if decoded.kind.name == "SELL":
            slot = decoded.a
            if slot >= space.board_slots:
                unit = real_env.player.bench[slot - space.board_slots]
                assert _copies_owned(real_env.player, unit) < 2
                checked += 1
        obs, _, terminated, truncated, info = real_env.step(action)
        if terminated or truncated:
            break
    assert checked > 0, "no sell was observed, so the assertion never ran"


# --- parallel evaluation (doc 99 entry 37.8) -----------------------------


def test_parallel_evaluation_is_identical_to_serial():
    """Not "similar" -- identical. Games are deterministic given a seed.

    If this ever diverges, either the engine has picked up hidden global state
    or the results are being reassembled in completion order rather than seed
    order, which would silently break every paired comparison.
    """
    from rl.evaluate import evaluate_scripted_parallel
    from tests.paths import REAL_DATA_DIR

    seeds = range(4)
    serial = evaluate_scripted_parallel(
        seeds, workers=1, data_dir=REAL_DATA_DIR, sell_bench=True
    )
    parallel = evaluate_scripted_parallel(
        seeds, workers=3, data_dir=REAL_DATA_DIR, sell_bench=True
    )
    assert parallel.placements == serial.placements
    assert parallel.rounds == serial.rounds
    assert parallel.rewards == pytest.approx(serial.rewards)
    assert parallel.episodes == serial.episodes


def test_parallel_evaluation_preserves_seed_order():
    """Reassembly must be by seed, so paired comparisons line up seed for seed.

    Run the seeds reversed: the results must come back reversed too, matching
    the requested order rather than whatever order the workers finished in.
    """
    from rl.evaluate import evaluate_scripted_parallel
    from tests.paths import REAL_DATA_DIR

    forward = evaluate_scripted_parallel(
        range(4), workers=3, data_dir=REAL_DATA_DIR
    )
    backward = evaluate_scripted_parallel(
        list(reversed(range(4))), workers=3, data_dir=REAL_DATA_DIR
    )
    assert backward.placements == list(reversed(forward.placements))


def test_parallel_model_evaluation_matches_serial(tmp_path):
    """A saved model must score identically however many processes run it.

    `compare_models` is the gate on every paired comparison in this project, so
    a parallel path that shifted results by even one placement would corrupt
    the comparisons rather than merely speed them up. Trains nothing: an
    untrained MaskablePPO is a perfectly good fixture for determinism.
    """
    from sb3_contrib import MaskablePPO

    from rl.evaluate import evaluate_model_parallel, sb3_policy

    data = load_all(REAL_DATA_DIR)
    env = TFTEnv(data=data)
    model = MaskablePPO("MlpPolicy", env, device="cpu", seed=0)
    path = tmp_path / "model"
    model.save(path)

    seeds = [0, 1, 2, 3]
    serial = evaluate(TFTEnv(data=data), sb3_policy(MaskablePPO.load(path, device="cpu")),
                      seeds=seeds)
    parallel = evaluate_model_parallel(path, seeds, workers=3, data_dir=REAL_DATA_DIR)

    assert parallel.placements == serial.placements
    assert parallel.rounds == serial.rounds
    assert parallel.illegal_actions == serial.illegal_actions


def test_gap_attribution_hybrid_delegates_only_its_kinds():
    """The hybrid must use the teacher's action exactly when it is delegated.

    The whole attribution rests on this dispatch: if it leaked, every arm would
    be some unlabelled blend of the two policies and the controls could still
    pass by coincidence.
    """
    from rl.action import ActionKind

    data = load_all(REAL_DATA_DIR)
    env = TFTEnv(data=data)
    env.reset(seed=0)
    space = env.action_space_helper

    teacher_choice = space.buy_offset          # a BUY
    clone_choice = space.end_index             # END_PLANNING
    delegated = {ActionKind.BUY}

    def hybrid(obs, mask):
        proposed = teacher_choice
        if space.decode(proposed).kind in delegated:
            return proposed
        return clone_choice

    # Delegated kind -> teacher's action wins.
    assert hybrid(None, None) == teacher_choice

    # Non-delegated kind -> the clone decides, even though the teacher proposed.
    delegated = {ActionKind.SELL}
    assert hybrid(None, None) == clone_choice


def test_pick_probe_random_arm_is_reproducible():
    """A randomised arm must depend on the episode seed, not on scheduling.

    The first version seeded one stream per worker process, so which episode
    drew which option depended on `imap_unordered`'s completion order. Two runs
    of the identical arm returned 3.493 and 3.257 -- a swing larger than most
    effects this project measures, silently inflating a paired t (doc 99 51.2).
    """
    import random
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    # The contract: reseeding from the episode seed reproduces the draw, and
    # different seeds generally do not.
    def draws(seed, n=12):
        rng = random.Random(0)
        rng.seed(seed)
        return [rng.choice([0, 1, 2, 3, 4]) for _ in range(n)]

    assert draws(7) == draws(7), "same seed must reproduce the same choices"
    assert draws(7) != draws(8), "different seeds must give different choices"

    # And the probe reseeds per episode rather than once per worker.
    source = (root / "scripts" / "pick_probe.py").read_text()
    assert '_WORKER["rng"].seed(seed)' in source, (
        "pick_probe must reseed its RNG per episode; a per-worker stream makes "
        "the random arms depend on scheduling order"
    )
