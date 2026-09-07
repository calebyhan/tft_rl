"""Does observation-deterministic item search retain its strength? (160.118).

    .venv/bin/python scripts/item_seeding_ab.py --games 200 --workers 6
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
from rl.evaluate import LP_BY_PLACEMENT, SEARCH_SEED_OFFSET  # noqa: E402
from rl.opponents import FAST8, default_opponent  # noqa: E402
from scripts.item_headroom_ab import ItemHeadroomPolicy, SearchBudget  # noqa: E402

_DATA = None
ARMS = {
    "control": None,
    "stream": SearchBudget(1, 2, 2, state_seeded=False),
    "state": SearchBudget(1, 2, 2, state_seeded=True),
}


def _init() -> None:
    global _DATA
    _DATA = load_all()


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    for name in (
        "engine/player.py",
        "engine/unit.py",
        "rl/opponents.py",
        "rl/search.py",
        "scripts/item_headroom_ab.py",
        "scripts/item_seeding_ab.py",
    ):
        digest.update((REPO_ROOT / name).read_bytes())
    return digest.hexdigest()[:12]


def play_one(job) -> dict:
    arm, seed = job
    data = _DATA if _DATA is not None else load_all()
    policy = ItemHeadroomPolicy(
        seed=0,
        econ=FAST8,
        budget=ARMS[arm],
        search_seed=seed + SEARCH_SEED_OFFSET,
    )
    started = time.perf_counter()
    result = Match(
        data,
        [policy] + [default_opponent(i) for i in range(1, 8)],
        seed=seed,
    ).run()
    return {
        "arm": arm,
        "seed": seed,
        "placement": result.placement_of(0),
        "seconds": time.perf_counter() - started,
        **{
            field: getattr(policy, field)
            for field in (
                "search_decisions",
                "changed_layouts",
                "component_completions",
                "candidate_boards",
                "fight_calls",
            )
        },
    }


def paired(control: list[int], treatment: list[int]) -> dict[str, float]:
    diffs = [b - a for a, b in zip(control, treatment, strict=True)]
    mean = statistics.fmean(diffs)
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
    for rows in grouped.values():
        rows.sort(key=lambda row: row["seed"])

    summary = {}
    for arm, rows in grouped.items():
        placements = [row["placement"] for row in rows]
        counts = Counter(placements)
        summary[arm] = {
            "placement": statistics.fmean(placements),
            "lp": statistics.fmean(LP_BY_PLACEMENT[p] for p in placements),
            "first": counts[1] / len(rows),
            "top4": sum(p <= 4 for p in placements) / len(rows),
            "eighth": counts[8] / len(rows),
            "histogram": [counts[p] for p in range(1, 9)],
            "placements": placements,
        }
        for field in (
            "seconds",
            "search_decisions",
            "changed_layouts",
            "component_completions",
            "candidate_boards",
            "fight_calls",
        ):
            summary[arm][field] = statistics.fmean(row[field] for row in rows)

    comparisons = {
        "stream minus control": paired(
            summary["control"]["placements"], summary["stream"]["placements"]
        ),
        "state minus control": paired(
            summary["control"]["placements"], summary["state"]["placements"]
        ),
        "state minus stream": paired(
            summary["stream"]["placements"], summary["state"]["placements"]
        ),
    }
    return summary, comparisons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=200)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--seed0", type=int, default=56_000)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    before = source_fingerprint()
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
    payload = {
        "games": args.games,
        "seed0": args.seed0,
        "workers": args.workers,
        "source_fingerprint": before,
        "wall_seconds": elapsed,
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
