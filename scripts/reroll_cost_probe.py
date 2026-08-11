"""What does attempting the reroll line cost when it misses? (doc 99 entry 111)

Entry 111 measured that *holding* a cost-2 3-star is fine in this engine —
-0.121 against seats without one, the same sign reality shows. So `slowroll6`'s
+0.553 deficit (100) is not the payoff being under-rewarded, which is what 97.7
and 102.4 each proposed and each had withdrawn. The remaining place for it to
live is the **cost of attempting**: a seat that rolls its gold away and does not
hit is a seat with no interest, no levels and a weak board.

That decomposition is invisible in entry 111's split, because a `slowroll6` seat
that misses lands in the *other* arm alongside every `standard` seat.

Splits the mixed field by archetype and by whether the seat hit:

    hit rate       -- P(cost-2 3-star | archetype)
    placement | hit, and placement | miss, per archetype

If `slowroll6` hitters place well and missers place terribly, the line's
expected value is a lottery the engine prices differently from reality — and the
lever is the hit rate, not the payoff. If `slowroll6` hitters *also* place
badly, the payoff is worth less to that archetype than to a seat that stumbled
into a 3-star while playing standard, which is a different and more interesting
defect.

    .venv/bin/python scripts/reroll_cost_probe.py --games 400
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loader import load_all  # noqa: E402
from engine.match import Match  # noqa: E402
from rl.opponents import DEFAULT_FIELD, default_opponent  # noqa: E402

REROLL_COST = 2
THREE_STAR = 3


def welch(a: list[int], b: list[int]) -> tuple[float, float]:
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return 0.0, 0.0
    ma, mb = sum(a) / na, sum(b) / nb
    va = sum((x - ma) ** 2 for x in a) / (na - 1)
    vb = sum((x - mb) ** 2 for x in b) / (nb - 1)
    se = math.sqrt(va / na + vb / nb)
    return mb - ma, ((mb - ma) / se if se > 0 else 0.0)


def run(games: int, seed0: int = 0):
    data = load_all()
    # (archetype, hit) -> placements
    cells: dict[tuple[str, bool], list[int]] = defaultdict(list)
    # Seat index -> archetype name, fixed by DEFAULT_FIELD and stable across
    # games, so a seat's economy is known without inspecting the policy.
    names = [DEFAULT_FIELD[seat % len(DEFAULT_FIELD)].name for seat in range(8)]

    for game in range(games):
        match = Match(data, [default_opponent(seat) for seat in range(8)],
                      seed=seed0 + game)
        hit: dict[int, bool] = {}
        while not match.finished:
            for player in match.living_players:
                # Sticky: once a seat has held the 3-star it has "hit", even if
                # it later sells or dies with a different board. Reading only
                # the final board would score a seat that hit and then got
                # dismantled as a miss.
                if not hit.get(player.player_id):
                    hit[player.player_id] = any(
                        unit.star_level == THREE_STAR
                        and unit.champion.cost == REROLL_COST
                        for unit in player.board_units
                    )
            match.play_round()
        match._finalise_placements()
        for index, player in enumerate(match.players):
            placement = match.placements.get(player.player_id)
            if placement is None:
                continue
            cells[(names[index], hit.get(player.player_id, False))].append(
                placement)
    return cells


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=400)
    args = parser.parse_args()

    cells = run(args.games)
    archetypes = sorted({name for name, _ in cells})

    print(f"{args.games} games, DEFAULT_FIELD "
          f"({', '.join(sorted({e.name for e in DEFAULT_FIELD}))})\n")
    print(f"{'archetype':<12}{'hit rate':>10}{'place|hit':>11}"
          f"{'place|miss':>12}{'cost of miss':>14}{'t':>8}"
          f"{'n_hit':>8}{'n_miss':>8}")
    for name in archetypes:
        hits = cells.get((name, True), [])
        misses = cells.get((name, False), [])
        total = len(hits) + len(misses)
        if not total:
            continue
        rate = len(hits) / total
        delta, t = welch(hits, misses)
        mh = sum(hits) / len(hits) if hits else float("nan")
        mm = sum(misses) / len(misses) if misses else float("nan")
        print(f"{name:<12}{rate:>10.1%}{mh:>11.3f}{mm:>12.3f}"
              f"{delta:>+14.3f}{t:>+8.2f}{len(hits):>8}{len(misses):>8}")

    print("\n`cost of miss` is placement|miss - placement|hit; positive means "
          "missing is\nworse. Compare it across archetypes: if it is much "
          "larger for slowroll6 than\nfor standard, the line's downside is "
          "what the engine prices, not its payoff.")

    overall = {name: [p for (n, _), ps in cells.items() if n == name
                      for p in ps] for name in archetypes}
    print(f"\n{'archetype':<12}{'placement':>11}{'n':>8}")
    for name in archetypes:
        ps = overall[name]
        print(f"{name:<12}{sum(ps) / len(ps):>11.3f}{len(ps):>8}")


if __name__ == "__main__":
    main()
