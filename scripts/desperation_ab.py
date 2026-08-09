"""Does an endgame spend-down close the gold gap, and what does it cost?

Doc 99 entry 99. `EconStrategy.save_floor` keeps 50 gold banked because that is
the interest cap, and no plan ever abandons it -- so this field dies holding
33.6 gold against a real challenger's ~8 (entry 97.4), with 24% of eliminated
seats on 60+.

`desperation_hp` drops the roll floor to 0 once a seat is that close to death.
This measures the arm against the unchanged field on **shared seeds**, so the
two differ in one field and nothing else.

Two questions, and they are separate:

1. **Does it work mechanically?** Gold at elimination should fall toward the
   reference's ~8. If it does not, the floor was not the binding constraint and
   entry 99's diagnosis is wrong.
2. **What does it do to placement?** The field getting stronger is not free --
   entries 72 and 73 both moved every downstream number by changing the field.
   A seat that dumps its bank may also just die with a better board and the
   same placement, since someone still comes last.

Placement of the *whole field* cannot move: eight seats always average 4.5.
What can move is survival -- how long a seat lasts -- so the reported metric is
the elimination round, plus gold at death for question 1.

    .venv/bin/python scripts/desperation_ab.py --games 100 --hp 20
"""

from __future__ import annotations

import argparse
import dataclasses
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine.loader import load_all  # noqa: E402
from engine.match import Match  # noqa: E402
from rl.opponents import DEFAULT_FIELD, GreedyPolicy  # noqa: E402


def mean(values) -> float:
    return statistics.mean(values) if values else 0.0


def sd(values) -> float:
    return statistics.stdev(values) if len(values) > 1 else 0.0


def run(data, games: int, desperation_hp: int, seed0: int = 0) -> dict:
    stage_one = data.config.round_structure.stage_one_rounds
    per_stage = data.config.round_structure.rounds_per_stage

    def flat(stage: int, round_: int) -> int:
        return round_ if stage == 1 else stage_one + per_stage * (stage - 2) + round_

    econs = [
        dataclasses.replace(DEFAULT_FIELD[seat % len(DEFAULT_FIELD)],
                            desperation_hp=desperation_hp)
        for seat in range(8)
    ]

    gold_at_death: list[int] = []
    elimination_round: list[int] = []

    for game in range(games):
        policies = [GreedyPolicy(seed=seat, econ=econs[seat]) for seat in range(8)]
        match = Match(data, policies, seed=seed0 + game)
        pending: dict[int, tuple[int, int]] = {}
        alive_before = {p.player_id for p in match.living_players}

        while not match.finished:
            index = flat(match.round_id.stage, match.round_id.round)
            for player in match.living_players:
                pending[player.player_id] = (index, player.gold)
            match.play_round()
            alive_now = {p.player_id for p in match.living_players}
            for player_id in alive_before - alive_now:
                index, gold = pending[player_id]
                elimination_round.append(index)
                gold_at_death.append(gold)
            alive_before = alive_now

    return {"gold": gold_at_death, "round": elimination_round}


def welch_t(a: list, b: list) -> float:
    if len(a) < 2 or len(b) < 2:
        return 0.0
    variance = sd(a) ** 2 / len(a) + sd(b) ** 2 / len(b)
    return 0.0 if variance <= 0 else (mean(a) - mean(b)) / variance ** 0.5


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=100)
    parser.add_argument("--hp", type=int, default=20,
                        help="HP at or below which a seat dumps its bank")
    args = parser.parse_args()

    data = load_all()
    off = run(data, args.games, desperation_hp=0)
    on = run(data, args.games, desperation_hp=args.hp)

    print(f"{args.games} games, shared seeds, mixed field; "
          f"desperation_hp={args.hp}\n")
    print(f"{'metric':>22}{'off':>10}{'on':>10}{'delta':>9}{'t':>8}")
    for name, key in (("gold at elimination", "gold"),
                      ("elimination round", "round")):
        a, b = off[key], on[key]
        print(f"{name:>22}{mean(a):>10.2f}{mean(b):>10.2f}"
              f"{mean(b) - mean(a):>+9.2f}{welch_t(b, a):>+8.2f}")

    rich_off = sum(1 for g in off["gold"] if g >= 60) / len(off["gold"])
    rich_on = sum(1 for g in on["gold"] if g >= 60) / len(on["gold"])
    print(f"\n  died holding 60+ gold: {rich_off:.0%} -> {rich_on:.0%}")
    print("  reference (challenger, entry 97.4): ~8 gold at elimination")


if __name__ == "__main__":
    main()
