"""Does a teacher that *searches* its buy beat one that heuristics it? (entry 144)

Stage 1 of the only learning path left open. The chain, from the log:

* Imitation transmits a teacher improvement at **89%** (75), so a better
  teacher is a better agent -- the machinery works.
* Nothing else improves the agent: PPO closed on per-decision credit 46x below
  its noise (130), ES on economics (94), and the econ parameter space is flat
  near the incumbents across 60 candidates (142).
* The one decision rule in this repo that beats the teacher is **search**
  (0.243 placement, 108.2 corrected in 130.1), and it has only ever been
  applied to the *board* decision.

143 built the other half -- scoring a purchase by simulated combat. Nobody has
tested a teacher that searches **both**. This asks whether it is better at all,
before anything is cloned from it.

**Cost forced the design.** `_buy_phase` runs on every roll iteration, so
searching there would be 10-50x entry 106's board search, which was already
~30% overhead. The search buy fires **once per round on the opening shop**;
greedy buying proceeds untouched afterwards. A null here is therefore a null
about *this* intervention, not about search-based buying in general.

Named outcomes, before the run:

* **A -- >= 0.45 better.** n=200 resolves it (141.2). First teacher improvement
  since 75; proceed to the observation work needed to clone it.
* **B -- better but under resolution.** Needs ~1,570 games to confirm a 0.15
  effect; a deliberate budget decision, not an automatic next step.
* **C -- no better or worse.** Search helps the board and not the buy, and the
  distinction is itself informative: the buy decision may already be near
  optimal, or one search per round may be too sparse to matter.

    .venv/bin/python scripts/search_teacher_ab.py --games 200
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
from engine.unit import UnitInstance  # noqa: E402
from rl.opponents import FAST8, GreedyPolicy, default_opponent  # noqa: E402
from rl.search import clone_board, fight_value, opponent_panel  # noqa: E402

PANEL = 2
TRIALS = 2
MARGIN = 0.25          # per fight, matching the advisor's scale (136.3)

_DATA = None


def _init():
    global _DATA
    from engine.loader import load_all
    _DATA = load_all()


class SearchBuyPolicy(GreedyPolicy):
    """`GreedyPolicy`, but the first buy each round is chosen by simulation.

    Everything else -- levelling, rolling, subsequent buys, board filling -- is
    the parent's. So any difference is attributable to that one decision, which
    is the same discipline entry 106 used to isolate the board search.
    """

    def plan(self, player, context) -> None:
        self._search_buy(player, context)
        super().plan(player, context)

    def _search_buy(self, player, context) -> None:
        match = context.match
        if not player.board or not player.free_bench_slots:
            return
        panel = opponent_panel(match, player, PANEL)
        if not panel:
            return
        seeds = [[self.rng.randrange(2**31) for _ in range(TRIALS)]
                 for _ in panel]
        shim = SimpleNamespace(player=player, match=match)
        base = self._score(shim, panel, seeds)

        best = None
        for index, champion_id in enumerate(player.shop.slots):
            if champion_id is None or not player.can_buy(index):
                continue
            champion = context.data.champions[champion_id]
            held = sum(1 for u in player.all_units
                       if u.champion.id == champion_id and u.star_level == 1)
            star = 2 if held >= 2 else 1
            unit = UnitInstance(champion, star, [], registry=match.registry)
            free = [h for h in sorted(player._own_hexes) if h not in player.board]
            if len(player.board) < player.max_board_units and free:
                extra, drops = ((unit, free[0]),), ()
            else:
                weakest = min(player.board,
                              key=lambda h: (player.board[h].star_level,
                                             player.board[h].champion.cost))
                extra, drops = ((unit, weakest),), (weakest,)
            if star == 2:
                pair = [h for h, u in player.board.items()
                        if u.champion.id == champion_id and u.star_level == 1]
                drops = tuple({*drops, *pair[:2]})
            value = self._score(shim, panel, seeds, extra=extra, drops=drops)
            if best is None or value > best[0]:
                best = (value, index)

        if best is not None and best[0] > base + MARGIN * len(panel):
            player.buy(best[1], context.pool)

    @staticmethod
    def _score(shim, panel, seeds, extra=(), drops=()) -> float:
        player, match = shim.player, shim.match
        board, data = player.hex_board, player.data
        total = 0.0
        for other, trial_seeds in zip(panel, seeds[:len(panel)], strict=True):
            for seed in trial_seeds:
                total += fight_value(
                    data, board,
                    clone_board(match, player, 0, extra=extra, drops=drops),
                    clone_board(match, other, 1), seed)
        return total / max(len(seeds[0]), 1)


class RandomBuyPolicy(GreedyPolicy):
    """The control for `SearchBuyPolicy`: same extra purchase, no search.

    `_search_buy` makes one buy per round that greedy might decline, and **board
    size dominates** in this engine (67, 68, 72), so a gain could be volume
    rather than judgement. This arm buys a *random* affordable slot in the same
    place, which isolates which one it is. Without it the headline number is
    unreadable.
    """

    def plan(self, player, context) -> None:
        slots = [i for i in range(len(player.shop.slots))
                 if player.can_buy(i)]
        if slots and player.free_bench_slots:
            player.buy(self.rng.choice(slots), context.pool)
        super().plan(player, context)


def _play(job):
    kind, seed = job
    cls = {"search": SearchBuyPolicy, "random": RandomBuyPolicy}.get(
        kind, GreedyPolicy)
    policies = [cls(seed=0, econ=FAST8)] + [default_opponent(i)
                                            for i in range(1, 8)]
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
    parser.add_argument("--seed", type=int, default=0,
                        help="first match seed; use a disjoint block to replicate")
    args = parser.parse_args()

    seeds = list(range(args.seed, args.seed + args.games))
    with mp.Pool(args.workers, initializer=_init) as pool:
        base = pool.map(_play, [("greedy", s) for s in seeds], chunksize=4)
        print(f"  greedy   {statistics.mean(base):.3f}", flush=True)
        rand = pool.map(_play, [("random", s) for s in seeds], chunksize=4)
        print(f"  random   {statistics.mean(rand):.3f}", flush=True)
        arm = pool.map(_play, [("search", s) for s in seeds], chunksize=4)
        print(f"  search   {statistics.mean(arm):.3f}", flush=True)

    print(f"\nn={args.games} seed-paired, seat 0, fast8 econ, parity 4.500\n")
    print(f"{'teacher':>28}{'placement':>11}{'vs greedy':>11}{'t':>8}")
    for name, places in (("greedy buy (incumbent)", base),
                         ("random buy, once per round", rand),
                         ("search buy, once per round", arm)):
        d, t = paired_t(base, places)
        print(f"{name:>28}{statistics.mean(places):>11.3f}{d:>+11.3f}{t:>8.2f}")
    d, t = paired_t(rand, arm)
    print(f"\nsearch - random: {d:+.3f}  t {t:+.2f}  "
          f"<- the readable number: does searching beat merely buying?")


if __name__ == "__main__":
    main()
