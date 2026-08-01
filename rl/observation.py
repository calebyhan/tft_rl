"""State -> fixed-size feature vector encoding (doc 03 sec 3.1).

Everything is packed into one flat ``float32`` vector so a plain MLP policy
works out of the box. The layout is built from the loaded data's dimensions
(champion count, trait count, board size), so swapping in the full Set 17
dataset at milestone 8 changes the vector's size but needs no code change.

Champions are encoded as a **normalised id index plus cost and star level**
rather than one-hot, keeping the vector small enough for 28 board slots plus
9 bench slots plus 5 shop slots. Doc 03 sec 3.1 notes a set/attention encoder
is the natural upgrade later.

Opponent visibility is deliberately limited to HP / level / streak, per
doc 03 sec 3.1 -- full board scouting is a listed v2 addition.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from engine.economy import RoundId
from engine.player import PlayerState
from engine.schema import GameData
from engine.traits import active_traits

# Per-unit encoding width: (champion index, cost, star level, item count).
UNIT_FEATURES = 4
# Per-opponent: (hp, level, streak count, streak is-win flag).
OPPONENT_FEATURES = 4
# Self scalars: gold, level, xp, hp, streak count, streak sign, stage, round,
# board count, bench count, item bag count, actions remaining.
SELF_FEATURES = 12
# Selection state for the two-step SELECT -> PLACE move interaction:
# (holding a unit, which slot, is it a board slot, then the held unit's
# champion / cost / star / attack range).
#
# Without this the policy cannot tell whether it is mid-move, nor what it is
# holding -- and attack range is what decides front-line vs back-line
# placement. The action mask gates *legality*, but the network still needs
# these as *features* to choose sensibly among the legal options.
SELECTION_FEATURES = 7


@dataclass(frozen=True)
class ObservationSpec:
    """The layout and dimensions of the observation vector."""

    n_champions: int
    n_traits: int
    board_slots: int
    bench_slots: int
    shop_slots: int
    n_opponents: int

    @property
    def size(self) -> int:
        return sum(width for _, width in self.describe())

    def describe(self) -> list[tuple[str, int]]:
        """Section name and width, in layout order. Also used to locate sections."""
        return [
            ("self", SELF_FEATURES),
            ("selection", SELECTION_FEATURES),
            ("board", self.board_slots * UNIT_FEATURES),
            ("bench", self.bench_slots * UNIT_FEATURES),
            ("shop", self.shop_slots * 2),
            ("traits", self.n_traits),
            ("opponents", self.n_opponents * OPPONENT_FEATURES),
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

    def __init__(self, data: GameData, board_slots: int, n_opponents: int) -> None:
        self.data = data
        self.champion_ids = tuple(sorted(data.champions))
        self.trait_ids = tuple(sorted(data.traits))
        self._champion_index = {cid: i for i, cid in enumerate(self.champion_ids)}
        self._trait_index = {tid: i for i, tid in enumerate(self.trait_ids)}
        self.spec = ObservationSpec(
            n_champions=len(self.champion_ids),
            n_traits=len(self.trait_ids),
            board_slots=board_slots,
            bench_slots=data.config.bench_size,
            shop_slots=data.config.shop_slots,
            n_opponents=n_opponents,
        )
        # Normalisers keep every feature roughly in [0, 1].
        cfg = data.config
        self._max_hp = float(cfg.starting_hp)
        self._max_level = float(cfg.max_level)
        self._max_cost = float(max(cfg.pool_sizes)) if cfg.pool_sizes else 5.0
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
        for hex_ in sorted(board_hexes):
            self._write_unit(out, cursor, player.board.get(hex_))
            cursor += UNIT_FEATURES

        # -- bench --------------------------------------------------------
        for index in range(self.spec.bench_slots):
            unit = player.bench[index] if index < len(player.bench) else None
            self._write_unit(out, cursor, unit)
            cursor += UNIT_FEATURES

        # -- shop ---------------------------------------------------------
        for slot in range(self.spec.shop_slots):
            champion_id = player.shop.slots[slot] if slot < len(player.shop.slots) else None
            if champion_id is not None:
                champion = self.data.champions[champion_id]
                out[cursor] = (self._champion_index[champion_id] + 1) / self.spec.n_champions
                out[cursor + 1] = champion.cost / self._max_cost
            cursor += 2

        # -- active traits ------------------------------------------------
        active = active_traits(player.board_units, self.data)
        for trait_id, breakpoint_ in active.items():
            index = self._trait_index.get(trait_id)
            if index is not None:
                out[cursor + index] = breakpoint_.count / self._max_trait_tier
        cursor += self.spec.n_traits

        # -- opponents (public info only, doc 03 sec 3.1) -----------------
        for i in range(self.spec.n_opponents):
            if i < len(opponents):
                opponent = opponents[i]
                out[cursor] = opponent.hp / self._max_hp
                out[cursor + 1] = opponent.level / self._max_level
                out[cursor + 2] = min(opponent.streak_count / 8.0, 1.0)
                out[cursor + 3] = 1.0 if opponent.streak_type == "win" else 0.0
            cursor += OPPONENT_FEATURES

        assert cursor == self.spec.size, f"encoded {cursor} of {self.spec.size} features"
        return out

    def _write_unit(self, out: np.ndarray, cursor: int, unit) -> None:
        if unit is None:
            return
        out[cursor] = (self._champion_index[unit.champion.id] + 1) / self.spec.n_champions
        out[cursor + 1] = unit.champion.cost / self._max_cost
        out[cursor + 2] = unit.star_level / 3.0
        out[cursor + 3] = len(unit.items) / self._max_items
