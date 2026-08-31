"""Does rolling the late surplus help? (doc 99 entry 160.75, item from 120.5).

Four arms in one run on shared seeds: two archetypes, each with and without a
``5-1`` roll floor of zero. Nothing shipped in ``rl.opponents`` is modified --
the treatments are built locally with ``dataclasses.replace``.

**This file has a ``__main__`` guard and needs one.** Workers re-import the
module they were launched from; module-level work would re-execute in every
worker and spawn more (the fork-bomb documented in ``econ_teacher_ab``).

    .venv/bin/python scripts/surplus_roll_ab.py --games 300 --workers 8
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import replace
from multiprocessing import Pool
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine import player as player_mod  # noqa: E402
from engine.loader import load_all  # noqa: E402
from engine.match import Match  # noqa: E402
from rl.opponents import (  # noqa: E402
    DEFAULT_FIELD,
    HYPERROLL,
    STANDARD,
    GreedyPolicy,
)


def fields() -> dict[str, tuple]:
    """Field variants that change contention for the arm's target pool.

    Every measurement before doc 99 entry 160.79 used `default`, in which seat 7
    is still `HYPERROLL` -- so the 3-star result was obtained with exactly one
    rival contesting the same 1-cost pool. These variants vary that and nothing
    else; seat 0 always carries the arm.
    """
    base = list(DEFAULT_FIELD)
    uncontested = list(base)
    uncontested[7] = STANDARD
    contested = list(base)
    contested[5] = contested[6] = HYPERROLL
    built = {
        "default": tuple(base),
        "uncontested": tuple(uncontested),
        "contested": tuple(contested),
    }

    # `rivals*` are the clean contention axis of doc 99 entry 160.81. Seats 5-7
    # always run HYPERROLL's plan -- same level curve, same roll floors -- and
    # only `target_cost` varies, so the rivals are equally strong and differ
    # solely in which pool they drain. 160.80's fields moved plan strength
    # along with contention and could not separate the two.
    aims_at_two = replace(HYPERROLL, name="hyperroll-c2", target_cost=2)
    for rivals in (0, 1, 3):
        seats = list(base)
        for offset in range(3):
            seats[5 + offset] = HYPERROLL if offset < rivals else aims_at_two
        built[f"rivals{rivals}"] = tuple(seats)
    return built

SEAT = 0
# The round the surplus roll opens at, as a label and as its (stage, round)
# pair -- the diagnostic needs to know when a game has reached it.
SURPLUS_ROUND = "5-1"
SURPLUS_STAGE_ROUND = (5, 1)
# The round that restores the save floor, making the surplus roll a one-round
# breakpoint instead of a standing floor -- the idiom `EconStrategy` documents
# and `standard`/`fast8` already use (doc 99 entries 71.2, 160.77).
RESTORE_ROUND = "5-2"


def arms() -> dict[str, object]:
    """Control and treatments for each base archetype, built without mutation.

    Two treatments per base: a *standing* surplus floor that rolls to zero every
    round from 5-1 onward (160.75), and a *decaying* one that restores the save
    floor the round after, so the roll-down happens once (160.77).
    """
    built: dict[str, object] = {}
    for base in (HYPERROLL, STANDARD):
        built[base.name] = base
        standing = f"{base.name}+{SURPLUS_ROUND}"
        built[standing] = replace(
            base,
            name=standing,
            roll_floors={**base.roll_floors, SURPLUS_ROUND: 0},
        )
        decaying = f"{base.name}+{SURPLUS_ROUND}r"
        built[decaying] = replace(
            base,
            name=decaying,
            roll_floors={
                **base.roll_floors,
                SURPLUS_ROUND: 0,
                RESTORE_ROUND: base.save_floor,
            },
        )
    return built


def paired_t(control: list[float], treatment: list[float]) -> tuple[float, float]:
    diffs = [b - a for a, b in zip(control, treatment, strict=True)]
    n = len(diffs)
    mean = sum(diffs) / n
    if n < 2:
        return mean, 0.0
    var = sum((d - mean) ** 2 for d in diffs) / (n - 1)
    return mean, (mean / math.sqrt(var / n) if var > 0 else 0.0)


def play_one(job: tuple[str, int] | tuple[str, int, str]) -> dict:
    """One whole game with the arm's econ on ``SEAT``; returns its record."""
    arm_name, seed, field_name = (*job, "default")[:3]
    data = _DATA if _DATA is not None else load_all()
    econ = arms()[arm_name]
    field = fields()[field_name]
    econs = [field[s % len(field)] for s in range(8)]
    econs[SEAT] = econ

    rolls: Counter = Counter()
    real_reroll = player_mod.PlayerState.reroll
    reached = {"seen": False, "gold": None, "rolls_at": 0}

    def counting_reroll(self, *a, **kw):
        rolls[self.player_id] += 1
        return real_reroll(self, *a, **kw)

    player_mod.PlayerState.reroll = counting_reroll
    try:
        policies = [GreedyPolicy(seed=s, econ=econs[s]) for s in range(8)]
        match = Match(data, policies, seed=seed)
        best = 0
        while not match.finished:
            seat_player = next(
                (p for p in match.living_players if p.player_id == SEAT), None
            )
            if seat_player is not None:
                best = max(best, sum(
                    1 for unit in seat_player.all_units if unit.star_level == 3
                ))
                here = (match.round_id.stage, match.round_id.round)
                if not reached["seen"] and here >= SURPLUS_STAGE_ROUND:
                    # Gold on *arriving* at the surplus round, before the floor
                    # has had a chance to spend it (doc 99 entry 160.75).
                    reached["seen"] = True
                    reached["gold"] = seat_player.gold
                    reached["rolls_at"] = rolls[SEAT]
            match.play_round()
        match._finalise_placements()
        seat_player = next(p for p in match.players if p.player_id == SEAT)
        return {
            "arm": arm_name,
            "field": field_name,
            "seed": seed,
            "place": match.placements[SEAT],
            "three_stars": best,
            "hit": 1.0 if best else 0.0,
            "rolls": rolls[SEAT],
            "level": seat_player.level,
            "gold": seat_player.gold,
            "reached_surplus": 1.0 if reached["seen"] else 0.0,
            "gold_at_surplus": reached["gold"],
            "rolls_after_surplus": (
                rolls[SEAT] - reached["rolls_at"] if reached["seen"] else None
            ),
        }
    finally:
        player_mod.PlayerState.reroll = real_reroll


_DATA = None


def _init() -> None:
    global _DATA
    _DATA = load_all()


def summarise(records: list[dict]) -> dict:
    def mean(key: str) -> float | None:
        values = [r[key] for r in records if r[key] is not None]
        return sum(values) / len(values) if values else None

    return {
        "n": len(records),
        "place": mean("place"),
        "three_stars": mean("three_stars"),
        "hit_rate": mean("hit"),
        "rolls": mean("rolls"),
        "level": mean("level"),
        "gold": mean("gold"),
        "reached_surplus": mean("reached_surplus"),
        "gold_at_surplus": mean("gold_at_surplus"),
        "rolls_after_surplus": mean("rolls_after_surplus"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=300)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--seed0", type=int, default=0)
    parser.add_argument("--bases", nargs="+", default=["hyperroll", "standard"])
    parser.add_argument("--fields", nargs="+", default=["default"])
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    built = arms()
    names = [
        name for name in built
        if any(name == base or name.startswith(f"{base}+") for base in args.bases)
    ]
    jobs = [
        (name, args.seed0 + game, field)
        for field in args.fields
        for name in names
        for game in range(args.games)
    ]
    with Pool(args.workers, initializer=_init) as pool:
        records = pool.map(play_one, jobs, chunksize=4)

    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for record in records:
        by_key[(record["field"], record["arm"])].append(record)
    for group in by_key.values():
        group.sort(key=lambda record: record["seed"])

    summary = {f"{field}/{name}": summarise(by_key[(field, name)])
               for field in args.fields for name in names}
    deltas = {}
    for field in args.fields:
        for base in args.bases:
            triple = [base, f"{base}+{SURPLUS_ROUND}", f"{base}+{SURPLUS_ROUND}r"]
            available = [name for name in triple if name in names]
            for control, treatment in [
                (a, b) for i, a in enumerate(available) for b in available[i + 1:]
            ]:
                row = {}
                for key in ("place", "three_stars", "hit", "rolls", "level", "gold"):
                    mean, t = paired_t(
                        [r[key] for r in by_key[(field, control)]],
                        [r[key] for r in by_key[(field, treatment)]],
                    )
                    row[key] = {"delta": mean, "t": t}
                deltas[f"{field}: {treatment} vs {control}"] = row

    print(f"{'field/arm':<28}{'place':>8}{'3star':>7}{'hit':>7}{'rolls':>7}"
          f"{'level':>7}{'gold':>7}{'@5-1':>7}{'g@5-1':>8}{'roll>5-1':>9}")
    for label, s_ in summary.items():
        print(f"{label:<28}{s_['place']:>8.3f}{s_['three_stars']:>7.2f}"
              f"{s_['hit_rate']:>7.1%}{s_['rolls']:>7.1f}{s_['level']:>7.2f}"
              f"{s_['gold']:>7.1f}{s_['reached_surplus']:>7.1%}"
              f"{(s_['gold_at_surplus'] or 0):>8.1f}"
              f"{(s_['rolls_after_surplus'] or 0):>9.1f}")
    print()
    for label, row in deltas.items():
        print(f"{label}: place {row['place']['delta']:+.3f} "
              f"(t={row['place']['t']:+.2f})  "
              f"3star {row['three_stars']['delta']:+.3f} "
              f"(t={row['three_stars']['t']:+.2f})  "
              f"rolls {row['rolls']['delta']:+.1f}")

    if args.json:
        args.json.write_text(json.dumps(
            {"summary": summary, "deltas": deltas,
             "records": {f"{k[0]}/{k[1]}": v for k, v in by_key.items()}}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
