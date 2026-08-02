"""Frozen dataclasses mirroring the clean JSON schema in doc 02 section 2.

Nothing here knows about specific champions, traits, items or set numbers --
those all arrive as data. The only literals are the schema's own vocabulary
(valid role names, cast modes, item categories, stat keys), which the loader
validates against so a misconfigured fetch script fails loudly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

STAR_LEVELS = 3

# --- schema vocabulary ---------------------------------------------------

# The six team roles from Riot's role revamp. Doc 01 sec 3.2 lists only five;
# "Specialist" ("unique champions" that generate resources their own way) is
# real and Set 17 ships two of them, so leaving it out forced those champions
# into a role whose mana rules do not apply to them (doc 99 entry 9.2).
ROLES: frozenset[str] = frozenset(
    {"Assassin", "Marksman", "Fighter", "Caster", "Tank", "Specialist"}
)
CAST_MODES: frozenset[str] = frozenset({"mana", "cooldown"})
TRAIT_CATEGORIES: frozenset[str] = frozenset({"origin", "class"})
ITEM_CATEGORIES: frozenset[str] = frozenset(
    {"component", "advanced", "artifact", "radiant", "emblem", "consumable"}
)

# How a shop slot picks a champion once its cost tier is rolled.
#
# ``by_copies`` draws a random *copy* from the shared pool, so a champion many
# players have already bought becomes proportionally rarer -- this is what a
# shared physical pool means, and it is what makes contesting a unit matter.
# ``uniform`` reads doc 01 sec 5's "picks uniformly among currently-available
# champions" literally: every champion still in the pool is equally likely
# regardless of how many copies remain.
SHOP_DRAW_WEIGHTINGS: frozenset[str] = frozenset({"by_copies", "uniform"})

# Augment rarity tiers (doc 01 sec 8). Which tier is offered at which round is
# configured in ``config.augment_rounds``, not fixed here.
AUGMENT_TIERS: frozenset[str] = frozenset({"silver", "gold", "prismatic"})

# How the tank damage-mana post-mitigation term treats shields (doc 99 5.4).
DAMAGE_MANA_BASES: frozenset[str] = frozenset({"hp_lost", "after_resists"})

# Stat keys an ItemDef may grant. Flat keys add to the corresponding unit
# stat; ``*_pct`` keys are multiplicative/percentage bonuses (TFT items grant
# attack speed and some AD as a percentage, not a flat value). Validated
# strictly so a typo in a data file is an error, not a silently ignored stat.
ITEM_STAT_KEYS: frozenset[str] = frozenset(
    {
        "health",
        "armor",
        "magic_resist",
        "attack_damage",
        "attack_damage_pct",
        "attack_speed_pct",
        "ability_power",
        "crit_chance",
        "crit_damage",
        "mana",
        "attack_range",
        "damage_amp",
        "durability",
        "omnivamp",
    }
)


def _freeze(mapping: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """Make a nested mapping read-only so frozen dataclasses stay immutable."""
    if not mapping:
        return MappingProxyType({})
    return MappingProxyType(dict(mapping))


@dataclass(frozen=True)
class ChampionStats:
    """Base stats for a champion, before stars, items and traits.

    ``health`` and ``attack_damage`` are per-star tuples of length
    :data:`STAR_LEVELS`; the loader broadcasts a scalar into all three when a
    stat does not scale with star level.
    """

    health: tuple[float, ...]
    armor: float
    magic_resist: float
    attack_damage: tuple[float, ...]
    attack_speed: float
    attack_range: int
    starting_mana: float
    max_mana: float
    mana_per_attack: float
    crit_chance: float
    crit_damage: float

    def health_at(self, star_level: int) -> float:
        return self.health[_star_index(star_level)]

    def attack_damage_at(self, star_level: int) -> float:
        return self.attack_damage[_star_index(star_level)]


def _star_index(star_level: int) -> int:
    if not 1 <= star_level <= STAR_LEVELS:
        raise ValueError(
            f"star_level must be 1..{STAR_LEVELS}, got {star_level}"
        )
    return star_level - 1


@dataclass(frozen=True)
class AbilityDef:
    """A champion's ability (doc 02 sec 2).

    ``effect_id`` keys into ``engine.effects.EFFECTS``. An id with no
    registered implementation logs a warning and no-ops -- the champion still
    loads and auto-attacks normally (doc 02 sec 2, doc 03 sec 2.4).
    """

    name: str
    cast_mode: str
    effect_id: str | None
    cooldown_seconds: float | None = None
    params: Mapping[str, Any] = field(default_factory=dict)

    def param_at(self, key: str, star_level: int, default: Any = None) -> Any:
        """Read an ability param, indexing per-star lists by ``star_level``."""
        if key not in self.params:
            return default
        value = self.params[key]
        if isinstance(value, (list, tuple)):
            return value[_star_index(star_level)]
        return value


@dataclass(frozen=True)
class ChampionDef:
    id: str
    display_name: str
    cost: int
    traits: tuple[str, ...]
    role: str
    stats: ChampionStats
    ability: AbilityDef | None = None


@dataclass(frozen=True)
class TraitBreakpoint:
    count: int
    effect_id: str | None
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TraitDef:
    id: str
    display_name: str
    category: str
    breakpoints: tuple[TraitBreakpoint, ...]

    def active_breakpoint(self, count: int) -> TraitBreakpoint | None:
        """The highest breakpoint met by ``count`` fielded units, if any.

        Breakpoints are stored sorted ascending; per doc 01 sec 6 only the
        highest met tier applies, not the sum of all tiers passed.
        """
        active: TraitBreakpoint | None = None
        for bp in self.breakpoints:
            if count >= bp.count:
                active = bp
            else:
                break
        return active


@dataclass(frozen=True)
class ItemDef:
    """An item.

    ``params`` extends doc 02's schema: it carries magnitudes an effect needs
    that are *not* stats the item grants -- Bramble Vest's reflect, Dragon's
    Claw's magic reduction. Without it those effects have nowhere to read their
    numbers from and cannot be data-driven at all. It mirrors ``AbilityDef``
    and ``TraitBreakpoint``, which already have exactly this field.
    """

    id: str
    display_name: str
    is_component: bool
    category: str
    recipe: tuple[str, ...] = ()
    unique: bool = False
    stats: Mapping[str, float] = field(default_factory=dict)
    params: Mapping[str, Any] = field(default_factory=dict)
    effect_id: str | None = None
    radiant_version_of: str | None = None

    @property
    def effect_values(self) -> Mapping[str, Any]:
        """What an effect implementation reads: ``stats`` overlaid with ``params``.

        Keeping stats visible preserves the existing convention (Spear of
        Shojin's bonus mana is its ``mana`` stat) while letting ``params``
        supply anything that is not a stat.
        """
        return MappingProxyType({**dict(self.stats), **dict(self.params)})


@dataclass(frozen=True)
class RealmOffering:
    """One pick on the carousel / Realm of the Gods: a champion plus a component.

    Doc 01 sec 1: Set 17 replaced the shared-carousel draft with the Realm of
    the Gods, but explicitly directs that "the lowest-HP-picks-first spirit of
    the old carousel is preserved ... model this as its own system". So this is
    a **contested ordered draft** -- one shared line-up, lowest HP picks first
    -- rather than Set 17's literal per-player blessing menu (doc 99 21.1).
    """

    champion_id: str
    component_id: str | None = None


@dataclass(frozen=True)
class RealmSchedule:
    """When the draft happens and what it offers (doc 01 sec 1).

    ``rounds`` and ``cost_tiers`` are parallel: the *n*-th draft offers
    champions of ``cost_tiers[n]``. ``extra_offerings`` is how many more
    offerings than players there are -- real carousels put 9 champions in front
    of 8 players, so the last picker still has a choice rather than a leftover.
    """

    rounds: tuple[tuple[int, int], ...] = ()
    cost_tiers: tuple[int, ...] = ()
    extra_offerings: int = 1

    def __post_init__(self) -> None:
        if len(self.rounds) != len(self.cost_tiers):
            raise ValueError(
                f"realm rounds and cost_tiers must be parallel: "
                f"{len(self.rounds)} rounds against {len(self.cost_tiers)} tiers"
            )
        if self.extra_offerings < 0:
            raise ValueError(
                f"extra_offerings must be >= 0, got {self.extra_offerings}"
            )

    @property
    def enabled(self) -> bool:
        return bool(self.rounds)

    def is_realm_round(self, stage: int, round_: int) -> bool:
        return (stage, round_) in self.rounds

    def cost_tier_at(self, stage: int, round_: int) -> int | None:
        for (s, r), tier in zip(self.rounds, self.cost_tiers, strict=True):
            if (s, r) == (stage, round_):
                return tier
        return None


@dataclass(frozen=True)
class CreepPlacement:
    """One monster and where it stands, in the creep half-board's own frame."""

    creep_id: str
    row: int
    col: int


@dataclass(frozen=True)
class LootOption:
    """One possible drop from a PvE round, chosen by weight.

    Doc 01 sec 5: components come from PvE rounds. Real TFT guarantees a
    creep round drops "1 or more items, or 5 gold", which is expressible as
    two weighted options.
    """

    weight: float
    gold: int = 0
    components: int = 0


@dataclass(frozen=True)
class CreepWave:
    """The monsters fought on one PvE round, and what beating them drops.

    Doc 01 sec 1 allowed stage 1 to be "stubbed" as a fixed sequence; that
    stub is what made PvE an unconditional free win and left the whole item
    system unreachable. A wave is a real board, so a weak player can lose it.
    """

    stage: int
    round: int
    display_name: str
    units: tuple[CreepPlacement, ...]
    loot: tuple[LootOption, ...] = ()

    def pick_loot(self, rng) -> LootOption | None:
        """Weighted choice among the drop options, or ``None`` if there are none."""
        if not self.loot:
            return None
        total = sum(option.weight for option in self.loot)
        if total <= 0:
            return None
        roll = rng.random() * total
        cumulative = 0.0
        for option in self.loot:
            cumulative += option.weight
            if roll < cumulative:
                return option
        return self.loot[-1]


@dataclass(frozen=True)
class AugmentDef:
    """A persistent, player-scoped modifier picked once and kept for the game.

    Doc 01 sec 8: augment effects are bespoke, so each is a small hook rather
    than a special case in the engine. Two halves, exactly as for traits and
    items:

    * ``params`` keys that name a modelled stat (:data:`ITEM_STAT_KEYS`) are
      applied to the player's whole board with no Python at all.
    * ``effect_id`` keys into :data:`engine.augments.AUGMENT_EFFECTS` for
      anything that is not a stat -- econ tweaks, free items, extra board
      slots. An unimplemented id warns once and no-ops, so the stat half of a
      partially-implemented augment still works (doc 02 sec 2).
    """

    id: str
    display_name: str
    tier: str
    effect_id: str | None = None
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AugmentSchedule:
    """When augments are offered and from which tier (doc 01 sec 8).

    Doc 01 sec 9 flags the exact reveal rounds as unverified against the live
    patch, so they are data. ``rounds`` and ``tiers`` are parallel: the *n*-th
    reveal offers ``choices`` augments of ``tiers[n]``.
    """

    rounds: tuple[tuple[int, int], ...] = ()
    tiers: tuple[str, ...] = ()
    choices: int = 3

    def __post_init__(self) -> None:
        if len(self.rounds) != len(self.tiers):
            raise ValueError(
                f"augment rounds and tiers must be parallel: {len(self.rounds)} "
                f"rounds against {len(self.tiers)} tiers"
            )

    @property
    def enabled(self) -> bool:
        return bool(self.rounds)

    def tier_at(self, stage: int, round_: int) -> str | None:
        """The tier offered at this round, or ``None`` if it is not a reveal."""
        for (s, r), tier in zip(self.rounds, self.tiers, strict=True):
            if (s, r) == (stage, round_):
                return tier
        return None


@dataclass(frozen=True)
class CombatConfig:
    """Tick-simulation tunables (doc 01 sec 3).

    Several of these are approximations that doc 01 sec 9 explicitly flags as
    unverified against the live client (movement speed, the armour curve
    coefficient, the stall-breaker ramp); they live in data so tuning them is
    a config edit, not a code change.
    """

    tick_seconds: float
    movement_hexes_per_second: float
    projectile_hexes_per_second: float
    max_duration_seconds: float
    sudden_death_start_seconds: float
    sudden_death_damage_pct_per_second: float
    armor_mitigation_constant: float
    damage_mana_roles: frozenset[str]
    damage_mana_pre_mitigation_pct: float
    damage_mana_post_mitigation_pct: float
    damage_mana_cap_per_instance: float
    # Which quantity the post-mitigation term is measured against when a
    # shield absorbs part of a hit. Doc 01 sec 3.2 equates "post-mitigation"
    # with "actual HP lost", which is unambiguous only when no shield is
    # involved; sources do not settle the shielded case, so both readings are
    # implemented (doc 99 entry 5.4).
    #
    #   "hp_lost"        -- a shield suppresses the 3% term (default)
    #   "after_resists"  -- the 3% term ignores shields, counting damage that
    #                       got past armour/MR whether or not HP was lost
    damage_mana_post_mitigation_basis: str = "hp_lost"
    # Per-role perks from Riot's role revamp beyond mana-per-attack: Casters
    # also regenerate mana over time, Fighters carry innate omnivamp
    # (doc 99 entry 9.2).
    role_mana_per_second: Mapping[str, float] = field(default_factory=dict)
    role_omnivamp: Mapping[str, float] = field(default_factory=dict)

    @property
    def seconds_per_hex(self) -> float:
        return 1.0 / self.movement_hexes_per_second

    def generates_mana_from_damage(self, role: str) -> bool:
        """Doc 01 sec 3.2: only Tanks build mana from damage taken."""
        return role in self.damage_mana_roles

    def mana_per_second(self, role: str) -> float:
        """Passive mana regeneration for a role (Casters gain 2/s)."""
        return float(self.role_mana_per_second.get(role, 0.0))

    def omnivamp_for(self, role: str) -> float:
        """Innate omnivamp for a role (Fighters heal for 10% of damage dealt)."""
        return float(self.role_omnivamp.get(role, 0.0))


@dataclass(frozen=True)
class RoundStructure:
    """The stage/round skeleton of a match (doc 01 sec 1).

    Doc 01 describes stage 1 as PvE-only and later stages as PvP with
    "periodic PvE rounds" without pinning the exact schedule, so which rounds
    are PvE is configured here rather than assumed in code.
    """

    players: int
    rounds_per_stage: int
    stage_one_rounds: int
    pve_rounds_per_stage: frozenset[int]
    max_stages: int

    def rounds_in_stage(self, stage: int) -> int:
        return self.stage_one_rounds if stage == 1 else self.rounds_per_stage

    def is_pve(self, stage: int, round_: int) -> bool:
        """Stage 1 is entirely PvE; later stages have periodic creep rounds."""
        return stage == 1 or round_ in self.pve_rounds_per_stage


@dataclass(frozen=True)
class GameConfig:
    """Set/patch-specific tunables loaded from ``data/config.json``.

    Everything here changes between sets or patches, so it is data rather than
    code (doc 03 sec 2.7/2.8). Tables flagged in doc 01 sec 9 as unverified are
    listed in ``unverified`` and echoed by the loader.
    """

    shop_odds: Mapping[int, tuple[float, ...]]
    pool_sizes: Mapping[int, int]
    xp_to_next_level: Mapping[int, int]
    max_level: int
    passive_xp_per_round: int
    xp_purchase_gold: int
    xp_purchase_amount: int
    base_income: int
    income_ramp: Mapping[str, int]
    interest_per_gold: int
    interest_cap: int
    streak_bonus: tuple[tuple[int, int], ...]
    pvp_win_gold: int
    reroll_cost: int
    shop_slots: int
    shop_draw_weighting: str
    bench_size: int
    max_items_per_unit: int
    starting_gold: int
    starting_hp: int
    role_mana_per_attack: Mapping[str, float]
    stage_base_damage: Mapping[int, int]
    star_damage_multiplier: Mapping[int, int]
    combat: CombatConfig
    round_structure: RoundStructure
    augments: AugmentSchedule = field(default_factory=AugmentSchedule)
    realm: RealmSchedule = field(default_factory=RealmSchedule)
    unverified: tuple[str, ...] = ()

    def board_size_for_level(self, level: int) -> int:
        """Units fieldable at ``level`` -- in TFT this equals the level."""
        return level

    def shop_odds_for_level(self, level: int) -> tuple[float, ...]:
        if level not in self.shop_odds:
            raise KeyError(f"no shop odds configured for level {level}")
        return self.shop_odds[level]


@dataclass(frozen=True)
class DataVersion:
    set: int
    patch: str
    fetched_at: str
    source: str = "unknown"


@dataclass(frozen=True)
class GameData:
    """Everything the engine needs, keyed by id."""

    champions: Mapping[str, ChampionDef]
    traits: Mapping[str, TraitDef]
    items: Mapping[str, ItemDef]
    config: GameConfig
    version: DataVersion
    augments: Mapping[str, AugmentDef] = field(default_factory=dict)
    # Monsters are kept *out* of ``champions`` deliberately: ``SharedPool`` and
    # the shop are both built from that mapping, so a creep listed there would
    # become purchasable.
    creeps: Mapping[str, ChampionDef] = field(default_factory=dict)
    creep_waves: tuple[CreepWave, ...] = ()

    def wave_for(self, stage: int, round_: int) -> CreepWave | None:
        """The wave fought at this round.

        Rounds past the last defined wave reuse it, so a long game does not
        silently fall back to a free win -- which is the bug this whole system
        exists to fix.
        """
        if not self.creep_waves:
            return None
        exact = [w for w in self.creep_waves if (w.stage, w.round) == (stage, round_)]
        if exact:
            return exact[0]
        earlier = [w for w in self.creep_waves if (w.stage, w.round) <= (stage, round_)]
        return max(earlier, key=lambda w: (w.stage, w.round)) if earlier else None

    def augments_of_tier(self, tier: str) -> tuple[AugmentDef, ...]:
        return tuple(
            a for a in sorted(self.augments.values(), key=lambda a: a.id)
            if a.tier == tier
        )

    def champions_by_cost(self, cost: int) -> tuple[ChampionDef, ...]:
        return tuple(c for c in self.champions.values() if c.cost == cost)

    @property
    def cost_tiers(self) -> tuple[int, ...]:
        return tuple(sorted(self.config.pool_sizes))
