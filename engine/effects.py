"""Registry mapping data-file ``effect_id`` values to Python implementations.

The data files are declarative: they say *which* hook implements a behaviour,
never what the behaviour is (doc 02 sec 2). This module is where those hooks
live.

An ``effect_id`` with no registered implementation logs a warning **once** and
no-ops -- it must never crash, so partial ability coverage still runs full
matches (doc 02 sec 2, doc 03 sec 2.4). Note that a trait or item whose
``params``/``stats`` name modelled stats still delivers those stats even when
its ``effect_id`` is unimplemented, because stat application happens in
:mod:`engine.stats`, independently of this registry.

Milestone 2 ships the registry and the miss-tracking; the damage/shield/CC
primitives and the ability implementations arrive with ``combat.py``.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Callable, TypeVar

log = logging.getLogger(__name__)


class EffectTrigger(str, Enum):
    """When an effect fires (doc 03 sec 2.6)."""

    ON_CAST = "on_cast"
    ON_ATTACK = "on_attack"
    ON_HIT = "on_hit"
    ON_DAMAGED = "on_damaged"
    ON_DEATH = "on_death"
    ON_COMBAT_START = "on_combat_start"
    PERIODIC = "periodic"


# effect_id -> implementation. Populated by @register at import time.
EFFECTS: dict[str, Callable] = {}
# effect_id -> the trigger it is wired to.
EFFECT_TRIGGERS: dict[str, EffectTrigger] = {}

# effect_ids already reported as missing, so the warning fires once per id
# rather than once per tick.
_reported_missing: set[str] = set()

F = TypeVar("F", bound=Callable)


def register(
    effect_id: str, trigger: EffectTrigger = EffectTrigger.ON_CAST
) -> Callable[[F], F]:
    """Register an implementation for ``effect_id``."""

    def decorator(fn: F) -> F:
        if effect_id in EFFECTS:
            raise ValueError(f"effect_id {effect_id!r} is already registered")
        EFFECTS[effect_id] = fn
        EFFECT_TRIGGERS[effect_id] = trigger
        return fn

    return decorator


def resolve(effect_id: str | None) -> Callable | None:
    """Look up an effect, warning once if it is not implemented yet.

    Returns ``None`` for both "no effect declared" and "declared but not
    implemented"; callers simply skip.
    """
    if effect_id is None:
        return None
    fn = EFFECTS.get(effect_id)
    if fn is None and effect_id not in _reported_missing:
        _reported_missing.add(effect_id)
        log.warning(
            "effect_id %r has no implementation -- skipping it. Stats granted "
            "by the same entry still apply; only its special behaviour is "
            "missing.",
            effect_id,
        )
    return fn


def is_implemented(effect_id: str | None) -> bool:
    return effect_id is not None and effect_id in EFFECTS


def missing_effect_ids(declared: set[str]) -> set[str]:
    """Which of ``declared`` have no implementation -- for coverage reporting."""
    return {e for e in declared if e and e not in EFFECTS}


def reset_missing_warnings() -> None:
    """Clear the warn-once memo. For tests."""
    _reported_missing.clear()


@register("no_effect")
def _no_effect(*_args, **_kwargs) -> None:
    """Explicit no-op, for data entries that intentionally do nothing.

    Lets a component like Spatula declare "no behaviour" without tripping the
    unimplemented-effect warning.
    """
    return None


# =========================================================================
# Ability effects
#
# Every implementation below is generic: all magnitudes come from the data
# file's ``params``, so these hooks are reusable across champions and no
# per-champion numbers live in code (doc 03 module responsibilities).
# Damage/shield/heal/CC all go through the simulator's primitives, which keeps
# mitigation logic in exactly one place (doc 01 sec 3.3, doc 03 sec 2.4).
# =========================================================================


def _ability_damage(ctx, key: str = "damage", ratio_key: str = "ap_ratio") -> float:
    """Flat ability damage scaled by the caster's AP, per the data's ratio."""
    base = ctx.number(key)
    ratio = ctx.number(ratio_key, 1.0)
    return base * (1.0 + (ctx.source.derived_stats().ability_power_multiplier - 1.0) * ratio)


@register("single_target_magic_damage")
def single_target_magic_damage(ctx) -> None:
    from engine.combat import DamageType

    if ctx.target is None:
        return
    ctx.sim.deal_damage(
        ctx.source,
        ctx.target,
        _ability_damage(ctx),
        DamageType.MAGIC,
        source_label="ability",
    )


@register("single_target_physical_damage")
def single_target_physical_damage(ctx) -> None:
    from engine.combat import DamageType

    if ctx.target is None:
        return
    damage = ctx.source.derived_stats().attack_damage * ctx.number("ad_ratio", 1.0)
    ctx.sim.deal_damage(
        ctx.source, ctx.target, damage, DamageType.PHYSICAL, source_label="ability"
    )


@register("single_target_physical_damage_heal")
def single_target_physical_damage_heal(ctx) -> None:
    from engine.combat import DamageType

    if ctx.target is None:
        return
    damage = ctx.source.derived_stats().attack_damage * ctx.number("ad_ratio", 1.0)
    dealt = ctx.sim.deal_damage(
        ctx.source, ctx.target, damage, DamageType.PHYSICAL, source_label="ability"
    )
    ctx.sim.heal(ctx.source, dealt * ctx.number("heal_ratio"), source_label="ability")


@register("single_target_magic_damage_stun")
def single_target_magic_damage_stun(ctx) -> None:
    from engine.combat import DamageType

    if ctx.target is None:
        return
    ctx.sim.deal_damage(
        ctx.source,
        ctx.target,
        _ability_damage(ctx),
        DamageType.MAGIC,
        source_label="ability",
    )
    duration = ctx.number("stun_duration")
    if duration > 0 and ctx.target.alive:
        ctx.sim.apply_stun(ctx.target, duration, source_label="ability")


@register("splash_magic_damage")
def splash_magic_damage(ctx) -> None:
    """Damage the target and every enemy within ``splash_radius`` hexes."""
    from engine.combat import DamageType

    if ctx.target is None:
        return
    damage = _ability_damage(ctx)
    radius = int(ctx.number("splash_radius", 1))
    hit = ctx.sim.units_within(ctx.target.position, radius, team=ctx.target.team)
    for enemy in hit:
        ctx.sim.deal_damage(
            ctx.source, enemy, damage, DamageType.MAGIC, source_label="ability_splash"
        )


@register("line_magic_damage")
def line_magic_damage(ctx) -> None:
    """Damage every enemy on the line from the caster through its target."""
    from engine.combat import DamageType
    from engine.hexgrid import line

    if ctx.target is None:
        return
    damage = _ability_damage(ctx)
    struck = set(line(ctx.source.position, ctx.target.position))
    for enemy in ctx.sim.enemies_of(ctx.source):
        if enemy.position in struck:
            ctx.sim.deal_damage(
                ctx.source, enemy, damage, DamageType.MAGIC, source_label="ability_line"
            )


@register("shield_self")
def shield_self(ctx) -> None:
    ctx.sim.apply_shield(
        ctx.source,
        ctx.number("shield"),
        ctx.number("duration") or None,
        source_label="ability",
    )


@register("shield_lowest_health_ally")
def shield_lowest_health_ally(ctx) -> None:
    allies = ctx.sim.allies_of(ctx.source)
    if not allies:
        return
    # uid tie-break keeps the choice deterministic.
    weakest = min(allies, key=lambda u: (u.health_fraction, u.uid))
    ctx.sim.apply_shield(
        weakest,
        ctx.number("shield"),
        ctx.number("duration") or None,
        source_label="ability",
    )


@register("jinx_get_excited")
def jinx_get_excited(ctx) -> None:
    """Damage plus a temporary attack-speed buff on the caster."""
    from engine.combat import DamageType
    from engine.unit import StatusEffect

    if ctx.target is not None:
        ctx.sim.deal_damage(
            ctx.source,
            ctx.target,
            _ability_damage(ctx),
            DamageType.MAGIC,
            source_label="ability",
        )
    bonus = ctx.number("attack_speed_bonus")
    if bonus > 0:
        from engine.stats import StatBonuses

        ctx.sim.apply_status(
            ctx.source,
            StatusEffect(
                "jinx_get_excited",
                remaining=ctx.number("duration") or None,
                bonuses=StatBonuses({"attack_speed_pct": bonus}),
            ),
        )


# =========================================================================
# Item effects
#
# Items have no ``params`` in the doc 02 schema, so an item effect's magnitude
# is read from the item's own ``stats`` block (passed in as ``ctx.params``).
# That keeps item numbers in the data file rather than in code.
# =========================================================================


@register("spear_of_shojin_bonus_mana_on_attack", EffectTrigger.ON_ATTACK)
def spear_of_shojin_bonus_mana_on_attack(ctx) -> None:
    """Bonus mana per attack, on top of the role-based base (doc 01 sec 3.2)."""
    ctx.sim.grant_mana(ctx.source, ctx.number("mana"), reason="spear_of_shojin")


@register("bramble_vest_thorns", EffectTrigger.ON_DAMAGED)
def bramble_vest_thorns(ctx) -> None:
    """Reflect flat magic damage back at a melee attacker.

    The magnitude lives in the item's ``params`` rather than its ``stats``,
    since "damage reflected" is not a stat the wearer gains -- this is the
    class of effect that ``ItemDef.params`` exists to support.
    """
    from engine.combat import DamageType

    attacker = ctx.target
    reflect = ctx.number("reflect")
    if attacker is None or reflect <= 0 or not attacker.alive:
        return
    if attacker.derived_stats().attack_range > int(ctx.number("max_attacker_range", 1)):
        return
    ctx.sim.deal_damage(
        ctx.source,
        attacker,
        reflect,
        DamageType.MAGIC,
        source_label="bramble_vest",
        trigger_effects=False,
    )


@register("guinsoos_stacking_attack_speed", EffectTrigger.ON_ATTACK)
def guinsoos_stacking_attack_speed(ctx) -> None:
    """Permanent attack-speed stack each attack, sized by the item's own bonus."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    step = ctx.number("attack_speed_pct")
    if step <= 0:
        return
    ctx.source.add_status(
        StatusEffect(
            "guinsoos_stack",
            remaining=None,
            bonuses=StatBonuses({"attack_speed_pct": step}),
        )
    )
