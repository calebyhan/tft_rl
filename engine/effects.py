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
    # Fires on every living enemy of a unit that just cast, with the mana it
    # spent in ``ctx.amount``. Ionic Spark is the case this exists for.
    ON_ENEMY_CAST = "on_enemy_cast"
    # Unlike every other trigger, a DAMAGE_MODIFIER implementation *returns* a
    # multiplier applied to the damage being dealt (``None`` or 0 meaning "no
    # opinion"). It fires from the attacker's side inside ``deal_damage``, which
    # is the only point where the victim is known and the number is not yet
    # final -- conditional amps like Giant Slayer's "vs Tanks" cannot be
    # expressed as a stat, because the condition depends on who is being hit.
    DAMAGE_MODIFIER = "damage_modifier"


# effect_id -> every (trigger, implementation) registered for it.
#
# One effect_id may have several hooks on different triggers, because real
# items routinely combine them: Sunfire Cape grants max health at combat start
# *and* burns on an interval, and an item carries exactly one effect_id to
# express both. Keying only by effect_id -- as this module originally did --
# forced such items into a single trigger and silently dropped the other half
# (doc 99 entry 34.7).
EFFECT_HOOKS: dict[str, list[tuple[EffectTrigger, Callable]]] = {}

# effect_id -> primary implementation / trigger, i.e. the first one registered.
# Kept because abilities are single-trigger and read through these.
EFFECTS: dict[str, Callable] = {}
EFFECT_TRIGGERS: dict[str, EffectTrigger] = {}

# effect_ids already reported as missing, so the warning fires once per id
# rather than once per tick.
_reported_missing: set[str] = set()

F = TypeVar("F", bound=Callable)


def register(
    effect_id: str, trigger: EffectTrigger = EffectTrigger.ON_CAST
) -> Callable[[F], F]:
    """Register an implementation for ``effect_id`` on ``trigger``.

    Registering the same effect_id twice on *different* triggers is how a
    multi-part item is expressed. Registering it twice on the *same* trigger is
    a mistake -- almost certainly a copy-paste -- and raises.
    """

    def decorator(fn: F) -> F:
        hooks = EFFECT_HOOKS.setdefault(effect_id, [])
        if any(existing is trigger for existing, _ in hooks):
            raise ValueError(
                f"effect_id {effect_id!r} already has a {trigger.value} hook"
            )
        hooks.append((trigger, fn))
        EFFECTS.setdefault(effect_id, fn)
        EFFECT_TRIGGERS.setdefault(effect_id, trigger)
        return fn

    return decorator


def hooks_for(effect_id: str | None, trigger: EffectTrigger) -> list[Callable]:
    """Every implementation registered for ``effect_id`` on ``trigger``."""
    if effect_id is None:
        return []
    return [fn for hook_trigger, fn in EFFECT_HOOKS.get(effect_id, ()) if hook_trigger is trigger]


# Emblems are implemented, just not here: ``engine.items.emblem_trait_id``
# reads the trait out of the effect_id and ``engine.traits`` grants it, all
# before combat starts. Without this they would warn as unimplemented every
# session and pad the "missing effects" count with 16 false entries.
EMBLEM_EFFECT_PREFIX = "emblem_"


def is_emblem_effect(effect_id: str | None) -> bool:
    return effect_id is not None and effect_id.startswith(EMBLEM_EFFECT_PREFIX)


def resolve(effect_id: str | None) -> Callable | None:
    """Look up an effect, warning once if it is not implemented yet.

    Returns ``None`` for both "no effect declared" and "declared but not
    implemented"; callers simply skip.
    """
    if effect_id is None or is_emblem_effect(effect_id):
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
    return effect_id is not None and (
        effect_id in EFFECTS or is_emblem_effect(effect_id)
    )


def missing_effect_ids(declared: set[str]) -> set[str]:
    """Which of ``declared`` have no implementation -- for coverage reporting."""
    return {e for e in declared if e and not is_implemented(e)}


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


def _spread_targets(ctx, count: int) -> list:
    """The primary target plus the nearest other enemies, up to ``count``.

    Ordered by distance from the primary target, with uid as a tie-break so
    the choice stays deterministic (doc 03 sec 2.4).
    """
    from engine.hexgrid import distance

    if ctx.target is None:
        return []
    if count <= 1:
        return [ctx.target]
    others = [
        e for e in ctx.sim.enemies_of(ctx.source) if e.uid != ctx.target.uid
    ]
    others.sort(key=lambda u: (distance(ctx.target.position, u.position), u.uid))
    return [ctx.target, *others[: count - 1]]


def _multi_hit(ctx, per_hit: float, damage_type, label: str) -> None:
    """Apply ``hits`` damage instances spread over ``targets`` enemies.

    Many real abilities fire a volley -- "@NumRockets@ rockets, each dealing
    X" -- and modelling that as a single hit understates a carry's output by
    the volley size. ``hits`` and ``targets`` both default to 1, so an ability
    that declares neither behaves exactly like the single-target effects.
    """
    hits = max(1, int(ctx.number("hits", 1)))
    target_count = max(1, int(ctx.number("targets", 1)))
    if per_hit <= 0:
        return
    victims = _spread_targets(ctx, target_count)
    if not victims:
        return
    for index in range(hits):
        victim = victims[index % len(victims)]
        if not victim.alive:
            # Re-pick among the living so a volley is not wasted on a corpse.
            remaining = [v for v in victims if v.alive]
            if not remaining:
                return
            victim = remaining[index % len(remaining)]
        ctx.sim.deal_damage(ctx.source, victim, per_hit, damage_type, source_label=label)


@register("flat_physical_damage")
def flat_physical_damage(ctx) -> None:
    """Physical damage given as a flat number rather than a share of AD.

    Riot uses both forms: ``ADDamage`` is a percentage of the caster's attack
    damage, while a plain ``Damage`` on a physical ability is an absolute
    value. Supports ``hits``/``targets`` like the volley effects.
    """
    from engine.combat import DamageType

    _multi_hit(ctx, _ability_damage(ctx), DamageType.PHYSICAL, "ability_volley")


@register("multi_hit_magic_damage")
def multi_hit_magic_damage(ctx) -> None:
    """Flat magic damage per hit, ``hits`` times over ``targets`` enemies."""
    from engine.combat import DamageType

    _multi_hit(ctx, _ability_damage(ctx), DamageType.MAGIC, "ability_volley")


@register("multi_hit_physical_damage")
def multi_hit_physical_damage(ctx) -> None:
    """AD-scaled damage per hit, ``hits`` times over ``targets`` enemies."""
    from engine.combat import DamageType

    per_hit = ctx.source.derived_stats().attack_damage * ctx.number("ad_ratio", 1.0)
    _multi_hit(ctx, per_hit, DamageType.PHYSICAL, "ability_volley")


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
# An effect reads ``ctx.number(key)``, where ``ctx.params`` is the item's
# ``stats`` overlaid with its ``params`` (``ItemDef.effect_values``). Riot's
# raw variable names are used verbatim.
#
# **A key that the item does not carry silently reads as 0.0**, which is how
# Spear of Shojin shipped granting no mana at all: it read ``"mana"``, a key
# from the hand-authored starter fixture that the real dataset does not have
# (doc 99 entry 36.1). ``tests/test_item_effects.py`` now extracts every literal
# key each effect reads and asserts the item actually declares it.
# =========================================================================


@register("spear_of_shojin_bonus_mana_on_attack", EffectTrigger.ON_ATTACK)
def spear_of_shojin_bonus_mana_on_attack(ctx) -> None:
    """Bonus mana per attack, on top of the role-based base (doc 01 sec 3.2).

    ``FlatManaRestore`` is Riot's name for it; ``mana`` is the starter
    fixture's. Both are read so the fixture-driven tests keep working against
    the same implementation as the real data.
    """
    mana = ctx.number("FlatManaRestore") or ctx.number("mana")
    ctx.sim.grant_mana(ctx.source, mana, reason="spear_of_shojin")


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


@register("guinsoos_stacking_attack_speed", EffectTrigger.PERIODIC)
def guinsoos_stacking_attack_speed(ctx) -> None:
    """Stacking attack speed, once per second.

    Two corrections (doc 99 entry 36.1): Riot's description is "every second",
    not per attack, and the per-stack value is ``AttackSpeedPerStack`` (7%).
    Reading the item's flat ``attack_speed_pct`` used its *total* bonus as the
    step, which on a fast carry compounded into the attack-speed cap.
    """
    step = ctx.number("AttackSpeedPerStack") / 100.0 or ctx.number("attack_speed_pct")
    if step <= 0:
        return
    _stack_per_interval_value(ctx, "guinsoos_stack", step, "attack_speed_pct", 1.0)


# =========================================================================
# Real Set 17 item effects (doc 99 entry 33)
#
# Every one of these already had its magnitudes in ``data/items.json`` --
# 36 items carried params and none had an implementation, so the whole set was
# stats-only. That is a large part of why the engine rewarded raw unit count
# over composition: two boards of equal cost fought almost identically.
#
# The ``effect_id``s are the fetch script's ``item_<RiotId>`` convention, not
# the hand-authored names used by the starter fixture above.
#
# Params are Riot's own variable names, verbatim. They are not renamed on the
# way in: a rename is a silent place for a transcription error to hide, and
# the loader has no way to catch one.
# =========================================================================


def _once(unit, key: str) -> bool:
    """True the first time it is called for ``key`` on ``unit`` this combat.

    Threshold items (Sterak's, Bloodthirster) fire once per fight, not once
    per damage instance. Recorded on the unit so it resets with the unit's
    per-combat state rather than persisting across rounds.
    """
    fired = getattr(unit, "_effect_once", None)
    if fired is None:
        fired = set()
        unit._effect_once = fired
    if key in fired:
        return False
    fired.add(key)
    return True


def _hp_fraction(unit) -> float:
    return unit.health_fraction


@register("item_TFT_Item_WarmogsArmor", EffectTrigger.ON_COMBAT_START)
def warmogs_armor(ctx) -> None:
    """Bonus max health, as a fraction of the wearer's own maximum."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    pct = ctx.number("BonusPercentHP")
    if pct <= 0:
        return
    bonus = ctx.source.derived_stats().max_health * pct
    ctx.source.add_status(
        StatusEffect("warmogs", remaining=None, bonuses=StatBonuses({"health": bonus}))
    )
    # A max-health grant mid-combat raises the ceiling only; TFT grants the
    # current health with it, so the unit is not instantly a smaller fraction
    # of its own maximum.
    ctx.source.current_hp += bonus


@register("item_TFT_Item_SteraksGage", EffectTrigger.ON_DAMAGED)
def steraks_gage(ctx) -> None:
    """Once per combat, below a health threshold, shield a share of max health."""
    threshold = ctx.number("HealthThreshold") / 100.0
    if threshold <= 0 or _hp_fraction(ctx.source) > threshold:
        return
    if not _once(ctx.source, "steraks"):
        return
    ctx.sim.apply_shield(
        ctx.source,
        ctx.source.derived_stats().max_health * ctx.number("PercentHealthShield"),
        duration=ctx.number("ShieldDuration") or None,
        source_label="steraks_gage",
    )


@register("item_TFT_Item_Bloodthirster", EffectTrigger.ON_DAMAGED)
def bloodthirster(ctx) -> None:
    """Once per combat, below a health threshold, shield a share of max health.

    The lifesteal half is the item's ``omnivamp`` stat and applies already.
    """
    threshold = ctx.number("HealthThreshold") / 100.0
    if threshold <= 0 or _hp_fraction(ctx.source) > threshold:
        return
    if not _once(ctx.source, "bloodthirster"):
        return
    ctx.sim.apply_shield(
        ctx.source,
        ctx.source.derived_stats().max_health * (ctx.number("ShieldHealthPercent") / 100.0),
        duration=ctx.number("ShieldDuration") or None,
        source_label="bloodthirster",
    )


@register("item_TFT_Item_TitansResolve", EffectTrigger.ON_DAMAGED)
def titans_resolve(ctx) -> None:
    """Stacking attack damage and ability power, capped, on taking a hit."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    cap = int(ctx.number("StackCap", 25))
    stacks = sum(1 for s in ctx.source.status_effects if s.source == "titans_stack")
    if stacks >= cap:
        return
    ctx.source.add_status(
        StatusEffect(
            "titans_stack",
            remaining=None,
            bonuses=StatBonuses(
                {
                    "attack_damage_pct": ctx.number("StackingAD"),
                    "ability_power": ctx.number("StackingSP"),
                }
            ),
        )
    )


@register("item_TFT_Item_RapidFireCannon", EffectTrigger.ON_HIT)
def red_buff(ctx) -> None:
    """Attacks and abilities burn and wound the target.

    Registered under ``RapidFireCannon`` because that is the internal id Set
    17's **Red Buff** ships under -- the second display-name/id mismatch in
    this dataset after Void Staff (doc 99 entries 33.5, 36.1).

    The previous implementation read ``ADOnAttack``, a key this item does not
    have, and fell back to its flat 45% attack speed *per attack*: a carrier
    reached 2.49 attack speed from 0.87 in six autos. None of the item's real
    variables were being read at all.
    """
    target = ctx.target
    if target is None or not target.alive:
        return
    duration = ctx.number("Duration")
    ctx.sim.apply_burn(
        ctx.source,
        target,
        ctx.number("BurnPercent") / 100.0,
        duration,
        source_label="red_buff",
    )
    ctx.sim.apply_grievous_wounds(
        target,
        ctx.number("HealingReductionPct") / 100.0,
        duration,
        source_label="red_buff_wound",
    )


@register("item_TFT_Item_ArchangelsStaff", EffectTrigger.PERIODIC)
def archangels_staff(ctx) -> None:
    """Ability power on a fixed interval, for the whole fight."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    interval = ctx.number("IntervalSeconds")
    gain = ctx.number("APPerInterval")
    if interval <= 0 or gain <= 0:
        return
    due = int(ctx.sim.t / interval)
    if not _once(ctx.source, f"archangels_{due}"):
        return
    ctx.source.add_status(
        StatusEffect("archangels", remaining=None,
                     bonuses=StatBonuses({"ability_power": gain}))
    )


@register("item_TFT_Item_LastWhisper", EffectTrigger.ON_HIT)
def last_whisper(ctx) -> None:
    """Shred a percentage of the target's armour for a duration."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    target = ctx.target
    pct = ctx.number("ArmorReductionPercent") / 100.0
    if target is None or not target.alive or pct <= 0:
        return
    if any(s.source == "armor_shred" for s in target.status_effects):
        return
    ctx.sim.apply_status(
        target,
        StatusEffect(
            "armor_shred",
            remaining=ctx.number("ArmorBreakDuration") or None,
            bonuses=StatBonuses({"armor": -target.derived_stats().armor * pct}),
        ),
    )


@register("item_TFT_Item_StatikkShiv", EffectTrigger.ON_HIT)
def void_staff(ctx) -> None:
    """Shred a percentage of the target's magic resist for a duration.

    Registered under ``StatikkShiv``: in Set 17 the item displayed as **Void
    Staff** ships with Statikk Shiv's internal id. Matching on the display name
    would have registered an effect that silently never fires, which is the
    failure mode this whole batch exists to remove.
    """
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    target = ctx.target
    pct = ctx.number("MRShred") / 100.0
    if target is None or not target.alive or pct <= 0:
        return
    if any(s.source == "mr_shred" for s in target.status_effects):
        return
    ctx.sim.apply_status(
        target,
        StatusEffect(
            "mr_shred",
            remaining=ctx.number("MRShredDuration") or None,
            bonuses=StatBonuses({"magic_resist": -target.derived_stats().magic_resist * pct}),
        ),
    )


@register("item_TFT_Item_Crownguard", EffectTrigger.ON_COMBAT_START)
def crownguard(ctx) -> None:
    """Shield at combat start; ability power for the rest of the fight after."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    ctx.sim.apply_shield(
        ctx.source,
        ctx.source.derived_stats().max_health * (ctx.number("ShieldSize") / 100.0),
        duration=ctx.number("ShieldDuration") or None,
        source_label="crownguard",
    )
    bonus = ctx.number("ShieldBonusAP")
    if bonus > 0:
        ctx.source.add_status(
            StatusEffect("crownguard_ap", remaining=None,
                         bonuses=StatBonuses({"ability_power": bonus}))
        )


@register("item_TFT_Item_Quicksilver", EffectTrigger.ON_COMBAT_START)
def quicksilver(ctx) -> None:
    """Crowd-control immunity for a duration (doc 99 entry 34.5).

    The stacking attack speed is a *separate* paragraph in Riot's description
    ("Gain X% stacking Attack Speed every second"), with no clause tying it to
    the immunity window, so it runs for the whole fight. Its cadence comes from
    that same sentence rather than from a constant here.
    """
    from engine.unit import StatusEffect

    duration = ctx.number("SpellShieldDuration")
    if duration <= 0:
        return
    ctx.source.add_status(
        StatusEffect("cc_immune", remaining=duration, cc_immune=True)
    )


@register("item_TFT_Item_Quicksilver", EffectTrigger.PERIODIC)
def quicksilver_attack_speed(ctx) -> None:
    """Quicksilver's second half: stacking attack speed, once per second."""
    _stack_per_interval(
        ctx, "quicksilver_as", "ProcAttackSpeed", "attack_speed_pct", interval=1.0
    )


# --- helpers shared by the interval and aura items -----------------------


def _stack_per_interval_value(
    ctx, key: str, step: float, stat: str, interval: float, cap: int | None = None
) -> None:
    """Grant a already-computed ``step`` of ``stat`` once per ``interval``."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    if step <= 0 or interval <= 0:
        return
    due = int(ctx.sim.t / interval)
    if not _once(ctx.source, f"{key}_{due}"):
        return
    if cap is not None:
        held = sum(1 for s in ctx.source.status_effects if s.source == key)
        if held >= cap:
            return
    ctx.source.add_status(
        StatusEffect(key, remaining=None, bonuses=StatBonuses({stat: step}))
    )


def _stack_per_interval(
    ctx, key: str, param: str, stat: str, *, interval: float, cap: int | None = None
) -> None:
    """Grant ``stat`` once per ``interval`` seconds of combat, optionally capped."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    step = ctx.number(param)
    if step <= 0 or interval <= 0:
        return
    due = int(ctx.sim.t / interval)
    if not _once(ctx.source, f"{key}_{due}"):
        return
    if cap is not None:
        held = sum(1 for s in ctx.source.status_effects if s.source == key)
        if held >= cap:
            return
    ctx.source.add_status(
        StatusEffect(key, remaining=None, bonuses=StatBonuses({stat: step}))
    )


def _replace_status(unit, source: str, effect=None) -> None:
    """Swap a recomputed-every-tick status for its new value.

    Aura items (Gargoyle, Steadfast Heart) recompute a bonus from live board
    state each tick. Appending would stack them without bound, so the previous
    copy is removed first.
    """
    unit.status_effects = [s for s in unit.status_effects if s.source != source]
    unit._invalidate()
    if effect is not None:
        unit.add_status(effect)


def _aura_shred(ctx, key: str, param: str, stat: str) -> None:
    """Apply a percentage resist reduction to every enemy within ``HexRange``.

    Refreshed each tick rather than applied once, because units move: an enemy
    that walks into an Ionic Spark's radius must pick the shred up, and one
    that walks out must lose it.
    """
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    pct = ctx.number(param) / 100.0
    radius = int(ctx.number("HexRange", 2))
    if pct <= 0 or ctx.source.position is None:
        return
    inside = {
        u.uid
        for u in ctx.sim.units_within(
            ctx.source.position, radius, team=1 - ctx.source.team
        )
    }
    for enemy in ctx.sim.enemies_of(ctx.source):
        held = any(s.source == key for s in enemy.status_effects)
        if enemy.uid in inside and not held:
            base = getattr(enemy.derived_stats(), stat)
            enemy.add_status(
                StatusEffect(key, remaining=None, bonuses=StatBonuses({stat: -base * pct}))
            )
        elif enemy.uid not in inside and held:
            _replace_status(enemy, key)


@register("item_TFT_Item_AdaptiveHelm", EffectTrigger.ON_COMBAT_START)
def adaptive_helm(ctx) -> None:
    """Extra mana from all sources, plus a role-dependent stat half."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    frontline = ctx.source.champion.role in ("Tank", "Fighter")
    if frontline:
        resists = ctx.number("FrontlineResists")
        bonuses = StatBonuses({"armor": resists, "magic_resist": resists})
    else:
        adap = ctx.number("BacklineADAP")
        bonuses = StatBonuses(
            {"attack_damage_pct": adap / 100.0, "ability_power": adap}
        )
    ctx.source.add_status(
        StatusEffect(
            "adaptive_helm",
            remaining=None,
            bonuses=bonuses,
            mana_gain_bonus=ctx.number("ManaPercIncrease"),
        )
    )


@register("item_TFT_Item_BlueBuff", EffectTrigger.ON_COMBAT_START)
def blue_buff(ctx) -> None:
    """A share more attack damage and ability power *from all sources*.

    "From all sources" means the bonus half only, so this is measured against
    the champion's own base rather than applied to the total -- a unit with no
    AD items gains nothing from it.
    """
    from engine.stats import BASE_ABILITY_POWER, StatBonuses
    from engine.unit import StatusEffect

    share = ctx.number("ModifiedADAP")
    if share <= 0:
        return
    stats = ctx.source.derived_stats()
    base_ad = ctx.source.champion.stats.attack_damage_at(ctx.source.star_level)
    bonus_ad = max(stats.attack_damage - base_ad, 0.0)
    bonus_ap = max(stats.ability_power - BASE_ABILITY_POWER, 0.0)
    ctx.source.add_status(
        StatusEffect(
            "blue_buff",
            remaining=None,
            bonuses=StatBonuses(
                {
                    "attack_damage": bonus_ad * share,
                    "ability_power": bonus_ap * share,
                }
            ),
        )
    )


@register("item_TFT_Item_BrambleVest", EffectTrigger.ON_DAMAGED)
def bramble_vest(ctx) -> None:
    """Reflect star-scaled magic damage to adjacent enemies, on a cooldown.

    The percentage max-health grant and the flat attack damage reduction are
    handled by :func:`bramble_vest_setup` at combat start; this half is only
    the retaliation.
    """
    from engine.combat import DamageType

    cooldown = ctx.number("ICD", 2.0)
    damage = ctx.number(f"{ctx.star_level}StarAoEDamage")
    if damage <= 0 or ctx.source.position is None:
        return
    due = int(ctx.sim.t / cooldown) if cooldown > 0 else ctx.sim.tick_index
    if not _once(ctx.source, f"bramble_{due}"):
        return
    for enemy in ctx.sim.units_within(
        ctx.source.position, 1, team=1 - ctx.source.team
    ):
        ctx.sim.deal_damage(
            ctx.source,
            enemy,
            damage,
            DamageType.MAGIC,
            source_label="bramble_vest",
            trigger_effects=False,
        )


@register("item_TFT_Item_BrambleVest", EffectTrigger.ON_COMBAT_START)
def bramble_vest_setup(ctx) -> None:
    """Bramble Vest's passive half: bonus max health and attack damage taken."""
    _grant_percent_max_health(ctx, "bramble_hp", "PercentMaxHP")


@register("item_TFT_Item_DragonsClaw", EffectTrigger.ON_COMBAT_START)
def dragons_claw_setup(ctx) -> None:
    _grant_percent_max_health(ctx, "dragons_claw_hp", "PercentMaxHP")


@register("item_TFT_Item_DragonsClaw", EffectTrigger.PERIODIC)
def dragons_claw(ctx) -> None:
    """Heal a share of maximum health on a fixed interval."""
    interval = ctx.number("HealthRegenInterval")
    pct = ctx.number("PercentHealthDamage") / 100.0
    if interval <= 0 or pct <= 0:
        return
    due = int(ctx.sim.t / interval)
    if not _once(ctx.source, f"dragons_claw_{due}"):
        return
    ctx.sim.heal(
        ctx.source,
        ctx.source.derived_stats().max_health * pct,
        source_label="dragons_claw",
    )


def _grant_percent_max_health(ctx, key: str, param: str) -> None:
    """Add a share of the wearer's own max health, carrying current HP with it."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    pct = ctx.number(param)
    if pct <= 0:
        return
    bonus = ctx.source.derived_stats().max_health * pct
    ctx.source.add_status(
        StatusEffect(key, remaining=None, bonuses=StatBonuses({"health": bonus}))
    )
    ctx.source.current_hp += bonus


@register("item_TFT_Item_FrozenHeart", EffectTrigger.ON_COMBAT_START)
def protectors_vow_start(ctx) -> None:
    """Mana at combat start; the threshold half is a separate hook."""
    ctx.sim.grant_mana(ctx.source, ctx.number("CombatStartMana"), reason="protectors_vow")


@register("item_TFT_Item_FrozenHeart", EffectTrigger.ON_DAMAGED)
def protectors_vow_trigger(ctx) -> None:
    """Below a health threshold, once: mana and a share-of-max-health shield."""
    threshold = ctx.number("HealthThreshold") / 100.0
    if threshold <= 0 or ctx.source.health_fraction > threshold:
        return
    if not _once(ctx.source, "protectors_vow"):
        return
    ctx.sim.grant_mana(ctx.source, ctx.number("TriggerMana"), reason="protectors_vow")
    ctx.sim.apply_shield(
        ctx.source,
        ctx.source.derived_stats().max_health * (ctx.number("ShieldHealthPercent") / 100.0),
        duration=ctx.number("ShieldDuration") or None,
        source_label="protectors_vow",
    )


@register("item_TFT_Item_GargoyleStoneplate", EffectTrigger.PERIODIC)
def gargoyle_stoneplate(ctx) -> None:
    """Armour and magic resist scaled by how many enemies are targeting you."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    attackers = sum(
        1 for e in ctx.sim.enemies_of(ctx.source) if e.target_uid == ctx.source.uid
    )
    armor = ctx.number("ArmorPerEnemy") * attackers
    magic_resist = ctx.number("MRPerEnemy") * attackers
    _replace_status(
        ctx.source,
        "gargoyle",
        StatusEffect(
            "gargoyle",
            remaining=None,
            bonuses=StatBonuses({"armor": armor, "magic_resist": magic_resist}),
        )
        if attackers
        else None,
    )


@register("item_TFT_Item_GuardianAngel", EffectTrigger.ON_DAMAGED)
def edge_of_night(ctx) -> None:
    """Once, at a health threshold: shed crowd control and heal missing health.

    Untargetability is approximated by the shed plus the heal. Modelling the
    one-second stealth properly needs a targeting exclusion the simulator does
    not have, and a fake stealth that units still shoot at would be worse than
    an honest omission (doc 99 entry 34.6).
    """
    threshold = ctx.number("HealthThreshold") / 100.0
    if threshold <= 0 or ctx.source.health_fraction > threshold:
        return
    if not _once(ctx.source, "edge_of_night"):
        return
    ctx.source.status_effects = [
        s for s in ctx.source.status_effects if not (s.stun or s.root or s.disarm)
    ]
    ctx.source._invalidate()
    stats = ctx.source.derived_stats()
    missing = max(stats.max_health - ctx.source.current_hp, 0.0)
    ctx.sim.heal(
        ctx.source,
        missing * ctx.number("MissingHealthRestore"),
        source_label="edge_of_night",
    )


@register("item_TFT_Item_HextechGunblade", EffectTrigger.ON_HIT)
def hextech_gunblade(ctx) -> None:
    """Heal the lowest-percent-health ally for a share of the damage dealt."""
    allies = ctx.sim.allies_of(ctx.source)
    share = ctx.number("AllyHealing")
    if not allies or share <= 0 or ctx.amount <= 0:
        return
    weakest = min(allies, key=lambda u: (u.health_fraction, u.uid))
    ctx.sim.heal(weakest, ctx.amount * share, source_label="hextech_gunblade")


@register("item_TFT_Item_IonicSpark", EffectTrigger.PERIODIC)
def ionic_spark_aura(ctx) -> None:
    """Shred the magic resist of every enemy in range."""
    _aura_shred(ctx, "ionic_spark_shred", "MRShred", "magic_resist")


@register("item_TFT_Item_IonicSpark", EffectTrigger.ON_ENEMY_CAST)
def ionic_spark_zap(ctx) -> None:
    """Burn a caster for a share of the mana it just spent."""
    from engine.combat import DamageType
    from engine.hexgrid import distance

    caster = ctx.target
    ratio = ctx.number("ManaRatio") / 100.0
    radius = int(ctx.number("HexRange", 2))
    if caster is None or ratio <= 0 or ctx.source.position is None:
        return
    if caster.position is None or distance(ctx.source.position, caster.position) > radius:
        return
    ctx.sim.deal_damage(
        ctx.source,
        caster,
        ctx.amount * ratio,
        DamageType.MAGIC,
        source_label="ionic_spark",
        trigger_effects=False,
    )


@register("item_TFT_Item_Leviathan", EffectTrigger.ON_ATTACK)
def nashors_tooth(ctx) -> None:
    """Bonus mana per attack, more on a critical strike."""
    mana = ctx.number("ManaOnCrit") if ctx.is_crit else ctx.number("BaseManaOnHit")
    ctx.sim.grant_mana(ctx.source, mana, reason="nashors_tooth")


@register("item_TFT_Item_MadredsBloodrazor", EffectTrigger.DAMAGE_MODIFIER)
def giant_slayer(ctx) -> float | None:
    """Additional damage amp against Tanks.

    Returns a multiplier rather than mutating anything -- the condition is the
    victim's role, which is only known inside ``deal_damage``.
    """
    bonus = ctx.number("{abb9f4ce}") / 100.0
    if ctx.target is None or bonus <= 0:
        return None
    return 1.0 + bonus if ctx.target.champion.role == "Tank" else None


@register("item_TFT_Item_Morellonomicon", EffectTrigger.ON_HIT)
def morellonomicon(ctx) -> None:
    """Attacks and abilities burn and wound the target."""
    target = ctx.target
    if target is None or not target.alive:
        return
    ctx.sim.apply_burn(
        ctx.source,
        target,
        ctx.number("BurnPercent") / 100.0,
        ctx.number("BurnDuration"),
        ticks_per_second=ctx.number("TicksPerSecond", 1.0),
        source_label="morellonomicon",
    )
    ctx.sim.apply_grievous_wounds(
        target,
        ctx.number("GrievousWoundsPercent") / 100.0,
        ctx.number("BurnDuration"),
        source_label="morellonomicon_wound",
    )


@register("item_TFT_Item_NightHarvester", EffectTrigger.PERIODIC)
def steadfast_heart(ctx) -> None:
    """Durability that doubles while the holder is above a health threshold."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    above = ctx.source.health_fraction > ctx.number("ThresholdForEmpower")
    value = ctx.number("EmpoweredDurability" if above else "BaseDurability")
    if value <= 0:
        return
    _replace_status(
        ctx.source,
        "steadfast_heart",
        StatusEffect(
            "steadfast_heart", remaining=None, bonuses=StatBonuses({"durability": value})
        ),
    )


@register("item_TFT_Item_PowerGauntlet", EffectTrigger.ON_ATTACK)
def strikers_flail(ctx) -> None:
    """Critical strikes grant stacking, expiring damage amp."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    step = ctx.number("BuffDamageAmp")
    if not ctx.is_crit or step <= 0:
        return
    cap = int(ctx.number("MaxStacks", 4))
    held = sum(1 for s in ctx.source.status_effects if s.source == "strikers_flail")
    if held >= cap:
        return
    ctx.source.add_status(
        StatusEffect(
            "strikers_flail",
            remaining=ctx.number("Duration") or None,
            bonuses=StatBonuses({"damage_amp": step}),
        )
    )


@register("item_TFT_Item_RedBuff", EffectTrigger.ON_COMBAT_START)
def sunfire_cape_setup(ctx) -> None:
    _grant_percent_max_health(ctx, "sunfire_hp", "BonusPercentHP")


@register("item_TFT_Item_RedBuff", EffectTrigger.PERIODIC)
def sunfire_cape(ctx) -> None:
    """Periodically burn and wound one nearby enemy."""
    interval = ctx.number("ICD", 2.0)
    radius = int(ctx.number("HexRange", 2))
    if interval <= 0 or ctx.source.position is None:
        return
    due = int(ctx.sim.t / interval)
    if not _once(ctx.source, f"sunfire_{due}"):
        return
    nearby = ctx.sim.units_within(ctx.source.position, radius, team=1 - ctx.source.team)
    if not nearby:
        return
    victim = nearby[0]
    ctx.sim.apply_burn(
        ctx.source,
        victim,
        ctx.number("BurnPercent") / 100.0,
        ctx.number("BurnDuration"),
        source_label="sunfire_cape",
    )
    ctx.sim.apply_grievous_wounds(
        victim,
        ctx.number("GrievousWoundsPercent") / 100.0,
        ctx.number("BurnDuration"),
        source_label="sunfire_cape_wound",
    )


@register("item_TFT_Item_Redemption", EffectTrigger.PERIODIC)
def spirit_visage(ctx) -> None:
    """Regenerate a share of missing health each tick of its own rate."""
    rate = ctx.number("HealTickRate", 1.0)
    share = ctx.number("MissingHealthHeal")
    if rate <= 0 or share <= 0:
        return
    interval = 1.0 / rate
    due = int(ctx.sim.t / interval)
    if not _once(ctx.source, f"spirit_visage_{due}"):
        return
    stats = ctx.source.derived_stats()
    missing = max(stats.max_health - ctx.source.current_hp, 0.0)
    healed = missing * share
    cap = ctx.number("MaxHeal")
    if cap > 0:
        healed = min(healed, cap)
    ctx.sim.heal(ctx.source, healed, source_label="spirit_visage")


@register("item_TFT_Item_RunaansHurricane", EffectTrigger.ON_ATTACK)
def krakens_fury(ctx) -> None:
    """Stacking attack damage per attack; a one-off attack speed capstone."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    step = ctx.number("ADOnAttack")
    cap = int(ctx.number("MaxStacks", 15))
    if step <= 0:
        return
    held = sum(1 for s in ctx.source.status_effects if s.source == "krakens_stack")
    if held < cap:
        ctx.source.add_status(
            StatusEffect(
                "krakens_stack",
                remaining=None,
                bonuses=StatBonuses({"attack_damage_pct": step}),
            )
        )
        return
    capstone = ctx.number("ASCapstone")
    if capstone > 0 and _once(ctx.source, "krakens_capstone"):
        ctx.source.add_status(
            StatusEffect(
                "krakens_capstone",
                remaining=None,
                bonuses=StatBonuses({"attack_speed_pct": capstone}),
            )
        )


@register("item_TFT_Item_SpectralGauntlet", EffectTrigger.ON_COMBAT_START)
def evenshroud_setup(ctx) -> None:
    """Armour and magic resist for the opening seconds of the fight."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    resists = ctx.number("BonusResists")
    duration = ctx.number("BonusResistDuration")
    if resists <= 0 or duration <= 0:
        return
    ctx.source.add_status(
        StatusEffect(
            "evenshroud_resists",
            remaining=duration,
            bonuses=StatBonuses({"armor": resists, "magic_resist": resists}),
        )
    )


@register("item_TFT_Item_SpectralGauntlet", EffectTrigger.PERIODIC)
def evenshroud_aura(ctx) -> None:
    """Sunder the armour of every enemy in range."""
    _aura_shred(ctx, "evenshroud_sunder", "ARReductionAmount", "armor")


@register("item_TFT_Item_UnstableConcoction", EffectTrigger.PERIODIC)
def hand_of_justice(ctx) -> None:
    """Two effects, each doubled on the correct side of a health threshold."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    above = ctx.source.health_fraction > ctx.number("HealthThreshold")
    scale = ctx.number("{f23e83fc}", 2.0)
    attack = ctx.number("AD_NotStatBar")
    ability = ctx.number("AP_NotStatBar")
    omnivamp = ctx.number("StatOmnivamp_NotStatBar")
    if above:
        attack *= scale
        ability *= scale
    else:
        omnivamp *= scale
    _replace_status(
        ctx.source,
        "hand_of_justice",
        StatusEffect(
            "hand_of_justice",
            remaining=None,
            bonuses=StatBonuses(
                {
                    "attack_damage_pct": attack,
                    "ability_power": ability,
                    "omnivamp": omnivamp,
                }
            ),
        ),
    )


# --- items whose whole behaviour is now stats ----------------------------
#
# Deathblade and Rabadon's Deathcap publish their entire effect as Damage Amp
# under a hashed variable name; once the fetch script maps it (doc 99 entry
# 34.4) there is no behaviour left for a hook to add. They are registered
# explicitly rather than left unimplemented so that the missing-effect count
# means "genuinely missing" (doc 02 sec 2).

#
# The three Tactician items and Spatula have no combat behaviour at all: the
# Tacticians grant team size, resolved in ``engine.player.max_board_units``,
# and Spatula's description is flavour text ("It must do something...").
STAT_ONLY_ITEM_EFFECTS = (
    "item_TFT_Item_Deathblade",
    "item_TFT_Item_RabadonsDeathcap",
    "item_TFT_Item_Spatula",
    "item_TFT_Item_ForceOfNature",
    "item_TFT_Item_TacticiansRing",
    "item_TFT_Item_TacticiansScepter",
)

for _effect_id in STAT_ONLY_ITEM_EFFECTS:
    register(_effect_id, EffectTrigger.ON_COMBAT_START)(_no_effect)


# =========================================================================
# Keyword items (doc 99 entry 36.2)
#
# Riot ships these with no numeric variables at all -- their whole behaviour
# is a named keyword -- so the fetch script's "does it have leftover params?"
# test classified them as no-ops and they shipped as pure stat sticks.
# =========================================================================


def _grant_precision(ctx) -> None:
    """Abilities from this unit can critically strike."""
    from engine.unit import StatusEffect

    if any(s.source == "precision" for s in ctx.source.status_effects):
        return
    ctx.source.add_status(StatusEffect("precision", remaining=None, precision=True))


@register("item_TFT_Item_InfinityEdge", EffectTrigger.ON_COMBAT_START)
def infinity_edge(ctx) -> None:
    """Gain Precision. Its attack damage and crit chance are stats."""
    _grant_precision(ctx)


@register("item_TFT_Item_JeweledGauntlet", EffectTrigger.ON_COMBAT_START)
def jeweled_gauntlet(ctx) -> None:
    """Gain Precision. Its ability power and crit chance are stats."""
    _grant_precision(ctx)


@register("item_TFT_Item_ThiefsGloves", EffectTrigger.ON_COMBAT_START)
def thiefs_gloves(ctx) -> None:
    """Equip two random completed items each round.

    Resolved *outside* combat, in ``engine.player.PlayerState`` at round start,
    because the items must be on the unit before trait and item combat-start
    hooks run. This hook exists so the effect_id is not reported missing; the
    grant itself is not a combat behaviour.
    """
    return None
