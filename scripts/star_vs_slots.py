"""Does a smaller 3-star board beat a bigger 2-star one? (doc 99 entry 73.6)

The falsifiable claim behind the field residual. After entry 73 the reroll
archetypes hit 3-stars in **100%** of games and still placed ~0.9 worse than
the econ archetypes. Reroll trades board slots for star levels, so either:

* stars do not pay for slots here -- board size is **overweighted** relative to
  real TFT, which is a combat-fidelity defect; or
* the trade is priced correctly and reroll is simply a weaker line in this set.

In real TFT a six-unit board of 3-star 2-costs beats an eight-unit board of
2-star equivalents; that is the entire reason reroll comps exist. This fights
the two boards directly, which the whole-game measurements cannot isolate --
there, economy, items, augments and HP all vary at once.

**Champions are drawn from the same cost tier and the same roster for both
sides**, so the only differences are star level and unit count. Positions come
from `place_team`'s default layout for both, so neither side is hand-placed.

    .venv/bin/python scripts/star_vs_slots.py --trials 200
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.combat import CombatSimulator, place_team  # noqa: E402
from engine.hexgrid import Board  # noqa: E402
from engine.items import ItemRegistry  # noqa: E402
from engine.loader import load_all  # noqa: E402
from engine.unit import UnitInstance  # noqa: E402


def build(data, registry, champion_ids, star: int, team: int, board: Board):
    units = []
    for cid in champion_ids:
        unit = UnitInstance(data.champions[cid], star_level=star)
        units.append(unit)
    slots = _slots(len(units), team)
    place_team(units, slots, team=team, board=board)
    return units


def _slots(n: int, team: int) -> list[tuple[int, int]]:
    """Front-to-back rows, the same shape for both teams."""
    out: list[tuple[int, int]] = []
    row, col = 0, 0
    while len(out) < n:
        out.append((row, col))
        col += 1
        if col >= 7:
            col = 0
            row += 1
    return out


def one_fight(data, registry, pool_ids, small_n, small_star, big_n, big_star,
              rng, seed) -> int:
    """Return 1 if the small high-star board wins, 0 if it loses, -1 draw."""
    picks = rng.sample(pool_ids, max(small_n, big_n))
    board = Board()
    a = build(data, registry, picks[:small_n], small_star, 0, board)
    b = build(data, registry, picks[:big_n], big_star, 1, board)
    sim = CombatSimulator(a, b, data, seed=seed, board=board)
    result = sim.run()
    # `winner` is the authoritative outcome and is None for a draw; counting
    # survivors would re-derive it and could disagree with the engine.
    if result.winner == 0:
        return 1
    if result.winner == 1:
        return 0
    return -1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=200)
    parser.add_argument("--cost", type=int, default=2,
                        help="cost tier both boards are drawn from")
    args = parser.parse_args()

    data = load_all()
    registry = ItemRegistry(data.items, data.config.max_items_per_unit)
    pool = sorted(c.id for c in data.champions.values() if c.cost == args.cost)
    print(f"{len(pool)} champions at cost {args.cost}; "
          f"{args.trials} fights per matchup\n")

    matchups = [
        ("6x 3-star", 6, 3, "8x 2-star", 8, 2),
        ("6x 3-star", 6, 3, "9x 2-star", 9, 2),
        ("7x 3-star", 7, 3, "9x 2-star", 9, 2),
        # Controls: equal stars, so only the slot count differs. The bigger
        # board must win overwhelmingly or the harness is wrong.
        ("6x 2-star", 6, 2, "8x 2-star", 8, 2),
        # And equal slots, so only stars differ -- the 3-star side must win.
        ("8x 3-star", 8, 3, "8x 2-star", 8, 2),
    ]

    print(f"{'small board':>12}  vs {'big board':<12}{'small wins':>12}{'draws':>8}")
    for sname, sn, sstar, bname, bn, bstar in matchups:
        rng = random.Random(0)
        wins = draws = 0
        for trial in range(args.trials):
            out = one_fight(data, registry, pool, sn, sstar, bn, bstar,
                            rng, seed=trial)
            wins += out == 1
            draws += out == -1
        rate = wins / args.trials
        print(f"{sname:>12}  vs {bname:<12}{rate:>11.1%}{draws:>8}")

    print("\nReal TFT: a six-unit 3-star board beats an eight-unit 2-star one "
          "-- that is\nwhy reroll comps exist. A low win rate on the first row "
          "means board size is\noverweighted here, which is a combat defect "
          "rather than a strategy fact.")
    print("The two control rows must read ~0% and ~100% respectively; if they "
          "do not,\nthe harness is wrong and no row above should be read.")


if __name__ == "__main__":
    main()
