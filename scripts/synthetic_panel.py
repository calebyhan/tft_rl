"""Can a *prior* supply the breadth that scouting supplies? (doc 99 entry 138)

137.1 found that board advice loses 30% of its value without opponents, and
that the loss is **breadth** rather than identity: scouting one real board
(68% of true-field value) is worth no more than fighting your own shadow (70%).

Breadth does not require observation. A library of stage-typical boards is
*prior knowledge* -- harvested offline, fixed at inference, requiring nothing
from the player. If a synthetic panel of several diverse boards recovers the
missing 30%, the typed path costs one board a round at full value.

The library is harvested from games seeded far away from the evaluation games,
so a panel is never a copy of a seat the referee is grading against.

Named outcomes, before the run:

* **A -- the prior is enough.** Library panels reach true-field value. Breadth
  is generic, scouting buys nothing, and `board_advice` should ship the library.
* **B -- partial recovery.** Better than mirror, short of true. Then real
  opponents carry information a prior cannot, and the gap size says how much.
* **C -- no recovery.** Breadth per se was not the mechanism after all, and
  137.1's reading needs revisiting -- the true field's edge would then be that
  its boards are the *actually contemporary* ones, which a prior cannot be.

    .venv/bin/python scripts/synthetic_panel.py --games 12 --states 80
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
from engine.match import Match  # noqa: E402
from rl import search as search_mod  # noqa: E402
from rl.opponents import DEFAULT_FIELD, GreedyPolicy  # noqa: E402
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

# Far from any evaluation seed, so no library board is a copy of a seat the
# referee grades against.
LIBRARY_SEED = 500_000
STAGES = (2, 3, 4, 5, 6)


def harvest(data, per_stage: int, stages=STAGES) -> dict[int, list]:
    """Freeze seat boards at each stage, from games nobody will be graded on.

    Each game is played to its target stage and then **abandoned**, which is
    what makes the returned `PlayerState` objects safe to keep: 136.1's bug was
    holding references to players a match kept mutating. Nothing advances these
    matches again, so their boards are stable.
    """
    library: dict[int, list] = {}
    for stage in stages:
        seats = []
        game = 0
        while len(seats) < per_stage:
            policies = [GreedyPolicy(seed=s, econ=DEFAULT_FIELD[s % len(DEFAULT_FIELD)])
                        for s in range(8)]
            match = Match(data, policies, seed=LIBRARY_SEED + stage * 1000 + game)
            while not match.finished and match.round_id.stage < stage:
                match.play_round()
            seats.extend(p for p in match.players if p.alive and p.board)
            game += 1
            if game > per_stage:      # stage unreachable; take what there is
                break
        library[stage] = seats[:per_stage]
    return library


def library_panel(library, stage_of):
    """Panel drawn from the prior, matched to the current stage."""
    def panel(match, player, size):
        stage = stage_of(match)
        seats = library.get(stage) or library[max(library)]
        # Deterministic per (stage, board size) so two candidate boards in the
        # same search are always compared against the same opponents.
        picks = random.Random(stage * 31 + len(player.board)).sample(
            seats, min(size, len(seats)))
        return [p for p in picks if p is not player]
    return panel


def size_matched_panel(library):
    """Panel matched on **board size**, not stage.

    `harvest` freezes a seat the moment its game ticks into the target stage,
    so a stage-matched library holds *early*-stage boards while an evaluation
    state sits anywhere within that stage. The library arms firing far less
    than the true field (39% and 28% against 51%) is that mis-calibration
    showing, not a fact about priors.

    Board size is the discriminating axis and costs the player nothing: they
    can see their own board. Ties break toward the larger board.
    """
    pool = [seat for seats in library.values() for seat in seats]

    def panel(match, player, size):
        want = len(player.board)
        ranked = sorted(pool, key=lambda p: (abs(len(p.board) - want),
                                             -len(p.board)))
        picks = [p for p in ranked if p is not player][:size]
        return picks
    return panel


def strongest_panel(library, stage_of):
    """The *strongest* boards in the library, not ones matched to the player.

    Found by diagnostic, not by design: `opponent_panel` takes the strongest
    living seats (106 chose that deliberately -- strong opponents discriminate
    between candidate boards more sharply). Every surrogate built so far is
    matched to the **hero's** strength instead: the mirror is the hero, and
    size-matching targets the hero's board size. So they all fight average
    boards while the true field fights the top of the lobby, which confounds
    every arm in 138 and 140.

    This needs no scouting either -- "what a strong board looks like at this
    stage" is prior knowledge, not an observation of the lobby.
    """
    def panel(match, player, size):
        stage = stage_of(match)
        seats = library.get(stage) or library[max(library)]
        ranked = sorted(seats, key=lambda p: (
            len(p.board), sum(u.star_level for u in p.board.values())),
            reverse=True)
        return [p for p in ranked if p is not player][:size]
    return panel


def any_stage_panel(library):
    """Panel from the prior, ignoring stage -- does stage matching matter?"""
    pool = [seat for seats in library.values() for seat in seats]

    def panel(match, player, size):
        picks = random.Random(len(player.board)).sample(pool, min(size, len(pool)))
        return [p for p in picks if p is not player]
    return panel


def mirror_panel(match, player, size):
    return [player]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=12)
    parser.add_argument("--states", type=int, default=80)
    parser.add_argument("--library", type=int, default=24,
                        help="boards harvested per stage")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    data = load_all()
    library = harvest(data, args.library)
    print("library: " + ", ".join(f"stage {s}: {len(v)}"
                                  for s, v in sorted(library.items())), flush=True)

    arms = {
        "true field (shipped)": (REAL_PANEL, ADVISOR_PANEL),
        "mirror (no opp info)": (mirror_panel, 1),
        "library, stage-matched": (library_panel(library, lambda m: m.round_id.stage),
                                   ADVISOR_PANEL),
        "library, size-matched": (size_matched_panel(library), ADVISOR_PANEL),
        "library, strongest": (strongest_panel(library, lambda m: m.round_id.stage),
                               ADVISOR_PANEL),
        "library, any stage": (any_stage_panel(library), ADVISOR_PANEL),
    }

    deltas: dict[str, list[float]] = {name: [] for name in arms}
    secs: dict[str, list[float]] = {name: [] for name in arms}
    fired: dict[str, int] = {name: 0 for name in arms}
    agree: dict[str, int] = {name: 0 for name in arms}

    def visit(index, shim):
        seeds = referee_seeds(index)
        proposals = {}
        for name, (panel_fn, width) in arms.items():
            search_mod.opponent_panel = panel_fn
            try:
                rng = random.Random(index)
                start = time.perf_counter()
                # Per-fight firing threshold held fixed across arms (136.3).
                swaps = best_board(shim, rng, panel_size=ADVISOR_PANEL,
                                   margin=MARGIN_PER_FIGHT * width) or []
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
    print(f"{'search panel':>24}{'fires':>8}{'referee dv':>12}{'% of true':>11}"
          f"{'t vs true':>11}{'agrees':>8}{'sec/call':>10}")
    for name in arms:
        mean = statistics.mean(deltas[name])
        _, t = paired_t([b - a for a, b in zip(base, deltas[name], strict=True)])
        share = f"{mean / truth:>10.0%}" if truth else f"{'--':>10}"
        print(f"{name:>24}{fired[name] / n:>8.0%}{mean:>+12.3f}{share}"
              f"{'--' if name.startswith('true') else f'{t:+.2f}':>11}"
              f"{agree[name] / n:>8.0%}{statistics.mean(secs[name]):>10.3f}")


if __name__ == "__main__":
    main()
