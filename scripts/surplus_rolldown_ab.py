"""Does rolling the *surplus* late beat capping the level? (doc 99 entry 120.5)

Entry 119 bought 1-cost 3-stars by capping the rolling level (`commit_level`),
and paid for every one of them in placement: the arm that reached 1.776
three-stars per hyper seat placed 5.752 against a baseline 5.228. 120.3 found
why that was the wrong lever -- the seat was never short of gold. It spends
**3.3x more on XP than on rolling**, dies holding 39.2g, and ends at level 8.35,
which is `standard`'s level. `HYPERROLL`'s floors confine the whole roll-down to
stage 2, where income is 5-7g a round, and from 3-2 the floor is 50 forever.

120.2's arithmetic says a seat that levels the full standard curve and *then*
rolls its surplus from 5-1 reaches level 8 at P(1-cost 3-star) = 0.577 -- twice
the real 0.271, at the real 8.26. That needs no new field: `roll_floors` already
expresses it.

Named outcomes, before the run:

* **A -- the arithmetic transfers.** 3-stars rise well above the 0.176 baseline
  and end level holds near 8. Placement is genuinely unknown: entry 114 priced
  board slots and this arm gives none up, so it may move either way or not at
  all. Fidelity is the claim under test.
* **B -- 3-stars rise but level collapses anyway.** Then the surplus is not
  surplus: something the ledger did not price is consuming it, and 119.4's
  frontier survives in a weaker form.
* **C -- nothing moves.** The floor is not what gates rolling, and 120.3's
  ledger reading is wrong about the mechanism even though its totals are right.

The `roll_buys="targets"` arms were added after the first run, which returned
outcome C-and-A together: 3-stars rose 66% but rolls reached only 29 of a
predicted 91, because the roll loop's own buy phase outbids it (121.2). Their
outcomes, named before *that* run:

* **D -- the buys were a leak.** Rolls rise sharply, 3-stars follow, placement
  holds. 50.0g of non-target buys were buying nothing the plan wanted.
* **E -- the buys were board strength.** Rolls and 3-stars rise, placement gets
  worse. Then this is entry 114's slot price arriving by a new route, and it is
  the same trade 119 lost -- not a new lever.
* **F -- rolls rise, 3-stars flat.** Copies are not the constraint and
  something downstream of buying gates the combine.

Only the hyperroll seat's strategy changes between arms; the other seven are
`DEFAULT_FIELD` throughout, and arms share episode seeds so the comparison is
paired.

    .venv/bin/python scripts/surplus_rolldown_ab.py --games 250
"""

from __future__ import annotations

import argparse
import dataclasses
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine import player as player_mod  # noqa: E402
from engine.loader import load_all  # noqa: E402
from engine.match import Match  # noqa: E402
from rl.opponents import DEFAULT_FIELD, HYPERROLL, GreedyPolicy  # noqa: E402

# The arms. `HYPERROLL` today is {"2-3": 0, "3-2": 50}: roll to nothing in
# stage 2, then bank at 50 and never roll again. Each variant reopens the tap
# at a different round, spending only what is left after the level curve is
# paid -- which is what distinguishes this from entry 119's level cap.
SURPLUS_5_1 = {"roll_floors": {"2-3": 0, "3-2": 50, "5-1": 0}}

ARMS: dict[str, tuple[dict, str]] = {
    "baseline": ({}, "all"),
    "surplus 4-5": ({"roll_floors": {"2-3": 0, "3-2": 50, "4-5": 0}}, "all"),
    "surplus 5-1": (SURPLUS_5_1, "all"),
    "surplus 5-5": ({"roll_floors": {"2-3": 0, "3-2": 50, "5-5": 0}}, "all"),
    # A floor of 20 keeps two rounds of interest rather than none. If 5-1 wins
    # and this does not, the gain is the rolling; if both win equally, the
    # baseline's 50 was simply too high and the exact floor does not matter.
    "surplus 5-1 @20": ({"roll_floors": {"2-3": 0, "3-2": 50, "5-1": 20}}, "all"),
    # Entry 121.4: of the 52.8g a rolling seat spends on units from 5-1, only
    # 2.8g is target copies. These two arms stop the roll loop outbidding
    # itself. The `roll_buys` arm alone isolates it from the floor change.
    "targets-only buys": ({}, "targets"),
    "surplus 5-1 + targets": (SURPLUS_5_1, "targets"),
}


def paired_t(a: list[float], b: list[float]) -> tuple[float, float]:
    """(mean difference b-a, t) for paired samples."""
    diffs = [y - x for x, y in zip(a, b, strict=True)]
    n = len(diffs)
    mean = sum(diffs) / n
    if n < 2:
        return mean, 0.0
    sd = statistics.stdev(diffs)
    if sd == 0:
        return mean, 0.0
    return mean, mean / (sd / math.sqrt(n))


def run_arm(data, econ, games: int, seed0: int, roll_buys: str = "all") -> dict:
    """One arm. Every `hyperroll` seat in the field gets `econ`."""
    econs = [DEFAULT_FIELD[seat % len(DEFAULT_FIELD)] for seat in range(8)]
    hyper_seats = [i for i, e in enumerate(econs) if e.name == "hyperroll"]
    econs = [econ if i in hyper_seats else e for i, e in enumerate(econs)]

    # Count rerolls at the engine call rather than by inspecting the policy:
    # the policy decides, but only the player actually pays.
    rolls: Counter = Counter()
    real_reroll = player_mod.PlayerState.reroll

    def counting_reroll(self, *a, **kw):
        rolls[self.player_id] += 1
        return real_reroll(self, *a, **kw)

    player_mod.PlayerState.reroll = counting_reroll
    try:
        per_game: dict[str, list[float]] = defaultdict(list)
        for game in range(games):
            rolls.clear()
            policies = [
                GreedyPolicy(seed=seat, econ=econs[seat],
                             roll_buys=roll_buys if seat in hyper_seats else "all")
                for seat in range(8)
            ]
            match = Match(data, policies, seed=seed0 + game)
            # A seat's board is gone once it dies, so 3-stars have to be read
            # while it is alive -- the same reason `three_star_source` walks
            # the rounds instead of reading the final state.
            best: dict[int, int] = dict.fromkeys(range(8), 0)
            while not match.finished:
                for player in match.living_players:
                    n = sum(1 for u in player.all_units
                            if u.star_level == 3 and u.champion.cost == 1)
                    best[player.player_id] = max(best[player.player_id], n)
                match.play_round()

            # `Match.run` is this loop plus `_finalise_placements`, and only
            # that call ranks the seats still alive at the end; `placements`
            # otherwise holds eliminated seats alone. Interleaving the 3-star
            # scan means driving the rounds by hand, so finalise by hand too.
            match._finalise_placements()
            levels = {p.player_id: p.level for p in match.players}
            places = match.placements
            per_game["c1_hyper"].append(
                statistics.mean(best[s] for s in hyper_seats))
            per_game["c1_field"].append(statistics.mean(best.values()))
            per_game["rolls"].append(
                statistics.mean(rolls[s] for s in hyper_seats))
            per_game["level"].append(
                statistics.mean(levels[s] for s in hyper_seats))
            per_game["place"].append(
                statistics.mean(places[s] for s in hyper_seats))
        return per_game
    finally:
        player_mod.PlayerState.reroll = real_reroll


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=250)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    data = load_all()
    results: dict[str, dict] = {}
    for name, (changes, roll_buys) in ARMS.items():
        econ = dataclasses.replace(HYPERROLL, **changes) if changes else HYPERROLL
        results[name] = run_arm(data, econ, args.games, args.seed, roll_buys)
        print(f"  ran {name}", flush=True)

    print(f"\n{args.games} games per arm, paired seeds, only the hyperroll "
          f"seat changes\n")
    print(f"{'arm':>22}{'c1 3* /hyper':>14}{'c1 /seat':>10}{'rolls':>8}"
          f"{'end lvl':>9}{'placement':>11}{'t vs base':>11}")
    base = results["baseline"]
    for name, row in results.items():
        delta, t = paired_t(base["place"], row["place"])
        print(f"{name:>22}{statistics.mean(row['c1_hyper']):>14.3f}"
              f"{statistics.mean(row['c1_field']):>10.3f}"
              f"{statistics.mean(row['rolls']):>8.1f}"
              f"{statistics.mean(row['level']):>9.2f}"
              f"{statistics.mean(row['place']):>11.3f}"
              f"{'--' if name == 'baseline' else f'{t:+.2f}':>11}")
    print(f"{'real TFT':>22}{'--':>14}{0.271:>10.3f}{'--':>8}{8.26:>9.2f}"
          f"{4.43:>11.2f}{'--':>11}")


if __name__ == "__main__":
    main()
