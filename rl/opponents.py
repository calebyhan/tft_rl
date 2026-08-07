"""Scripted seat policies (doc 03 sec 3, milestone 5-6).

These fill the seats the learning agent is not playing, and drive the smoke
test. They are deliberately simple but not trivial -- a non-degenerate training
partner, per doc 03 sec 3 -- and every one of them uses ``PlayerState``'s
``can_*`` predicates rather than catching :class:`IllegalAction`, so a policy
never depends on exceptions for control flow.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from engine.economy import RoundId
from engine.match import PlanningContext
from engine.player import IllegalAction, PlayerState
from engine.traits import trait_counts
from engine.unit import UnitInstance


@dataclass(frozen=True)
class EconStrategy:
    """A real TFT economy plan: when to level, and when to spend down.

    Doc 99 entry 70 found the field running ~1 level behind real TFT on twice
    the gold, because :meth:`GreedyPolicy.plan` bought XP **once** per round
    however much gold it held -- 6 XP/round against the 60 needed for level
    7->8, so ten rounds where a real player takes one.

    The economics the old policy already had right: interest is +1 per 10 gold
    **capped at 50**, so gold above 50 earns nothing and holding it is pure
    waste. What it lacked was the ability to act on that.

    ``level_targets``
        ``round label -> level to have reached by then``. The policy buys XP as
        hard as its gold allows to stay on this curve. Real TFT benchmarks are
        published in exactly this form (level 6 at 3-2, 7 at 3-5/4-1, 8 at
        4-1/4-2).
    ``roll_floors``
        ``round label -> gold to roll down to``, in effect from that round
        until the next entry supersedes it. With **no entry yet in force the
        floor is ``save_floor``**, so surplus above the interest cap is rolled
        rather than banked -- gold over 50 earns nothing, so converting it into
        shop odds strictly beats holding it. That is what "spend down to 50"
        means; it is not the same as slow-rolling, which sets a floor at or
        below 50 and thereby also spends the *income* each round.

        Two shapes matter and the difference is easy to get wrong:

        * **Roll down once** (standard, fast 8): a low floor on the breakpoint
          round, then an entry restoring ``save_floor`` on the next round, so
          the seat rebuilds its economy. Leaving the low floor in force makes
          the seat roll to nothing *every* round, which is not fast 8 -- it is
          a policy with no economy, and it levels slower than the strategy it
          is supposed to beat because it never earns interest again.
        * **Roll the surplus** (slow roll, hyper roll): one entry at
          ``save_floor`` or below, left in force, so every round's income above
          the floor is rolled away. This is the archetype that genuinely wants
          continuous rolling.
    ``save_floor``
        Gold kept when not rolling. 50 is the interest cap and the only
        defensible default: below it you lose interest, above it you gain
        nothing.
    """

    name: str
    level_targets: Mapping[str, int] = field(default_factory=dict)
    roll_floors: Mapping[str, int] = field(default_factory=dict)
    save_floor: int = 50
    # A reroll comp commits to a few specific champions and buys every copy of
    # them. Without this a rolling policy spreads purchases across ~14
    # champions of a tier and copies never concentrate: doc 99 entry 73
    # measured `slowroll6` rolling 46 times a game, buying 95 units, and
    # ending with 3-stars on 0.2-0.4% of its units -- a smaller board of the
    # same 2-stars everyone else has. 0 disables targeting.
    target_cost: int = 0
    target_count: int = 0

    @staticmethod
    def _key(label: str) -> tuple[int, int]:
        stage, round_ = label.split("-")
        return int(stage), int(round_)

    def _latest(self, table: Mapping[str, int], now: RoundId):
        """The most recent entry at or before ``now``; None if none applies."""
        current = (now.stage, now.round)
        best = None
        for label, value in table.items():
            key = self._key(label)
            if key <= current and (best is None or key > best[0]):
                best = (key, value)
        return None if best is None else best[1]

    def target_level(self, now: RoundId) -> int | None:
        return self._latest(self.level_targets, now)

    def roll_floor(self, now: RoundId) -> int | None:
        return self._latest(self.roll_floors, now)


# The four archetypes players actually run. Level benchmarks follow published
# guidance (doc 99 entry 70's sources); the roll floors are this project's
# reading of "roll down to" and are flagged as such in entry 71.
# Every archetype carries a late 9 (and 10 where the econ supports it). An
# earlier version stopped at 8, which is not how real TFT is played -- level 9
# is standard from ~5-5 -- and in this engine, where board size dominates
# (doc 99 entries 67, 68, 72), a plan that caps at 8 forfeits slots to a
# policy that simply keeps levelling.
STANDARD = EconStrategy(
    name="standard",
    level_targets={"2-5": 5, "3-2": 6, "4-1": 7, "4-5": 8, "5-5": 9, "6-3": 10},
    # Roll down at 4-5 for the level-8 board, then rebuild.
    roll_floors={"4-5": 20, "4-6": 50},
)
FAST8 = EconStrategy(
    name="fast8",
    level_targets={"2-5": 5, "3-2": 6, "3-5": 7, "4-1": 8, "5-3": 9, "6-1": 10},
    roll_floors={"4-1": 10, "4-2": 50},
)
SLOWROLL6 = EconStrategy(
    name="slowroll6",
    # Hold 6 and roll the surplus; level only once the board is hit.
    level_targets={"2-5": 5, "3-2": 6, "5-1": 7, "5-5": 8, "6-1": 9},
    roll_floors={"3-2": 50},
    target_cost=2,
    target_count=3,
)
HYPERROLL = EconStrategy(
    name="hyperroll",
    # Roll to nothing in stage 2 for 1-cost 3-stars, **then transition back to
    # a normal curve**. An earlier version held level 5 from 2-3 to 4-5 -- a
    # five-unit board through all of stages 3 and 4 -- which is not hyper-roll,
    # it is never transitioning, and it placed 6.07 against standard's 4.02
    # (doc 99 entry 73).
    level_targets={"2-1": 4, "2-3": 5, "3-2": 6, "4-1": 7, "4-5": 8, "5-5": 9},
    roll_floors={"2-3": 0, "3-2": 50},
    target_cost=1,
    target_count=3,
)
STRATEGIES = {s.name: s for s in (STANDARD, FAST8, SLOWROLL6, HYPERROLL)}

# A real lobby is not eight identical bots. Eight seats running a mix is both
# closer to the game and better training: a field of one archetype lets a
# learned policy overfit to a single opponent model, which this project has
# never controlled for. Proportions lean standard because that is what most
# players default to.
DEFAULT_FIELD = (
    STANDARD, STANDARD, STANDARD,
    FAST8, FAST8,
    SLOWROLL6, SLOWROLL6,
    HYPERROLL,
)


def default_opponent(seat: int) -> "GreedyPolicy":
    """The seat policy `TFTEnv` fills opponent seats with.

    Seeded and indexed by seat, so a given seat plays the same archetype every
    game and the environment stays deterministic per match seed.
    """
    return GreedyPolicy(seed=seat, econ=DEFAULT_FIELD[seat % len(DEFAULT_FIELD)])


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

    Pass ``econ=`` an :class:`EconStrategy` for a real TFT economy plan
    (doc 99 entry 71); the default keeps the pre-entry-70 behaviour.
    """

    # A real player rolls 40-60 times in a roll-down round. This bounds the
    # loop so a pathological state cannot spin forever, and is deliberately
    # above what any archetype here actually uses.
    MAX_ROLLS_PER_ROUND = 80

    def __init__(
        self,
        seed: int | None = None,
        level_at_gold: int = 30,
        reroll_at_gold: int = 45,
        keep_interest: bool = True,
        econ: EconStrategy | None = None,
    ) -> None:
        self.rng = random.Random(seed)
        self.level_at_gold = level_at_gold
        self.reroll_at_gold = reroll_at_gold
        self.keep_interest = keep_interest
        # None keeps the pre-entry-70 behaviour, so every measurement taken
        # before this existed still reproduces (lesson 12).
        self.econ = econ

    def plan(self, player: PlayerState, context: PlanningContext) -> None:
        if self.econ is not None:
            self._econ_plan(player, context)
        else:
            self._legacy_plan(player, context)
        self._sell_surplus(player, context)
        _fill_board(player, self.rng, key=_strength)
        # After the board is settled, so items land on units that are actually
        # fielded rather than on something about to be benched.
        _equip_phase(player)

    def _legacy_plan(self, player: PlayerState, context: PlanningContext) -> None:
        """One XP purchase and one reroll per round (doc 99 entry 70.3).

        Kept verbatim because ~70 entries of measurements were taken against
        it. It is not a sensible economy: it banks gold it is willing to spend
        but cannot, reaching 145 gold by 6-4 against real TFT's 50.
        """
        self._buy_phase(player, context)
        if player.gold >= self.level_at_gold and player.can_buy_xp():
            player.buy_xp()
        if player.gold >= self.reroll_at_gold and player.gold >= player.config.reroll_cost:
            player.reroll(context.pool, self.rng)
            self._buy_phase(player, context)

    def _econ_plan(self, player: PlayerState, context: PlanningContext) -> None:
        """Level to the curve, then roll the surplus down to the floor."""
        self._buy_phase(player, context, budget="all")

        # -- levelling: buy XP until on curve, or out of spendable gold ------
        target = self.econ.target_level(context.round_id)
        if target is not None:
            cost = player.config.xp_purchase_gold
            # Levelling is worth dipping below the interest floor -- that is
            # what "level to 8 at 4-1" means -- so this spends real gold, not
            # `_spendable`. It still stops before bankrupting the seat.
            while (
                player.level < target
                and player.can_buy_xp()
                and player.gold >= cost
            ):
                player.buy_xp()

        self._buy_phase(player, context, budget="all")

        # -- rolling: spend down to the floor this round calls for ----------
        floor = self.econ.roll_floor(context.round_id)
        if floor is None:
            floor = self.econ.save_floor
        cost = player.config.reroll_cost
        rolls = 0
        while player.gold - cost >= floor and rolls < self.MAX_ROLLS_PER_ROUND:
            player.reroll(context.pool, self.rng)
            rolls += 1
            self._buy_phase(player, context, budget="all")
            self._sell_surplus(player, context)

    def choose_offering(self, player: PlayerState, offerings: Sequence) -> int:
        """Draft pick: prefer a copy the board already owns, then raw cost.

        Picking a champion already owned progresses a star-up, which is worth
        more than a marginally pricier unit -- the same ordering ``_buy_phase``
        uses, so the bot drafts consistently with how it shops.
        """
        owned = {u.champion.id for u in player.all_units}
        best, best_key = 0, None
        for index, offering in enumerate(offerings):
            champion = player.data.champions[offering.champion_id]
            key = (offering.champion_id in owned, champion.cost)
            if best_key is None or key > best_key:
                best, best_key = index, key
        return best

    def choose_component(self, player: PlayerState, offered: Sequence[str]) -> str:
        """Anvil pick (low-HP catch-up): finish an item on the carry if possible.

        A component that completes what the carry is already holding is worth
        far more than a second loose component, so that is preferred; failing
        that the choice is random, since ranking components against each other
        needs champion knowledge this bot does not have.
        """
        carry = _carry_unit(player)
        if carry is not None:
            held = [i for i in carry.items if i.is_component]
            for component in held:
                completions = [
                    c for c in offered
                    if player.registry.combine(component.id, c) is not None
                ]
                if completions:
                    return self.rng.choice(sorted(completions))
        return self.rng.choice(sorted(offered))

    # -- helpers ----------------------------------------------------------

    def _spendable(self, player: PlayerState) -> int:
        """Gold the bot is willing to spend, optionally protecting interest."""
        if not self.keep_interest:
            return player.gold
        per = player.config.interest_per_gold
        cap = player.config.interest_cap * per
        floor = min(player.gold - (player.gold % per), cap)
        return max(player.gold - floor, 0)

    def _buy_phase(
        self, player: PlayerState, context: PlanningContext, budget=None
    ) -> None:
        """Buy the best affordable shop units.

        ``budget`` defaults to :meth:`_spendable`, which protects the interest
        floor. Economy plans pass full gold instead: **the interest floor
        governs rolling, not buying.** Gating purchases at gold-50 means a
        slow-roller rolls down to 50, hits the copy it was rolling for, and
        cannot buy it -- it pays to search and then refuses the result. That
        alone made the reroll archetypes place 5.293 and 6.107 against
        standard's 3.887 (doc 99 entry 73).
        """
        counts = trait_counts(player.all_units)
        targets = self._targets(player)
        candidates = []
        for slot in range(len(player.shop)):
            champion_id = player.shop.peek(slot)
            if champion_id is None or not player.can_buy(slot):
                continue
            champion = player.data.champions[champion_id]
            synergy = sum(counts.get(t, 0) for t in champion.traits)
            owned = any(u.champion.id == champion_id for u in player.all_units)
            # Targeting outranks everything: a reroll comp buys every copy of
            # its carries regardless of synergy or cost.
            candidates.append(
                (champion_id in targets, owned, synergy, champion.cost, slot)
            )
        # Prefer a target, then completing a pair, then synergy, then cost.
        for is_target, owned, synergy, cost, slot in sorted(candidates, reverse=True):
            del is_target, owned, synergy
            available = player.gold if budget == "all" else self._spendable(player)
            if player.can_buy(slot) and cost <= max(available, 0):
                player.buy(slot, context.pool)

    def _targets(self, player: PlayerState) -> frozenset[str]:
        """The champions a reroll comp is committed to. See :func:`reroll_targets`."""
        return reroll_targets(player, self.econ)

    def _sell_surplus(self, player: PlayerState, context: PlanningContext) -> None:
        """Free bench space by selling the weakest surplus 1-stars.

        Never sells a target: those copies are the whole point of rolling, and
        a 3-star needs nine of them held long enough to combine.
        """
        targets = self._targets(player)
        while not player.free_bench_slots and player.bench_units:
            sellable = [
                u for u in player.bench_units
                if u.star_level == 1 and u.champion.id not in targets
            ]
            if not sellable:
                break
            player.sell(min(sellable, key=_strength), context.pool)



def reroll_targets(player, econ) -> frozenset[str]:
    """The champions a reroll comp is committed to.

    Chosen by copies already held, so the commitment emerges from what the shop
    has offered rather than being fixed in advance -- which is how a player
    actually picks a reroll carry. Empty unless the strategy sets
    ``target_cost``.

    Module-level and shared: `GreedyPolicy` honoured `target_cost` and the
    *teacher* silently ignored it, so `slowroll6` rolled the shop and then
    bought by generic strength, accumulating copies of nothing -- 0 three-stars
    in the agent seat against 100% in the field, from the same archetype
    (doc 99 entry 86). One definition, both callers.
    """
    if econ is None or not econ.target_cost:
        return frozenset()
    held: dict[str, int] = {}
    for unit in player.all_units:
        if unit.champion.cost == econ.target_cost:
            held[unit.champion.id] = (
                held.get(unit.champion.id, 0) + 3 ** (unit.star_level - 1)
            )
    ranked = sorted(held, key=lambda c: (-held[c], c))
    return frozenset(ranked[: econ.target_count])


class NoOpPolicy:
    """Does nothing. Useful for isolating one seat's behaviour in tests."""

    def plan(self, player: PlayerState, context: PlanningContext) -> None:
        return None


# --- shared placement helpers -------------------------------------------


def _strength(unit: UnitInstance) -> tuple[int, int]:
    """A crude ordering: star level dominates, then champion cost."""
    return (unit.star_level, unit.champion.cost)


def _carry_unit(player: PlayerState) -> UnitInstance | None:
    """The unit a bot funnels items into: its strongest *fielded* one.

    Concentrating items on one carry is the single most important itemisation
    heuristic in TFT -- three items on one unit beats one item on three -- and
    it needs no per-champion knowledge.
    """
    if not player.board:
        return None
    return max(player.board_units, key=_strength)


def _equip_phase(player: PlayerState) -> None:
    """Move bagged items onto the board, concentrating them on the carry.

    Without this the item system is inert: components accumulate in the bag
    and nothing ever benefits from them. Equipping goes through
    ``equip_from_bag``, so two components on the same unit auto-combine into
    the completed item exactly as in TFT.
    """
    if not player.board:
        return
    cap = player.config.max_items_per_unit
    # A stable snapshot: equipping mutates item_bag, and a combine can push an
    # item back into it.
    for _ in range(len(player.item_bag)):
        if not player.item_bag:
            break
        targets = [u for u in player.board_units if len(u.items) < cap]
        if not targets:
            break
        # Carry first, then the next strongest with room.
        target = max(targets, key=_strength)
        try:
            player.equip_from_bag(player.item_bag[0].id, target)
        except IllegalAction:
            # Nothing legal to do with this item right now; stop rather than
            # spin, and it stays in the bag for a later round.
            break


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
