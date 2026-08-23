"""Can a candidate-value model safely shortlist ``best_move`` layouts?

This follows the validated buy probe's contract rather than trying to imitate
the teacher's final action.  Each live positional search becomes a tiny,
matched ranking problem: unchanged board plus the exact sampled legal layouts
from :func:`rl.search.move_search_candidates` are scored against the same
visible opponent panel and combat seeds.  The model sees relational facts of
each resulting layout, and the deployment metric retains unchanged plus the
three highest predicted moves for an exact-simulator final decision.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import rl.search as search_mod  # noqa: E402
from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import greedy_action_policy  # noqa: E402
from rl.opponents import FAST8  # noqa: E402
from rl.search import (  # noqa: E402
    clone_board,
    fight_value,
    move_search_candidates,
    search_policy,
)
from scripts.search_buy_value_probe import candidate_features, fit  # noqa: E402


def _layout_after_move(player, source, target) -> dict:
    """Return the legal layout produced by one sampled move without mutation."""
    layout = dict(player.board)
    moving = layout.pop(source)
    displaced = layout.pop(target, None)
    layout[target] = moving
    if displaced is not None:
        layout[source] = displaced
    return layout


def _layout_score(data, player, match, panel, seeds, layout: dict) -> float:
    """Score a layout with the same clone/restore discipline as ``best_move``."""
    board = player.hex_board
    original = dict(player.board)
    try:
        player.board.clear()
        player.board.update(layout)
        total = 0.0
        for other, trial_seeds in zip(panel, seeds, strict=True):
            for seed in trial_seeds:
                total += fight_value(
                    data,
                    board,
                    clone_board(match, player, 0),
                    clone_board(match, other, 1),
                    seed,
                )
        return total / max(len(seeds[0]), 1)
    finally:
        player.board.clear()
        player.board.update(original)


def _layout_features(data, player, match, panel, layout: dict) -> np.ndarray:
    """Reuse the buy probe's relational feature contract for a moved board."""
    original = dict(player.board)
    try:
        player.board.clear()
        player.board.update(layout)
        return candidate_features(data, player, match, panel)
    finally:
        player.board.clear()
        player.board.update(original)


def collect(
    data,
    episode_seeds: range,
    *,
    trials: int,
    max_candidates: int,
    panel_size: int,
) -> dict:
    """Play frozen teacher games while recording exact positional candidates."""
    xs, ys, groups = [], [], []
    group = 0
    original = search_mod.best_move

    for episode_seed in episode_seeds:
        env = TFTEnv(data, scouting="tokens", max_actions_per_round=600)
        policy = search_policy(
            env,
            base=greedy_action_policy(env, econ=FAST8),
            mode="move",
            max_candidates=max_candidates,
            panel_size=panel_size,
            trials=trials,
            state_seeded=True,
        )
        env.register_external_policy(policy)
        observation, _ = env.reset(seed=episode_seed)

        def wrapped(probe_env, teacher_rng, **kwargs):
            nonlocal group
            context = move_search_candidates(
                probe_env,
                teacher_rng,
                max_candidates=kwargs["max_candidates"],
                panel_size=kwargs["panel_size"],
                trials=kwargs["trials"],
                state_seeded=kwargs["state_seeded"],
            )
            if context is not None:
                player, match = probe_env.player, probe_env.match
                assert match is not None
                panel, seeds, moves = context
                layouts = [dict(player.board)]
                # This happens after the unchanged layout is captured, matching
                # the live search's baseline-then-candidates evaluation order.
                layouts.extend(_layout_after_move(player, source, target) for source, target in moves)
                baseline = _layout_score(data, player, match, panel, seeds, layouts[0])
                for layout in layouts:
                    xs.append(_layout_features(data, player, match, panel, layout))
                    ys.append(_layout_score(data, player, match, panel, seeds, layout) - baseline)
                    groups.append(group)
                group += 1
            return original(probe_env, teacher_rng, **kwargs)

        search_mod.best_move = wrapped
        try:
            terminated = False
            while not terminated:
                action = policy(observation, env.action_masks())
                observation, _reward, terminated, truncated, _info = env.step(action)
                terminated = terminated or truncated
        finally:
            search_mod.best_move = original

    if not xs:
        raise RuntimeError("the position search never produced a candidate group")
    return {"x": np.stack(xs), "y": np.asarray(ys), "group": np.asarray(groups)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-episodes", type=int, default=12)
    parser.add_argument("--holdout-episodes", type=int, default=4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--holdout-offset", type=int, default=10_000)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--max-candidates", type=int, default=6)
    parser.add_argument("--panel-size", type=int, default=1)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--cache", type=Path, help="persist/load labelled candidate corpus")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    data = load_all()
    if args.cache and args.cache.exists():
        blob = np.load(args.cache)
        train = {name: blob[f"train_{name}"] for name in ("x", "y", "group")}
        holdout = {name: blob[f"holdout_{name}"] for name in ("x", "y", "group")}
    else:
        train = collect(
            data,
            range(args.seed, args.seed + args.train_episodes),
            trials=args.trials,
            max_candidates=args.max_candidates,
            panel_size=args.panel_size,
        )
        holdout = collect(
            data,
            range(args.holdout_offset, args.holdout_offset + args.holdout_episodes),
            trials=args.trials,
            max_candidates=args.max_candidates,
            panel_size=args.panel_size,
        )
        if args.cache:
            np.savez(
                args.cache,
                **{f"train_{name}": value for name, value in train.items()},
                **{f"holdout_{name}": value for name, value in holdout.items()},
            )

    result = fit(train, holdout, args.epochs, args.seed, "deepset")
    payload = {
        "train_candidates": len(train["y"]),
        "holdout_candidates": len(holdout["y"]),
        "train_states": len(set(train["group"])),
        "holdout_states": len(set(holdout["group"])),
        "trials": args.trials,
        "max_candidates": args.max_candidates,
        "panel_size": args.panel_size,
        "epochs": args.epochs,
        "representation": "deepset",
        **result,
    }
    print(json.dumps(payload, indent=2))
    if args.json:
        args.json.write_text(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
