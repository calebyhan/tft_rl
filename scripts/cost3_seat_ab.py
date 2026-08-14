"""Re-specify the 3-cost reroll seat against the real archetype (entry 125.4).

125.1-125.3 described what a real 3-cost reroll seat is, and `SLOWROLL7` is not
it: the modal hitting seat holds **one** 3-star, not three; 64% are at level 8
or above, not parked at 7; and a third of the board is 4- and 5-cost.

Outcomes were named in 125.4 before this ran. **C is what the rest of the arc
predicts** -- 123.2's income ceiling (~9g/round once a seat rolls to zero)
against 58.5 rolls per named 3-cost at level 7 -- so a null here is the expected
result and not a disappointment. A is the interesting one.

One seat in the field is swapped from `standard` to the 3-cost line so the
archetype is present at all; the other seven are `DEFAULT_FIELD`. Arms share
episode seeds.

    .venv/bin/python scripts/cost3_seat_ab.py --games 250
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
from rl.opponents import DEFAULT_FIELD, SLOWROLL7, GreedyPolicy  # noqa: E402

# The standard curve, for the arms that stop parking at 7. SLOWROLL7 ships with
# {"2-5": 5, "3-2": 6, "4-1": 7, "5-5": 8, "6-1": 9}.
TO_EIGHT = {"2-5": 5, "3-2": 6, "4-1": 7, "4-5": 8, "5-5": 9}

ARMS: dict[str, dict] = {
    "slowroll7 (shipped)": {},
    "count=1": {"target_count": 1},
    "count=2": {"target_count": 2},
    # 125.1: 64% of real hitters are level 8+. Levelling on the standard curve
    # while still targeting is the specification the rows imply.
    "count=1, level to 8": {"target_count": 1, "level_targets": TO_EIGHT},
    "count=2, level to 8": {"target_count": 2, "level_targets": TO_EIGHT},
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
    # Seat 0 carries the line. `DEFAULT_FIELD` has no 3-cost archetype at all,
    # which is the gap 115.3 named, so one seat has to be converted rather than
    # substituted for a same-archetype peer.
    seat = 0
    econs[seat] = econ

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
            best = 0
            while not match.finished:
                for player in match.living_players:
                    if player.player_id != seat:
                        continue
                    n = sum(1 for u in player.all_units
                            if u.star_level == 3 and u.champion.cost == 3)
                    best = max(best, n)
                match.play_round()
            match._finalise_placements()
            per_game["c3"].append(best)
            per_game["hit"].append(1.0 if best else 0.0)
            per_game["rolls"].append(rolls[seat])
            per_game["level"].append(
                next(p.level for p in match.players if p.player_id == seat))
            per_game["place"].append(match.placements[seat])
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
        econ = dataclasses.replace(SLOWROLL7, **changes) if changes else SLOWROLL7
        results[name] = run_arm(data, econ, args.games, args.seed)
        print(f"  ran {name}", flush=True)

    print(f"\n{args.games} games per arm, seat 0 runs the 3-cost line\n")
    print(f"{'arm':>21}{'c3 3*/seat':>12}{'hit rate':>10}{'rolls':>8}"
          f"{'end lvl':>9}{'placement':>11}{'t vs base':>11}")
    base = results["slowroll7 (shipped)"]
    for name, row in results.items():
        _, t = paired_t(base["place"], row["place"])
        print(f"{name:>21}{statistics.mean(row['c3']):>12.3f}"
              f"{statistics.mean(row['hit']):>10.1%}"
              f"{statistics.mean(row['rolls']):>8.1f}"
              f"{statistics.mean(row['level']):>9.2f}"
              f"{statistics.mean(row['place']):>11.3f}"
              f"{'--' if name.startswith('slowroll7') else f'{t:+.2f}':>11}")
    print(f"{'real TFT (hitters)':>21}{'--':>12}{0.101:>10.1%}{'--':>8}"
          f"{7.99:>9.2f}{4.01:>11.2f}{'--':>11}")


if __name__ == "__main__":
    main()
