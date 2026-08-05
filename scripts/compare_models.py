"""Paired comparison between saved models on identical seeds.

`train_ppo.py` prints a mean and an *unpaired* CI per run. Arms that share
seeds deserve the paired statistic, which is considerably more sensitive
(doc 99 entry 18.6) -- and the run logs do not keep per-episode placements, so
it cannot be recovered afterwards without replaying.

Each model is evaluated in an env built to match its own metadata, because the
observation width differs between them: `copy_counts` widens it 381 -> 418 and
loading a model against the wrong width is an opaque torch shape error.

    .venv/bin/python scripts/compare_models.py runs/a runs/b --episodes 150
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rl.evaluate import evaluate_model_parallel  # noqa: E402
from rl.timing import human, timed  # noqa: E402


def paired_t(a: list[int], b: list[int]) -> tuple[float, float]:
    diffs = [y - x for x, y in zip(a, b, strict=True)]
    n = len(diffs)
    mean = sum(diffs) / n
    if n < 2:
        return mean, 0.0
    var = sum((d - mean) ** 2 for d in diffs) / (n - 1)
    se = math.sqrt(var / n)
    return mean, (mean / se if se > 0 else 0.0)


def env_kwargs_for(run_dir: Path) -> dict:
    """Recover the env options a run was trained with from its sidecar."""
    sidecar = run_dir / "metadata.json"
    if not sidecar.exists():
        # Written *after* the final evaluation, so it appears well after
        # model.zip. Waiting on the model is a race that costs whatever
        # evaluation had already finished when the load failed.
        raise SystemExit(
            f"{sidecar} missing -- the run is still finishing. "
            "Wait for metadata.json, not model.zip."
        )
    meta = json.loads(sidecar.read_text())
    args = meta.get("args", meta.get("hyperparameters", {}))
    return {
        "copy_counts": bool(args.get("copy_counts", False)),
        "champion_encoding": args.get("champion_encoding", "index"),
        "scouting": args.get("scouting", "summary"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--episodes", type=int, default=150)
    parser.add_argument("--json", type=Path, default=None,
                        help="write per-episode placements here. Without this "
                             "a later question about any pair of arms needs a "
                             "full replay, which is how several comparisons "
                             "in this project got re-run from scratch")
    parser.add_argument("--workers", type=int, default=None,
                        help="evaluation processes; defaults to cpu_count(). "
                             "1 runs the serial path the equivalence test pins")
    args = parser.parse_args()

    from sb3_contrib import MaskablePPO

    seeds = range(args.episodes)
    results = {}
    timer = timed("compare_models", episodes=args.episodes,
                  arms=len(args.runs), workers=args.workers or 0)
    timer.__enter__()
    for run_dir in args.runs:
        import time as _time

        started = _time.perf_counter()
        env_kwargs = env_kwargs_for(run_dir)
        try:
            # Load once up front purely to fail fast on an orphaned checkpoint;
            # the workers each load their own copy from the path.
            MaskablePPO.load(run_dir / "model", device="cpu")
        except (RuntimeError, ValueError) as exc:
            # A custom policy is rebuilt from *current* source, so editing the
            # head's architecture orphans every checkpoint that used the old
            # one. Skip rather than lose the arms that do still load -- losing
            # a finished comparison to one dead artifact is the worse outcome.
            print(f"  {run_dir.name:<26} SKIPPED: {type(exc).__name__}", flush=True)
            print(f"    {str(exc).splitlines()[0][:120]}", flush=True)
            continue
        results[run_dir.name] = evaluate_model_parallel(
            run_dir / "model", seeds, workers=args.workers, env_kwargs=env_kwargs
        )
        print(
            f"  {run_dir.name:<26} done  ({human(_time.perf_counter() - started)})",
            flush=True,
        )

    timer.__exit__(None, None, None)

    if not results:
        raise SystemExit("no models could be loaded")

    names = list(results)
    base = results[names[0]]
    print(f"\n{'run':<26}{'place':>8}{'ci95':>7}{'LP':>8}{'1st':>7}{'top4':>7}"
          f"{'vs first (paired)':>22}")
    for name, r in results.items():
        if name == names[0]:
            delta = ""
        else:
            mean, t = paired_t(base.placements, r.placements)
            delta = f"{mean:+.3f}  t={t:+.2f}"
        print(f"{name:<26}{r.avg_placement:>8.3f}{r.ci95:>7.3f}{r.avg_lp:>8.2f}"
              f"{r.win_rate:>7.1%}{r.top4_rate:>7.1%}{delta:>22}")
    # Every pair, not just each against the first: the interesting comparison
    # is often between two non-baseline arms, and replaying 300 episodes to
    # recover it afterwards is pure waste.
    if len(names) > 2:
        print("\nall pairs (paired on shared seeds):")
        for i, left in enumerate(names):
            for right in names[i + 1:]:
                mean, t = paired_t(results[left].placements, results[right].placements)
                print(f"  {right:<26} vs {left:<26} {mean:+.3f}  t={t:+.2f}")

    if args.json:
        args.json.write_text(json.dumps(
            {name: {"placements": r.placements, "rewards": r.rewards,
                    "rounds": r.rounds, "avg_placement": r.avg_placement}
             for name, r in results.items()}, indent=1))
        print(f"\nper-episode results: {args.json}")

    # No hardcoded reference numbers here. This footer used to read
    # "Teacher (sell): 3.437; bots: 4.500", while doc 99 carried the teacher at
    # 3.030 -- both inherited from different runs on different engines, and at
    # least one simply wrong. A constant printed beside a fresh measurement
    # reads as though it were measured with it. Use `scripts/teacher_gap.py`,
    # which evaluates the teacher on the *same seeds* in the same run
    # (doc 99 entry 49).
    print("\nNegative deltas are better. For a teacher reference measured on "
          "these same seeds, use scripts/teacher_gap.py.")


if __name__ == "__main__":
    main()
