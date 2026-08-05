"""How much gold does each econ arm actually spend, and on what?

The discriminator for doc 99 entry 37.2 outcome D. If a `roll@N` arm comes out
*worse* than control, the question is whether rolling is genuinely bad play in
this engine or whether the reroll branch burns gold without converting it into
units. Placement cannot tell those apart; action counts can.

Counts are per game, averaged over seeds. Cheap -- a few seconds an arm.

    .venv/bin/python scripts/sink_probe.py --episodes 20 --roll-at-level 7
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import evaluate, scripted_policy  # noqa: E402


def counting(env: TFTEnv, policy):
    """Wrap a policy so every action it picks is tallied by kind."""
    space = env.action_space_helper
    counts: Counter[str] = Counter()

    def act(obs, mask):
        action = policy(obs, mask)
        # Ask the action space rather than re-deriving index ranges here; the
        # offsets move whenever the space changes and a stale copy would
        # miscount silently.
        counts[space.decode(action).kind.name] += 1
        return action

    return act, counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=20)
    parser.add_argument("--roll-at-level", type=int, nargs="*", default=[7])
    args = parser.parse_args()

    data = load_all()
    seeds = range(args.episodes)
    n = args.episodes

    arms: dict[str, dict] = {"control": {}, "sell": {"sell_bench": True}}
    for lv in args.roll_at_level:
        arms[f"roll@{lv}"] = {"roll_at_level": lv}
        arms[f"roll@{lv}+sell"] = {"roll_at_level": lv, "sell_bench": True}

    kinds = ("REROLL", "BUY_XP", "BUY", "SELL", "SELECT", "PLACE", "EQUIP")
    header = "".join(f"{k.lower():>9}" for k in kinds)
    print(f"{'arm':<12}{'place':>8}{header}")
    for name, flags in arms.items():
        env = TFTEnv(data=data)
        policy, counts = counting(env, scripted_policy(env, **flags))
        result = evaluate(env, policy, seeds=seeds)
        row = "".join(f"{counts[k] / n:>9.1f}" for k in kinds)
        print(f"{name:<12}{result.avg_placement:>8.3f}{row}")
    print("\nPer game, averaged over seeds. A reroll arm that rolls but does not")
    print("raise BUY is burning gold without converting it (doc 99 entry 37.2 D).")


if __name__ == "__main__":
    main()
