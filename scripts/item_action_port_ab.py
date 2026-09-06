"""Replicate item headroom through real EQUIP actions (doc 99 entry 160.112).

Four arms on the same seeds distinguish an item result from a port result:

* direct control / direct item use Match-level policies;
* action control / action item use the faithful scheduler and ActionExecutor.

The two within-interface contrasts independently estimate item value. The two
cross-interface contrasts test whether the port preserves the direct policy.

    .venv/bin/python scripts/item_action_port_ab.py --games 200 --workers 6
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.loader import load_all  # noqa: E402
from engine.match import Match  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import (  # noqa: E402
    LP_BY_PLACEMENT,
    SEARCH_SEED_OFFSET,
    greedy_action_policy,
)
from rl.opponents import FAST8, default_opponent  # noqa: E402
from rl.search import search_item_greedy_policy  # noqa: E402
from scripts.item_headroom_ab import (  # noqa: E402
    ItemHeadroomPolicy,
    SearchBudget,
)

_DATA = None
ITEM_BUDGET = SearchBudget(depth=1, panel_size=2, trials=2)
ARMS = ("direct-control", "direct-item", "action-control", "action-item")


def _init() -> None:
    global _DATA
    _DATA = load_all()


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
        "scripts/item_headroom_ab.py",
        "scripts/item_action_port_ab.py",
    ):
        digest.update((REPO_ROOT / name).read_bytes())
    return digest.hexdigest()[:12]


def _zero_diagnostics() -> dict[str, int]:
    return {
        "search_decisions": 0,
        "changed_layouts": 0,
        "component_candidates": 0,
        "component_completions": 0,
        "candidate_boards": 0,
        "fight_calls": 0,
    }


def _direct(data, arm: str, seed: int):
    policy = ItemHeadroomPolicy(
        seed=0,
        econ=FAST8,
        budget=ITEM_BUDGET if arm == "direct-item" else None,
        search_seed=seed + SEARCH_SEED_OFFSET,
    )
    policies = [policy] + [default_opponent(i) for i in range(1, 8)]
    result = Match(data, policies, seed=seed).run()
    diagnostics = {
        field: getattr(policy, field)
        for field in _zero_diagnostics()
    }
    return result.placement_of(0), diagnostics


def _action(data, arm: str, seed: int):
    env = TFTEnv(data, max_actions_per_round=600)
    if arm == "action-item":
        policy = search_item_greedy_policy(
            env,
            econ=FAST8,
            rng_seed=seed + SEARCH_SEED_OFFSET,
            depth=ITEM_BUDGET.depth,
            panel_size=ITEM_BUDGET.panel_size,
            trials=ITEM_BUDGET.trials,
        )
    else:
        policy = greedy_action_policy(env, econ=FAST8)
    observation, _ = env.reset(seed=seed)
    info = {}
    for _ in range(200_000):
        action = int(policy(observation, env.action_masks()))
        observation, _reward, terminated, truncated, info = env.step(action)
        if terminated or truncated:
            break
    else:
        raise RuntimeError(f"action policy did not terminate on seed {seed}")
    diagnostics = getattr(policy, "item_search_stats", _zero_diagnostics())
    return info.get("placement") or env.n_players, dict(diagnostics)


def play_one(job) -> dict:
    arm, seed = job
    data = _DATA if _DATA is not None else load_all()
    started = time.perf_counter()
    if arm.startswith("direct-"):
        placement, diagnostics = _direct(data, arm, seed)
    else:
        placement, diagnostics = _action(data, arm, seed)
    return {
        "arm": arm,
        "seed": seed,
        "placement": placement,
        "seconds": time.perf_counter() - started,
        **diagnostics,
    }


def paired(control: list[int], treatment: list[int]) -> dict[str, float]:
    diffs = [b - a for a, b in zip(control, treatment, strict=True)]
    mean = statistics.fmean(diffs)
    if len(diffs) < 2:
        return {"delta": mean, "sd": 0.0, "se": 0.0, "t": 0.0,
                "ci_low": mean, "ci_high": mean}
    sd = statistics.stdev(diffs)
    se = sd / math.sqrt(len(diffs))
    return {
        "delta": mean,
        "sd": sd,
        "se": se,
        "t": mean / se if se else 0.0,
        "ci_low": mean - 1.96 * se,
        "ci_high": mean + 1.96 * se,
    }


def summarise(records: list[dict]) -> tuple[dict, dict]:
    grouped = {arm: [] for arm in ARMS}
    for record in records:
        grouped[record["arm"]].append(record)
    for group in grouped.values():
        group.sort(key=lambda row: row["seed"])

    summary = {}
    for arm, group in grouped.items():
        placements = [row["placement"] for row in group]
        counts = Counter(placements)
        summary[arm] = {
            "n": len(group),
            "placement": statistics.fmean(placements),
            "avg_lp": statistics.fmean(LP_BY_PLACEMENT[p] for p in placements),
            "win_rate": counts[1] / len(group),
            "top4": sum(p <= 4 for p in placements) / len(group),
            "last": counts[8] / len(group),
            "distribution": {str(p): counts[p] for p in range(1, 9)},
            "placements": placements,
        }
        for field in ("seconds", *_zero_diagnostics()):
            summary[arm][field] = statistics.fmean(row[field] for row in group)

    comparisons = {}
    for control, treatment in (
        ("direct-control", "direct-item"),
        ("action-control", "action-item"),
        ("direct-control", "action-control"),
        ("direct-item", "action-item"),
    ):
        key = f"{treatment} minus {control}"
        comparisons[key] = paired(
            summary[control]["placements"], summary[treatment]["placements"]
        )
        comparisons[key]["exact_seed_matches"] = sum(
            a == b
            for a, b in zip(
                summary[control]["placements"],
                summary[treatment]["placements"],
                strict=True,
            )
        )
    return summary, comparisons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=200)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--seed0", type=int, default=53_000)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    before = source_fingerprint()
    print(f"source fingerprint: {before}", flush=True)
    jobs = [
        (arm, args.seed0 + game)
        for arm in ARMS
        for game in range(args.games)
    ]
    started = time.perf_counter()
    with Pool(args.workers, initializer=_init) as pool:
        records = pool.map(play_one, jobs, chunksize=1)
    elapsed = time.perf_counter() - started
    after = source_fingerprint()
    if after != before:
        raise RuntimeError(f"source changed during run: {before} -> {after}")

    summary, comparisons = summarise(records)
    print(
        f"{'arm':<16}{'place':>8}{'LP':>8}{'1st':>7}{'top4':>7}{'8th':>7}"
        f"{'search':>9}{'changed':>9}{'comb':>8}{'fights':>10}{'sec':>9}"
    )
    for arm in ARMS:
        row = summary[arm]
        print(
            f"{arm:<16}{row['placement']:>8.3f}{row['avg_lp']:>8.2f}"
            f"{row['win_rate']:>7.1%}{row['top4']:>7.1%}{row['last']:>7.1%}"
            f"{row['search_decisions']:>9.1f}{row['changed_layouts']:>9.1f}"
            f"{row['component_completions']:>8.1f}{row['fight_calls']:>10.1f}"
            f"{row['seconds']:>9.1f}"
        )
    print()
    for name, row in comparisons.items():
        print(
            f"{name}: {row['delta']:+.3f} placement, t={row['t']:+.2f}, "
            f"CI=[{row['ci_low']:+.3f}, {row['ci_high']:+.3f}], "
            f"exact={row['exact_seed_matches']}/{args.games}"
        )
    print(f"wall={elapsed:.1f}s fingerprint={after}")

    payload = {
        "source_fingerprint": after,
        "seed0": args.seed0,
        "games": args.games,
        "workers": args.workers,
        "wall_seconds": elapsed,
        "summary": summary,
        "comparisons": comparisons,
        "records": records,
    }
    if args.json:
        args.json.write_text(json.dumps(payload, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
