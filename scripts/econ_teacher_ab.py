"""Which economy should the teacher run? (doc 99 entry 72)

Entry 71 gave the seven opponents real economy plans. Entry 72 then measured
the teacher's edge over parity collapsing from 1.470 to 0.617 -- because the
field acquired an economy and the teacher still had "buy XP whenever gold >=
30". The teacher is the imitation target for an agent meant to play real TFT,
so it should not be the worst economist at the table.

Each arm is the teacher configuration (``sell_bench`` plus the three expert
flags) running one :class:`~rl.opponents.EconStrategy`, against the mixed
default field, on shared seeds. No training seed, so no replication caveat
(entry 65).

**This file has a ``__main__`` guard and needs one.** ``evaluate_scripted_
parallel`` uses ``spawn``, so every worker re-imports the module it was
launched from; module-level work re-executes in each worker and spawns more
workers. The first version of this comparison was a scratchpad script without
the guard and fork-bombed for 90 minutes, producing a 745 MB log of
``RuntimeError`` and zero results.

    .venv/bin/python scripts/econ_teacher_ab.py --episodes 300 --workers 10
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rl.evaluate import evaluate_scripted_parallel  # noqa: E402
from rl.opponents import STRATEGIES  # noqa: E402
from rl.timing import timed  # noqa: E402

TEACHER = {
    "sell_bench": True,
    "buy_synergy": True,
    "match_items": True,
    "corner_carry": True,
}


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
    arms: list[tuple[str, object]] = [("no-econ (incumbent)", None)]
    arms += [(name, strategy) for name, strategy in STRATEGIES.items()]

    results = {}
    with timed("econ_teacher_ab", episodes=args.episodes,
               arms=len(arms), workers=args.workers):
        for name, econ in arms:
            results[name] = evaluate_scripted_parallel(
                seeds, workers=args.workers, econ=econ, **TEACHER
            )
            print(f"  {name:<22}{results[name].avg_placement:.3f}", flush=True)

    base = results["no-econ (incumbent)"]
    print(f"\n{'arm':<22}{'place':>8}{'ci95':>7}{'LP':>8}{'1st':>7}{'top4':>7}"
          f"{'8th':>7}{'vs incumbent':>22}")
    for name, r in results.items():
        from collections import Counter
        last = Counter(r.placements)[8] / len(r.placements)
        if name == "no-econ (incumbent)":
            delta = ""
        else:
            mean, t = paired_t(base.placements, r.placements)
            delta = f"{mean:+.3f}  t={t:+.2f}"
        print(f"{name:<22}{r.avg_placement:>8.3f}{r.ci95:>7.3f}{r.avg_lp:>8.2f}"
              f"{r.win_rate:>7.1%}{r.top4_rate:>7.1%}{last:>7.1%}{delta:>22}")

    print("\n4.500 = parity with the seven bots. Negative deltas are better.")

    if args.json:
        args.json.write_text(json.dumps(
            {n: r.as_dict() | {"placements": r.placements}
             for n, r in results.items()}, indent=1))
        print(f"\nper-episode results: {args.json}")


if __name__ == "__main__":
    main()
