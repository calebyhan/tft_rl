"""State -> fixed-size feature vector encoding (doc 03 sec 3.1).

Everything is packed into one flat ``float32`` vector so a plain MLP policy
works out of the box. The layout is built from the loaded data's dimensions
(champion count, trait count, board size), so swapping in the full Set 17
dataset at milestone 8 changes the vector's size but needs no code change.

Two champion encodings exist, and **the simple one measured better** --
``champion_encoding="index"`` is the default for that reason, not by inertia.

- ``index`` packs champion identity into a single normalised ordinal. In
  principle this is wrong: it implies champion *n* resembles champion *n+1*,
  and sorted by id that similarity is fictional. It also cannot express what a
  shop or bench unit would contribute to a trait.
- ``features`` fixes both, describing a champion by role, base stats and a
  multi-hot of its traits (47 floats per slot against 4, so 2056 observation
  dims against 240).

Measured on the real 63-champion set, behaviour-cloning the scripted policy
then evaluating over 60 unseen seeds:

===============  ==================  ====================
budget           index (match/place) features (match/place)
===============  ==================  ====================
150 ep, 25 epoch 62.4% / 7.78        64.4% / 7.58
150 ep, 50 epoch 71.6% / 6.78        90.3% / 7.42
400 ep, 50 epoch 80.4% / 6.05        91.8% / 6.95
===============  ==================  ====================

``features`` imitates the expert far more accurately at every budget and plays
*worse* at every budget, and 2.7x more expert data did not close the gap. The
richer encoding appears to fit the expert's state distribution and generalise
off it poorly -- most of its width is sparse trait bits across 28 mostly-empty
board slots. Keep this in mind before assuming a defect in the encoding is
what limits the agent: on this evidence it is not (doc 99 entry 6b.5).

The comparison was behaviour-cloning only, with no PPO phase, so it is
evidence about representation rather than about the final ceiling.

Doc 03 sec 3.1 notes a set/attention encoder is the natural upgrade beyond
either of these, and would address the sparsity these numbers point at.

Opponent visibility defaults to HP / level / streak, per doc 03 sec 3.1.
``scouting="full"`` adds the board-strength summary doc 03 lists as the v2
addition -- see :data:`SCOUTING_MODES` for what it exposes and why it is not
the default.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from engine.economy import RoundId
from engine.player import PlayerState
from engine.schema import ROLES, GameData
from engine.traits import active_traits, trait_counts

CHAMPION_ENCODINGS = ("features", "index")

# How much of an opponent's board the agent may see (doc 03 sec 3.1).
#
# ``summary`` (default) is doc 03's v1: HP, level and streak only -- the
# information a TFT client shows without scouting.
# ``full`` adds the v2 scouting block: board size, total board value, best
# star level, average unit cost, item count, and the opponent's trait tiers.
#
# Scouting is *legal* in TFT -- you may visit any board between rounds -- so
# ``full`` is not cheating. It was once **measured harmful** (-0.303, t=-2.34,
# n=300; doc 99 entry 19.1), and that verdict has since been **withdrawn**.
# Re-measured against the frozen engine the sign reversed: +0.270 placement
# better than its control, t=-1.79, which does not reach significance (22.2).
#
# It stays off by default anyway, for a weaker but still sufficient reason: it
# has never been shown to help. Both arms remain worse than skipping PPO.
#
# What the reversal cost is the *generalisation*. 19.1 paired this with the
# champion-encoding A/B and concluded that widening this flat observation with
# sparse features is a known-harmful operation, with the burden of proof on any
# future widening. That claim now rests on one surviving data point. The likely
# reason this half moved: it was measured on a game whose boards carried no
# items, so the added features encoded far less than they do now.
#
# Single training seed -- needs 3-seed replication before it is quoted as a
# result in either direction (22.4).
SCOUTING_MODES = ("summary", "full")

# Per-opponent scouting block, before the trait multi-hot: board unit count,
# total board value, best star level, average unit cost, items on board, and
# whether the opponent is at their unit cap (i.e. cannot field more).
SCOUT_FEATURES = 6

# Legacy per-unit width: (champion index, cost, star level, item count).
UNIT_FEATURES = 4

# Feature encoding, per unit slot: cost, star level, item count, then a
# one-hot role, four normalised base stats, and a multi-hot of the champion's
# traits (width = number of traits, added at runtime).
UNIT_SCALAR_FEATURES = 3
UNIT_ROLE_FEATURES = len(ROLES)
UNIT_STAT_FEATURES = 4
# Per-opponent: (hp, level, streak count, streak is-win flag).
OPPONENT_FEATURES = 4
# Self scalars: gold, level, xp, hp, streak count, streak sign, stage, round,
# board count, bench count, item bag count, actions remaining, and whether the
# board is at its unit cap. The last is derivable from board count and level,
# but it is a *comparison* between two encoded values, and it switches the
# expert's placement rule between two regimes -- field into an empty hex, or
# evict the weakest fielded unit. A probe missing it fit 42.5% of PLACE labels
# on its own training set; with it, 81.4% (doc 99 entry 30).
SELF_FEATURES = 13
# Selection state for the two-step SELECT -> PLACE move interaction:
# (holding a unit, which slot, is it a board slot, then the held unit's
# champion / cost / star / attack range).
#
# Without this the policy cannot tell whether it is mid-move, nor what it is
# holding -- and attack range is what decides front-line vs back-line
# placement. The action mask gates *legality*, but the network still needs
# these as *features* to choose sensibly among the legal options.
SELECTION_FEATURES = 7

# Per shop slot, appended to whichever champion encoding is in use:
#
#   owned    -- does the player already hold a copy of this champion?
#   synergy  -- how many units the player owns share a trait with it?
#
# These are *relational*: each is a comparison between the shop slot and the
# current roster, not a property of the champion. Doc 99 entry 29 measured why
# that distinction matters. A 1281-parameter model given these two quantities
# (plus cost and slot) predicts the scripted expert's BUY choice with 91.2%
# accuracy; the trained agent, which must derive them from the flat vector,
# manages 48% -- unchanged by 3.75x more data, by DAgger, and by the `features`
# encoding's full trait multi-hot, which supplies the raw traits but not the
# comparison.
#
# Deriving them is not hard in principle and is apparently very hard in
# practice: `owned` needs an identity match against every board and bench slot,
# `synergy` a dot product between the champion's traits and the board's trait
# counts. Neither is a computation a flat MLP over a concatenated vector finds
# naturally.
SHOP_DERIVED_FEATURES = 2

# Per owned unit slot (board and bench), appended to the champion encoding:
#
#   star_rank -- this unit's star level as a rank among the player's units
#   cost_rank -- this unit's cost as a rank among the player's units
#
# Both are already *derivable*: star and cost are encoded per slot. The agent
# still scores 21.9% on SELECT, whose rule is `max(bench, key=(star, cost))` --
# a rule a 1281-parameter model predicts at **100%** given these quantities
# (doc 99 entry 30). What is missing is not the information but the
# *comparison*, which is the same failure mode BUY had.
#
# Deliberately two separate ranks rather than one composite "strength" score.
# The expert's notion of strength is lexicographic (star, cost); encoding that
# directly would hand over its policy rather than a fact about the board. Ranks
# are policy-neutral -- an ordering the player can see -- and leave the agent to
# discover how to combine them.
UNIT_RANK_FEATURES = 2


@dataclass(frozen=True)
class ObservationSpec:
    """The layout and dimensions of the observation vector."""

    n_champions: int
    n_traits: int
    board_slots: int
    bench_slots: int
    shop_slots: int
    n_opponents: int
    n_augments: int = 0
    augment_choices: int = 0
    champion_encoding: str = "index"
    scouting: str = "summary"

    @property
    def opponent_width(self) -> int:
        """Width of one opponent's block, which the scouting mode decides."""
        if self.scouting == "summary":
            return OPPONENT_FEATURES
        return OPPONENT_FEATURES + SCOUT_FEATURES + self.n_traits

    @property
    def unit_width(self) -> int:
        """Width of one unit slot, which the champion encoding decides.

        Both encodings then append :data:`UNIT_RANK_FEATURES`.
        """
        if self.champion_encoding == "index":
            base = UNIT_FEATURES
        else:
            base = (
                UNIT_SCALAR_FEATURES
                + UNIT_ROLE_FEATURES
                + UNIT_STAT_FEATURES
                + self.n_traits
            )
        return base + UNIT_RANK_FEATURES

    @property
    def shop_width(self) -> int:
        """Shop slots hold an un-owned champion: no star level or items.

        Under the feature encoding they reuse the full unit layout (star and
        item count simply stay 0), so the policy can compare a shop unit
        against a benched one feature-for-feature.

        Both encodings then append :data:`SHOP_DERIVED_FEATURES` -- ``owned``
        and ``synergy``. See the module comment: these are *relational* facts
        about the slot and the current board, and no amount of raw champion
        description substitutes for them.
        """
        base = (
            2
            if self.champion_encoding == "index"
            else self.unit_width - UNIT_RANK_FEATURES
        )
        return base + SHOP_DERIVED_FEATURES

    @property
    def augment_width(self) -> int:
        """Held augments (multi-hot) plus a one-hot per offered choice.

        One-hot rather than an ordinal, because augment ids have no meaningful
        order -- and unlike champions there are few enough of them that the
        one-hot stays small. Zero when the dataset ships no augments, so the
        section vanishes entirely rather than padding with dead floats.
        """
        if not self.n_augments:
            return 0
        return self.n_augments * (1 + self.augment_choices)

    @property
    def size(self) -> int:
        return sum(width for _, width in self.describe())

    def describe(self) -> list[tuple[str, int]]:
        """Section name and width, in layout order. Also used to locate sections."""
        return [
            ("self", SELF_FEATURES),
            ("selection", SELECTION_FEATURES),
            ("board", self.board_slots * self.unit_width),
            ("bench", self.bench_slots * self.unit_width),
            ("shop", self.shop_slots * self.shop_width),
            ("traits", self.n_traits),
            ("augments", self.augment_width),
            ("opponents", self.n_opponents * self.opponent_width),
        ]

    def offset_of(self, section: str) -> int:
        """Index where ``section`` starts. Keeps tests off hard-coded offsets."""
        cursor = 0
        for name, width in self.describe():
            if name == section:
                return cursor
            cursor += width
        raise KeyError(f"unknown observation section {section!r}")


class ObservationEncoder:
    """Turns a :class:`PlayerState` and its match context into a feature vector."""

    def __init__(
        self,
        data: GameData,
        board_slots: int,
        n_opponents: int,
        champion_encoding: str = "index",
        scouting: str = "summary",
    ) -> None:
        if champion_encoding not in CHAMPION_ENCODINGS:
            raise ValueError(
                f"champion_encoding must be one of {CHAMPION_ENCODINGS}, "
                f"got {champion_encoding!r}"
            )
        if scouting not in SCOUTING_MODES:
            raise ValueError(
                f"scouting must be one of {SCOUTING_MODES}, got {scouting!r}"
            )
        self.data = data
        self.champion_encoding = champion_encoding
        self.scouting = scouting
        self.champion_ids = tuple(sorted(data.champions))
        self.trait_ids = tuple(sorted(data.traits))
        self.augment_ids = tuple(sorted(data.augments))
        self._champion_index = {cid: i for i, cid in enumerate(self.champion_ids)}
        self._trait_index = {tid: i for i, tid in enumerate(self.trait_ids)}
        self._augment_index = {aid: i for i, aid in enumerate(self.augment_ids)}
        self._role_index = {role: i for i, role in enumerate(sorted(ROLES))}
        self.spec = ObservationSpec(
            n_champions=len(self.champion_ids),
            n_traits=len(self.trait_ids),
            board_slots=board_slots,
            bench_slots=data.config.bench_size,
            shop_slots=data.config.shop_slots,
            n_opponents=n_opponents,
            n_augments=len(self.augment_ids),
            augment_choices=data.config.augments.choices,
            champion_encoding=champion_encoding,
            scouting=scouting,
        )
        # Normalisers keep every feature roughly in [0, 1].
        cfg = data.config
        self._max_hp = float(cfg.starting_hp)
        self._max_level = float(cfg.max_level)
        self._max_cost = float(max(cfg.pool_sizes)) if cfg.pool_sizes else 5.0
        # Synergy counts owned units sharing a trait with a shop unit, summed
        # over the champion's traits. Normalised by max_level -- the board cap
        # at max level -- so it usually lands in [0, 1]; a multi-trait champion
        # on a full board can exceed that, hence the clamp at the write site.
        self._synergy_scale = float(cfg.max_level) or 1.0
        self._max_stage = float(cfg.round_structure.max_stages)
        self._max_rounds = float(cfg.round_structure.rounds_per_stage)
        self._max_items = float(cfg.max_items_per_unit)
        self._max_range = float(
            max((c.stats.attack_range for c in data.champions.values()), default=1)
        )
        self._max_trait_tier = float(
            max(
                (bp.count for t in data.traits.values() for bp in t.breakpoints),
                default=1,
            )
        )
        # Base-stat normalisers, taken over the 3-star values so a 3-star unit
        # lands near 1.0 rather than off the top of the scale.
        champions = list(data.champions.values())
        self._max_health = max(
            (c.stats.health_at(3) for c in champions), default=1.0
        ) or 1.0
        self._max_attack_damage = max(
            (c.stats.attack_damage_at(3) for c in champions), default=1.0
        ) or 1.0
        self._max_attack_speed = max(
            (c.stats.attack_speed for c in champions), default=1.0
        ) or 1.0

    @property
    def size(self) -> int:
        return self.spec.size

    # -- encoding ---------------------------------------------------------

    def encode(
        self,
        player: PlayerState,
        round_id: RoundId,
        opponents: list[PlayerState],
        board_hexes: tuple,
        actions_remaining: int = 0,
        max_actions: int = 1,
        selected_slot: int | None = None,
        selected_unit=None,
    ) -> np.ndarray:
        out = np.zeros(self.spec.size, dtype=np.float32)
        cursor = 0

        # -- self ---------------------------------------------------------
        streak_sign = {"win": 1.0, "loss": -1.0, "none": 0.0}[player.streak_type]
        out[cursor : cursor + SELF_FEATURES] = [
            min(player.gold / 100.0, 1.0),
            player.level / self._max_level,
            player.xp / 100.0,
            player.hp / self._max_hp,
            min(player.streak_count / 8.0, 1.0),
            streak_sign,
            round_id.stage / self._max_stage,
            round_id.round / self._max_rounds,
            len(player.board) / max(self.spec.board_slots, 1),
            len(player.bench_units) / max(self.spec.bench_slots, 1),
            min(len(player.item_bag) / 10.0, 1.0),
            actions_remaining / max(max_actions, 1),
            float(len(player.board) >= player.max_board_units),
        ]
        cursor += SELF_FEATURES

        # -- selection (mid-move state) -----------------------------------
        unit_slots = max(self.spec.board_slots + self.spec.bench_slots, 1)
        if selected_slot is not None:
            out[cursor] = 1.0
            out[cursor + 1] = (selected_slot + 1) / unit_slots
            out[cursor + 2] = 1.0 if selected_slot < self.spec.board_slots else 0.0
            if selected_unit is not None:
                out[cursor + 3] = (
                    self._champion_index[selected_unit.champion.id] + 1
                ) / self.spec.n_champions
                out[cursor + 4] = selected_unit.champion.cost / self._max_cost
                out[cursor + 5] = selected_unit.star_level / 3.0
                out[cursor + 6] = min(
                    selected_unit.derived_stats().attack_range / self._max_range, 1.0
                )
        cursor += SELECTION_FEATURES

        # -- board --------------------------------------------------------
        # Ranks are over *all* owned units, board and bench together, so a
        # bench unit's rank is directly comparable with a fielded one -- which
        # is exactly the comparison the swap rule makes.
        ranks = self._unit_ranks(player)
        unit_width = self.spec.unit_width
        for hex_ in sorted(board_hexes):
            self._write_unit(out, cursor, player.board.get(hex_), ranks)
            cursor += unit_width

        # -- bench --------------------------------------------------------
        for index in range(self.spec.bench_slots):
            unit = player.bench[index] if index < len(player.bench) else None
            self._write_unit(out, cursor, unit, ranks)
            cursor += unit_width

        # -- shop ---------------------------------------------------------
        owned_ids = {unit.champion.id for unit in player.all_units}
        board_counts = trait_counts(player.all_units)
        for slot in range(self.spec.shop_slots):
            champion_id = player.shop.slots[slot] if slot < len(player.shop.slots) else None
            if champion_id is not None:
                champion = self.data.champions[champion_id]
                if self.champion_encoding == "index":
                    out[cursor] = (
                        self._champion_index[champion_id] + 1
                    ) / self.spec.n_champions
                    out[cursor + 1] = champion.cost / self._max_cost
                else:
                    # A shop unit is always 1-star with no items.
                    self._write_champion_features(
                        out, cursor, champion, star_level=1, item_count=0
                    )
                # Derived, relational, and the reason this section exists in
                # this shape -- see the module comment on SHOP_DERIVED_FEATURES.
                base = self.spec.shop_width - SHOP_DERIVED_FEATURES
                out[cursor + base] = float(champion_id in owned_ids)
                out[cursor + base + 1] = min(
                    sum(board_counts.get(t, 0) for t in champion.traits)
                    / self._synergy_scale,
                    1.0,
                )
            cursor += self.spec.shop_width

        # -- active traits ------------------------------------------------
        active = active_traits(player.board_units, self.data)
        for trait_id, breakpoint_ in active.items():
            index = self._trait_index.get(trait_id)
            if index is not None:
                out[cursor + index] = breakpoint_.count / self._max_trait_tier
        cursor += self.spec.n_traits

        # -- augments: what is held, and what is on offer right now --------
        if self.spec.augment_width:
            for augment in player.augments:
                index = self._augment_index.get(augment.id)
                if index is not None:
                    out[cursor + index] = 1.0
            cursor += self.spec.n_augments
            for choice in range(self.spec.augment_choices):
                if choice < len(player.augment_offer):
                    index = self._augment_index.get(player.augment_offer[choice].id)
                    if index is not None:
                        out[cursor + index] = 1.0
                cursor += self.spec.n_augments

        # -- opponents (doc 03 sec 3.1) -----------------------------------
        for i in range(self.spec.n_opponents):
            if i < len(opponents):
                opponent = opponents[i]
                out[cursor] = opponent.hp / self._max_hp
                out[cursor + 1] = opponent.level / self._max_level
                out[cursor + 2] = min(opponent.streak_count / 8.0, 1.0)
                out[cursor + 3] = 1.0 if opponent.streak_type == "win" else 0.0
                if self.scouting == "full":
                    self._write_scout(out, cursor + OPPONENT_FEATURES, opponent)
            cursor += self.spec.opponent_width

        assert cursor == self.spec.size, f"encoded {cursor} of {self.spec.size} features"
        return out

    def _write_scout(self, out: np.ndarray, cursor: int, opponent) -> None:
        """Summarise an opponent's board: what scouting them would reveal.

        A *summary* rather than a slot-by-slot copy of their board. Encoding
        28 hexes per opponent would multiply the observation by roughly eight,
        and position matters far less to the decision this feeds ("is their
        board stronger than mine, and which traits are they contesting?") than
        composition does.
        """
        units = opponent.board_units
        if units:
            value = sum(u.champion.cost * u.star_level for u in units)
            reference = max(len(units) * self._max_cost * 3.0, 1.0)
            out[cursor] = min(len(units) / max(self.spec.board_slots, 1), 1.0)
            out[cursor + 1] = min(value / reference, 1.0)
            out[cursor + 2] = max(u.star_level for u in units) / 3.0
            out[cursor + 3] = (
                sum(u.champion.cost for u in units) / len(units)
            ) / self._max_cost
            out[cursor + 4] = min(
                sum(len(u.items) for u in units) / (len(units) * self._max_items), 1.0
            )
        out[cursor + 5] = (
            1.0 if len(opponent.board) >= opponent.max_board_units else 0.0
        )
        cursor += SCOUT_FEATURES

        # Their active traits, so the agent can see what is being contested.
        for trait_id, breakpoint_ in active_traits(units, self.data).items():
            index = self._trait_index.get(trait_id)
            if index is not None:
                out[cursor + index] = breakpoint_.count / self._max_trait_tier

    def _unit_ranks(self, player: PlayerState) -> dict:
        """Normalised star and cost ranks over every unit the player owns.

        Ties share a rank, and a single unit ranks 1.0 rather than 0.0 -- the
        top of an ordering of one is still the top, and mapping it to 0 would
        make "my only unit" look like "my worst unit".
        """
        units = list(player.all_units)
        if not units:
            return {}

        def rank_map(values):
            ordered = sorted(set(values))
            span = max(len(ordered) - 1, 1)
            return {v: (ordered.index(v) / span if len(ordered) > 1 else 1.0)
                    for v in ordered}

        star_rank = rank_map([u.star_level for u in units])
        cost_rank = rank_map([u.champion.cost for u in units])
        return {
            id(u): (star_rank[u.star_level], cost_rank[u.champion.cost])
            for u in units
        }

    def _write_unit(self, out: np.ndarray, cursor: int, unit, ranks=None) -> None:
        if unit is None:
            return
        if self.champion_encoding == "index":
            out[cursor] = (
                self._champion_index[unit.champion.id] + 1
            ) / self.spec.n_champions
            out[cursor + 1] = unit.champion.cost / self._max_cost
            out[cursor + 2] = unit.star_level / 3.0
            out[cursor + 3] = len(unit.items) / self._max_items
        else:
            self._write_champion_features(
                out,
                cursor,
                unit.champion,
                star_level=unit.star_level,
                item_count=len(unit.items),
            )
        tail = cursor + self.spec.unit_width - UNIT_RANK_FEATURES
        star, cost = (ranks or {}).get(id(unit), (0.0, 0.0))
        out[tail] = star
        out[tail + 1] = cost

    def _write_champion_features(
        self, out: np.ndarray, cursor: int, champion, star_level: int, item_count: int
    ) -> None:
        """Describe a champion by role, stats and traits rather than by id.

        Star level scales the stats it actually scales, so a 2-star unit reads
        as the stronger thing it is instead of relying on the policy to
        multiply the star feature through itself.
        """
        stats = champion.stats
        out[cursor] = champion.cost / self._max_cost
        out[cursor + 1] = star_level / 3.0
        out[cursor + 2] = item_count / self._max_items
        cursor += UNIT_SCALAR_FEATURES

        role_index = self._role_index.get(champion.role)
        if role_index is not None:
            out[cursor + role_index] = 1.0
        cursor += UNIT_ROLE_FEATURES

        star = max(1, min(star_level, 3))
        out[cursor] = min(stats.health_at(star) / self._max_health, 1.0)
        out[cursor + 1] = min(stats.attack_damage_at(star) / self._max_attack_damage, 1.0)
        out[cursor + 2] = min(stats.attack_range / self._max_range, 1.0)
        out[cursor + 3] = min(stats.attack_speed / self._max_attack_speed, 1.0)
        cursor += UNIT_STAT_FEATURES

        # Multi-hot traits: what this unit would contribute to a synergy. This
        # is the signal the index encoding could not express at all.
        for trait_id in champion.traits:
            index = self._trait_index.get(trait_id)
            if index is not None:
                out[cursor + index] = 1.0
