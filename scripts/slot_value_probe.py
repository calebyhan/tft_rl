"""What is a board slot worth, and what is a star-up worth? (doc 99 entry 114)

Entry 113 measured that `slowroll6`'s real boards lose to `standard`'s at 36.4%
carrying *more* value on 1.44 fewer units, and 113.5's trait test found
breakpoints explain only about a quarter of it. The claim -- a slot is worth
more than the value in it -- is still an inference from two archetypes that
differ in several ways at once.

This prices both sides of the trade directly. Take one captured board, perturb
exactly one thing, and fight the perturbed board against an *unperturbed*
opponent drawn from the same pool:

* **drop k** -- remove the k weakest units (by star, then cost). What a slot is
  worth.
* **upgrade k** -- promote k units from 2-star to 3-star, weakest first, so the
  upgraded units are the ones a reroll plan would actually have starred. What a
  star-up is worth.

Everything else -- champions, items, positions, the opponent pool -- is held
fixed, so the difference in survivor margin is the price of that one change.
`slowroll6` trades about 1.44 slots for about 1.33 star-ups; if a slot prices
higher than a star-up, 113.4 is confirmed as a statement about the engine rather
than about two policies.

The **k=0 row is a control** and must read ~0.00: it is the same board against
the same pool with nothing changed.

    .venv/bin/python scripts/slot_value_probe.py 300 900
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.combat import CombatSimulator, place_team  # noqa: E402
from engine.hexgrid import Board  # noqa: E402
from engine.items import ItemRegistry  # noqa: E402
from engine.loader import load_all  # noqa: E402
from engine.match import Match  # noqa: E402
from engine.unit import UnitInstance  # noqa: E402
from rl.opponents import DEFAULT_FIELD, GreedyPolicy  # noqa: E402

GAMES = int(sys.argv[1]) if len(sys.argv) > 1 else 300
FIGHTS = int(sys.argv[2]) if len(sys.argv) > 2 else 900

# `place_team` treats row 0 as the front line for *both* teams; `to_combat`
# mirrors team 1. Passing pre-mirrored rows put one side's melee in its back
# row and broke a symmetric control at 35.6% (doc 99 entry 113.1).
FRONT = [(0, c) for c in range(7)]
BACK = [(1, c) for c in range(7)]

data = load_all()


def capture(games: int) -> list[list[tuple[str, int, tuple[str, ...]]]]:
    """Final `standard` boards. One archetype only, so the pool is homogeneous
    and a perturbation is the only thing distinguishing the two sides."""
    out = []
    for game in range(games):
        match = Match(
            data,
            [GreedyPolicy(seed=s, econ=DEFAULT_FIELD[s]) for s in range(8)],
            seed=game,
        )
        final = {}
        while not match.finished:
            for player in match.living_players:
                final[player.player_id] = [
                    (u.champion.id, u.star_level, tuple(i.id for i in u.items))
                    for u in player.board_units
                ]
            match.play_round()
        for index, player in enumerate(match.players):
            if DEFAULT_FIELD[index].name != "standard":
                continue
            spec = final.get(player.player_id)
            if spec:
                out.append(spec)
    return out


def weakest_first(spec):
    """The order a player sheds or upgrades units: worst star, then worst cost."""
    return sorted(range(len(spec)),
                  key=lambda i: (spec[i][1], data.champions[spec[i][0]].cost))


def drop(spec, k):
    if k <= 0:
        return list(spec)
    doomed = set(weakest_first(spec)[:k])
    return [u for i, u in enumerate(spec) if i not in doomed]


def upgrade(spec, k):
    """Promote k 2-stars to 3-star, weakest first. Units already at 3 are
    skipped, so `applied` reports how many upgrades actually happened -- a row
    whose boards had nothing to upgrade would otherwise read as a null."""
    out = list(spec)
    applied = 0
    for i in weakest_first(spec):
        if applied >= k:
            break
        cid, star, items = out[i]
        if star == 2:
            out[i] = (cid, 3, items)
            applied += 1
    return out, applied


def build(spec, registry, board, team):
    units, slots = [], []
    n_front = n_back = 0
    for cid, star, item_ids in spec:
        champion = data.champions[cid]
        if champion.stats.attack_range <= 1 and n_front < len(FRONT):
            slots.append(FRONT[n_front])
            n_front += 1
        elif n_back < len(BACK):
            slots.append(BACK[n_back])
            n_back += 1
        else:
            slots.append(FRONT[n_front])
            n_front += 1
        units.append(UnitInstance(
            champion, star, [data.items[i] for i in item_ids], registry=registry))
    return place_team(units, slots, team=team, board=board)


def fight(spec_l, spec_r, seed):
    registry = ItemRegistry(data.items, data.config.max_items_per_unit)
    board = Board()
    team0 = build(spec_l, registry, board, 0)
    team1 = build(spec_r, registry, board, 1)
    CombatSimulator(team0, team1, data, seed=seed, board=board).run()
    return (sum(1 for u in team0 if u.alive),
            sum(1 for u in team1 if u.alive))


def main() -> None:
    boards = capture(GAMES)
    print(f"{GAMES} games -> {len(boards)} standard boards; "
          f"{FIGHTS} fights per row\n")

    def series(perturb, k):
        rng = random.Random(1000 + k)
        margin = wins = applied_total = 0.0
        for trial in range(FIGHTS):
            base = rng.choice(boards)
            other = rng.choice(boards)
            if perturb == "drop":
                mine, applied = drop(base, k), k
            else:
                mine, applied = upgrade(base, k)
            alive_l, alive_r = fight(mine, other, seed=trial)
            margin += alive_l - alive_r
            wins += 1.0 if alive_l > alive_r else 0.5 if alive_l == alive_r else 0.0
            applied_total += applied
        return margin / FIGHTS, wins / FIGHTS, applied_total / FIGHTS

    print(f"{'perturbation':<20}{'margin':>9}{'win':>8}{'applied':>9}"
          f"{'per unit':>10}")
    base_margin, base_win, _ = series("drop", 0)
    print(f"{'none (control)':<20}{base_margin:>+9.2f}{base_win:>8.1%}"
          f"{0.0:>9.2f}{'--':>10}")

    for k in (1, 2, 3):
        margin, win, _ = series("drop", k)
        per = (margin - base_margin) / k
        print(f"{f'drop {k} weakest':<20}{margin:>+9.2f}{win:>8.1%}"
              f"{float(k):>9.2f}{per:>+10.2f}")

    for k in (1, 2, 3):
        margin, win, applied = series("upgrade", k)
        per = (margin - base_margin) / applied if applied else float("nan")
        print(f"{f'upgrade {k} to 3*':<20}{margin:>+9.2f}{win:>8.1%}"
              f"{applied:>9.2f}{per:>+10.2f}")

    print("\n`per unit` is the change in survivor margin per slot removed or "
          "per star-up\napplied. If dropping a slot costs more than a star-up "
          "gains, the reroll trade\nis negative in this engine by construction "
          "(doc 99 entry 113.4).")


if __name__ == "__main__":
    main()
