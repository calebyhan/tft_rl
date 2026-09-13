"""Does exact positioning search add a fourth component to the teacher?

Doc 99 entry 160.147. The control is the 160.144 teacher: exact ``best_buy``
first in phase, exact one-swap fielding before items, exact item search at
margin 0.25. The treatment adds one ``best_move`` per planning phase at the
point ``search_policy`` has always fired it -- after the base scheduler ends
the phase, so after buys, the swap and the item plan.
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
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import LP_BY_PLACEMENT, SEARCH_SEED_OFFSET  # noqa: E402
from rl.opponents import FAST8  # noqa: E402
from rl.search import search_item_greedy_policy  # noqa: E402

ARMS = ("base", "move")

# The 160.144 swap budget, unchanged.
SWAP_KWARGS = {"max_candidates": 4, "panel_size": 2, "trials": 2, "margin": 0.5}

# ``best_move`` sums over the panel and averages over trials, and declines on
# ``best <= baseline + margin``, exactly as ``best_swap`` does. At panel 2 the
# 0.5 margin is therefore the 0.25-per-opponent rule the other three
# components already use -- transferred, not tuned. Candidates stay at the
# shipped 6; panel rises 1 -> 2 and trials fall 3 -> 2 to share one budget.
MOVE_KWARGS = {"max_candidates": 6, "panel_size": 2, "trials": 2, "margin": 0.5}

# Lesson 29: three blocks of one teacher contrast showed a between-block SD of
# about 0.170 that a single block's own interval does not contain. The
# inflated interval below is the conservative reading 160.147 predeclares.
TAU = 0.170

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
        "scripts/search_move_composition_ab.py",
    ):
        digest.update((REPO_ROOT / name).read_bytes())
    return digest.hexdigest()[:12]


def _init_worker() -> None:
    global _DATA
    logging.disable(logging.WARNING)
    _DATA = load_all()


def _policy(env: TFTEnv, arm: str, seed: int):
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
        swap_kwargs=dict(SWAP_KWARGS),
        swap_before_items=True,
        move_search=arm == "move",
        move_kwargs=dict(MOVE_KWARGS) if arm == "move" else None,
    )


def play_one(job: tuple[str, int]) -> dict:
    arm, seed = job
    if _DATA is None:
        raise RuntimeError("evaluation worker was not initialized")
    env = TFTEnv(_DATA, scouting="tokens", max_actions_per_round=600)
    policy = _policy(env, arm, seed)
    original_fight = search_mod.fight_value
    fight_calls = 0

    def counted_fight(*args, **kwargs):
        nonlocal fight_calls
        fight_calls += 1
        return original_fight(*args, **kwargs)

    search_mod.fight_value = counted_fight
    started = time.perf_counter()
    buy_decisions = 0
    try:
        observation, _ = env.reset(seed=seed)
        info = {}
        for _step in range(200_000):
            action = int(policy(observation, env.action_masks()))
            buy_decisions += int(
                getattr(policy, "last_search_buy_slot", None) is not None
            )
            observation, _reward, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                break
        else:
            raise RuntimeError(f"{arm} did not terminate on seed {seed}")
    finally:
        search_mod.fight_value = original_fight

    item_stats = getattr(policy, "item_search_stats", {})
    swap_stats = getattr(policy, "swap_search_stats", {})
    move_stats = getattr(policy, "move_search_stats", {})
    return {
        "arm": arm,
        "seed": seed,
        "placement": info.get("placement") or env.n_players,
        "seconds": time.perf_counter() - started,
        "fight_calls": fight_calls,
        "buy_decisions": buy_decisions,
        "item_decisions": item_stats.get("search_decisions", 0),
        "item_changes": item_stats.get("changed_layouts", 0),
        "swap_decisions": swap_stats.get("search_decisions", 0),
        "accepted_swaps": swap_stats.get("accepted_swaps", 0),
        "move_decisions": move_stats.get("search_decisions", 0),
        "accepted_moves": move_stats.get("accepted_moves", 0),
    }


def paired(first: list[float], second: list[float]) -> dict[str, float]:
    differences = [b - a for a, b in zip(first, second, strict=True)]
    mean = statistics.fmean(differences)
    se = statistics.stdev(differences) / math.sqrt(len(differences))
    inflated = math.sqrt(se**2 + TAU**2)
    return {
        "delta": mean,
        "t": mean / se if se else 0.0,
        "ci_low": mean - 1.96 * se,
        "ci_high": mean + 1.96 * se,
        "tau_ci_low": mean - 1.96 * inflated,
        "tau_ci_high": mean + 1.96 * inflated,
        "first_half": statistics.fmean(differences[: len(differences) // 2]),
        "second_half": statistics.fmean(differences[len(differences) // 2:]),
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
            "seconds", "fight_calls", "buy_decisions", "item_decisions",
            "item_changes", "swap_decisions", "accepted_swaps",
            "move_decisions", "accepted_moves",
        ):
            summary[arm][field] = statistics.fmean(row[field] for row in rows)

    base = summary["base"]["placements"]
    move = summary["move"]["placements"]
    comparisons = {
        "move minus base": paired(base, move),
        "move minus base, first-place rate": paired(
            [float(p == 1) for p in base], [float(p == 1) for p in move]
        ),
        "move minus base, top-four rate": paired(
            [float(p <= 4) for p in base], [float(p <= 4) for p in move]
        ),
    }
    return summary, comparisons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=600)
    parser.add_argument("--seed0", type=int, default=82_000)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    before = source_fingerprint()
    started = time.perf_counter()
    jobs = [
        (arm, args.seed0 + game)
        for game in range(args.games)
        for arm in ARMS
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
        "move_kwargs": MOVE_KWARGS,
        "tau": TAU,
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
