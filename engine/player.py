"""``PlayerState``: one seat's board, bench, gold, HP and items (doc 03 sec 2.10).

The methods here are the planning-phase primitives from doc 03 sec 3.2 -- buy,
sell, move, equip, reroll, buy XP. They are the *same* primitives the RL action
space calls and that a human-facing UI would call, so each one validates its
inputs and **raises** :class:`IllegalAction` rather than silently ignoring a bad
request. That lets the RL wrapper mask illegal actions cleanly instead of
learning from no-ops.

Board coordinates are :class:`~engine.hexgrid.Hex` keys in the player's own
frame (the team-0 half-board). :meth:`PlayerState.deploy_for_combat` mirrors
them onto whichever side the player occupies in a given fight.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Iterator, Sequence

from engine import economy
from engine.economy import RoundId, StreakType
from engine.hexgrid import Board, Hex, axial_to_offset
from engine.items import ItemError, ItemRegistry
from engine.schema import GameData, ItemDef
from engine.shop import SharedPool, Shop
from engine.unit import UnitInstance

MAX_STAR_LEVEL = 3
COPIES_TO_UPGRADE = 3


class IllegalAction(ValueError):
    """Raised when a requested planning-phase action is not legal."""


@dataclass
class PlayerState:
    """Everything one player owns."""

    data: GameData
    registry: ItemRegistry
    player_id: int = 0
    name: str = ""

    gold: int = 0
    level: int = 1
    xp: int = 0
    hp: int = 100
    streak_count: int = 0
    streak_type: StreakType = "none"
    placement: int | None = None

    board: dict[Hex, UnitInstance] = field(default_factory=dict)
    bench: list[UnitInstance | None] = field(default_factory=list)
    item_bag: list[ItemDef] = field(default_factory=list)
    shop: Shop = field(init=False)
    hex_board: Board = field(default_factory=Board)

    def __post_init__(self) -> None:
        config = self.data.config
        self.shop = Shop(config)
        if not self.bench:
            self.bench = [None] * config.bench_size
        if self.gold == 0:
            self.gold = config.starting_gold
        if self.hp == 100:
            self.hp = config.starting_hp
        self.name = self.name or f"P{self.player_id}"
        self._own_hexes = frozenset(self.hex_board.half_board_hexes(0))

    # -- derived views ----------------------------------------------------

    @property
    def config(self):
        return self.data.config

    @property
    def alive(self) -> bool:
        return self.hp > 0

    @property
    def max_board_units(self) -> int:
        """Units fieldable at the current level (doc 01 sec 4)."""
        return self.config.board_size_for_level(self.level)

    @property
    def board_units(self) -> list[UnitInstance]:
        """Fielded units, ordered by position for deterministic iteration."""
        return [self.board[h] for h in sorted(self.board)]

    @property
    def bench_units(self) -> list[UnitInstance]:
        return [u for u in self.bench if u is not None]

    @property
    def all_units(self) -> list[UnitInstance]:
        return self.board_units + self.bench_units

    @property
    def free_bench_slots(self) -> list[int]:
        return [i for i, slot in enumerate(self.bench) if slot is None]

    @property
    def free_board_hexes(self) -> list[Hex]:
        return sorted(h for h in self._own_hexes if h not in self.board)

    def __iter__(self) -> Iterator[UnitInstance]:
        return iter(self.all_units)

    # -- buying -----------------------------------------------------------

    def cost_of_slot(self, slot: int) -> int:
        champion_id = self.shop.peek(slot)
        if champion_id is None:
            raise IllegalAction(f"shop slot {slot} is empty")
        return self.data.champions[champion_id].cost

    def can_buy(self, slot: int) -> bool:
        try:
            self._check_buy(slot)
        except IllegalAction:
            return False
        return True

    def _check_buy(self, slot: int) -> str:
        champion_id = self.shop.peek(slot)
        if champion_id is None:
            raise IllegalAction(f"shop slot {slot} is empty")
        cost = self.data.champions[champion_id].cost
        if self.gold < cost:
            raise IllegalAction(
                f"{self.name} has {self.gold} gold, needs {cost} for "
                f"{self.data.champions[champion_id].display_name}"
            )
        # Purchases go to the bench, never straight to the board. A full bench
        # is only a blocker if the copy will not immediately combine away.
        if not self.free_bench_slots and not self._would_upgrade(champion_id):
            raise IllegalAction(f"{self.name}'s bench is full")
        return champion_id

    def buy(self, slot: int, pool: SharedPool | None = None) -> UnitInstance:
        """Buy the champion in ``slot``, auto-combining copies where possible.

        Nothing is mutated until the purchase is known to succeed: a rejected
        buy leaves gold, the shop slot and the shared pool untouched.
        """
        champion_id = self._check_buy(slot)
        champion = self.data.champions[champion_id]
        unit = UnitInstance(champion, 1, registry=self.registry)

        free = self.free_bench_slots
        if free:
            self.bench[free[0]] = unit
        else:
            # _check_buy guarantees this copy combines away immediately, so it
            # only needs a temporary home; _trim_bench_overflow clears it.
            self.bench.append(unit)

        self.shop.take_slot(slot)
        self.gold -= champion.cost
        self._resolve_upgrades(champion_id, pool)
        self._trim_bench_overflow()
        # A combine may have consumed the copy just bought. When it did, hand
        # back the upgraded survivor; otherwise hand back the new unit itself,
        # so the caller can always act on the unit it just paid for.
        owned = self.all_units
        if unit in owned:
            return unit
        return self._highest_star(champion_id) or unit

    def _highest_star(self, champion_id: str) -> UnitInstance | None:
        candidates = [u for u in self.all_units if u.champion.id == champion_id]
        if not candidates:
            return None
        return max(candidates, key=lambda u: u.star_level)

    def _trim_bench_overflow(self) -> None:
        """Collapse the temporary overflow slot used by an immediate combine."""
        size = self.config.bench_size
        if len(self.bench) <= size:
            return
        stranded = [u for u in self.bench[size:] if u is not None]
        del self.bench[size:]
        for unit in stranded:
            free = self.free_bench_slots
            if not free:
                raise IllegalAction(
                    f"{self.name}'s bench overflowed and {unit.name} has nowhere "
                    "to go -- this indicates a combine bookkeeping bug"
                )
            self.bench[free[0]] = unit

    # -- combining --------------------------------------------------------

    def _units_of(self, champion_id: str, star_level: int) -> list[UnitInstance]:
        return [
            u
            for u in self.all_units
            if u.champion.id == champion_id and u.star_level == star_level
        ]

    def _would_upgrade(self, champion_id: str) -> bool:
        """Whether buying one more copy immediately triggers a combine."""
        return len(self._units_of(champion_id, 1)) >= COPIES_TO_UPGRADE - 1

    def _resolve_upgrades(self, champion_id: str, pool: SharedPool | None) -> None:
        """Combine 3-of-a-kind upward, cascading into higher star levels.

        The surviving unit keeps every item the consumed copies held, up to the
        slot cap; anything over the cap goes back to the item bag.
        """
        for star in range(1, MAX_STAR_LEVEL):
            while len(self._units_of(champion_id, star)) >= COPIES_TO_UPGRADE:
                group = self._units_of(champion_id, star)[:COPIES_TO_UPGRADE]
                self._combine(group, pool)

    def _combine(self, group: Sequence[UnitInstance], pool: SharedPool | None) -> None:
        # Keep whichever copy is already fielded, so a combine does not knock a
        # unit off the board.
        fielded = [u for u in group if self._hex_of(u) is not None]
        keeper = fielded[0] if fielded else group[0]
        consumed = [u for u in group if u is not keeper]

        salvaged: list[ItemDef] = []
        for unit in consumed:
            salvaged.extend(unit.items)
            self._remove_unit(unit, pool=None)  # copies fold in, not back to pool

        keeper.star_level = keeper.star_level + 1
        for item in salvaged:
            try:
                keeper.equip(item)
            except ItemError:
                self.item_bag.append(item)

    # -- selling ----------------------------------------------------------

    def sell(self, unit: UnitInstance, pool: SharedPool | None = None) -> int:
        """Sell a unit, returning its copies to the pool and its items to the bag."""
        if unit not in self.all_units:
            raise IllegalAction(f"{self.name} does not own {unit.name}")
        refund = unit.sell_value()
        self.item_bag.extend(unit.items)
        self._remove_unit(unit, pool)
        self.gold += refund
        return refund

    def sell_bench_slot(self, index: int, pool: SharedPool | None = None) -> int:
        if not 0 <= index < len(self.bench):
            raise IllegalAction(f"bench slot {index} is out of range")
        unit = self.bench[index]
        if unit is None:
            raise IllegalAction(f"bench slot {index} is empty")
        return self.sell(unit, pool)

    def sell_board_hex(self, hex_: Hex, pool: SharedPool | None = None) -> int:
        unit = self.board.get(hex_)
        if unit is None:
            raise IllegalAction(f"no unit on {hex_}")
        return self.sell(unit, pool)

    def _remove_unit(self, unit: UnitInstance, pool: SharedPool | None) -> None:
        hex_ = self._hex_of(unit)
        if hex_ is not None:
            del self.board[hex_]
        else:
            for i, benched in enumerate(self.bench):
                if benched is unit:
                    self.bench[i] = None
                    break
            else:
                raise IllegalAction(f"{unit.name} is not on this player's board or bench")
        if pool is not None:
            pool.return_to_pool(unit.champion.id, unit.pool_copies)

    def _hex_of(self, unit: UnitInstance) -> Hex | None:
        for hex_, placed in self.board.items():
            if placed is unit:
                return hex_
        return None

    # -- moving -----------------------------------------------------------

    def move_to_board(self, bench_index: int, hex_: Hex) -> None:
        """Field a benched unit, swapping if the destination is occupied."""
        if not 0 <= bench_index < len(self.bench):
            raise IllegalAction(f"bench slot {bench_index} is out of range")
        unit = self.bench[bench_index]
        if unit is None:
            raise IllegalAction(f"bench slot {bench_index} is empty")
        self._check_own_hex(hex_)
        occupant = self.board.get(hex_)
        if occupant is None and len(self.board) >= self.max_board_units:
            raise IllegalAction(
                f"{self.name} can field {self.max_board_units} units at level "
                f"{self.level} and already has {len(self.board)}"
            )
        self.board[hex_] = unit
        self.bench[bench_index] = occupant

    def move_to_bench(self, hex_: Hex, bench_index: int | None = None) -> None:
        """Return a fielded unit to the bench."""
        unit = self.board.get(hex_)
        if unit is None:
            raise IllegalAction(f"no unit on {hex_}")
        if bench_index is None:
            free = self.free_bench_slots
            if not free:
                raise IllegalAction(f"{self.name}'s bench is full")
            bench_index = free[0]
        elif not 0 <= bench_index < len(self.bench):
            raise IllegalAction(f"bench slot {bench_index} is out of range")
        elif self.bench[bench_index] is not None:
            raise IllegalAction(f"bench slot {bench_index} is occupied")
        self.bench[bench_index] = unit
        del self.board[hex_]

    def move_on_board(self, source: Hex, destination: Hex) -> None:
        """Move a fielded unit, swapping with any occupant of the destination."""
        unit = self.board.get(source)
        if unit is None:
            raise IllegalAction(f"no unit on {source}")
        self._check_own_hex(destination)
        occupant = self.board.get(destination)
        self.board[destination] = unit
        if occupant is not None:
            self.board[source] = occupant
        else:
            del self.board[source]

    def _check_own_hex(self, hex_: Hex) -> None:
        if hex_ not in self._own_hexes:
            raise IllegalAction(
                f"{hex_} is not on {self.name}'s half-board "
                f"(rows {self.hex_board.half_rows}-{self.hex_board.rows - 1})"
            )

    # -- items ------------------------------------------------------------

    def equip_from_bag(self, item_id: str, unit: UnitInstance) -> ItemDef:
        """Attach a bagged item to a unit, combining components automatically.

        Dropping a component onto a unit already holding a component combines
        the two into the completed item, exactly as in TFT.
        """
        if unit not in self.all_units:
            raise IllegalAction(f"{self.name} does not own {unit.name}")
        item = self._take_from_bag(item_id)

        if item.is_component:
            for held in unit.items:
                if not held.is_component:
                    continue
                combined_id = self.registry.combine(held.id, item.id)
                if combined_id is None:
                    continue
                combined = self.registry.get(combined_id)
                try:
                    unit.unequip(held.id)
                    unit.equip(combined)
                except ItemError as exc:
                    unit.equip(held)
                    self.item_bag.append(item)
                    raise IllegalAction(str(exc)) from exc
                return combined

        try:
            unit.equip(item)
        except ItemError as exc:
            self.item_bag.append(item)
            raise IllegalAction(str(exc)) from exc
        return item

    def _take_from_bag(self, item_id: str) -> ItemDef:
        for i, item in enumerate(self.item_bag):
            if item.id == item_id:
                return self.item_bag.pop(i)
        raise IllegalAction(f"{self.name} has no {item_id!r} in the item bag")

    def add_item(self, item_id: str) -> None:
        self.item_bag.append(self.registry.get(item_id))

    # -- shop and XP ------------------------------------------------------

    def roll_shop(self, pool: SharedPool, rng: random.Random) -> list[str | None]:
        """Refresh the shop for free (start of a planning phase)."""
        return self.shop.roll(self.level, pool, rng)

    def reroll(self, pool: SharedPool, rng: random.Random) -> list[str | None]:
        """Pay to refresh the shop (doc 01 sec 5)."""
        cost = self.config.reroll_cost
        if self.gold < cost:
            raise IllegalAction(
                f"{self.name} has {self.gold} gold, a reroll costs {cost}"
            )
        self.gold -= cost
        return self.shop.roll(self.level, pool, rng)

    def can_buy_xp(self) -> bool:
        gold_cost, _ = economy.xp_purchase(self.config)
        return self.gold >= gold_cost and self.level < self.config.max_level

    def buy_xp(self) -> int:
        """Buy one XP increment (4 gold for 4 XP). Returns the new level."""
        gold_cost, xp_gain = economy.xp_purchase(self.config)
        if self.level >= self.config.max_level:
            raise IllegalAction(f"{self.name} is already max level")
        if self.gold < gold_cost:
            raise IllegalAction(
                f"{self.name} has {self.gold} gold, buying XP costs {gold_cost}"
            )
        self.gold -= gold_cost
        self.grant_xp(xp_gain)
        return self.level

    def grant_xp(self, amount: int) -> int:
        self.level, self.xp = economy.apply_xp(self.config, self.level, self.xp, amount)
        return self.level

    # -- round transitions ------------------------------------------------

    def award_income(self, round_id: RoundId, won_pvp: bool = False) -> economy.IncomeBreakdown:
        """Pay end-of-round gold and the passive XP trickle (doc 01 sec 4)."""
        breakdown = economy.round_income(
            self.config,
            round_id,
            self.gold,
            self.streak_count,
            self.streak_type,
            won_pvp,
        )
        self.gold += breakdown.total
        self.grant_xp(economy.passive_xp_per_round(self.config))
        return breakdown

    def record_result(self, won: bool) -> None:
        """Update the win/loss streak after a PvP round."""
        streak_type: StreakType = "win" if won else "loss"
        if self.streak_type == streak_type:
            self.streak_count += 1
        else:
            self.streak_type = streak_type
            self.streak_count = 1

    def take_damage(self, amount: int) -> int:
        """Apply HP loss, returning the amount actually lost."""
        if amount < 0:
            raise ValueError(f"damage must be >= 0, got {amount}")
        lost = min(amount, self.hp)
        self.hp -= lost
        return lost

    def release_all_to_pool(self, pool: SharedPool) -> None:
        """Return every owned unit to the shared pool (on elimination, doc 01 sec 7)."""
        for unit in self.all_units:
            pool.return_to_pool(unit.champion.id, unit.pool_copies)
        self.board.clear()
        self.bench = [None] * self.config.bench_size
        self.shop.discard(pool)

    # -- combat handoff ---------------------------------------------------

    def deploy_for_combat(self, team: int, board: Board | None = None) -> list[UnitInstance]:
        """Position this player's fielded units on ``team``'s side of a fight.

        The player's own-frame hexes are converted back to ``(row, col)`` slots
        and re-projected onto whichever half of the battlefield they occupy.
        """
        board = board or self.hex_board
        deployed: list[UnitInstance] = []
        for own_hex in sorted(self.board):
            unit = self.board[own_hex]
            row, col = axial_to_offset(own_hex)
            unit.position = board.to_combat(team, row - board.half_rows, col)
            unit.team = team
            deployed.append(unit)
        return deployed

    def __repr__(self) -> str:
        return (
            f"<{self.name} hp={self.hp} gold={self.gold} lvl={self.level} "
            f"board={len(self.board)}/{self.max_board_units} "
            f"streak={self.streak_type}:{self.streak_count}>"
        )
