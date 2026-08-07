"""Can the teacher's placement rule be improved directly? (doc 99 entry 80)

Entry 79.9 established that positional *search* does not transmit: the teacher
gains 0.277 (t=-2.13) and the clone gains nothing, because the observation
cannot express which hex is better. Search is also expensive -- ~4x per game.

A placement *rule* has neither problem. It is a deterministic function of the
board, so it costs nothing at inference and a clone can follow it; PLACE match
against the plain econ teacher is already 78.8% (79.2), against 45.5% for the
search teacher's moves.

The incumbent sorts empty slots by depth and takes an end. That sort is
**stable**, so within the chosen row ties break by slot index and every unit
lands on the same flank -- the board clumps into one corner. Two alternatives:

* `centre` -- fill the chosen row from the middle outward. Standard TFT
  practice puts the front line in the centre so it engages first.
* `spread` -- pick the column furthest from any already-fielded unit. A clumped
  board is what area abilities and a single focused enemy carry punish.

Both keep the melee-front / ranged-back split and the `corner_carry` rule, so
the only thing varying is the *column* chosen within the target row.

Reading it: this is the cheap half of 79.6's open list. If a rule pays, it pays
at inference for free and should transmit; if none does, position is worth less
than 78 and 79 imply outside of search.

    .venv/bin/python scripts/place_rule_ab.py --episodes 300 --workers 10
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
    """Digest of what the spawn workers re-import from disk (entry 68.4)."""
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

    rules = ["rows", "centre", "spread"]
    results = {}
    with timed("place_rule_ab", episodes=args.episodes,
               arms=len(rules), workers=args.workers):
        for rule in rules:
            results[rule] = evaluate_scripted_parallel(
                seeds, workers=args.workers, place_rule=rule, **TEACHER
            )
            print(f"  {rule:<10}{results[rule].avg_placement:.3f}", flush=True)

    after = source_fingerprint()
    if after != before:
        print(f"\n!! SOURCE CHANGED MID-RUN ({before} -> {after}) -- discard "
              "this run (doc 99 entry 68.4).")

    base = results["rows"]
    print(f"\n{'rule':<10}{'place':>8}{'ci95':>7}{'LP':>8}{'1st':>7}{'top4':>7}"
          f"{'8th':>7}{'vs rows':>22}")
    for rule, r in results.items():
        last = Counter(r.placements)[8] / len(r.placements)
        if rule == "rows":
            delta = ""
        else:
            mean, t = paired_t(base.placements, r.placements)
            delta = f"{mean:+.3f}  t={t:+.2f}"
        print(f"{rule:<10}{r.avg_placement:>8.3f}{r.ci95:>7.3f}{r.avg_lp:>8.2f}"
              f"{r.win_rate:>7.1%}{r.top4_rate:>7.1%}{last:>7.1%}{delta:>22}")

    print("\n`rows` is the incumbent and must reproduce 4.213 (entry 78.1); if "
          "it does not,\nsomething else moved and no row here should be read.")
    print("Negative deltas are better. The search teacher is 3.937 (79.7) at "
          "~4x the\ncost per game and does not transmit (79.9) -- that is the "
          "bar a free rule is\nbeing compared against, not 4.500.")

    if args.json:
        args.json.write_text(json.dumps(
            {n: r.as_dict() | {"placements": r.placements}
             for n, r in results.items()}, indent=1))
        print(f"\nper-episode results: {args.json}")


if __name__ == "__main__":
    main()
