"""Do real 1-cost 3-stars and level 8.26 belong to the *same* seat? (entry 124)

Entries 119-123 chased a target stated as "0.271 1-cost 3-stars at level 8.26,
placing 4.43". Both numbers are **field averages over every seat**, and they
have been treated throughout as a joint property of one seat -- the "real
corner" the engine could not reach.

That is exactly the mistake lesson 27 names, applied to the reference side
instead of the engine side: a total is a sum over a mechanism that may not be
uniform. If the 3-stars come from seats at level 7 and the 8.26 comes from
seats with none, there is no corner, the engine's frontier is not anomalous,
and 119.4 was right for the third time.

Named outcomes, before the run:

* **A -- there is no corner.** Seats holding a 1-cost 3-star sit well below
  8.26. The target was an averaging artefact and the whole 119-123 arc was
  chasing a number no real player achieves.
* **B -- the corner is real.** Seats holding a 1-cost 3-star are at or near
  8.26 and place well. Then real TFT genuinely does both and the engine's
  economy differs structurally, as 123.4 concluded.
* **C -- in between.** They sit above the reroll archetype's engine level
  (6.4-7.9) but below 8.26. The gap is then quantitative, and this says by how
  much.

`gold_left` is the only gold field Riot's match payload carries -- there is no
per-round trace -- so 123.5's interest check cannot be run against this data at
all. This asks the question that *can* be answered with it.

    .venv/bin/python scripts/reroll_seat_profile.py
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.reference_profile import champion_costs, unit_cost  # noqa: E402

REFERENCE = REPO_ROOT / "data" / "reference"


def seats(path: Path) -> list[dict]:
    payload = json.loads(path.read_text())
    return [p for m in payload["matches"] for p in m["participants"]]


def three_stars_by_cost(units: list[dict], costs: dict[str, int]) -> Counter:
    """Cost tiers this seat holds a 3-star in. `tier` is Riot's star level."""
    found: Counter = Counter()
    for unit in units:
        if unit.get("tier") == 3:
            cost = unit_cost(unit, costs)
            if cost is not None:
                found[cost] += 1
    return found


def report(path: Path, costs: dict[str, int]) -> None:
    rows = seats(path)
    groups: dict[str, list[dict]] = defaultdict(list)
    for seat in rows:
        found = three_stars_by_cost(seat.get("units", []), costs)
        groups["all"].append(seat)
        groups["c1 3★" if found[1] else "no c1 3★"].append(seat)
        if found[3]:
            groups["c3 3★"].append(seat)
        if not found:
            groups["no 3★ at all"].append(seat)

    print(f"\n=== {path.name} ({len(rows)} seats) ===")
    print(f"{'group':>14}{'seats':>8}{'share':>8}{'level':>8}"
          f"{'placement':>11}{'gold left':>11}{'last round':>12}")
    for name in ("all", "c1 3★", "no c1 3★", "c3 3★", "no 3★ at all"):
        group = groups.get(name, [])
        if not group:
            continue
        print(f"{name:>14}{len(group):>8}{len(group) / len(rows):>8.1%}"
              f"{statistics.mean(s['level'] for s in group):>8.2f}"
              f"{statistics.mean(s['placement'] for s in group):>11.2f}"
              f"{statistics.mean(s['gold_left'] for s in group):>11.1f}"
              f"{statistics.mean(s['last_round'] for s in group):>12.1f}")

    # The level distribution of the seats that actually hit, which is the
    # question a mean cannot answer.
    hitters = groups.get("c1 3★", [])
    if hitters:
        dist = Counter(s["level"] for s in hitters)
        total = len(hitters)
        print("\n  level distribution of seats holding a 1-cost 3★:")
        for level in sorted(dist):
            bar = "#" * round(40 * dist[level] / total)
            print(f"    {level:>2}  {dist[level]:>4}  {dist[level]/total:>5.1%}  {bar}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--band", choices=["challenger", "diamond", "both"],
                        default="both")
    args = parser.parse_args()

    costs = champion_costs()
    names = (["challenger", "diamond"] if args.band == "both" else [args.band])
    for band in names:
        matches = sorted(REFERENCE.glob(f"matches_{band}_*.json"))
        if not matches:
            print(f"no {band} sample in {REFERENCE}")
            continue
        report(matches[-1], costs)


if __name__ == "__main__":
    main()
