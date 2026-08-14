"""What *is* a real 3-cost reroll seat? (doc 99 entry 125)

124.3 made this the highest-value open question: 3-cost reroll is the
best-placing group in real TFT (4.01 challenger against a 4.50 field mean) at
10.1% incidence, and the engine produces 0.003. Every previous attempt treated
it as the 1-cost problem rescaled, and 124.1 showed it is not -- 3-cost hitters
end *lower* than 1-cost hitters (7.99 vs 8.34) and place *better*.

`SLOWROLL7` exists in `rl/opponents.py` (`target_cost=3`, `target_count=3`,
level 7 at 4-1, floor 50 from 4-1) and is deliberately not in `DEFAULT_FIELD`,
because 116.2 measured it reaching 27% of the real rate and making the profile
worse. That was a parameter guess. This describes the archetype from the sample
before another parameter is guessed at it -- lesson 27, applied before the fact
rather than after.

Questions, all of which change what a strategy should say:

* **How many** 3-cost 3-stars does a hitting seat hold? `target_count=3` is an
  assumption nobody has checked.
* At **what level**, and how tight is that distribution?
* What is the **rest of the board** -- does the archetype cap out on 3-costs, or
  pair them with 4-cost carries?
* **Which champions**, and is it a handful or the whole tier?

    .venv/bin/python scripts/cost3_archetype.py
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.reference_profile import champion_costs, unit_cost  # noqa: E402

REFERENCE = REPO_ROOT / "data" / "reference"


def seats(path: Path) -> list[dict]:
    return [p for m in json.loads(path.read_text())["matches"]
            for p in m["participants"]]


def profile(seat: dict, costs: dict[str, int]) -> dict:
    """Star levels by cost tier for one seat's final board."""
    stars: Counter = Counter()          # (cost, tier) -> count
    names: Counter = Counter()          # 3-star cost-3 champion ids
    resolved = 0
    for unit in seat.get("units", []):
        cost = unit_cost(unit, costs)
        if cost is None:
            continue                     # summons and PvE monsters (see 97.2)
        resolved += 1
        tier = unit.get("tier", 1)
        stars[(cost, tier)] += 1
        if cost == 3 and tier == 3:
            names[unit["character_id"]] += 1
    return {"stars": stars, "names": names, "units": resolved}


def report(path: Path, costs: dict[str, int]) -> None:
    rows = seats(path)
    hitters = []
    for seat in rows:
        prof = profile(seat, costs)
        n3 = sum(c for (cost, tier), c in prof["stars"].items()
                 if cost == 3 and tier == 3)
        if n3:
            hitters.append((seat, prof, n3))

    print(f"\n=== {path.name}: {len(hitters)} seats hold a 3-cost 3★ "
          f"({len(hitters) / len(rows):.1%} of {len(rows)}) ===")

    counts = Counter(n for _, _, n in hitters)
    print("\n  how many 3-cost 3★ per hitting seat:")
    for n in sorted(counts):
        share = counts[n] / len(hitters)
        place = statistics.mean(s["placement"] for s, _, k in hitters if k == n)
        level = statistics.mean(s["level"] for s, _, k in hitters if k == n)
        print(f"    {n}  {counts[n]:>5}  {share:>6.1%}   "
              f"level {level:.2f}   placement {place:.2f}   {'#' * round(40 * share)}")

    dist = Counter(s["level"] for s, _, _ in hitters)
    print("\n  level distribution:")
    for level in sorted(dist):
        print(f"    {level:>2}  {dist[level]:>5}  {dist[level]/len(hitters):>6.1%}  "
              f"{'#' * round(40 * dist[level] / len(hitters))}")

    print("\n  the rest of the board (mean units per hitting seat, by cost x star):")
    print(f"    {'cost':>6}{'1★':>8}{'2★':>8}{'3★':>8}")
    for cost in (1, 2, 3, 4, 5):
        cells = []
        for tier in (1, 2, 3):
            total = sum(p["stars"][(cost, tier)] for _, p, _ in hitters)
            cells.append(total / len(hitters))
        print(f"    {cost:>6}{cells[0]:>8.2f}{cells[1]:>8.2f}{cells[2]:>8.2f}")
    board = statistics.mean(p["units"] for _, p, _ in hitters)
    print(f"    board size {board:.2f} units")

    names: Counter = Counter()
    for _, prof, _ in hitters:
        names.update(prof["names"])
    print(f"\n  which champions ({len(names)} distinct 3-costs 3-starred):")
    for champ, n in names.most_common(8):
        print(f"    {champ:<28}{n:>5}  {n / len(hitters):>6.1%}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--band", choices=["challenger", "diamond", "both"],
                        default="challenger")
    args = parser.parse_args()
    costs = champion_costs()
    bands = ["challenger", "diamond"] if args.band == "both" else [args.band]
    for band in bands:
        found = sorted(REFERENCE.glob(f"matches_{band}_*.json"))
        if not found:
            print(f"no {band} sample in {REFERENCE}")
            continue
        report(found[-1], costs)


if __name__ == "__main__":
    main()
