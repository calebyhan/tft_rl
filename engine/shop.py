"""The shared champion pool and per-player shop rolls (doc 01 sec 5, doc 03 sec 2.8).

One :class:`SharedPool` is owned by the whole lobby: copies are removed when
bought and returned when a unit is sold or its owner is eliminated
(doc 01 sec 7). Shop odds and pool sizes both come from ``config.json``, so a
future set's different tables are a data change rather than a code change.

All randomness is drawn from a caller-supplied ``random.Random`` so rolls are
reproducible under a fixed seed, exactly like combat.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from engine.schema import ChampionDef, GameConfig, GameData


class ShopError(ValueError):
    """Raised on an illegal pool or shop operation."""


class SharedPool:
    """Remaining copies of every champion, shared across all 8 players."""

    def __init__(self, data: GameData) -> None:
        self.data = data
        self.config = data.config
        self._remaining: dict[str, int] = {
            champ.id: data.config.pool_sizes[champ.cost]
            for champ in data.champions.values()
        }
        self._by_cost: dict[int, tuple[str, ...]] = {}
        for champ in data.champions.values():
            self._by_cost.setdefault(champ.cost, ())
        for cost in self._by_cost:
            self._by_cost[cost] = tuple(
                sorted(c.id for c in data.champions.values() if c.cost == cost)
            )

    # -- inspection -------------------------------------------------------

    def remaining(self, champion_id: str) -> int:
        try:
            return self._remaining[champion_id]
        except KeyError:
            raise ShopError(f"unknown champion id {champion_id!r}") from None

    def available_in_tier(self, cost: int) -> list[str]:
        """Champion ids of ``cost`` that still have at least one copy left."""
        return [cid for cid in self._by_cost.get(cost, ()) if self._remaining[cid] > 0]

    def copies_in_tier(self, cost: int) -> int:
        return sum(self._remaining[cid] for cid in self._by_cost.get(cost, ()))

    @property
    def total_remaining(self) -> int:
        return sum(self._remaining.values())

    def snapshot(self) -> dict[str, int]:
        return dict(self._remaining)

    # -- mutation ---------------------------------------------------------

    def take(self, champion_id: str, count: int = 1) -> None:
        """Remove copies from the pool (a purchase)."""
        remaining = self.remaining(champion_id)
        if count > remaining:
            raise ShopError(
                f"cannot take {count} copies of {champion_id!r}; only {remaining} left"
            )
        self._remaining[champion_id] -= count

    def return_to_pool(self, champion_id: str, count: int = 1) -> None:
        """Return copies (a sale, or an eliminated player's board and bench)."""
        if count < 0:
            raise ShopError(f"cannot return a negative count: {count}")
        cap = self.config.pool_sizes[self.data.champions[champion_id].cost]
        current = self.remaining(champion_id)
        if current + count > cap:
            raise ShopError(
                f"returning {count} copies of {champion_id!r} would exceed the "
                f"pool size of {cap} (currently {current})"
            )
        self._remaining[champion_id] += count

    # -- drawing ----------------------------------------------------------

    def draw(self, cost: int, rng: random.Random) -> str | None:
        """Draw one champion of ``cost``, removing it from the pool.

        Returns ``None`` when the tier is exhausted -- a real possibility late
        in a game where a tier has been bought out, and the caller's cue to
        leave the shop slot empty.
        """
        available = self.available_in_tier(cost)
        if not available:
            return None
        if self.config.shop_draw_weighting == "by_copies":
            weights = [self._remaining[cid] for cid in available]
            champion_id = rng.choices(available, weights=weights, k=1)[0]
        else:
            champion_id = rng.choice(available)
        self.take(champion_id)
        return champion_id


# --- rolling -------------------------------------------------------------


def roll_cost_tier(config: GameConfig, level: int, rng: random.Random) -> int:
    """Roll one slot's cost tier from the level's odds row (doc 01 sec 5)."""
    odds = config.shop_odds_for_level(level)
    tiers = sorted(config.pool_sizes)
    if len(odds) != len(tiers):
        raise ShopError(
            f"shop odds row for level {level} has {len(odds)} entries but "
            f"there are {len(tiers)} cost tiers"
        )
    roll = rng.random()
    cumulative = 0.0
    for tier, probability in zip(tiers, odds, strict=True):
        cumulative += probability
        if roll < cumulative:
            return tier
    # Only reachable through floating-point drift at the very top of the range.
    return tiers[-1]


def roll_shop(
    config: GameConfig, level: int, pool: SharedPool, rng: random.Random
) -> list[str | None]:
    """Roll a full shop: each slot picks its tier independently, then a champion.

    A slot whose rolled tier is exhausted comes back empty (``None``) rather
    than silently falling back to another tier.
    """
    slots: list[str | None] = []
    for _ in range(config.shop_slots):
        tier = roll_cost_tier(config, level, rng)
        slots.append(pool.draw(tier, rng))
    return slots


# --- per-player shop state -----------------------------------------------


@dataclass
class Shop:
    """One player's 5 visible slots.

    Slots are consumed on purchase and refilled only by a reroll or the
    automatic roll at the start of a planning phase, matching TFT.
    """

    config: GameConfig
    slots: list[str | None] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.slots:
            self.slots = [None] * self.config.shop_slots

    def roll(self, level: int, pool: SharedPool, rng: random.Random) -> list[str | None]:
        """Discard the current slots back to the pool and roll a fresh shop."""
        self.discard(pool)
        self.slots = roll_shop(self.config, level, pool, rng)
        return list(self.slots)

    def discard(self, pool: SharedPool) -> None:
        """Return every unbought slot to the shared pool."""
        for i, champion_id in enumerate(self.slots):
            if champion_id is not None:
                pool.return_to_pool(champion_id)
                self.slots[i] = None

    def take_slot(self, index: int) -> str:
        """Claim the champion in ``index``, emptying the slot."""
        if not 0 <= index < len(self.slots):
            raise ShopError(
                f"shop slot {index} is out of range 0..{len(self.slots) - 1}"
            )
        champion_id = self.slots[index]
        if champion_id is None:
            raise ShopError(f"shop slot {index} is empty")
        self.slots[index] = None
        return champion_id

    def peek(self, index: int) -> str | None:
        if not 0 <= index < len(self.slots):
            raise ShopError(
                f"shop slot {index} is out of range 0..{len(self.slots) - 1}"
            )
        return self.slots[index]

    def __len__(self) -> int:
        return len(self.slots)


def expected_tier_distribution(config: GameConfig, level: int) -> Mapping[int, float]:
    """The odds row as a ``{cost: probability}`` map. For tests and reporting."""
    tiers = sorted(config.pool_sizes)
    return dict(zip(tiers, config.shop_odds_for_level(level), strict=True))


def champions_of_cost(
    champions: Iterable[ChampionDef], cost: int
) -> tuple[ChampionDef, ...]:
    return tuple(c for c in champions if c.cost == cost)
