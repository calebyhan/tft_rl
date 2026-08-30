"""Is there a deployable short-horizon reroll target? (doc 99 entry 160.67).

Calibration only. Nothing here fits a model or defines a training label: it
measures what one reroll actually buys, in exact-simulation combat margin and
in gold, over independently sampled legal shops drawn from one identical
observed planning state.

Design is frozen in doc 99 entry 160.67 -- state selection, horizon, what is
held fixed, the terminal measurement vector, and the named outcomes A/B/C/D.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.loader import load_all  # noqa: E402
from rl.action import ActionKind  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import greedy_action_policy  # noqa: E402
from rl.opponents import FAST8  # noqa: E402
from rl.planning_snapshot import PlanningSnapshot  # noqa: E402
from rl.search import (  # noqa: E402
    best_buy_from_scores,
    buy_candidate_values,
    opponent_panel,
)


def find_reroll_state(data, episode_seed: int, panel_size: int):
    """First greedy-policy REROLL where END_PLANNING is also legal (160.61).

    Returns ``(snapshot, match, panel)`` or ``None`` when the episode never
    reaches such a state. The live ``match`` is kept only as a read-only source
    of opponents and of the engine's board-cloning geometry; the branches never
    step it.
    """
    env = TFTEnv(data, scouting="tokens", max_actions_per_round=600)
    policy = greedy_action_policy(env, econ=FAST8)
    observation, _ = env.reset(seed=episode_seed)
    space = env.action_space_helper
    for _ in range(6000):
        mask = env.action_masks()
        action = int(policy(observation, mask))
        if space.decode(action).kind is ActionKind.REROLL and mask[space.end_index]:
            assert env.match is not None
            panel = opponent_panel(env.match, env.player, panel_size)
            if not panel or not env.player.board:
                return None
            snapshot = PlanningSnapshot.capture(
                env.player, env.match.pool, env.match.rng
            )
            return snapshot, env.match, panel
        observation, _reward, terminated, truncated, _info = env.step(action)
        if terminated or truncated:
            return None
    return None


def _qualifies(env, mask, panel_size: int) -> bool:
    """Both decisions legal and a fight is measurable at this state (160.69)."""
    space = env.action_space_helper
    if not (mask[space.reroll_index] and mask[space.end_index]):
        return False
    if not env.player.board or env.match is None:
        return False
    return bool(opponent_panel(env.match, env.player, panel_size))


def _walk(data, episode_seed: int, panel_size: int, stop_at: int | None):
    """Step one greedy episode, counting states where both decisions are legal.

    With ``stop_at`` set, halts at that qualifying state and returns the live
    environment and its policy; otherwise runs to the end and returns the count.
    Two passes rather than one because the opponent panel is made of live
    players that keep mutating, so a state cannot be held aside and used later
    -- and deterministic prefix replay is already established (160.61).

    The policy comes back with the environment so a caller can *continue* the
    episode from the sampled state rather than only inspect it (160.71).
    """
    env = TFTEnv(data, scouting="tokens", max_actions_per_round=600)
    policy = greedy_action_policy(env, econ=FAST8)
    observation, _ = env.reset(seed=episode_seed)
    qualifying = 0
    for _ in range(6000):
        mask = env.action_masks()
        if _qualifies(env, mask, panel_size):
            if stop_at is not None and qualifying == stop_at:
                return env, policy, qualifying
            qualifying += 1
        action = int(policy(observation, mask))
        observation, _reward, terminated, truncated, _info = env.step(action)
        if terminated or truncated:
            break
    return None, None, qualifying


def sample_reroll_state(data, episode_seed: int, panel_size: int, rng: random.Random):
    """A legality-sampled planning state, independent of the policy's choice.

    Selection deliberately ignores whether the greedy policy rerolls here and
    never conditions on ``end_legal_buys``, which is the quantity that decides
    the sign of the measured delta (doc 99 entry 160.69).
    """
    _env, _policy, qualifying = _walk(data, episode_seed, panel_size, None)
    if not qualifying:
        return None
    chosen = rng.randrange(qualifying)
    env, _policy, recount = _walk(data, episode_seed, panel_size, chosen)
    if env is None:
        raise RuntimeError(f"seed {episode_seed} replay did not reach state {chosen}")
    assert recount == chosen, "replay diverged from the counting pass"
    assert env.match is not None
    panel = opponent_panel(env.match, env.player, panel_size)
    snapshot = PlanningSnapshot.capture(env.player, env.match.pool, env.match.rng)
    return snapshot, env.match, panel, {"qualifying_states": qualifying, "chosen": chosen}


def _shop_facts(player) -> tuple[int, int]:
    """Descriptive, on-screen shop facts. Never a utility (160.66)."""
    legal_buys = sum(player.can_buy(slot) for slot in range(len(player.shop)))
    held = Counter(unit.champion.id for unit in player.all_units if unit.star_level == 1)
    pair_offers = sum(
        held[champion_id] >= 2 for champion_id in player.shop.slots if champion_id
    )
    return legal_buys, pair_offers


def run_branch(player, pool, match, panel, seeds, args) -> dict:
    """One buy decision by exact simulation; report the terminal vector.

    The terminal board is the candidate board the decision selects, which is
    exactly what ``buy_candidates`` says the purchase becomes. No fielding rule
    is invented, and no second buy is attempted (160.67).
    """
    legal_buys, pair_offers = _shop_facts(player)
    pool_before = sum(pool.snapshot().values())
    scored = buy_candidate_values(
        player, match, panel, seeds, args.trials, args.max_candidates
    )
    baseline, candidates = scored
    slot = best_buy_from_scores(scored, args.margin, len(panel))

    record = {
        "legal_buys": legal_buys,
        "pair_offers": pair_offers,
        "baseline_margin": baseline,
        "bought_slot": slot,
        "bought_champion": None,
        "bought_star": None,
    }
    if slot is None:
        record["margin"] = baseline
    else:
        chosen = next(c for c in candidates if c[0] == slot)
        record["margin"] = chosen[1]
        record["bought_champion"] = player.shop.slots[slot]
        record["bought_star"] = chosen[2][0][0].star_level
        player.buy(slot, pool)
    record["gold"] = player.gold
    record["board_units"] = len(player.board)
    # Diagnostic only: a real player cannot read the shared pool exactly.
    record["pool_consumed"] = pool_before - sum(pool.snapshot().values())
    return record


def summarise(values: list[float]) -> dict:
    ordered = sorted(values)
    n = len(ordered)

    def quantile(fraction: float) -> float:
        return ordered[min(n - 1, int(fraction * n))]

    sd = statistics.pstdev(ordered) if n > 1 else 0.0
    return {
        "n": n,
        "mean": statistics.fmean(ordered),
        "sd": sd,
        "se": sd / (n ** 0.5) if n else 0.0,
        "min": ordered[0],
        "p25": quantile(0.25),
        "median": quantile(0.5),
        "p75": quantile(0.75),
        "max": ordered[-1],
        "p_positive": sum(v > 0 for v in ordered) / n,
        "p_zero": sum(v == 0 for v in ordered) / n,
        "p_negative": sum(v < 0 for v in ordered) / n,
    }


def calibrate_state(data, registry, snapshot, match, panel, index, args) -> dict:
    """Paired END vs REROLL branches under common random combat numbers."""
    seed_rng = random.Random(args.combat_seed + index)
    seeds = [
        [seed_rng.randrange(2**31) for _ in range(args.trials)] for _ in panel
    ]

    player, pool, _rng = snapshot.restore(data, registry)
    end = run_branch(player, pool, match, panel, seeds, args)

    rerolls = []
    for replica in range(args.replicas):
        player, pool, _rng = snapshot.restore(data, registry)
        player.reroll(pool, random.Random(args.shop_seed + 1000 * index + replica))
        rerolls.append(run_branch(player, pool, match, panel, seeds, args))

    margin_deltas = [branch["margin"] - end["margin"] for branch in rerolls]
    gold_deltas = [branch["gold"] - end["gold"] for branch in rerolls]
    mean_gold_cost = -statistics.fmean(gold_deltas)
    margin_summary = summarise(margin_deltas)
    return {
        "state_index": index,
        "gold": snapshot.gold,
        "level": snapshot.level,
        "board_units": len(snapshot.board),
        "free_bench_slots": sum(unit is None for unit in snapshot.bench),
        "end": end,
        "distinct_reroll_shops": len({
            (branch["legal_buys"], branch["pair_offers"], branch["bought_champion"])
            for branch in rerolls
        }),
        "reroll_bought_fraction": sum(
            branch["bought_slot"] is not None for branch in rerolls
        ) / len(rerolls),
        "margin_delta": margin_summary,
        "gold_delta": summarise(gold_deltas),
        # Positive means the sampled reroll bought margin at this many units of
        # combat margin per gold spent. Reported, not optimised.
        "margin_per_gold": (
            margin_summary["mean"] / mean_gold_cost if mean_gold_cost else None
        ),
    }


def classify(states: list[dict]) -> dict:
    """Outcome A/B/C from 160.67, decided by predeclared comparisons.

    Outcome A is a **conjunction**: the estimate must be sharp *and* the states
    must disagree in sign at a fixed gold price. Sharpness alone says only that
    a one-sided quantity was measured precisely, which is not a decision rule --
    so both halves are tested here rather than the numeric half alone.
    """
    means = [state["margin_delta"]["mean"] for state in states]
    ses = [state["margin_delta"]["se"] for state in states]
    zero_fraction = statistics.fmean(
        [state["margin_delta"]["p_zero"] for state in states]
    )
    between = statistics.pstdev(means) if len(means) > 1 else 0.0
    within = statistics.fmean(ses) if ses else 0.0
    sharp = between > 0.0 and within / between <= 0.5
    both_signs = any(mean > 0 for mean in means) and any(mean < 0 for mean in means)
    if zero_fraction >= 0.95:
        outcome = "C: degenerate -- one planning phase almost never changes the board"
    elif sharp and both_signs:
        outcome = "A: sharp and two-sided -- a calibrated utility may be proposed"
    elif sharp:
        outcome = (
            "A-partial: sharp but one-sided -- no state prefers END, so the "
            "measurement cannot rank REROLL against END without pricing gold"
        )
    else:
        outcome = "B: noisy -- within-state SE not small against between-state spread"
    exchange = [
        state["margin_per_gold"] for state in states
        if state["margin_per_gold"] is not None
    ]
    strata = {}
    for label, predicate in (
        ("end_could_buy", lambda st: st["end"]["legal_buys"] > 0),
        ("end_had_no_legal_buy", lambda st: st["end"]["legal_buys"] == 0),
        ("open_bench", lambda st: st["free_bench_slots"] > 0),
        ("full_bench", lambda st: st["free_bench_slots"] == 0),
    ):
        group = [state["margin_delta"]["mean"] for state in states if predicate(state)]
        strata[label] = {
            "states": len(group),
            "negative": sum(mean < 0 for mean in group),
            "positive": sum(mean > 0 for mean in group),
            "both_signs": any(m > 0 for m in group) and any(m < 0 for m in group),
            "mean": statistics.fmean(group) if group else None,
        }
    return {
        "states": len(states),
        "between_state_sd_of_mean_delta": between,
        "mean_within_state_se": within,
        "se_over_spread": within / between if between else None,
        "sharp": sharp,
        "both_signs": both_signs,
        "states_with_negative_mean_delta": sum(mean < 0 for mean in means),
        "states_where_end_bought": sum(
            state["end"]["bought_slot"] is not None for state in states
        ),
        "mean_zero_fraction": zero_fraction,
        "min_mean_delta": min(means) if means else None,
        "max_mean_delta": max(means) if means else None,
        "margin_per_gold": summarise(exchange) if exchange else None,
        # 160.69 stratifies after the fact; selection never conditions on these.
        "strata": strata,
        "outcome": outcome,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode-seeds", type=int, default=40)
    parser.add_argument("--replicas", type=int, default=64)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--panel-size", type=int, default=2)
    parser.add_argument("--margin", type=float, default=0.25)
    parser.add_argument("--max-candidates", type=int, default=5)
    parser.add_argument("--shop-seed", type=int, default=1)
    parser.add_argument("--combat-seed", type=int, default=7)
    parser.add_argument(
        "--selection", choices=("greedy-reroll", "legal-uniform"),
        default="greedy-reroll",
        help="greedy-reroll reproduces 160.67/160.68; legal-uniform is 160.69",
    )
    parser.add_argument("--selection-seed", type=int, default=3)
    parser.add_argument("--json", type=Path)
    parser.add_argument(
        "--from-json", type=Path,
        help="re-summarise a saved run instead of sampling it again",
    )
    args = parser.parse_args()

    if args.from_json:
        # Classification is pure post-processing, so a criterion correction is
        # re-derived from the saved run rather than by resampling it.
        payload = json.loads(args.from_json.read_text())
        payload["summary"] = classify(payload["states"])
        print(json.dumps(payload["summary"], indent=2))
        if args.json:
            args.json.write_text(json.dumps(payload, indent=2))
        return 0

    data = load_all()
    registry = TFTEnv(data).registry
    states, skipped = [], 0
    for episode_seed in range(args.episode_seeds):
        selection = None
        if args.selection == "greedy-reroll":
            found = find_reroll_state(data, episode_seed, args.panel_size)
        else:
            sampled = sample_reroll_state(
                data, episode_seed, args.panel_size,
                random.Random(args.selection_seed + episode_seed),
            )
            found = sampled[:3] if sampled else None
            selection = sampled[3] if sampled else None
        if found is None:
            skipped += 1
            continue
        snapshot, match, panel = found
        state = calibrate_state(
            data, registry, snapshot, match, panel, len(states), args
        )
        state["episode_seed"] = episode_seed
        state["selection"] = selection
        states.append(state)
        print(
            f"seed {episode_seed}: mean d-margin "
            f"{state['margin_delta']['mean']:+.3f} "
            f"(se {state['margin_delta']['se']:.3f}, "
            f"zero {state['margin_delta']['p_zero']:.2f}), "
            f"mean d-gold {state['gold_delta']['mean']:+.2f}",
            flush=True,
        )

    payload = {
        "config": vars(args) | {"json": str(args.json) if args.json else None},
        "episodes_without_reroll_state": skipped,
        "states": states,
        "summary": classify(states) if states else None,
    }
    print(json.dumps(payload["summary"], indent=2))
    if args.json:
        args.json.write_text(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
