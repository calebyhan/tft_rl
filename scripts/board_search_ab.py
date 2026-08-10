"""Does searching over *boards* beat searching over single swaps? Entry 106.

`best_swap` moves one bench unit onto the board -- a single action. Entry 91
measured 1,098 single-action counterfactuals at max |t| = 1.82: single actions
do not move placement. So 54's +0.307 is roughly the ceiling of that shape of
search, and widening it buys precision on a decision that does not matter
(105.3).

91 tested single actions only. `best_board` changes up to `max_swaps` units at
once for the **same one combat per candidate** -- 83.6s against 64.2s per ten
episodes, measured. The hypothesis is that placement responds to board-level
changes while being insensitive to unit-level ones, which is what "board size
dominates" (67, 68, 72) predicts.

This gates a much larger programme (105.5): a combat surrogate is only worth
building if search is worth having, and search is only worth having if it beats
its own one-swap incumbent by more than noise.

Named outcomes, before the run:

* **board >> swap** -- multi-action search is the lever; build the surrogate.
* **board ~= swap** -- the gain is the search *firing at all*, not its depth,
  and no surrogate is justified.
* **board < swap** -- more simultaneous change is worse; the engine rewards
  incremental boards, which would itself explain the reroll deficit.

    .venv/bin/python scripts/board_search_ab.py --episodes 150 --workers 10
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
    parser.add_argument("--episodes", type=int, default=150)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--econ", default="standard")
    parser.add_argument("--max-swaps", type=int, default=3)
    args = parser.parse_args()

    seeds = list(range(args.episodes))
    econ = STRATEGIES[args.econ] if args.econ else None
    arms = [
        ("no search", None),
        ("swap (1 action)", dict(mode="swap", max_candidates=4,
                                 panel_size=2, trials=3)),
        (f"board ({args.max_swaps} actions)",
         dict(mode="board", max_swaps=args.max_swaps, max_candidates=6,
              panel_size=2, trials=3)),
    ]

    results = {}
    for label, search in arms:
        results[label] = evaluate_scripted_parallel(
            seeds, workers=args.workers, econ=econ, search_kwargs=search,
            **TEACHER
        )
        print(f"  {label:<20}{results[label].avg_placement:.3f}", flush=True)

    base = results["no search"]
    swap = results["swap (1 action)"]
    print(f"\n{'arm':<20}{'place':>8}{'ci95':>7}{'LP':>8}{'1st':>7}{'top4':>7}"
          f"{'8th':>7}{'vs none':>18}{'vs swap':>18}")
    for label, r in results.items():
        last = r.placements.count(8) / len(r.placements)
        vs_none = "" if label == "no search" else (
            "%+.3f  t=%+.2f" % paired_t(base.placements, r.placements))
        vs_swap = "" if label in ("no search", "swap (1 action)") else (
            "%+.3f  t=%+.2f" % paired_t(swap.placements, r.placements))
        print(f"{label:<20}{r.avg_placement:>8.3f}{r.ci95:>7.3f}{r.avg_lp:>8.2f}"
              f"{r.win_rate:>7.1%}{r.top4_rate:>7.1%}{last:>7.1%}"
              f"{vs_none:>18}{vs_swap:>18}")
    print("\nnegative is better. Entry 54 measured swap at +0.307 vs no search "
          "(n=300, pre-98 engine).")


if __name__ == "__main__":
    main()
