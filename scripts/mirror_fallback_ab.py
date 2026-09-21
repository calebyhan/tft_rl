"""What is the advisor's mirror fallback worth to the four-search teacher?

Doc 99 entry 160.160. When a person enters no opponent boards, ``plan_advice``
lets the four searches fight a reflection of the hero's own board: the hero's
seat as observed, bench and item bag stripped, as the only opponent. 137.1
measured a mirror at 70% of true-field value for ``best_board`` alone; for
these searches it is unmeasured. Four paired arms, all on the FAST8 scheduler:

* ``greedy`` -- no search: the floor that defines "value".
* ``field`` -- the 160.152 teacher, its panel drawn from the real lobby.
* ``mirror`` -- the same teacher whose every panel is the reflection, built
  through the advisor's own adapter path, at the shipped budgets.
* ``mirror_scaled`` -- as ``mirror``, with the swap and move margins halved.
  Those two compare a panel-summed score against an absolute margin, so the
  shipped budgets, set for a panel of two, demand twice the per-fight edge of
  a one-member mirror. Buy scales its margin by panel size and item averages
  per fight, so both are already consistent.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import logging
import math
import random
import statistics
import sys
import time
from collections import Counter
from multiprocessing import get_context
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import rl.search as search_mod  # noqa: E402
from bridge.adapter import seat_from_player, seat_to_player  # noqa: E402
from engine.hexgrid import Board  # noqa: E402
from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import (  # noqa: E402
    LP_BY_PLACEMENT,
    SEARCH_SEED_OFFSET,
    greedy_action_policy,
)
from rl.opponents import FAST8  # noqa: E402
from rl.search import search_item_greedy_policy  # noqa: E402

ARMS = ("greedy", "field", "mirror", "mirror_scaled")

# The 160.144 swap and 160.152 move budgets, which `bridge.decide.PLAN_BUDGETS`
# also ships.
SWAP_KWARGS = {"max_candidates": 4, "panel_size": 2, "trials": 2, "margin": 0.5}
MOVE_KWARGS = {"max_candidates": 6, "panel_size": 2, "trials": 2, "margin": 0.5}
# 0.25 per opponent, the rule every margin in this teacher follows (160.152),
# applied to a panel of one.
SCALED_MARGIN = 0.25

BOOTSTRAP_RESAMPLES = 2_000

_DATA = None


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    for name in (
        "bridge/adapter.py",
        "bridge/state.py",
        "engine/player.py",
        "engine/unit.py",
        "rl/action.py",
        "rl/env.py",
        "rl/evaluate.py",
        "rl/greedy_action.py",
        "rl/opponents.py",
        "rl/search.py",
        "scripts/mirror_fallback_ab.py",
    ):
        digest.update((REPO_ROOT / name).read_bytes())
    return digest.hexdigest()[:12]


def _init_worker() -> None:
    global _DATA
    logging.disable(logging.WARNING)
    _DATA = load_all()


def reflect(player, data, registry):
    """The opponent `plan_advice` builds when no opponent boards were entered."""
    seat = dataclasses.replace(
        seat_from_player(player), player_id=1, bench=[], bench_slots=0, item_bag=())
    return seat_to_player(seat, data, registry, Board())


def mirror_panel_fn(env, data, original):
    """An `opponent_panel` that answers the hero's searches with its reflection.

    The reflection is taken at the first panel request of each round -- the
    moment a person would ask for advice -- and held for the rest of the round,
    as the advisor's is. Any other seat's request goes to the real panel.
    """
    held = {"round": None, "reflection": None}

    def panel(match, player, size):
        if player is not env.player:
            return original(match, player, size)
        round_key = (match.round_id.stage, match.round_id.round)
        if held["round"] != round_key:
            held["round"] = round_key
            held["reflection"] = reflect(player, data, env.registry)
        reflection = held["reflection"]
        return [reflection] if reflection.board else []

    return panel


def teacher(env, seed: int, arm: str):
    swap_kwargs, move_kwargs = dict(SWAP_KWARGS), dict(MOVE_KWARGS)
    if arm == "mirror_scaled":
        swap_kwargs["margin"] = move_kwargs["margin"] = SCALED_MARGIN
    return search_item_greedy_policy(
        env,
        econ=FAST8,
        rng_seed=seed + SEARCH_SEED_OFFSET,
        depth=1,
        panel_size=2,
        trials=2,
        margin=0.25,
        buy_search=True,
        swap_search=True,
        swap_kwargs=swap_kwargs,
        swap_before_items=True,
        move_search=True,
        move_kwargs=move_kwargs,
    )


def play_one(job: tuple[str, int]) -> dict:
    arm, seed = job
    if _DATA is None:
        raise RuntimeError("evaluation worker was not initialized")
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}")
    original_fight = search_mod.fight_value
    original_panel = search_mod.opponent_panel
    fight_calls = 0

    def counted_fight(*args, **kwargs):
        nonlocal fight_calls
        fight_calls += 1
        return original_fight(*args, **kwargs)

    started = time.process_time()
    env = TFTEnv(_DATA, scouting="tokens", max_actions_per_round=600)
    search_mod.fight_value = counted_fight
    if arm.startswith("mirror"):
        search_mod.opponent_panel = mirror_panel_fn(env, _DATA, original_panel)
    try:
        if arm == "greedy":
            policy = greedy_action_policy(env, econ=FAST8)
        else:
            policy = teacher(env, seed, arm)
        observation, _ = env.reset(seed=seed)
        info = {}
        for _step in range(200_000):
            action = int(policy(observation, env.action_masks()))
            observation, _reward, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                break
        else:
            raise RuntimeError(f"{arm} did not terminate on seed {seed}")
    finally:
        search_mod.fight_value = original_fight
        search_mod.opponent_panel = original_panel

    return {
        "arm": arm,
        "seed": seed,
        "placement": info.get("placement") or env.n_players,
        "cpu_seconds": time.process_time() - started,
        "fight_calls": fight_calls,
        "accepted_swaps": getattr(policy, "swap_search_stats", {}).get("accepted_swaps", 0),
        "item_changes": getattr(policy, "item_search_stats", {}).get("changed_layouts", 0),
        "accepted_moves": getattr(policy, "move_search_stats", {}).get("accepted_moves", 0),
    }


def paired(first: list[float], second: list[float]) -> dict[str, float]:
    """second − first, per seed. No τ widening (doc 99 entry 160.159)."""
    differences = [b - a for a, b in zip(first, second, strict=True)]
    mean = statistics.fmean(differences)
    enough = len(differences) > 1
    se = statistics.stdev(differences) / math.sqrt(len(differences)) if enough else math.nan
    half = len(differences) // 2
    return {
        "delta": mean,
        "se": se,
        "t": mean / se if enough and se else 0.0,
        "ci_low": mean - 1.96 * se,
        "ci_high": mean + 1.96 * se,
        "first_half": statistics.fmean(differences[:half]) if enough else math.nan,
        "second_half": statistics.fmean(differences[half:]) if enough else math.nan,
    }


def retention(floor: list[float], full: list[float], test: list[float],
              resamples: int = BOOTSTRAP_RESAMPLES, seed: int = 0) -> dict[str, float]:
    """Share of the full teacher's gain over the floor that ``test`` keeps.

    (floor − test) / (floor − full) on mean placement, lower being better, with
    a paired percentile bootstrap over seeds.
    """
    n = len(floor)
    if not n == len(full) == len(test):
        raise ValueError("arms must be paired on the same seeds")

    def ratio(indices) -> float:
        gain = sum(floor[i] - full[i] for i in indices)
        kept = sum(floor[i] - test[i] for i in indices)
        return kept / gain if gain else math.nan

    point = ratio(range(n))
    rng = random.Random(seed)
    draws = sorted(
        value for value in (
            ratio([rng.randrange(n) for _ in range(n)]) for _ in range(resamples)
        ) if not math.isnan(value)
    )
    if not draws:
        return {"retention": point, "ci_low": math.nan, "ci_high": math.nan}
    return {
        "retention": point,
        "ci_low": draws[int(0.025 * (len(draws) - 1))],
        "ci_high": draws[int(math.ceil(0.975 * (len(draws) - 1)))],
    }


def summarise(records: list[dict]) -> tuple[dict, dict]:
    grouped = {arm: [] for arm in ARMS}
    for record in records:
        grouped[record["arm"]].append(record)
    for rows in grouped.values():
        rows.sort(key=lambda row: row["seed"])

    summary = {}
    for arm, rows in grouped.items():
        placements = [row["placement"] for row in rows]
        histogram = Counter(placements)
        summary[arm] = {
            "n": len(rows),
            "placement": statistics.fmean(placements),
            "lp": statistics.fmean(LP_BY_PLACEMENT[p] for p in placements),
            "first": histogram[1] / len(rows),
            "top4": sum(p <= 4 for p in placements) / len(rows),
            "eighth": histogram[8] / len(rows),
            "histogram": [histogram[p] for p in range(1, 9)],
            "placements": placements,
        }
        for field in ("cpu_seconds", "fight_calls", "accepted_swaps",
                      "item_changes", "accepted_moves"):
            summary[arm][field] = statistics.fmean(row[field] for row in rows)

    arm = {name: summary[name]["placements"] for name in ARMS}
    comparisons = {
        "field minus greedy": paired(arm["greedy"], arm["field"]),
        "mirror minus field": paired(arm["field"], arm["mirror"]),
        "mirror_scaled minus mirror": paired(arm["mirror"], arm["mirror_scaled"]),
        "mirror_scaled minus field": paired(arm["field"], arm["mirror_scaled"]),
        "retention, mirror": retention(arm["greedy"], arm["field"], arm["mirror"]),
        "retention, mirror_scaled": retention(
            arm["greedy"], arm["field"], arm["mirror_scaled"]),
    }
    return summary, comparisons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=600)
    parser.add_argument("--seed0", type=int, default=87_000)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--arms", nargs="+", default=list(ARMS), choices=ARMS)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    before = source_fingerprint()
    started = time.perf_counter()
    jobs = [
        (arm, args.seed0 + game)
        for game in range(args.games)
        for arm in args.arms
    ]
    context = get_context("spawn")
    with context.Pool(args.workers, initializer=_init_worker) as pool:
        records = pool.map(play_one, jobs, chunksize=1)
    if args.json:
        # Hours of games must survive a failure in the arithmetic below.
        args.json.write_text(json.dumps({"records": records}, indent=2))
    after = source_fingerprint()
    if after != before:
        raise RuntimeError(f"source changed during run: {before} -> {after}")
    payload = {
        "source_fingerprint": before,
        "swap_kwargs": SWAP_KWARGS,
        "move_kwargs": MOVE_KWARGS,
        "scaled_margin": SCALED_MARGIN,
        "games": args.games,
        "seed0": args.seed0,
        "workers": args.workers,
        "wall_seconds": time.perf_counter() - started,
        "records": records,
    }
    if set(args.arms) == set(ARMS) and args.games > 1:
        payload["summary"], payload["comparisons"] = summarise(records)
    text = json.dumps(payload, indent=2)
    if args.json:
        args.json.write_text(text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
