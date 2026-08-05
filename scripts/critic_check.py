"""Did PPO wreck the critic it was handed? (doc 99 entry 49)

Behaviour cloning fits the value head alongside the policy and reports
``explained_variance`` on expert data -- 0.968 for the clone PPO then degraded
by 1.077 placement (48.2). That number was never re-measured after PPO, so the
degradation has no named mechanism.

A critic that has collapsed makes every advantage estimate noise, which is a
concrete and fixable story. A critic that is still fine means the damage is in
the policy objective, which is a different problem. Measuring costs a few
minutes and discriminates between them.

Expert transitions are the same evaluation set for every model, so the
comparison is like-for-like.

    .venv/bin/python scripts/critic_check.py runs/reclone-rowhead runs/ppo-from-clone
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import torch  # noqa: E402

from engine.loader import load_all  # noqa: E402
from rl.collect import collect_parallel  # noqa: E402
from rl.timing import timed  # noqa: E402


def env_kwargs_for(run_dir: Path) -> dict:
    args = json.loads((run_dir / "metadata.json").read_text())
    args = args.get("args", args.get("hyperparameters", {}))
    return {
        "copy_counts": bool(args.get("copy_counts", False)),
        "champion_encoding": args.get("champion_encoding", "index"),
        "scouting": args.get("scouting", "summary"),
    }


def expert_kwargs_for(run_dir: Path) -> dict:
    args = json.loads((run_dir / "metadata.json").read_text())
    args = args.get("args", args.get("hyperparameters", {}))
    flags = bool(args.get("expert_flags", False))
    return {
        "sell_bench": bool(args.get("expert_sell", False)),
        "buy_synergy": flags,
        "match_items": flags,
        "corner_carry": flags,
        "roll_at_level": args.get("expert_roll_at_level", 0) or 0,
    }


def explained_variance(predicted: np.ndarray, actual: np.ndarray) -> float:
    """1 - Var(actual - predicted) / Var(actual); 0 is as good as the mean."""
    var = np.var(actual)
    return float("nan") if var == 0 else float(1 - np.var(actual - predicted) / var)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--episodes", type=int, default=40)
    parser.add_argument("--gamma", type=float, default=0.999)
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()

    from sb3_contrib import MaskablePPO

    load_all()  # fail early on a broken dataset rather than inside a worker
    # One dataset, evaluated by every model: a critic compared on its own
    # states rather than a shared set would be measuring the state
    # distribution, not the critic.
    with timed("critic_check", episodes=args.episodes, arms=1, workers=args.workers):
        observations, _, _, returns = collect_parallel(
            [90_000 + i for i in range(args.episodes)],
            gamma=args.gamma,
            workers=args.workers,
            env_kwargs=env_kwargs_for(args.runs[0]),
            expert_kwargs=expert_kwargs_for(args.runs[0]),
        )
    print(f"expert evaluation set: {len(observations)} transitions "
          f"from {args.episodes} episodes")

    print(f"\n{'run':<26}{'explained_var':>15}{'pred mean':>12}{'pred sd':>10}")
    print(f"{'ACTUAL RETURNS':<26}{'':>15}{returns.mean():>12.3f}{returns.std():>10.3f}")
    for run_dir in args.runs:
        model = MaskablePPO.load(run_dir / "model", device="cpu")
        with torch.no_grad():
            tensor = torch.as_tensor(observations, dtype=torch.float32)
            values = model.policy.predict_values(tensor).cpu().numpy().flatten()
        ev = explained_variance(values, returns)
        print(f"{run_dir.name:<26}{ev:>15.3f}{values.mean():>12.3f}"
              f"{values.std():>10.3f}")
    print("\n1.0 is perfect; 0.0 is no better than predicting the mean; "
          "negative is worse than that.")


if __name__ == "__main__":
    main()
