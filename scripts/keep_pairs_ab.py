"""Does keeping upgrade-progressing copies make the teacher better? Entry 102.

101 found untargeted seats reach a 3-star in 0.33% of games against a real
34.5%. 102 traced it to the sell rule: a 1-star of a champion already held at
2-star is the start of the second pair a 3-star needs, and it is also the
weakest unit on the bench, so "sell the weakest surplus" reaches for it first.
The teacher did this on 13.4% of its sells and reached a 3-star in 0 of 30
games.

`keep_pairs` prefers to sell something else. This measures whether the more
realistic behaviour is also *better*, which is the only reason it matters:
lesson 16 says the teacher is the imitation ceiling and improving it is the one
lever that has ever moved the clone.

Both arms share seeds and the same field, so they differ in the teacher only.

    .venv/bin/python scripts/keep_pairs_ab.py --episodes 300 --workers 10
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rl.evaluate import evaluate_scripted_parallel  # noqa: E402
from rl.opponents import STRATEGIES  # noqa: E402

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
    parser.add_argument("--econ", default="standard")
    parser.add_argument("--caps", default="0,2,3,99",
                        help="keep_pairs values to sweep; 0 is off, 99 is the "
                             "unconditional arm entry 102.3 measured")
    args = parser.parse_args()

    seeds = list(range(args.episodes))
    econ = STRATEGIES[args.econ] if args.econ else None
    caps = [int(c) for c in args.caps.split(",")]
    results = {}
    for cap in caps:
        results[cap] = evaluate_scripted_parallel(
            seeds, workers=args.workers, econ=econ, keep_pairs=cap, **TEACHER
        )
        print(f"  keep_pairs={cap:<4}{results[cap].avg_placement:.3f}", flush=True)

    base = results[caps[0]]
    print(f"\n{'arm':<14}{'place':>8}{'ci95':>7}{'LP':>8}{'1st':>7}"
          f"{'top4':>7}{'8th':>7}{'vs off':>18}")
    for cap, r in results.items():
        last = r.placements.count(8) / len(r.placements)
        if cap == caps[0]:
            delta = ""
        else:
            mean, t = paired_t(base.placements, r.placements)
            delta = f"{mean:+.3f}  t={t:+.2f}"
        print(f"{'keep_pairs=' + str(cap):<14}{r.avg_placement:>8.3f}"
              f"{r.ci95:>7.3f}{r.avg_lp:>8.2f}"
              f"{r.win_rate:>7.1%}{r.top4_rate:>7.1%}{last:>7.1%}{delta:>18}")
    print(f"\nnegative is better; econ={args.econ}. 0=off, 99=unconditional "
          "(the arm entry 102.3 measured).")


if __name__ == "__main__":
    main()
