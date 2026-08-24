"""Can one planning snapshot sample diverse legal reroll shops? (doc 99 160.65)."""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.loader import load_all  # noqa: E402
from rl.action import ActionKind  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import greedy_action_policy  # noqa: E402
from rl.opponents import FAST8  # noqa: E402
from rl.planning_snapshot import PlanningSnapshot  # noqa: E402


def _first_reroll_snapshot(data, episode_seed: int) -> PlanningSnapshot:
    env = TFTEnv(data, scouting="tokens", max_actions_per_round=600)
    policy = greedy_action_policy(env, econ=FAST8)
    observation, _ = env.reset(seed=episode_seed)
    for _ in range(6000):
        action = int(policy(observation, env.action_masks()))
        if env.action_space_helper.decode(action).kind is ActionKind.REROLL:
            assert env.match is not None
            return PlanningSnapshot.capture(env.player, env.match.pool, env.match.rng)
        observation, _reward, terminated, truncated, _info = env.step(action)
        if terminated or truncated:
            break
    raise RuntimeError(f"seed {episode_seed} reached no baseline reroll")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode-seed", type=int, default=0)
    parser.add_argument("--replicas", type=int, default=64)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    data = load_all()
    registry = TFTEnv(data).registry
    captured = _first_reroll_snapshot(data, args.episode_seed)
    shops, legal_buys, pair_offers = [], [], []
    for replica in range(args.replicas):
        player, pool, _rng = captured.restore(data, registry)
        player.reroll(pool, random.Random(args.seed + replica))
        shops.append(tuple(player.shop.slots))
        legal_buys.append(sum(player.can_buy(slot) for slot in range(len(player.shop))))
        held = Counter(
            unit.champion.id for unit in player.all_units if unit.star_level == 1
        )
        pair_offers.append(sum(held[champion_id] >= 2 for champion_id in player.shop.slots if champion_id))
    payload = {
        "replicas": args.replicas,
        "distinct_shops": len(set(shops)),
        "legal_buys": {"min": min(legal_buys), "max": max(legal_buys), "mean": sum(legal_buys) / len(legal_buys)},
        "pair_offers": {"min": min(pair_offers), "max": max(pair_offers), "mean": sum(pair_offers) / len(pair_offers)},
    }
    print(json.dumps(payload, indent=2))
    if args.json:
        args.json.write_text(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
