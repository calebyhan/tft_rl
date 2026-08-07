"""Does making the search learnable cost any of its strength? (doc 99 entry 79)

Entry 79.3 found `best_move` samples its candidates from a free-running RNG,
so identical boards get different answers -- 38.7% self-agreement, five
distinct answers from five streams on 55% of states. That is a ceiling on
imitation, and it explains why the search teacher gained 0.330 (78.2) while
its clone gained nothing (79.1).

Seeding the sample from the board state removes the one-to-many map. The
sampling *distribution* is untouched -- moves are still drawn uniformly from
the same ~200 -- so search quality should be unchanged. Should be. This
measures it, because the whole plan downstream rests on it:

* `control`        -- econ teacher, no search. Reproduces 78.2's 4.213.
* `c12 stream`     -- the pre-79 search. Reproduces 78.2's 3.883.
* `c12 state-seed` -- the same search, seeded from the board.

All three on shared seeds in one run: engine changes shift every number, so
the old figures are re-derived here rather than quoted (CLAUDE.md).

Reading it: if `state-seed` matches `stream`, the fix is free and the clone
experiment can proceed. If it is materially worse, determinism costs strength
and the trade has to be stated rather than assumed.

    .venv/bin/python scripts/search_seeding_ab.py --episodes 300 --workers 10
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rl.evaluate import evaluate_scripted_parallel  # noqa: E402
from rl.opponents import STANDARD  # noqa: E402
from rl.timing import timed  # noqa: E402

TEACHER = {
    "sell_bench": True,
    "buy_synergy": True,
    "match_items": True,
    "corner_carry": True,
    "econ": STANDARD,
}


def source_fingerprint() -> str:
    """Digest of the modules the spawn workers re-import from disk.

    Entry 68.4: a mutation test rewrote `rl/evaluate.py` while a live parallel
    evaluation was running, and two arms were measured against broken code
    without anything looking wrong. The workers read source at import time, so
    editing during a run silently changes what is being measured.
    """
    digest = hashlib.sha256()
    for name in ("rl/evaluate.py", "rl/search.py", "rl/opponents.py"):
        digest.update(Path(name).read_bytes())
    return digest.hexdigest()[:12]


def paired_t(a: list[int], b: list[int]) -> tuple[float, float]:
    diffs = [y - x for x, y in zip(a, b, strict=True)]
    n = len(diffs)
    mean = sum(diffs) / n
    if n < 2:
        return mean, 0.0
    var = sum((d - mean) ** 2 for d in diffs) / (n - 1)
    return mean, (mean / math.sqrt(var / n) if var > 0 else 0.0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=300)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    seeds = list(range(args.episodes))
    before = source_fingerprint()
    print(f"source fingerprint: {before}")

    arms: list[tuple[str, dict | None]] = [
        ("control (no search)", None),
        ("c12 stream", {"mode": "move", "max_candidates": 12, "panel_size": 1,
                        "state_seeded": False}),
        ("c12 state-seed", {"mode": "move", "max_candidates": 12, "panel_size": 1,
                            "state_seeded": True}),
    ]

    results = {}
    with timed("search_seeding_ab", episodes=args.episodes,
               arms=len(arms), workers=args.workers):
        for name, search in arms:
            results[name] = evaluate_scripted_parallel(
                seeds, workers=args.workers, search_kwargs=search, **TEACHER
            )
            print(f"  {name:<22}{results[name].avg_placement:.3f}", flush=True)

    after = source_fingerprint()
    if after != before:
        print(f"\n!! SOURCE CHANGED MID-RUN ({before} -> {after}). The workers "
              "re-import\n   from disk, so these arms were not all measured "
              "against the same code.\n   Discard this run (doc 99 entry 68.4).")

    base = results["control (no search)"]
    print(f"\n{'arm':<22}{'place':>8}{'ci95':>7}{'LP':>8}{'1st':>7}{'top4':>7}"
          f"{'8th':>7}{'vs control':>22}")
    for name, r in results.items():
        last = Counter(r.placements)[8] / len(r.placements)
        if name == "control (no search)":
            delta = ""
        else:
            mean, t = paired_t(base.placements, r.placements)
            delta = f"{mean:+.3f}  t={t:+.2f}"
        print(f"{name:<22}{r.avg_placement:>8.3f}{r.ci95:>7.3f}{r.avg_lp:>8.2f}"
              f"{r.win_rate:>7.1%}{r.top4_rate:>7.1%}{last:>7.1%}{delta:>22}")

    mean, t = paired_t(results["c12 stream"].placements,
                       results["c12 state-seed"].placements)
    print(f"\nstate-seed vs stream: {mean:+.3f}  t={t:+.2f}  n={args.episodes}")
    print("Positive means state-seeding made the teacher worse. The claim being "
          "tested is\nthat this is ~0: same distribution, reproducible draw.")

    if args.json:
        args.json.write_text(json.dumps(
            {n: r.as_dict() | {"placements": r.placements}
             for n, r in results.items()}, indent=1))
        print(f"\nper-episode results: {args.json}")


if __name__ == "__main__":
    main()
