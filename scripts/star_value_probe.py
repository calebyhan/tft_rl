"""Is a 3-star worth its slots? (doc 99 entry 112.5)

The reroll mispricing has survived every explanation tried through policy.
Entry 111.2 measured it at **+0.379 (t=+4.82)** against real data, 111.3 ruled
out "a 3-star is worth too little" as an isolated claim, and 112 showed no
change to the field's plan touches it — the line is dominated at every pivot
point tested. 112.4 left one candidate: a **six-unit board of 3-stars losing to
an eight-unit board of 2-stars**, which is "board size dominates" (67, 68, 72)
meeting the reroll archetype head on.

Every number in that chain came from placements — eight seats, an economy, a
shop, elimination order. This asks the question directly in combat, where there
is no policy and no economy to confound it.

Two references, because a raw win rate means nothing on its own:

* **The design heuristic.** TFT is balanced so a 3-star of cost N is roughly a
  2-star of cost N+2. It is community documentation rather than a Riot
  publication, so it is a *reference point*, not ground truth — but a 3-star
  2-cost losing badly to a 2-star 4-cost would be a clear signal, and champion
  star stats here are per-champion arrays straight from the Riot payload rather
  than a computed multiplier, so the engine has no scaling constant to blame.
* **The slot trade.** Six 3-stars against eight 2-stars is the matchup the
  archetypes actually produce. Sweeping the count on both sides separates "a
  3-star is weak" from "two extra bodies are worth more than three star-ups".

Champions are drawn by cost tier and held **fixed across arms** so a result is
not one lucky unit, and traits are reported because a six-unit board activates
fewer breakpoints — which is a real part of the slot trade, not a confound to
be removed.

    .venv/bin/python scripts/star_value_probe.py --trials 60
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.combat import CombatSimulator, place_team  # noqa: E402
from engine.hexgrid import Board  # noqa: E402
from engine.items import ItemRegistry  # noqa: E402
from engine.loader import load_all  # noqa: E402
from engine.traits import active_traits  # noqa: E402
from engine.unit import UnitInstance  # noqa: E402

# `place_team`'s contract is "**row 0 is the front line**" for *both* teams --
# `Board.to_combat` mirrors team 1 onto the far half. So both sides use the same
# rows here.
#
# An earlier version gave team 0 rows 3/2 and team 1 rows 0/1, on the assumption
# that the caller mirrors. That put team 0's melee in its *back* row and its
# ranged in front, and a same-archetype control fight -- which must be 50% by
# symmetry -- read **35.6%** with a -2.38 survivor margin. Every cross-arm
# number taken with it was measuring the handicap.
FRONT = [(0, c) for c in range(7)]
BACK = [(1, c) for c in range(7)]
ENEMY_FRONT = FRONT
ENEMY_BACK = BACK


def pick(data, cost: int, count: int, rng: random.Random) -> list:
    """`count` distinct champions at `cost`, sampled without replacement."""
    pool = sorted({c.id for c in data.champions.values() if c.cost == cost})
    if len(pool) < count:
        raise SystemExit(f"only {len(pool)} champions at cost {cost}, need {count}")
    return [data.champions[i] for i in rng.sample(pool, count)]


def build(champions, star, registry, board, team):
    units, slots = [], []
    front = FRONT if team == 0 else ENEMY_FRONT
    back = BACK if team == 0 else ENEMY_BACK
    n_front = n_back = 0
    for champion in champions:
        unit = UnitInstance(champion, star, registry=registry)
        # Melee forward, ranged back -- the same rule the scripted placement
        # uses, so neither arm gets a positioning advantage.
        if champion.stats.attack_range <= 1:
            slots.append(front[n_front])
            n_front += 1
        else:
            slots.append(back[n_back])
            n_back += 1
        units.append(unit)
    return place_team(units, slots, team=team, board=board)


def fight(data, left, left_star, right, right_star, seed: int) -> tuple[int, int]:
    """Returns (survivors_left, survivors_right) after one deterministic fight."""
    registry = ItemRegistry(data.items, data.config.max_items_per_unit)
    board = Board()
    team0 = build(left, left_star, registry, board, 0)
    team1 = build(right, right_star, registry, board, 1)
    CombatSimulator(team0, team1, data, seed=seed, board=board).run()
    return (sum(1 for u in team0 if u.alive),
            sum(1 for u in team1 if u.alive))


def series(data, left_spec, trials: int, seed0: int = 0):
    """`trials` fights on fresh champion draws; returns win rate and margin."""
    lc, rc = left_spec
    rc_cost, rc_star, rc_n = rc
    lc_cost, lc_star, lc_n = lc
    wins = margin = 0.0
    left_traits = right_traits = 0
    for trial in range(trials):
        rng = random.Random(seed0 + trial)
        left = pick(data, lc_cost, lc_n, rng)
        right = pick(data, rc_cost, rc_n, rng)
        alive_l, alive_r = fight(data, left, lc_star, right, rc_star,
                                 seed=seed0 + trial)
        wins += 1.0 if alive_l > alive_r else 0.5 if alive_l == alive_r else 0.0
        margin += alive_l - alive_r
        left_traits += len(active_traits(
            [UnitInstance(c, lc_star) for c in left], data))
        right_traits += len(active_traits(
            [UnitInstance(c, rc_star) for c in right], data))
    return (wins / trials, margin / trials,
            left_traits / trials, right_traits / trials)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=60)
    args = parser.parse_args()

    data = load_all()

    print("Each row: LEFT vs RIGHT, `trials` fights, champions redrawn per "
          "trial and\nheld identical across the two sides of a row.\n")

    print("--- 1. the design heuristic: a 3-star N is about a 2-star N+2 ---")
    print(f"{'left':<22}{'right':<22}{'win':>7}{'margin':>9}"
          f"{'L traits':>10}{'R traits':>10}")
    for cost in (1, 2, 3):
        win, margin, lt, rt = series(
            data, ((cost, 3, 1), (cost + 2, 2, 1)), args.trials)
        print(f"{f'1x cost-{cost} 3-star':<22}{f'1x cost-{cost + 2} 2-star':<22}"
              f"{win:>7.1%}{margin:>+9.2f}{lt:>10.1f}{rt:>10.1f}")

    print("\n--- 2. the slot trade: 3-stars against more 2-stars ---")
    print(f"{'left':<22}{'right':<22}{'win':>7}{'margin':>9}"
          f"{'L traits':>10}{'R traits':>10}")
    for n_right in (6, 7, 8, 9):
        win, margin, lt, rt = series(
            data, ((2, 3, 6), (3, 2, n_right)), args.trials)
        print(f"{'6x cost-2 3-star':<22}{f'{n_right}x cost-3 2-star':<22}"
              f"{win:>7.1%}{margin:>+9.2f}{lt:>10.1f}{rt:>10.1f}")

    print("\nRow 2 at n_right=8 is the archetype matchup: what `slowroll6` "
          "fields at\nlevel 6 against what `standard` fields at level 8. A win "
          "rate far below 50%\nthere, with row 1 healthy, is the slot trade "
          "rather than the 3-star.")


if __name__ == "__main__":
    main()
