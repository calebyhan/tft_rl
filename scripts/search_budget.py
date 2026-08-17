"""What budget should the *advisor's* board search run at? (doc 99 entry 136)

`bridge/decide.py:board_advice` calls `best_board` with its shipped defaults --
`max_swaps=3, max_candidates=6, panel_size=2, trials=3`. Those were chosen for
a teacher running inside a training loop (entry 106), where the search fires
once per planning phase for tens of thousands of phases and every extra combat
is multiplied by that. **An advisor has the opposite budget.** It fires once,
for a person who is already waiting, and a second of compute is free.

Entry 135.4 left this un-re-derived, which is exactly the pattern lesson "a
number measured once in one regime became a default and then a fact" warns
about. This measures it in the regime it is now used in.

Method. Real mid-game states are snapshotted from `DEFAULT_FIELD` games. Every
arm runs on the **same** state, so nothing but the budget varies. Each arm's
proposal is then scored by an independent **referee** -- a much larger panel
and trial count, on seeds no arm ever saw -- as the survivor margin of the
proposed board minus that of the current board. A search graded by its own
fights would grade its own noise.

The ceiling is measured, not assumed (`oracle`): the same search at a budget no
advisor would pay, which bounds what this candidate generator can find at all.
A budget curve is uninterpretable without it.

Named outcomes, before the run:

* **A -- the default is already at the ceiling.** Extra budget buys nothing the
  referee can see; `board_advice` keeps its defaults and 135.4 closes.
* **B -- there is headroom and it is cheap.** A larger budget lands materially
  closer to the oracle at a latency a person would not notice. Change the
  advisor's defaults (and only the advisor's -- the teacher's regime is
  unchanged).
* **C -- headroom, but only at unusable latency.** Then say so and leave the
  defaults, which is a different answer from A and must not be reported as one.

    .venv/bin/python scripts/search_budget.py --games 6 --states 60
"""

from __future__ import annotations

import argparse
import math
import random
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.loader import load_all  # noqa: E402
from engine.match import Match  # noqa: E402
from rl.opponents import DEFAULT_FIELD, GreedyPolicy  # noqa: E402
from rl.search import best_board, clone_board, fight_value, opponent_panel  # noqa: E402

# `best_board.score()` divides by `trials` but **not** by `panel_size`, so its
# `margin` is a threshold on the summed margin over the panel, not the per-fight
# one. Raising the panel therefore loosens the firing rule as a side effect --
# an arm with a bigger panel would look better partly by searching more often
# rather than by searching better. `MARGIN_PER_FIGHT` restores the invariance so
# that budget is the only thing varying (see `scaled`).
MARGIN_PER_FIGHT = 0.25          # 0.5 summed over the shipped panel of 2
ADVISOR_PANEL = 4                # what 136.2 settled on; see `ADVISOR_SEARCH`

# Shipped first: every other arm is reported as a difference from it.
ARMS: dict[str, dict] = {
    "shipped (t3 p2 c6 s3)": {},
    "trials 6": {"trials": 6},
    "panel 4": {"panel_size": 4},
    "candidates 10": {"max_candidates": 10},
    "swaps 5": {"max_swaps": 5},
    "t6 p4": {"trials": 6, "panel_size": 4},
    "t6 p4 c10 s5": {"trials": 6, "panel_size": 4,
                     "max_candidates": 10, "max_swaps": 5},
}
# Not an arm anyone would ship -- the bound on what this candidate generator can
# reach, so the arms above can be read as a fraction of something.
# A large-budget *reference*, not a true ceiling: it searches the same
# candidate generator with more compute, so an arm can and does exceed it by
# luck of the draw. When a row prints >100% that is the honest reading -- the
# denominator is "what a lot of compute finds", not "what is findable".
ORACLE = {"trials": 12, "panel_size": 7, "max_candidates": 14, "max_swaps": 6}

REFEREE_TRIALS = 12
REFEREE_PANEL = 7


def scaled(kwargs: dict) -> dict:
    """An arm's kwargs with `margin` set to hold the per-fight threshold fixed."""
    panel = kwargs.get("panel_size", 2)
    return {**kwargs, "margin": MARGIN_PER_FIGHT * panel}


def paired_t(diffs: list[float]) -> tuple[float, float]:
    n = len(diffs)
    if n < 2:
        return (sum(diffs) / max(n, 1), 0.0)
    mean = statistics.mean(diffs)
    sd = statistics.stdev(diffs)
    return (mean, 0.0) if sd == 0 else (mean, mean / (sd / math.sqrt(n)))


def board_margin(shim, seeds, extra=(), drops=(), panel=None) -> float:
    """Mean survivor margin per fight of a hypothetical board, over the panel.

    Normalised by panel *and* trials, unlike `best_board.score()` -- see
    `MARGIN_PER_FIGHT`. One scorer serves both the referee and its control so
    the sanity check cannot pass against a different measurement than the one
    it is vouching for.
    """
    player, match = shim.player, shim.match
    # An explicit `panel` lets a caller grade against opponents the search was
    # never shown (entry 139). Defaults to the real field.
    if panel is None:
        panel = opponent_panel(match, player, REFEREE_PANEL)
    if not panel:
        return 0.0
    board, data = player.hex_board, player.data
    total = 0.0
    # `seeds` is sized for a full lobby; late-game panels are shorter as seats
    # die. Truncating keeps each opponent bound to the *same* seed row across
    # every call, which is what makes two boards comparable at all.
    for other, trial_seeds in zip(panel, seeds[:len(panel)], strict=True):
        for seed in trial_seeds:
            total += fight_value(
                data, board,
                clone_board(match, player, 0, extra=extra, drops=drops),
                clone_board(match, other, 1), seed)
    return total / (len(panel) * len(seeds[0]))


def referee_seeds(index: int) -> list[list[int]]:
    """Fight seeds for one state, from a stream no arm ever draws from."""
    rng = random.Random(9_000_000 + index)
    return [[rng.randrange(2**31) for _ in range(REFEREE_TRIALS)]
            for _ in range(REFEREE_PANEL)]


def referee(shim, swaps, seeds, panel=None) -> float:
    """The proposed board's margin minus the current one's.

    `seeds` are drawn once per state and shared by every arm, for the same
    reason `best_board` shares them across candidates: scoring two proposals on
    different fights would measure the fights.
    """
    if not swaps:
        return 0.0
    # The search returns only what it *adds*; a target hex that is already
    # occupied means that unit is displaced, so the drops are re-derived here.
    drops = tuple(h for _, h in swaps if h in shim.player.board)
    return (board_margin(shim, seeds, extra=tuple(swaps), drops=drops,
                         panel=panel)
            - board_margin(shim, seeds, panel=panel))


def control_visit(deltas: list):
    """Does the referee see board quality at all? (135.2's discipline)

    Every arm scoring <= 0 is exactly what a **blind** referee would also
    produce, so the budget table is unreadable until this comes out clearly
    negative. Removing a player's strongest fielded unit must cost survivors --
    if it does not, the referee measures nothing and no other row means
    anything.
    """
    def visit(index, shim):
        player = shim.player
        seeds = referee_seeds(index)
        best_hex = max(player.board, key=lambda h: (
            player.board[h].star_level, player.board[h].champion.cost))
        deltas.append(board_margin(shim, seeds, drops=(best_hex,))
                      - board_margin(shim, seeds))
    return visit


def sweep(data, games: int, wanted: int, seed0: int, visit) -> int:
    """Walk `DEFAULT_FIELD` games and call `visit(index, shim)` on each state.

    **Streaming, not collected.** A first version returned a list of
    `SimpleNamespace(player=player, match=match)`, which stores *live
    references*: the engine keeps mutating those objects as the game plays on,
    so every state from one game silently aliased that game's final state. 80
    states were really ~12, measured after the fact and paired against
    duplicates of themselves. The control caught it by reporting n=19 -- most
    of the aliased players were dead or boardless by the end.

    Measuring at the moment the state exists is both correct and cheaper than
    deep-copying a `Match`, and it removes the class of bug rather than this
    instance of it.
    """
    seen = 0
    for game in range(games):
        policies = [GreedyPolicy(seed=s, econ=DEFAULT_FIELD[s % len(DEFAULT_FIELD)])
                    for s in range(8)]
        match = Match(data, policies, seed=seed0 + game)
        while not match.finished and seen < wanted:
            match.play_round()
            player = next((p for p in match.players
                           if p.player_id == 0 and p.alive), None)
            if player is None:
                break
            if (player.board and any(u is not None for u in player.bench)
                    and opponent_panel(match, player, REFEREE_PANEL)):
                visit(seen, SimpleNamespace(player=player, match=match))
                seen += 1
        if seen >= wanted:
            break
    return seen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=12)
    parser.add_argument("--states", type=int, default=80)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--control", action="store_true",
                        help="referee sanity check only; see `control_visit`")
    args = parser.parse_args()

    data = load_all()

    if args.control:
        control_deltas: list[float] = []
        n = sweep(data, args.games, args.states, args.seed,
                  control_visit(control_deltas))
        mean, t = paired_t(control_deltas)
        verdict = "referee sees board quality" if t < -3 else "REFEREE IS BLIND"
        print(f"\ncontrol (drop the best board unit), n={n}: "
              f"dv {mean:+.3f}  t {t:+.2f}  -- {verdict}")
        return

    arms = {**ARMS, "oracle (unshippable)": ORACLE}
    deltas: dict[str, list[float]] = {name: [] for name in arms}
    secs: dict[str, list[float]] = {name: [] for name in arms}
    fired: dict[str, int] = {name: 0 for name in arms}
    agree: dict[str, int] = {name: 0 for name in arms}

    def visit(index, shim):
        # Referee seeds come from a stream no arm touches, so no arm can have
        # optimised against the fights it is graded on.
        seeds = referee_seeds(index)
        proposals = {}
        for name, kwargs in arms.items():
            rng = random.Random(index)          # same draws for every arm
            start = time.perf_counter()
            swaps = best_board(shim, rng, **scaled(kwargs)) or []
            secs[name].append(time.perf_counter() - start)
            proposals[name] = swaps
            fired[name] += bool(swaps)
            deltas[name].append(referee(shim, swaps, seeds))
        gold = {id(u) for u, _ in proposals["oracle (unshippable)"]}
        for name, swaps in proposals.items():
            agree[name] += ({id(u) for u, _ in swaps} == gold)
        if (index + 1) % 10 == 0:
            print(f"  {index + 1} states", flush=True)

    n = sweep(data, args.games, args.states, args.seed, visit)

    base = deltas["shipped (t3 p2 c6 s3)"]
    reference = statistics.mean(deltas["oracle (unshippable)"])
    print(f"\n{n} states; referee = {REFEREE_PANEL} opponents x "
          f"{REFEREE_TRIALS} fights on unseen seeds\n")
    print(f"{'arm':>22}{'fires':>8}{'referee dv':>12}{'% of ref':>10}"
          f"{'t vs shipped':>14}{'agrees':>8}{'sec/call':>10}")
    for name in arms:
        mean = statistics.mean(deltas[name])
        _, t = paired_t([b - a for a, b in zip(base, deltas[name], strict=True)])
        share = f"{mean / reference:>9.0%}" if reference else f"{'--':>9}"
        print(f"{name:>22}{fired[name] / n:>8.0%}{mean:>+12.3f}{share}"
              f"{'--' if name.startswith('shipped') else f'{t:+.2f}':>14}"
              f"{agree[name] / n:>8.0%}{statistics.mean(secs[name]):>10.3f}")


if __name__ == "__main__":
    main()
