"""Re-score every recorded run under LP as well as average placement.

Doc 99 entry 31.3 found a PPO arm that is a null on average placement while
clearly improving the tails. Average placement has been this project's primary
metric since doc 03 sec 4, chosen before any policy existed whose distribution
shape differed from its peers.

Every run stored its full placement distribution, so the whole back catalogue
can be re-scored for free. The question this answers: **does any past verdict
flip under LP?** If several do, the back catalogue needs reading with care; if
none do, the metric change is safe and 31.3 is an isolated case.

    python scripts/rescore.py
    python scripts/rescore.py --sort lp
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rl.evaluate import EvalResult  # noqa: E402

# Which line of a run log to score. Cloning-only runs report "after cloning";
# everything else reports a final "trained" evaluation. Taking the *last*
# match means a run that did both is scored on its final policy.
MARKERS = ("trained: episodes", "after dagger:", "after cloning:")


def scored(path: Path) -> tuple[str, EvalResult] | None:
    lines = path.read_text(errors="ignore").splitlines()
    best: tuple[int, str, dict] | None = None
    for index, line in enumerate(lines):
        for marker in MARKERS:
            if marker in line and index + 1 < len(lines):
                counts = {
                    int(k): int(v)
                    for k, v in re.findall(r"(\d):(\d+)", lines[index + 1])
                }
                if counts:
                    best = (index, marker.split(":")[0], counts)
    if best is None:
        return None
    _, label, counts = best
    placements = [p for p, n in sorted(counts.items()) for _ in range(n)]
    return label, EvalResult(episodes=len(placements), placements=placements)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=Path("runs"))
    parser.add_argument("--sort", choices=["name", "place", "lp"], default="place")
    args = parser.parse_args()

    rows = []
    for log in sorted(args.runs.glob("*.log")):
        entry = scored(log)
        if entry is None:
            continue
        label, result = entry
        if result.episodes < 100:
            continue  # too few episodes for either interval to mean anything
        rows.append((log.stem, label, result))

    if not rows:
        print("no scoreable runs found")
        return

    key = {
        "name": lambda r: r[0],
        "place": lambda r: r[2].avg_placement,
        "lp": lambda r: -r[2].avg_lp,
    }[args.sort]
    rows.sort(key=key)

    print(f"{'run':<20}{'stage':<9}{'n':>5}{'place':>8}{'+/-':>7}"
          f"{'LP':>8}{'+/-':>6}{'1st':>7}{'top4':>7}")
    for name, label, r in rows:
        print(
            f"{name:<20}{label:<9}{r.episodes:>5}{r.avg_placement:>8.3f}"
            f"{r.ci95:>7.3f}{r.avg_lp:>8.2f}{r.lp_ci95:>6.2f}"
            f"{r.win_rate:>7.1%}{r.top4_rate:>7.1%}"
        )

    print("\nRanking by placement vs by LP -- disagreements are what matter:")
    by_place = [n for n, _, _ in sorted(rows, key=lambda r: r[2].avg_placement)]
    by_lp = [n for n, _, _ in sorted(rows, key=lambda r: -r[2].avg_lp)]
    flips = [
        (n, by_place.index(n), by_lp.index(n))
        for n in by_place
        if by_place.index(n) != by_lp.index(n)
    ]
    if not flips:
        print("  none -- the two metrics rank every recorded run identically")
    else:
        for name, place_rank, lp_rank in flips:
            print(f"  {name:<20} placement #{place_rank + 1:<3} LP #{lp_rank + 1}")


if __name__ == "__main__":
    main()
