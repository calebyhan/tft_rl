r"""How much of final placement is knowable from the current state? (doc 99 entry 58)

Every warm start prints the same pair of numbers and nothing has ever been done
about the second one::

    critic explained_variance: 0.965 in-sample, 0.228 held-out

PPO's update is driven by *advantage* = return - critic(state). If the critic
cannot predict returns on unseen states, advantages are noise and PPO walks a
good policy in a random direction -- which is the measured symptom, a warm start
degraded by +1.077 (t=+6.27, entry 48).

But **0.228 is uninterpretable without its achievable maximum**, and that
maximum has never been measured. TFT placement depends on shop rolls, item
drops and matchmaking that have not happened yet; some of the return is simply
not a function of the current state. Two worlds fit the same 0.228:

* achievable ~0.9 -- the critic is underfit, and fixing it unblocks PPO.
* achievable ~0.25 -- the critic is already at the ceiling, advantages are
  irreducibly noisy, and no amount of PPO tuning can work. Different problem,
  different response.

**Method.** The engine is deterministic given a seed, so replaying a seed
reproduces a state exactly. Play to round `k`, then replace the match RNG (and
each seat policy's) with an independent stream and play to the end, `R` times.
The spread across those rollouts is variance that the state at round `k` cannot
explain, by construction.

Law of total variance::

    Var(P) = E_s[Var(P | s)] + Var_s(E[P | s])
             \_ irreducible _/   \_ explainable _/

so the best achievable explained variance for *any* critic at round `k` is
``Var_s(E[P|s]) / Var(P)``.

**The between-seed term is corrected for estimation error.** ``E[P|s]`` is
estimated from `R` rollouts, so the observed variance of those means is inflated
by ``W/R``. Subtracting it is the difference between measuring the ceiling and
measuring the ceiling plus one's own sampling noise; both are reported so the
correction is visible rather than assumed.

**What this is a proxy for, stated up front.** It measures placement under
`GreedyPolicy` in all eight seats. The critic actually fits *discounted shaped
returns* for the teacher's seat. The dominant noise terms -- shop, damage rolls,
matchmaking -- are policy-independent to first order, but this is an
approximation and a large gap between the two would itself be worth knowing.

    .venv/bin/python scripts/variance_probe.py --seeds 40 --rollouts 8
"""

from __future__ import annotations

import argparse
import json
import logging
import multiprocessing as mp
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rl.timing import timed  # noqa: E402

_WORKER: dict = {}

# A prime offset so a fork's RNG stream cannot coincide with the base seed's.
# Reusing `seed` directly is exactly the defect that made a search arm look
# clairvoyant in entry 54; the same mistake is available here.
FORK_SEED_OFFSET = 7_001_003


def _init() -> None:
    from engine.loader import load_all

    logging.getLogger("engine.loader").setLevel(logging.ERROR)
    _WORKER["data"] = load_all()


def _rollout(task: tuple[int, int, int]) -> tuple[int, int, int, int]:
    """Replay `seed` to round `fork_round`, then diverge under `rollout`."""
    from engine.match import Match
    from rl.opponents import GreedyPolicy

    seed, fork_round, rollout = task
    data = _WORKER["data"]
    match = Match(
        data, [GreedyPolicy(seed=seed * 100 + i) for i in range(8)], seed=seed
    )
    fork_seed = FORK_SEED_OFFSET + rollout * 7919 + seed
    played = 0
    while not match.finished:
        if played == fork_round:
            match.rng = random.Random(fork_seed)
            for i, policy in enumerate(match.policies):
                rng = getattr(policy, "rng", None)
                if isinstance(rng, random.Random):
                    rng.seed(fork_seed * 100 + i)
        match.play_round()
        played += 1
    match._finalise_placements()
    return seed, fork_round, rollout, match.placements[0]


def decompose(by_seed: dict[int, list[int]], rollouts: int) -> dict:
    """Split placement variance into irreducible and explainable parts."""
    within = [statistics.variance(v) for v in by_seed.values() if len(v) > 1]
    means = [statistics.mean(v) for v in by_seed.values()]
    w = statistics.mean(within) if within else 0.0
    between_raw = statistics.variance(means) if len(means) > 1 else 0.0
    # Remove the sampling noise in each seed's mean, which inflates `between`.
    between = max(between_raw - w / rollouts, 0.0)
    total = between + w
    return {
        "within": w,
        "between_raw": between_raw,
        "between": between,
        "total": total,
        "ev_max": between / total if total > 0 else 0.0,
        "ev_max_uncorrected": (
            between_raw / (between_raw + w) if (between_raw + w) > 0 else 0.0
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=40)
    parser.add_argument("--rollouts", type=int, default=8)
    parser.add_argument(
        "--fork-rounds", type=int, nargs="+", default=[6, 12, 18, 24],
        help="rounds played before the RNG is replaced; a typical game is ~37",
    )
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--json", type=Path, default=Path("runs/variance_probe.json"))
    args = parser.parse_args()

    tasks = [
        (seed, fork, rollout)
        for fork in args.fork_rounds
        for seed in range(args.seeds)
        for rollout in range(args.rollouts)
    ]
    print(
        f"{len(tasks)} rollouts: {args.seeds} seeds x {len(args.fork_rounds)} "
        f"fork points x {args.rollouts} rollouts"
    )

    context = mp.get_context("spawn")
    results: dict[int, dict[int, list[int]]] = {f: {} for f in args.fork_rounds}
    with timed("variance_probe", rollouts=len(tasks), workers=args.workers):
        with context.Pool(processes=args.workers, initializer=_init) as pool:
            for i, (seed, fork, _, placement) in enumerate(
                pool.imap_unordered(_rollout, tasks, chunksize=4), 1
            ):
                results[fork].setdefault(seed, []).append(placement)
                if i % 200 == 0:
                    print(f"  {i}/{len(tasks)}", flush=True)

    print(
        f"\n{'fork round':>11}{'irreducible':>13}{'explainable':>13}"
        f"{'total':>9}{'EV ceiling':>12}{'(uncorr)':>10}"
    )
    summary = {}
    for fork in args.fork_rounds:
        d = decompose(results[fork], args.rollouts)
        summary[fork] = d
        print(
            f"{fork:>11}{d['within']:>13.3f}{d['between']:>13.3f}"
            f"{d['total']:>9.3f}{d['ev_max']:>12.3f}"
            f"{d['ev_max_uncorrected']:>10.3f}"
        )

    print(
        "\n'EV ceiling' is the best explained variance ANY critic could reach "
        "predicting final placement from the state at that round."
    )
    mid = summary[args.fork_rounds[len(args.fork_rounds) // 2]]["ev_max"]
    print(f"Our critic measures 0.228 held-out; the mid-game ceiling is {mid:.3f}.")
    if mid < 0.35:
        print(
            "  -> the critic is near the ceiling. Advantages are mostly noise "
            "and this is a reward/credit-assignment problem, not a tuning one."
        )
    else:
        print(
            "  -> real headroom in the critic. Fitting it better is worth doing "
            "before concluding anything about PPO."
        )

    args.json.write_text(json.dumps(
        {"summary": {str(k): v for k, v in summary.items()},
         "placements": {str(f): {str(s): p for s, p in by.items()}
                        for f, by in results.items()}}, indent=1))
    print(f"per-rollout results: {args.json}")


if __name__ == "__main__":
    main()
