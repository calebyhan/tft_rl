"""Which disagreements with the teacher actually cost placement? (doc 99 entry 82)

Entry 81 eliminated distribution shift: DAgger raised student-state agreement
25-29 points on the two collapsing decision kinds and moved placement -0.083
(t=-0.57). Combined with 79.8 eliminating label noise, the only surviving
explanation for the clone's 0.527 gap is the observation.

Widening the observation blind costs a training run per guess, and this project
has rejected the same champion encoding three times for want of a target. A 4%
disagreement rate costing a fifth of the placement range implies the residual is
concentrated on a few decisions of very high leverage. This finds them.

**The counterfactual.** At a state where clone and teacher disagree, the cost of
that one disagreement is: play the rest of the game under the clone, versus take
the *teacher's* action once and then play the rest under the clone. The
difference in final placement is the leverage of that single choice.

`copy.deepcopy` cannot fork the env (`mappingproxy`), so branches are replayed
from the seed instead -- verified deterministic: replaying a seed reproduces the
action sequence and placement exactly. Both branches therefore share every RNG
draw, and the *only* difference between them is the one substituted action.

Reported per `ActionKind` and per stage, because "where" has two meanings and
only one of them is about which feature to add.

    .venv/bin/python scripts/disagreement_cost.py runs/dagger-r2 --episodes 200
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import multiprocessing as mp
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rl.timing import timed  # noqa: E402

_W: dict = {}


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    for name in ("rl/evaluate.py", "rl/env.py", "rl/action.py"):
        digest.update(Path(name).read_bytes())
    return digest.hexdigest()[:12]


def _init(run_dir: str, env_kwargs: dict, expert_kwargs: dict,
          kind: str | None = None, per_episode: int = 3) -> None:
    import logging

    import torch
    from sb3_contrib import MaskablePPO

    from engine.loader import load_all
    from rl.env import TFTEnv
    from rl.evaluate import sb3_policy, scripted_policy

    logging.getLogger("engine.loader").setLevel(logging.ERROR)
    torch.set_num_threads(1)
    data = load_all()
    _W["data"] = data
    _W["env_kwargs"] = env_kwargs
    env = TFTEnv(data=data, **env_kwargs)
    _W["teacher"] = scripted_policy(env, **expert_kwargs)
    _W["teacher_env"] = env
    _W["clone"] = sb3_policy(MaskablePPO.load(run_dir, device="cpu"))
    _W["kind"] = kind
    _W["per_episode"] = per_episode


def _rollout(seed: int, override: tuple[int, int] | None):
    """Play one episode under the clone, optionally forcing one action.

    Returns (placement, trace) where trace lists (step, clone_action,
    teacher_action, kind, round_id) for every step the two disagreed. The
    teacher is driven through its *own* env instance kept in lockstep, because
    `scripted_policy` closes over the env it was built with and reads live
    player state from it rather than from the observation.
    """
    from rl.env import TFTEnv

    env = TFTEnv(data=_W["data"], **_W["env_kwargs"])
    tenv = _W["teacher_env"]
    obs, _info = env.reset(seed=seed)
    tobs, _tinfo = tenv.reset(seed=seed)
    space = env.action_space_helper

    trace = []
    placement = None
    for step in range(10_000):
        mask = env.action_masks()
        clone_action = int(_W["clone"](obs, mask))
        teacher_action = int(_W["teacher"](tobs, tenv.action_masks()))
        if clone_action != teacher_action:
            trace.append((step, clone_action, teacher_action,
                          space.decode(teacher_action).kind.name,
                          env.match.round_id))
        action = clone_action
        if override is not None and override[0] == step:
            action = override[1]
        obs, _r, term, trunc, info = env.step(action)
        # The teacher's env must follow the *executed* action, or the two
        # diverge and every later "disagreement" is between two different games.
        tobs, _tr, tterm, ttrunc, _ti = tenv.step(action)
        if term or trunc:
            placement = info.get("placement")
            break
        if tterm or ttrunc:
            break
    return placement, trace


def _episode(seed: int):
    """Baseline rollout, then one counterfactual per sampled disagreement."""
    import random

    base_placement, trace = _rollout(seed, None)
    if base_placement is None or not trace:
        return []
    rng = random.Random(seed)
    # Stratify when a kind is named. Entry 82.1 sampled disagreements
    # uniformly, so a kind holding 4.7% of them got n=42 and t=-1.55 -- too
    # thin to build on. Filtering first spends the same budget on the question
    # being asked; the per-kind mean is unbiased either way, only its precision
    # changes.
    kind_filter = _W.get("kind")
    pool = [row for row in trace if row[3] == kind_filter] if kind_filter else trace
    if not pool:
        return []
    picks = rng.sample(pool, min(_W.get("per_episode", 3), len(pool)))
    rows = []
    for step, _clone_action, teacher_action, kind, round_id in picks:
        alt_placement, _ = _rollout(seed, (step, teacher_action))
        if alt_placement is None:
            continue
        # Negative = taking the teacher's action once improved placement.
        rows.append((kind, round_id, alt_placement - base_placement,
                     len(trace), base_placement))
    return rows


def paired_stats(values: list[float]) -> tuple[float, float]:
    n = len(values)
    if n < 2:
        return (values[0] if values else 0.0), 0.0
    mean = statistics.mean(values)
    var = statistics.variance(values)
    return mean, (mean / math.sqrt(var / n) if var > 0 else 0.0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--episodes", type=int, default=200)
    parser.add_argument("--per-episode", type=int, default=3,
                        help="disagreements sampled per episode")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--kind", default=None,
                        help="sample only disagreements of this ActionKind")
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    from scripts.teacher_gap import teacher_config

    expert_kwargs, env_kwargs, search_kwargs = teacher_config(args.run)
    if search_kwargs is not None:
        raise SystemExit(
            "this run's teacher uses positional search, which is not a "
            "function of a single action substitution -- see doc 99 79.3"
        )
    before = source_fingerprint()
    print(f"source fingerprint: {before}")
    print(f"teacher: econ={expert_kwargs['econ'] and expert_kwargs['econ'].name}")

    context = mp.get_context("spawn")
    rows = []
    with timed("disagreement_cost", episodes=args.episodes,
               arms=1, workers=args.workers):
        with context.Pool(
            processes=args.workers, initializer=_init,
            initargs=(str(args.run / "model"), env_kwargs, expert_kwargs,
                      args.kind, args.per_episode),
        ) as pool:
            for batch in pool.imap_unordered(_episode, range(args.episodes)):
                rows.extend(batch)

    if source_fingerprint() != before:
        print("!! SOURCE CHANGED MID-RUN -- discard (doc 99 entry 68.4)")
    if not rows:
        raise SystemExit("no disagreements sampled -- nothing to report")

    by_kind: dict[str, list[float]] = defaultdict(list)
    by_stage: dict[int, list[float]] = defaultdict(list)
    for kind, round_id, delta, _n, _base in rows:
        by_kind[kind].append(delta)
        by_stage[int(str(round_id).split("-")[0])].append(delta)

    overall, overall_t = paired_stats([r[2] for r in rows])
    print(f"\n{len(rows)} counterfactuals. Negative = the teacher's action was "
          f"better.\noverall {overall:+.3f}  t={overall_t:+.2f}\n")

    print(f"{'action kind':<16}{'n':>6}{'mean delta':>13}{'t':>8}")
    for kind in sorted(by_kind, key=lambda k: paired_stats(by_kind[k])[0]):
        mean, t = paired_stats(by_kind[kind])
        print(f"{kind:<16}{len(by_kind[kind]):>6}{mean:>13.3f}{t:>8.2f}")

    print(f"\n{'stage':<16}{'n':>6}{'mean delta':>13}{'t':>8}")
    for stage in sorted(by_stage):
        mean, t = paired_stats(by_stage[stage])
        print(f"{stage:<16}{len(by_stage[stage]):>6}{mean:>13.3f}{t:>8.2f}")

    print("\nA kind with a large negative mean is where copying the teacher "
          "pays, and so\nis where the observation most likely cannot support "
          "the decision. A kind near\nzero is disagreement that does not "
          "matter, however large its share of the\nmismatch (lesson 18).")

    if args.json:
        args.json.write_text(json.dumps(
            [{"kind": k, "round": str(r), "delta": d} for k, r, d, _n, _b in rows],
            indent=1))
        print(f"\nper-counterfactual results: {args.json}")


if __name__ == "__main__":
    main()
