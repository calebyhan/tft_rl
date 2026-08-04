"""Gold income, interest, streaks, XP and levelling (doc 01 sec 4, doc 03 sec 2.7).

Everything here is a pure function of a :class:`~engine.schema.GameConfig` plus
some player state -- no mutation, no randomness -- so the numbers can be tested
directly against doc 01 sec 4's tables. Every constant comes from
``data/config.json``; nothing is baked into this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from engine.schema import GameConfig

StreakType = Literal["win", "loss", "none"]


@dataclass(frozen=True, order=True)
class RoundId:
    """A stage/round pair such as ``2-1``."""

    stage: int
    round: int

    def __post_init__(self) -> None:
        if self.stage < 1 or self.round < 1:
            raise ValueError(f"invalid round id {self.stage}-{self.round}")

    @classmethod
    def parse(cls, text: str) -> "RoundId":
        try:
            stage, round_ = text.split("-")
            return cls(int(stage), int(round_))
        except (ValueError, AttributeError):
            raise ValueError(f"malformed round id {text!r}, expected 'stage-round'") from None

    def next(self, rounds_per_stage: int) -> "RoundId":
        if self.round >= rounds_per_stage:
            return RoundId(self.stage + 1, 1)
        return RoundId(self.stage, self.round + 1)

    def __str__(self) -> str:
        return f"{self.stage}-{self.round}"


@dataclass(frozen=True)
class IncomeBreakdown:
    """Where a round's gold came from -- useful for debugging and for the RL log."""

    base: int
    interest: int
    streak: int
    win_bonus: int

    @property
    def total(self) -> int:
        return self.base + self.interest + self.streak + self.win_bonus


def base_income(config: GameConfig, round_id: RoundId) -> int:
    """Base gold for a round.

    Stage 1 and 2-1 follow the ramp in ``config.income_ramp``; every later
    round pays ``config.base_income`` (doc 01 sec 4).
    """
    return config.income_ramp.get(str(round_id), config.base_income)


def interest(config: GameConfig, gold: int) -> int:
    """+1 gold per ``interest_per_gold`` held, capped (doc 01 sec 4)."""
    if gold <= 0:
        return 0
    return min(gold // config.interest_per_gold, config.interest_cap)


def streak_bonus(config: GameConfig, streak_count: int, streak_type: StreakType) -> int:
    """Streak gold. Win and loss streaks pay identically (doc 01 sec 4)."""
    if streak_type == "none" or streak_count <= 0:
        return 0
    bonus = 0
    for threshold, amount in config.streak_bonus:
        if streak_count >= threshold:
            bonus = amount
    return bonus


def round_income(
    config: GameConfig,
    round_id: RoundId,
    gold: int,
    streak_count: int = 0,
    streak_type: StreakType = "none",
    won_pvp: bool = False,
) -> IncomeBreakdown:
    """Total end-of-round income.

    Interest is computed on the gold held *before* income is added
    (doc 01 sec 4). The PvP win bonus is separate from the streak bonus and
    stacks with it.
    """
    return IncomeBreakdown(
        base=base_income(config, round_id),
        interest=interest(config, gold),
        streak=streak_bonus(config, streak_count, streak_type),
        win_bonus=config.pvp_win_gold if won_pvp else 0,
    )


# --- XP and levelling ----------------------------------------------------


def passive_xp_per_round(config: GameConfig) -> int:
    return config.passive_xp_per_round


def xp_purchase(config: GameConfig) -> tuple[int, int]:
    """The fixed ``(gold cost, xp gained)`` exchange for one XP buy."""
    return config.xp_purchase_gold, config.xp_purchase_amount


def xp_cost_to_buy(config: GameConfig, amount: int) -> int:
    """Gold needed to buy ``amount`` XP, in whole purchase increments."""
    gold_per, xp_per = xp_purchase(config)
    if amount <= 0:
        return 0
    purchases = -(-amount // xp_per)  # ceiling division
    return purchases * gold_per


def xp_to_next_level(config: GameConfig, level: int) -> int | None:
    """XP needed to advance from ``level``, or ``None`` at max level."""
    if level >= config.max_level:
        return None
    try:
        return config.xp_to_next_level[level]
    except KeyError:
        raise KeyError(
            f"no xp_to_next_level entry for level {level} "
            f"(configured levels: {sorted(config.xp_to_next_level)})"
        ) from None


def apply_xp(config: GameConfig, level: int, xp: int, gained: int) -> tuple[int, int]:
    """Add XP and resolve any level-ups. Returns ``(level, leftover xp)``.

    XP is spent as each threshold is crossed, so a single large grant can pass
    several levels. At max level XP stops accumulating.
    """
    if gained < 0:
        raise ValueError(f"cannot gain negative xp: {gained}")
    level, xp = level, xp + gained
    while level < config.max_level:
        needed = config.xp_to_next_level.get(level)
        if needed is None or xp < needed:
            break
        xp -= needed
        level += 1
    if level >= config.max_level:
        xp = 0
    return level, xp


# --- selling -------------------------------------------------------------


def sell_value(champion_cost: int, star_level: int) -> int:
    """Gold refunded for selling a unit (doc 01 sec 4).

    The unit's combine cost is its champion cost times the 1-star copies it
    represents (1 / 3 / 9). Everything except a 1-star 1-cost loses 1 gold,
    floored at the champion's cost.
    """
    if champion_cost < 1:
        raise ValueError(f"champion_cost must be >= 1, got {champion_cost}")
    if not 1 <= star_level <= 3:
        raise ValueError(f"star_level must be 1..3, got {star_level}")
    combine_cost = champion_cost * 3 ** (star_level - 1)
    if star_level == 1 and champion_cost == 1:
        return combine_cost
    return max(combine_cost - 1, champion_cost)


# --- round damage (doc 01 sec 7) -----------------------------------------


def round_damage(
    config: GameConfig, round_id: RoundId, survivors: list[tuple[int, int]]
) -> int:
    """Damage the loser takes: a stage base plus **one per surviving unit**.

    ``survivors`` is ``(champion_cost, star_level)`` per surviving enemy unit.
    Neither field affects the damage: a 3-star 5-cost costs the loser exactly
    as much as a 1-star 1-cost. They are still taken as the argument shape so
    callers do not change, and because it makes the rule explicit at a glance.

    This was previously ``cost x star_multiplier``, following doc 01 sec 7,
    which is simply wrong -- the LoL wiki states "base damage for the stage
    plus 1 damage per surviving enemy champion". The old rule inflated damage
    roughly fourfold and truncated games by ~7 rounds, cutting off the entire
    phase in which composition pays off (doc 99 entry 36.4).
    """
    stages = sorted(config.stage_base_damage)
    capped_stage = min(round_id.stage, stages[-1]) if stages else 0
    base = config.stage_base_damage.get(capped_stage, 0)
    per_unit = len(survivors) * config.damage_per_surviving_unit
    return max(base + per_unit, config.minimum_round_damage)
