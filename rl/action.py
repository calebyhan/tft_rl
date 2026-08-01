"""Action space definition and action -> engine-call mapping (doc 03 sec 3.2).

The planning phase is modelled as a short sub-episode: the agent takes up to
``max_actions_per_round`` discrete actions, each returning a fresh observation,
and ends early with ``END_PLANNING``. That avoids a combinatorial joint action
space and makes masking trivial (doc 03 sec 3.2).

The action space is a flat ``Discrete(n)`` laid out as contiguous blocks:

    [ BUY x shop_slots ]
    [ SELL x (board_hexes + bench_slots) ]
    [ MOVE x (board_hexes + bench_slots)^... ]  -- see below
    [ EQUIP x (item_bag_slots * unit_slots) ]
    [ REROLL ][ BUY_XP ][ END_PLANNING ]

``MOVE`` is the only combinatorially awkward one. A full from x to product over
37 slots would be ~1400 actions, so it is decomposed into a two-step
*select-then-place* interaction: ``SELECT(slot)`` marks a unit, and the next
``PLACE(slot)`` moves it there. That keeps the space at O(slots) rather than
O(slots^2) and mirrors how a human drags a unit.

Every action validates through ``PlayerState``, which raises
:class:`~engine.player.IllegalAction`; the mask exists so a well-behaved agent
never triggers one.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING

from engine.hexgrid import Hex
from engine.player import IllegalAction, PlayerState

if TYPE_CHECKING:
    from engine.shop import SharedPool


class ActionKind(IntEnum):
    BUY = 0
    SELL = 1
    SELECT = 2
    PLACE = 3
    EQUIP = 4
    REROLL = 5
    BUY_XP = 6
    END_PLANNING = 7


@dataclass(frozen=True)
class Action:
    """A decoded action: a kind plus up to two operands."""

    kind: ActionKind
    a: int = 0
    b: int = 0

    def __repr__(self) -> str:
        if self.kind in (ActionKind.REROLL, ActionKind.BUY_XP, ActionKind.END_PLANNING):
            return self.kind.name
        if self.kind is ActionKind.EQUIP:
            return f"{self.kind.name}(item={self.a}, unit={self.b})"
        return f"{self.kind.name}({self.a})"


class ActionSpace:
    """Flat discrete action space, built from the loaded config's dimensions.

    Slot indexing, used by SELL / SELECT / PLACE:

    * ``0 .. board_slots-1``            -- board hexes, in sorted own-frame order
    * ``board_slots .. board_slots+bench_size-1`` -- bench slots
    """

    def __init__(self, config, item_bag_slots: int = 10) -> None:
        self.shop_slots = config.shop_slots
        self.bench_size = config.bench_size
        self.board_slots = 0  # filled in by bind_board
        self.item_bag_slots = item_bag_slots
        self.config = config
        self._hexes: tuple[Hex, ...] = ()

    def bind_board(self, hexes: tuple[Hex, ...]) -> None:
        """Fix the board-hex ordering the slot indices refer to."""
        self._hexes = tuple(sorted(hexes))
        self.board_slots = len(self._hexes)
        self._build_offsets()

    def _build_offsets(self) -> None:
        self.unit_slots = self.board_slots + self.bench_size
        self.buy_offset = 0
        self.sell_offset = self.buy_offset + self.shop_slots
        self.select_offset = self.sell_offset + self.unit_slots
        self.place_offset = self.select_offset + self.unit_slots
        self.equip_offset = self.place_offset + self.unit_slots
        self.reroll_index = self.equip_offset + self.item_bag_slots * self.unit_slots
        self.buy_xp_index = self.reroll_index + 1
        self.end_index = self.buy_xp_index + 1
        self.n = self.end_index + 1

    # -- slot <-> location -------------------------------------------------

    def hex_for_slot(self, slot: int) -> Hex | None:
        if 0 <= slot < self.board_slots:
            return self._hexes[slot]
        return None

    def bench_index_for_slot(self, slot: int) -> int | None:
        if self.board_slots <= slot < self.unit_slots:
            return slot - self.board_slots
        return None

    def slot_for_hex(self, hex_: Hex) -> int:
        return self._hexes.index(hex_)

    def slot_for_bench(self, index: int) -> int:
        return self.board_slots + index

    # -- encode / decode --------------------------------------------------

    def decode(self, index: int) -> Action:
        if not 0 <= index < self.n:
            raise ValueError(f"action {index} out of range 0..{self.n - 1}")
        if index == self.end_index:
            return Action(ActionKind.END_PLANNING)
        if index == self.buy_xp_index:
            return Action(ActionKind.BUY_XP)
        if index == self.reroll_index:
            return Action(ActionKind.REROLL)
        if index >= self.equip_offset:
            offset = index - self.equip_offset
            return Action(ActionKind.EQUIP, offset // self.unit_slots, offset % self.unit_slots)
        if index >= self.place_offset:
            return Action(ActionKind.PLACE, index - self.place_offset)
        if index >= self.select_offset:
            return Action(ActionKind.SELECT, index - self.select_offset)
        if index >= self.sell_offset:
            return Action(ActionKind.SELL, index - self.sell_offset)
        return Action(ActionKind.BUY, index - self.buy_offset)

    def encode(self, action: Action) -> int:
        match action.kind:
            case ActionKind.BUY:
                return self.buy_offset + action.a
            case ActionKind.SELL:
                return self.sell_offset + action.a
            case ActionKind.SELECT:
                return self.select_offset + action.a
            case ActionKind.PLACE:
                return self.place_offset + action.a
            case ActionKind.EQUIP:
                return self.equip_offset + action.a * self.unit_slots + action.b
            case ActionKind.REROLL:
                return self.reroll_index
            case ActionKind.BUY_XP:
                return self.buy_xp_index
            case ActionKind.END_PLANNING:
                return self.end_index
        raise ValueError(f"unknown action kind {action.kind}")


class ActionExecutor:
    """Applies decoded actions to a :class:`PlayerState`, and builds the mask.

    Holds the one piece of interaction state the action space needs: which unit
    slot is currently *selected* for a move.
    """

    def __init__(self, space: ActionSpace) -> None:
        self.space = space
        self.selected: int | None = None

    def reset(self) -> None:
        self.selected = None

    def _validate_selection(self, player: PlayerState) -> None:
        """Drop a selection whose unit has gone.

        A selected unit can vanish without being explicitly sold -- buying its
        third copy combines it away -- which would otherwise leave ``selected``
        pointing at an empty slot.
        """
        if self.selected is not None and self.unit_at(player, self.selected) is None:
            self.selected = None

    # -- legality ---------------------------------------------------------

    def unit_at(self, player: PlayerState, slot: int):
        hex_ = self.space.hex_for_slot(slot)
        if hex_ is not None:
            return player.board.get(hex_)
        bench_index = self.space.bench_index_for_slot(slot)
        if bench_index is not None and bench_index < len(player.bench):
            return player.bench[bench_index]
        return None

    def legal_mask(self, player: PlayerState) -> list[bool]:
        """A boolean mask over the whole action space.

        Doc 03 sec 3.2: illegal actions are excluded rather than punished, so
        the agent never has to learn the rules of the interface.
        """
        space = self.space
        self._validate_selection(player)
        mask = [False] * space.n

        for slot in range(space.shop_slots):
            mask[space.buy_offset + slot] = player.can_buy(slot)

        for slot in range(space.unit_slots):
            occupied = self.unit_at(player, slot) is not None
            mask[space.sell_offset + slot] = occupied
            if self.selected is None:
                # Nothing picked up yet: any occupied slot can be selected.
                mask[space.select_offset + slot] = occupied
            else:
                mask[space.place_offset + slot] = self._can_place(player, slot)

        if player.item_bag:
            for item_index in range(min(len(player.item_bag), space.item_bag_slots)):
                for slot in range(space.unit_slots):
                    unit = self.unit_at(player, slot)
                    legal = unit is not None and len(unit.items) < player.config.max_items_per_unit
                    mask[space.equip_offset + item_index * space.unit_slots + slot] = legal

        mask[space.reroll_index] = player.gold >= player.config.reroll_cost
        mask[space.buy_xp_index] = player.can_buy_xp()
        mask[space.end_index] = True
        return mask

    def _can_place(self, player: PlayerState, slot: int) -> bool:
        """Whether the selected unit may move into ``slot``."""
        if self.selected is None or slot == self.selected:
            return False
        source_is_board = self.space.hex_for_slot(self.selected) is not None
        target_hex = self.space.hex_for_slot(slot)
        occupant = self.unit_at(player, slot)

        if target_hex is not None:
            # Fielding a new unit is capped by level; a swap keeps the count.
            if not source_is_board and occupant is None:
                return len(player.board) < player.max_board_units
            return True
        # Target is a bench slot. Only benching a fielded unit is modelled --
        # bench order carries no meaning in TFT, so bench-to-bench moves are
        # excluded rather than wasting an action on a no-op.
        return source_is_board and occupant is None

    # -- execution --------------------------------------------------------

    def apply(
        self, player: PlayerState, index: int, pool: "SharedPool", rng
    ) -> tuple[Action, bool]:
        """Run one action. Returns ``(action, planning_finished)``.

        Raises :class:`IllegalAction` for anything the mask would have blocked,
        so a mis-masked agent fails loudly rather than silently no-opping.
        """
        space = self.space
        self._validate_selection(player)
        action = space.decode(index)

        match action.kind:
            case ActionKind.END_PLANNING:
                self.selected = None
                return action, True
            case ActionKind.BUY:
                player.buy(action.a, pool)
            case ActionKind.SELL:
                unit = self.unit_at(player, action.a)
                if unit is None:
                    raise IllegalAction(f"slot {action.a} is empty")
                player.sell(unit, pool)
                if self.selected == action.a:
                    self.selected = None
            case ActionKind.SELECT:
                if self.unit_at(player, action.a) is None:
                    raise IllegalAction(f"slot {action.a} is empty")
                self.selected = action.a
            case ActionKind.PLACE:
                self._place(player, action.a)
            case ActionKind.EQUIP:
                self._equip(player, action.a, action.b)
            case ActionKind.REROLL:
                player.reroll(pool, rng)
            case ActionKind.BUY_XP:
                player.buy_xp()
        return action, False

    def _place(self, player: PlayerState, slot: int) -> None:
        if self.selected is None:
            raise IllegalAction("no unit is selected")
        source, self.selected = self.selected, None
        source_hex = self.space.hex_for_slot(source)
        target_hex = self.space.hex_for_slot(slot)

        if source_hex is not None and target_hex is not None:
            player.move_on_board(source_hex, target_hex)
        elif source_hex is not None:
            player.move_to_bench(source_hex, self.space.bench_index_for_slot(slot))
        elif target_hex is not None:
            player.move_to_board(self.space.bench_index_for_slot(source), target_hex)
        else:
            raise IllegalAction("bench-to-bench moves are not modelled")

    def _equip(self, player: PlayerState, item_index: int, slot: int) -> None:
        if item_index >= len(player.item_bag):
            raise IllegalAction(f"item bag has no slot {item_index}")
        unit = self.unit_at(player, slot)
        if unit is None:
            raise IllegalAction(f"slot {slot} is empty")
        player.equip_from_bag(player.item_bag[item_index].id, unit)
