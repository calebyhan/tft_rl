"""Is the teacher good, or are the opponents just bad? (doc 99 entry 56)

Every number in this project is measured with the agent in one seat and seven
`GreedyPolicy` bots in the others. Eight seats means **4.500 is parity by
construction**, so the teacher's 3.030 says exactly one thing: it beats those
seven bots. Whether that constitutes playing well is untested, and every
downstream figure -- the clone's gap, the value of each decision -- inherits the
question.

This swaps the opponents for a trained policy and re-measures. The arms:

* `teacher vs greedy`  -- the control; must reproduce the known 3.030.
* `teacher vs clones`  -- the real question.
* `clone vs clones`    -- a sanity check that must land near **4.500**: when
  every seat runs the same policy, placement is parity by arithmetic. If this
  arm misses, the harness is wrong and neither other arm means anything.
* `weak-scripted vs clones` -- the *unflagged* scripted policy (the `scripted`
  baseline in every training log, ~4.9 against the bots) against the same
  strong field, to calibrate the scale. `GreedyPolicy` itself cannot fill this
  arm: it plans a whole phase at once rather than acting per step, so it cannot
  drive the agent seat through `evaluate`. Labelling it "greedy" would have
  named an arm after a policy it does not run.

Reading it: if `teacher vs clones` sits near 4.500, the teacher's advantage was
an artefact of weak opposition. If it stays well below, the teacher beats a
genuinely stronger field and 3.030 means more than "beats GreedyPolicy".

    .venv/bin/python scripts/teacher_check.py runs/reclone-rowhead --episodes 300
"""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rl.evaluate import EvalResult, evaluate  # noqa: E402
from rl.timing import timed  # noqa: E402

_WORKER: dict = {}

# (agent, opponents) for each arm.
ARMS = (
    ("teacher", "greedy"),
    ("teacher", "clones"),
    ("clone", "clones"),
    ("weak-scripted", "clones"),
)


def paired_t(a: list[int], b: list[int]) -> tuple[float, float]:
    diffs = [y - x for x, y in zip(a, b, strict=True)]
    n = len(diffs)
    mean = sum(diffs) / n
    if n < 2:
        return mean, 0.0
    var = sum((d - mean) ** 2 for d in diffs) / (n - 1)
    return mean, (mean / math.sqrt(var / n) if var > 0 else 0.0)


def config_for(run_dir: Path) -> tuple[dict, dict]:
    meta = json.loads((run_dir / "metadata.json").read_text())
    args = meta.get("args", meta.get("hyperparameters", {}))
    flags = bool(args.get("expert_flags", False))
    return (
        {
            "sell_bench": bool(args.get("expert_sell", False)),
            "buy_synergy": flags,
            "match_items": flags,
            "corner_carry": flags,
            "roll_at_level": args.get("expert_roll_at_level", 0) or 0,
        },
        {
            "copy_counts": bool(args.get("copy_counts", False)),
            "champion_encoding": args.get("champion_encoding", "index"),
            "scouting": args.get("scouting", "summary"),
        },
    )


def _init(run_dir: str, env_kwargs: dict, expert_kwargs: dict,
          agent: str, opponents: str) -> None:
    import logging

    import torch
    from sb3_contrib import MaskablePPO

    from engine.loader import load_all
    from rl.env import TFTEnv
    from rl.evaluate import sb3_policy, scripted_policy
    from rl.selfplay import SnapshotPool, snapshot_factory

    logging.getLogger("engine.loader").setLevel(logging.ERROR)
    torch.set_num_threads(1)
    data = load_all()
    env = TFTEnv(data=data, **env_kwargs)

    if opponents == "clones":
        model = MaskablePPO.load(run_dir, device="cpu")
        pool = SnapshotPool(capacity=1)
        pool.add(model)
        # `deterministic=False` keeps the seats from being one fixed target;
        # `mix=1.0` puts a trained policy in every opponent seat.
        env.opponent_factory = snapshot_factory(pool, env, mix=1.0, seed=7)

    if agent == "teacher":
        _WORKER["policy"] = scripted_policy(env, **expert_kwargs)
    elif agent == "clone":
        _WORKER["policy"] = sb3_policy(
            MaskablePPO.load(run_dir, device="cpu")
        )
    else:
        # The unflagged scripted policy -- the `scripted` baseline every
        # training log reports at ~4.9 against the bots. Deliberately *not*
        # `GreedyPolicy`, which plans a phase at a time and cannot drive the
        # agent seat at all.
        _WORKER["policy"] = scripted_policy(env)

    _WORKER["env"] = env


def _episode(seed: int):
    result = evaluate(_WORKER["env"], _WORKER["policy"], seeds=[seed])
    return seed, result.placements[0], result.rewards[0], result.rounds[0]


def run_arm(run_dir, seeds, agent, opponents, workers, env_kwargs, expert_kwargs):
    context = mp.get_context("spawn")
    with context.Pool(
        processes=workers,
        initializer=_init,
        initargs=(str(run_dir / "model"), env_kwargs, expert_kwargs,
                  agent, opponents),
    ) as pool:
        rows = list(pool.imap_unordered(_episode, list(seeds)))
    by_seed = {seed: row for seed, *row in rows}
    result = EvalResult(episodes=len(seeds))
    for seed in seeds:
        placement, reward, rounds = by_seed[seed]
        result.placements.append(placement)
        result.rewards.append(reward)
        result.rounds.append(rounds)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="the policy filling opponent seats")
    parser.add_argument("--episodes", type=int, default=300)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    seeds = list(range(args.episodes))
    expert_kwargs, env_kwargs = config_for(args.run)
    print(f"opponent policy: {args.run.name}")

    results = {}
    with timed("teacher_check", episodes=args.episodes,
               arms=len(ARMS), workers=args.workers):
        for agent, opponents in ARMS:
            name = f"{agent} vs {opponents}"
            results[name] = run_arm(
                args.run, seeds, agent, opponents, args.workers,
                env_kwargs, expert_kwargs,
            )
            print(f"  {name:<22}{results[name].avg_placement:.3f}", flush=True)

    print(f"\n{'arm':<22}{'place':>8}{'ci95':>7}{'1st':>7}{'top4':>7}")
    for name, r in results.items():
        print(f"{name:<22}{r.avg_placement:>8.3f}{r.ci95:>7.3f}"
              f"{r.win_rate:>7.1%}{r.top4_rate:>7.1%}")

    control = results["clone vs clones"]
    print(f"\nSANITY: 'clone vs clones' = {control.avg_placement:.3f}; "
          "every seat runs the same policy, so this must be ~4.500.")
    if abs(control.avg_placement - 4.5) > 0.35:
        print("  !! control missed parity -- the harness is wrong and no arm "
              "below should be read.")

    a, b = results["teacher vs greedy"], results["teacher vs clones"]
    mean, t = paired_t(a.placements, b.placements)
    print(f"\nteacher loses {mean:+.3f} placement (t={t:+.2f}) when the bots are "
          "replaced by a trained policy.")
    if b.avg_placement > 4.2:
        print("  -> the teacher is roughly parity against a real policy. Its "
              "3.030 measured weak opposition, not skill.")
    else:
        print("  -> the teacher still beats a genuinely stronger field.")

    if args.json:
        args.json.write_text(json.dumps(
            {n: {"placements": r.placements, "avg_placement": r.avg_placement}
             for n, r in results.items()}, indent=1))


if __name__ == "__main__":
    main()
