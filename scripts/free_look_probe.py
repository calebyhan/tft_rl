"""Do free shop looks behave like paid ones? (doc 99 entry 160.84).

The first ``K`` rerolls each round cost the carrying seat nothing. This is a
harness intervention, not a policy: no seat observes it and it is not
deployable. It exists to test 160.82's reading that the binding constraint on
3-stars is shop looks rather than copies -- which predicts free looks should
show the same contention gradient paid ones did.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine import player as player_mod  # noqa: E402
from engine.loader import load_all  # noqa: E402
from engine.match import Match  # noqa: E402
from rl.opponents import HYPERROLL, GreedyPolicy  # noqa: E402
from scripts.surplus_roll_ab import SEAT, fields, paired_t, summarise  # noqa: E402

_DATA = None


def _init() -> None:
    global _DATA
    _DATA = load_all()


def play_one(job: tuple[int, int, str] | tuple[int, int, str, int]) -> dict:
    """One game granting ``SEAT`` free rolls, gold, or nothing, each round.

    ``gold_per_round`` is the value-matched alternative of doc 99 entry 160.87:
    a reroll costs 2, so ``K`` free rolls and ``2K`` gold are the same grant in
    two currencies.
    """
    free_rolls, seed, field_name, gold_per_round = (*job, 0)[:4]
    data = _DATA if _DATA is not None else load_all()
    field = fields()[field_name]
    econs = [field[s % len(field)] for s in range(8)]
    econs[SEAT] = HYPERROLL

    rolls: Counter = Counter()
    used = {"this_round": 0}
    real_reroll = player_mod.PlayerState.reroll

    def patched_reroll(self, pool, rng):
        rolls[self.player_id] += 1
        if self.player_id == SEAT and used["this_round"] < free_rolls:
            used["this_round"] += 1
            # The look without the price: refresh the shop, charge nothing.
            return self.shop.roll(self.level, pool, rng)
        return real_reroll(self, pool, rng)

    player_mod.PlayerState.reroll = patched_reroll
    try:
        policies = [GreedyPolicy(seed=s, econ=econs[s]) for s in range(8)]
        match = Match(data, policies, seed=seed)
        best = 0
        while not match.finished:
            used["this_round"] = 0
            if gold_per_round:
                granted = next(
                    (p for p in match.living_players if p.player_id == SEAT), None
                )
                if granted is not None:
                    granted.gold += gold_per_round
            seat_player = next(
                (p for p in match.living_players if p.player_id == SEAT), None
            )
            if seat_player is not None:
                best = max(best, sum(
                    1 for unit in seat_player.all_units if unit.star_level == 3
                ))
            match.play_round()
        match._finalise_placements()
        seat_player = next(p for p in match.players if p.player_id == SEAT)
        return {
            "free_rolls": free_rolls,
            "gold_per_round": gold_per_round,
            "arm": (
                f"looks+{free_rolls}" if free_rolls
                else f"gold+{gold_per_round}" if gold_per_round
                else "control"
            ),
            "field": field_name,
            "seed": seed,
            "place": match.placements[SEAT],
            "three_stars": best,
            "hit": 1.0 if best else 0.0,
            "rolls": rolls[SEAT],
            "level": seat_player.level,
            "gold": seat_player.gold,
            "reached_surplus": 1.0,
            "gold_at_surplus": None,
            "rolls_after_surplus": None,
        }
    finally:
        player_mod.PlayerState.reroll = real_reroll


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=300)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--seed0", type=int, default=900)
    parser.add_argument("--free-rolls", type=int, nargs="+", default=[0, 2, 5])
    parser.add_argument(
        "--gold", type=int, nargs="*", default=[],
        help="gold-per-round arms, the second currency of doc 99 entry 160.87",
    )
    parser.add_argument("--fields", nargs="+", default=["rivals0", "rivals3"])
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    grants: list[tuple[int, int]] = [(free, 0) for free in args.free_rolls]
    grants += [(0, gold) for gold in args.gold if gold]

    jobs = [
        (free, args.seed0 + game, field, gold)
        for field in args.fields
        for free, gold in grants
        for game in range(args.games)
    ]
    with Pool(args.workers, initializer=_init) as pool:
        records = pool.map(play_one, jobs, chunksize=4)

    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for record in records:
        by_key[(record["field"], record["arm"])].append(record)
    for group in by_key.values():
        group.sort(key=lambda record: record["seed"])

    names = []
    for free, gold in grants:
        name = f"looks+{free}" if free else f"gold+{gold}" if gold else "control"
        if name not in names:
            names.append(name)

    print(f"{'field/arm':<20}{'place':>8}{'3star':>8}{'hit':>8}{'rolls':>8}"
          f"{'level':>8}{'gold':>8}")
    summary, deltas = {}, {}
    for field in args.fields:
        for name in names:
            s_ = summarise(by_key[(field, name)])
            summary[f"{field}/{name}"] = s_
            print(f"{field + '/' + name:<20}{s_['place']:>8.3f}"
                  f"{s_['three_stars']:>8.2f}{s_['hit_rate']:>8.1%}"
                  f"{s_['rolls']:>8.1f}{s_['level']:>8.2f}{s_['gold']:>8.1f}")
    print()
    for field in args.fields:
        contrasts = [("control", name) for name in names if name != "control"]

        for control, treatment in contrasts:
            if not by_key[(field, control)] or not by_key[(field, treatment)]:
                continue
            row = {}
            for key in ("place", "three_stars", "hit", "rolls", "level", "gold"):
                mean, t = paired_t(
                    [r[key] for r in by_key[(field, control)]],
                    [r[key] for r in by_key[(field, treatment)]],
                )
                row[key] = {"delta": mean, "t": t}
            deltas[f"{field}: {treatment} vs {control}"] = row
            print(f"{field}: {treatment} vs {control}: "
                  f"place {row['place']['delta']:+.3f} "
                  f"(t={row['place']['t']:+.2f})  "
                  f"3star {row['three_stars']['delta']:+.3f} "
                  f"(t={row['three_stars']['t']:+.2f})  "
                  f"rolls {row['rolls']['delta']:+.1f}  "
                  f"endgold {row['gold']['delta']:+.1f}")

    if args.json:
        args.json.write_text(json.dumps(
            {"summary": summary, "deltas": deltas,
             "records": {f"{k[0]}/{k[1]}": v for k, v in by_key.items()}}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
