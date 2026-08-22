"""Locate the first whole-match divergence of direct and action search-buy."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.loader import load_all  # noqa: E402
from engine.match import PlanningContext  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.opponents import FAST8  # noqa: E402
from rl.search import search_buy_greedy_policy  # noqa: E402
from scripts.policy_conformance import first_difference, snapshot  # noqa: E402
from scripts.search_teacher_ab import SearchBuyPolicy  # noqa: E402


def match_snapshot(env: TFTEnv) -> dict:
    assert env.match is not None
    return {
        "agent": snapshot(env),
        "players": [
            {"hp": player.hp, "gold": player.gold, "level": player.level,
             "xp": player.xp, "alive": player.alive, "placement": player.placement,
             "shop": list(player.shop.slots),
             "items": [item.id for item in player.item_bag],
             "augments": [augment.id for augment in player.augments],
             "board": sorted((hex_.q, hex_.r, unit.champion.id, unit.star_level,
                                tuple(item.id for item in unit.items))
                             for hex_, unit in player.board.items()),
             "bench": [None if unit is None else (unit.champion.id, unit.star_level,
                                                    tuple(item.id for item in unit.items))
                       for unit in player.bench]}
            for player in env.match.players
        ],
        "rng": hashlib.sha256(repr(env.match.rng.getstate()).encode()).hexdigest(),
        "placements": dict(env.match.placements),
    }


def direct_phase(env: TFTEnv, policy: SearchBuyPolicy) -> None:
    assert env.match is not None
    player, match = env.player, env.match
    trace = []
    originals = {}
    for name in ("buy", "sell", "reroll", "buy_xp", "move_to_board", "equip_from_bag"):
        original = getattr(player, name)
        originals[name] = original

        def record(*args, _name=name, _original=original, **kwargs):
            trace.append(_name)
            return _original(*args, **kwargs)

        setattr(player, name, record)
    if player.has_pending_offering:
        player.pick_offering(policy.choose_offering(player, player.realm_offer))
        trace.append("pick_offering")
    if player.has_pending_augment:
        player.pick_augment(0)
        trace.append("pick_augment")
    try:
        policy.plan(player, PlanningContext(match, match.round_id, match.pool, match.rng,
                                            env._pending_pve))
    finally:
        for name, original in originals.items():
            setattr(player, name, original)
    return trace


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--max-rounds", type=int, default=160,
        help="safety limit for traced planning rounds (default: 160)",
    )
    parser.add_argument("--json", type=Path)
    parser.add_argument(
        "--hybrid-cache", type=Path,
        help="trace the frozen learned shortlist instead of the full buyer",
    )
    args = parser.parse_args()
    data = load_all()
    direct, action = TFTEnv(data=data, max_actions_per_round=600), TFTEnv(
        data=data, max_actions_per_round=600
    )
    direct.reset(seed=args.seed)
    obs, _ = action.reset(seed=args.seed)
    restore_best_buy = None
    if args.hybrid_cache:
        import rl.search as search_mod
        from scripts import search_buy_hybrid_ab as hybrid_mod

        hybrid_mod._init(str(args.hybrid_cache))
        direct_policy = hybrid_mod.HybridSearchBuyPolicy(seed=0, econ=FAST8)
        restore_best_buy = search_mod.best_buy
        search_mod.best_buy = hybrid_mod.hybrid_best_buy
    else:
        direct_policy = SearchBuyPolicy(seed=0, econ=FAST8)
    direct.register_external_policy(direct_policy)
    action_policy = search_buy_greedy_policy(action, econ=FAST8)

    rows = []
    try:
        for _ in range(args.max_rounds):
            before = first_difference(match_snapshot(direct), match_snapshot(action))
            if before is not None:
                rows.append({"round": str(direct.match.round_id), "when": "pre", "diff": before})
                break
            if not direct.player.alive or not action.player.alive:
                rows.append({"round": str(direct.match.round_id), "when": "terminal", "diff": None})
                break
            round_id = str(direct.match.round_id)
            direct_actions = direct_phase(direct, direct_policy)
            direct._advance_round()
            if not direct.match.finished and direct.player.alive:
                direct._begin_planning()
            action_actions = []
            while (
                not action.match.finished
                and action.player.alive
                and str(action.match.round_id) == round_id
            ):
                selected = action_policy(obs, action.action_masks())
                action_actions.append(repr(action.action_space_helper.decode(selected)))
                obs, _reward, terminated, truncated, _info = action.step(selected)
                if terminated or truncated:
                    break
            if direct.match.finished:
                direct.match._finalise_placements()
            if action.match.finished:
                action.match._finalise_placements()
            after = first_difference(match_snapshot(direct), match_snapshot(action))
            rows.append({"round": round_id, "when": "post", "diff": after,
                         "direct_actions": direct_actions, "action_actions": action_actions})
            if after is not None or direct.match.finished or action.match.finished:
                break
    finally:
        if restore_best_buy is not None:
            import rl.search as search_mod

            search_mod.best_buy = restore_best_buy
    print(json.dumps(rows[-1], indent=2, default=str))
    if args.json:
        args.json.write_text(json.dumps(rows, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
