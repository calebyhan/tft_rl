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
from engine.traits import trait_counts
from rl.env import TFTEnv
from rl.greedy_action import GreedyActionPolicy
from rl.opponents import reroll_targets

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


def _copies_owned(player, unit) -> int:
    """How many copies of ``unit``'s champion sit at its star level.

    Guards the sell branch: two copies are one upgrade away, so selling either
    destroys more value than the sale returns.
    """
    return sum(
        1
        for other in player.all_units
        if other.champion.id == unit.champion.id
        and other.star_level == unit.star_level
    )


# Which item stats a carry can actually use, keyed by the champion's role.
#
# The default policy always equips bag slot 0, so an ability-power item lands
# on a marksman about half the time and contributes nothing. Role is the signal
# the dataset actually carries (18 Casters, 23 AD-ish, 20 Tanks); attack range
# is *not* a proxy for AD-vs-AP, and using it as one would be a guess dressed
# as a rule.
_ROLE_STATS = {
    "Caster": ("ability_power", "damage_amp"),
    "Marksman": ("attack_damage_pct", "attack_speed_pct", "crit_chance"),
    "Assassin": ("attack_damage_pct", "crit_chance", "attack_speed_pct"),
    "Fighter": ("attack_damage_pct", "attack_speed_pct", "omnivamp"),
    "Tank": ("health", "armor", "magic_resist"),
    "Specialist": ("attack_damage_pct", "ability_power"),
}


def _best_item_for(player, carry, space) -> int:
    """Index in the item bag of the item best suited to ``carry``.

    Scores each bagged item by the share of its stat block the carry's role can
    use, normalised so a big raw number (health 200) does not automatically
    beat a small one (crit_chance 0.2). Ties and unknown roles fall back to
    slot 0, i.e. the historical behaviour.
    """
    wanted = _ROLE_STATS.get(carry.champion.role)
    if not wanted:
        return 0

    best, best_score = 0, None
    for index, item in enumerate(player.item_bag[: space.item_bag_slots]):
        stats = item.stats or {}
        total = sum(abs(float(v)) for v in stats.values())
        if total <= 0:
            score = 0.0
        else:
            score = sum(abs(float(stats.get(k, 0.0))) for k in wanted) / total
        if best_score is None or score > best_score:
            best, best_score = index, score
    return best


def scripted_policy(
    env: TFTEnv,
    level_at_gold: int = 30,
    keep_interest: bool = True,
    *,
    buy_synergy: bool = False,
    match_items: bool = False,
    corner_carry: bool = False,
    roll_at_level: int = 0,
    level_cap: int = 0,
    sell_bench: bool = False,
    keep_pairs: int = 0,
    econ=None,
    place_rule: str = "rows",
) -> PolicyFn:
    """A competent heuristic expressed **through the action space**.

    This is the ceiling check: if a sensible heuristic cannot reach roughly
    average placement (4.5) against the same heuristic bots, then the action
    space or the environment is handicapping the agent and a learned policy
    could never do better either. It also gives PPO a real target to beat.

    Mirrors :class:`rl.opponents.GreedyPolicy`: protect interest gold, buy the
    best affordable unit, field the strongest units (melee front, ranged back),
    upgrade the board by swapping in stronger bench units, level on a gold
    threshold.

    **The keyword flags are candidate improvements to the teacher, not to the
    bots.** Doc 99 §8 records the binding constraint: the clone is at parity
    with this policy, and imitation caps at its teacher by construction. Since
    the seven opponents run the *same* heuristic, average placement is pinned
    near 4.5 unless the teacher is made better than them specifically.

    All three default to the historical behaviour, so every number measured
    before they existed remains reproducible.

    ``buy_synergy``
        Add the trait-synergy term to the buy ordering. Without it this policy
        shops on ``(owned, cost)`` while :class:`~rl.opponents.GreedyPolicy`
        shops on ``(owned, synergy, cost)`` -- the teacher is a *strictly
        weaker* shopper than its own opponents, which is a plausible reason
        the ceiling check reads 4.620 rather than 4.5.
    ``match_items``
        Choose *which* bagged item to equip by the carry's damage type instead
        of always taking bag slot 0. Half the item pool is dead stats on the
        wrong carry.
    ``corner_carry``
        Field the strongest ranged unit in a back *corner* rather than merely
        the back row, which is what actually keeps a carry alive against the
        engine's melee pathing.
    ``roll_at_level``
        Spend spare gold rerolling the shop once the player reaches this
        level. **0 disables it, which is what every measurement before
        2026-08-03 did** -- no policy in this project has ever rerolled, so XP
        was the only unbounded gold sink and levelling won by construction
        (doc 99 entry 36.6). Rolling is the primary gold sink in real TFT and
        the only way to convert gold into specific units.

    ``level_cap``
        Stop *buying* XP at this level. **0 disables it.** Passive XP still
        applies, so a long game drifts past the cap -- 2/round against 36 to go
        6->7. That matches real TFT, where a slow-roller stops paying for
        levels rather than stops receiving them. Measured in doc 99 entry 68:
        capping costs +0.553 at level 8 and +1.730 at level 7, and rolling the
        freed gold recovers **none** of it. This is the knob real
        slow-rolling needs and the one this project did not have: doc 99 entry
        67 tried to express it as ``level_at_gold=80``, which starves levelling
        from stage 1 and tests "never level" rather than "level normally to 6-7,
        then hold". Separating the two requires capping the *destination*
        without delaying the *journey*, which no existing parameter does.

    ``econ``
        An :class:`~rl.opponents.EconStrategy`, which **replaces**
        ``level_at_gold``/``roll_at_level``/``level_cap`` with a real economy
        plan: level to the curve, roll down to the floor that round calls for.

        Doc 99 entry 72's motivation: once the field ran real economies the
        teacher's edge over parity fell from 1.470 to 0.617, because the
        opponents had an economy and the teacher had "buy XP whenever gold >=
        30". A teacher that is the imitation target for an agent meant to play
        real TFT should not be the worst economist at the table.

    ``sell_bench``
        Sell the weakest bench unit when the bench is full and it is not
        combine progress. Also off by default and also historically absent --
        and without it ``roll_at_level`` is inert, because a full bench masks
        every buy action and the reroll branch then spins on a shop it cannot
        buy from (doc 99 entry 37.4). Measure the two together.
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
                if corner_carry and ranged:
                    # Deepest row, then furthest from the centre column: a
                    # corner is what actually survives the melee pathing, and
                    # the back *row* alone does not.
                    centre = (player.hex_board.cols - 1) / 2

                    def corner_key(slot: int):
                        row, col = axial_to_offset(space.hex_for_slot(slot))
                        return (row - half_rows, abs(col - centre))

                    return space.place_offset + max(empty, key=corner_key)
                empty.sort(key=lambda s: axial_to_offset(space.hex_for_slot(s))[0] - half_rows)
                if place_rule == "rows":
                    return space.place_offset + (empty[-1] if ranged else empty[0])
                # `rows` sorts by depth and takes an end. The sort is *stable*,
                # so within the chosen row ties break by slot index and every
                # unit lands on the same flank -- the board clumps into one
                # corner. Entry 80 tests whether spreading pays: a clumped
                # board is what area abilities and a single focused enemy carry
                # punish. Both alternatives are deterministic functions of the
                # board, so unlike the search (79.9) a clone can follow them.
                def depth_of(slot: int) -> int:
                    return axial_to_offset(space.hex_for_slot(slot))[0] - half_rows

                extreme = max(map(depth_of, empty)) if ranged else min(
                    map(depth_of, empty))
                row_slots = [s for s in empty if depth_of(s) == extreme]
                centre = (player.hex_board.cols - 1) / 2

                def col_of(slot: int) -> int:
                    return axial_to_offset(space.hex_for_slot(slot))[1]

                if place_rule == "centre":
                    return space.place_offset + min(
                        row_slots, key=lambda s: (abs(col_of(s) - centre), s))
                if place_rule == "spread":
                    taken = [axial_to_offset(h)[1] for h in player.board]
                    if not taken:
                        return space.place_offset + min(
                            row_slots, key=lambda s: (abs(col_of(s) - centre), s))
                    # Furthest column from any fielded unit, centre-most on a
                    # tie so the board fills outward rather than to one edge.
                    return space.place_offset + max(
                        row_slots,
                        key=lambda s: (min(abs(col_of(s) - c) for c in taken),
                                       -abs(col_of(s) - centre), -s))
                raise ValueError(f"unknown place_rule {place_rule!r}")

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
                index = 0
                if match_items:
                    index = _best_item_for(
                        player, player.board[space.hex_for_slot(carry)], space
                    )
                action = space.equip_offset + index * space.unit_slots + carry
                if mask[action]:
                    return action

        # -- nothing held --------------------------------------------------
        #
        # Under an econ plan, buying spends full gold: the interest floor
        # governs *rolling*, not buying. Gating purchases at gold-50 means a
        # policy that rolls down to 50 cannot buy what it just rolled for
        # (doc 99 entry 73).
        budget = player.gold if econ is not None else spendable(player)
        buys = [
            i
            for i in range(space.shop_slots)
            if mask[i] and player.data.champions[player.shop.slots[i]].cost <= budget
        ]
        if buys:
            counts = trait_counts(player.all_units) if buy_synergy else {}

            # A reroll plan's whole purpose is concentrating copies into a few
            # champions. `EconStrategy` declares which via `target_cost` /
            # `target_count`, `GreedyPolicy` has always honoured it, and this
            # policy silently ignored it -- so `slowroll6` rolled the shop and
            # bought by generic strength, reaching **0** three-stars in the
            # agent seat against 100% in the field (doc 99 entry 86). A target
            # outranks synergy and cost: a fourth copy of the carry is worth
            # more than a better unit the plan will never star up.
            targets = reroll_targets(player, econ, env.match.round_id)

            def buy_key(i: int):
                champion = player.data.champions[player.shop.slots[i]]
                owned = any(u.champion.id == champion.id for u in player.all_units)
                target = champion.id in targets or (
                    # Nothing held yet at the target cost: any unit of that
                    # cost is a candidate carry, or the plan can never start.
                    not targets and econ is not None and econ.target_cost
                    and champion.cost == econ.target_cost
                )
                if not buy_synergy:
                    return (target, owned, 0, champion.cost)
                synergy = sum(counts.get(t, 0) for t in champion.traits)
                return (target, owned, synergy, champion.cost)

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

        if econ is not None:
            # Level to the curve. Worth dipping below the interest floor --
            # that is what "level 8 at 4-1" means -- so this spends real gold.
            target = econ.level_target_after_pivot(player, env.match.round_id)
            if (
                mask[space.buy_xp_index]
                and target is not None
                and player.level < target
                and player.gold >= player.config.xp_purchase_gold
            ):
                return space.buy_xp_index
        elif (
            mask[space.buy_xp_index]
            and player.gold >= level_at_gold
            and not (level_cap and player.level >= level_cap)
        ):
            return space.buy_xp_index

        # -- clear the bench so buying is possible at all -------------------
        #
        # This policy has never sold a unit -- unlike the bots it plays
        # against, whose `GreedyPolicy._sell_surplus` has always freed bench
        # space. The board fills with
        # the best units, the SELECT branch above then refuses to field
        # anything weaker, and every later purchase is stranded on the bench
        # forever. Measured on the first reroll arm: **100% of rerolls
        # happened with a full bench**, mean gold 25.1, with an affordable
        # shop slot present every single time. The buy action was masked off,
        # so the policy rerolled a shop it could not buy from until its gold
        # hit the interest floor. Rolling could not work (doc 99 entry 37.4).
        #
        # Sell the weakest bench unit, but never one that is combine progress:
        # a second copy is worth more than its sell value.
        if sell_bench and all(u is not None for u in player.bench):
            spare = [
                b
                for b, unit in enumerate(player.bench)
                if unit is not None
                and mask[space.sell_offset + space.slot_for_bench(b)]
                and _copies_owned(player, unit) < 2
                # Never a reroll target: nine copies must be *held* long
                # enough to combine, and the bench is where they wait.
                and unit.champion.id not in reroll_targets(
                    player, econ, env.match.round_id)
            ]
            if spare:
                # Prefer copies that are not progressing an upgrade. A 1-star
                # of a champion already held at 2-star is the start of the
                # second pair a 3-star needs, and it is also the weakest thing
                # on the bench -- so "sell the weakest" reaches for it first.
                # Doc 99 entry 102 measured the cost: 13.4% of the teacher's
                # sells were this, and it reached a 3-star in 0 of 30 games
                # against a real 34.5%, peaking at one 2-star and no more.
                #
                # A preference, not a ban: if every candidate is progressing,
                # the seat still sells rather than deadlocking on a full bench
                # and stalling every later purchase (entry 37.4).
                #
                # `keep_pairs` is a *count*, not a switch: the number of
                # champions whose progressing copies are protected, chosen by
                # how close each is to completing. Protecting every one of them
                # unconditionally cost 0.343 placement (102.3), and bench
                # congestion could not be ruled out as the reason (102.5) --
                # a real player commits to two or three carries, not to every
                # pair the shop happens to offer.
                protected: set[str] = set()
                if keep_pairs:
                    progress: dict[str, int] = {}
                    for unit in player.all_units:
                        if unit.star_level >= 2:
                            progress[unit.champion.id] = (
                                progress.get(unit.champion.id, 0)
                                + 3 ** (unit.star_level - 1)
                            )
                    protected = set(sorted(
                        progress, key=lambda c: (-progress[c], c)
                    )[:keep_pairs])
                keepers = [
                    b for b in spare
                    if not (player.bench[b].star_level == 1
                            and player.bench[b].champion.id in protected)
                ]
                worst = min(keepers or spare,
                            key=lambda b: _unit_strength(player.bench[b]))
                return space.sell_offset + space.slot_for_bench(worst)

        # -- roll down: the gold sink that did not exist ------------------
        #
        # No measured policy in this project has ever rerolled: this branch
        # was absent and `GreedyPolicy` rolls at most once per phase above 45
        # gold, so gold piled up unspent (mean 164 by 5-4) and XP was the only
        # unbounded sink. That makes "spend everything on XP" win by
        # construction rather than by mechanics, and it is the most likely
        # reason two batches of content failed to move the econ sweep
        # (doc 99 entry 36.6).
        #
        # Rolling is gated on having reached the level worth rolling at, and
        # protects interest exactly as buying does.
        if econ is not None:
            floor = econ.roll_floor(env.match.round_id)
            if floor is None:
                floor = econ.save_floor
            # A seat one hit from elimination has no use for an interest
            # economy (doc 99 entry 99.1). Honoured here as well as in
            # `GreedyPolicy`: a field read by one consumer and ignored by the
            # other is entry 86's defect, and entry 87's guard in
            # `tests/test_econ_fields.py` exists to catch exactly this.
            if econ.desperation_hp and player.hp <= econ.desperation_hp:
                floor = 0
            # An abandoned reroll line stops rolling and banks (entry 111.5),
            # honoured here for the same both-consumers reason as above.
            if econ.has_pivoted(player, env.match.round_id):
                floor = econ.pivot_floor
            if (
                mask[space.reroll_index]
                and player.gold - player.config.reroll_cost >= floor
            ):
                return space.reroll_index
        elif (
            roll_at_level
            and player.level >= roll_at_level
            and mask[space.reroll_index]
            and spendable(player) >= player.config.reroll_cost
        ):
            return space.reroll_index

        return space.end_index

    return act


def greedy_action_policy(
    env: TFTEnv,
    *,
    level_at_gold: int = 30,
    reroll_at_gold: int = 45,
    keep_interest: bool = True,
    econ=None,
    roll_buys: str = "all",
    off_policy: bool = False,
    item_planner=None,
    board_planner=None,
    board_planner_first: bool = True,
) -> PolicyFn:
    """Faithful action-space adapter for :class:`rl.opponents.GreedyPolicy`.

    Unlike :func:`scripted_policy`, this is not an independently evolved
    heuristic.  It preserves the direct teacher's planning order exactly and
    is therefore the base required before measuring a search-policy port (doc
    99 entries 153--154).
    """
    policy = GreedyActionPolicy(
        env,
        level_at_gold=level_at_gold,
        reroll_at_gold=reroll_at_gold,
        keep_interest=keep_interest,
        econ=econ,
        roll_buys=roll_buys,
        off_policy=off_policy,
        item_planner=item_planner,
        board_planner=board_planner,
        board_planner_first=board_planner_first,
    )
    env.register_external_policy(policy)
    return policy


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


# --- parallel evaluation -------------------------------------------------
#
# A game is ~3-10 seconds of pure-Python combat ticks and 97% of measurement
# time is spent inside `Simulation.step`, so the only cheap speedup available
# is running seeds side by side: they are fully independent and each is
# deterministic given its seed. Measured on an M3 Pro, one arm of the econ
# sweep went from a single busy core to all of them.
#
# The workers rebuild the env and the policy themselves rather than receiving
# them. `scripted_policy` returns a closure over its env, which is not
# picklable, and shipping a live env to a worker would share mutable state
# between processes even if it were. That restricts this path to policies
# describable by keyword arguments -- which is every arm of every sweep, but
# *not* an sb3 model, so `evaluate` stays the general entry point.

_WORKER: dict = {}


def _parallel_init(
    data_dir, env_kwargs: dict, policy_kwargs: dict, search_kwargs: dict | None = None
) -> None:
    import logging

    from engine.loader import load_all

    # Each worker re-loads the dataset and would re-emit the loader's
    # unverified-constants warning, once per process.
    logging.getLogger("engine.loader").setLevel(logging.ERROR)
    data = load_all(data_dir) if data_dir is not None else load_all()
    env = TFTEnv(data=data, **env_kwargs)
    _WORKER["env"] = env
    kwargs = dict(policy_kwargs)
    policy = expert_base_policy(env, kwargs.pop("expert_base", "scripted"), **kwargs)
    if search_kwargs is not None:
        from rl.search import search_policy

        policy = search_policy(env, base=policy, **search_kwargs)
    _WORKER["policy"] = policy


# Keeps a search policy's stream disjoint from the match's own.
SEARCH_SEED_OFFSET = 1_000_003


def _parallel_episode(seed: int):
    # Reseed any policy carrying its own stream (the search wrapper), so a
    # given (config, seed) reproduces regardless of which worker runs it.
    rng = getattr(_WORKER["policy"], "rng", None)
    if rng is not None:
        # Offset, **not** the bare episode seed. `TFTEnv.reset(seed=s)` builds
        # `Match(seed=s)` whose own `random.Random(s)` draws every combat seed,
        # so seeding the search identically hands it the same sequence the real
        # fight will use -- the search would be scoring candidates on the exact
        # fight about to happen. Seeding with `s` measured -0.087 against +0.303
        # for the same configuration; a large prime offset gives an independent
        # stream that is still reproducible per episode (doc 99 entry 54.2).
        rng.seed(seed + SEARCH_SEED_OFFSET)
    result = evaluate(_WORKER["env"], _WORKER["policy"], seeds=[seed])
    return (
        seed,
        result.placements[0],
        result.rewards[0],
        result.rounds[0],
        result.illegal_actions,
    )


EXPERT_BASES = ("scripted", "greedy")


def expert_base_policy(env: TFTEnv, base: str = "scripted", **policy_kwargs):
    """Build the cloning teacher's base policy (doc 99 entry 160.93).

    ``scripted`` is the separately evolved heuristic; ``greedy`` is the faithful
    :class:`~rl.opponents.GreedyPolicy` port. The two place the same to within
    a quarter of a standard error (160.91) and are **not** interchangeable: exact
    buy search is worth −1.095 placement wrapped around ``greedy`` and −0.095
    around ``scripted`` (160.92), because ``scripted``'s flags already buy well.
    Which base a search teacher wraps decides whether it is worth anything, so
    the base is selected explicitly and recorded, never assumed.

    ``greedy`` takes no scripted-only flags. Silently dropping them would let a
    run record ``expert_flags=True`` in its sidecar while the teacher ignored
    them, which is a sidecar that lies about the policy that produced the
    labels -- the failure ``teacher_gap`` exists to prevent.
    """
    if base not in EXPERT_BASES:
        raise ValueError(f"unknown expert base {base!r}, expected one of {EXPERT_BASES}")
    if base == "scripted":
        return scripted_policy(env, **policy_kwargs)
    ignored = {
        key: value for key, value in policy_kwargs.items()
        if key not in ("econ", "level_at_gold", "keep_interest", "off_policy")
        and value
    }
    if ignored:
        raise ValueError(
            f"expert base 'greedy' does not take {sorted(ignored)}; "
            "these are scripted_policy flags and would be silently dropped"
        )
    return greedy_action_policy(
        env,
        econ=policy_kwargs.get("econ"),
        **{k: v for k, v in policy_kwargs.items()
           if k in ("level_at_gold", "keep_interest", "off_policy")},
    )


def evaluate_scripted_parallel(
    seeds: Sequence[int],
    workers: int | None = None,
    data_dir=None,
    env_kwargs: dict | None = None,
    search_kwargs: dict | None = None,
    **policy_kwargs,
) -> EvalResult:
    """Evaluate :func:`scripted_policy` over ``seeds`` across processes.

    Returns exactly what the serial path returns -- results are reassembled in
    seed order, not completion order, so paired comparisons still line up seed
    for seed. ``workers=1`` runs in-process, which is what the equivalence test
    compares against.
    """
    import multiprocessing as mp

    seeds = list(seeds)
    env_kwargs = env_kwargs or {}
    workers = workers or mp.cpu_count()

    if workers <= 1 or len(seeds) <= 1:
        from engine.loader import load_all

        data = load_all(data_dir) if data_dir is not None else load_all()
        env = TFTEnv(data=data, **env_kwargs)
        kwargs = dict(policy_kwargs)
        policy = expert_base_policy(
            env, kwargs.pop("expert_base", "scripted"), **kwargs)
        if search_kwargs is not None:
            from rl.search import search_policy

            policy = search_policy(env, base=policy, **search_kwargs)
        return evaluate(env, policy, seeds=seeds)

    with mp.get_context("spawn").Pool(
        processes=workers,
        initializer=_parallel_init,
        initargs=(data_dir, env_kwargs, policy_kwargs, search_kwargs),
    ) as pool:
        # imap_unordered, not map: games vary from ~3 to ~10 seconds, so
        # handing results back as they finish keeps every worker busy instead
        # of blocking a chunk on its slowest seed. It also means the results
        # arrive in completion order, which is why the reassembly below is
        # keyed by seed rather than zipped positionally.
        rows = list(pool.imap_unordered(_parallel_episode, seeds))

    by_seed = {seed: row for seed, *row in rows}
    result = EvalResult(episodes=len(seeds))
    for seed in seeds:
        placement, reward, rounds, illegal = by_seed[seed]
        result.placements.append(placement)
        result.rewards.append(reward)
        result.rounds.append(rounds)
        result.illegal_actions += illegal
    return result


def _model_init(run_dir, data_dir, env_kwargs: dict) -> None:
    import logging

    import torch
    from sb3_contrib import MaskablePPO

    from engine.loader import load_all

    logging.getLogger("engine.loader").setLevel(logging.ERROR)
    # One thread per worker. The forward pass is 1.2% of evaluation wall clock,
    # so there is nothing to gain from intra-op parallelism here and plenty to
    # lose: N workers each spawning 6 threads oversubscribes a 12-core machine.
    torch.set_num_threads(1)
    data = load_all(data_dir) if data_dir is not None else load_all()
    _WORKER["env"] = TFTEnv(data=data, **env_kwargs)
    # The model is loaded per worker rather than pickled to it: an SB3 model
    # carries an optimiser and a live env reference, and a custom policy class
    # is rebuilt from current source on load. A path survives that; an object
    # graph does not.
    _WORKER["policy"] = sb3_policy(MaskablePPO.load(run_dir, device="cpu"))


def _model_episode(seed: int):
    result = evaluate(_WORKER["env"], _WORKER["policy"], seeds=[seed])
    return (
        seed,
        result.placements[0],
        result.rewards[0],
        result.rounds[0],
        result.illegal_actions,
    )


def evaluate_model_parallel(
    run_dir,
    seeds: Sequence[int],
    workers: int | None = None,
    data_dir=None,
    env_kwargs: dict | None = None,
) -> EvalResult:
    """Evaluate a saved model over ``seeds`` across processes.

    The serial equivalent was the whole of `compare_models`' 68-minute median,
    and profiling put 97.8% of it inside the combat simulator rather than in
    torch -- so this is the same win as :func:`evaluate_scripted_parallel`, on
    the task that actually gates every paired comparison.

    ``sb3_policy`` is deterministic, so an episode depends only on its seed.
    Results are reassembled in seed order, which is what keeps a paired
    comparison lined up seed for seed.
    """
    import multiprocessing as mp

    seeds = list(seeds)
    env_kwargs = env_kwargs or {}
    workers = workers or mp.cpu_count()

    context = mp.get_context("spawn")
    with context.Pool(
        processes=workers,
        initializer=_model_init,
        initargs=(str(run_dir), data_dir, env_kwargs),
    ) as pool:
        rows = list(pool.imap_unordered(_model_episode, seeds))

    by_seed = {seed: row for seed, *row in rows}
    result = EvalResult(episodes=len(seeds))
    for seed in seeds:
        placement, reward, rounds, illegal = by_seed[seed]
        result.placements.append(placement)
        result.rewards.append(reward)
        result.rounds.append(rounds)
        result.illegal_actions += illegal
    return result
