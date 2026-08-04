"""Load and validate ``data/*.json`` into the :mod:`engine.schema` dataclasses.

Validation is deliberately strict and *loud*: every problem across every file
is collected and raised together as a single :class:`DataValidationError`
listing all of them (doc 03 sec 2.2). Nothing is silently dropped or coerced,
so a misconfigured fetch script fails visibly instead of producing a subtly
wrong dataset.

Unimplemented ``effect_id`` values are *not* an error -- those are expected
during incremental ability coverage and are handled at runtime by
``engine.effects`` (doc 02 sec 2).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

# Imported for their registration side effects: each module populates an
# effect registry at import time, and the loader's coverage warnings are only
# accurate once every implementation has registered itself.
from engine import abilities as _abilities  # noqa: F401
from engine import trait_effects as _trait_effects  # noqa: F401
from engine.items import EMBLEM_EFFECT_PREFIX, emblem_trait_id
from engine.schema import (
    AUGMENT_TIERS,
    CAST_MODES,
    DAMAGE_MANA_BASES,
    ITEM_CATEGORIES,
    ITEM_STAT_KEYS,
    ROLES,
    SHOP_DRAW_WEIGHTINGS,
    STAR_LEVELS,
    TRAIT_CATEGORIES,
    AbilityDef,
    AugmentDef,
    AugmentSchedule,
    ChampionDef,
    ChampionStats,
    CombatConfig,
    CreepPlacement,
    CreepWave,
    DataVersion,
    GameConfig,
    GameData,
    ItemDef,
    LootOption,
    RealmSchedule,
    RoundStructure,
    TraitBreakpoint,
    TraitDef,
)
from engine.stats import bonuses_from_params

log = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_CHAMPION_KEYS = {"id", "display_name", "cost", "traits", "role", "stats", "ability"}
_STAT_KEYS = {
    "health",
    "armor",
    "magic_resist",
    "attack_damage",
    "attack_speed",
    "attack_range",
    "starting_mana",
    "max_mana",
    "mana_per_attack",
    "crit_chance",
    "crit_damage",
}
_ABILITY_KEYS = {"name", "cast_mode", "cooldown_seconds", "effect_id", "params"}
_TRAIT_KEYS = {"id", "display_name", "category", "breakpoints"}
_AUGMENT_KEYS = {"id", "display_name", "tier", "effect_id", "params"}
_BREAKPOINT_KEYS = {"count", "effect_id", "params"}
_ITEM_KEYS = {
    "id",
    "display_name",
    "is_component",
    "recipe",
    "unique",
    "stats",
    "params",
    "effect_id",
    "radiant_version_of",
    "category",
}
# Per-star stats: a scalar is broadcast across all star levels for champions
# whose value does not scale (doc 02 sec 2).
_PER_STAR_STATS = ("health", "attack_damage")


class DataValidationError(ValueError):
    """Raised with the full list of problems found while loading data."""

    def __init__(self, problems: Sequence[str], data_dir: Path) -> None:
        self.problems = list(problems)
        detail = "\n".join(f"  - {p}" for p in self.problems)
        super().__init__(
            f"{len(self.problems)} problem(s) validating game data in "
            f"{data_dir}:\n{detail}"
        )


class _Collector:
    """Accumulates validation problems so all of them surface at once."""

    def __init__(self) -> None:
        self.problems: list[str] = []

    def add(self, where: str, message: str) -> None:
        self.problems.append(f"{where}: {message}")

    def require_keys(
        self, where: str, raw: Mapping[str, Any], required: set[str], allowed: set[str]
    ) -> bool:
        """Check for missing required keys and reject unknown ones."""
        ok = True
        for key in sorted(required - set(raw)):
            self.add(where, f"missing required field {key!r}")
            ok = False
        for key in sorted(set(raw) - allowed):
            self.add(where, f"unknown field {key!r}")
            ok = False
        return ok

    def number(
        self,
        where: str,
        raw: Mapping[str, Any],
        key: str,
        *,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> float | None:
        value = raw.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            self.add(where, f"{key} must be a number, got {value!r}")
            return None
        if minimum is not None and value < minimum:
            self.add(where, f"{key} must be >= {minimum}, got {value}")
            return None
        if maximum is not None and value > maximum:
            self.add(where, f"{key} must be <= {maximum}, got {value}")
            return None
        return float(value)

    def per_star(
        self, where: str, raw: Mapping[str, Any], key: str
    ) -> tuple[float, ...] | None:
        """Read a per-star stat, broadcasting a scalar across all star levels."""
        value = raw.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return (float(value),) * STAR_LEVELS
        if not isinstance(value, list):
            self.add(
                where,
                f"{key} must be a number or a list of {STAR_LEVELS} numbers, "
                f"got {value!r}",
            )
            return None
        if len(value) != STAR_LEVELS:
            self.add(
                where,
                f"{key} must have exactly {STAR_LEVELS} entries "
                f"(one per star level), got {len(value)}",
            )
            return None
        out: list[float] = []
        for i, entry in enumerate(value):
            if isinstance(entry, bool) or not isinstance(entry, (int, float)):
                self.add(where, f"{key}[{i}] must be a number, got {entry!r}")
                return None
            if entry < 0:
                self.add(where, f"{key}[{i}] must be >= 0, got {entry}")
                return None
            out.append(float(entry))
        return tuple(out)


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"required data file not found: {path}")
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise DataValidationError(
            [f"{path.name}: invalid JSON -- {exc}"], path.parent
        ) from exc


def _expect_list(raw: Any, path: Path) -> list[Any]:
    if not isinstance(raw, list):
        raise DataValidationError(
            [f"{path.name}: top level must be a JSON list, got {type(raw).__name__}"],
            path.parent,
        )
    return raw


# --- per-file parsing ----------------------------------------------------


def _parse_ability(where: str, raw: Any, c: _Collector) -> AbilityDef | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        c.add(where, f"ability must be an object or null, got {type(raw).__name__}")
        return None

    c.require_keys(
        where, raw, {"name", "cast_mode", "effect_id"}, _ABILITY_KEYS
    )
    cast_mode = raw.get("cast_mode")
    if cast_mode not in CAST_MODES:
        c.add(where, f"ability.cast_mode must be one of {sorted(CAST_MODES)}, got {cast_mode!r}")
        return None

    cooldown = raw.get("cooldown_seconds")
    if cast_mode == "cooldown":
        if not isinstance(cooldown, (int, float)) or isinstance(cooldown, bool) or cooldown <= 0:
            c.add(where, f"ability.cooldown_seconds must be a positive number when cast_mode is 'cooldown', got {cooldown!r}")
            return None
    elif cooldown is not None:
        c.add(where, "ability.cooldown_seconds must be null when cast_mode is 'mana'")
        return None

    params = raw.get("params") or {}
    if not isinstance(params, dict):
        c.add(where, f"ability.params must be an object, got {type(params).__name__}")
        return None
    for key, value in params.items():
        if isinstance(value, list) and len(value) != STAR_LEVELS:
            c.add(
                where,
                f"ability.params[{key!r}] is a per-star list and must have "
                f"{STAR_LEVELS} entries, got {len(value)}",
            )

    effect_id = raw.get("effect_id")
    if effect_id is not None and not isinstance(effect_id, str):
        c.add(where, f"ability.effect_id must be a string or null, got {effect_id!r}")
        return None

    name = raw.get("name")
    if not isinstance(name, str) or not name:
        c.add(where, f"ability.name must be a non-empty string, got {name!r}")
        return None

    return AbilityDef(
        name=name,
        cast_mode=cast_mode,
        effect_id=effect_id,
        cooldown_seconds=float(cooldown) if cooldown is not None else None,
        params=MappingProxyType(dict(params)),
    )


def _parse_champion(
    raw: Any,
    index: int,
    c: _Collector,
    role_mana: Mapping[str, float],
    *,
    source: str = "champions.json",
    is_creep: bool = False,
    is_summon: bool = False,
) -> ChampionDef | None:
    """Parse a champion, or a PvE monster when ``is_creep``.

    Monsters share the champion shape but legitimately break two of its rules:
    they belong to no trait, and they never cast (Riot ships them with
    ``mana: 0/0`` and a placeholder "Nothing To See Here!" ability). Those two
    checks are relaxed rather than removed from the champion path, so a real
    champion missing traits or mana is still an error.
    """
    where = f"{source}[{index}]"
    if not isinstance(raw, dict):
        c.add(where, f"entry must be an object, got {type(raw).__name__}")
        return None

    champ_id = raw.get("id")
    if isinstance(champ_id, str) and champ_id:
        where = f"{source}[{champ_id}]"
    else:
        c.add(where, f"id must be a non-empty string, got {champ_id!r}")
        return None

    allowed = _CHAMPION_KEYS | ({"summon_role"} if is_summon else set())
    c.require_keys(where, raw, _CHAMPION_KEYS - {"ability"}, allowed)

    display_name = raw.get("display_name")
    if not isinstance(display_name, str) or not display_name:
        c.add(where, f"display_name must be a non-empty string, got {display_name!r}")

    cost = raw.get("cost")
    # A summon is never bought, so cost 0 is correct for it rather than a typo.
    floor = 0 if is_summon else 1
    if isinstance(cost, bool) or not isinstance(cost, int) or cost < floor:
        c.add(where, f"cost must be an integer >= {floor}, got {cost!r}")
        cost = None

    traits = raw.get("traits")
    traits_ok = isinstance(traits, list) and all(
        isinstance(t, str) and t for t in traits
    )
    if is_creep or is_summon:
        # A monster or summon with traits would silently join trait counts --
        # Shepherd's own summons would raise the Shepherd breakpoint.
        if not traits_ok or traits:
            kind = "creep" if is_creep else "summon"
            c.add(where, f"a {kind} must declare an empty trait list, got {traits!r}")
    elif not traits_ok or not traits:
        c.add(where, f"traits must be a non-empty list of trait ids, got {traits!r}")
        traits = None
    elif len(set(traits)) != len(traits):
        c.add(where, f"traits contains duplicates: {traits}")
        traits = None

    role = raw.get("role")
    if role not in ROLES:
        c.add(where, f"role must be one of {sorted(ROLES)}, got {role!r}")
        role = None

    stats = _parse_stats(
        where, raw.get("stats"), c, role, role_mana, is_creep=is_creep or is_summon
    )
    ability = _parse_ability(where, raw.get("ability"), c)

    if None in (cost, traits, role, stats) or not isinstance(display_name, str):
        return None
    return ChampionDef(
        id=champ_id,
        display_name=display_name,
        cost=cost,
        traits=tuple(traits),
        role=role,
        stats=stats,
        ability=ability,
        summon_role=raw.get("summon_role") if is_summon else None,
    )


def _parse_stats(
    where: str,
    raw: Any,
    c: _Collector,
    role: str | None,
    role_mana: Mapping[str, float],
    *,
    is_creep: bool = False,
) -> ChampionStats | None:
    if not isinstance(raw, dict):
        c.add(where, f"stats must be an object, got {type(raw).__name__}")
        return None

    # mana_per_attack is role-derived (doc 01 sec 3.2) and may be omitted;
    # everything else must be present explicitly.
    required = _STAT_KEYS - {"mana_per_attack"}
    c.require_keys(f"{where}.stats", raw, required, _STAT_KEYS)

    values: dict[str, Any] = {}
    for key in _PER_STAR_STATS:
        values[key] = c.per_star(f"{where}.stats", raw, key)

    values["armor"] = c.number(f"{where}.stats", raw, "armor", minimum=0)
    values["magic_resist"] = c.number(f"{where}.stats", raw, "magic_resist", minimum=0)
    values["attack_speed"] = c.number(f"{where}.stats", raw, "attack_speed", minimum=0.01)
    values["starting_mana"] = c.number(f"{where}.stats", raw, "starting_mana", minimum=0)
    # A creep never casts, so max_mana 0 is correct for it rather than a typo.
    values["max_mana"] = c.number(
        f"{where}.stats", raw, "max_mana", minimum=0 if is_creep else 1
    )
    values["crit_chance"] = c.number(f"{where}.stats", raw, "crit_chance", minimum=0, maximum=1)
    values["crit_damage"] = c.number(f"{where}.stats", raw, "crit_damage", minimum=1)

    attack_range = raw.get("attack_range")
    if isinstance(attack_range, bool) or not isinstance(attack_range, int) or attack_range < 1:
        c.add(f"{where}.stats", f"attack_range must be a positive integer (hexes), got {attack_range!r}")
        attack_range = None

    if "mana_per_attack" in raw:
        mana_per_attack = c.number(f"{where}.stats", raw, "mana_per_attack", minimum=0)
    elif role in role_mana:
        mana_per_attack = float(role_mana[role])
    else:
        # Role was already reported invalid; avoid a duplicate complaint.
        mana_per_attack = None if role is None else 0.0

    if any(v is None for v in values.values()) or attack_range is None or mana_per_attack is None:
        return None
    if values["starting_mana"] > values["max_mana"]:
        c.add(f"{where}.stats", f"starting_mana ({values['starting_mana']}) exceeds max_mana ({values['max_mana']})")
        return None

    return ChampionStats(
        health=values["health"],
        armor=values["armor"],
        magic_resist=values["magic_resist"],
        attack_damage=values["attack_damage"],
        attack_speed=values["attack_speed"],
        attack_range=attack_range,
        starting_mana=values["starting_mana"],
        max_mana=values["max_mana"],
        mana_per_attack=mana_per_attack,
        crit_chance=values["crit_chance"],
        crit_damage=values["crit_damage"],
    )


def _parse_trait(raw: Any, index: int, c: _Collector) -> TraitDef | None:
    where = f"traits.json[{index}]"
    if not isinstance(raw, dict):
        c.add(where, f"entry must be an object, got {type(raw).__name__}")
        return None

    trait_id = raw.get("id")
    if isinstance(trait_id, str) and trait_id:
        where = f"traits.json[{trait_id}]"
    else:
        c.add(where, f"id must be a non-empty string, got {trait_id!r}")
        return None

    c.require_keys(where, raw, _TRAIT_KEYS, _TRAIT_KEYS)

    display_name = raw.get("display_name")
    if not isinstance(display_name, str) or not display_name:
        c.add(where, f"display_name must be a non-empty string, got {display_name!r}")
        return None

    category = raw.get("category")
    if category not in TRAIT_CATEGORIES:
        c.add(where, f"category must be one of {sorted(TRAIT_CATEGORIES)}, got {category!r}")
        return None

    raw_bps = raw.get("breakpoints")
    if not isinstance(raw_bps, list) or not raw_bps:
        c.add(where, f"breakpoints must be a non-empty list, got {raw_bps!r}")
        return None

    breakpoints: list[TraitBreakpoint] = []
    seen_counts: set[int] = set()
    for i, raw_bp in enumerate(raw_bps):
        bp_where = f"{where}.breakpoints[{i}]"
        if not isinstance(raw_bp, dict):
            c.add(bp_where, f"must be an object, got {type(raw_bp).__name__}")
            return None
        c.require_keys(bp_where, raw_bp, {"count", "effect_id"}, _BREAKPOINT_KEYS)
        count = raw_bp.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            c.add(bp_where, f"count must be a positive integer, got {count!r}")
            return None
        if count in seen_counts:
            c.add(bp_where, f"duplicate breakpoint count {count}")
            return None
        seen_counts.add(count)
        effect_id = raw_bp.get("effect_id")
        if effect_id is not None and not isinstance(effect_id, str):
            c.add(bp_where, f"effect_id must be a string or null, got {effect_id!r}")
            return None
        params = raw_bp.get("params") or {}
        if not isinstance(params, dict):
            c.add(bp_where, f"params must be an object, got {type(params).__name__}")
            return None
        breakpoints.append(
            TraitBreakpoint(count=count, effect_id=effect_id, params=MappingProxyType(dict(params)))
        )

    # Sorted so TraitDef.active_breakpoint can scan ascending and stop early.
    breakpoints.sort(key=lambda bp: bp.count)
    return TraitDef(
        id=trait_id,
        display_name=display_name,
        category=category,
        breakpoints=tuple(breakpoints),
    )


def _parse_item(raw: Any, index: int, c: _Collector) -> ItemDef | None:
    where = f"items.json[{index}]"
    if not isinstance(raw, dict):
        c.add(where, f"entry must be an object, got {type(raw).__name__}")
        return None

    item_id = raw.get("id")
    if isinstance(item_id, str) and item_id:
        where = f"items.json[{item_id}]"
    else:
        c.add(where, f"id must be a non-empty string, got {item_id!r}")
        return None

    c.require_keys(
        where, raw, {"id", "display_name", "is_component", "category"}, _ITEM_KEYS
    )

    display_name = raw.get("display_name")
    if not isinstance(display_name, str) or not display_name:
        c.add(where, f"display_name must be a non-empty string, got {display_name!r}")
        return None

    is_component = raw.get("is_component")
    if not isinstance(is_component, bool):
        c.add(where, f"is_component must be a boolean, got {is_component!r}")
        return None

    category = raw.get("category")
    if category not in ITEM_CATEGORIES:
        c.add(where, f"category must be one of {sorted(ITEM_CATEGORIES)}, got {category!r}")
        return None
    if is_component != (category == "component"):
        c.add(where, f"is_component={is_component} contradicts category={category!r}")
        return None

    recipe = raw.get("recipe") or ()
    if not isinstance(recipe, (list, tuple)) or not all(isinstance(r, str) and r for r in recipe):
        c.add(where, f"recipe must be a list of component ids or null, got {recipe!r}")
        return None
    if is_component and recipe:
        c.add(where, "component items must have an empty recipe")
        return None
    if recipe and len(recipe) != 2:
        c.add(where, f"recipe must combine exactly 2 components (doc 01 sec 5), got {len(recipe)}")
        return None

    unique = raw.get("unique", False)
    if not isinstance(unique, bool):
        c.add(where, f"unique must be a boolean, got {unique!r}")
        return None

    stats = raw.get("stats") or {}
    if not isinstance(stats, dict):
        c.add(where, f"stats must be an object, got {type(stats).__name__}")
        return None
    parsed_stats: dict[str, float] = {}
    for key, value in stats.items():
        if key not in ITEM_STAT_KEYS:
            c.add(where, f"unknown stat key {key!r} (valid: {sorted(ITEM_STAT_KEYS)})")
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            c.add(where, f"stats[{key!r}] must be a number, got {value!r}")
            continue
        parsed_stats[key] = float(value)

    params = raw.get("params") or {}
    if not isinstance(params, dict):
        c.add(where, f"params must be an object, got {type(params).__name__}")
        return None
    if params and raw.get("effect_id") is None:
        c.add(where, "params are set but effect_id is null, so nothing would read them")
        return None

    effect_id = raw.get("effect_id")
    if effect_id is not None and not isinstance(effect_id, str):
        c.add(where, f"effect_id must be a string or null, got {effect_id!r}")
        return None
    if not parsed_stats and effect_id is None:
        c.add(where, "item grants neither stats nor an effect_id")
        return None

    radiant_of = raw.get("radiant_version_of")
    if radiant_of is not None and not isinstance(radiant_of, str):
        c.add(where, f"radiant_version_of must be a string or null, got {radiant_of!r}")
        return None
    if radiant_of is not None and category != "radiant":
        c.add(where, f"radiant_version_of is set but category is {category!r}, expected 'radiant'")
        return None
    if radiant_of is None and category == "radiant":
        c.add(where, "radiant items must set radiant_version_of to the base item id")
        return None

    return ItemDef(
        id=item_id,
        display_name=display_name,
        is_component=is_component,
        category=category,
        recipe=tuple(recipe),
        unique=unique,
        stats=MappingProxyType(parsed_stats),
        params=MappingProxyType(dict(params)),
        effect_id=effect_id,
        radiant_version_of=radiant_of,
    )


def _parse_augment(raw: Any, index: int, c: _Collector) -> AugmentDef | None:
    where = f"augments.json[{index}]"
    if not isinstance(raw, dict):
        c.add(where, f"entry must be an object, got {type(raw).__name__}")
        return None

    augment_id = raw.get("id")
    if isinstance(augment_id, str) and augment_id:
        where = f"augments.json[{augment_id}]"
    else:
        c.add(where, f"id must be a non-empty string, got {augment_id!r}")
        return None

    c.require_keys(where, raw, {"id", "display_name", "tier"}, _AUGMENT_KEYS)

    display_name = raw.get("display_name")
    if not isinstance(display_name, str) or not display_name:
        c.add(where, f"display_name must be a non-empty string, got {display_name!r}")
        return None

    tier = raw.get("tier")
    if tier not in AUGMENT_TIERS:
        c.add(where, f"tier must be one of {sorted(AUGMENT_TIERS)}, got {tier!r}")
        return None

    effect_id = raw.get("effect_id")
    if effect_id is not None and not isinstance(effect_id, str):
        c.add(where, f"effect_id must be a string or null, got {effect_id!r}")
        return None

    params = raw.get("params") or {}
    if not isinstance(params, dict):
        c.add(where, f"params must be an object, got {type(params).__name__}")
        return None

    # An augment that grants no stats and has no hook does nothing at all --
    # almost certainly a data mistake rather than an intentional blank.
    if not effect_id and not bonuses_from_params(params).values:
        c.add(where, "augment grants neither a modelled stat nor an effect_id")
        return None

    return AugmentDef(
        id=augment_id,
        display_name=display_name,
        tier=tier,
        effect_id=effect_id,
        params=MappingProxyType(dict(params)),
    )


def _parse_creep_wave(raw: Any, index: int, creeps: Mapping[str, Any], c: _Collector):
    where = f"creeps.json.waves[{index}]"
    if not isinstance(raw, dict):
        c.add(where, f"entry must be an object, got {type(raw).__name__}")
        return None

    c.require_keys(
        where, raw, {"stage", "round", "units"},
        {"stage", "round", "display_name", "units", "loot"},
    )
    stage, round_ = raw.get("stage"), raw.get("round")
    for name, value in (("stage", stage), ("round", round_)):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            c.add(where, f"{name} must be a positive integer, got {value!r}")
            return None

    raw_units = raw.get("units")
    if not isinstance(raw_units, list) or not raw_units:
        c.add(where, "units must be a non-empty list")
        return None

    placements: list[CreepPlacement] = []
    for i, unit in enumerate(raw_units):
        if not isinstance(unit, dict):
            c.add(f"{where}.units[{i}]", "must be an object")
            return None
        creep_id = unit.get("creep_id")
        if creep_id not in creeps:
            c.add(f"{where}.units[{i}]", f"unknown creep_id {creep_id!r}")
            return None
        row, col = unit.get("row"), unit.get("col")
        for name, value in (("row", row), ("col", col)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                c.add(f"{where}.units[{i}]", f"{name} must be a non-negative integer")
                return None
        placements.append(CreepPlacement(creep_id=creep_id, row=row, col=col))

    seen = {(p.row, p.col) for p in placements}
    if len(seen) != len(placements):
        c.add(where, "two monsters occupy the same hex")
        return None

    options: list[LootOption] = []
    for i, entry in enumerate(raw.get("loot") or []):
        if not isinstance(entry, dict):
            c.add(f"{where}.loot[{i}]", "must be an object")
            return None
        weight = entry.get("weight", 1)
        gold = entry.get("gold", 0)
        components = entry.get("components", 0)
        if not isinstance(weight, (int, float)) or isinstance(weight, bool) or weight <= 0:
            c.add(f"{where}.loot[{i}]", f"weight must be a positive number, got {weight!r}")
            return None
        for name, value in (("gold", gold), ("components", components)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                c.add(f"{where}.loot[{i}]", f"{name} must be a non-negative integer")
                return None
        if not gold and not components:
            c.add(f"{where}.loot[{i}]", "drops neither gold nor components")
            return None
        options.append(LootOption(weight=float(weight), gold=gold, components=components))

    return CreepWave(
        stage=stage,
        round=round_,
        display_name=raw.get("display_name") or f"wave {stage}-{round_}",
        units=tuple(placements),
        loot=tuple(options),
    )


def _load_creeps(data_dir: Path, config: GameConfig, c: _Collector):
    """Load ``creeps.json``. Absent means PvE stays a free win (the old stub)."""
    path = data_dir / "creeps.json"
    if not path.exists():
        log.info(
            "no creeps.json in %s -- PvE rounds resolve as free wins and drop "
            "no loot, so no items will ever enter play", data_dir,
        )
        return {}, ()

    raw = _read_json(path)
    if not isinstance(raw, dict):
        c.add("creeps.json", f"top level must be an object, got {type(raw).__name__}")
        return {}, ()

    parsed = [
        _parse_champion(
            entry, i, c, config.role_mana_per_attack,
            source="creeps.json.monsters", is_creep=True,
        )
        for i, entry in enumerate(raw.get("monsters") or [])
    ]
    creeps = _index_by_id([m for m in parsed if m], "creeps.json.monsters", c)

    waves = [
        _parse_creep_wave(entry, i, creeps, c)
        for i, entry in enumerate(raw.get("waves") or [])
    ]
    waves = [w for w in waves if w is not None]

    scheduled = {(w.stage, w.round) for w in waves}
    duplicates = len(waves) - len(scheduled)
    if duplicates:
        c.add("creeps.json.waves", f"{duplicates} duplicate stage/round entries")

    structure = config.round_structure
    for stage, round_ in sorted(scheduled):
        if not structure.is_pve(stage, round_):
            c.add(
                "creeps.json.waves",
                f"wave scheduled at {stage}-{round_}, which round_structure "
                "does not mark as a PvE round",
            )
    return creeps, tuple(sorted(waves, key=lambda w: (w.stage, w.round)))


def _load_summons(data_dir: Path, config: GameConfig, c: _Collector):
    """Load ``summons.json``. Absent means summoning traits simply summon nothing."""
    path = data_dir / "summons.json"
    if not path.exists():
        log.info(
            "no summons.json in %s -- traits and abilities that summon units "
            "will find none and no-op", data_dir,
        )
        return {}

    raw = _read_json(path)
    if not isinstance(raw, list):
        c.add("summons.json", f"top level must be a list, got {type(raw).__name__}")
        return {}

    parsed = [
        _parse_champion(
            entry, i, c, config.role_mana_per_attack,
            source="summons.json", is_summon=True,
        )
        for i, entry in enumerate(raw)
    ]
    return _index_by_id([s for s in parsed if s], "summons.json", c)


def _parse_realm_schedule(raw: Any, c: _Collector, cost_tiers: set[int]) -> RealmSchedule:
    """Parse ``config.realm``. Absent or empty disables the draft."""
    where = "config.json[realm]"
    if raw is None:
        return RealmSchedule()
    if not isinstance(raw, dict):
        c.add(where, f"must be an object, got {type(raw).__name__}")
        return RealmSchedule()

    rounds_raw = raw.get("rounds") or []
    tiers_raw = raw.get("cost_tiers") or []
    if not isinstance(rounds_raw, list) or not isinstance(tiers_raw, list):
        c.add(where, "rounds and cost_tiers must both be lists")
        return RealmSchedule()

    rounds: list[tuple[int, int]] = []
    for entry in rounds_raw:
        if (
            not isinstance(entry, (list, tuple))
            or len(entry) != 2
            or not all(isinstance(v, int) and not isinstance(v, bool) for v in entry)
        ):
            c.add(where, f"each round must be a [stage, round] integer pair, got {entry!r}")
            continue
        rounds.append((int(entry[0]), int(entry[1])))

    for tier in tiers_raw:
        if not isinstance(tier, int) or isinstance(tier, bool) or tier not in cost_tiers:
            c.add(where, f"cost_tier {tier!r} is not one of the pool's tiers {sorted(cost_tiers)}")

    if len(rounds) != len(tiers_raw):
        c.add(
            where,
            f"rounds and cost_tiers must be parallel: {len(rounds)} rounds "
            f"against {len(tiers_raw)} tiers",
        )
        return RealmSchedule()

    extra = raw.get("extra_offerings", 1)
    if not isinstance(extra, int) or isinstance(extra, bool) or extra < 0:
        c.add(where, f"extra_offerings must be a non-negative integer, got {extra!r}")
        return RealmSchedule()

    return RealmSchedule(
        rounds=tuple(rounds), cost_tiers=tuple(tiers_raw), extra_offerings=extra
    )


def _parse_augment_schedule(raw: Any, c: _Collector) -> AugmentSchedule:
    """Parse ``config.augments``. Absent or empty means the feature is off."""
    where = "config.json[augments]"
    if raw is None:
        return AugmentSchedule()
    if not isinstance(raw, dict):
        c.add(where, f"must be an object, got {type(raw).__name__}")
        return AugmentSchedule()

    rounds_raw = raw.get("rounds") or []
    tiers_raw = raw.get("tiers") or []
    if not isinstance(rounds_raw, list) or not isinstance(tiers_raw, list):
        c.add(where, "rounds and tiers must both be lists")
        return AugmentSchedule()

    rounds: list[tuple[int, int]] = []
    for entry in rounds_raw:
        if (
            not isinstance(entry, (list, tuple))
            or len(entry) != 2
            or not all(isinstance(v, int) and not isinstance(v, bool) for v in entry)
        ):
            c.add(where, f"each round must be a [stage, round] integer pair, got {entry!r}")
            continue
        rounds.append((int(entry[0]), int(entry[1])))

    for tier in tiers_raw:
        if tier not in AUGMENT_TIERS:
            c.add(where, f"tier must be one of {sorted(AUGMENT_TIERS)}, got {tier!r}")

    if len(rounds) != len(tiers_raw):
        c.add(
            where,
            f"rounds and tiers must be parallel: {len(rounds)} rounds against "
            f"{len(tiers_raw)} tiers",
        )
        return AugmentSchedule()

    choices = raw.get("choices", 3)
    if not isinstance(choices, int) or isinstance(choices, bool) or choices < 1:
        c.add(where, f"choices must be a positive integer, got {choices!r}")
        return AugmentSchedule()

    return AugmentSchedule(
        rounds=tuple(rounds), tiers=tuple(tiers_raw), choices=choices
    )


def _parse_config(raw: Any, c: _Collector) -> GameConfig | None:
    if not isinstance(raw, dict):
        c.add("config.json", f"top level must be an object, got {type(raw).__name__}")
        return None

    def int_map(key: str, value_name: str) -> dict[int, int] | None:
        section = raw.get(key)
        if not isinstance(section, dict) or not section:
            c.add("config.json", f"{key} must be a non-empty object")
            return None
        out: dict[int, int] = {}
        for k, v in section.items():
            try:
                ik = int(k)
            except (TypeError, ValueError):
                c.add("config.json", f"{key} key {k!r} must be an integer")
                return None
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                c.add("config.json", f"{key}[{k}] {value_name} must be a non-negative integer, got {v!r}")
                return None
            out[ik] = v
        return out

    def scalar(key: str, minimum: int | None = None) -> int | None:
        v = raw.get(key)
        if isinstance(v, bool) or not isinstance(v, int):
            c.add("config.json", f"{key} must be an integer, got {v!r}")
            return None
        if minimum is not None and v < minimum:
            c.add("config.json", f"{key} must be >= {minimum}, got {v}")
            return None
        return v

    shop_odds_raw = raw.get("shop_odds")
    shop_odds: dict[int, tuple[float, ...]] = {}
    if not isinstance(shop_odds_raw, dict) or not shop_odds_raw:
        c.add("config.json", "shop_odds must be a non-empty object keyed by player level")
        shop_odds_raw = {}
    for level_key, row in shop_odds_raw.items():
        try:
            level = int(level_key)
        except (TypeError, ValueError):
            c.add("config.json", f"shop_odds key {level_key!r} must be an integer level")
            continue
        if not isinstance(row, list) or not all(
            isinstance(p, (int, float)) and not isinstance(p, bool) and p >= 0 for p in row
        ):
            c.add("config.json", f"shop_odds[{level}] must be a list of non-negative numbers")
            continue
        total = sum(row)
        if abs(total - 1.0) > 1e-6:
            c.add("config.json", f"shop_odds[{level}] must sum to 1.0, got {total}")
            continue
        shop_odds[level] = tuple(float(p) for p in row)

    pool_sizes = int_map("pool_sizes", "copy count")
    xp_to_next = int_map("xp_to_next_level", "xp")
    stage_damage = int_map("stage_base_damage", "damage")

    if shop_odds and pool_sizes:
        tiers = len(pool_sizes)
        for level, row in shop_odds.items():
            if len(row) != tiers:
                c.add(
                    "config.json",
                    f"shop_odds[{level}] has {len(row)} entries but pool_sizes "
                    f"defines {tiers} cost tiers",
                )

    role_mana_raw = raw.get("role_mana_per_attack")
    role_mana: dict[str, float] = {}
    if not isinstance(role_mana_raw, dict) or set(role_mana_raw) != set(ROLES):
        c.add("config.json", f"role_mana_per_attack must map every role {sorted(ROLES)} to a mana value")
    else:
        for role, value in role_mana_raw.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                c.add("config.json", f"role_mana_per_attack[{role!r}] must be a non-negative number")
            else:
                role_mana[role] = float(value)

    income_ramp_raw = raw.get("income_ramp")
    income_ramp: dict[str, int] = {}
    if not isinstance(income_ramp_raw, dict):
        c.add("config.json", "income_ramp must be an object mapping round ids to gold")
    else:
        for round_id, gold in income_ramp_raw.items():
            if isinstance(gold, bool) or not isinstance(gold, int) or gold < 0:
                c.add("config.json", f"income_ramp[{round_id!r}] must be a non-negative integer")
            else:
                income_ramp[str(round_id)] = gold

    streak_raw = raw.get("streak_bonus")
    streak: list[tuple[int, int]] = []
    if not isinstance(streak_raw, list) or not streak_raw:
        c.add("config.json", "streak_bonus must be a non-empty list of [streak_length, gold] pairs")
    else:
        for entry in streak_raw:
            if (
                not isinstance(entry, list)
                or len(entry) != 2
                or any(isinstance(v, bool) or not isinstance(v, int) for v in entry)
            ):
                c.add("config.json", f"streak_bonus entry {entry!r} must be a [streak_length, gold] integer pair")
                continue
            streak.append((entry[0], entry[1]))
        streak.sort()

    scalars = {
        "max_level": scalar("max_level", 1),
        "passive_xp_per_round": scalar("passive_xp_per_round", 0),
        "xp_purchase_gold": scalar("xp_purchase_gold", 1),
        "xp_purchase_amount": scalar("xp_purchase_amount", 1),
        "base_income": scalar("base_income", 0),
        "interest_per_gold": scalar("interest_per_gold", 1),
        "interest_cap": scalar("interest_cap", 0),
        "pvp_win_gold": scalar("pvp_win_gold", 0),
        "reroll_cost": scalar("reroll_cost", 0),
        "shop_slots": scalar("shop_slots", 1),
        "bench_size": scalar("bench_size", 1),
        "max_items_per_unit": scalar("max_items_per_unit", 1),
        "starting_gold": scalar("starting_gold", 0),
        "starting_hp": scalar("starting_hp", 1),
        "damage_per_surviving_unit": scalar("damage_per_surviving_unit", 0),
        "minimum_round_damage": scalar("minimum_round_damage", 0),
    }

    combat = _parse_combat_config(raw.get("combat"), c)
    round_structure = _parse_round_structure(raw.get("round_structure"), c)

    weighting = raw.get("shop_draw_weighting")
    if weighting not in SHOP_DRAW_WEIGHTINGS:
        c.add(
            "config.json",
            f"shop_draw_weighting must be one of {sorted(SHOP_DRAW_WEIGHTINGS)}, "
            f"got {weighting!r}",
        )
        weighting = None

    unverified = raw.get("unverified") or []
    if not isinstance(unverified, list) or not all(isinstance(u, str) for u in unverified):
        c.add("config.json", "unverified must be a list of strings")
        unverified = []

    if (
        not shop_odds
        or pool_sizes is None
        or xp_to_next is None
        or stage_damage is None
        or combat is None
        or round_structure is None
        or weighting is None
        or not role_mana
        or any(v is None for v in scalars.values())
    ):
        return None

    if scalars["max_level"] is not None:
        missing_levels = [
            lvl for lvl in range(1, scalars["max_level"] + 1) if lvl not in shop_odds
        ]
        if missing_levels:
            c.add("config.json", f"shop_odds missing rows for level(s) {missing_levels}")
            return None

    return GameConfig(
        combat=combat,
        round_structure=round_structure,
        augments=_parse_augment_schedule(raw.get("augments"), c),
        realm=_parse_realm_schedule(raw.get("realm"), c, set(pool_sizes)),
        shop_draw_weighting=weighting,
        shop_odds=MappingProxyType(shop_odds),
        pool_sizes=MappingProxyType(pool_sizes),
        xp_to_next_level=MappingProxyType(xp_to_next),
        streak_bonus=tuple(streak),
        role_mana_per_attack=MappingProxyType(role_mana),
        income_ramp=MappingProxyType(income_ramp),
        stage_base_damage=MappingProxyType(stage_damage),
        unverified=tuple(unverified),
        **scalars,
    )


_COMBAT_POSITIVE_KEYS = (
    "tick_seconds",
    "movement_hexes_per_second",
    "projectile_hexes_per_second",
    "max_duration_seconds",
    "armor_mitigation_constant",
    "damage_mana_cap_per_instance",
)
_COMBAT_NON_NEGATIVE_KEYS = (
    "sudden_death_start_seconds",
    "sudden_death_damage_pct_per_second",
    "damage_mana_pre_mitigation_pct",
    "damage_mana_post_mitigation_pct",
    "mana_lock_seconds",
    "overtime_attack_speed_pct",
    "overtime_damage_amp",
    "overtime_healing_reduction",
)


def _parse_combat_config(raw: Any, c: _Collector) -> CombatConfig | None:
    where = "config.json.combat"
    if not isinstance(raw, dict):
        c.add(where, f"must be an object, got {type(raw).__name__}")
        return None

    required = set(_COMBAT_POSITIVE_KEYS) | set(_COMBAT_NON_NEGATIVE_KEYS) | {
        "damage_mana_roles"
    }
    # Optional so an existing config (and the frozen starter fixture) keeps
    # loading without edits; it defaults to the documented reading.
    optional = required | {
        "damage_mana_post_mitigation_basis",
        "role_mana_per_second",
        "role_omnivamp",
    }
    c.require_keys(where, raw, required, optional)

    values: dict[str, float] = {}
    for key in _COMBAT_POSITIVE_KEYS:
        v = c.number(where, raw, key, minimum=1e-9)
        if v is not None:
            values[key] = v
    for key in _COMBAT_NON_NEGATIVE_KEYS:
        v = c.number(where, raw, key, minimum=0.0)
        if v is not None:
            values[key] = v

    roles_raw = raw.get("damage_mana_roles")
    if not isinstance(roles_raw, list) or not all(r in ROLES for r in roles_raw):
        c.add(where, f"damage_mana_roles must be a list of roles from {sorted(ROLES)}, got {roles_raw!r}")
        return None

    if len(values) != len(_COMBAT_POSITIVE_KEYS) + len(_COMBAT_NON_NEGATIVE_KEYS):
        return None

    if values["sudden_death_start_seconds"] > values["max_duration_seconds"]:
        c.add(
            where,
            "sudden_death_start_seconds must not exceed max_duration_seconds, "
            "or the stall-breaker never fires",
        )
        return None

    role_maps: dict[str, dict[str, float]] = {}
    for key in ("role_mana_per_second", "role_omnivamp"):
        entry = raw.get(key) or {}
        if not isinstance(entry, dict):
            c.add(where, f"{key} must be an object, got {type(entry).__name__}")
            return None
        parsed: dict[str, float] = {}
        for role, value in entry.items():
            if role not in ROLES:
                c.add(where, f"{key} names unknown role {role!r}")
                return None
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                c.add(where, f"{key}[{role!r}] must be a non-negative number, got {value!r}")
                return None
            parsed[role] = float(value)
        role_maps[key] = parsed

    basis = raw.get("damage_mana_post_mitigation_basis", "hp_lost")
    if basis not in DAMAGE_MANA_BASES:
        c.add(
            where,
            "damage_mana_post_mitigation_basis must be one of "
            f"{sorted(DAMAGE_MANA_BASES)}, got {basis!r}",
        )
        return None

    return CombatConfig(
        damage_mana_roles=frozenset(roles_raw),
        damage_mana_post_mitigation_basis=basis,
        role_mana_per_second=MappingProxyType(role_maps["role_mana_per_second"]),
        role_omnivamp=MappingProxyType(role_maps["role_omnivamp"]),
        **values,
    )


_ROUND_STRUCTURE_KEYS = {
    "players",
    "rounds_per_stage",
    "stage_one_rounds",
    "pve_rounds_per_stage",
    "max_stages",
}


def _parse_round_structure(raw: Any, c: _Collector) -> RoundStructure | None:
    where = "config.json.round_structure"
    if not isinstance(raw, dict):
        c.add(where, f"must be an object, got {type(raw).__name__}")
        return None
    c.require_keys(where, raw, _ROUND_STRUCTURE_KEYS, _ROUND_STRUCTURE_KEYS)

    values: dict[str, int] = {}
    for key in ("players", "rounds_per_stage", "stage_one_rounds", "max_stages"):
        value = raw.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            c.add(where, f"{key} must be a positive integer, got {value!r}")
        else:
            values[key] = value

    pve_raw = raw.get("pve_rounds_per_stage")
    if not isinstance(pve_raw, list) or not all(
        isinstance(r, int) and not isinstance(r, bool) and r >= 1 for r in pve_raw
    ):
        c.add(where, f"pve_rounds_per_stage must be a list of positive round numbers, got {pve_raw!r}")
        return None

    if len(values) != 4:
        return None
    if values["stage_one_rounds"] > values["rounds_per_stage"]:
        c.add(where, "stage_one_rounds cannot exceed rounds_per_stage")
        return None
    out_of_range = [r for r in pve_raw if r > values["rounds_per_stage"]]
    if out_of_range:
        c.add(where, f"pve_rounds_per_stage entries {out_of_range} exceed rounds_per_stage")
        return None
    if len(pve_raw) >= values["rounds_per_stage"]:
        c.add(where, "every round cannot be a PvE round -- players would never fight")
        return None

    return RoundStructure(pve_rounds_per_stage=frozenset(pve_raw), **values)


def _parse_version(raw: Any, c: _Collector) -> DataVersion | None:
    if not isinstance(raw, dict):
        c.add("VERSION.json", f"top level must be an object, got {type(raw).__name__}")
        return None
    set_number = raw.get("set")
    patch = raw.get("patch")
    fetched_at = raw.get("fetched_at")
    if isinstance(set_number, bool) or not isinstance(set_number, int):
        c.add("VERSION.json", f"set must be an integer, got {set_number!r}")
        return None
    for key, value in (("patch", patch), ("fetched_at", fetched_at)):
        if not isinstance(value, str) or not value:
            c.add("VERSION.json", f"{key} must be a non-empty string, got {value!r}")
            return None
    return DataVersion(
        set=set_number,
        patch=patch,
        fetched_at=fetched_at,
        source=raw.get("source", "unknown"),
    )


# --- cross-file validation ----------------------------------------------


def _cross_validate(
    champions: Mapping[str, ChampionDef],
    traits: Mapping[str, TraitDef],
    items: Mapping[str, ItemDef],
    config: GameConfig,
    c: _Collector,
) -> None:
    for champ in champions.values():
        for trait_id in champ.traits:
            if trait_id not in traits:
                c.add(f"champions.json[{champ.id}]", f"references unknown trait {trait_id!r}")
        if champ.cost not in config.pool_sizes:
            c.add(
                f"champions.json[{champ.id}]",
                f"cost {champ.cost} has no pool size configured "
                f"(known tiers: {sorted(config.pool_sizes)})",
            )

    for item in items.values():
        for component_id in item.recipe:
            component = items.get(component_id)
            if component is None:
                c.add(f"items.json[{item.id}]", f"recipe references unknown item {component_id!r}")
            elif not component.is_component:
                c.add(
                    f"items.json[{item.id}]",
                    f"recipe references {component_id!r}, which is not a component",
                )
        if item.radiant_version_of is not None and item.radiant_version_of not in items:
            c.add(
                f"items.json[{item.id}]",
                f"radiant_version_of references unknown item {item.radiant_version_of!r}",
            )
        if item.category == "emblem":
            trait_id = emblem_trait_id(item)
            if trait_id is None:
                c.add(
                    f"items.json[{item.id}]",
                    "emblem items must set effect_id to "
                    f"'{EMBLEM_EFFECT_PREFIX}<TraitId>' so the granted trait is "
                    f"discoverable, got {item.effect_id!r}",
                )
            elif trait_id not in traits:
                c.add(
                    f"items.json[{item.id}]",
                    f"grants unknown trait {trait_id!r}",
                )

    # Two advanced items sharing a recipe would make combine() ambiguous.
    by_recipe: dict[tuple[str, ...], list[str]] = {}
    for item in items.values():
        if item.recipe and item.category != "radiant":
            by_recipe.setdefault(tuple(sorted(item.recipe)), []).append(item.id)
    for recipe, owners in sorted(by_recipe.items()):
        if len(owners) > 1:
            c.add("items.json", f"recipe {list(recipe)} produces multiple items: {sorted(owners)}")

    # Every cost tier the shop can roll needs at least one champion to draw.
    rollable = {
        i + 1
        for row in config.shop_odds.values()
        for i, p in enumerate(row)
        if p > 0
    }
    for tier in sorted(rollable):
        if not any(champ.cost == tier for champ in champions.values()):
            c.add(
                "champions.json",
                f"shop odds can roll cost tier {tier} but no champion has that cost",
            )


def _index_by_id(defs: list[Any], filename: str, c: _Collector) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for d in defs:
        if d.id in out:
            c.add(filename, f"duplicate id {d.id!r}")
            continue
        out[d.id] = d
    return out


def load_all(data_dir: Path | str = DEFAULT_DATA_DIR) -> GameData:
    """Load and validate every data file in ``data_dir``.

    Raises :class:`DataValidationError` listing *all* problems found, or
    :class:`FileNotFoundError` if a required file is missing.
    """
    data_dir = Path(data_dir)
    c = _Collector()

    config = _parse_config(_read_json(data_dir / "config.json"), c)
    version = _parse_version(_read_json(data_dir / "VERSION.json"), c)
    if config is None:
        raise DataValidationError(c.problems, data_dir)

    raw_traits = _expect_list(_read_json(data_dir / "traits.json"), data_dir / "traits.json")
    raw_champs = _expect_list(_read_json(data_dir / "champions.json"), data_dir / "champions.json")
    raw_items = _expect_list(_read_json(data_dir / "items.json"), data_dir / "items.json")

    # Entries that fail to parse are dropped here but have already recorded a
    # problem, so the load still fails -- with every problem listed, not just
    # the first.
    parsed_traits = [_parse_trait(raw, i, c) for i, raw in enumerate(raw_traits)]
    parsed_champs = [
        _parse_champion(raw, i, c, config.role_mana_per_attack)
        for i, raw in enumerate(raw_champs)
    ]
    parsed_items = [_parse_item(raw, i, c) for i, raw in enumerate(raw_items)]

    traits = _index_by_id([t for t in parsed_traits if t], "traits.json", c)
    champions = _index_by_id([ch for ch in parsed_champs if ch], "champions.json", c)
    items = _index_by_id([it for it in parsed_items if it], "items.json", c)
    augments = _load_augments(data_dir, config, c)
    creeps, creep_waves = _load_creeps(data_dir, config, c)
    summons = _load_summons(data_dir, config, c)

    _cross_validate(champions, traits, items, config, c)

    if c.problems or version is None:
        raise DataValidationError(c.problems, data_dir)

    if config.unverified:
        log.warning(
            "Loaded set %s patch %s with %d unverified constant table(s): %s "
            "(see doc 01 sec 9)",
            version.set,
            version.patch,
            len(config.unverified),
            ", ".join(config.unverified),
        )
    log.info(
        "Loaded %d champions, %d traits, %d items, %d augments, %d creeps "
        "in %d waves (set %s, patch %s)",
        len(champions),
        len(traits),
        len(items),
        len(augments),
        len(creeps),
        len(creep_waves),
        version.set,
        version.patch,
    )

    return GameData(
        champions=MappingProxyType(champions),
        traits=MappingProxyType(traits),
        items=MappingProxyType(items),
        config=config,
        version=version,
        augments=MappingProxyType(augments),
        creeps=MappingProxyType(creeps),
        creep_waves=creep_waves,
        summons=MappingProxyType(summons),
    )


def _load_augments(
    data_dir: Path, config: GameConfig, c: _Collector
) -> dict[str, AugmentDef]:
    """Load ``augments.json``, which is required only when augments are enabled.

    Making the file conditionally required rather than always required means a
    dataset that predates the feature still loads, while a config that *asks*
    for augment rounds cannot silently run without any augments to offer.
    """
    path = data_dir / "augments.json"
    if not path.exists():
        if config.augments.enabled:
            c.add(
                "augments.json",
                "config.augments schedules augment rounds but the file is missing",
            )
        return {}

    raw_augments = _expect_list(_read_json(path), path)
    parsed = [_parse_augment(raw, i, c) for i, raw in enumerate(raw_augments)]
    augments = _index_by_id([a for a in parsed if a], "augments.json", c)

    # Every scheduled tier must actually have augments to offer, or that reveal
    # round silently does nothing.
    available = {a.tier for a in augments.values()}
    for tier in set(config.augments.tiers) - available:
        c.add("augments.json", f"config schedules tier {tier!r} but no augment has it")
    return augments
