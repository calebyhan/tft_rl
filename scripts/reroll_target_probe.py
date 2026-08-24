"""Pilot whether a reroll's short-horizon counterfactual is replayable (doc 99 160.61)."""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.loader import load_all  # noqa: E402
from rl.action import ActionKind  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import greedy_action_policy  # noqa: E402
from rl.opponents import FAST8  # noqa: E402
from rl.search import clone_board, fight_value, opponent_panel  # noqa: E402
from scripts.policy_conformance import first_difference, snapshot  # noqa: E402


def _margin(env: TFTEnv, seed: int, trials: int) -> float | None:
    """Fixed-seed post-round combat margin against one visible opponent."""
    match = env.match
    assert match is not None
    panel = opponent_panel(match, env.player, 1)
    if not panel:
        return None
    rng = random.Random(seed)
    total = 0.0
    for _ in range(trials):
        total += fight_value(
            env.data,
            env.player.hex_board,
            clone_board(match, env.player, 0),
            clone_board(match, panel[0], 1),
            rng.randrange(2**31),
        )
    return total / trials


def _run_branch(data, episode_seed: int, target_step: int, forced: ActionKind, trials: int) -> dict:
    """Replay a seed, force one legal choice, and finish its planning round."""
    env = TFTEnv(data, scouting="tokens", max_actions_per_round=600)
    policy = greedy_action_policy(env, econ=FAST8)
    observation, _ = env.reset(seed=episode_seed)
    before = None
    forced_action = None
    target_round = None

    for step in range(6000):
        mask = env.action_masks()
        action = int(policy(observation, mask))
        if step == target_step:
            before = snapshot(env)
            target_round = str(env.match.round_id)
            forced_action = (
                env.action_space_helper.reroll_index
                if forced is ActionKind.REROLL else env.action_space_helper.end_index
            )
            if not mask[forced_action]:
                raise AssertionError(f"forced {forced.name} was masked at step {step}")
            action = forced_action
        observation, _reward, terminated, truncated, _info = env.step(action)
        if terminated or truncated:
            raise AssertionError("game ended before the forced reroll phase resolved")
        if before is not None and str(env.match.round_id) != target_round:
            player = env.player
            return {
                "before": before,
                "forced": forced.name,
                "gold": player.gold,
                "hp": player.hp,
                "board_units": len(player.board),
                "margin": _margin(env, episode_seed * 10_000 + target_step, trials),
                "round_after": str(env.match.round_id),
            }
    raise AssertionError("branch did not finish its planning round")


def _first_reroll_step(data, episode_seed: int) -> int | None:
    """Find the first action the fixed policy itself elects to reroll."""
    env = TFTEnv(data, scouting="tokens", max_actions_per_round=600)
    policy = greedy_action_policy(env, econ=FAST8)
    observation, _ = env.reset(seed=episode_seed)
    for step in range(6000):
        action = int(policy(observation, env.action_masks()))
        if env.action_space_helper.decode(action).kind is ActionKind.REROLL:
            return step
        observation, _reward, terminated, truncated, _info = env.step(action)
        if terminated or truncated:
            return None
    raise AssertionError("episode exceeded action cap")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=12)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    data = load_all()
    rows = []
    for episode_seed in range(args.seed, args.seed + args.episodes):
        step = _first_reroll_step(data, episode_seed)
        if step is None:
            continue
        rolled = _run_branch(data, episode_seed, step, ActionKind.REROLL, args.trials)
        ended = _run_branch(data, episode_seed, step, ActionKind.END_PLANNING, args.trials)
        difference = first_difference(rolled["before"], ended["before"])
        if difference is not None:
            raise AssertionError(f"branch prefixes differ before intervention: {difference}")
        if rolled["round_after"] != ended["round_after"]:
            raise AssertionError("branches did not reach the same next planning round")
        rows.append({
            "seed": episode_seed,
            "step": step,
            "delta_hp": rolled["hp"] - ended["hp"],
            "delta_gold": rolled["gold"] - ended["gold"],
            "delta_board_units": rolled["board_units"] - ended["board_units"],
            "delta_margin": (
                None if rolled["margin"] is None or ended["margin"] is None
                else rolled["margin"] - ended["margin"]
            ),
        })
    if not rows:
        raise RuntimeError("no baseline rerolls found; the probe asserted nothing")
    summary = {"states": len(rows), "rows": rows}
    for key in ("delta_hp", "delta_gold", "delta_board_units", "delta_margin"):
        values = [row[key] for row in rows if row[key] is not None]
        summary[key] = {
            "mean": statistics.mean(values), "min": min(values), "max": max(values),
            "positive": sum(value > 0 for value in values),
            "negative": sum(value < 0 for value in values), "zero": sum(value == 0 for value in values),
        }
    print(json.dumps(summary, indent=2))
    if args.json:
        args.json.write_text(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
