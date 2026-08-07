"""Is the mixed field balanced, or are two of its archetypes free wins?

Doc 99 entry 72.3's open item. `slowroll6` and `hyperroll` are catastrophic in
the *agent* seat (+1.173, +1.723) while sitting in two of the seven opponent
seats. If they also place badly inside a game, the default field is a lobby
containing two weak seats, which flatters every agent number measured against
it -- the exact failure entry 72.1 just found in the old field.

Eight seats, `GreedyPolicy` throughout, no agent: the seats differ only by
archetype, so mean placement per archetype is directly comparable and 4.500 is
parity by arithmetic.

    .venv/bin/python scripts/field_check.py --games 200
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loader import load_all  # noqa: E402
from engine.match import Match  # noqa: E402
from rl.opponents import DEFAULT_FIELD, GreedyPolicy  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=200)
    args = parser.parse_args()

    data = load_all()
    by_archetype: dict[str, list[int]] = defaultdict(list)
    by_seat: dict[int, list[int]] = defaultdict(list)

    for game in range(args.games):
        policies = [
            GreedyPolicy(seed=seat, econ=DEFAULT_FIELD[seat])
            for seat in range(8)
        ]
        result = Match(data, policies, seed=game).run()
        for seat in range(8):
            placement = result.placements[seat]
            by_archetype[DEFAULT_FIELD[seat].name].append(placement)
            by_seat[seat].append(placement)

    print(f"{args.games} games, 8 seats, no agent. 4.500 = parity.\n")
    print(f"{'archetype':<12}{'seats':>7}{'place':>8}{'sd':>7}{'top4':>8}{'8th':>7}")
    for name, places in sorted(by_archetype.items(), key=lambda kv: statistics.mean(kv[1])):
        seats = sum(1 for s in DEFAULT_FIELD if s.name == name)
        top4 = sum(1 for p in places if p <= 4) / len(places)
        last = sum(1 for p in places if p == 8) / len(places)
        sd = statistics.stdev(places) if len(places) > 1 else 0.0
        print(f"{name:<12}{seats:>7}{statistics.mean(places):>8.3f}{sd:>7.2f}"
              f"{top4:>8.1%}{last:>7.1%}")

    print(f"\n{'seat':<12}{'archetype':>12}{'place':>8}")
    for seat in range(8):
        print(f"{seat:<12}{DEFAULT_FIELD[seat].name:>12}"
              f"{statistics.mean(by_seat[seat]):>8.3f}")

    spread = (max(statistics.mean(v) for v in by_archetype.values())
              - min(statistics.mean(v) for v in by_archetype.values()))
    print(f"\narchetype spread: {spread:.3f} placement.")
    print("A large spread means the field is not a fair lobby: the weak "
          "archetypes\nare free wins that inflate every agent number measured "
          "against it.")


if __name__ == "__main__":
    main()
