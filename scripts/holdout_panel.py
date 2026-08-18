"""Is the true field's advantage real, or in-sample? (doc 99 entry 139)

138.2 flagged the defect in its own headline number: the true-field arm
searches against the same seats the referee grades it against, while every
opponent-free surrogate is out-of-sample by construction. So "opponent-free
advice is worth 70%" may be measuring the advantage of being handed the answer
key rather than the value of scouting.

This grades every arm against a **held-out half of the lobby**. The living
opponents are split in two; the search sees half A, the referee scores against
half B, and no arm ever searches against a seat that grades it.

138.4 called the remaining 30% unexplained. This tests the one explanation
already on the table before looking for a subtler one.

Named outcomes, before the run:

* **A -- it was in-sample.** True-field advice collapses toward the surrogates
  once it cannot see its graders. Opponent-free advice is then worth ~100% of a
  fair baseline, and the typed path loses nothing by entering one board.
* **B -- partly.** The gap narrows but survives. Real opponents carry
  information beyond the seats being graded, and the honest figure is between
  70% and 100%.
* **C -- not at all.** The gap is unchanged, so 138.2's caveat was wrong and
  the true field's edge is something else entirely -- which would make 138.4's
  open question sharper rather than answered.

    .venv/bin/python scripts/holdout_panel.py --games 12 --states 80
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

REAL_PANEL = search_mod.opponent_panel
MIN_OPPONENTS = 4          # so each half holds at least two seats


def halves(match, player):
    """Split the living opponents into (searchable, held-out).

    Alternating over the strength-ordered field rather than cutting it in two,
    so neither half is systematically the stronger one -- a held-out half made
    entirely of weak seats would grade every proposal as fine.
    """
    field = REAL_PANEL(match, player, 99)
    return field[0::2], field[1::2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=12)
    parser.add_argument("--states", type=int, default=80)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    data = load_all()
    names = ("true half (held out)", "mirror (no opp info)",
             "true field (in-sample)")
    deltas: dict[str, list[float]] = {name: [] for name in names}
    fired: dict[str, int] = {name: 0 for name in names}
    agree: dict[str, int] = {name: 0 for name in names}
    used = [0]

    def visit(index, shim):
        searchable, held_out = halves(shim.match, shim.player)
        if len(searchable) < 2 or len(held_out) < 2:
            return
        used[0] += 1
        seeds = referee_seeds(index)

        # Every arm is graded on `held_out`, which only the in-sample arm has
        # searched against.
        arms = {
            "true half (held out)": (lambda m, p, size: searchable[:size],
                                     ADVISOR_PANEL),
            "mirror (no opp info)": (lambda m, p, size: [p], 1),
            "true field (in-sample)": (lambda m, p, size: held_out[:size],
                                       ADVISOR_PANEL),
        }
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
            deltas[name].append(referee(shim, swaps, seeds[:len(held_out)],
                                        panel=held_out))
        gold = {id(u) for u, _ in proposals["true half (held out)"]}
        for name, swaps in proposals.items():
            agree[name] += ({id(u) for u, _ in swaps} == gold)
        if used[0] % 10 == 0:
            print(f"  {used[0]} states", flush=True)

    sweep(data, args.games, args.states, args.seed, visit)
    n = used[0]

    base = deltas["true half (held out)"]
    truth = statistics.mean(base)
    print(f"\n{n} states with >= {MIN_OPPONENTS} living opponents; "
          f"all arms graded on the HELD-OUT half\n")
    print(f"{'search panel':>24}{'fires':>8}{'referee dv':>12}{'% of true':>11}"
          f"{'t vs true':>11}{'agrees':>8}")
    for name in names:
        mean = statistics.mean(deltas[name])
        _, t = paired_t([b - a for a, b in zip(base, deltas[name], strict=True)])
        share = f"{mean / truth:>10.0%}" if truth else f"{'--':>10}"
        print(f"{name:>24}{fired[name] / n:>8.0%}{mean:>+12.3f}{share}"
              f"{'--' if name.startswith('true half') else f'{t:+.2f}':>11}"
              f"{agree[name] / n:>8.0%}")


if __name__ == "__main__":
    main()
