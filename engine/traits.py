"""Trait activation counting and bonus application (doc 03 sec 2.5).

Counting follows TFT's rule: a trait counts **distinct champions** fielded on
the board, not unit copies -- two Jinxes give one Sniper, not two -- and bench
units never count (doc 01 sec 6). Emblems add their trait to the wearer's set
before counting.

Only the highest breakpoint met applies, not the sum of all tiers passed
(doc 01 sec 6). Because breakpoints are an explicit sorted list per trait,
irregular tiers (a trait active at exactly 1 unit, or at 3/5) work without
special-casing.

A breakpoint's ``params`` may set the reserved key ``targets``:

* ``"trait_members"`` (default) -- bonuses apply only to units that have the
  trait, matching most TFT traits.
* ``"team"`` -- bonuses apply to the whole board.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Iterable, Mapping, Sequence

from engine.items import emblem_trait_id
from engine.schema import GameData, TraitBreakpoint
from engine.stats import StatBonuses, bonuses_from_params

if TYPE_CHECKING:  # avoids a runtime import cycle (unit -> items/stats -> ...)
    from engine.unit import UnitInstance

log = logging.getLogger(__name__)

TARGETS_PARAM = "targets"
TARGETS_TEAM = "team"
TARGETS_TRAIT_MEMBERS = "trait_members"
_VALID_TARGETS = (TARGETS_TEAM, TARGETS_TRAIT_MEMBERS)


def unit_traits(unit: "UnitInstance") -> frozenset[str]:
    """A unit's effective traits: innate ones plus any granted by emblems."""
    granted = {
        trait_id
        for item in unit.items
        if (trait_id := emblem_trait_id(item)) is not None
    }
    return frozenset(unit.champion.traits) | granted


def trait_counts(units: Iterable["UnitInstance"]) -> dict[str, int]:
    """Distinct fielded champions per trait id."""
    champions_by_trait: dict[str, set[str]] = {}
    for unit in units:
        for trait_id in unit_traits(unit):
            champions_by_trait.setdefault(trait_id, set()).add(unit.champion.id)
    return {trait_id: len(champs) for trait_id, champs in champions_by_trait.items()}


def active_traits(
    units: Sequence["UnitInstance"], data: GameData
) -> dict[str, TraitBreakpoint]:
    """The active breakpoint per trait for a fielded board.

    Traits present but below their lowest breakpoint are omitted entirely.
    """
    active: dict[str, TraitBreakpoint] = {}
    for trait_id, count in trait_counts(units).items():
        trait = data.traits.get(trait_id)
        if trait is None:
            log.warning(
                "trait %r is not present in the loaded trait data -- ignoring it",
                trait_id,
            )
            continue
        breakpoint_ = trait.active_breakpoint(count)
        if breakpoint_ is not None:
            active[trait_id] = breakpoint_
    return active


def _applies_to(
    breakpoint_: TraitBreakpoint, trait_id: str, unit: "UnitInstance"
) -> bool:
    targets = breakpoint_.params.get(TARGETS_PARAM, TARGETS_TRAIT_MEMBERS)
    if targets not in _VALID_TARGETS:
        log.warning(
            "trait %r breakpoint %d has unknown targets=%r; treating it as %r",
            trait_id,
            breakpoint_.count,
            targets,
            TARGETS_TRAIT_MEMBERS,
        )
        targets = TARGETS_TRAIT_MEMBERS
    if targets == TARGETS_TEAM:
        return True
    return trait_id in unit_traits(unit)


def trait_bonuses_for(
    unit: "UnitInstance", active: Mapping[str, TraitBreakpoint]
) -> StatBonuses:
    """The stat bonuses ``unit`` receives from the board's active traits."""
    bonuses = StatBonuses()
    for trait_id, breakpoint_ in active.items():
        if _applies_to(breakpoint_, trait_id, unit):
            bonuses = bonuses.merged_with(bonuses_from_params(breakpoint_.params))
    return bonuses


class TraitState:
    """Active traits for one board, with per-unit bonuses computed once.

    Traits are fixed for the duration of a combat (units do not gain or lose
    traits mid-fight in v1), so this is built at combat start and reused.
    """

    def __init__(self, units: Sequence["UnitInstance"], data: GameData) -> None:
        self.data = data
        self.active: dict[str, TraitBreakpoint] = active_traits(units, data)
        self.counts: dict[str, int] = trait_counts(units)
        self._by_unit: dict[int, StatBonuses] = {
            id(unit): trait_bonuses_for(unit, self.active) for unit in units
        }

    def bonuses_for(self, unit: "UnitInstance") -> StatBonuses:
        cached = self._by_unit.get(id(unit))
        if cached is None:
            # A unit not present at construction (e.g. a summon) still gets
            # team-wide bonuses computed on demand.
            cached = trait_bonuses_for(unit, self.active)
            self._by_unit[id(unit)] = cached
        return cached

    def tier_of(self, trait_id: str) -> int:
        """The active breakpoint count for ``trait_id``, or 0 if inactive."""
        breakpoint_ = self.active.get(trait_id)
        return breakpoint_.count if breakpoint_ else 0

    def __repr__(self) -> str:
        parts = ", ".join(
            f"{tid} {bp.count}/{self.counts[tid]}"
            for tid, bp in sorted(self.active.items())
        )
        return f"TraitState({parts})"
