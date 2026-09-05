"""Do the search decisions stack? (doc 99 entry 149)

The goal is a teacher that decides **holistically** -- buy, field, items,
positioning -- so it can be cloned into an agent that does the same (75:
imitation transmits 89% of a teacher gain). 144 searched the *buy* alone and
gained −1.4 placement. This asks whether adding the other fight-evaluable
decisions adds more, or whether the first one already captures the available
gain.

Worth asking rather than assuming: all three decisions move the same object --
the board that fights -- so they may be substitutes rather than complements.
A better buy improves the board; so does a better field; the second may find
nothing left to fix.

Arms are cumulative, each adding one decision:

* **greedy** -- the incumbent heuristic throughout.
* **+buy** -- 144's policy, reproduced here as the reference point.
* **+board** -- also swaps bench units onto the board by simulation.
* **+items** -- also assigns bagged items by simulation rather than by
  `_strength`, the rule 146 measured at 13% of random's regret.

    .venv/bin/python scripts/search_stack_ab.py --games 200
"""

from __future__ import annotations

import argparse
import math
import multiprocessing as mp
import statistics
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.match import Match  # noqa: E402
from engine.player import IllegalAction  # noqa: E402
from rl.opponents import FAST8, default_opponent  # noqa: E402
from rl.search import (  # noqa: E402
    best_board,
    clone_board,
    fight_value,
    item_candidates,
    opponent_panel,
)
from scripts.search_teacher_ab import PANEL, TRIALS, SearchBuyPolicy  # noqa: E402

_DATA = None


def _init():
    global _DATA
    from engine.loader import load_all
    _DATA = load_all()


class StackedSearchPolicy(SearchBuyPolicy):
    """`GreedyPolicy` with each fight-evaluable decision optionally searched."""

    def __init__(self, *args, use_buy=True, use_board=False, use_items=False,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.use_buy = use_buy
        self.use_board = use_board
        self.use_items = use_items

    def plan(self, player, context) -> None:
        if self.use_buy:
            self._search_buy(player, context)
        # **Items are searched before the parent plans.** `GreedyPolicy.plan`
        # ends by calling the module-level `_equip_phase`, and TFT items cannot
        # be moved once equipped -- so anything not placed by then is placed by
        # `_strength` and is unrecoverable. Searching first claims the good
        # assignments; the parent still empties whatever is left.
        if self.use_items:
            self._search_items(player, context)
        super(SearchBuyPolicy, self).plan(player, context)
        if self.use_board:
            self._search_board(player, context)

    def _panel_and_seeds(self, player, context):
        panel = opponent_panel(context.match, player, PANEL)
        if not panel:
            return None, None
        seeds = [[self.rng.randrange(2**31) for _ in range(TRIALS)]
                 for _ in panel]
        return panel, seeds

    def _score_with_item(self, player, match, panel, seeds, own_hex, item):
        """Score the board as if `item` were on the unit at `own_hex`.

        **Equipped on the clone, never on the real unit.**
        `UnitInstance.equip_or_combine` shares the live action's component
        transition without touching the item bag. `clone_board` emits units in
        `sorted(board)` order, which is what indexes the clone back to the hex.
        """
        order = sorted(player.board)
        index = order.index(own_hex)
        total = 0.0
        for other, trial_seeds in zip(panel, seeds[:len(panel)], strict=True):
            for seed in trial_seeds:
                team0 = clone_board(match, player, 0)
                team0[index].equip_or_combine(item)
                total += fight_value(player.data, player.hex_board, team0,
                                     clone_board(match, other, 1), seed)
        return total / max(len(seeds[0]), 1)

    def _search_items(self, player, context) -> None:
        for _ in range(2):                      # at most two per round, for cost
            candidate_context = item_candidates(player)
            if candidate_context is None:
                return
            panel, seeds = self._panel_and_seeds(player, context)
            if panel is None:
                return
            item, candidates = candidate_context
            best, best_hex = None, None
            for own_hex in candidates:
                value = self._score_with_item(player, context.match, panel,
                                              seeds, own_hex, item)
                if best is None or value > best:
                    best, best_hex = value, own_hex
            if best_hex is None:
                return
            try:
                player.equip_from_bag(item.id, player.board[best_hex])
            except IllegalAction:
                return

    def _search_board(self, player, context) -> None:
        shim = SimpleNamespace(player=player, match=context.match)
        swaps = best_board(shim, self.rng, panel_size=PANEL, trials=TRIALS,
                           margin=0.25 * PANEL)
        if not swaps:
            return
        for unit, target in swaps:
            index = next((i for i, u in enumerate(player.bench) if u is unit),
                         None)
            if index is None:
                continue
            try:
                player.move_to_board(index, target)
            except Exception:
                return


ARMS = {
    "greedy": {"use_buy": False},
    "+buy": {"use_buy": True},
    "+board": {"use_buy": True, "use_board": True},
    "+items": {"use_buy": True, "use_board": True, "use_items": True},
}


def _play(job):
    name, seed = job
    policies = [StackedSearchPolicy(seed=0, econ=FAST8, **ARMS[name])] + [
        default_opponent(i) for i in range(1, 8)]
    match = Match(_DATA, policies, seed=seed)
    while not match.finished:
        match.play_round()
    match._finalise_placements()
    return match.placements[0]


def paired_t(a, b):
    diffs = [y - x for x, y in zip(a, b, strict=True)]
    mean = statistics.mean(diffs)
    sd = statistics.stdev(diffs)
    return mean, (mean / (sd / math.sqrt(len(diffs))) if sd else 0.0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=200)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    seeds = list(range(args.seed, args.seed + args.games))
    got = {}
    with mp.Pool(args.workers, initializer=_init) as pool:
        for name in ARMS:
            got[name] = pool.map(_play, [(name, s) for s in seeds], chunksize=4)
            print(f"  {name:>8} {statistics.mean(got[name]):.3f}", flush=True)

    print(f"\nn={args.games} seed-paired, seat 0, fast8 econ, parity 4.500\n")
    print(f"{'teacher':>10}{'placement':>11}{'vs greedy':>11}{'t':>8}"
          f"{'vs previous':>13}{'t':>8}")
    previous = None
    for name in ARMS:
        places = got[name]
        d, t = paired_t(got["greedy"], places)
        if previous is None:
            step = "--"
            step_t = ""
        else:
            sd, st = paired_t(got[previous], places)
            step, step_t = f"{sd:+.3f}", f"{st:+.2f}"
        print(f"{name:>10}{statistics.mean(places):>11.3f}{d:>+11.3f}{t:>8.2f}"
              f"{step:>13}{step_t:>8}")
        previous = name
    print("\n'vs previous' is the increment from adding that one decision -- "
          "the number that says whether they stack.")


if __name__ == "__main__":
    main()
