"""Paired action-environment test of full versus simulator-finalised buy search."""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import SEARCH_SEED_OFFSET  # noqa: E402
from rl.opponents import FAST8  # noqa: E402
from rl.search import search_buy_greedy_policy  # noqa: E402
from scripts import search_buy_hybrid_ab as hybrid_mod  # noqa: E402

_DATA = None


def _init(cache: str) -> None:
    global _DATA
    _DATA = load_all()
    hybrid_mod._init(cache)


def _play(job) -> dict:
    import rl.search as search_mod

    kind, seed = job
    env = TFTEnv(_DATA, max_actions_per_round=600)
    original_search_fight = search_mod.fight_value
    original_hybrid_fight = hybrid_mod.fight_value
    fights = 0

    def counted(*args, **kwargs):
        nonlocal fights
        fights += 1
        return original_search_fight(*args, **kwargs)

    search_mod.fight_value = counted
    hybrid_mod.fight_value = counted
    original_best_buy = search_mod.best_buy
    if kind == "hybrid":
        search_mod.best_buy = hybrid_mod.hybrid_best_buy
    try:
        policy = search_buy_greedy_policy(env, econ=FAST8)
        policy.rng.seed(seed + SEARCH_SEED_OFFSET)
        observation, _ = env.reset(seed=seed)
        terminated = False
        search_buys = 0
        while not terminated:
            action = policy(observation, env.action_masks())
            search_buys += policy.last_search_buy_slot is not None
            observation, _reward, terminated, truncated, info = env.step(action)
            terminated = terminated or truncated
        return {
            "seed": seed, "placement": info.get("placement") or env.n_players,
            "fight_calls": fights, "search_buys": search_buys,
        }
    finally:
        search_mod.best_buy = original_best_buy
        search_mod.fight_value = original_search_fight
        hybrid_mod.fight_value = original_hybrid_fight


def summarize(rows: list[dict]) -> dict:
    return {
        key: statistics.mean(row[key] for row in rows)
        for key in ("placement", "fight_calls", "search_buys")
    } | {
        "distribution": {
            str(place): sum(row["placement"] == place for row in rows) for place in range(1, 9)
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=32)
    parser.add_argument("--seed", type=int, default=43_000)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--cache", type=Path,
        default=Path("/private/tmp/search_buy_value_features_replica_12x4.npz"),
    )
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    if not args.cache.exists():
        raise FileNotFoundError(f"missing frozen replica cache: {args.cache}")
    jobs = [(kind, seed) for kind in ("full", "hybrid")
            for seed in range(args.seed, args.seed + args.games)]
    with mp.get_context("spawn").Pool(args.workers, _init, (str(args.cache),)) as pool:
        rows = pool.map(_play, jobs, chunksize=1)
    full, hybrid = rows[:args.games], rows[args.games:]
    differences = [b["placement"] - a["placement"] for a, b in zip(full, hybrid, strict=True)]
    delta = statistics.mean(differences)
    sd = statistics.stdev(differences)
    t_value = delta / (sd / math.sqrt(args.games)) if sd else 0.0
    output = {
        "games": args.games, "seed": args.seed,
        "full": summarize(full), "hybrid": summarize(hybrid),
        "hybrid_minus_full_placement": delta, "paired_t": t_value,
        "fight_call_reduction": 1 - (
            statistics.mean(row["fight_calls"] for row in hybrid)
            / statistics.mean(row["fight_calls"] for row in full)
        ),
    }
    print(json.dumps(output, indent=2))
    if args.json:
        args.json.write_text(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
