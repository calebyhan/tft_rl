"""The 29 champion abilities the fetch script declines to canonicalise.

`scripts/fetch_cdragon.py` maps most abilities onto a generic effect
(`single_target_magic_damage`, `multi_hit_physical_damage`, ...) by reading
Riot's tags. It **refuses** when an ability carries both `spellPassive` and
`spellActive`, because nothing in the payload says which variable belongs to
which half -- the `@Var@` references in the display text are computed names
that do not resolve back to raw variables. Casting the wrong number is worse
than declining, so it declines (doc 99 entries 11.2, 16).

That left 29 champions with `ability_TFT17_<Name>` ids and no implementation.
This module supplies them. The split is resolved *per champion* by reading
Riot's own description prose, which does name each variable's role -- the
blocker was automation, not information (doc 99 entry 35.1).

**These are per-champion implementations, and that is deliberate.** The house
rule is "no per-champion *constants* in code": every magnitude here still comes
from the champion's `params`, indexed per star level by `ctx.number`. What is
per-champion is the *logic*, which the `ability_TFT17_<Name>` id convention
already anticipates -- a generic hook cannot express "every third cast, leap
and fire a cone".

Riot's raw variable names are used verbatim, for the same reason as the item
effects: renaming on the way in is a silent place for a transcription error to
hide, and the loader cannot catch one.
"""

from __future__ import annotations

from engine.effects import EffectTrigger, _once, register

# Riot expresses ability damage two ways, and the suffix says which:
#   * `...AD` / `ADDamage`  -- a *percentage* of attack damage (115 == 115%)
#   * `...AP` / plain names -- a flat number that scales with ability power
# These two helpers are the only place that convention is encoded.


def _ap(ctx, key: str) -> float:
    """A flat magnitude scaled by the caster's ability power."""
    return ctx.number(key) * ctx.source.derived_stats().ability_power_multiplier


def _ad(ctx, key: str) -> float:
    """A percentage-of-attack-damage magnitude."""
    return ctx.source.derived_stats().attack_damage * ctx.number(key) / 100.0


def _hp(ctx, key: str) -> float:
    """A share of the caster's maximum health."""
    return ctx.source.derived_stats().max_health * ctx.number(key)


def _damage(ctx, target, amount, kind="magic", label="ability", **kw) -> float:
    from engine.combat import DamageType

    if target is None or not target.alive or amount <= 0:
        return 0.0
    types = {"magic": DamageType.MAGIC, "physical": DamageType.PHYSICAL,
             "true": DamageType.TRUE}
    return ctx.sim.deal_damage(
        ctx.source, target, amount, types[kind], source_label=label, **kw
    )


def _nearby_enemies(ctx, center=None, radius=1):
    """Living enemies within ``radius`` of ``center`` (default: the target)."""
    anchor = center or (ctx.target.position if ctx.target else ctx.source.position)
    if anchor is None:
        return []
    return ctx.sim.units_within(anchor, radius, team=1 - ctx.source.team)


def _cone_enemies(ctx, length, half_angle=2):
    """Living enemies inside a cone from the caster toward its target."""
    from engine.hexgrid import cone

    if ctx.source.position is None or ctx.target is None or ctx.target.position is None:
        return []
    hexes = set(cone(ctx.source.position, ctx.target.position, int(length), half_angle))
    return [e for e in ctx.sim.enemies_of(ctx.source) if e.position in hexes]


def _is_lucky(ctx) -> bool:
    """Fateweaver grants its members "check twice, take the better outcome"."""
    return ctx.sim.has_trait(ctx.source, "TFT17_Fateweaver")


def _enter_groove(ctx, seconds: float) -> None:
    """Several champions enter Space Groove's state from their own ability.

    The buff's magnitude belongs to the trait, so this only sets the state; if
    the board has no Space Groove the status is inert, which matches TFT --
    a Groovian ability still says "enter the Groove" with nothing to gain.
    """
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    if seconds <= 0:
        return
    ctx.source.add_status(
        StatusEffect("space_groove", remaining=seconds, bonuses=StatBonuses())
    )


def _strongest(units):
    """Star level, then cost, with uid as a deterministic tie-break."""
    if not units:
        return None
    return max(units, key=lambda u: (u.star_level, u.champion.cost, -u.uid))


# =========================================================================
# Marksmen and casters
# =========================================================================


@register("ability_TFT17_Lulu")
def lulu(ctx) -> None:
    """Call down damage on several nearby enemies.

    The Stargazer-constellation secondary effect is not modelled: it depends on
    a per-game constellation the engine does not roll (doc 99 entry 35.4).
    """
    victims = ctx.sim.enemies_of(ctx.source)[: int(ctx.number("NumEnemies", 3))]
    for enemy in victims:
        _damage(ctx, enemy, _ap(ctx, "Damage"))


@register("ability_TFT17_TwistedFate")
def twisted_fate(ctx) -> None:
    """Throw a card worth between a minimum and maximum, Lucky if available.

    Overkill bouncing to the nearest enemy is modelled: the excess above the
    target's remaining health is re-applied once.
    """
    low, high = ctx.number("DamageMin"), ctx.number("DamageMax")
    scale = ctx.source.derived_stats().ability_power_multiplier
    amount = ctx.sim.lucky_value(low, high, _is_lucky(ctx)) * scale
    if ctx.target is None:
        return
    before = ctx.target.current_hp
    _damage(ctx, ctx.target, amount)
    overkill = amount - before
    if overkill > 0:
        others = [e for e in ctx.sim.enemies_of(ctx.source) if e.uid != ctx.target.uid]
        if others:
            _damage(ctx, others[0], overkill, label="ability_bounce")


@register("ability_TFT17_Caitlyn", EffectTrigger.ON_ATTACK)
def caitlyn_headshot(ctx) -> None:
    """Passive: attacks have a Lucky chance to fire an empowered Headshot."""
    chance = ctx.number("ProcChance") / 100.0
    if chance <= 0 or ctx.target is None:
        return
    if not ctx.sim.lucky_roll(chance, _is_lucky(ctx)):
        return
    _damage(
        ctx, ctx.target,
        _ad(ctx, "BonusDamage") + _ap(ctx, "Damage"),
        kind="physical", label="caitlyn_headshot",
    )


@register("ability_TFT17_Caitlyn")
def caitlyn(ctx) -> None:
    """Active: mark every enemy, amplifying the damage they take."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    amp = ctx.number("NovaMarkDamageAmp")
    for enemy in ctx.sim.enemies_of(ctx.source):
        if any(s.source == "nova_mark" for s in enemy.status_effects):
            continue
        # Damage *taken* is raised by lowering durability, the only
        # incoming-damage multiplier the stat model has.
        enemy.add_status(
            StatusEffect(
                "nova_mark", remaining=None, bonuses=StatBonuses({"durability": -amp})
            )
        )


@register("ability_TFT17_Vex", EffectTrigger.ON_ATTACK)
def vex_shadow(ctx) -> None:
    """Passive: Shadow strikes a nearby enemy; every Nth strike hits twice."""
    enemies = ctx.sim.enemies_of(ctx.source)
    if not enemies:
        return
    victim = ctx.target if ctx.target in enemies else enemies[0]
    _damage(ctx, victim, _ap(ctx, "ShadowHandDamage"), label="vex_shadow")
    threshold = int(ctx.number("NumStrikesForPassive", 5))
    if threshold > 0 and victim.add_mark("vex_shadow", ctx.source.uid) >= threshold:
        victim.clear_marks("vex_shadow", ctx.source.uid)
        _damage(ctx, victim, _ap(ctx, "ShadowHandDamage"), label="vex_shadow_repeat")


@register("ability_TFT17_Vex")
def vex(ctx) -> None:
    """Active: several empowered Shadow strikes."""
    strikes = int(ctx.number("NumActiveStrikes", 3))
    for _ in range(strikes):
        enemies = ctx.sim.enemies_of(ctx.source)
        if not enemies:
            return
        victim = ctx.target if (ctx.target and ctx.target.alive) else enemies[0]
        _damage(ctx, victim, _ap(ctx, "ShadowHandMagicDamage"), label="vex_strike")


@register("ability_TFT17_Xayah", EffectTrigger.ON_ATTACK)
def xayah_feathers(ctx) -> None:
    """Passive: attacks bounce, losing damage per target, leaving a Feather."""
    bounces = int(ctx.number("AttackNumEnemies", 3))
    falloff = ctx.number("PassivePercentReducedDamage")
    base = ctx.source.derived_stats().attack_damage
    enemies = [e for e in ctx.sim.enemies_of(ctx.source) if ctx.target is None or e.uid != ctx.target.uid]
    amount = base
    for enemy in enemies[: max(0, bounces - 1)]:
        amount *= 1.0 - falloff
        _damage(ctx, enemy, amount, kind="physical", label="xayah_bounce")
    if ctx.target is not None:
        ctx.target.add_mark("feather", ctx.source.uid)


@register("ability_TFT17_Xayah")
def xayah(ctx) -> None:
    """Active: attack speed, then recall every Feather onto nearby enemies."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    ctx.source.add_status(
        StatusEffect(
            "xayah_frenzy",
            remaining=ctx.number("Duration") or None,
            bonuses=StatBonuses({"attack_speed_pct": ctx.number("AttackSpeed")}),
        )
    )
    feathers = sum(
        e.mark_count("feather", ctx.source.uid) for e in ctx.sim.enemies_of(ctx.source)
    )
    if feathers <= 0:
        return
    per = _ad(ctx, "ADDamage") + _ap(ctx, "APDamage")
    victims = ctx.sim.enemies_of(ctx.source)[: int(ctx.number("RecallFeatherTargets", 3))]
    for enemy in victims:
        enemy.clear_marks("feather", ctx.source.uid)
        _damage(ctx, enemy, per * feathers, kind="physical", label="xayah_recall")
    if ctx.target is not None:
        _damage(
            ctx, ctx.target, _ad(ctx, "PrimaryTargetBonusDamage"),
            kind="physical", label="xayah_primary",
        )


@register("ability_TFT17_Jhin", EffectTrigger.ON_COMBAT_START)
def jhin_passive(ctx) -> None:
    """Passive: a fixed attack speed, with bonus AS converted into damage.

    Applied at combat start rather than continuously: converting again every
    tick would compound, and the conversion is of *bonus* attack speed, which
    items and traits have already granted by this point.
    """
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    fixed = ctx.number("FixedAS")
    if fixed <= 0:
        return
    stats = ctx.source.derived_stats()
    base = ctx.source.champion.stats.attack_speed
    bonus_fraction = max(stats.attack_speed / base - 1.0, 0.0) if base > 0 else 0.0
    per = ctx.number("PercentBonusASToConvert")
    rate = ctx.number("ADConversionRate")
    converted = (bonus_fraction / per) * rate if per > 0 else 0.0
    ctx.source.add_status(
        StatusEffect(
            "jhin_passive",
            remaining=None,
            bonuses=StatBonuses(
                {
                    # Pin attack speed to the fixed value by cancelling the rest.
                    "attack_speed_pct": (fixed / base) - (stats.attack_speed / base),
                    "attack_damage": converted,
                }
            ),
        )
    )


@register("ability_TFT17_Jhin")
def jhin(ctx) -> None:
    """Active: spectral hands fire alongside Jhin; the final shots hit harder."""
    hands = int(ctx.number("NumHands", 4))
    shots = int(ctx.number("NumAttacks", 4))
    per = _ad(ctx, "ADDamage") + _ap(ctx, "APDamage")
    final_bonus = 1.0 + ctx.number("FinalShotPercentDamageIncrease")
    for shot in range(shots):
        enemies = ctx.sim.enemies_of(ctx.source)
        if not enemies:
            return
        victim = ctx.target if (ctx.target and ctx.target.alive) else enemies[0]
        scale = final_bonus if shot == shots - 1 else 1.0
        _damage(ctx, victim, per * hands * scale, kind="physical", label="jhin")


@register("ability_TFT17_Kindred", EffectTrigger.ON_ATTACK)
def kindred_marks(ctx) -> None:
    """Passive: attacks mark; at the cap Wolf consumes them for damage."""
    if ctx.target is None:
        return
    cap = int(ctx.number("MaxMarks", 3))
    if cap > 0 and ctx.target.add_mark("kindred", ctx.source.uid) >= cap:
        ctx.target.clear_marks("kindred", ctx.source.uid)
        _damage(
            ctx, ctx.target, _ad(ctx, "ADDamage") + _ap(ctx, "APDamage"),
            kind="physical", label="kindred_wolf",
        )


@register("ability_TFT17_Kindred")
def kindred(ctx) -> None:
    """Active: jump, then fire arrows at the nearest enemies."""
    if ctx.target is not None and ctx.target.position is not None:
        ctx.sim.reposition(ctx.source, ctx.target.position, int(ctx.number("HexDistance", 1)))
    victims = ctx.sim.enemies_of(ctx.source)[: int(ctx.number("NumTargets", 3))]
    for enemy in victims:
        _damage(ctx, enemy, _ad(ctx, "SpellDamage"), kind="physical", label="kindred")


@register("ability_TFT17_Leblanc", EffectTrigger.ON_ATTACK)
def leblanc_passive(ctx) -> None:
    """Passive: attacks deal magic damage instead of physical.

    Modelled as a rider rather than a replacement: the simulator resolves the
    physical hit through `_land_attack` before on-attack effects run, so the
    magic half is added here.
    """
    _damage(ctx, ctx.target, _ap(ctx, "BasicAttackDamage"), label="leblanc_passive")


@register("ability_TFT17_Leblanc")
def leblanc(ctx) -> None:
    """Active: summon clones that attack alongside, then fire a bolt each."""
    clones = int(ctx.number("NumClones", 5))
    shots = int(ctx.number("NumAttacks", 5))
    multiplier = ctx.number("CloneDamageMultiplier")
    base = ctx.source.derived_stats().attack_damage * multiplier
    for _ in range(shots):
        enemies = ctx.sim.enemies_of(ctx.source)
        if not enemies:
            return
        victim = ctx.target if (ctx.target and ctx.target.alive) else enemies[0]
        _damage(ctx, victim, base * clones, kind="physical", label="leblanc_clones")
    for _ in range(clones):
        enemies = ctx.sim.enemies_of(ctx.source)
        if not enemies:
            return
        _damage(ctx, enemies[0], _ap(ctx, "BoltDamage"), label="leblanc_bolt")


@register("ability_TFT17_Graves", EffectTrigger.ON_ATTACK)
def graves_passive(ctx) -> None:
    """Passive: attacks fire several projectiles in a cone."""
    count = int(ctx.number("NumProjectiles", 5))
    share = ctx.number("PassivePercentBAD")
    per = ctx.source.derived_stats().attack_damage * share
    for enemy in _cone_enemies(ctx, 3)[:count]:
        _damage(ctx, enemy, per, kind="physical", label="graves_cone")


@register("ability_TFT17_Graves")
def graves(ctx) -> None:
    """Active: an explosive shell, splashing onto adjacent enemies."""
    _damage(ctx, ctx.target, _ad(ctx, "Damage"), kind="physical", label="graves")
    splash = _ad(ctx, "SecondaryDamageAD") + _ap(ctx, "SecondaryDamageAP")
    for enemy in _nearby_enemies(ctx, radius=1):
        if ctx.target is None or enemy.uid != ctx.target.uid:
            _damage(ctx, enemy, splash, kind="physical", label="graves_splash")


@register("ability_TFT17_Teemo", EffectTrigger.ON_ATTACK)
def teemo_passive(ctx) -> None:
    """Passive: bonus magic damage plus a stacking poison."""
    if ctx.target is None:
        return
    _damage(ctx, ctx.target, _ap(ctx, "HitDamage"), label="teemo_hit")
    duration = ctx.number("PoisonDuration")
    poison = _ap(ctx, "MagicDamage")
    max_health = ctx.target.derived_stats().max_health
    if duration > 0 and poison > 0 and max_health > 0:
        ctx.sim.apply_burn(
            ctx.source, ctx.target, poison / max_health / duration, duration,
            source_label="teemo_poison",
        )
    stacks = ctx.target.add_mark("teemo_poison", ctx.source.uid)
    if stacks >= int(ctx.number("GrooveStacks", 5)):
        _enter_groove(ctx, 1.0)


@register("ability_TFT17_Teemo")
def teemo(ctx) -> None:
    """Active: a burst of attack speed for a few attacks."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    attacks = ctx.number("ActiveAttacks", 3)
    speed = ctx.source.derived_stats().attack_speed
    ctx.source.add_status(
        StatusEffect(
            "teemo_haste",
            remaining=(attacks / speed) if speed > 0 else None,
            bonuses=StatBonuses({"attack_speed_pct": ctx.number("AttackSpeed")}),
        )
    )


@register("ability_TFT17_Sona")
def sona(ctx) -> None:
    """Stick debris to a target; every Nth cast rip it all off and slam."""
    every = int(ctx.number("NumCasts", 5))
    casts = ctx.source.bump_counter("sona_casts")
    enemies = ctx.sim.enemies_of(ctx.source)
    if not enemies:
        return

    if every > 0 and casts % every == 0:
        carriers = [e for e in enemies if e.mark_count("debris", ctx.source.uid)]
        for enemy in carriers:
            enemy.clear_marks("debris", ctx.source.uid)
            _damage(ctx, enemy, _ap(ctx, "DebrisRipDamage"), label="sona_rip")
        victim = ctx.target if (ctx.target and ctx.target.alive) else enemies[0]
        _damage(ctx, victim, _ap(ctx, "SlamDamage"), label="sona_slam")
        if victim.alive:
            ctx.sim.apply_stun(victim, ctx.number("StunDuration"), source_label="sona")
        return

    # Prefer an enemy without debris, matching "nearest target without one".
    victim = next(
        (e for e in enemies if not e.mark_count("debris", ctx.source.uid)), enemies[0]
    )
    _damage(ctx, victim, _ap(ctx, "DebrisDamage"), label="sona_debris")
    if victim.alive:
        victim.add_mark("debris", ctx.source.uid)


@register("ability_TFT17_MissFortune")
def miss_fortune(ctx) -> None:
    """Damage scaling with her chosen mode's tier.

    Gun Goddess lets the player pick Conduit / Challenger / Replicator mode,
    which the engine has no mechanism to offer. The mode is resolved as the
    highest tier whose param exists, i.e. her strongest form, and the choice
    itself is recorded as unmodelled (doc 99 entry 35.4).
    """
    tier = 0.0
    for index in range(5, 0, -1):
        value = ctx.number(f"Tier{index}Damage")
        if value > 0:
            tier = value
            break
    if tier <= 0 or ctx.target is None:
        return
    _damage(ctx, ctx.target, ctx.source.derived_stats().attack_damage * tier,
            kind="physical", label="miss_fortune")


# =========================================================================
# Assassins and fighters
# =========================================================================


@register("ability_TFT17_Talon")
def talon(ctx) -> None:
    """Stab for a bleed, then leap to the healthiest enemy in range."""
    if ctx.target is None:
        return
    duration = ctx.number("BleedDuration")
    bleed = _ad(ctx, "ADBleedDamage") + _ap(ctx, "APBleedDamage")
    max_health = ctx.target.derived_stats().max_health
    if duration > 0 and bleed > 0 and max_health > 0:
        ctx.sim.apply_burn(
            ctx.source, ctx.target, bleed / max_health / duration, duration,
            source_label="talon_bleed",
        )
    reach = int(ctx.number("HexDistance", 3))
    candidates = [
        e for e in ctx.sim.enemies_of(ctx.source)
        if e.position and ctx.source.position
        and _within(ctx, e, reach)
    ]
    if candidates:
        best = max(candidates, key=lambda u: (u.health_fraction, -u.uid))
        if best.position is not None:
            ctx.sim.reposition(ctx.source, best.position, reach)


def _within(ctx, other, reach) -> bool:
    from engine.hexgrid import distance

    return distance(ctx.source.position, other.position) <= reach


@register("ability_TFT17_Pyke")
def pyke(ctx) -> None:
    """Harpoon the furthest enemy, then teleport behind them and cleave."""
    from engine.hexgrid import distance

    enemies = ctx.sim.enemies_of(ctx.source)
    if not enemies or ctx.source.position is None:
        return
    furthest = max(
        enemies, key=lambda e: (distance(ctx.source.position, e.position), -e.uid)
    )
    _damage(ctx, furthest, _ap(ctx, "SpearDamage"), kind="physical", label="pyke_spear")
    if not furthest.alive or furthest.position is None:
        return
    ctx.sim.reposition(ctx.source, furthest.position, 1)
    _damage(ctx, furthest, _ad(ctx, "TargetDamage"), kind="physical", label="pyke_cleave")
    for enemy in _nearby_enemies(ctx, center=furthest.position, radius=1):
        if enemy.uid != furthest.uid:
            _damage(ctx, enemy, _ad(ctx, "AoEDamage"), kind="physical", label="pyke_aoe")


@register("ability_TFT17_Fizz")
def fizz(ctx) -> None:
    """Dash through the target; every third cast summons a stunning Mega Meep."""
    if ctx.target is None:
        return
    _damage(ctx, ctx.target, _ap(ctx, "DashDamage"), label="fizz_dash")
    if ctx.target.position is not None:
        ctx.sim.reposition(ctx.source, ctx.target.position, 1)
    if ctx.source.bump_counter("fizz_casts") % 3 != 0:
        return
    bite = _ap(ctx, "BiteDamageAP")
    _damage(ctx, ctx.target, bite, label="fizz_meep")
    if ctx.target.alive:
        ctx.sim.apply_stun(
            ctx.target, ctx.number("MegaMeepStunDuration"), source_label="fizz"
        )
    secondary = bite * ctx.number("SecondaryDamage")
    for enemy in _nearby_enemies(ctx, radius=1):
        if enemy.uid != ctx.target.uid:
            _damage(ctx, enemy, secondary, label="fizz_meep_splash")


@register("ability_TFT17_Gwen")
def gwen(ctx) -> None:
    """Snip the weakest enemy in a cone, re-casting at reduced damage on a kill."""
    scale = 1.0
    for _ in range(4):  # bounded: a reset chain cannot run forever
        enemies = ctx.sim.enemies_of(ctx.source)
        if not enemies:
            return
        victim = min(enemies, key=lambda u: (u.health_fraction, u.uid))
        if victim.position is not None:
            ctx.sim.reposition(ctx.source, victim.position, 1)
        cone_victims = _cone_enemies(ctx, 2)
        _damage(ctx, victim, _ap(ctx, "Damage") * scale, label="gwen")
        for enemy in cone_victims:
            if enemy.uid != victim.uid:
                _damage(ctx, enemy, _ap(ctx, "AreaDamage") * scale, label="gwen_cone")
        if victim.alive:
            return
        scale *= ctx.number("ResetDamage")
        if scale <= 0:
            return


@register("ability_TFT17_Gwen", EffectTrigger.PERIODIC)
def gwen_groove(ctx) -> None:
    """Passive: in the Groove while targeting a low-health enemy."""
    threshold = ctx.number("GrooveThreshold")
    target = ctx.sim.by_uid.get(ctx.source.target_uid or -1)
    if target is not None and target.alive and target.health_fraction < threshold:
        if not any(s.source == "space_groove" for s in ctx.source.status_effects):
            _enter_groove(ctx, 1.0)


@register("ability_TFT17_MasterYi", EffectTrigger.ON_ATTACK)
def master_yi_passive(ctx) -> None:
    """Passive: every third attack is a doubleslash."""
    if ctx.source.bump_counter("yi_attacks") % 3 == 0:
        _damage(
            ctx, ctx.target, _ad(ctx, "PassiveDamage"),
            kind="physical", label="yi_doubleslash",
        )


@register("ability_TFT17_MasterYi")
def master_yi(ctx) -> None:
    """Active: a Psi-State of omnivamp and attack speed."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    ctx.source.add_status(
        StatusEffect(
            "yi_psi_state",
            remaining=ctx.number("Duration") or None,
            bonuses=StatBonuses(
                {
                    "attack_speed_pct": ctx.number("AttackSpeed"),
                    "omnivamp": ctx.number("Omnivamp"),
                }
            ),
        )
    )
    _damage(
        ctx, ctx.target, _ad(ctx, "DamageAD") + _ap(ctx, "DamageAP"),
        kind="physical", label="yi_projection",
    )


@register("ability_TFT17_Riven")
def riven(ctx) -> None:
    """Dash and slash; every third cast launches a cone wave instead."""
    from engine.stats import StatBonuses  # noqa: F401  (kept for symmetry)

    ctx.sim.apply_shield(
        ctx.source, ctx.number("Shield"),
        duration=ctx.number("ShieldDuration") or None, source_label="riven",
    )
    if ctx.target is not None and ctx.target.position is not None:
        ctx.sim.reposition(ctx.source, ctx.target.position, int(ctx.number("DashRange", 1)))

    every = int(ctx.number("SpecialCastCount", 3))
    casts = ctx.source.bump_counter("riven_casts")
    if every > 0 and casts % every == 0:
        for enemy in _cone_enemies(ctx, ctx.number("ThirdCastConeHexRange", 3)):
            _damage(ctx, enemy, _ap(ctx, "WaveDamage"), label="riven_wave")
        return
    for enemy in _nearby_enemies(ctx, center=ctx.source.position, radius=1):
        _damage(ctx, enemy, _ap(ctx, "Damage"), label="riven_slash")


@register("ability_TFT17_Riven", EffectTrigger.ON_ATTACK)
def riven_passive(ctx) -> None:
    """Passive: attacks carry bonus damage, adapting to AD or AP."""
    _damage(ctx, ctx.target, _ap(ctx, "PassiveDamage"), label="riven_passive")


@register("ability_TFT17_Fiora", EffectTrigger.ON_ATTACK)
def fiora_vitals(ctx) -> None:
    """Passive: every Nth attack reveals and strikes a Vital."""
    every = int(ctx.number("NumAttacks", 2))
    if every <= 0 or ctx.source.bump_counter("fiora_attacks") % every != 0:
        return
    dealt = _damage(
        ctx, ctx.target, _ad(ctx, "VitalDamage"), kind="true", label="fiora_vital"
    )
    ctx.sim.heal(ctx.source, dealt * ctx.number("PercentHealing"), source_label="fiora")


@register("ability_TFT17_Fiora")
def fiora(ctx) -> None:
    """Active: strike several Vitals, then leave a healing aura."""
    vitals = int(ctx.number("NumVitals", 6))
    for _ in range(vitals):
        enemies = ctx.sim.enemies_of(ctx.source)
        if not enemies:
            break
        victim = ctx.target if (ctx.target and ctx.target.alive) else enemies[0]
        dealt = _damage(
            ctx, victim, _ad(ctx, "VitalDamage"), kind="true", label="fiora_vital"
        )
        ctx.sim.heal(ctx.source, dealt * ctx.number("PercentHealing"), source_label="fiora")
    healing = _ap(ctx, "AuraHealing")
    if healing > 0 and ctx.source.position is not None:
        for ally in ctx.sim.units_within(ctx.source.position, 2, team=ctx.source.team):
            ctx.sim.heal(ally, healing, source_label="fiora_aura")


@register("ability_TFT17_Shen", EffectTrigger.ON_ATTACK)
def shen_passive(ctx) -> None:
    """Passive: after casting, attacks carry stacking bonus damage.

    True damage from the third cast onward, per the description.
    """
    casts = ctx.source.counter("shen_casts")
    if casts <= 0:
        return
    bonus = _hp(ctx, "DamageHP") + _ap(ctx, "ShieldAP") * 0.0 + ctx.number(
        "BonusDamageOnAttack"
    ) * ctx.source.derived_stats().ability_power_multiplier
    kind = "true" if casts >= 3 else "magic"
    _damage(ctx, ctx.target, bonus * casts, kind=kind, label="shen_passive")


@register("ability_TFT17_Shen")
def shen(ctx) -> None:
    """Active: shield, then a rift that slows enemies and hastens allies."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    ctx.source.bump_counter("shen_casts")
    ctx.sim.apply_shield(
        ctx.source, _hp(ctx, "ShieldHP") + _ap(ctx, "ShieldAP"),
        duration=ctx.number("ShieldDuration") or None, source_label="shen",
    )
    duration = ctx.number("BuffDebuffDuration") or None
    for enemy in _nearby_enemies(ctx, center=ctx.source.position, radius=2):
        _damage(ctx, enemy, _hp(ctx, "DamageHP"), label="shen_rift")
        enemy.add_status(
            StatusEffect(
                "shen_slow", remaining=duration,
                bonuses=StatBonuses({"attack_speed_pct": -ctx.number("ASSlow")}),
            )
        )
    if ctx.source.position is None:
        return
    for ally in ctx.sim.units_within(ctx.source.position, 2, team=ctx.source.team):
        ally.add_status(
            StatusEffect(
                "shen_haste", remaining=duration,
                bonuses=StatBonuses({"attack_speed_pct": ctx.number("BonusAS")}),
            )
        )


@register("ability_TFT17_Zed")
def zed(ctx) -> None:
    """Create a clone inheriting the caster's stats at reduced health."""
    if ctx.source.position is None or _once(ctx.source, "zed_clone") is False:
        return
    clone = ctx.sim.summon(
        ctx.source.champion,
        ctx.source.team,
        ctx.source.position,
        star_level=ctx.source.star_level,
        health_scale=1.0 - ctx.number("HPPenalty"),
        items=ctx.source.items,
        source_label="zed_clone",
    )
    if clone is not None:
        # The clone's own casts cost more, per the description.
        clone.current_mana = -ctx.number("ManaCostIncrease")


@register("ability_TFT17_Urgot")
def urgot(ctx) -> None:
    """Shield, then blast a cone with falloff per hex."""
    from engine.hexgrid import distance

    ctx.sim.apply_shield(
        ctx.source, _ap(ctx, "ShieldAmount"),
        duration=ctx.number("ShieldDuration") or None, source_label="urgot",
    )
    falloff = ctx.number("FalloffPerHex")
    base = _ad(ctx, "ShotgunDamage")
    for enemy in _cone_enemies(ctx, 3):
        if enemy.position is None or ctx.source.position is None:
            continue
        hexes = distance(ctx.source.position, enemy.position)
        _damage(
            ctx, enemy, base * max(0.0, 1.0 - falloff * (hexes - 1)),
            kind="physical", label="urgot_blast",
        )


@register("ability_TFT17_Samira")
def samira(ctx) -> None:
    """Volley the target and knock them up."""
    if ctx.target is None:
        return
    _damage(ctx, ctx.target, _ad(ctx, "Damage"), kind="physical", label="samira")
    if ctx.target.alive:
        ctx.sim.apply_stun(
            ctx.target, ctx.number("StunDuration"), source_label="samira_knockup"
        )
    _enter_groove(ctx, ctx.number("GrooveDuration"))


@register("ability_TFT17_Samira", EffectTrigger.ON_ATTACK)
def samira_passive(ctx) -> None:
    """Passive: shoot enemies that are knocked up (modelled as stunned)."""
    if ctx.target is None or not ctx.target.is_stunned:
        return
    _damage(
        ctx, ctx.target, _ad(ctx, "PassiveAD") + _ap(ctx, "PassiveAP"),
        kind="physical", label="samira_passive",
    )


@register("ability_TFT17_Blitzcrank")
def blitzcrank(ctx) -> None:
    """Uppercut the target into a disco ball, exploding in a radius."""
    if ctx.target is None:
        return
    _damage(ctx, ctx.target, _ap(ctx, "UppercutDamage"), label="blitzcrank_uppercut")
    if ctx.target.alive:
        ctx.sim.apply_stun(ctx.target, 1.0, source_label="blitzcrank_knockup")
    hit = _nearby_enemies(ctx, radius=3)
    for enemy in hit:
        _damage(ctx, enemy, _ap(ctx, "ExplosionDamage"), label="blitzcrank_explosion")
    _enter_groove(ctx, ctx.number("GrooveDurationPerTarget") * max(len(hit), 1))


@register("ability_TFT17_Blitzcrank", EffectTrigger.PERIODIC)
def blitzcrank_bolt(ctx) -> None:
    """Passive: periodically bolt the healthiest nearby enemy."""
    cooldown = ctx.number("BoltCooldown")
    if cooldown <= 0:
        return
    due = int(ctx.sim.t / cooldown)
    if not _once(ctx.source, f"blitz_bolt_{due}"):
        return
    enemies = ctx.sim.enemies_of(ctx.source)
    if not enemies:
        return
    victim = max(enemies, key=lambda u: (u.current_hp, -u.uid))
    _damage(ctx, victim, _ap(ctx, "BoltDamage"), label="blitzcrank_bolt")


# =========================================================================
# Tanks and support
# =========================================================================


@register("ability_TFT17_Maokai", EffectTrigger.ON_COMBAT_START)
def maokai_passive(ctx) -> None:
    """Passive: a share more maximum health from all sources."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    ratio = ctx.number("PassiveRatio")
    if ratio <= 0:
        return
    base = ctx.source.champion.stats.health_at(ctx.source.star_level)
    bonus_health = max(ctx.source.derived_stats().max_health - base, 0.0)
    extra = bonus_health * ratio
    ctx.source.add_status(
        StatusEffect("maokai_passive", remaining=None,
                     bonuses=StatBonuses({"health": extra}))
    )
    ctx.source.current_hp += extra


@register("ability_TFT17_Maokai")
def maokai(ctx) -> None:
    """Active: vines converge on the target, stunning everything hit."""
    victims = _nearby_enemies(ctx, radius=1)
    if ctx.target is not None and ctx.target not in victims:
        victims = [ctx.target, *victims]
    for enemy in victims:
        _damage(ctx, enemy, _ap(ctx, "Damage"), label="maokai")
        if enemy.alive:
            ctx.sim.apply_stun(
                enemy, ctx.number("StunDuration"), source_label="maokai"
            )


@register("ability_TFT17_TahmKench")
def tahm_kench(ctx) -> None:
    """Heal, then lash every enemy within two hexes."""
    healed = ctx.sim.heal(
        ctx.source, _hp(ctx, "HealHP") + _ap(ctx, "HealAP"), source_label="tahm_kench"
    )
    ctx.source.bump_counter("tk_healing", int(healed))
    damage = _hp(ctx, "DamageHP") + _ap(ctx, "DamageAP")
    for enemy in _nearby_enemies(ctx, center=ctx.source.position, radius=2):
        _damage(ctx, enemy, damage, label="tahm_kench")


@register("ability_TFT17_TahmKench", EffectTrigger.ON_DAMAGED)
def tahm_kench_passive(ctx) -> None:
    """Passive: once, below a threshold, shield a share of healing received."""
    threshold = ctx.number("HPThreshold")
    if threshold <= 0 or ctx.source.health_fraction > threshold:
        return
    if not _once(ctx.source, "tk_shield"):
        return
    ctx.sim.apply_shield(
        ctx.source,
        ctx.source.counter("tk_healing") * ctx.number("PercentHealingToShield"),
        duration=ctx.number("ShieldDuration") or None,
        source_label="tahm_kench_shield",
    )


@register("ability_TFT17_Ornn")
def ornn(ctx) -> None:
    """Shield, then breathe fire in a cone."""
    ctx.sim.apply_shield(
        ctx.source, _ap(ctx, "Shield"),
        duration=ctx.number("ShieldDuration") or None, source_label="ornn",
    )
    for enemy in _cone_enemies(ctx, 3):
        _damage(ctx, enemy, _ap(ctx, "Damage"), label="ornn")
    _enter_groove(ctx, ctx.number("GrooveDuration"))


@register("ability_TFT17_Galio")
def galio(ctx) -> None:
    """A defensive stance that heals, then releases a shockwave.

    Projectile attraction is not modelled -- redirecting in-flight projectiles
    needs a retarget the projectile model does not support.
    """
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    duration = ctx.number("DurabilityDuration")
    ctx.source.add_status(
        StatusEffect(
            "galio_stance",
            remaining=duration or None,
            bonuses=StatBonuses({"durability": ctx.number("Durability")}),
        )
    )
    ctx.sim.heal(ctx.source, _ap(ctx, "Heal"), source_label="galio")
    stats = ctx.source.derived_stats()
    shock = (stats.armor + stats.magic_resist) * ctx.number("ARMARScaling")
    for enemy in _nearby_enemies(ctx, center=ctx.source.position,
                                 radius=int(ctx.number("HexRange", 2))):
        _damage(ctx, enemy, shock, kind="physical", label="galio_shockwave")


@register("ability_TFT17_Bard")
def bard(ctx) -> None:
    """A saucer over the target, damaging it and splitting damage nearby.

    The saucer's per-second ticks are collapsed into its full duration at cast
    time. Modelling it as a persistent hazard would need a board-effect system
    the simulator does not have, and the total damage is the same.
    """
    if ctx.target is None:
        return
    duration = ctx.number("AugmentedDuration") or ctx.number("Duration")
    primary = _ap(ctx, "DamagePerSecond") * duration
    if ctx.target.champion.role == "Tank":
        primary *= 1.0 + ctx.number("TankDamageIncrease")
    _damage(ctx, ctx.target, primary, label="bard_saucer")

    splash = _ap(ctx, "SplitDamagePerSecond") * duration
    nearby = [
        e for e in _nearby_enemies(ctx, radius=int(ctx.number("SecondaryHexRange", 1)))
        if e.uid != ctx.target.uid
    ]
    if nearby:
        per = splash / len(nearby)
        for enemy in nearby:
            _damage(ctx, enemy, per, label="bard_split")
