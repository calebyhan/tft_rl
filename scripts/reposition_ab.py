"""Is repositioning worth anything now the world is validated? (doc 99 entry 78)

Entry 52.4 established the teacher **never repositions**: over 8 games it issued
173 bench selections and 0 board selections. It picks a hex once, when a unit is
fielded, and never revisits it. Entry 47.10 measured positional search at
**-0.198 (t=-1.78)** pooled across four configurations -- suggestive, under this
project's bar, and measured in the world entry 71 voided: throttled opponents,
a 12-action budget, and a teacher with no economy.

Re-derived here because three things changed that bear on it directly:

* targeting is now **verified** faithful (nearest, held until death, entry
  77.4), so where a unit stands actually determines what attacks it;
* the star-vs-slot exchange rate is verified (76.1), so fights are decided by
  the board rather than by a modelling artefact;
* the teacher has an economy (74.2) and the field is a fair lobby (73.5).

Augment choice was the other candidate teacher gap and was **dropped**: the
augment pool is 14 generic archetypes rather than the real Set 17 set
(`config.unverified`, entry 17.1), so tuning against it optimises invented data.
Positioning uses the real hex board and verified targeting.

    .venv/bin/python scripts/reposition_ab.py --episodes 300 --workers 10
"""

from __future__ import annotations

import argparse
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
    # `max_candidates` is the search's budget: 6 covers ~3.6% of the ~168 legal
    # moves on a typical board (entry 47.6). More candidates bought nothing
    # then (47.7); the open question was whether a move that beats one opponent
    # generalises, which `panel_size` addresses.
    arms: list[tuple[str, dict | None]] = [
        ("control (no search)", None),
        ("move c6 p1", {"mode": "move", "max_candidates": 6, "panel_size": 1}),
        ("move c12 p1", {"mode": "move", "max_candidates": 12, "panel_size": 1}),
        ("move c6 p3", {"mode": "move", "max_candidates": 6, "panel_size": 3}),
    ]

    results = {}
    with timed("reposition_ab", episodes=args.episodes,
               arms=len(arms), workers=args.workers):
        for name, search in arms:
            results[name] = evaluate_scripted_parallel(
                seeds, workers=args.workers, search_kwargs=search, **TEACHER
            )
            print(f"  {name:<22}{results[name].avg_placement:.3f}", flush=True)

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

    print("\n4.500 = parity. Negative deltas are better.")
    print("Entry 47.10's pooled figure in the *old* world was -0.198 (t=-1.78);")
    print("that world is void (entry 71.4), so this replaces it rather than "
          "confirming it.")

    if args.json:
        args.json.write_text(json.dumps(
            {n: r.as_dict() | {"placements": r.placements}
             for n, r in results.items()}, indent=1))
        print(f"\nper-episode results: {args.json}")


if __name__ == "__main__":
    main()
