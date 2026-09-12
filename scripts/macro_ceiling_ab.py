"""Is there unconditional macro headroom once the micro play is strong?

Doc 99 entry 160.145. The established teacher (160.144: exact buy, exact item
at margin 0.25, exact one-swap fielding before items) has only ever played the
FAST8 economy. This run holds each micro policy fixed and varies only the
hand-written economy plan, under both the teacher and plain greedy micro, on
one paired seed block, so macro value is measured *conditional on micro*
without any cross-block comparison.

A flat result bounds only **fixed-plan** macro value. A state-conditioned macro
policy -- roll when weak, level when strong -- is not measured by any preset
and stays open whatever this returns.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import statistics
import sys
import time
from collections import Counter
from multiprocessing import get_context
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import rl.search as search_mod  # noqa: E402
from engine.loader import load_all  # noqa: E402
from rl.action import ActionKind  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import (  # noqa: E402
    LP_BY_PLACEMENT,
    SEARCH_SEED_OFFSET,
    greedy_action_policy,
)
from rl.opponents import STRATEGIES  # noqa: E402
from rl.search import search_item_greedy_policy  # noqa: E402

MICROS = ("greedy", "search")
MACROS = ("fast8", "standard", "slowroll6")
ARMS = tuple(f"{micro}:{macro}" for micro in MICROS for macro in MACROS)

# The 160.144 swap budget, unchanged.
SWAP_KWARGS = {"max_candidates": 4, "panel_size": 2, "trials": 2, "margin": 0.5}

# Two alternative presets are tested against FAST8 under the teacher, so the
# primary intervals are Bonferroni-widened to a family-wise 95%.
Z_95 = 1.96
Z_FAMILY = 2.2414

_DATA = None


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    for name in (
        "engine/player.py",
        "engine/unit.py",
        "rl/action.py",
        "rl/env.py",
        "rl/evaluate.py",
        "rl/greedy_action.py",
        "rl/opponents.py",
        "rl/search.py",
        "scripts/macro_ceiling_ab.py",
    ):
        digest.update((REPO_ROOT / name).read_bytes())
    return digest.hexdigest()[:12]


def _init_worker() -> None:
    global _DATA
    logging.disable(logging.WARNING)
    _DATA = load_all()


def _policy(env: TFTEnv, arm: str, seed: int):
    micro, macro = arm.split(":")
    econ = STRATEGIES[macro]
    if micro == "greedy":
        return greedy_action_policy(env, econ=econ)
    return search_item_greedy_policy(
        env,
        econ=econ,
        rng_seed=seed + SEARCH_SEED_OFFSET,
        depth=1,
        panel_size=2,
        trials=2,
        margin=0.25,
        buy_search=True,
        swap_search=True,
        swap_kwargs=dict(SWAP_KWARGS),
        swap_before_items=True,
    )


def play_one(job: tuple[str, int]) -> dict:
    arm, seed = job
    if _DATA is None:
        raise RuntimeError("evaluation worker was not initialized")
    env = TFTEnv(_DATA, scouting="tokens", max_actions_per_round=600)
    policy = _policy(env, arm, seed)
    space = env.action_space_helper
    original_fight = search_mod.fight_value
    fight_calls = 0

    def counted_fight(*args, **kwargs):
        nonlocal fight_calls
        fight_calls += 1
        return original_fight(*args, **kwargs)

    search_mod.fight_value = counted_fight
    started = time.perf_counter()
    kinds: Counter = Counter()
    try:
        observation, _ = env.reset(seed=seed)
        info = {}
        for _step in range(200_000):
            action = int(policy(observation, env.action_masks()))
            kinds[space.decode(action).kind] += 1
            observation, _reward, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                break
        else:
            raise RuntimeError(f"{arm} did not terminate on seed {seed}")
    finally:
        search_mod.fight_value = original_fight

    item_stats = getattr(policy, "item_search_stats", {})
    swap_stats = getattr(policy, "swap_search_stats", {})
    return {
        "arm": arm,
        "seed": seed,
        "placement": info.get("placement") or env.n_players,
        "seconds": time.perf_counter() - started,
        "fight_calls": fight_calls,
        # Macro diagnostics: without them a flat result cannot be told apart
        # from presets that never actually behaved differently.
        "rerolls": kinds[ActionKind.REROLL],
        "xp_buys": kinds[ActionKind.BUY_XP],
        "final_level": env.player.level,
        "final_gold": env.player.gold,
        "item_changes": item_stats.get("changed_layouts", 0),
        "accepted_swaps": swap_stats.get("accepted_swaps", 0),
    }


def stats(differences: list[float]) -> dict[str, float]:
    mean = statistics.fmean(differences)
    se = statistics.stdev(differences) / math.sqrt(len(differences))
    return {
        "delta": mean,
        "t": mean / se if se else 0.0,
        "ci_low": mean - Z_95 * se,
        "ci_high": mean + Z_95 * se,
        "family_ci_low": mean - Z_FAMILY * se,
        "family_ci_high": mean + Z_FAMILY * se,
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
        for field in (
            "seconds", "fight_calls", "rerolls", "xp_buys", "final_level",
            "final_gold", "item_changes", "accepted_swaps",
        ):
            summary[arm][field] = statistics.fmean(row[field] for row in rows)

    def place(arm: str) -> list[float]:
        return summary[arm]["placements"]

    def minus(first: list[float], second: list[float]) -> list[float]:
        return [a - b for a, b in zip(first, second, strict=True)]

    comparisons = {}
    for micro in MICROS:
        for macro in MACROS[1:]:
            comparisons[f"{micro}: {macro} minus fast8"] = stats(
                minus(place(f"{micro}:{macro}"), place(f"{micro}:fast8"))
            )
    # Seed-paired difference-in-differences: does strong micro change what
    # the economy plan is worth?
    for macro in MACROS[1:]:
        search_gap = minus(place(f"search:{macro}"), place("search:fast8"))
        greedy_gap = minus(place(f"greedy:{macro}"), place("greedy:fast8"))
        comparisons[f"interaction {macro}: search gap minus greedy gap"] = stats(
            minus(search_gap, greedy_gap)
        )
    for macro in MACROS:
        comparisons[f"teacher value under {macro}: search minus greedy"] = stats(
            minus(place(f"search:{macro}"), place(f"greedy:{macro}"))
        )
    return summary, comparisons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=600)
    parser.add_argument("--seed0", type=int, default=81_000)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    before = source_fingerprint()
    started = time.perf_counter()
    # Search arms first so the long jobs start early and the cheap greedy arms
    # fill the tail, rather than six workers idling behind one straggler.
    jobs = [
        (arm, args.seed0 + game)
        for arm in sorted(ARMS, key=lambda a: a.startswith("greedy"))
        for game in range(args.games)
    ]
    context = get_context("spawn")
    with context.Pool(args.workers, initializer=_init_worker) as pool:
        records = pool.map(play_one, jobs, chunksize=1)
    summary, comparisons = summarise(records)
    after = source_fingerprint()
    if after != before:
        raise RuntimeError(f"source changed during run: {before} -> {after}")
    payload = {
        "source_fingerprint": before,
        "swap_kwargs": SWAP_KWARGS,
        "games": args.games,
        "seed0": args.seed0,
        "workers": args.workers,
        "wall_seconds": time.perf_counter() - started,
        "summary": summary,
        "comparisons": comparisons,
        "records": records,
    }
    print(json.dumps(payload, indent=2))
    if args.json:
        args.json.write_text(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
