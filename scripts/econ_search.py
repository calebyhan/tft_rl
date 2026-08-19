"""Search the `EconStrategy` parameter space jointly (doc 99 entry 142).

Entry 72 compared four **hand-written archetypes** and picked the best. Nobody
has searched the parameters themselves, and they interact: when to roll depends
on when to level, which depends on what is being rolled for. Every existing A/B
script (`surplus_rolldown_ab`, `cost3_seat_ab`, `keep_pairs_ab`,
`desperation_ab`) varies one at a time, which is the method that misses the
optimum in a coupled space.

**Priced before running, per 141.2.** The seed-paired sd of placement
differences is ~2.97, so n=200 resolves ~0.42 at t=2. This search can only find
*large* effects, and 141 measured native `fast8` vs `standard` at +0.033, which
argues the space may not contain any. Run anyway, with that stated up front.

Two-stage, because selecting the best of many noisy estimates is winner's
curse:

1. **Screen** every candidate on shared seeds (CRN), n=`--screen`.
2. **Confirm** the top few on **fresh seeds** at n=`--confirm`. Re-running the
   screen seeds would re-confirm the luck that won the screen, not the
   strategy. This is the axis that discriminates.

Named outcomes, before the run:

* **A -- a real improvement.** Some vector beats `fast8` by >= 0.4 on held-out
  seeds at t >= 2. Ship it as the teacher's econ; 75 says imitation transmits
  ~89% of a teacher gain.
* **B -- winner's curse.** Candidates win the screen and regress on held-out
  seeds. The space holds no large effects and 141's pricing stands.
* **C -- nothing wins even the screen.**

    .venv/bin/python scripts/econ_search.py --candidates 60 --screen 200
"""

from __future__ import annotations

import argparse
import math
import multiprocessing as mp
import random
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.match import Match  # noqa: E402
from rl.opponents import (  # noqa: E402
    FAST8,
    STANDARD,
    EconStrategy,
    GreedyPolicy,
    default_opponent,
)

# Rounds a plan can name. x-4 is a carousel and x-7 the stage's last combat;
# the curve only ever needs breakpoints, not every label.
LABELS = [f"{stage}-{r}" for stage in (2, 3, 4, 5) for r in range(1, 8)] + ["6-1"]

_DATA = None


def _init():
    global _DATA
    from engine.loader import load_all
    _DATA = load_all()


def _play(job):
    """One game. Seat 0 runs the candidate; seats 1-7 are `TFTEnv`'s field."""
    genome, seed = job
    econ = to_strategy(genome)
    policies = [GreedyPolicy(seed=0, econ=econ)] + [
        default_opponent(i) for i in range(1, 8)]
    match = Match(_DATA, policies, seed=seed)
    while not match.finished:
        match.play_round()
    match._finalise_placements()
    return match.placements[0]


def to_strategy(genome: dict) -> EconStrategy | None:
    """Genome -> `EconStrategy`. `None` is the no-econ control."""
    if genome is None:
        return None
    if "preset" in genome:
        return {"fast8": FAST8, "standard": STANDARD}[genome["preset"]]
    levels = {label: lvl for lvl, label in zip(range(5, 10), genome["levels"], strict=True)}
    floors = {genome["roll_at"]: genome["roll_floor"]}
    if genome["restore_at"]:
        floors[genome["restore_at"]] = genome["save_floor"]
    return EconStrategy(
        name="candidate",
        level_targets=levels,
        roll_floors=floors,
        save_floor=genome["save_floor"],
        desperation_hp=genome["desperation_hp"],
    )


def sample(rng: random.Random) -> dict:
    """A monotone level curve, one roll-down window, and the two gold knobs."""
    picks = sorted(rng.sample(range(len(LABELS)), 5))
    levels = [LABELS[i] for i in picks]
    roll_index = rng.randrange(picks[1], len(LABELS))
    restore = ""
    if rng.random() < 0.7 and roll_index + 1 < len(LABELS):
        # "Roll down once then rebuild" vs "roll the surplus forever" are the
        # two shapes the docstring says matter; both must be reachable.
        restore = LABELS[min(roll_index + rng.choice((1, 2)), len(LABELS) - 1)]
    return {
        "levels": levels,
        "roll_at": LABELS[roll_index],
        "roll_floor": rng.choice((0, 10, 20, 30, 40, 50)),
        "restore_at": restore,
        "save_floor": rng.choice((30, 40, 50, 60)),
        "desperation_hp": rng.choice((0, 0, 15, 25, 35)),
    }


def paired_t(a: list[float], b: list[float]) -> tuple[float, float]:
    diffs = [y - x for x, y in zip(a, b, strict=True)]
    mean = statistics.mean(diffs)
    sd = statistics.stdev(diffs)
    return mean, (mean / (sd / math.sqrt(len(diffs))) if sd else 0.0)


def evaluate(pool, genome, seeds) -> list[float]:
    return pool.map(_play, [(genome, s) for s in seeds], chunksize=4)


def describe(genome: dict) -> str:
    if genome is None:
        return "(no econ)"
    if "preset" in genome:
        return genome["preset"]
    return (f"lv{'/'.join(genome['levels'])} roll@{genome['roll_at']}"
            f"->{genome['roll_floor']} restore@{genome['restore_at'] or '-'}"
            f" save{genome['save_floor']} desp{genome['desperation_hp']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=int, default=60)
    parser.add_argument("--screen", type=int, default=200)
    parser.add_argument("--confirm", type=int, default=800)
    parser.add_argument("--finalists", type=int, default=3)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    screen_seeds = list(range(args.screen))
    # Disjoint from the screen, so a confirmation cannot inherit its luck.
    confirm_seeds = list(range(100_000, 100_000 + args.confirm))

    arms = {"fast8": {"preset": "fast8"}, "standard": {"preset": "standard"}}
    for i in range(args.candidates):
        arms[f"c{i:02d}"] = sample(rng)

    with mp.Pool(args.workers, initializer=_init) as pool:
        print(f"screening {len(arms)} arms at n={args.screen}", flush=True)
        screened = {}
        for name, genome in arms.items():
            screened[name] = evaluate(pool, genome, screen_seeds)
            print(f"  {name:>8} {statistics.mean(screened[name]):.3f}", flush=True)

        ranked = sorted(screened, key=lambda k: statistics.mean(screened[k]))
        print(f"\nscreen top {args.finalists + 2}:")
        for name in ranked[:args.finalists + 2]:
            d, t = paired_t(screened["fast8"], screened[name])
            print(f"  {name:>8} {statistics.mean(screened[name]):.3f}"
                  f"  vs fast8 {d:+.3f} t {t:+.2f}   {describe(arms[name])}")

        finalists = [n for n in ranked if n != "fast8"][:args.finalists]
        finalists.append("fast8")
        print(f"\nconfirming {finalists} on {args.confirm} FRESH seeds",
              flush=True)
        confirmed = {}
        for name in finalists:
            confirmed[name] = evaluate(pool, arms[name], confirm_seeds)
            print(f"  {name:>8} {statistics.mean(confirmed[name]):.3f}", flush=True)

    print(f"\n=== held-out, n={args.confirm} ===")
    print(f"{'arm':>8}{'screen':>9}{'held-out':>10}{'regression':>12}"
          f"{'vs fast8':>10}{'t':>8}")
    for name in finalists:
        s = statistics.mean(screened[name])
        h = statistics.mean(confirmed[name])
        d, t = paired_t(confirmed["fast8"], confirmed[name])
        print(f"{name:>8}{s:>9.3f}{h:>10.3f}{h - s:>+12.3f}"
              f"{d:>+10.3f}{t:>8.2f}")
    for name in finalists:
        if name != "fast8":
            print(f"  {name}: {describe(arms[name])}")


if __name__ == "__main__":
    main()
