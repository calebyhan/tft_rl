"""What budget should the *teacher's* buy search run at? (doc 99 entry 160.105)

`best_buy` ships `panel_size=2, trials=2, max_candidates=5, margin=0.25`. Those
came from entry 150's port, chosen for a search firing once per planning phase
across a whole training run. Nobody has asked what they buy.

The question is not academic. 160.53 validated a learned shortlist that cuts
exact combat calls **32.8%** at no cost in placement. Savings are only worth
something if they can be *spent*, and they can only be spent if placement
responds to budget at all. This measures that response before any effort goes
into converting one into the other -- the ceiling-first rule, applied to a
direction rather than a rate.

Every arm plays the **same seeds** with the same teacher (`search_buy_greedy`,
`fast8`), so nothing but the buy budget varies, and the contrast is paired.
Fight calls are counted by wrapping `fight_value`, the same way
`search_buy_hybrid_action_ab` does, so cost is measured rather than assumed.

`margin` is deliberately *not* an arm. 136.3 established it is not
panel-invariant, and `best_buy_from_scores` already scales it by `panel_size`;
varying both would confound the acceptance threshold with the panel.

    .venv/bin/python scripts/buy_budget.py --episodes 200 --workers 10
"""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import SEARCH_SEED_OFFSET  # noqa: E402
from rl.opponents import FAST8  # noqa: E402
from rl.search import search_buy_greedy_policy  # noqa: E402

# The oracle arm is a budget no training loop would pay. A budget curve is
# uninterpretable without the ceiling it is approaching (lesson: a rate is
# uninterpretable without its achievable maximum).
ARMS: dict[str, dict] = {
    "control": {},
    "trials6": {"trials": 6},
    "panel4": {"panel_size": 4},
    "cand10": {"max_candidates": 10},
    "oracle": {"panel_size": 4, "trials": 6, "max_candidates": 10},
}

_DATA = None


def _init() -> None:
    global _DATA
    import logging

    from engine.loader import load_all

    logging.getLogger("engine.loader").setLevel(logging.ERROR)
    _DATA = load_all()


def _play(job) -> dict:
    import rl.search as search_mod

    arm, seed = job
    env = TFTEnv(_DATA, max_actions_per_round=600)
    original = search_mod.fight_value
    fights = 0

    def counted(*args, **kwargs):
        nonlocal fights
        fights += 1
        return original(*args, **kwargs)

    search_mod.fight_value = counted
    started = time.time()
    try:
        policy = search_buy_greedy_policy(env, econ=FAST8, buy_kwargs=ARMS[arm])
        policy.rng.seed(seed + SEARCH_SEED_OFFSET)
        obs, _ = env.reset(seed=seed)
        done = False
        buys = 0
        while not done:
            action = policy(obs, env.action_masks())
            buys += policy.last_search_buy_slot is not None
            obs, _r, term, trunc, info = env.step(action)
            done = term or trunc
        return {
            "arm": arm, "seed": seed,
            "placement": info.get("placement") or env.n_players,
            "fight_calls": fights, "search_buys": buys,
            "seconds": time.time() - started,
        }
    finally:
        search_mod.fight_value = original


def paired_t(control: list[int], arm: list[int]) -> tuple[float, float]:
    diffs = [b - a for a, b in zip(control, arm, strict=True)]
    n = len(diffs)
    mean = sum(diffs) / n
    if n < 2:
        return mean, 0.0
    var = sum((d - mean) ** 2 for d in diffs) / (n - 1)
    return mean, (mean / math.sqrt(var / n) if var > 0 else 0.0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=200)
    parser.add_argument("--start", type=int, default=47_000)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--arms", default=",".join(ARMS))
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    arms = [a for a in args.arms.split(",") if a]
    unknown = set(arms) - set(ARMS)
    if unknown:
        raise SystemExit(f"unknown arms {sorted(unknown)}; have {sorted(ARMS)}")
    seeds = list(range(args.start, args.start + args.episodes))
    jobs = [(arm, seed) for arm in arms for seed in seeds]

    context = mp.get_context("spawn")
    started = time.time()
    rows: list[dict] = []
    with context.Pool(processes=args.workers, initializer=_init) as pool:
        for row in pool.imap_unordered(_play, jobs):
            rows.append(row)
    elapsed = time.time() - started

    by_arm = {arm: sorted((r for r in rows if r["arm"] == arm),
                          key=lambda r: r["seed"]) for arm in arms}
    control = [r["placement"] for r in by_arm.get("control", [])]

    print(f"\n{args.episodes} seeds from {args.start}, {elapsed / 60:.1f} min\n")
    header = f"{'arm':<10}{'place':>8}{'vs ctrl':>10}{'t':>7}{'fights':>10}{'x cost':>8}{'buys':>7}"
    print(header)
    base_cost = (statistics.mean(r["fight_calls"] for r in by_arm["control"])
                 if control else None)
    for arm in arms:
        place = [r["placement"] for r in by_arm[arm]]
        fights = statistics.mean(r["fight_calls"] for r in by_arm[arm])
        buys = statistics.mean(r["search_buys"] for r in by_arm[arm])
        if control and arm != "control":
            delta, t = paired_t(control, place)
            cmp = f"{delta:>+10.3f}{t:>7.2f}"
        else:
            cmp = f"{'--':>10}{'--':>7}"
        ratio = f"{fights / base_cost:>8.2f}" if base_cost else f"{'--':>8}"
        print(f"{arm:<10}{statistics.mean(place):>8.3f}{cmp}"
              f"{fights:>10.1f}{ratio}{buys:>7.2f}")

    if args.json:
        args.json.write_text(json.dumps(rows, indent=1))
        print(f"\nper-episode rows: {args.json}")


if __name__ == "__main__":
    main()
