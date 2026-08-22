"""Locate the first direct-Match versus action-environment search-buy difference.

Unlike ``search_buy_match_trace.py``, the direct side here is a real
``Match.play_round`` loop rather than a manually driven paused environment.
It therefore tests the round driver itself as well as the policy port.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.loader import load_all  # noqa: E402
from engine.match import Match  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.opponents import FAST8, default_opponent  # noqa: E402
from rl.search import search_buy_greedy_policy  # noqa: E402
from scripts.policy_conformance import first_difference  # noqa: E402
from scripts.search_teacher_ab import SearchBuyPolicy  # noqa: E402


def snapshot(match: Match, seat: int = 0) -> dict:
    """Complete state that can be altered by a round or policy callback."""
    return {
        "round": str(match.round_id),
        "agent": seat,
        "players": [
            {
                "hp": player.hp,
                "gold": player.gold,
                "level": player.level,
                "xp": player.xp,
                "alive": player.alive,
                "placement": player.placement,
                "shop": list(player.shop.slots),
                "items": [item.id for item in player.item_bag],
                "augments": [augment.id for augment in player.augments],
                "board": sorted(
                    (hex_.q, hex_.r, unit.champion.id, unit.star_level,
                     tuple(item.id for item in unit.items))
                    for hex_, unit in player.board.items()
                ),
                "bench": [
                    None if unit is None else (
                        unit.champion.id, unit.star_level,
                        tuple(item.id for item in unit.items),
                    )
                    for unit in player.bench
                ],
            }
            for player in match.players
        ],
        "pool": match.pool.snapshot(),
        "rng": hashlib.sha256(repr(match.rng.getstate()).encode()).hexdigest(),
        "placements": dict(match.placements),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-rounds", type=int, default=160)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    data = load_all()
    direct = Match(
        data,
        [SearchBuyPolicy(seed=0, econ=FAST8)]
        + [default_opponent(seat) for seat in range(1, 8)],
        seed=args.seed,
    )
    action = TFTEnv(data=data, max_actions_per_round=600)
    obs, _ = action.reset(seed=args.seed)
    policy = search_buy_greedy_policy(action, econ=FAST8)
    rows = []

    for _ in range(args.max_rounds):
        assert action.match is not None
        if direct.finished or action.match.finished:
            direct._finalise_placements()
            action.match._finalise_placements()
            rows.append({"round": str(direct.round_id), "when": "terminal", "diff": None})
            break

        round_id = str(direct.round_id)
        direct.play_round()
        action_actions = []
        # `TFTEnv.step` normally opens the next planning phase immediately
        # after END_PLANNING. Match.play_round instead returns at resolution,
        # so suppress that one automatic call while taking the comparison
        # snapshot. It is restored and invoked below before the next round.
        begin_planning = action._begin_planning
        action._begin_planning = lambda: None
        while (
            not action.match.finished
            and action.player.alive
            and str(action.match.round_id) == round_id
        ):
            selected = policy(obs, action.action_masks())
            action_actions.append(repr(action.action_space_helper.decode(selected)))
            obs, _reward, terminated, truncated, _info = action.step(selected)
            if terminated or truncated:
                break
        action._begin_planning = begin_planning

        if direct.finished:
            direct._finalise_placements()
        if action.match.finished:
            action.match._finalise_placements()
        after = first_difference(snapshot(direct), snapshot(action.match))
        rows.append({
            "round": round_id,
            "when": "post",
            "diff": after,
            "action_actions": action_actions,
        })
        if after is not None or direct.finished or action.match.finished:
            break
        # The environment correctly terminates once the controlled seat dies;
        # Match continues only to decide the surviving seats' relative places.
        # Its post-death state is not an action-policy comparison target.
        if not action.player.alive:
            break
        if action.player.alive:
            action._begin_planning()
            obs = action._observe()

    print(json.dumps(rows[-1], indent=2, default=str))
    if args.json:
        args.json.write_text(json.dumps(rows, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
