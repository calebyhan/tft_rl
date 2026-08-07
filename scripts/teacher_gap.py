"""How far is the clone from its own teacher, right now? (doc 99 entry 49)

Every "imitation is exhausted" claim in this project rests on the gap between a
clone and the scripted policy it was cloned from -- and that gap has never been
measured on shared seeds in the current regime. The teacher's number has been
carried across entries as a constant (3.030 in doc 99, 3.437 hardcoded in
`compare_models`' footer -- they cannot both be right), which is the exact
failure mode the *re-derive numbers before citing them* lesson exists for.

The teacher and the model are evaluated on the **same seeds**, in the same run,
so the comparison is paired and neither figure is inherited from an older
engine.

    .venv/bin/python scripts/teacher_gap.py runs/reclone-rowhead --episodes 300
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rl.evaluate import (  # noqa: E402
    evaluate_model_parallel,
    evaluate_scripted_parallel,
)
from rl.timing import timed  # noqa: E402

# The teacher the current clones were trained from: --expert-sell plus
# --expert-flags. Read from the checkpoint's sidecar rather than assumed.
FLAG_KEYS = {
    "sell_bench": "expert_sell",
    "buy_synergy": "expert_flags",
    "match_items": "expert_flags",
    "corner_carry": "expert_flags",
}


def paired_t(a: list[int], b: list[int]) -> tuple[float, float]:
    diffs = [y - x for x, y in zip(a, b, strict=True)]
    n = len(diffs)
    mean = sum(diffs) / n
    if n < 2:
        return mean, 0.0
    var = sum((d - mean) ** 2 for d in diffs) / (n - 1)
    return mean, (mean / math.sqrt(var / n) if var > 0 else 0.0)


def search_config(args: dict) -> dict | None:
    """The positional-search budget a run's teacher was wrapped in, or None.

    Same reasoning as `econ` below: a search teacher places 3.883 against the
    plain econ teacher's 4.213 (doc 99 entry 78.2), so reconstructing without
    it scores a clone against a teacher 0.330 weaker than the one that
    labelled it. The budget matters too -- c6/p1 is not distinguishable from
    no search at all -- so it is read rather than assumed. The fallbacks are
    6/1 because that is what runs predating these flags hardcoded, not because
    it is a sensible default for a new run.
    """
    if not args.get("expert_reposition", False):
        return None
    return {
        "mode": "move",
        "max_candidates": args.get("expert_reposition_candidates", 6),
        "panel_size": args.get("expert_reposition_panel", 1),
        # Defaults **False**, opposite to `best_move`'s own default. Runs
        # predating entry 79.4 were labelled by the free-running stream, and
        # rebuilding them state-seeded would score those clones against a
        # teacher that never labelled them -- the same failure this function
        # exists to prevent, arriving through a changed default rather than a
        # dropped key.
        "state_seeded": args.get("expert_reposition_state_seeded", False),
    }


def teacher_config(run_dir: Path) -> tuple[dict, dict, dict | None]:
    """The teacher flags, env options and search budget this run was trained with."""
    from rl.opponents import STRATEGIES

    meta = json.loads((run_dir / "metadata.json").read_text())
    args = meta.get("args", meta.get("hyperparameters", {}))
    expert = {flag: bool(args.get(key, False)) for flag, key in FLAG_KEYS.items()}
    expert["roll_at_level"] = args.get("expert_roll_at_level", 0) or 0
    # Must come from the sidecar. Dropping it silently rebuilds a *no-econ*
    # teacher, which places 4.823 against 4.213 -- so a clone trained on the
    # good teacher would be scored against the bad one and the gap would be
    # measured against a policy that never labelled it (doc 99 entry 74).
    econ_name = args.get("expert_econ")
    expert["econ"] = STRATEGIES[econ_name] if econ_name else None
    env = {
        "copy_counts": bool(args.get("copy_counts", False)),
        "champion_encoding": args.get("champion_encoding", "index"),
        "scouting": args.get("scouting", "summary"),
        "unit_range": bool(args.get("unit_range", False)),
    }
    return expert, env, search_config(args)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--episodes", type=int, default=300)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    seeds = list(range(args.episodes))
    expert, env_kwargs, search_kwargs = teacher_config(args.runs[0])
    print(f"teacher flags (from {args.runs[0].name}): "
          + " ".join(f"{k}={v}" for k, v in expert.items())
          + f" search={search_kwargs}")

    results = {}
    with timed("teacher_gap", episodes=args.episodes,
               arms=len(args.runs) + 1, workers=args.workers):
        results["TEACHER (scripted)"] = evaluate_scripted_parallel(
            seeds, workers=args.workers, env_kwargs=env_kwargs,
            search_kwargs=search_kwargs, **expert
        )
        for run_dir in args.runs:
            results[run_dir.name] = evaluate_model_parallel(
                run_dir / "model", seeds, workers=args.workers,
                env_kwargs=teacher_config(run_dir)[1],
            )

    base_name = "TEACHER (scripted)"
    base = results[base_name]
    print(f"\n{'arm':<26}{'place':>8}{'ci95':>7}{'LP':>8}{'1st':>7}{'top4':>7}"
          f"{'vs teacher (paired)':>24}")
    for name, r in results.items():
        if name == base_name:
            delta = ""
        else:
            mean, t = paired_t(base.placements, r.placements)
            delta = f"{mean:+.3f}  t={t:+.2f}"
        print(f"{name:<26}{r.avg_placement:>8.3f}{r.ci95:>7.3f}{r.avg_lp:>8.2f}"
              f"{r.win_rate:>7.1%}{r.top4_rate:>7.1%}{delta:>24}")
    print("\nPositive deltas mean the model is WORSE than its teacher; that "
          "difference is the headroom imitation has left.")

    if args.json:
        args.json.write_text(json.dumps(
            {name: {"placements": r.placements, "avg_placement": r.avg_placement}
             for name, r in results.items()}, indent=1))
        print(f"per-episode results: {args.json}")


if __name__ == "__main__":
    main()
