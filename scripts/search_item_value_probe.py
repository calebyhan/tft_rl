"""Test simulator-finalised item-allocation candidate values (doc 99 160.58)."""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.loader import load_all  # noqa: E402
from rl.action import ActionKind  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import greedy_action_policy  # noqa: E402
from rl.opponents import FAST8  # noqa: E402
from rl.search import (  # noqa: E402
    clone_board,
    fight_value,
    item_candidates,
    opponent_panel,
)
from scripts.search_buy_value_probe import (  # noqa: E402
    candidate_opponent_features,
    fit,
)


def _candidate_board(match, player, item, own_hex=None):
    """Clone a board and, optionally, equip an item on the clone at ``own_hex``."""
    team = clone_board(match, player, 0)
    if own_hex is not None:
        team[sorted(player.board).index(own_hex)].equip(item)
    return team


def _features(data, ours, match, panel) -> np.ndarray:
    rows = [
        candidate_opponent_features(ours, clone_board(match, other, 1), data)
        for other in panel
    ]
    values = np.zeros((2, len(rows[0]) + 1), dtype=float)
    for index, row in enumerate(rows):
        values[index, :-1] = row
        values[index, -1] = 1.0
    return values


def _score(data, player, match, panel, seeds, item=None, own_hex=None) -> float:
    total = 0.0
    for other, trial_seeds in zip(panel, seeds, strict=True):
        for seed in trial_seeds:
            total += fight_value(
                data,
                player.hex_board,
                _candidate_board(match, player, item, own_hex),
                clone_board(match, other, 1),
                seed,
            )
    return total / max(len(seeds[0]), 1)


def collect(data, episode_seeds: range, *, trials: int, max_candidates: int, panel_size: int) -> dict:
    """Label each first-bag-item action state from the action-space teacher."""
    xs, ys, groups = [], [], []
    group = 0
    for episode_seed in episode_seeds:
        env = TFTEnv(data, scouting="tokens", max_actions_per_round=600)
        base = greedy_action_policy(env, econ=FAST8)
        space = env.action_space_helper
        observation, _ = env.reset(seed=episode_seed)
        calls = 0

        def policy(obs, mask, *, _base=base, _space=space, _env=env, _episode_seed=episode_seed):
            nonlocal calls, group
            action = _base(obs, mask)
            decoded = _space.decode(action)
            if decoded.kind is ActionKind.EQUIP and decoded.a == 0:
                player, match = _env.player, _env.match
                assert match is not None
                candidate_context = item_candidates(player, max_candidates)
                panel = opponent_panel(match, player, panel_size)
                if candidate_context is not None and panel:
                    item, targets = candidate_context
                    label_rng = random.Random((_episode_seed + 1) * 100_000 + calls)
                    seeds = [[label_rng.randrange(2**31) for _ in range(trials)] for _ in panel]
                    baseline = _score(data, player, match, panel, seeds)
                    for target in (None, *targets):
                        ours = _candidate_board(match, player, item, target)
                        xs.append(_features(data, ours, match, panel))
                        ys.append(_score(data, player, match, panel, seeds, item, target) - baseline)
                        groups.append(group)
                    group += 1
            calls += 1
            return action

        terminated = False
        while not terminated:
            action = policy(observation, env.action_masks())
            observation, _reward, terminated, truncated, _info = env.step(action)
            terminated = terminated or truncated
    if not xs:
        raise RuntimeError("the teacher never emitted a first-bag-item equip action")
    return {"x": np.stack(xs), "y": np.asarray(ys), "group": np.asarray(groups)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-episodes", type=int, default=12)
    parser.add_argument("--holdout-episodes", type=int, default=4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--holdout-offset", type=int, default=10_000)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--max-candidates", type=int, default=4)
    parser.add_argument("--panel-size", type=int, default=1)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    data = load_all()
    if args.cache and args.cache.exists():
        blob = np.load(args.cache)
        train = {key: blob[f"train_{key}"] for key in ("x", "y", "group")}
        holdout = {key: blob[f"holdout_{key}"] for key in ("x", "y", "group")}
    else:
        train = collect(data, range(args.seed, args.seed + args.train_episodes), trials=args.trials, max_candidates=args.max_candidates, panel_size=args.panel_size)
        holdout = collect(data, range(args.holdout_offset, args.holdout_offset + args.holdout_episodes), trials=args.trials, max_candidates=args.max_candidates, panel_size=args.panel_size)
        if args.cache:
            np.savez(args.cache, **{f"train_{key}": value for key, value in train.items()}, **{f"holdout_{key}": value for key, value in holdout.items()})
    result = fit(train, holdout, args.epochs, args.seed, "deepset")
    payload = {
        "train_candidates": len(train["y"]), "holdout_candidates": len(holdout["y"]),
        "train_states": len(set(train["group"])), "holdout_states": len(set(holdout["group"])),
        "trials": args.trials, "max_candidates": args.max_candidates, "panel_size": args.panel_size,
        "epochs": args.epochs, "representation": "deepset", **result,
    }
    print(json.dumps(payload, indent=2))
    if args.json:
        args.json.write_text(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
