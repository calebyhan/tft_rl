"""Why does the field die rich? Doc 99 entries 97.4 and 98.5.

Real challenger players hold ~8 gold at the moment they are eliminated. This
engine's scripted field holds 40-55 through the mid-game (97.4, t to +28.6),
while sitting 0.5-1.3 levels *below* real at the same round -- gold-rich and
under-levelled at once, with XP an available sink it declines to use.

`EconStrategy.save_floor` is 50 and `STANDARD.roll_floors` restores 50 at 4-6,
so from there a seat spends only the income above 50. That reasoning is right
for the mid-game -- 50 is the interest cap, below it you lose interest and
above it you gain nothing -- and it **has no endgame clause**. A real player one
hit from elimination rolls their whole bank trying to survive; no plan here
ever does.

This probe asks whether that floor is what actually binds at the moment of
death, or whether something else refuses to spend:

* **gold at elimination against the floor in force** -- is the seat sitting
  exactly on its floor, or below it?
* **gold against HP** -- do seats one hit from death hold a full bank?
* **what the leftover could have bought** -- XP to the next level, or rerolls.

Outcomes were named before the first run (doc 99 entry 99):
O1 floor binding everywhere; O2 floor never binding, a different blocker;
O3 binding mid-game and not late.

    .venv/bin/python scripts/gold_sink_probe.py --games 100
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.loader import load_all  # noqa: E402
from engine.match import Match  # noqa: E402
from rl.opponents import DEFAULT_FIELD, GreedyPolicy  # noqa: E402


def mean(values) -> float:
    return statistics.mean(values) if values else 0.0


def probe(data, games: int, seed0: int = 0) -> dict:
    config = data.config
    xp_cost = config.xp_purchase_gold
    reroll_cost = config.reroll_cost

    rows: list[dict] = []
    for game in range(games):
        econs = [DEFAULT_FIELD[seat % len(DEFAULT_FIELD)] for seat in range(8)]
        policies = [GreedyPolicy(seed=seat, econ=econs[seat]) for seat in range(8)]
        match = Match(data, policies, seed=seed0 + game)

        # State each seat goes into a round with, so the eliminated seat's last
        # entry is the board and bank it died holding (as in engine_profile).
        pending: dict[int, dict] = {}
        alive_before = {p.player_id for p in match.living_players}

        while not match.finished:
            label = f"{match.round_id.stage}-{match.round_id.round}"
            for player in match.living_players:
                econ = econs[player.player_id]
                floor = econ.roll_floor(match.round_id)
                pending[player.player_id] = {
                    "round": label,
                    "stage": match.round_id.stage,
                    "econ": econ.name,
                    "gold": player.gold,
                    "hp": player.hp,
                    "level": player.level,
                    "floor": econ.save_floor if floor is None else floor,
                }
            match.play_round()
            alive_now = {p.player_id for p in match.living_players}
            for player_id in alive_before - alive_now:
                rows.append(pending[player_id])
            alive_before = alive_now

    return {
        "rows": rows,
        "games": games,
        "xp_cost": xp_cost,
        "reroll_cost": reroll_cost,
    }


def report(result: dict) -> None:
    rows = result["rows"]
    xp_cost, reroll_cost = result["xp_cost"], result["reroll_cost"]
    print(f"{len(rows)} eliminations over {result['games']} games\n")

    print("gold held at elimination, against the roll floor in force:")
    print(f"{'stage':>7}{'n':>6}{'gold':>8}{'floor':>7}{'over':>8}"
          f"{'at/above':>10}{'hp<=20':>9}{'gold@hp<=20':>13}")
    by_stage: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        by_stage[row["stage"]].append(row)
    for stage in sorted(by_stage):
        sample = by_stage[stage]
        low = [r for r in sample if r["hp"] <= 20]
        at_or_above = sum(1 for r in sample if r["gold"] >= r["floor"])
        print(f"{stage:>7}{len(sample):>6}{mean([r['gold'] for r in sample]):>8.1f}"
              f"{mean([r['floor'] for r in sample]):>7.1f}"
              f"{mean([r['gold'] - r['floor'] for r in sample]):>+8.1f}"
              f"{at_or_above / len(sample):>10.0%}"
              f"{len(low):>9}"
              f"{mean([r['gold'] for r in low]):>13.1f}")

    print("\nby archetype:")
    print(f"{'econ':>12}{'n':>6}{'gold':>8}{'floor':>7}{'at/above':>10}")
    by_econ: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_econ[row["econ"]].append(row)
    for econ in sorted(by_econ):
        sample = by_econ[econ]
        at_or_above = sum(1 for r in sample if r["gold"] >= r["floor"])
        print(f"{econ:>12}{len(sample):>6}{mean([r['gold'] for r in sample]):>8.1f}"
              f"{mean([r['floor'] for r in sample]):>7.1f}"
              f"{at_or_above / len(sample):>10.0%}")

    # What the unspent gold was worth, in the only two sinks that exist.
    gold = [r["gold"] for r in rows]
    print(f"\nunspent at death: mean {mean(gold):.1f} gold "
          f"= {mean(gold) / reroll_cost:.1f} rerolls "
          f"or {mean(gold) / xp_cost:.1f} XP purchases")
    buckets = Counter()
    for value in gold:
        buckets[min(value // 10 * 10, 60)] += 1
    print("distribution: " + "  ".join(
        f"{k}+:{v / len(gold):.0%}" for k, v in sorted(buckets.items())
    ))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=100)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    result = probe(load_all(), args.games)
    report(result)
    if args.json:
        args.json.write_text(json.dumps(result, indent=1))
        print(f"\nwritten to {args.json}")


if __name__ == "__main__":
    main()
