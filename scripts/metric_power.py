"""Is placement the wrong instrument? (doc 99 entry 141)

Every method in this project has closed against the same wall: PPO because
per-decision value is ~46x below its noise (130), ES at 3-6 days of compute
(94), and teacher tuning because the seed-paired standard deviation of
placement differences is **~2.97**, so detecting 0.15 placement needs ~1,570
games per arm. The effects actually on offer are 0.03-0.5. The instrument is
blunter than the thing it measures.

Placement is one quantised number per ~30 rounds. `RoundReport` already carries
`won`, `damage_taken` and `hp_after` **per player per round** -- a signal a
policy change moves every round rather than once a game. This asks whether any
of them is a sharper instrument for the *same* comparison.

Method: one comparison with a real effect (an economy plan against none), run
once, scored several ways. Efficiency is the ratio of t-statistics squared,
because n scales as 1/t^2 -- a metric with twice the t needs a quarter of the
games.

A metric also has to *agree* with placement, or it is sharply measuring
something nobody wants. Correlation against placement is reported alongside,
and a metric that is precise but uncorrelated is worse than useless.

Named outcomes, before the run:

* **A -- a dense metric is sharply better.** Screening moves to it and every
  A/B in this project gets cheaper by the efficiency factor. The teacher and
  econ searches that are currently priced out become affordable.
* **B -- modest gain.** Worth using, does not change what is affordable.
* **C -- no gain.** Placement's noise is the *game's* noise, not the metric's,
  and no re-instrumentation helps. Then the honest answer is that this engine
  costs ~1,500 games per comparison and every plan must budget for it.

    .venv/bin/python scripts/metric_power.py --games 200
"""

from __future__ import annotations

import argparse
import math
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.loader import load_all  # noqa: E402
from engine.match import Match  # noqa: E402
from rl.opponents import FAST8, GreedyPolicy, default_opponent  # noqa: E402


def paired_t(a: list[float], b: list[float]) -> tuple[float, float]:
    diffs = [y - x for x, y in zip(a, b, strict=True)]
    mean = statistics.mean(diffs)
    sd = statistics.stdev(diffs)
    return mean, (mean / (sd / math.sqrt(len(diffs))) if sd else 0.0)


def play(data, econ, seeds: list[int]) -> dict[str, list[float]]:
    """One arm. Seat 0 runs `econ`; seats 1-7 are `TFTEnv`'s own field."""
    out: dict[str, list[float]] = {
        "placement": [], "pvp win rate": [], "damage taken": [],
        "mean hp": [], "rounds": []}
    for seed in seeds:
        policies = [GreedyPolicy(seed=0, econ=econ)] + [
            default_opponent(i) for i in range(1, 8)]
        match = Match(data, policies, seed=seed)
        wins = fights = damage = 0
        hps: list[int] = []
        rounds = 0
        while not match.finished:
            for report in match.play_round():
                if report.player_id != 0:
                    continue
                rounds += 1
                hps.append(report.hp_after)
                damage += report.damage_taken
                if not report.is_pve:
                    fights += 1
                    wins += report.won
        match._finalise_placements()
        out["placement"].append(match.placements[0])
        out["pvp win rate"].append(wins / fights if fights else 0.0)
        out["damage taken"].append(damage)
        out["mean hp"].append(statistics.mean(hps) if hps else 0.0)
        out["rounds"].append(rounds)
    return out


def correlation(xs: list[float], ys: list[float]) -> float:
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return num / (dx * dy) if dx and dy else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=200)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    data = load_all()
    seeds = list(range(args.seed, args.seed + args.games))
    with_econ = play(data, FAST8, seeds)
    without = play(data, None, seeds)

    base = None
    print(f"\nn={args.games} seed-paired; seat 0 fast8 vs no econ\n")
    print(f"{'metric':>16}{'with':>10}{'without':>10}{'diff':>10}{'t':>8}"
          f"{'|r| vs place':>14}{'games needed':>14}")
    for name in with_econ:
        a, b = without[name], with_econ[name]
        diff, t = paired_t(a, b)
        r = abs(correlation(with_econ["placement"], with_econ[name]))
        if base is None:
            base = abs(t)
        # n scales as 1/t^2: what this metric would need to reach the same
        # certainty placement reaches at `--games`.
        need = args.games * (base / abs(t)) ** 2 if t else float("inf")
        print(f"{name:>16}{statistics.mean(b):>10.3f}{statistics.mean(a):>10.3f}"
              f"{diff:>+10.3f}{t:>8.2f}{r:>14.2f}{need:>14.0f}")
    print("\n'games needed' is relative to placement at this n; lower is a "
          "sharper instrument.")


if __name__ == "__main__":
    main()
