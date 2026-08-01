"""Evaluation harness: measure a policy against the heuristic bots.

Doc 03 sec 4 names **win rate and average placement** as the core success
metric, so both are reported here, along with top-4 rate (the metric TFT
players actually optimise) and a random-policy baseline for reference.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Sequence

import numpy as np

from engine.hexgrid import axial_to_offset
from rl.env import TFTEnv


@dataclass
class EvalResult:
    """Aggregate performance over a set of evaluation episodes."""

    episodes: int
    placements: list[int] = field(default_factory=list)
    rewards: list[float] = field(default_factory=list)
    rounds: list[int] = field(default_factory=list)
    illegal_actions: int = 0

    @property
    def avg_placement(self) -> float:
        return sum(self.placements) / len(self.placements) if self.placements else 0.0

    @property
    def win_rate(self) -> float:
        return self.placements.count(1) / len(self.placements) if self.placements else 0.0

    @property
    def top4_rate(self) -> float:
        if not self.placements:
            return 0.0
        return sum(1 for p in self.placements if p <= 4) / len(self.placements)

    @property
    def avg_reward(self) -> float:
        return sum(self.rewards) / len(self.rewards) if self.rewards else 0.0

    @property
    def distribution(self) -> dict[int, int]:
        return dict(sorted(Counter(self.placements).items()))

    def summary(self) -> str:
        bars = " ".join(
            f"{place}:{self.distribution.get(place, 0)}" for place in range(1, 9)
        )
        return (
            f"episodes={self.episodes}  avg_placement={self.avg_placement:.3f}  "
            f"win_rate={self.win_rate:.1%}  top4={self.top4_rate:.1%}  "
            f"avg_reward={self.avg_reward:.3f}\n  placements  {bars}"
        )

    def as_dict(self) -> dict:
        return {
            "episodes": self.episodes,
            "avg_placement": round(self.avg_placement, 4),
            "win_rate": round(self.win_rate, 4),
            "top4_rate": round(self.top4_rate, 4),
            "avg_reward": round(self.avg_reward, 4),
            "distribution": self.distribution,
            "illegal_actions": self.illegal_actions,
        }


PolicyFn = Callable[[np.ndarray, np.ndarray], int]


def random_policy(rng: random.Random) -> PolicyFn:
    """Uniform over legal actions -- the baseline any agent must beat."""

    def act(obs: np.ndarray, mask: np.ndarray) -> int:
        legal = np.flatnonzero(mask)
        return int(rng.choice(list(legal))) if len(legal) else 0

    return act


def end_planning_policy(env: TFTEnv) -> PolicyFn:
    """Does nothing every round. The absolute floor."""

    def act(obs: np.ndarray, mask: np.ndarray) -> int:
        return env.action_space_helper.end_index

    return act


def _unit_strength(unit) -> tuple[int, int]:
    return (unit.star_level, unit.champion.cost)


def scripted_policy(env: TFTEnv, level_at_gold: int = 30, keep_interest: bool = True) -> PolicyFn:
    """A competent heuristic expressed **through the action space**.

    This is the ceiling check: if a sensible heuristic cannot reach roughly
    average placement (4.5) against the same heuristic bots, then the action
    space or the environment is handicapping the agent and a learned policy
    could never do better either. It also gives PPO a real target to beat.

    Mirrors :class:`rl.opponents.GreedyPolicy`: protect interest gold, buy the
    best affordable unit, field the strongest units (melee front, ranged back),
    upgrade the board by swapping in stronger bench units, level on a gold
    threshold.
    """
    space = env.action_space_helper

    def spendable(player) -> int:
        if not keep_interest:
            return player.gold
        per = player.config.interest_per_gold
        cap = player.config.interest_cap * per
        floor = min(player.gold - (player.gold % per), cap)
        return max(player.gold - floor, 0)

    def board_slot_of(player, unit) -> int | None:
        for slot in range(space.board_slots):
            if player.board.get(space.hex_for_slot(slot)) is unit:
                return slot
        return None

    def act(obs: np.ndarray, mask: np.ndarray) -> int:
        player = env.player
        half_rows = player.hex_board.half_rows

        # -- a unit is held: put it down -----------------------------------
        if env.executor.selected is not None:
            held = env.executor.unit_at(player, env.executor.selected)
            # Only an *empty* hex actually fields a unit; an occupied one is a
            # legal swap that leaves the board size unchanged.
            empty = [
                slot
                for slot in range(space.board_slots)
                if mask[space.place_offset + slot]
                and space.hex_for_slot(slot) not in player.board
            ]
            if empty and len(player.board) < player.max_board_units:
                ranged = held is not None and held.derived_stats().attack_range > 1
                empty.sort(key=lambda s: axial_to_offset(space.hex_for_slot(s))[0] - half_rows)
                return space.place_offset + (empty[-1] if ranged else empty[0])

            # Board is full: swap out the weakest fielded unit if this is better.
            if player.board and held is not None:
                weakest = min(player.board_units, key=_unit_strength)
                if _unit_strength(held) > _unit_strength(weakest):
                    slot = board_slot_of(player, weakest)
                    if slot is not None and mask[space.place_offset + slot]:
                        return space.place_offset + slot

            benches = [
                i
                for i in range(space.place_offset, space.place_offset + space.unit_slots)
                if mask[i]
            ]
            if benches:
                return benches[0]
            return space.end_index

        # -- nothing held --------------------------------------------------
        budget = spendable(player)
        buys = [
            i
            for i in range(space.shop_slots)
            if mask[i] and player.data.champions[player.shop.slots[i]].cost <= budget
        ]
        if buys:
            def buy_key(i: int):
                champion = player.data.champions[player.shop.slots[i]]
                owned = any(u.champion.id == champion.id for u in player.all_units)
                return (owned, champion.cost)

            return max(buys, key=buy_key)

        benched = [
            b
            for b in range(player.config.bench_size)
            if mask[space.select_offset + space.slot_for_bench(b)]
        ]
        if benched:
            best = max(benched, key=lambda b: _unit_strength(player.bench[b]))
            if len(player.board) < player.max_board_units:
                return space.select_offset + space.slot_for_bench(best)
            # Board full: only pick up a bench unit that beats the weakest one.
            if player.board:
                weakest = min(player.board_units, key=_unit_strength)
                if _unit_strength(player.bench[best]) > _unit_strength(weakest):
                    return space.select_offset + space.slot_for_bench(best)

        if mask[space.buy_xp_index] and player.gold >= level_at_gold:
            return space.buy_xp_index

        return space.end_index

    return act


def sb3_policy(model, deterministic: bool = True) -> PolicyFn:
    """Wrap a MaskablePPO model as a plain ``(obs, mask) -> action`` callable."""

    def act(obs: np.ndarray, mask: np.ndarray) -> int:
        action, _ = model.predict(obs, action_masks=mask, deterministic=deterministic)
        return int(action)

    return act


def evaluate(
    env: TFTEnv,
    policy: PolicyFn,
    episodes: int = 20,
    seeds: Sequence[int] | None = None,
    max_steps: int = 5000,
) -> EvalResult:
    """Play ``episodes`` games and aggregate the outcome.

    Seeds are fixed by default so two policies are compared on the *same* set
    of games, which removes most of the variance from the comparison.
    """
    seeds = list(seeds) if seeds is not None else list(range(episodes))
    result = EvalResult(episodes=len(seeds))

    for seed in seeds:
        obs, info = env.reset(seed=seed)
        total_reward = 0.0
        terminated = False
        steps = 0
        while not terminated:
            action = policy(obs, env.action_mask())
            obs, reward, terminated, _, info = env.step(action)
            total_reward += reward
            result.illegal_actions += bool(info.get("illegal_action"))
            steps += 1
            if steps > max_steps:
                raise RuntimeError(f"episode (seed {seed}) exceeded {max_steps} steps")
        result.placements.append(info.get("placement") or env.n_players)
        result.rewards.append(total_reward)
        result.rounds.append(env.match.rounds_played if env.match else 0)
    return result


def compare(
    env: TFTEnv, policies: dict[str, PolicyFn], episodes: int = 20
) -> dict[str, EvalResult]:
    """Evaluate several policies on an identical set of seeds."""
    seeds = list(range(episodes))
    return {name: evaluate(env, fn, seeds=seeds) for name, fn in policies.items()}
