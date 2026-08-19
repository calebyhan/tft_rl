"""Is the true field's edge the shared champion pool? (doc 99 entry 140)

139.2 eliminated three explanations for the 30% that opponent-free board advice
gives up (simulation volume, breadth, in-sample advantage) and named one it did
not test: real lobby opponents draw from the **same shared pool** as the
player, so their boards are *anti-correlated* with the player's own. A copy the
player holds is a copy no opponent can hold. No foreign board carries that.

There is already a prior against it. The mirror panel is *maximally* correlated
with the hero (it is the hero's board) and a library panel is essentially
*un*correlated, and 138.1 measured both at 70-71%. If the pool relationship
drove the gap, those two should not have matched. What neither is, is
**anti**-correlated -- which is what this builds.

Power is held roughly fixed first (board size within +/-1 of the hero's, the
axis 138.1 found mattered), and overlap is chosen within that band, so the arms
differ in champion overlap rather than in strength.

Named outcomes, before the run:

* **A -- the pool is the mechanism.** Low-overlap panels recover toward the
  true field and high-overlap panels sit at the surrogate floor. Then advice
  can be improved with no scouting at all, by sampling opponents from the pool
  the player is not holding.
* **B -- partial.** Low beats high, neither reaches the true field. Pool
  structure is one ingredient among others.
* **C -- not the mechanism.** Low and high overlap score alike, as the mirror
  vs library prior suggests. Then four explanations are eliminated and the
  remainder is something none of the obvious candidates covers.

    .venv/bin/python scripts/pool_overlap.py --games 12 --states 80
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.loader import load_all  # noqa: E402
from rl import search as search_mod  # noqa: E402
from rl.search import best_board  # noqa: E402
from scripts.search_budget import (  # noqa: E402
    ADVISOR_PANEL,
    MARGIN_PER_FIGHT,
    paired_t,
    referee,
    referee_seeds,
    sweep,
)
from scripts.synthetic_panel import harvest  # noqa: E402

REAL_PANEL = search_mod.opponent_panel


def champions_of(seat) -> set[str]:
    return {unit.champion.id for unit in seat.board.values()}


def overlap_panel(library, *, lowest: bool):
    """Panel chosen by champion overlap with the player, power held fixed.

    Board size is matched first (138.1 found power level is the one thing a
    panel must get right), and overlap ranks only within that band. Otherwise
    "low overlap" would quietly select for boards of a different strength and
    measure that instead.
    """
    pool = [seat for seats in library.values() for seat in seats]

    def panel(match, player, size):
        want = len(player.board)
        mine = champions_of(player)
        band = [p for p in pool if abs(len(p.board) - want) <= 1 and p is not player]
        if len(band) < size:
            band = [p for p in pool if p is not player]
        band.sort(key=lambda p: (len(champions_of(p) & mine), -len(p.board)),
                  reverse=not lowest)
        return band[:size]
    return panel


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=12)
    parser.add_argument("--states", type=int, default=80)
    parser.add_argument("--library", type=int, default=24)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    data = load_all()
    library = harvest(data, args.library)

    arms = {
        "true field (shipped)": (REAL_PANEL, ADVISOR_PANEL),
        "mirror (no opp info)": (lambda m, p, size: [p], 1),
        "library, low overlap": (overlap_panel(library, lowest=True), ADVISOR_PANEL),
        "library, high overlap": (overlap_panel(library, lowest=False), ADVISOR_PANEL),
    }
    deltas: dict[str, list[float]] = {name: [] for name in arms}
    fired: dict[str, int] = {name: 0 for name in arms}
    agree: dict[str, int] = {name: 0 for name in arms}
    shared: list[float] = []

    def visit(index, shim):
        seeds = referee_seeds(index)
        mine = champions_of(shim.player)
        field = REAL_PANEL(shim.match, shim.player, ADVISOR_PANEL)
        if field and mine:
            # How anti-correlated the *real* field actually is, which decides
            # whether there was room for this mechanism to matter at all.
            shared.append(statistics.mean(
                len(champions_of(p) & mine) / len(mine) for p in field))
        proposals = {}
        for name, (panel_fn, width) in arms.items():
            search_mod.opponent_panel = panel_fn
            try:
                swaps = best_board(shim, random.Random(index),
                                   panel_size=ADVISOR_PANEL,
                                   margin=MARGIN_PER_FIGHT * width) or []
            finally:
                search_mod.opponent_panel = REAL_PANEL
            proposals[name] = swaps
            fired[name] += bool(swaps)
            deltas[name].append(referee(shim, swaps, seeds))
        gold = {id(u) for u, _ in proposals["true field (shipped)"]}
        for name, swaps in proposals.items():
            agree[name] += ({id(u) for u, _ in swaps} == gold)
        if (index + 1) % 10 == 0:
            print(f"  {index + 1} states", flush=True)

    n = sweep(data, args.games, args.states, args.seed, visit)

    # The load-bearing comparison is low *against high*, not either against the
    # true field: outcome B and outcome C differ only in whether this gap is
    # real. Quoting the two arms' distances from a third arm cannot settle it.
    low, high = deltas["library, low overlap"], deltas["library, high overlap"]
    gap, gap_t = paired_t([lo - hi for hi, lo in zip(high, low, strict=True)])

    base = deltas["true field (shipped)"]
    truth = statistics.mean(base)
    print(f"\n{n} states; every arm graded against the TRUE field")
    if shared:
        print(f"real field shares {statistics.mean(shared):.1%} of the player's "
              f"champions on average\n")
    print(f"{'search panel':>23}{'fires':>8}{'referee dv':>12}{'% of true':>11}"
          f"{'t vs true':>11}{'agrees':>8}")
    for name in arms:
        mean = statistics.mean(deltas[name])
        _, t = paired_t([b - a for a, b in zip(base, deltas[name], strict=True)])
        share = f"{mean / truth:>10.0%}" if truth else f"{'--':>10}"
        print(f"{name:>23}{fired[name] / n:>8.0%}{mean:>+12.3f}{share}"
              f"{'--' if name.startswith('true') else f'{t:+.2f}':>11}"
              f"{agree[name] / n:>8.0%}")
    print(f"\nlow overlap - high overlap: {gap:+.3f} survivors/fight, "
          f"t {gap_t:+.2f}, n={n}")


if __name__ == "__main__":
    main()
