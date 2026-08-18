"""Does board advice need to know the *opponents*? (doc 99 entry 137)

This gates the typed path, which 136.4 established is the only live-play route
this project will take. `board_advice` picks a board by simulating fights
against a panel of opponents — so as written a person must enter **eight
boards** per round, which nobody will do. If the same advice survives a panel
built from no opponent information at all, they enter **one**: their own.

136.2 makes this a real question rather than a formality: widening the panel
from 2 to 4 moved both the firing rate (62% -> 51%) and the value, so *who* is
simulated against demonstrably matters.

Arms differ only in the panel the **search** sees. Every proposal is graded by
the same referee against the **true** opponents, because the true opponents are
what the player actually fights. A surrogate panel that flatters itself would
otherwise score well by being wrong consistently.

Named outcomes, before the run:

* **A -- mirror is enough.** Advice from a self-mirror panel is worth about as
  much as advice from the real field. The reader only ever needs the player's
  own half of the screen, and the typed path is practical.
* **B -- one opponent is enough, mirror is not.** Then scouting a single board
  is the requirement: more typing than A, far less than eight.
* **C -- the field is required.** Advice degrades badly without real
  opponents. The typed path costs eight boards a round, and is likely dead in
  the form it has now.

    .venv/bin/python scripts/panel_identity.py --games 12 --states 80
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
import time
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

# The real `opponent_panel`, captured before anything is patched. The referee
# must keep using it: the whole question is how a surrogate-panel proposal
# fares against the *true* field, so grading it against the surrogate would
# measure nothing.
REAL_PANEL = search_mod.opponent_panel


def true_panel(match, player, size):
    return REAL_PANEL(match, player, size)


def mirror_panel(match, player, size):
    """Fight a copy of your own board. Requires zero opponent information.

    `clone_board(match, player, 1)` mirrors the player's own board onto the
    enemy half, so the hero itself serves as the panel member with no new
    object. `best_board` clones team 0 (with its candidate swaps applied and
    restored) before cloning team 1, so the mirror is always the *unmodified*
    board -- a fixed reference, not a moving one.
    """
    return [player]


def one_opponent_panel(match, player, size):
    """The single strongest living opponent -- one board to scout, not seven."""
    return REAL_PANEL(match, player, 1)


# (panel function, trials). **Fight count is a confound and is controlled
# here.** `best_board` runs `panel_size x trials` combats, so a one-member
# panel at the default `trials=3` simulates 3 fights against the true field's
# 12. The first run of this probe did exactly that, and some of the gap it
# showed was simulation volume rather than opponent knowledge. The "fights
# matched" arms spend the same 12 combats on a single surrogate opponent.
TRUE_TRIALS = 3
MATCHED_TRIALS = TRUE_TRIALS * ADVISOR_PANEL

ARMS = {
    "true field (shipped)": (true_panel, TRUE_TRIALS),
    "mirror (no opp info)": (mirror_panel, TRUE_TRIALS),
    "one opponent": (one_opponent_panel, TRUE_TRIALS),
    "mirror, fights matched": (mirror_panel, MATCHED_TRIALS),
    "one opp, fights matched": (one_opponent_panel, MATCHED_TRIALS),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=12)
    parser.add_argument("--states", type=int, default=80)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    data = load_all()
    deltas: dict[str, list[float]] = {name: [] for name in ARMS}
    secs: dict[str, list[float]] = {name: [] for name in ARMS}
    fired: dict[str, int] = {name: 0 for name in ARMS}
    agree: dict[str, int] = {name: 0 for name in ARMS}

    def visit(index, shim):
        seeds = referee_seeds(index)
        proposals = {}
        for name, (panel_fn, trials) in ARMS.items():
            # A surrogate panel of one still has to keep the per-fight firing
            # threshold it would have had (136.3), or the arms differ in when
            # they fire as well as in what they see.
            size = 1 if panel_fn is not true_panel else ADVISOR_PANEL
            search_mod.opponent_panel = panel_fn
            try:
                rng = random.Random(index)
                start = time.perf_counter()
                swaps = best_board(shim, rng, panel_size=ADVISOR_PANEL,
                                   trials=trials,
                                   margin=MARGIN_PER_FIGHT * size) or []
            finally:
                search_mod.opponent_panel = REAL_PANEL
            secs[name].append(time.perf_counter() - start)
            proposals[name] = swaps
            fired[name] += bool(swaps)
            deltas[name].append(referee(shim, swaps, seeds))
        gold = {id(u) for u, _ in proposals["true field (shipped)"]}
        for name, swaps in proposals.items():
            agree[name] += ({id(u) for u, _ in swaps} == gold)
        if (index + 1) % 10 == 0:
            print(f"  {index + 1} states", flush=True)

    n = sweep(data, args.games, args.states, args.seed, visit)

    base = deltas["true field (shipped)"]
    truth = statistics.mean(base)
    print(f"\n{n} states; every arm graded against the TRUE field\n")
    print(f"{'search panel':>25}{'fires':>8}{'referee dv':>12}{'% of true':>11}"
          f"{'t vs true':>11}{'agrees':>8}{'sec/call':>10}")
    for name in ARMS:
        mean = statistics.mean(deltas[name])
        _, t = paired_t([b - a for a, b in zip(base, deltas[name], strict=True)])
        share = f"{mean / truth:>10.0%}" if truth else f"{'--':>10}"
        print(f"{name:>25}{fired[name] / n:>8.0%}{mean:>+12.3f}{share}"
              f"{'--' if name.startswith('true') else f'{t:+.2f}':>11}"
              f"{agree[name] / n:>8.0%}{statistics.mean(secs[name]):>10.3f}")


if __name__ == "__main__":
    main()
