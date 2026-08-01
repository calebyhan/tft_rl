"""Scripted seat policies (doc 03 sec 3, milestone 5-6).

These fill the seats the learning agent is not playing, and drive the smoke
test. They are deliberately simple but not trivial -- a non-degenerate training
partner, per doc 03 sec 3 -- and every one of them uses ``PlayerState``'s
``can_*`` predicates rather than catching :class:`IllegalAction`, so a policy
never depends on exceptions for control flow.
"""

from __future__ import annotations

import random
from typing import Sequence

from engine.match import PlanningContext
from engine.player import PlayerState
from engine.traits import trait_counts
from engine.unit import UnitInstance


class RandomPolicy:
    """Acts uniformly at random within the legal action set.

    The baseline every other policy should beat; also the best fuzz driver,
    since it explores odd states a sensible policy never reaches.
    """

    def __init__(self, seed: int | None = None, actions_per_round: int = 8) -> None:
        self.rng = random.Random(seed)
        self.actions_per_round = actions_per_round

    def plan(self, player: PlayerState, context: PlanningContext) -> None:
        for _ in range(self.actions_per_round):
            choices = ["buy", "reroll", "xp", "field", "bench", "sell", "stop"]
            action = self.rng.choice(choices)
            if action == "stop":
                break
            if action == "buy":
                slots = [i for i in range(len(player.shop)) if player.can_buy(i)]
                if slots:
                    player.buy(self.rng.choice(slots), context.pool)
            elif action == "reroll" and player.gold >= player.config.reroll_cost:
                player.reroll(context.pool, self.rng)
            elif action == "xp" and player.can_buy_xp():
                player.buy_xp()
            elif action == "field":
                _field_one(player, self.rng)
            elif action == "bench" and player.board:
                if player.free_bench_slots:
                    player.move_to_bench(self.rng.choice(sorted(player.board)))
            elif action == "sell" and player.all_units:
                player.sell(self.rng.choice(player.all_units), context.pool)
        _fill_board(player, self.rng)


class GreedyPolicy:
    """Doc 03 sec 3's suggested heuristic bot.

    Buys the most expensive affordable unit that helps its current traits,
    levels on a gold-threshold curve, rerolls with genuinely spare gold, and
    fields its strongest units front-to-back by role.
    """

    def __init__(
        self,
        seed: int | None = None,
        level_at_gold: int = 30,
        reroll_at_gold: int = 45,
        keep_interest: bool = True,
    ) -> None:
        self.rng = random.Random(seed)
        self.level_at_gold = level_at_gold
        self.reroll_at_gold = reroll_at_gold
        self.keep_interest = keep_interest

    def plan(self, player: PlayerState, context: PlanningContext) -> None:
        self._buy_phase(player, context)
        if player.gold >= self.level_at_gold and player.can_buy_xp():
            player.buy_xp()
        if player.gold >= self.reroll_at_gold and player.gold >= player.config.reroll_cost:
            player.reroll(context.pool, self.rng)
            self._buy_phase(player, context)
        self._sell_surplus(player, context)
        _fill_board(player, self.rng, key=_strength)

    # -- helpers ----------------------------------------------------------

    def _spendable(self, player: PlayerState) -> int:
        """Gold the bot is willing to spend, optionally protecting interest."""
        if not self.keep_interest:
            return player.gold
        per = player.config.interest_per_gold
        cap = player.config.interest_cap * per
        floor = min(player.gold - (player.gold % per), cap)
        return max(player.gold - floor, 0)

    def _buy_phase(self, player: PlayerState, context: PlanningContext) -> None:
        counts = trait_counts(player.all_units)
        candidates = []
        for slot in range(len(player.shop)):
            champion_id = player.shop.peek(slot)
            if champion_id is None or not player.can_buy(slot):
                continue
            champion = player.data.champions[champion_id]
            synergy = sum(counts.get(t, 0) for t in champion.traits)
            owned = any(u.champion.id == champion_id for u in player.all_units)
            candidates.append((owned, synergy, champion.cost, slot))
        # Prefer completing a pair, then trait synergy, then raw cost.
        for owned, synergy, cost, slot in sorted(candidates, reverse=True):
            del owned, synergy
            if player.can_buy(slot) and cost <= max(self._spendable(player), 0):
                player.buy(slot, context.pool)

    def _sell_surplus(self, player: PlayerState, context: PlanningContext) -> None:
        """Free bench space by selling the weakest surplus 1-stars."""
        while not player.free_bench_slots and player.bench_units:
            weakest = min(player.bench_units, key=_strength)
            if weakest.star_level > 1:
                break
            player.sell(weakest, context.pool)


class NoOpPolicy:
    """Does nothing. Useful for isolating one seat's behaviour in tests."""

    def plan(self, player: PlayerState, context: PlanningContext) -> None:
        return None


# --- shared placement helpers -------------------------------------------


def _strength(unit: UnitInstance) -> tuple[int, int]:
    """A crude ordering: star level dominates, then champion cost."""
    return (unit.star_level, unit.champion.cost)


def _field_one(player: PlayerState, rng: random.Random) -> bool:
    """Move one benched unit onto a free hex, if that is legal."""
    if len(player.board) >= player.max_board_units:
        return False
    occupied = [i for i, u in enumerate(player.bench) if u is not None]
    free = player.free_board_hexes
    if not occupied or not free:
        return False
    player.move_to_board(rng.choice(occupied), rng.choice(free))
    return True


def _fill_board(player: PlayerState, rng: random.Random, key=None) -> None:
    """Field as many units as the level allows, strongest first.

    Melee units are placed on the front rows and ranged ones behind, which is
    the single most important positioning heuristic in TFT and keeps scripted
    boards from being trivially bad.
    """
    while len(player.board) < player.max_board_units:
        benched = [(i, u) for i, u in enumerate(player.bench) if u is not None]
        if not benched:
            break
        if key is not None:
            index, unit = max(benched, key=lambda pair: key(pair[1]))
        else:
            index, unit = benched[0]
        target = _preferred_hex(player, unit)
        if target is None:
            break
        player.move_to_board(index, target)

    # A weak fielded unit should give way to a stronger benched one.
    if key is None:
        return
    while player.bench_units and player.board:
        best_bench = max(player.bench_units, key=key)
        weakest_hex = min(player.board, key=lambda h: key(player.board[h]))
        if key(best_bench) <= key(player.board[weakest_hex]):
            break
        bench_index = player.bench.index(best_bench)
        player.move_to_board(bench_index, weakest_hex)


def _preferred_hex(player: PlayerState, unit: UnitInstance):
    """A free hex on the front rows for melee, the back rows for ranged."""
    free = player.free_board_hexes
    if not free:
        return None
    from engine.hexgrid import axial_to_offset

    half_rows = player.hex_board.half_rows
    melee = unit.derived_stats().attack_range <= 1

    def depth(hex_) -> int:
        # Own-frame rows run from the centre line outward.
        row, _ = axial_to_offset(hex_)
        return row - half_rows

    return min(free, key=lambda h: (depth(h) if melee else -depth(h), h))


def build_seats(
    count: int, policy_factory=None, seed: int = 0
) -> Sequence[object]:
    """Build ``count`` seat policies, each with its own derived seed."""
    factory = policy_factory or (lambda s: GreedyPolicy(seed=s))
    return [factory(seed * 1000 + i) for i in range(count)]
