"""Does 126.1's level finding generalise to `slowroll6`? (doc 99 entry 127)

126.1 measured that a 3-cost reroll plan parked at level 7 places **0.96 worse**
than one that levels to 8 (t = -9.70). `SLOWROLL7` is not shipped, so that was a
finding about an archetype nobody plays.

`SLOWROLL6` is shipped, and it parks harder: `level_targets` reach 6 at 3-2 and
do not reach 7 until **5-1** -- roughly thirteen rounds at level 6. `HYPERROLL`
by contrast already follows the standard curve (7 at 4-1, 8 at 4-5) and is not a
candidate. So `slowroll6` is the one shipped plan the 126 finding could apply
to, and it holds **two of eight seats** in `DEFAULT_FIELD`.

The tension, named before the run because it is the reason this is not obvious:
**118.4 established that cost-2 3-stars are the one tier already matching
reality** (0.344 engine against 0.326 real). Levelling `slowroll6` out of level
6 should reduce exactly those. A placement gain here would therefore *break* the
project's only tier-level fidelity match, and that trade has to be stated rather
than discovered.

Named outcomes:

* **A -- generalises.** Placement improves markedly and cost-2 3-stars fall.
  Parking is bad in general; the fidelity match was an artefact of bad play.
* **B -- does not generalise.** Placement flat. 126.1 was about level 7 and the
  3-cost tier specifically, not about parking as such.
* **C -- both hold.** Placement improves and the cost-2 rate survives. The only
  outcome that would justify changing a shipped default.

The `slowroll6` seats of `DEFAULT_FIELD` (two of eight) are the only ones whose
strategy changes.
Arms share episode seeds.

    .venv/bin/python scripts/slowroll6_level_ab.py --games 250
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
from rl.opponents import DEFAULT_FIELD, SLOWROLL6, GreedyPolicy  # noqa: E402

ARMS: dict[str, dict] = {
    "slowroll6 (shipped)": {},
    # The standard curve: 7 at 4-1, 8 at 4-5. This is what `hyperroll` already
    # runs and what 126.1's winning 3-cost arm ran.
    "standard curve": {"level_targets": {"2-5": 5, "3-2": 6, "4-1": 7,
                                         "4-5": 8, "5-5": 9}},
    # Halfway: leave 3-2 alone, reach 7 at 4-1 but keep 8 late. Separates "get
    # off level 6" from "reach 8 early", which the full swap confounds.
    "7 at 4-1 only": {"level_targets": {"2-5": 5, "3-2": 6, "4-1": 7,
                                        "5-5": 8, "6-1": 9}},
}


def paired_t(a: list[float], b: list[float]) -> tuple[float, float]:
    diffs = [y - x for x, y in zip(a, b, strict=True)]
    n = len(diffs)
    mean = sum(diffs) / n
    if n < 2:
        return mean, 0.0
    sd = statistics.stdev(diffs)
    return (mean, 0.0) if sd == 0 else (mean, mean / (sd / math.sqrt(n)))


def run_arm(data, econ, games: int, seed0: int) -> dict:
    econs = [DEFAULT_FIELD[s % len(DEFAULT_FIELD)] for s in range(8)]
    seats = [i for i, e in enumerate(econs) if e.name == "slowroll6"]
    econs = [econ if i in seats else e for i, e in enumerate(econs)]

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
            policies = [GreedyPolicy(seed=s, econ=econs[s]) for s in range(8)]
            match = Match(data, policies, seed=seed0 + game)
            # Peak 3-star counts must be read while the seat is alive.
            best2 = dict.fromkeys(seats, 0)
            while not match.finished:
                for player in match.living_players:
                    if player.player_id not in seats:
                        continue
                    n = sum(1 for u in player.all_units
                            if u.star_level == 3 and u.champion.cost == 2)
                    best2[player.player_id] = max(best2[player.player_id], n)
                match.play_round()
            match._finalise_placements()
            levels = {p.player_id: p.level for p in match.players}
            per_game["c2"].append(statistics.mean(best2.values()))
            per_game["hit"].append(
                statistics.mean(1.0 if best2[s] else 0.0 for s in seats))
            per_game["rolls"].append(statistics.mean(rolls[s] for s in seats))
            per_game["level"].append(statistics.mean(levels[s] for s in seats))
            per_game["place"].append(
                statistics.mean(match.placements[s] for s in seats))
        return per_game
    finally:
        player_mod.PlayerState.reroll = real_reroll


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=250)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    data = load_all()
    results = {}
    for name, changes in ARMS.items():
        econ = dataclasses.replace(SLOWROLL6, **changes) if changes else SLOWROLL6
        results[name] = run_arm(data, econ, args.games, args.seed)
        print(f"  ran {name}", flush=True)

    print(f"\n{args.games} games per arm, the slowroll6 seats\n")
    print(f"{'arm':>21}{'c2 3*/seat':>12}{'hit rate':>10}{'rolls':>8}"
          f"{'end lvl':>9}{'placement':>11}{'t vs base':>11}")
    base = results["slowroll6 (shipped)"]
    for name, row in results.items():
        _, t = paired_t(base["place"], row["place"])
        print(f"{name:>21}{statistics.mean(row['c2']):>12.3f}"
              f"{statistics.mean(row['hit']):>10.1%}"
              f"{statistics.mean(row['rolls']):>8.1f}"
              f"{statistics.mean(row['level']):>9.2f}"
              f"{statistics.mean(row['place']):>11.3f}"
              f"{'--' if name.startswith('slowroll6') else f'{t:+.2f}':>11}")
    print("\n118.4 reference: cost-2 3-stars 0.344 engine / 0.326 real "
          "(field-wide, not per slowroll6 seat).")


if __name__ == "__main__":
    main()
