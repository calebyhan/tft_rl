"""Is `standard`'s level curve tuned, or just plausible? (doc 99 entry 88)

The last untested economy lever. 84 settled archetype *selection* (`standard`
best, `fast8` indistinguishable), 87.1 settled roll floors (not a lever), 86
fixed reroll targeting (which `standard` does not use). What has never been
measured is the level curve inside `standard` itself -- it was hand-written
from real TFT practice in entry 74 and adopted on the strength of the +0.610
that having *any* economy bought.

Economy is the one improvement class measured to transmit to the clone (89%,
entry 75), unlike positional improvements (0%, entry 79), so a gain here should
reach the agent.

Teacher-side: no training seed, so entry 83's 0.14 clone noise floor does not
apply and arms are paired on shared episode seeds.

    .venv/bin/python scripts/level_curve_ab.py --episodes 300 --workers 10
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
from rl.opponents import STANDARD  # noqa: E402
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


def curve(**targets):
    return dataclasses.replace(STANDARD, level_targets=dict(targets))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=300)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    seeds = list(range(args.episodes))
    before = source_fingerprint()
    print(f"source fingerprint: {before}")
    print(f"incumbent curve: {STANDARD.level_targets}")

    arms = [
        ("incumbent", STANDARD),
        # Reach 8 and 9 a stage earlier. `fast8` already tests an aggressive
        # whole archetype (4.337, t=+1.05 vs standard); this moves only the
        # late curve, keeping standard's early game.
        ("late-push", curve(**{"2-5": 5, "3-2": 6, "4-1": 7, "4-4": 8,
                               "5-2": 9, "6-1": 10})),
        # Hold 7 longer, bank interest, then jump. The opposite bet.
        ("late-hold", curve(**{"2-5": 5, "3-2": 6, "4-1": 7, "5-1": 8,
                               "5-6": 9, "6-5": 10})),
        # Reach 6 a round earlier: entry 70 verified the xp table, so this is
        # a real tempo trade rather than a free gain.
        ("early-6", curve(**{"2-4": 5, "3-1": 6, "4-1": 7, "4-5": 8,
                             "5-5": 9, "6-3": 10})),
        # Never level past 8. Tests whether 9 and 10 pay for themselves at all.
        ("cap-8", curve(**{"2-5": 5, "3-2": 6, "4-1": 7, "4-5": 8})),
    ]

    results = {}
    with timed("level_curve_ab", episodes=args.episodes,
               arms=len(arms), workers=args.workers):
        for name, econ in arms:
            results[name] = evaluate_scripted_parallel(
                seeds, workers=args.workers, econ=econ, **TEACHER
            )
            print(f"  {name:<12}{results[name].avg_placement:.3f}", flush=True)

    if source_fingerprint() != before:
        print("!! SOURCE CHANGED MID-RUN -- discard (doc 99 entry 68.4)")

    base = results["incumbent"]
    print(f"\n{'arm':<12}{'place':>8}{'ci95':>7}{'LP':>8}{'1st':>7}{'top4':>7}"
          f"{'8th':>7}{'vs incumbent':>22}")
    for name, r in results.items():
        last = Counter(r.placements)[8] / len(r.placements)
        delta = "" if name == "incumbent" else "%+.3f  t=%+.2f" % paired_t(
            base.placements, r.placements)
        print(f"{name:<12}{r.avg_placement:>8.3f}{r.ci95:>7.3f}{r.avg_lp:>8.2f}"
              f"{r.win_rate:>7.1%}{r.top4_rate:>7.1%}{last:>7.1%}{delta:>22}")

    print("\nIncumbent must reproduce 4.213 (entry 86.3); if it misses, "
          "something else\nmoved and no row here should be read.")
    print("This is the last untested economy lever. Nothing here means (b) is "
          "exhausted\nand the imitation ceiling (entry 81) is the only "
          "remaining constraint.")

    if args.json:
        args.json.write_text(json.dumps(
            {n: r.as_dict() | {"placements": r.placements}
             for n, r in results.items()}, indent=1))
        print(f"\nper-episode results: {args.json}")


if __name__ == "__main__":
    main()
