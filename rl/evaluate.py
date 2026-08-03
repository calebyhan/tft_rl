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

# Last-place rate above which a result is treated as degenerate rather than
# measured. 50% is well clear of a competent policy (the scripted baseline sits
# at 22%) and well below the 84% that made four experiments uninterpretable.
FLOOR_WARNING_THRESHOLD = 0.5


# LP awarded per placement in ranked TFT, 1st through 8th.
#
# Average placement -- this project's primary metric since doc 03 sec 4 -- is
# linear: it scores 1st->2nd and 6th->7th as identical improvements. Ranked TFT
# does not. Top four gain, bottom four lose, and 1st is worth far more than
# 4th. That difference is not academic here: doc 99 entry 31 measured a PPO arm
# that is a *null* on average placement (+0.070, t=0.38) while moving firsts
# 8.3% -> 12.3% and top-four 47.0% -> 51.0%, both past the scripted teacher.
#
# These are the mid-tier values (roughly Gold/Platinum, before rank and MMR
# adjustments), which Riot does not publish exactly -- they are community
# documented, like the shop odds. The *shape* is what matters and is not in
# doubt: steeply convex toward 1st, symmetric-ish around the 4/5 boundary.
# Recorded in config provenance terms as community_documented.
LP_BY_PLACEMENT = {1: 40, 2: 28, 3: 18, 4: 8, 5: -8, 6: -16, 7: -24, 8: -32}


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
    def avg_lp(self) -> float:
        """Mean LP per game under :data:`LP_BY_PLACEMENT`.

        Reported *alongside* average placement, never instead of it. The two
        can disagree -- that is the point of having both -- and every number in
        this project's history was measured against placement.
        """
        if not self.placements:
            return 0.0
        return sum(LP_BY_PLACEMENT.get(p, 0) for p in self.placements) / len(
            self.placements
        )

    @property
    def lp_ci95(self) -> float:
        """Half-width of the 95% CI on :attr:`avg_lp`.

        LP has a much wider spread than placement (a 72-point range against 7),
        so its interval is correspondingly wider. Quoting an LP difference
        without this invites reading noise as a result.
        """
        n = len(self.placements)
        if n < 2:
            return 0.0
        values = [LP_BY_PLACEMENT.get(p, 0) for p in self.placements]
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / (n - 1)
        return 1.96 * (variance**0.5) / (n**0.5)

    @property
    def avg_reward(self) -> float:
        return sum(self.rewards) / len(self.rewards) if self.rewards else 0.0

    @property
    def distribution(self) -> dict[int, int]:
        return dict(sorted(Counter(self.placements).items()))

    @property
    def ci95(self) -> float:
        """Half-width of the 95% CI on ``avg_placement``, i.e. 1.96*sd/sqrt(n).

        Any claimed effect smaller than this is not distinguishable from noise
        on an *unpaired* comparison. Comparing two policies on the same seeds
        is paired and considerably more sensitive -- see doc 99 entry 18.6.
        """
        n = len(self.placements)
        if n < 2:
            return 0.0
        mean = self.avg_placement
        variance = sum((p - mean) ** 2 for p in self.placements) / (n - 1)
        return 1.96 * (variance**0.5) / (n**0.5)

    @property
    def floor_rate(self) -> float:
        """Fraction of games finishing in last place.

        The floor-effect detector. A policy pinned at last place has almost no
        outcome variance, so no A/B built on it can resolve anything -- four
        consecutive experiments were wasted this way before it was noticed
        (doc 99 entry 18.3).
        """
        if not self.placements:
            return 0.0
        worst = max(self.placements)
        return self.placements.count(worst) / len(self.placements)

    @property
    def on_the_floor(self) -> bool:
        """Whether this result is too degenerate to compare against."""
        return self.floor_rate >= FLOOR_WARNING_THRESHOLD

    def summary(self) -> str:
        bars = " ".join(
            f"{place}:{self.distribution.get(place, 0)}" for place in range(1, 9)
        )
        text = (
            f"episodes={self.episodes}  avg_placement={self.avg_placement:.3f}"
            f" +/-{self.ci95:.3f}  "
            f"win_rate={self.win_rate:.1%}  top4={self.top4_rate:.1%}  "
            f"lp={self.avg_lp:+.2f} +/-{self.lp_ci95:.2f}  "
            f"avg_reward={self.avg_reward:.3f}\n  placements  {bars}"
        )
        if self.on_the_floor:
            text += (
                f"\n  !! FLOOR EFFECT: {self.floor_rate:.0%} of games finish last. "
                "This result has too little outcome variance to compare against "
                "-- raise --warm-start (see doc 99 entry 18.5)."
            )
        return text

    def as_dict(self) -> dict:
        return {
            "episodes": self.episodes,
            "avg_placement": round(self.avg_placement, 4),
            "ci95": round(self.ci95, 4),
            "win_rate": round(self.win_rate, 4),
            "top4_rate": round(self.top4_rate, 4),
            "avg_lp": round(self.avg_lp, 4),
            "lp_ci95": round(self.lp_ci95, 4),
            "avg_reward": round(self.avg_reward, 4),
            "distribution": self.distribution,
            "floor_rate": round(self.floor_rate, 4),
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
    """Does nothing every round. The absolute floor.

    It still takes augments, because TFT gives no way to decline one -- doing
    nothing is only a choice among the actions that are actually optional.
    """
    space = env.action_space_helper

    def act(obs: np.ndarray, mask: np.ndarray) -> int:
        if not mask[space.end_index]:
            # A forced pick is outstanding; take the first legal one.
            for offset in (space.offering_offset, space.augment_offset):
                legal = [i for i in range(offset, space.n) if mask[i]]
                if legal:
                    return legal[0]
        return space.end_index

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

        # -- a realm offering is on the table: draft before anything else ---
        #
        # Same ordering as the bots: a copy the board already owns beats a
        # pricier stranger, because it progresses a star-up.
        if player.has_pending_offering:
            owned = {u.champion.id for u in player.all_units}
            best, best_key = 0, None
            for index, offering in enumerate(player.realm_offer):
                if index >= space.realm_offerings:
                    break
                champion = player.data.champions[offering.champion_id]
                key = (offering.champion_id in owned, champion.cost)
                if best_key is None or key > best_key:
                    best, best_key = index, key
            if mask[space.offering_offset + best]:
                return space.offering_offset + best

        # -- an augment is on offer: it must be taken before anything else --
        #
        # Deliberately un-optimised: the first offer, always. Ranking augments
        # needs per-augment knowledge this heuristic does not have, and doc 03
        # sec 4 wants the scripted policy to be a *competent baseline*, not a
        # ceiling on every mechanic. Augment choice is therefore headroom a
        # learned policy can beat rather than a target it must match.
        if player.has_pending_augment:
            return space.augment_offset

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

        # -- items in the bag: put them on the carry ------------------------
        #
        # Concentrating items on the strongest fielded unit is the dominant
        # itemisation heuristic in TFT, and equipping goes through the action
        # space here so the behaviour is something a cloned policy can copy.
        if player.item_bag and player.board:
            cap = player.config.max_items_per_unit
            targets = [
                slot for slot in range(space.board_slots)
                if (unit := player.board.get(space.hex_for_slot(slot))) is not None
                and len(unit.items) < cap
            ]
            if targets:
                carry = max(
                    targets,
                    key=lambda s: _unit_strength(player.board[space.hex_for_slot(s)]),
                )
                action = space.equip_offset + 0 * space.unit_slots + carry
                if mask[action]:
                    return action

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
