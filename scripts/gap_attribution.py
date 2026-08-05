"""Where is the clone's 0.507 gap to its teacher? (doc 99 entry 50)

49.1 measured the best clone at 0.507 placement behind the scripted policy it
was cloned from (t=+3.31, n=300). This asks *which decisions* that gap lives in.

**Attribution by placement, not by agreement.** The obvious approach -- compare
per-kind action match -- has failed to predict placement five separate times in
this project (45.6 raised match 76.8% -> 81.9% and moved placement t=-1.43).
So instead of asking where the policies disagree, this hands the teacher
*authority* over one kind of decision at a time and measures what placement
comes back. A kind where the teacher's judgement is worth nothing recovers
nothing, however much the two policies disagree there.

The hybrid asks the teacher what it would do; if that falls in the delegated
group the teacher's action is used, otherwise the clone decides. Two controls
bound the scale: delegating nothing must reproduce the clone, and delegating
everything must reproduce the teacher. If either control misses, the harness is
wrong and no attribution from it means anything.

SELECT and PLACE are delegated together. They are one two-step interaction --
a PLACE names a destination for the unit a SELECT picked up, so splitting them
would have the teacher placing a unit the clone chose, which is neither policy.

    .venv/bin/python scripts/gap_attribution.py runs/reclone-rowhead --episodes 300
"""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rl.action import ActionKind  # noqa: E402
from rl.evaluate import EvalResult, evaluate  # noqa: E402
from rl.timing import timed  # noqa: E402

# Delegation groups. Ordered so the two controls bracket the real arms.
GROUPS: dict[str, tuple[ActionKind, ...]] = {
    "none (= clone)": (),
    "BUY": (ActionKind.BUY,),
    "SELL": (ActionKind.SELL,),
    "MOVE (SELECT+PLACE)": (ActionKind.SELECT, ActionKind.PLACE),
    "EQUIP": (ActionKind.EQUIP,),
    "ECON (REROLL+BUY_XP)": (ActionKind.REROLL, ActionKind.BUY_XP),
    "PICK (augment+offering)": (ActionKind.PICK_AUGMENT, ActionKind.PICK_OFFERING),
    "all (= teacher)": tuple(ActionKind),
}

_WORKER: dict = {}


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
    expert = {
        "sell_bench": bool(args.get("expert_sell", False)),
        "buy_synergy": flags,
        "match_items": flags,
        "corner_carry": flags,
        "roll_at_level": args.get("expert_roll_at_level", 0) or 0,
    }
    env = {
        "copy_counts": bool(args.get("copy_counts", False)),
        "champion_encoding": args.get("champion_encoding", "index"),
        "scouting": args.get("scouting", "summary"),
    }
    return expert, env


def _init(run_dir: str, env_kwargs: dict, expert_kwargs: dict, kinds: tuple) -> None:
    import logging

    import torch
    from sb3_contrib import MaskablePPO

    from engine.loader import load_all
    from rl.env import TFTEnv
    from rl.evaluate import sb3_policy, scripted_policy

    logging.getLogger("engine.loader").setLevel(logging.ERROR)
    torch.set_num_threads(1)
    data = load_all()
    env = TFTEnv(data=data, **env_kwargs)
    _WORKER["env"] = env
    clone = sb3_policy(MaskablePPO.load(run_dir, device="cpu"))
    teacher = scripted_policy(env, **expert_kwargs)
    space = env.action_space_helper
    delegated = set(kinds)

    def hybrid(obs, mask):
        if not delegated:
            return clone(obs, mask)
        proposed = teacher(obs, mask)
        if space.decode(proposed).kind in delegated:
            return proposed
        return clone(obs, mask)

    _WORKER["policy"] = hybrid


def _episode(seed: int):
    result = evaluate(_WORKER["env"], _WORKER["policy"], seeds=[seed])
    return seed, result.placements[0], result.rewards[0], result.rounds[0]


def run_group(run_dir: Path, seeds, kinds, workers, env_kwargs, expert_kwargs):
    context = mp.get_context("spawn")
    with context.Pool(
        processes=workers,
        initializer=_init,
        initargs=(str(run_dir / "model"), env_kwargs, expert_kwargs, tuple(kinds)),
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
    parser.add_argument("run", type=Path)
    parser.add_argument("--episodes", type=int, default=300)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument(
        "--complement",
        action="store_true",
        help=(
            "invert every group: the teacher takes authority over everything "
            "EXCEPT the named kinds. A kind that hurts when delegated because "
            "the teacher's choice does not fit the clone's later play should "
            "behave differently under inversion than one that is simply hard "
            "(doc 99 entry 50)"
        ),
    )
    args = parser.parse_args()

    seeds = list(range(args.episodes))
    expert_kwargs, env_kwargs = config_for(args.run)

    groups = GROUPS
    if args.complement:
        every = set(ActionKind)
        groups = {
            ("all but " + name if kinds and len(kinds) < len(every) else name):
                tuple(sorted(every - set(kinds)))
            for name, kinds in GROUPS.items()
        }

    results = {}
    with timed("gap_attribution", episodes=args.episodes,
               arms=len(groups), workers=args.workers):
        for name, kinds in groups.items():
            results[name] = run_group(
                args.run, seeds, kinds, args.workers, env_kwargs, expert_kwargs
            )
            print(f"  {name:<26} {results[name].avg_placement:.3f}", flush=True)

    # Under --complement the labels swap roles: delegating "none" of the
    # complement is delegating everything, i.e. the teacher.
    clone_key = "all (= teacher)" if args.complement else "none (= clone)"
    teacher_key = "none (= clone)" if args.complement else "all (= teacher)"
    clone = results[clone_key]
    teacher = results[teacher_key]
    gap = clone.avg_placement - teacher.avg_placement
    print(f"\nclone {clone.avg_placement:.3f}  teacher {teacher.avg_placement:.3f}  "
          f"gap {gap:+.3f}")
    print(f"\n{'delegated to teacher':<26}{'place':>8}{'recovered':>11}"
          f"{'% of gap':>10}{'vs clone (paired)':>22}")
    for name, r in results.items():
        recovered = clone.avg_placement - r.avg_placement
        share = recovered / gap if gap else 0.0
        mean, t = paired_t(clone.placements, r.placements)
        delta = "" if name == "none (= clone)" else f"{mean:+.3f}  t={t:+.2f}"
        print(f"{name:<26}{r.avg_placement:>8.3f}{recovered:>+11.3f}"
              f"{share:>9.0%}{delta:>22}")
    print("\nRecovered = how much of the clone-teacher gap this kind buys back. "
          "Shares need not sum to 100%: decisions interact.")

    if args.json:
        args.json.write_text(json.dumps(
            {name: {"placements": r.placements, "avg_placement": r.avg_placement}
             for name, r in results.items()}, indent=1))
        print(f"per-episode results: {args.json}")


if __name__ == "__main__":
    main()
