"""``UnitInstance``: a placed or benched champion plus its live combat state.

Derived stats are ``base at star level + item bonuses + trait bonuses +
status-effect modifiers`` (doc 03 sec 2.3). The result is cached and
invalidated by a version counter that every mutation bumps, so the combat loop
can read stats freely each tick without recomputing them per access.

Trait bonuses are passed *in* rather than computed here: they depend on the
whole board, and taking them as an argument keeps ``unit`` free of an import
cycle with ``traits``.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from engine import economy
from engine.hexgrid import Hex
from engine.items import ItemError, ItemRegistry, item_bonuses
from engine.schema import STAR_LEVELS, ChampionDef, ItemDef
from engine.stats import DerivedStats, StatBonuses, derive_stats

_unit_ids = itertools.count(1)


@dataclass
class StatusEffect:
    """A temporary modifier on a unit.

    ``bonuses`` are folded into derived stats while active. ``stun``, ``root``
    and ``disarm`` gate action selection in the combat loop (doc 01 sec 3.1).
    ``remaining`` counts down in seconds; ``None`` means "until combat ends".

    ``cc_immune`` and ``healing_reduction`` are the two non-stat modifiers that
    more than one effect needs, so they live here rather than being re-derived
    by string-matching ``source`` at each site (doc 99 entry 34.1).
    """

    source: str
    remaining: float | None = None
    bonuses: StatBonuses = field(default_factory=StatBonuses)
    stun: bool = False
    root: bool = False
    disarm: bool = False
    cc_immune: bool = False
    healing_reduction: float = 0.0
    mana_gain_bonus: float = 0.0
    # An untargetable unit is skipped by target selection but still occupies
    # its hex and still takes area damage, matching TFT's behaviour for
    # Edge of Night, Rogue's stealth and Party Animal's repair.
    untargetable: bool = False
    # "Precision": ability damage from this unit can critically strike.
    precision: bool = False

    @property
    def expired(self) -> bool:
        return self.remaining is not None and self.remaining <= 0.0

    def tick(self, dt: float) -> None:
        if self.remaining is not None:
            self.remaining -= dt


@dataclass
class Shield:
    """An absorbing shield. ``damage_type`` ``None`` absorbs everything."""

    amount: float
    remaining: float | None = None
    damage_type: str | None = None
    source: str = ""

    @property
    def expired(self) -> bool:
        return self.amount <= 0.0 or (
            self.remaining is not None and self.remaining <= 0.0
        )


class UnitInstance:
    """One owned champion: its identity, items, and (in combat) its live state."""

    def __init__(
        self,
        champion: ChampionDef,
        star_level: int = 1,
        items: Sequence[ItemDef] = (),
        *,
        team: int = 0,
        position: Hex | None = None,
        registry: ItemRegistry | None = None,
    ) -> None:
        if not 1 <= star_level <= STAR_LEVELS:
            raise ValueError(
                f"star_level must be 1..{STAR_LEVELS}, got {star_level}"
            )
        self.uid: int = next(_unit_ids)
        self.champion = champion
        self._star_level = star_level
        self._items: list[ItemDef] = []
        self.team = team
        self.position = position
        self.registry = registry

        # Live combat state (meaningful only once combat starts).
        self.current_hp: float = 0.0
        self.current_mana: float = 0.0
        self.attack_timer: float = 0.0
        self.cast_timer: float = 0.0
        # Simulation time until which this unit cannot gain mana (set on cast).
        self.mana_locked_until: float = 0.0
        self.target_uid: int | None = None
        self.status_effects: list[StatusEffect] = []
        self.shields: list[Shield] = []
        self.alive: bool = True
        self.counters: dict[str, int] = {}
        self.marks: dict[str, dict[int, int]] = {}
        # Set on units created mid-combat (Zed's clone, Shepherd's summons) so
        # the match knows not to return them to the champion pool.
        self.is_summon: bool = False

        self._version = 0
        self._cached_stats: DerivedStats | None = None
        self._cached_key: int | None = None
        self._trait_bonuses = StatBonuses()
        self._owner_bonuses = StatBonuses()

        for item in items:
            self.equip(item)

    # -- identity ---------------------------------------------------------

    @property
    def star_level(self) -> int:
        return self._star_level

    @star_level.setter
    def star_level(self, value: int) -> None:
        if not 1 <= value <= STAR_LEVELS:
            raise ValueError(f"star_level must be 1..{STAR_LEVELS}, got {value}")
        self._star_level = value
        self._invalidate()

    @property
    def items(self) -> tuple[ItemDef, ...]:
        return tuple(self._items)

    @property
    def name(self) -> str:
        return f"{self.champion.display_name}{'*' * self._star_level}"

    def __repr__(self) -> str:
        return f"<Unit {self.uid} {self.name} team={self.team} at={self.position}>"

    # -- items ------------------------------------------------------------

    def equip(self, item: ItemDef) -> None:
        """Add an item, raising :class:`ItemError` if the loadout would be illegal."""
        if self.registry is not None:
            self.registry.validate_loadout([i.id for i in self._items] + [item.id])
        elif len(self._items) >= 3:
            raise ItemError("a unit may hold at most 3 items")
        self._items.append(item)
        self._invalidate()

    def unequip(self, item_id: str) -> ItemDef:
        for i, item in enumerate(self._items):
            if item.id == item_id:
                self._invalidate()
                return self._items.pop(i)
        raise ItemError(f"{self.name} is not holding {item_id!r}")

    # -- derived stats ----------------------------------------------------

    def set_trait_bonuses(self, bonuses: StatBonuses) -> None:
        """Install the board-level trait bonuses this unit receives."""
        self._trait_bonuses = bonuses
        self._invalidate()

    def set_owner_bonuses(self, bonuses: StatBonuses) -> None:
        """Install bonuses that come from the *owning player*, not the board.

        Augments are the case this exists for: they are player-scoped and
        persist across fights, so they cannot ride on ``set_trait_bonuses``,
        which combat overwrites at the start of every fight from the board's
        own trait state.
        """
        self._owner_bonuses = bonuses
        self._invalidate()

    def _invalidate(self) -> None:
        """Mark cached stats stale. Every mutation that affects stats calls this."""
        self._version += 1

    def derived_stats(self) -> DerivedStats:
        """Final stats, recomputed only when something relevant changed."""
        key = self._version
        if self._cached_key != key or self._cached_stats is None:
            bonuses = item_bonuses(self._items).merged_with(
                self._trait_bonuses, self._owner_bonuses, self._status_bonuses()
            )
            self._cached_stats = derive_stats(
                self.champion.stats, self._star_level, bonuses
            )
            self._cached_key = key
        return self._cached_stats

    def _status_bonuses(self) -> StatBonuses:
        bonuses = StatBonuses()
        for effect in self.status_effects:
            bonuses = bonuses.merged_with(effect.bonuses)
        return bonuses

    # -- combat state -----------------------------------------------------

    def reset_for_combat(self, position: Hex | None = None, team: int | None = None) -> None:
        """Restore full HP/starting mana and clear per-combat state."""
        if position is not None:
            self.position = position
        if team is not None:
            self.team = team
        self.status_effects.clear()
        self.shields.clear()
        # Per-combat firing guards (Sterak's threshold, the interval items'
        # time buckets). Units persist across rounds, so leaving this set
        # populated made every once-per-combat and every interval item work in
        # the first fight of a game and never again (doc 99 entry 34.8).
        self._effect_once = set()
        self.counters = {}
        self.marks = {}
        self._invalidate()
        stats = self.derived_stats()
        self.current_hp = stats.max_health
        self.current_mana = stats.starting_mana
        self.attack_timer = 0.0
        self.cast_timer = 0.0
        self.mana_locked_until = 0.0
        self.target_uid = None
        self.alive = True

    @property
    def shield_amount(self) -> float:
        return sum(s.amount for s in self.shields)

    @property
    def health_fraction(self) -> float:
        max_health = self.derived_stats().max_health
        return self.current_hp / max_health if max_health > 0 else 0.0

    @property
    def is_stunned(self) -> bool:
        return any(e.stun for e in self.status_effects)

    @property
    def is_rooted(self) -> bool:
        return any(e.root or e.stun for e in self.status_effects)

    @property
    def is_disarmed(self) -> bool:
        return any(e.disarm or e.stun for e in self.status_effects)

    @property
    def is_cc_immune(self) -> bool:
        """True while any status grants crowd-control immunity (Quicksilver)."""
        return any(e.cc_immune for e in self.status_effects)

    @property
    def is_untargetable(self) -> bool:
        return any(e.untargetable for e in self.status_effects)

    @property
    def has_precision(self) -> bool:
        """Whether this unit's *abilities* can critically strike.

        Without it `crit_chance` and `crit_damage` are dead stats on every AP
        carry, and Infinity Edge and Jeweled Gauntlet are pure stat sticks
        (doc 99 entry 36.2).
        """
        return any(e.precision for e in self.status_effects)

    # -- per-combat counters ----------------------------------------------
    #
    # "Every third cast", "every N attacks" and stacking marks are the three
    # bookkeeping shapes that recur across the champion abilities. Keeping them
    # on the unit means each ability reads a counter rather than inventing its
    # own storage, and `reset_for_combat` clears them all in one place.

    def bump_counter(self, key: str, amount: int = 1) -> int:
        """Increment a per-combat counter and return its new value."""
        self.counters[key] = self.counters.get(key, 0) + amount
        return self.counters[key]

    def counter(self, key: str) -> int:
        return self.counters.get(key, 0)

    def add_mark(self, key: str, source_uid: int, amount: int = 1) -> int:
        """Add stacks of a mark placed *by* ``source_uid``, returning the total.

        Marks are keyed by their placer so two Kindreds do not share a stack
        count on the same victim.
        """
        marks = self.marks.setdefault(key, {})
        marks[source_uid] = marks.get(source_uid, 0) + amount
        return marks[source_uid]

    def mark_count(self, key: str, source_uid: int) -> int:
        return self.marks.get(key, {}).get(source_uid, 0)

    def clear_marks(self, key: str, source_uid: int) -> None:
        self.marks.get(key, {}).pop(source_uid, None)

    @property
    def mana_gain_bonus(self) -> float:
        """Extra mana from all sources, as a fraction (Adaptive Helm)."""
        return sum(e.mana_gain_bonus for e in self.status_effects)

    @property
    def healing_reduction(self) -> float:
        """Strongest active grievous-wounds effect, as a 0..1 fraction.

        TFT does not stack healing reduction additively -- two sources of
        Grievous Wounds do not add to 66%. The strongest applies.
        """
        return min(
            max((e.healing_reduction for e in self.status_effects), default=0.0), 1.0
        )

    def add_status(self, effect: StatusEffect) -> None:
        self.status_effects.append(effect)
        self._invalidate()

    def tick_statuses(self, dt: float) -> None:
        """Advance status/shield durations and drop the expired ones."""
        changed = False
        for effect in self.status_effects:
            effect.tick(dt)
        if any(e.expired for e in self.status_effects):
            self.status_effects = [e for e in self.status_effects if not e.expired]
            changed = True
        for shield in self.shields:
            if shield.remaining is not None:
                shield.remaining -= dt
        if any(s.expired for s in self.shields):
            self.shields = [s for s in self.shields if not s.expired]
        if changed:
            self._invalidate()

    # -- economy ----------------------------------------------------------

    def sell_value(self) -> int:
        """Gold refunded when sold (doc 01 sec 4)."""
        return economy.sell_value(self.champion.cost, self._star_level)

    @property
    def pool_copies(self) -> int:
        """How many 1-star copies this unit represents (1 / 3 / 9).

        This is what returns to the shared pool when the unit is sold or its
        owner is eliminated.
        """
        return 3 ** (self._star_level - 1)


def make_units(
    champions: Iterable[ChampionDef],
    star_level: int = 1,
    *,
    team: int = 0,
    registry: ItemRegistry | None = None,
) -> list[UnitInstance]:
    """Convenience builder for tests and scripted boards."""
    return [
        UnitInstance(champ, star_level, team=team, registry=registry)
        for champ in champions
    ]
