"""Bounded shared-seed match-level check for the search-buy action port.

This is a retention pilot, not a search-strength measurement: direct and
action arms both use the same once-per-round SearchBuy teacher.  A materially
different result would expose a match-level port seam missed by planning-state
conformance; a small difference is inconclusive at this sample size.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.loader import load_all  # noqa: E402
from engine.match import Match  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.opponents import FAST8, default_opponent  # noqa: E402
from rl.search import search_buy_greedy_policy  # noqa: E402
from scripts.search_teacher_ab import SearchBuyPolicy  # noqa: E402


def paired_t(direct: list[int], action: list[int]) -> tuple[float, float]:
    diffs = [b - a for a, b in zip(direct, action, strict=True)]
    mean = sum(diffs) / len(diffs)
    if len(diffs) < 2:
        return mean, 0.0
    variance = sum((value - mean) ** 2 for value in diffs) / (len(diffs) - 1)
    return mean, mean / math.sqrt(variance / len(diffs)) if variance else 0.0


def direct_game(data, seed: int) -> int:
    policies = [SearchBuyPolicy(seed=0, econ=FAST8)] + [
        default_opponent(seat) for seat in range(1, 8)
    ]
    match = Match(data, policies, seed=seed)
    return match.run().placements[0]


def action_game(data, seed: int) -> tuple[int, int]:
    env = TFTEnv(data=data, max_actions_per_round=600)
    obs, _ = env.reset(seed=seed)
    policy = search_buy_greedy_policy(env, econ=FAST8)
    caps = 0
    while True:
        before = env.actions_left
        action = policy(obs, env.action_masks())
        obs, _reward, terminated, truncated, _info = env.step(action)
        caps += int(before == 1 and not (terminated or truncated))
        if terminated or truncated:
            assert env.player.placement is not None
            return env.player.placement, caps


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=10)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    data = load_all()
    seeds = range(args.seed, args.seed + args.games)
    direct, action, caps = [], [], 0
    for seed in seeds:
        direct.append(direct_game(data, seed))
        placement, capped = action_game(data, seed)
        action.append(placement)
        caps += capped
        print(f"seed {seed}: direct={direct[-1]} action={placement}", flush=True)

    delta, t_stat = paired_t(direct, action)
    print(f"\nn={args.games} shared seeds, FAST8 once-per-round search buy")
    print(f"direct mean={sum(direct) / len(direct):.3f}  {dict(sorted(Counter(direct).items()))}")
    print(f"action mean={sum(action) / len(action):.3f}  {dict(sorted(Counter(action).items()))}")
    print(f"action - direct={delta:+.3f}  paired t={t_stat:+.2f}  cap rounds={caps}")
    if args.json:
        args.json.write_text(json.dumps({
            "seeds": list(seeds), "direct": direct, "action": action,
            "delta": delta, "t": t_stat, "cap_rounds": caps,
        }, indent=2))


if __name__ == "__main__":
    main()
