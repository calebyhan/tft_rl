"""Greedy versus exact-simulation buying at identical resources (doc 99 160.89).

Both arms run the same econ, field and seeds; only the choice of *which unit to
buy* differs. The placement gap is therefore a fixed-resource quantity: it is
what better decisions are worth when nobody is given anything extra.

    .venv/bin/python scripts/teacher_headroom_ab.py --games 200 --workers 8
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import (  # noqa: E402
    SEARCH_SEED_OFFSET,
    greedy_action_policy,
    scripted_policy,
)
from rl.opponents import FAST8  # noqa: E402
from rl.search import search_buy_greedy_policy, search_policy  # noqa: E402

_DATA = None


def _init() -> None:
    global _DATA
    _DATA = load_all()


def play_one(job: tuple[str, int] | tuple[str, int, int]) -> dict:
    # The cap must match whatever the clone was trained and evaluated
    # under, or the teachers get 12x the actions per round (160.96).
    arm, seed, args_cap = (*job, 600)[:3]
    data = _DATA if _DATA is not None else load_all()
    env = TFTEnv(data, max_actions_per_round=args_cap)
    if arm == "search":
        policy = search_buy_greedy_policy(env, econ=FAST8)
        policy.rng.seed(seed + SEARCH_SEED_OFFSET)
    elif arm == "scripted":
        # The expert `train_ppo.py` actually clones -- a separately evolved
        # heuristic, not the faithful `GreedyPolicy` port. Included because a
        # headroom figure measured against `greedy` says nothing about the BC
        # target unless the two are known to sit in the same place
        # (doc 99 entry 160.91).
        # `train_ppo.py` defaults `--expert-sell` and `--expert-flags` on, so
        # the cloned teacher has all four. Measuring the flagless default would
        # understate the BC target and overstate the headroom above it.
        policy = scripted_policy(
            env, econ=FAST8, sell_bench=True,
            buy_synergy=True, match_items=True, corner_carry=True,
        )
    elif arm == "scripted+search":
        # Exactly how `train_ppo.py --expert-buy-search` builds its teacher:
        # `search_policy` wrapping `scripted_policy`, mode "none". The `search`
        # arm wraps `greedy_action_policy` instead, so the two are not the same
        # teacher and the clone must be scored against this one.
        base = scripted_policy(
            env, econ=FAST8, sell_bench=True,
            buy_synergy=True, match_items=True, corner_carry=True,
        )
        policy = search_policy(
            env, base=base, mode="none", buy_search=True,
            rng_seed=seed + SEARCH_SEED_OFFSET,
        )
    else:
        policy = greedy_action_policy(env, econ=FAST8)

    observation, _ = env.reset(seed=seed)
    info: dict = {}
    for _ in range(200_000):
        action = int(policy(observation, env.action_masks()))
        observation, _reward, terminated, truncated, info = env.step(action)
        if terminated or truncated:
            break
    return {
        "arm": arm,
        "seed": seed,
        "placement": info.get("placement") or env.n_players,
    }


def paired_t(control: list[float], treatment: list[float]) -> tuple[float, float]:
    diffs = [b - a for a, b in zip(control, treatment, strict=True)]
    n = len(diffs)
    mean = sum(diffs) / n
    var = sum((d - mean) ** 2 for d in diffs) / (n - 1)
    return mean, (mean / math.sqrt(var / n) if var > 0 else 0.0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=200)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--seed0", type=int, default=43_000)
    parser.add_argument("--max-actions", type=int, default=600)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    arms = ("scripted", "greedy", "search", "scripted+search")
    jobs = [(arm, args.seed0 + game, args.max_actions)
            for arm in arms for game in range(args.games)]
    with Pool(args.workers, initializer=_init) as pool:
        records = pool.map(play_one, jobs, chunksize=2)

    by_arm: dict[str, list[dict]] = {arm: [] for arm in arms}
    for record in records:
        by_arm[record["arm"]].append(record)
    for group in by_arm.values():
        group.sort(key=lambda record: record["seed"])

    summary = {}
    print(f"{'arm':<10}{'place':>8}{'1st':>7}{'top4':>7}{'8th':>7}   distribution")
    for arm in arms:
        places = [record["placement"] for record in by_arm[arm]]
        counts = Counter(places)
        summary[arm] = {
            "n": len(places),
            "place": statistics.fmean(places),
            "win_rate": counts[1] / len(places),
            "top4": sum(1 for p in places if p <= 4) / len(places),
            "last": counts[8] / len(places),
            "distribution": {str(p): counts[p] for p in range(1, 9)},
            "placements": places,
        }
        s = summary[arm]
        print(f"{arm:<10}{s['place']:>8.3f}{s['win_rate']:>7.1%}{s['top4']:>7.1%}"
              f"{s['last']:>7.1%}   {[counts[p] for p in range(1, 9)]}")

    deltas = {}
    print()
    for control, treatment in (
        ("greedy", "search"), ("scripted", "greedy"),
        ("scripted", "scripted+search"), ("scripted+search", "search")
    ):
        mean, t = paired_t(
            summary[control]["placements"], summary[treatment]["placements"]
        )
        deltas[f"{treatment} vs {control}"] = {"place": mean, "t": t}
        print(f"{treatment} minus {control}: {mean:+.3f} placement "
              f"(t={t:+.2f}, n={args.games})")
    if args.json:
        args.json.write_text(json.dumps(
            {"summary": summary, "deltas": deltas}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
