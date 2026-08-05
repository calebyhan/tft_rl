"""Is PICK a skill, or a default the clone failed to copy? (doc 99 entry 51)

50.2 measured withholding PICK from the teacher at +0.370 placement, t=+3.21 --
the largest single term in the clone's gap. Then inspection showed the teacher
has **no augment policy at all**: over three games it chose option index 0 for
9 of 9 augments. Its PICK behaviour is the action space's first legal option.

So the 0.370 is not obviously a skill gap. Two readings fit it:

* index 0 is genuinely good (offered choices ordered so the first is strong),
  and the clone fails to find it -- a real, learnable decision; or
* index 0 is arbitrary, and the clone is *worse than arbitrary* -- meaning it
  has learned to actively mis-pick a decision that is under 2% of its training
  signal.

**Random picking discriminates them.** If random lands near the teacher, index 0
carries no information and the second reading holds. If random is much worse,
the first does.

Everything except PICK is the teacher, so this runs in the regime 50.3 showed is
the sensitive one -- a decision's value is only visible against a competent
surrounding policy.

    .venv/bin/python scripts/pick_probe.py runs/reclone-rowhead --episodes 300
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

# Which kinds the probe varies. PICK was the original question (51); the same
# design answers "what is this decision worth, and is the clone better than
# arbitrary at it" for any kind, so the groups match 50's delegation groups.
KIND_GROUPS = {
    "PICK": (ActionKind.PICK_AUGMENT, ActionKind.PICK_OFFERING),
    "SELL": (ActionKind.SELL,),
    "MOVE": (ActionKind.SELECT, ActionKind.PLACE),
    "BUY": (ActionKind.BUY,),
    "EQUIP": (ActionKind.EQUIP,),
    "ECON": (ActionKind.REROLL, ActionKind.BUY_XP),
}
PICK_KINDS = KIND_GROUPS["PICK"]

# How the PICK decision is made; everything else is always the teacher.
# `random` randomises both PICK kinds; the two split arms isolate them.
# Augment offers come from `rng.sample` and offerings from sequential pool
# draws, so on inspection *neither* should be ordered by strength and
# randomising either should cost nothing. It costs 0.463 (51.1), so one of
# them has an ordering that inspection missed -- these arms say which.
MODES = ("teacher", "random", "random_augment", "random_offering", "last", "clone")
# For non-PICK kinds `random`/`last` bottom out (52.1), so `forbidden` -- the
# teacher denied the decision entirely -- is the interpretable baseline.
KIND_MODES = ("teacher", "forbidden", "random", "clone")
# MOVE needs a finer cut than `forbidden`. SELECT+PLACE is the *only* way to
# field a unit, so denying it entirely leaves an empty board and 8.000 in every
# game (52.2) -- that measures fielding, not positioning. Forbidding SELECT of
# a *board* slot keeps bench->board fielding while preventing a fielded unit
# from ever moving again, which isolates repositioning.
MOVE_MODES = ("teacher", "no_reposition", "clone")

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


def _init(run_dir: str, env_kwargs: dict, expert_kwargs: dict, mode: str,
          varied: tuple = PICK_KINDS) -> None:
    import logging
    import random as _random

    import numpy as np
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
    teacher = scripted_policy(env, **expert_kwargs)
    space = env.action_space_helper
    # Seeded **per episode**, in `_episode`, not once per worker.
    #
    # The first version built one stream per process. `imap_unordered` hands
    # seeds to whichever worker is free, so which episode drew which option
    # changed between runs -- and two runs of the identical `random` arm
    # returned 3.493 and 3.257. That is a 0.236 swing from nothing but worker
    # scheduling, larger than most effects this project measures, and it makes
    # the paired t invalid: the arms differ by an uncontrolled draw as well as
    # by policy (doc 99 entry 51.2).
    rng = _random.Random(0)
    clone = (
        sb3_policy(MaskablePPO.load(run_dir, device="cpu"))
        if mode == "clone"
        else None
    )

    def policy(obs, mask):
        if mode == "no_reposition":
            allowed = mask.copy()
            for index in np.flatnonzero(allowed):
                action = space.decode(int(index))
                if action.kind is ActionKind.SELECT and action.a < space.board_slots:
                    allowed[index] = False
            if allowed.any():
                return teacher(obs, allowed)
            return teacher(obs, mask)

        if mode == "forbidden":
            # The neutral baseline: the teacher plays on with this decision
            # *unavailable*, rather than made badly.
            #
            # `random` and `last` are destructive for SELL and MOVE -- they sell
            # the carry and unfield the board, bottoming out at 7.977 and 8.000
            # (52.1). That measures the cost of self-sabotage, not what the
            # decision is worth, and a floor leaves no variance to compare
            # against (18.5). Masking the kind out asks the interpretable
            # question: what does the teacher lose if it cannot do this at all?
            allowed = mask.copy()
            for index in np.flatnonzero(allowed):
                if space.decode(int(index)).kind in varied:
                    allowed[index] = False
            if allowed.any():
                return teacher(obs, allowed)
            return teacher(obs, mask)

        proposed = teacher(obs, mask)
        kind = space.decode(proposed).kind
        if kind not in varied or mode == "teacher":
            return proposed
        if mode == "random_augment" and kind is not ActionKind.PICK_AUGMENT:
            return proposed
        if mode == "random_offering" and kind is not ActionKind.PICK_OFFERING:
            return proposed
        options = [
            i for i in np.flatnonzero(mask) if space.decode(int(i)).kind is kind
        ]
        if not options:
            return proposed
        if mode.startswith("random"):
            return int(rng.choice(options))
        if mode == "last":
            return int(options[-1])
        return clone(obs, mask)

    _WORKER["rng"] = rng
    _WORKER["policy"] = policy


def _episode(seed: int):
    # Reseeded from the episode seed, so a given (mode, seed) always makes the
    # same choices no matter which worker runs it or in what order.
    _WORKER["rng"].seed(seed)
    result = evaluate(_WORKER["env"], _WORKER["policy"], seeds=[seed])
    return seed, result.placements[0], result.rewards[0], result.rounds[0]


def run_mode(run_dir, seeds, mode, workers, env_kwargs, expert_kwargs,
             varied=PICK_KINDS):
    context = mp.get_context("spawn")
    with context.Pool(
        processes=workers,
        initializer=_init,
        initargs=(str(run_dir / "model"), env_kwargs, expert_kwargs, mode, varied),
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
    parser.add_argument("--kind", default="PICK", choices=sorted(KIND_GROUPS),
                        help="which decision to vary; everything else is the "
                             "teacher, which 50.3 showed is the regime where a "
                             "decision's value is actually visible")
    args = parser.parse_args()

    seeds = list(range(args.episodes))
    expert_kwargs, env_kwargs = config_for(args.run)

    varied = KIND_GROUPS[args.kind]
    # The augment/offering split only means anything for PICK.
    modes = KIND_MODES
    if args.kind == "PICK":
        modes = MODES
    elif args.kind == "MOVE":
        modes = MOVE_MODES

    results = {}
    with timed("pick_probe", episodes=args.episodes,
               arms=len(modes), workers=args.workers, decision=args.kind):
        for mode in modes:
            results[mode] = run_mode(
                args.run, seeds, mode, args.workers, env_kwargs, expert_kwargs,
                varied=varied,
            )
            print(f"  {args.kind} by {mode:<10} {results[mode].avg_placement:.3f}", flush=True)

    base = results["teacher"]
    print(f"\n{args.kind + ' made by':<16}{'place':>8}{'ci95':>7}{'1st':>7}{'top4':>7}"
          f"{'vs teacher (paired)':>28}")
    for mode, r in results.items():
        mean, t = paired_t(base.placements, r.placements)
        delta = "" if mode == "teacher" else f"{mean:+.3f}  t={t:+.2f}"
        print(f"{mode:<16}{r.avg_placement:>8.3f}{r.ci95:>7.3f}"
              f"{r.win_rate:>7.1%}{r.top4_rate:>7.1%}{delta:>28}")
    print(
        "\n`random` is the achievable floor for this decision and `teacher` the "
        "reference.\nA clone near `random` has not learned the decision; a clone "
        "near `teacher` has.\nThe teacher-to-random spread is what the decision "
        "is worth at all -- a gap is\nuninterpretable without it."
    )

    if args.json:
        args.json.write_text(json.dumps(
            {m: {"placements": r.placements, "avg_placement": r.avg_placement}
             for m, r in results.items()}, indent=1))


if __name__ == "__main__":
    main()
