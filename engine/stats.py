"""Derived-stat model shared by units, items and traits.

Doc 03's layout does not name this module explicitly, but items, traits and
units all need a common vocabulary for "a bag of stat bonuses" and "the final
stats of a unit", and putting it below all three avoids an import cycle
(``unit`` -> ``items``/``traits`` -> ``stats``).

Bonus keys are the same vocabulary as :data:`engine.schema.ITEM_STAT_KEYS`, so
item ``stats`` blocks and trait breakpoint ``params`` both feed in unchanged
and no code needs to know what any particular item or trait is called.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from engine.schema import ITEM_STAT_KEYS, ChampionStats

# Global engine caps, not set-specific balance data. TFT hard-caps attack speed
# at 5.0 attacks/sec; crit chance cannot exceed 100% (real TFT converts the
# excess into bonus crit damage via specific items -- not modelled yet).
ATTACK_SPEED_CAP = 5.0
CRIT_CHANCE_CAP = 1.0

# TFT expresses ability power as a percentage where 100 is the baseline, so a
# unit with no AP items still scales its ability at 1.0x.
BASE_ABILITY_POWER = 100.0


class UnknownStatKey(KeyError):
    """Raised when a bonus names a stat the engine does not model."""


@dataclass
class StatBonuses:
    """Additive stat contributions from items, traits and status effects.

    Everything accumulates additively here; how each key folds into a final
    stat (flat vs. percentage) is decided once in :func:`derive_stats`.
    """

    values: dict[str, float] = field(default_factory=dict)

    def add(self, key: str, amount: float) -> None:
        if key not in ITEM_STAT_KEYS:
            raise UnknownStatKey(
                f"{key!r} is not a modelled stat (valid: {sorted(ITEM_STAT_KEYS)})"
            )
        self.values[key] = self.values.get(key, 0.0) + float(amount)

    def add_all(self, mapping: Mapping[str, float]) -> None:
        for key, amount in mapping.items():
            self.add(key, amount)

    def get(self, key: str) -> float:
        return self.values.get(key, 0.0)

    def merged_with(self, *others: "StatBonuses") -> "StatBonuses":
        out = StatBonuses(dict(self.values))
        for other in others:
            for key, amount in other.values.items():
                out.values[key] = out.values.get(key, 0.0) + amount
        return out

    def __bool__(self) -> bool:
        return any(v for v in self.values.values())


def bonuses_from_params(params: Mapping[str, object]) -> StatBonuses:
    """Extract the flat stat grants from a trait/ability ``params`` block.

    Params whose key names a modelled stat are applied as bonuses directly, so
    a purely statistical trait needs no Python at all. Any other key belongs to
    the entry's ``effect_id`` implementation and is ignored here -- which is
    what lets an unimplemented effect still deliver its stat half instead of
    doing nothing (doc 02 sec 2).
    """
    out = StatBonuses()
    for key, value in params.items():
        if key in ITEM_STAT_KEYS and isinstance(value, (int, float)) and not isinstance(
            value, bool
        ):
            out.add(key, float(value))
    return out


def sum_bonuses(bonuses: Iterable[StatBonuses]) -> StatBonuses:
    total = StatBonuses()
    for b in bonuses:
        for key, amount in b.values.items():
            total.values[key] = total.values.get(key, 0.0) + amount
    return total


@dataclass(frozen=True)
class DerivedStats:
    """A unit's final stats after star level, items, traits and buffs."""

    max_health: float
    armor: float
    magic_resist: float
    attack_damage: float
    attack_speed: float
    attack_range: int
    max_mana: float
    starting_mana: float
    mana_per_attack: float
    mana_regen: float
    crit_chance: float
    crit_damage: float
    ability_power: float
    damage_amp: float
    durability: float
    omnivamp: float

    @property
    def ability_power_multiplier(self) -> float:
        """AP as a scaling multiplier -- 100 AP means 1.0x ability damage."""
        return self.ability_power / BASE_ABILITY_POWER

    @property
    def seconds_per_attack(self) -> float:
        return 1.0 / self.attack_speed


def derive_stats(
    base: ChampionStats, star_level: int, bonuses: StatBonuses | None = None
) -> DerivedStats:
    """Fold ``bonuses`` into a champion's base stats at ``star_level``.

    Percentage keys (``attack_damage_pct``, ``attack_speed_pct``) multiply the
    post-flat value, matching how TFT layers percentage bonuses on top of flat
    ones. Everything else is a flat addition.
    """
    b = bonuses or StatBonuses()

    attack_damage = (base.attack_damage_at(star_level) + b.get("attack_damage")) * (
        1.0 + b.get("attack_damage_pct")
    )
    attack_speed = min(
        base.attack_speed * (1.0 + b.get("attack_speed_pct")), ATTACK_SPEED_CAP
    )
    max_mana = max(base.max_mana, 1.0)
    starting_mana = min(base.starting_mana + b.get("mana"), max_mana)

    return DerivedStats(
        max_health=max(base.health_at(star_level) + b.get("health"), 1.0),
        armor=max(base.armor + b.get("armor"), 0.0),
        magic_resist=max(base.magic_resist + b.get("magic_resist"), 0.0),
        attack_damage=max(attack_damage, 0.0),
        attack_speed=max(attack_speed, 0.01),
        attack_range=max(int(base.attack_range + b.get("attack_range")), 1),
        max_mana=max_mana,
        starting_mana=starting_mana,
        mana_per_attack=max(base.mana_per_attack, 0.0),
        # Riot renders "Mana Regen" as a stat line on Tear and its builds
        # (`%i:TFTManaRegen% +@ManaRegen@ Mana Regen`), so it is a stat here
        # rather than an effect -- eight items would otherwise each need their
        # own hook for the same behaviour (doc 99 entry 34.3).
        mana_regen=max(b.get("mana_regen"), 0.0),
        crit_chance=min(max(base.crit_chance + b.get("crit_chance"), 0.0), CRIT_CHANCE_CAP),
        crit_damage=max(base.crit_damage + b.get("crit_damage"), 1.0),
        ability_power=max(BASE_ABILITY_POWER + b.get("ability_power"), 0.0),
        damage_amp=b.get("damage_amp"),
        durability=min(max(b.get("durability"), 0.0), 0.9),
        omnivamp=max(b.get("omnivamp"), 0.0),
    )
