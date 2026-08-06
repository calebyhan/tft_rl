r"""Does PPO's drift target whatever cloning suppressed hardest? (doc 99 entry 63)

Entry 62 refuted the last structural hypothesis and left one prediction. If the
collapse is regression-to-the-mean in logit space -- cloning drives rarely-used
actions to extreme low log-probability, and any perturbation pulls them back --
then the mass PPO *gains* should concentrate on the actions the clone suppressed
**hardest**, and REROLL should not be special except for being always legal.

Both policies are evaluated on the **same states**, so the comparison is paired
per action index and neither is measured on its own distribution.

**A confound that is named rather than solved.** Log-probabilities are bounded
above by 0, so an action at -0.5 can rise at most 0.5 while one at -9.5 can rise
9.5. Some negative correlation between baseline and gain is therefore
*mechanical*, and a correlation alone cannot establish the prediction. Two
sharper checks are reported alongside it:

* **rank agreement** -- are the biggest gainers actually the lowest-baseline
  actions, or merely somewhere below average?
* **legality split** -- among equally suppressed actions, the prediction says
  the *always-legal* ones run away (they get sampled, so the recovery
  compounds) while rarely-legal ones do not. That contrast has no mechanical
  ceiling explanation, so it is the part that can actually fail.

    .venv/bin/python scripts/regression_probe.py runs/ws1200 runs/ppo-noent
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    dx = math_sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math_sqrt(sum((y - my) ** 2 for y in ys))
    return num / (dx * dy) if dx > 0 and dy > 0 else 0.0


def math_sqrt(value: float) -> float:
    import math

    return math.sqrt(value)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path, help="the warm start")
    parser.add_argument("drifted", type=Path, help="the collapsed policy")
    parser.add_argument("--states", type=int, default=4000)
    parser.add_argument("--min-legal", type=int, default=40,
                        help="ignore actions legal in fewer states than this")
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    import torch
    from sb3_contrib import MaskablePPO

    from engine.loader import load_all
    from scripts.coupling_probe import collect_states
    from scripts.train_ppo import ENV_DEFAULTS, build_env

    logging.getLogger("engine.loader").setLevel(logging.ERROR)
    torch.set_num_threads(2)

    saved = json.loads(
        (args.baseline / "metadata.json").read_text()
    )["hyperparameters"]
    ENV_DEFAULTS.update({
        "copy_counts": saved["copy_counts"],
        "champion_encoding": saved["champion_encoding"],
        "scouting": saved["scouting"],
    })
    data = load_all()
    env = build_env(data)
    space = env.action_space_helper

    base_model = MaskablePPO.load(args.baseline / "model", device="cpu")
    drift_model = MaskablePPO.load(args.drifted / "model", device="cpu")

    # States from the *warm start*, the distribution the drift departs from.
    print(f"collecting {args.states} states under {args.baseline.name}")
    observations, masks = collect_states(base_model, env, space, args.states)
    obs_t = torch.as_tensor(observations)
    mask_t = torch.as_tensor(masks)

    def logprobs(model) -> np.ndarray:
        with torch.no_grad():
            distribution = model.policy.get_distribution(
                obs_t, action_masks=mask_t
            )
            return distribution.distribution.logits.numpy()

    base_lp, drift_lp = logprobs(base_model), logprobs(drift_model)

    rows = []
    for index in range(space.n):
        legal = mask_t[:, index].numpy()
        if legal.sum() < args.min_legal:
            continue
        rows.append({
            "index": index,
            "kind": space.decode(index).kind.name,
            "legal_rate": float(legal.mean()),
            "base": float(base_lp[legal, index].mean()),
            "gain": float(drift_lp[legal, index].mean()
                          - base_lp[legal, index].mean()),
        })
    print(f"{len(rows)} action indices legal in >= {args.min_legal} states "
          f"(of {space.n})")

    base_values = [r["base"] for r in rows]
    gains = [r["gain"] for r in rows]
    r = pearson(base_values, gains)
    print(f"\ncorrelation(baseline log-prob, gain) = {r:+.3f}")
    print("  (bounded above by 0, so some negative correlation is mechanical)")

    ranked = sorted(rows, key=lambda x: x["base"])
    quintile = max(len(ranked) // 5, 1)
    lowest = ranked[:quintile]
    highest = ranked[-quintile:]
    print(f"\nlowest-baseline fifth:  mean gain "
          f"{statistics.mean(x['gain'] for x in lowest):+.3f}")
    print(f"highest-baseline fifth: mean gain "
          f"{statistics.mean(x['gain'] for x in highest):+.3f}")

    # The discriminating contrast: among the *equally suppressed* actions, does
    # legality predict the runaway? No ceiling effect explains this one.
    suppressed = [x for x in rows if x["base"] < statistics.median(base_values)]
    often = [x for x in suppressed if x["legal_rate"] > 0.5]
    rarely = [x for x in suppressed if x["legal_rate"] <= 0.5]
    print("\namong suppressed actions (baseline below median):")
    for label, group in (("legal >50% of states", often),
                         ("legal <=50%", rarely)):
        if group:
            print(f"  {label:<24} n={len(group):<5} mean gain "
                  f"{statistics.mean(x['gain'] for x in group):+.3f}")

    print(f"\n{'top gainers':<16}{'kind':<16}{'legal':>8}{'base':>9}{'gain':>9}")
    for x in sorted(rows, key=lambda x: -x["gain"])[:8]:
        print(f"{x['index']:<16}{x['kind']:<16}{x['legal_rate']:>8.1%}"
              f"{x['base']:>9.2f}{x['gain']:>+9.2f}")

    if often and rarely:
        delta = (statistics.mean(x["gain"] for x in often)
                 - statistics.mean(x["gain"] for x in rarely))
        print(
            f"\nlegality contrast among equally suppressed actions: {delta:+.3f}"
        )
        if delta > 0.3:
            print("  -> PREDICTION HOLDS: suppressed *and* always-legal actions "
                  "run away; suppression alone is not enough.")
        else:
            print("  -> PREDICTION FAILS: legality does not separate the "
                  "gainers, so the sampling-feedback story is wrong.")

    if args.json:
        args.json.write_text(json.dumps({"correlation": r, "rows": rows}, indent=1))


if __name__ == "__main__":
    main()
