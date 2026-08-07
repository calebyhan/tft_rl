"""Is slowroll's floor the reason it never rolls? (doc 99 entry 86)

Entry 85 established the arithmetic: 58 rolls are needed for the 9 copies a
2-cost 3-star takes, and `slowroll6` performs **30-33 per game** and holds a
maximum of **0** copies of anything. It is not the action budget (85.2, refuted
at budget 400) and not the buy/sell spread (zero, refuted).

85.3 located the constraint as the *window*: `roll_floors={"3-2": 50}` cannot
fire until gold reaches 50, which the plan's own `level_targets` delay by
spending on XP to reach level 6 at 3-2. Gold hits 50 only at **4-1**, and the
seat is dead by **5-2** -- about 8 rounds of rolling where a real slow-roll has
roughly double.

If that reading is right, an **earlier or lower floor** should produce more
rolls and better placement. If placement does not move, the plan is not the
binding constraint and reroll is mispriced somewhere the config cannot reach --
which is the fidelity question 85.5 could not judge.

Teacher-side only: no training seed, so entry 83's 0.14 clone noise floor does
not apply and arms are paired on shared episode seeds.

    .venv/bin/python scripts/reroll_floor_ab.py --episodes 300 --workers 10
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rl.evaluate import evaluate_scripted_parallel  # noqa: E402
from rl.opponents import SLOWROLL6, STANDARD  # noqa: E402
from rl.timing import timed  # noqa: E402

TEACHER = {
    "sell_bench": True,
    "buy_synergy": True,
    "match_items": True,
    "corner_carry": True,
}


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    for name in ("rl/evaluate.py", "rl/opponents.py"):
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


def floors(**mapping) -> object:
    """`SLOWROLL6` with a different roll plan, everything else identical."""
    return dataclasses.replace(SLOWROLL6, roll_floors=dict(mapping))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=300)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    seeds = list(range(args.episodes))
    before = source_fingerprint()
    print(f"source fingerprint: {before}")

    arms: list[tuple[str, object]] = [
        ("standard (control)", STANDARD),
        ("slowroll6 3-2@50", SLOWROLL6),
        # Lower floor: same start, more of each round's gold spent rolling.
        ("slowroll6 3-2@30", floors(**{"3-2": 30})),
        # Earlier start: rolling begins before the 50-gold bank exists.
        ("slowroll6 2-5@20", floors(**{"2-5": 20})),
        # The extreme -- roll everything from 3-2. Not a sane plan (it forfeits
        # interest entirely), included as the upper bound on what *more rolls*
        # can buy. If even this does not move placement, the config is not the
        # constraint.
        ("slowroll6 3-2@0", floors(**{"3-2": 0})),
    ]

    results = {}
    with timed("reroll_floor_ab", episodes=args.episodes,
               arms=len(arms), workers=args.workers):
        for name, econ in arms:
            results[name] = evaluate_scripted_parallel(
                seeds, workers=args.workers, econ=econ, **TEACHER
            )
            print(f"  {name:<22}{results[name].avg_placement:.3f}", flush=True)

    if source_fingerprint() != before:
        print("!! SOURCE CHANGED MID-RUN -- discard (doc 99 entry 68.4)")

    base = results["slowroll6 3-2@50"]
    print(f"\n{'arm':<22}{'place':>8}{'ci95':>7}{'LP':>8}{'1st':>7}{'top4':>7}"
          f"{'8th':>7}{'vs incumbent slowroll':>24}")
    for name, r in results.items():
        last = Counter(r.placements)[8] / len(r.placements)
        if name == "slowroll6 3-2@50":
            delta = ""
        else:
            mean, t = paired_t(base.placements, r.placements)
            delta = f"{mean:+.3f}  t={t:+.2f}"
        print(f"{name:<22}{r.avg_placement:>8.3f}{r.ci95:>7.3f}{r.avg_lp:>8.2f}"
              f"{r.win_rate:>7.1%}{r.top4_rate:>7.1%}{last:>7.1%}{delta:>24}")

    print("\nControl must reproduce 4.213 and the incumbent 4.867 (entry 86.3, "
          "which\nsuperseded 84's pre-targeting 6.077); if either misses, "
          "something else moved\nand no row here should be read.")
    print("A floor that moves placement means the *plan* starved it (85.3). "
          "No movement\nacross any floor, including 0, means the config is not "
          "the constraint.")

    if args.json:
        args.json.write_text(json.dumps(
            {n: r.as_dict() | {"placements": r.placements}
             for n, r in results.items()}, indent=1))
        print(f"\nper-episode results: {args.json}")


if __name__ == "__main__":
    main()
