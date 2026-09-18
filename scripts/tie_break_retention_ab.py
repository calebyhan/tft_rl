"""Does the visible board tie-break retain the established teacher's strength?

Doc 99 entry 160.156. Both arms are the 160.152 teacher (buy, swap, items,
move at their established budgets); they differ only in
``rl.search.BOARD_TIE_BREAK``:

* ``insertion`` -- the teacher as measured: ties between equally ranked board
  hexes follow the board dict's insertion order, which no observer can see.
* ``hex`` -- the repair: ties follow hex order.

The repair "retains" the teacher when the paired placement difference's
two-sided 90% interval lies inside +/- the teacher's smallest established
component (TOST at 5%).
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

ARMS = ("insertion", "hex")

# The 160.144 swap and 160.152 move budgets, unchanged.
SWAP_KWARGS = {"max_candidates": 4, "panel_size": 2, "trials": 2, "margin": 0.5}
MOVE_KWARGS = {"max_candidates": 6, "panel_size": 2, "trials": 2, "margin": 0.5}

# The smallest established component of this teacher: positioning, pooled
# -0.229 over 1,800 seeds (160.152). A repair that moves the teacher by less
# than its weakest real part has not changed what the teacher is.
EQUIVALENCE_MARGIN = 0.229
# Reported beside the plain interval; it does not decide (160.152's open τ).
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
        "scripts/tie_break_retention_ab.py",
    ):
        digest.update((REPO_ROOT / name).read_bytes())
    return digest.hexdigest()[:12]


def _init_worker() -> None:
    global _DATA
    logging.disable(logging.WARNING)
    _DATA = load_all()


def teacher(env, seed: int):
    """The 160.152 teacher, exactly as `search_move_composition_ab` built it."""
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
        move_search=True,
        move_kwargs=dict(MOVE_KWARGS),
    )


def play_one(job: tuple[str, int]) -> dict:
    arm, seed = job
    if _DATA is None:
        raise RuntimeError("evaluation worker was not initialized")
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}")
    previous_mode = search_mod.BOARD_TIE_BREAK
    search_mod.BOARD_TIE_BREAK = arm
    original_fight = search_mod.fight_value
    fight_calls = 0

    def counted_fight(*args, **kwargs):
        nonlocal fight_calls
        fight_calls += 1
        return original_fight(*args, **kwargs)

    search_mod.fight_value = counted_fight
    started = time.process_time()
    try:
        env = TFTEnv(_DATA, scouting="tokens", max_actions_per_round=600)
        policy = teacher(env, seed)
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
        search_mod.BOARD_TIE_BREAK = previous_mode

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
    differences = [b - a for a, b in zip(first, second, strict=True)]
    mean = statistics.fmean(differences)
    enough = len(differences) > 1
    se = (
        statistics.stdev(differences) / math.sqrt(len(differences))
        if enough else math.nan
    )
    widened = math.sqrt(se**2 + TAU**2) if enough else math.nan
    half = len(differences) // 2
    return {
        "delta": mean,
        "se": se,
        "t": mean / se if enough and se else 0.0,
        "ci_low": mean - 1.96 * se,
        "ci_high": mean + 1.96 * se,
        "ci90_low": mean - 1.645 * se,
        "ci90_high": mean + 1.645 * se,
        "tau_ci_low": mean - 1.96 * widened,
        "tau_ci_high": mean + 1.96 * widened,
        "first_half": statistics.fmean(differences[:half]) if enough else math.nan,
        "second_half": statistics.fmean(differences[half:]) if enough else math.nan,
    }


def equivalent(contrast: dict[str, float], margin: float = EQUIVALENCE_MARGIN) -> bool:
    """TOST at 5%: the 90% interval lies strictly inside (-margin, +margin)."""
    return (
        not math.isnan(contrast["se"])
        and -margin < contrast["ci90_low"]
        and contrast["ci90_high"] < margin
    )


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

    legacy = summary["insertion"]["placements"]
    visible = summary["hex"]["placements"]
    placement = paired(legacy, visible)
    comparisons = {
        "hex minus insertion": placement | {"equivalent": equivalent(placement)},
        "hex minus insertion, first-place rate": paired(
            [float(p == 1) for p in legacy], [float(p == 1) for p in visible]
        ),
        "hex minus insertion, top-four rate": paired(
            [float(p <= 4) for p in legacy], [float(p <= 4) for p in visible]
        ),
        "identical placements": sum(a == b for a, b in zip(legacy, visible, strict=True)),
    }
    return summary, comparisons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=600)
    parser.add_argument("--seed0", type=int, default=86_000)
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
        "equivalence_margin": EQUIVALENCE_MARGIN,
        "tau": TAU,
        "games": args.games,
        "seed0": args.seed0,
        "workers": args.workers,
        "wall_seconds": time.perf_counter() - started,
        "records": records,
    }
    if set(args.arms) == set(ARMS):
        payload["summary"], payload["comparisons"] = summarise(records)
    text = json.dumps(payload, indent=2)
    if args.json:
        args.json.write_text(text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
