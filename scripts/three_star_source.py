"""Who actually produces this engine's 3-stars? Doc 99 entry 101.

Entry 97.5 compared 3-star incidence in aggregate: 21.7% of engine seats
against a real challenger's 34.5%. Splitting it by cost tier turns a modest gap
into a structural one:

    cost 1   2.04% engine   16.39% real    8x too rare
    cost 2  19.29% engine   18.15% real    matches
    cost 3   0.33% engine   10.12% real   30x too rare
    cost 4-5    0% engine    1.00% real    never happens

The 2-cost rate is right and every other tier is missing. In real TFT a 1-cost
is the *easiest* thing to 3-star -- 30 copies in the pool against a 3-cost's
18, and the best shop odds at low level -- so a profile where 2-costs are the
common case and 1-costs are rare is inverted.

The hypothesis this tests: **the engine only 3-stars what a plan explicitly
targets.** `DEFAULT_FIELD` runs two `slowroll6` seats (`target_cost=2`), one
`hyperroll` (`target_cost=1`) and five seats that target nothing. If the
untargeted seats produce ~zero 3-stars while real players of every style
accumulate them incidentally, the defect is in how copies are held -- the sell
rule breaking up pairs before they can combine -- and not in the shop odds,
which 96.5 already exonerated.

Named outcomes, before the run:

* **A -- targeting is the whole story.** Untargeted seats produce ~0 3-stars;
  the tier profile is just `DEFAULT_FIELD`'s composition. The fix is the sell
  rule, and 97.7's per-tier placement comparison is confounded by archetype.
* **B -- untargeted seats do 3-star, just rarely.** Then targeting is a
  multiplier rather than a gate, and the shortfall is about volume.
* **C -- production is spread evenly across archetypes.** The hypothesis is
  wrong and something upstream of the policy is suppressing combines.

    .venv/bin/python scripts/three_star_source.py --games 100
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.loader import load_all  # noqa: E402
from engine.match import Match  # noqa: E402
from rl.opponents import DEFAULT_FIELD, GreedyPolicy  # noqa: E402


def probe(data, games: int, seed0: int = 0) -> dict:
    econs = [DEFAULT_FIELD[seat % len(DEFAULT_FIELD)] for seat in range(8)]

    # Per archetype: seats played, seats that ever held a 3-star, and the cost
    # tiers those 3-stars were. Peak copies held tells the pair-breaking story
    # even for seats that never finish a 3-star.
    holders: dict[str, Counter] = defaultdict(Counter)
    seats_played: Counter = Counter()
    seats_with_any: Counter = Counter()
    peak_copies: dict[str, list[int]] = defaultdict(list)

    for game in range(games):
        policies = [GreedyPolicy(seed=seat, econ=econs[seat]) for seat in range(8)]
        match = Match(data, policies, seed=seed0 + game)
        best_copies = dict.fromkeys(range(8), 0)
        seen: dict[int, set[int]] = defaultdict(set)

        while not match.finished:
            for player in match.living_players:
                counts: Counter = Counter()
                for unit in player.all_units:
                    counts[unit.champion.id] += unit.star_level ** 2
                    if unit.star_level == 3:
                        seen[player.player_id].add(unit.champion.cost)
                if counts:
                    best_copies[player.player_id] = max(
                        best_copies[player.player_id], max(counts.values())
                    )
            match.play_round()

        for seat in range(8):
            name = econs[seat].name
            seats_played[name] += 1
            peak_copies[name].append(best_copies[seat])
            if seen[seat]:
                seats_with_any[name] += 1
                for cost in seen[seat]:
                    holders[name][cost] += 1

    return {
        "holders": holders,
        "seats_played": seats_played,
        "seats_with_any": seats_with_any,
        "peak_copies": peak_copies,
        "targets": {e.name: e.target_cost for e in DEFAULT_FIELD},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=100)
    args = parser.parse_args()

    result = probe(load_all(), args.games)
    played = result["seats_played"]
    print(f"{args.games} games, mixed field, seats grouped by archetype\n")
    print(f"{'archetype':>12}{'targets':>9}{'seats':>7}{'any 3*':>9}"
          f"{'c1':>7}{'c2':>7}{'c3':>7}{'c4':>6}{'peak copies':>13}")
    for name in sorted(played):
        seats = played[name]
        row = result["holders"][name]
        peak = result["peak_copies"][name]
        target = result["targets"].get(name, 0)
        print(f"{name:>12}{target or '-':>9}{seats:>7}"
              f"{result['seats_with_any'][name] / seats:>9.1%}"
              f"{row[1] / seats:>7.1%}{row[2] / seats:>7.1%}"
              f"{row[3] / seats:>7.1%}{row[4] / seats:>6.1%}"
              f"{statistics.mean(peak):>13.2f}")

    untargeted = [n for n in played if not result["targets"].get(n, 0)]
    hit = sum(result["seats_with_any"][n] for n in untargeted)
    seats = sum(played[n] for n in untargeted)
    print(f"\nuntargeted archetypes ({', '.join(sorted(untargeted))}): "
          f"{hit}/{seats} seats reached any 3-star = {hit / seats:.2%}")
    print("real challenger, any 3-star: 34.5% of seats (doc 99 entry 97.5)")


if __name__ == "__main__":
    main()
