"""Faithful action-space scheduler for :class:`rl.opponents.GreedyPolicy`.

The direct teacher mutates a ``PlayerState`` through a fixed sequence of
primitives.  This adapter emits that same sequence one action at a time, but
never simulates or mutates the live player ahead of :class:`ActionExecutor`.
It is intentionally a scheduler, not a second heuristic: the conformance test
in doc 99 entry 154 is its contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Sequence

import numpy as np

from engine.traits import trait_counts
from rl.action import Action, ActionKind
from rl.opponents import EconStrategy, GreedyPolicy, _preferred_hex, _strength

if TYPE_CHECKING:
    from rl.env import TFTEnv


class GreedyActionPolicy:
    """Emit a ``GreedyPolicy`` planning phase through the discrete action space.

    A buy phase captures its ranked shop candidates once, just as
    ``GreedyPolicy._buy_phase`` does.  Re-ranking after each purchase looks
    natural in an action loop but is a materially different policy (doc 99
    entry 153).  Other decisions are evaluated precisely at the point the
    direct policy would make them, after preceding actions have reached the
    live player.
    """

    def __init__(
        self,
        env: "TFTEnv",
        *,
        level_at_gold: int = 30,
        reroll_at_gold: int = 45,
        keep_interest: bool = True,
        econ: EconStrategy | None = None,
        roll_buys: str = "all",
        off_policy: bool = False,
        item_planner: Callable[[], Sequence[tuple[str, object]]] | None = None,
        board_planner: Callable[[], Sequence[tuple[object, object]]] | None = None,
        board_planner_first: bool = True,
    ) -> None:
        self.env = env
        self.off_policy = off_policy
        self.greedy = GreedyPolicy(
            seed=0,
            level_at_gold=level_at_gold,
            reroll_at_gold=reroll_at_gold,
            keep_interest=keep_interest,
            econ=econ,
            roll_buys=roll_buys,
        )
        self.econ = econ
        self._round: str | None = None
        self._stage = ""
        self._buy_candidates: list[tuple[int, int]] | None = None
        self._buy_after = ""
        self._pending_place: int | None = None
        self._item_planner = item_planner
        self._item_actions: list[tuple[str, object]] | None = None
        self._board_planner = board_planner
        self._board_actions: list[tuple[object, object]] | None = None
        # Where an injected board search sits relative to the item phase. TFT
        # items cannot be moved once equipped, so a swap that fires after the
        # equip stage strands them on a unit that leaves the board -- the
        # ordering defect entry 160.108 corrected for item search itself. Both
        # orders are expressible so the ordering can be measured rather than
        # assumed (doc 99 entry 160.139).
        self._stage_after_field, self._stage_after_board, self._stage_after_equip = (
            ("board", "equip", "done") if board_planner_first
            else ("equip", "done", "board")
        )
        self._rolls = 0

    def __call__(self, _obs: np.ndarray, mask: np.ndarray) -> int:
        """Return the next direct-teacher primitive encoded as an action."""
        player = self.env.player
        assert self.env.match is not None
        self._reset_if_new_round()
        space = self.env.action_space_helper

        # Carousel picks resolve before planning in Match, so they must happen
        # before the scheduler can touch the shop. Augments are deliberately
        # different: Match offers one before planning but resolves it *after*
        # the policy has finished. Keeping it pending lets buy/search decisions
        # see the same pre-augment state as their direct counterpart.
        if player.has_pending_offering:
            choice = self.greedy.choose_offering(player, player.realm_offer)
            return space.encode(Action(ActionKind.PICK_OFFERING, choice))

        replanned = False
        for _ in range(100):
            action = self._advance(mask)
            if action is not None:
                if not mask[action]:
                    # Off-policy drivers (counterfactual harnesses) advance the
                    # world with somebody *else's* action, which strands a plan
                    # this scheduler already committed to -- a queued PLACE for
                    # a unit that was never selected. Re-planning from the live
                    # state is the defensible answer to "what would the teacher
                    # do here"; asserting is the right answer on-policy, where a
                    # stranded plan can only be a scheduler bug. Hence the flag
                    # rather than a blanket softening (doc 99 entry 160.98).
                    if self.off_policy and not replanned:
                        replanned = True
                        self._invalidate_plan()
                        continue
                    raise AssertionError(
                        f"Greedy scheduler emitted masked action "
                        f"{space.decode(action)!r} in stage {self._stage}; "
                        f"gold={player.gold} level={player.level} xp={player.xp} "
                        f"can_buy_xp={player.can_buy_xp()} "
                        f"mask_buy_xp={bool(mask[space.buy_xp_index])}"
                    )
                return action
        raise AssertionError(f"Greedy scheduler did not settle from {self._stage}")

    def choose_component(self, player, offered):
        """Use the direct teacher's anvil rule outside the action episode."""
        return self.greedy.choose_component(player, offered)

    def _reset_if_new_round(self) -> None:
        assert self.env.match is not None
        round_id = str(self.env.match.round_id)
        if round_id == self._round:
            return
        self._round = round_id
        self._invalidate_plan()
        self._rolls = 0

    def _invalidate_plan(self) -> None:
        """Discard the committed plan and restart the phase from live state.

        ``_rolls`` and ``_round`` deliberately survive: they are the round's
        reroll *budget*, not part of the plan, and resetting them would let an
        off-policy replan roll past ``MAX_ROLLS_PER_ROUND``.
        """
        self._stage = "econ_initial_buy" if self.econ is not None else "legacy_initial_buy"
        self._buy_candidates = None
        self._buy_after = ""
        self._pending_place = None
        self._item_actions = None
        self._board_actions = None

    def _advance(self, mask: np.ndarray) -> int | None:
        player = self.env.player
        assert self.env.match is not None
        space = self.env.action_space_helper

        if self._pending_place is not None:
            action, self._pending_place = self._pending_place, None
            return action

        buy_stages = {
            "legacy_initial_buy": (None, False, "legacy_xp"),
            "legacy_post_roll_buy": (None, False, "final_sell"),
            "econ_initial_buy": ("all", False, "econ_xp"),
            "econ_post_xp_buy": ("all", False, "econ_rolling"),
            "econ_roll_buy": ("all", self.greedy.roll_buys == "targets", "econ_roll_sell"),
        }
        if self._stage in buy_stages:
            budget, targets_only, after = buy_stages[self._stage]
            return self._next_buy(budget, targets_only, after)

        if self._stage == "legacy_xp":
            if player.gold >= self.greedy.level_at_gold and player.can_buy_xp():
                return space.buy_xp_index
            self._stage = "legacy_reroll"
            return None

        if self._stage == "legacy_reroll":
            if (
                player.gold >= self.greedy.reroll_at_gold
                and player.gold >= player.config.reroll_cost
            ):
                self._stage = "legacy_post_roll_buy"
                return space.reroll_index
            self._stage = "final_sell"
            return None

        if self._stage == "econ_xp":
            target = self.econ.level_target_after_pivot(player, self.env.match.round_id)
            if (
                target is not None
                and player.level < target
                and player.can_buy_xp()
                and player.gold >= player.config.xp_purchase_gold
            ):
                return space.buy_xp_index
            self._stage = "econ_post_xp_buy"
            return None

        if self._stage == "econ_rolling":
            floor = self.econ.roll_floor(self.env.match.round_id)
            if floor is None:
                floor = self.econ.save_floor
            if self.econ.has_pivoted(player, self.env.match.round_id):
                floor = self.econ.pivot_floor
            if self.econ.desperation_hp and player.hp <= self.econ.desperation_hp:
                floor = 0
            if (
                player.gold - player.config.reroll_cost >= floor
                and self._rolls < self.greedy.MAX_ROLLS_PER_ROUND
            ):
                self._rolls += 1
                self._stage = "econ_roll_buy"
                return space.reroll_index
            self._stage = "final_sell"
            return None

        if self._stage in ("econ_roll_sell", "final_sell"):
            action = self._next_surplus_sell()
            if action is not None:
                return action
            self._stage = "econ_rolling" if self._stage == "econ_roll_sell" else "field"
            return None

        if self._stage == "field":
            action = self._next_field_action()
            if action is not None:
                return action
            self._stage = self._stage_after_field
            return None

        if self._stage == "board":
            action = self._next_board_action(mask)
            if action is not None:
                return action
            self._stage = self._stage_after_board
            return None

        if self._stage == "equip":
            action = self._next_equip_action()
            if action is not None:
                return action
            self._stage = self._stage_after_equip
            return None

        if self._stage == "done":
            if player.has_pending_augment:
                return space.encode(Action(ActionKind.PICK_AUGMENT, 0))
            return space.end_index
        raise AssertionError(f"unknown greedy scheduler stage {self._stage!r}")

    def _next_buy(self, budget, targets_only: bool, after: str) -> int | None:
        """Emit the next action of one direct ``_buy_phase`` invocation."""
        player = self.env.player
        assert self.env.match is not None
        if self._buy_candidates is None:
            counts = trait_counts(player.all_units)
            targets = self.greedy._targets(player, self.env.match.round_id)
            candidates: list[tuple[bool, bool, int, int, int]] = []
            for slot in range(len(player.shop)):
                champion_id = player.shop.peek(slot)
                if champion_id is None or not player.can_buy(slot):
                    continue
                if targets_only and champion_id not in targets:
                    continue
                champion = player.data.champions[champion_id]
                synergy = sum(counts.get(trait, 0) for trait in champion.traits)
                owned = any(unit.champion.id == champion_id for unit in player.all_units)
                candidates.append((champion_id in targets, owned, synergy, champion.cost, slot))
            self._buy_candidates = [
                (slot, cost)
                for _target, _owned, _synergy, cost, slot in sorted(candidates, reverse=True)
            ]
            self._buy_after = after

        while self._buy_candidates:
            slot, cost = self._buy_candidates.pop(0)
            available = player.gold if budget == "all" else self.greedy._spendable(player)
            if player.can_buy(slot) and cost <= max(available, 0):
                return self.env.action_space_helper.buy_offset + slot

        self._buy_candidates = None
        self._stage = self._buy_after
        return None

    def _next_surplus_sell(self) -> int | None:
        player = self.env.player
        assert self.env.match is not None
        if player.free_bench_slots or not player.bench_units:
            return None
        targets = self.greedy._targets(player, self.env.match.round_id)
        sellable = [
            unit for unit in player.bench_units
            if unit.star_level == 1 and unit.champion.id not in targets
        ]
        if not sellable:
            return None
        unit = min(sellable, key=_strength)
        return self.env.action_space_helper.sell_offset + self.env.action_space_helper.slot_for_bench(
            player.bench.index(unit)
        )

    def _next_field_action(self) -> int | None:
        player = self.env.player
        space = self.env.action_space_helper
        if len(player.board) < player.max_board_units:
            benched = [(i, unit) for i, unit in enumerate(player.bench) if unit is not None]
            if not benched:
                return None
            bench_index, unit = max(benched, key=lambda pair: _strength(pair[1]))
            target = _preferred_hex(player, unit)
            if target is None:
                return None
            self._pending_place = space.place_offset + space.slot_for_hex(target)
            return space.select_offset + space.slot_for_bench(bench_index)

        if not player.bench_units or not player.board:
            return None
        best_bench = max(player.bench_units, key=_strength)
        weakest_hex = min(player.board, key=lambda hex_: _strength(player.board[hex_]))
        if _strength(best_bench) <= _strength(player.board[weakest_hex]):
            return None
        self._pending_place = space.place_offset + space.slot_for_hex(weakest_hex)
        return space.select_offset + space.slot_for_bench(player.bench.index(best_bench))

    def _next_board_action(self, mask: np.ndarray) -> int | None:
        """Emit one injected board-search swap as a SELECT with a queued PLACE.

        The planner names units, not bench indices: an earlier swap in the same
        phase displaces a board unit back onto the bench and renumbers every
        later slot, so an index computed at plan time goes stale mid-sequence
        (the note ``rl.search.search_policy`` carries for the same reason).
        """
        if self._board_planner is None:
            return None
        player = self.env.player
        space = self.env.action_space_helper
        if self._board_actions is None:
            self._board_actions = list(self._board_planner())
        while self._board_actions:
            unit, target_hex = self._board_actions.pop(0)
            index = next(
                (i for i, candidate in enumerate(player.bench) if candidate is unit),
                None,
            )
            if index is None:
                continue  # already fielded, sold, or combined away
            select = space.select_offset + space.slot_for_bench(index)
            if not mask[select] or target_hex not in player._own_hexes:
                continue
            self._pending_place = space.place_offset + space.slot_for_hex(target_hex)
            return select
        return None

    def _next_equip_action(self) -> int | None:
        player = self.env.player
        space = self.env.action_space_helper
        if not player.item_bag or not player.board:
            return None
        if self._item_planner is not None:
            if self._item_actions is None:
                self._item_actions = list(self._item_planner())
            while self._item_actions:
                item_id, target_hex = self._item_actions.pop(0)
                item_index = next(
                    (
                        index
                        for index, item in enumerate(
                            player.item_bag[: space.item_bag_slots]
                        )
                        if item.id == item_id
                    ),
                    None,
                )
                if item_index is None or target_hex not in player.board:
                    continue
                target = player.board[target_hex]
                if not player.can_equip_from_bag(item_id, target):
                    continue
                return (
                    space.equip_offset
                    + item_index * space.unit_slots
                    + space.slot_for_hex(target_hex)
                )
        cap = player.config.max_items_per_unit
        targets = [unit for unit in player.board_units if len(unit.items) < cap]
        if not targets:
            return None
        target = max(targets, key=_strength)
        if not player.can_equip_from_bag(player.item_bag[0].id, target):
            return None
        target_hex = next(hex_ for hex_, unit in player.board.items() if unit is target)
        return (
            space.equip_offset
            + space.slot_for_hex(target_hex)
        )
