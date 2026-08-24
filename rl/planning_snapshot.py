"""Forkable mutable planning state for counterfactual shop actions (doc 99 160.64)."""

from __future__ import annotations

import random
from dataclasses import dataclass

from engine.items import ItemRegistry
from engine.player import PlayerState
from engine.schema import GameData
from engine.shop import SharedPool
from engine.unit import UnitInstance


@dataclass(frozen=True)
class UnitSnapshot:
    champion_id: str
    star_level: int
    item_ids: tuple[str, ...]
    position: object | None


@dataclass(frozen=True)
class PlanningSnapshot:
    """All mutable state one planning primitive may read or mutate.

    Definitions in ``GameData`` are immutable and deliberately excluded.  The
    snapshot is not a combat or whole-match clone: it is the smallest state
    required to fork a shop decision safely.
    """

    player_id: int
    name: str
    gold: int
    level: int
    xp: int
    hp: int
    streak_count: int
    streak_type: str
    placement: int | None
    board: tuple[UnitSnapshot, ...]
    bench: tuple[UnitSnapshot | None, ...]
    item_ids: tuple[str, ...]
    augment_ids: tuple[str, ...]
    augment_offer_ids: tuple[str, ...]
    trait_progress: tuple[tuple[str, float], ...]
    free_rerolls: int
    realm_offer: tuple[object, ...]
    taken_offering: object | None
    realm_pick_was_sold: bool
    shop_slots: tuple[str | None, ...]
    pool_remaining: tuple[tuple[str, int], ...]
    rng_state: object

    @staticmethod
    def _unit(unit, position=None) -> UnitSnapshot:
        return UnitSnapshot(
            unit.champion.id,
            unit.star_level,
            tuple(item.id for item in unit.items),
            position,
        )

    @classmethod
    def capture(cls, player: PlayerState, pool: SharedPool, rng: random.Random) -> "PlanningSnapshot":
        """Capture mutable planning state without copying immutable definitions."""
        return cls(
            player_id=player.player_id,
            name=player.name,
            gold=player.gold,
            level=player.level,
            xp=player.xp,
            hp=player.hp,
            streak_count=player.streak_count,
            streak_type=player.streak_type,
            placement=player.placement,
            board=tuple(cls._unit(unit, hex_) for hex_, unit in sorted(player.board.items())),
            bench=tuple(cls._unit(unit) if unit is not None else None for unit in player.bench),
            item_ids=tuple(item.id for item in player.item_bag),
            augment_ids=tuple(augment.id for augment in player.augments),
            augment_offer_ids=tuple(augment.id for augment in player.augment_offer),
            trait_progress=tuple(sorted(player.trait_progress.items())),
            free_rerolls=player.free_rerolls,
            realm_offer=tuple(player.realm_offer),
            taken_offering=player.taken_offering,
            realm_pick_was_sold=player.realm_pick_was_sold,
            shop_slots=tuple(player.shop.slots),
            pool_remaining=tuple(sorted(pool.snapshot().items())),
            rng_state=rng.getstate(),
        )

    def restore(self, data: GameData, registry: ItemRegistry) -> tuple[PlayerState, SharedPool, random.Random]:
        """Construct independent mutable planning objects sharing only data."""
        player = PlayerState(data, registry, player_id=self.player_id, name=self.name)

        def unit_from(snapshot: UnitSnapshot) -> UnitInstance:
            return UnitInstance(
                data.champions[snapshot.champion_id],
                snapshot.star_level,
                [data.items[item_id] for item_id in snapshot.item_ids],
                registry=registry,
            )

        player.gold = self.gold
        player.level = self.level
        player.xp = self.xp
        player.hp = self.hp
        player.streak_count = self.streak_count
        player.streak_type = self.streak_type
        player.placement = self.placement
        player.board = {snapshot.position: unit_from(snapshot) for snapshot in self.board}
        player.bench = [unit_from(unit) if unit is not None else None for unit in self.bench]
        player.item_bag = [data.items[item_id] for item_id in self.item_ids]
        player.augments = [data.augments[augment_id] for augment_id in self.augment_ids]
        player.augment_offer = tuple(data.augments[augment_id] for augment_id in self.augment_offer_ids)
        player.trait_progress = dict(self.trait_progress)
        player.free_rerolls = self.free_rerolls
        player.realm_offer = self.realm_offer
        player.taken_offering = self.taken_offering
        player.realm_pick_was_sold = self.realm_pick_was_sold
        player.shop.slots = list(self.shop_slots)

        pool = SharedPool(data)
        pool._remaining = dict(self.pool_remaining)
        rng = random.Random()
        rng.setstate(self.rng_state)
        return player, pool, rng
