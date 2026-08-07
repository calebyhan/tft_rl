"""How much do the unverifiable combat constants actually matter?

Doc 99 entry 76.3 left `movement_hexes_per_second`,
`projectile_hexes_per_second` and the `sudden_death_*` pair unvalidated.
Unlike the xp table (70.1) or the mitigation curve (76.4), **these cannot be
validated**: Riot does not publish them, `config.unverified` says so, and a
search found no source.

Validation being impossible does not make the risk unmeasurable. The
decision-relevant question is not "is 2.0 hexes/second correct" but **"would
anything we conclude change if it were 1.0 or 4.0"**. That is a sensitivity
analysis, and this project has never run one.

Two probes, chosen because both are *ratios* rather than placements. Placement
is zero-sum across eight seats and a global constant moves every seat at once,
so an agent's placement can sit still while combat changes underneath it --
which would look like insensitivity and would be an artefact of the metric.

* **star-vs-slots exchange rate** (76.1): does a 6-unit 3-star board still beat
  an 8-unit 2-star one? This is the axis the whole reroll question turns on.
* **combat duration**: how long fights run, and how often they hit the timeout.
  A constant that pushes fights into sudden death changes which comps win.

`dataclasses.replace` overrides in memory. `data/config.json` is hand-curated
and carries a provenance block; nothing here writes to it.

    .venv/bin/python scripts/combat_sensitivity.py --trials 60
"""

from __future__ import annotations

import argparse
import dataclasses
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.combat import CombatSimulator, place_team  # noqa: E402
from engine.hexgrid import Board  # noqa: E402
from engine.loader import load_all  # noqa: E402
from engine.unit import UnitInstance  # noqa: E402


def _slots(n: int) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    row, col = 0, 0
    while len(out) < n:
        out.append((row, col))
        col += 1
        if col >= 7:
            col, row = 0, row + 1
    return out


def matchup(data, pool, small_n, small_star, big_n, big_star, trials):
    """Win rate of the small high-star board, plus fight duration stats."""
    rng = random.Random(0)
    wins = 0
    durations: list[float] = []
    timeouts = 0
    for trial in range(trials):
        picks = rng.sample(pool, max(small_n, big_n))
        board = Board()
        a = [UnitInstance(data.champions[c], small_star) for c in picks[:small_n]]
        b = [UnitInstance(data.champions[c], big_star) for c in picks[:big_n]]
        place_team(a, _slots(small_n), team=0, board=board)
        place_team(b, _slots(big_n), team=1, board=board)
        result = CombatSimulator(a, b, data, seed=trial, board=board).run()
        wins += result.winner == 0
        durations.append(result.duration)
        timeouts += bool(result.timed_out)
    return wins / trials, statistics.mean(durations), timeouts / trials


def with_combat(data, **overrides):
    """A copy of `data` whose combat config carries `overrides`."""
    combat = dataclasses.replace(data.config.combat, **overrides)
    config = dataclasses.replace(data.config, combat=combat)
    return dataclasses.replace(data, config=config)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=60)
    parser.add_argument("--cost", type=int, default=2)
    args = parser.parse_args()

    base = load_all()
    pool = sorted(c.id for c in base.champions.values() if c.cost == args.cost)
    c = base.config.combat

    sweeps: list[tuple[str, dict]] = [
        ("baseline", {}),
        ("move 1.0 (half)", {"movement_hexes_per_second": 1.0}),
        ("move 4.0 (double)", {"movement_hexes_per_second": 4.0}),
        ("projectile 6", {"projectile_hexes_per_second": 6.0}),
        ("projectile 24", {"projectile_hexes_per_second": 24.0}),
        ("sudden death 15s", {"sudden_death_start_seconds": 15.0}),
        ("sudden death 45s", {"sudden_death_start_seconds": 45.0}),
        ("sd dmg 1%/s", {"sudden_death_damage_pct_per_second": 0.01}),
        ("sd dmg 6%/s", {"sudden_death_damage_pct_per_second": 0.06}),
    ]

    print(f"cost {args.cost}, {args.trials} fights per cell. "
          f"baseline: move={c.movement_hexes_per_second} "
          f"proj={c.projectile_hexes_per_second} "
          f"sd_start={c.sudden_death_start_seconds} "
          f"sd_dmg={c.sudden_death_damage_pct_per_second}\n")
    # Pick a matchup that is not saturated. 6x3* vs 8x2* is 100% at baseline
    # (entry 76.1), and a metric pinned at its ceiling cannot show sensitivity
    # even where sensitivity exists -- the floor-effect trap of entries 18.5
    # and 52.1. Calibrate on the baseline config first, then sweep whichever
    # matchup sits closest to a coin flip, where the metric has room to move.
    candidates = [
        (6, 3, 8, 2), (6, 3, 9, 2), (5, 3, 9, 2), (4, 3, 9, 2), (3, 3, 9, 2),
        (7, 2, 8, 2), (6, 2, 8, 2), (8, 2, 9, 2),
    ]
    print("calibrating (baseline config):")
    scored = []
    for sn, ss, bn, bs in candidates:
        rate, _dur, _to = matchup(base, pool, sn, ss, bn, bs, args.trials)
        scored.append((abs(rate - 0.5), rate, (sn, ss, bn, bs)))
        print(f"  {sn}x{ss}* vs {bn}x{bs}*: {rate:.1%}", flush=True)
    scored.sort()
    _, base_rate, (sn, ss, bn, bs) = scored[0]
    label = f"{sn}x{ss}* beats {bn}x{bs}*"
    print(f"\nsweeping {label} (baseline {base_rate:.1%}, "
          "closest to a coin flip)\n")

    print(f"{'variant':<20}{label:>19}{'mean dur':>10}{'timeout':>9}")
    rows = []
    for name, override in sweeps:
        data = base if not override else with_combat(base, **override)
        rate, dur, timeout = matchup(data, pool, sn, ss, bn, bs, args.trials)
        rows.append((name, rate, dur, timeout))
        print(f"{name:<20}{rate:>18.1%}{dur:>10.1f}{timeout:>9.1%}", flush=True)

    baseline_rate = rows[0][1]
    worst = max(rows[1:], key=lambda r: abs(r[1] - baseline_rate))
    print(f"\nlargest swing in the exchange rate: {worst[0]} "
          f"({worst[1]:.1%} vs baseline {baseline_rate:.1%}, "
          f"delta {worst[1] - baseline_rate:+.1%})")
    print("\nA small swing means these approximations do not carry the "
          "conclusions that\nrest on them, and `config.unverified` can say so. "
          "A large one means a number\nnobody can source is deciding which "
          "strategies work.")


if __name__ == "__main__":
    main()
