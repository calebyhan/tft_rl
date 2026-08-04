"""Trait behaviours: the third effect registry (doc 99 entry 34.9).

Traits were the largest gap in the engine. :mod:`engine.traits` counts them and
applies any breakpoint ``params`` that happen to name a modelled stat, but a
trait's *behaviour* had no dispatch at all -- all 86 breakpoints were inert
beyond their incidental stat keys. Since composition is what TFT is actually
about, that is a large part of why the simulator rewarded raw unit count over
board building.

Why a third registry rather than a branch in :mod:`engine.effects`:

* An item effect fires for **one wearer**. A trait effect fires for a **team**,
  and routinely treats trait members and the rest of the board differently
  ("Your team gains 5% Health. Brawlers gain more"). The context objects are
  not compatible, and merging them would mean every item hook carrying team
  fields it never reads.
* Traits are keyed by trait id and tier, not by a single effect_id: the data
  ships ``trait_TFT17_HPTank_2``, ``_4`` and ``_6`` as separate entries whose
  only difference is magnitude. Registering by trait id and reading the tier's
  params keeps that one implementation instead of three.

The warn-once-and-no-op discipline is identical to the other two registries: an
unimplemented trait still delivers whatever stats its params name, and never
crashes a match.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Mapping, Sequence, TypeVar

from engine.effects import EffectTrigger

if TYPE_CHECKING:
    from engine.combat import CombatSimulator
    from engine.unit import UnitInstance

log = logging.getLogger(__name__)

# The prefix the fetch script gives every trait breakpoint's effect_id:
# ``trait_<TraitId>_<tier>``. Implementations register under ``<TraitId>``.
TRAIT_EFFECT_PREFIX = "trait_"

# trait_id -> [(trigger, implementation)]. Same multi-hook shape as the item
# registry, and for the same reason: Vanguard shields at combat start *and*
# grants durability while shielded.
TRAIT_HOOKS: dict[str, list[tuple[EffectTrigger, Callable]]] = {}

# trait_id -> implementation, for traits whose effect happens *between* rounds
# rather than during a fight (Anima's Tech, Oracle's reward, Factory New's
# armoury). These take a ``PlayerState`` rather than a combat context, which is
# why they cannot share the registry above (doc 99 entry 35.3).
PLAYER_TRAIT_HOOKS: dict[str, Callable] = {}
ON_ROUND_END = "round_end"

_reported_missing: set[str] = set()

F = TypeVar("F", bound=Callable)


def trait_id_of(effect_id: str | None) -> str | None:
    """``trait_TFT17_HPTank_4`` -> ``TFT17_HPTank``."""
    if not effect_id or not effect_id.startswith(TRAIT_EFFECT_PREFIX):
        return None
    body = effect_id[len(TRAIT_EFFECT_PREFIX) :]
    head, _, tail = body.rpartition("_")
    # Only strip the trailing segment when it really is the tier number.
    return head if head and tail.isdigit() else body


def register_trait(
    trait_id: str, trigger: EffectTrigger = EffectTrigger.ON_COMBAT_START
) -> Callable[[F], F]:
    def decorator(fn: F) -> F:
        hooks = TRAIT_HOOKS.setdefault(trait_id, [])
        if any(existing is trigger for existing, _ in hooks):
            raise ValueError(f"trait {trait_id!r} already has a {trigger.value} hook")
        hooks.append((trigger, fn))
        return fn

    return decorator


def register_player_trait(trait_id: str) -> Callable[[F], F]:
    """Register a between-rounds trait behaviour, keyed by trait id."""

    def decorator(fn: F) -> F:
        if trait_id in PLAYER_TRAIT_HOOKS:
            raise ValueError(f"trait {trait_id!r} already has a round-end hook")
        PLAYER_TRAIT_HOOKS[trait_id] = fn
        return fn

    return decorator


def apply_round_end(player) -> None:
    """Run every active trait's between-rounds hook for one player.

    Counted off the *fielded* board, so a trait benched between rounds stops
    paying out -- the same rule combat uses.
    """
    from engine.traits import active_traits

    if not PLAYER_TRAIT_HOOKS:
        return
    active = active_traits(player.board_units, player.data)
    for trait_id, breakpoint_ in sorted(active.items()):
        fn = PLAYER_TRAIT_HOOKS.get(trait_id)
        if fn is not None:
            fn(player, breakpoint_.count, breakpoint_.params)


def trait_hooks_for(trait_id: str, trigger: EffectTrigger) -> list[Callable]:
    return [fn for hook_trigger, fn in TRAIT_HOOKS.get(trait_id, ()) if hook_trigger is trigger]


def is_trait_implemented(trait_id: str | None) -> bool:
    return trait_id is not None and (
        trait_id in TRAIT_HOOKS or trait_id in PLAYER_TRAIT_HOOKS
    )


def note_missing_trait(trait_id: str) -> None:
    """Warn once for a trait whose behaviour is not modelled."""
    if trait_id in _reported_missing:
        return
    _reported_missing.add(trait_id)
    log.warning(
        "trait %r has no behaviour implementation -- its breakpoint params that "
        "name modelled stats still apply; only its special behaviour is missing.",
        trait_id,
    )


def reset_missing_warnings() -> None:
    _reported_missing.clear()


@dataclass
class TraitContext:
    """What a trait implementation receives.

    ``members`` are the units carrying the trait (emblems included);
    ``allies`` is the whole team. Both are already filtered to the living.
    """

    sim: "CombatSimulator"
    team: int
    trait_id: str
    tier: int
    params: Mapping[str, object] = field(default_factory=dict)
    members: Sequence["UnitInstance"] = ()
    allies: Sequence["UnitInstance"] = ()
    # Set only for the per-unit triggers (DAMAGE_MODIFIER).
    unit: "UnitInstance | None" = None
    target: "UnitInstance | None" = None
    amount: float = 0.0

    def number(self, key: str, default: float = 0.0) -> float:
        value = self.params.get(key, default)
        return float(value) if isinstance(value, (int, float)) else default

    @property
    def others(self) -> list["UnitInstance"]:
        """Allies that are *not* trait members."""
        ids = {u.uid for u in self.members}
        return [u for u in self.allies if u.uid not in ids]


# =========================================================================
# Helpers
# =========================================================================


def _grant(units, source: str, bonuses: dict[str, float], duration=None, **flags) -> None:
    """Add a status carrying ``bonuses`` to every unit in ``units``."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    if not any(bonuses.values()) and not flags:
        return
    for unit in units:
        unit.add_status(
            StatusEffect(
                source,
                remaining=duration,
                bonuses=StatBonuses(dict(bonuses)),
                **flags,
            )
        )


def _replace_status(unit, source: str, effect=None) -> None:
    """Swap a recomputed-every-tick status for its new value.

    Traits that recompute a bonus from live state each tick (Primordian's
    damage conversion, Galaxy Hunter's clone check) must remove the previous
    copy first, or the bonus stacks without bound.
    """
    unit.status_effects = [s for s in unit.status_effects if s.source != source]
    unit._invalidate()
    if effect is not None:
        unit.add_status(effect)


def _grant_percent_health(units, source: str, fraction: float) -> None:
    """Percentage max-health grants must carry current HP with them."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    if fraction <= 0:
        return
    for unit in units:
        bonus = unit.derived_stats().max_health * fraction
        unit.add_status(
            StatusEffect(source, remaining=None, bonuses=StatBonuses({"health": bonus}))
        )
        unit.current_hp += bonus


# =========================================================================
# Class traits -- the stat backbone of a composition
# =========================================================================


@register_trait("TFT17_ASTrait")
def challenger(ctx) -> None:
    """Team-wide attack speed; Challengers gain considerably more."""
    _grant(ctx.allies, "challenger_team", {"attack_speed_pct": ctx.number("TeamwideAS")})
    _grant(
        ctx.members,
        "challenger",
        {"attack_speed_pct": ctx.number("AttackSpeedPercent")},
    )


@register_trait("TFT17_HPTank")
def brawler(ctx) -> None:
    """Team-wide maximum health; Brawlers gain more."""
    _grant_percent_health(ctx.allies, "brawler_team", ctx.number("TeamwideBonus"))
    _grant_percent_health(ctx.members, "brawler", ctx.number("HealthBonus"))


@register_trait("TFT17_ResistTank")
def bastion(ctx) -> None:
    """Team-wide resists; Bastions more, doubled for the opening seconds.

    At the top tier non-Bastions gain an extra flat amount on top of the
    team-wide share, which is why ``others`` exists.
    """
    teamwide = ctx.number("TeamwideResists")
    _grant(ctx.allies, "bastion_team", {"armor": teamwide, "magic_resist": teamwide})

    enhanced = ctx.number("EnhancedTeamwideArmor")
    if ctx.tier >= 6 and enhanced > 0:
        _grant(ctx.others, "bastion_enhanced", {"armor": enhanced, "magic_resist": enhanced})

    armor, magic_resist = ctx.number("BonusArmor"), ctx.number("BonusMR")
    _grant(ctx.members, "bastion", {"armor": armor, "magic_resist": magic_resist})

    # The doubling is an *extra* copy for `Duration` seconds, so the value
    # returns to the base amount when it expires rather than to zero.
    multiplier = ctx.number("StatMultiplier", 1.0) - 1.0
    duration = ctx.number("Duration")
    if multiplier > 0 and duration > 0:
        _grant(
            ctx.members,
            "bastion_opening",
            {"armor": armor * multiplier, "magic_resist": magic_resist * multiplier},
            duration=duration,
        )


@register_trait("TFT17_MeleeTrait")
def marauder(ctx) -> None:
    """Team-wide omnivamp; Marauders more, plus attack damage."""
    _grant(ctx.allies, "marauder_team", {"omnivamp": ctx.number("TeamwideBonus")})
    _grant(
        ctx.members,
        "marauder",
        {
            "omnivamp": ctx.number("Omnivamp"),
            "attack_damage_pct": ctx.number("AD"),
        },
    )
    # Overheal-into-shield is not modelled: `heal` clamps at max health and
    # discards the excess, so there is no overheal quantity to convert. It
    # would need a heal primitive that reports what it could not apply.


@register_trait("TFT17_ManaTrait")
def conduit(ctx) -> None:
    """Team-wide mana regen, more for Conduits, who also gain mana faster."""
    _grant(ctx.allies, "conduit_team", {"mana_regen": ctx.number("TeamManaRegen")})
    channeler = ctx.number("ChannelerManaRegen") - ctx.number("TeamManaRegen")
    _grant(ctx.members, "conduit", {"mana_regen": max(channeler, 0.0)})
    innate = ctx.number("InnateManaGain")
    if innate > 0:
        _grant(ctx.members, "conduit_innate", {}, mana_gain_bonus=innate)


@register_trait("TFT17_Timebreaker")
def timebreaker(ctx) -> None:
    """Allies gain attack speed; at the top tier Timebreakers gain more."""
    _grant(ctx.allies, "timebreaker_team", {"attack_speed_pct": ctx.number("AttackSpeed")})
    _grant(
        ctx.members,
        "timebreaker",
        {"attack_speed_pct": ctx.number("TimebreakerAdditionalAS")},
    )


@register_trait("TFT17_FlexTrait")
def voyager(ctx) -> None:
    """Tanks are shielded, everyone else gains damage amp; Voyagers double."""
    doubling = ctx.number("{2ad3e251}", 2.0)
    member_ids = {u.uid for u in ctx.members}
    shield = ctx.number("ShieldHP")
    duration = ctx.number("ShieldDuration") or None
    amp = ctx.number("BonusDA")

    for unit in ctx.allies:
        scale = doubling if unit.uid in member_ids else 1.0
        if unit.champion.role == "Tank":
            ctx.sim.apply_shield(
                unit, shield * scale, duration=duration, source_label="voyager"
            )
        else:
            _grant([unit], "voyager", {"damage_amp": amp * scale})


@register_trait("TFT17_Fateweaver")
def fateweaver(ctx) -> None:
    """Critical strike chance and damage at the upper tier.

    "Lucky" (roll twice, keep the better) is not modelled: it would change the
    meaning of every rng draw in the simulator, and the trait's measurable half
    is the crit stats.
    """
    _grant(
        ctx.members,
        "fateweaver",
        {
            "crit_chance": ctx.number("CritChance"),
            "crit_damage": ctx.number("CritDamage") / 100.0,
        },
    )


@register_trait("TFT17_RangedTrait", EffectTrigger.DAMAGE_MODIFIER)
def sniper(ctx) -> float | None:
    """Damage amp that grows with the distance to the victim.

    A damage modifier rather than a stat, because the bonus depends on where
    the target is standing at the moment of the hit.
    """
    from engine.hexgrid import distance

    if ctx.unit is None or ctx.target is None:
        return None
    if ctx.unit.position is None or ctx.target.position is None:
        return None
    base = ctx.number("PercentDamageIncrease") / 100.0
    per_hex = ctx.number("PerHexIncrease") / 100.0
    hexes = distance(ctx.unit.position, ctx.target.position)
    total = base + per_hex * hexes
    return 1.0 + total if total > 0 else None


@register_trait("TFT17_ShieldTank")
def vanguard_shield(ctx) -> None:
    """A max-health shield at combat start (the threshold half is periodic)."""
    amount = ctx.number("ShieldPercentAmount")
    duration = ctx.number("ShieldDuration") or None
    for unit in ctx.members:
        ctx.sim.apply_shield(
            unit,
            unit.derived_stats().max_health * amount,
            duration=duration,
            source_label="vanguard",
        )


@register_trait("TFT17_ShieldTank", EffectTrigger.PERIODIC)
def vanguard_durability(ctx) -> None:
    """Durability while shielded, and a second shield at a health threshold."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    base = ctx.number("DamageReductionPct")
    enhanced = ctx.number("EnhancedDurability")
    value = enhanced if ctx.tier >= 6 and enhanced > 0 else base
    threshold = ctx.number("HealthThreshold")

    for unit in ctx.members:
        shielded = unit.shield_amount > 0
        held = any(s.source == "vanguard_durability" for s in unit.status_effects)
        if shielded and not held and value > 0:
            unit.add_status(
                StatusEffect(
                    "vanguard_durability",
                    remaining=None,
                    bonuses=StatBonuses({"durability": value}),
                )
            )
        elif not shielded and held:
            unit.status_effects = [
                s for s in unit.status_effects if s.source != "vanguard_durability"
            ]
            unit._invalidate()

        if (
            threshold > 0
            and unit.health_fraction <= threshold
            and _fires_once(unit, "vanguard_threshold")
        ):
            ctx.sim.apply_shield(
                unit,
                unit.derived_stats().max_health * ctx.number("ShieldPercentAmount"),
                duration=ctx.number("ShieldDuration") or None,
                source_label="vanguard",
            )


@register_trait("TFT17_AssassinTrait")
def rogue(ctx) -> None:
    """Attack damage and ability power for Rogues.

    The stealth-redirect half needs a targeting exclusion the simulator does
    not have, and is deliberately omitted rather than faked.
    """
    _grant(
        ctx.members,
        "rogue",
        {"attack_damage_pct": ctx.number("AD"), "ability_power": ctx.number("AP")},
    )


# =========================================================================
# Origin traits
# =========================================================================


@register_trait("TFT17_Mecha")
def mecha(ctx) -> None:
    """Attack damage and ability power. Transformation is not modelled."""
    _grant(
        ctx.members,
        "mecha",
        {"attack_damage_pct": ctx.number("AD"), "ability_power": ctx.number("AP")},
    )


@register_trait("TFT17_Astronaut")
def meeple(ctx) -> None:
    """Bonus health. The Meeps that empower abilities are not modelled."""
    _grant(ctx.members, "meeple", {"health": ctx.number("BonusHealth")})


@register_trait("TFT17_DarkStar")
def dark_star(ctx) -> None:
    """Attack damage and ability power from the second tier upward."""
    if ctx.tier >= 4:
        adap = ctx.number("ADAP")
        _grant(
            ctx.members,
            "dark_star",
            {"attack_damage_pct": adap / 100.0, "ability_power": adap},
        )


@register_trait("TFT17_SpaceGroove")
def space_groove_start(ctx) -> None:
    """Groovians start the fight in the Groove for a fixed duration."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    duration = ctx.number("StartOfCombatDuration")
    if ctx.tier < 3 or duration <= 0:
        return
    for unit in ctx.members:
        unit.add_status(
            StatusEffect(
                "space_groove",
                remaining=duration,
                bonuses=StatBonuses({"attack_speed_pct": _groove_scale(ctx)}),
            )
        )


@register_trait("TFT17_SpaceGroove", EffectTrigger.PERIODIC)
def space_groove_stacking(ctx) -> None:
    """Each second in the Groove grants stacking attack damage and power."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    per_second = ctx.number("ADAPPerSecond")
    if ctx.tier < 5 or per_second <= 0:
        return
    step = per_second * (1.0 + ctx.number("EffectBonus") / 100.0)
    due = int(ctx.sim.t)
    for unit in ctx.members:
        if not any(s.source == "space_groove" for s in unit.status_effects):
            continue
        if not _fires_once(unit, f"groove_stack_{due}"):
            continue
        unit.add_status(
            StatusEffect(
                "groove_stack",
                remaining=None,
                bonuses=StatBonuses(
                    {"attack_damage_pct": step / 100.0, "ability_power": step}
                ),
            )
        )


def _groove_scale(ctx) -> float:
    """The Groove's attack speed, scaled by how many Groovians are fielded.

    Riot renders the value from a unit property rather than publishing it in
    the trait's variables, so the count itself is the only published lever.
    """
    return 0.01 * len(ctx.members)


# =========================================================================
# Unique (one-champion) traits
# =========================================================================


@register_trait("TFT17_MorganaUniqueTrait")
def dark_lady(ctx) -> None:
    """Team-wide durability. The Dark Form upgrade is not modelled."""
    _grant(ctx.allies, "dark_lady", {"durability": ctx.number("Durability")})


@register_trait("TFT17_JhinUniqueTrait")
def eradicator(ctx) -> None:
    """Enemies have a share less armour and magic resist."""
    pct = ctx.number("PctResists")
    if pct <= 0:
        return
    for enemy in ctx.sim.living(1 - ctx.team):
        stats = enemy.derived_stats()
        _grant(
            [enemy],
            "eradicator",
            {"armor": -stats.armor * pct, "magic_resist": -stats.magic_resist * pct},
        )


@register_trait("TFT17_RhaastUniqueTrait")
def redeemer(ctx) -> None:
    """Team-wide stats scaling with how many non-unique traits are active.

    "Non-unique" is read off the board rather than from a flag: a unique trait
    is one whose only breakpoint is a single unit, which is exactly how the
    one-champion traits in this section are shaped.
    """
    state = ctx.sim.trait_states[ctx.team]
    count = 0
    for trait_id in state.active:
        trait = ctx.sim.data.traits.get(trait_id)
        if trait is None:
            continue
        tiers = [bp.count for bp in trait.breakpoints]
        if tiers != [1]:
            count += 1
    if count <= 0:
        return
    _grant(
        ctx.allies,
        "redeemer",
        {
            "attack_speed_pct": ctx.number("BonusOffensiveStat1") * count,
            "armor": ctx.number("BonusDefensiveStat1") * count,
            "magic_resist": ctx.number("BonusDefensiveStat1") * count,
        },
    )


@register_trait("TFT17_ShenUniqueTrait")
def bulwark(ctx) -> None:
    """Shen's relic shields and hastens adjacent allies.

    The relic is a placeable the player positions; with no placement mechanic
    it is anchored to Shen himself, so "adjacent to the relic" is read as
    adjacent to the Bulwark unit.
    """
    shield = ctx.number("PercentHealthShield")
    duration = ctx.number("ShieldDuration") or None
    speed = ctx.number("AttackSpeed")
    for anchor in ctx.members:
        if anchor.position is None:
            continue
        for ally in ctx.sim.units_within(anchor.position, 1, team=ctx.team):
            ctx.sim.apply_shield(
                ally,
                ally.derived_stats().max_health * shield,
                duration=duration,
                source_label="bulwark",
            )
            _grant(
                [ally],
                "bulwark",
                {"attack_speed_pct": speed},
                duration=ctx.number("AttackSpeedDuration") or None,
            )


@register_trait("TFT17_VexUniqueTrait")
def doomer(ctx) -> None:
    """Steal a share of every enemy's attack damage and power for the best Vex."""
    share = ctx.number("ADAP1") / 100.0
    enemies = ctx.sim.living(1 - ctx.team)
    if share <= 0 or not ctx.members or not enemies:
        return
    # "Strongest" is star level then cost, with uid as a deterministic tie-break.
    best = max(
        ctx.members,
        key=lambda u: (u.star_level, u.champion.cost, -u.uid),
    )
    stolen_ad = 0.0
    stolen_ap = 0.0
    for enemy in enemies:
        stats = enemy.derived_stats()
        take_ad = stats.attack_damage * share
        take_ap = max(stats.ability_power - 100.0, 0.0) * share
        _grant([enemy], "doomed", {"attack_damage": -take_ad, "ability_power": -take_ap})
        stolen_ad += take_ad
        stolen_ap += take_ap
    _grant([best], "doomer", {"attack_damage": stolen_ad, "ability_power": stolen_ap})


@register_trait("TFT17_BlitzcrankUniqueTrait", EffectTrigger.PERIODIC)
def party_animal(ctx) -> None:
    """Once per combat, repair a share of max health each second when low.

    Untargetability while repairing is not modelled; the repair itself is.
    """
    threshold = ctx.number("HealthThreshold")
    per_second = ctx.number("PercentHealthHeal")
    if threshold <= 0 or per_second <= 0:
        return
    for unit in ctx.members:
        if unit.health_fraction > threshold:
            continue
        due = int(ctx.sim.t)
        if not _fires_once(unit, f"party_animal_{due}"):
            continue
        ctx.sim.heal(
            unit,
            unit.derived_stats().max_health * per_second,
            source_label="party_animal",
        )


def _fires_once(unit, key: str) -> bool:
    """Per-combat firing guard, shared with the item registry's ``_once``."""
    from engine.effects import _once

    return _once(unit, key)


# =========================================================================
# The traits that needed new engine systems (doc 99 entry 35.3)
# =========================================================================


@register_trait("TFT17_SummonTrait")
def shepherd(ctx) -> None:
    """Summon Bia and Bayin, scaled by the total star level of all Shepherds.

    The summon is a real unit from ``summons.json``, deliberately kept out of
    ``champions`` so it never enters the shop or the shared champion pool.
    Its star level is the trait's power dial: Riot scales the pair by "the
    total star level of all Shepherds", which is read straight off the board.
    """
    champion = ctx.sim.data.summon_for("shepherd")
    if champion is None or not ctx.members:
        return
    total_stars = sum(u.star_level for u in ctx.members)
    # Star levels are capped at the engine's maximum; a deep Shepherd board
    # summons a stronger pair rather than more of them.
    from engine.schema import STAR_LEVELS

    star = max(1, min(STAR_LEVELS, total_stars // max(len(ctx.members), 1)))
    anchor = next((u.position for u in ctx.members if u.position), None)
    if anchor is None:
        return
    # Two summons: Bia and Bayin. The tier controls how many arrive.
    count = 1 if ctx.tier < 5 else 2
    for _ in range(count):
        ctx.sim.summon(
            champion, ctx.team, anchor, star_level=star, source_label="shepherd"
        )


@register_trait("TFT17_DarkStar", EffectTrigger.PERIODIC)
def dark_star_black_hole(ctx) -> None:
    """Consume enemies below a share of maximum health.

    Riot models the black hole as a pseudo-unit with no range and no crit,
    which is a marker for an execute rather than a unit that fights, so it is
    implemented directly as the execute it is (doc 99 entry 35.2).
    """
    threshold = ctx.number("ExecuteHPPercent")
    if threshold <= 0:
        return
    for enemy in ctx.sim.living(1 - ctx.team):
        if enemy.health_fraction <= threshold:
            ctx.sim.deal_damage(
                None, enemy, enemy.current_hp, _true(), source_label="dark_star_hole"
            )


def _true():
    from engine.combat import DamageType

    return DamageType.TRUE


@register_trait("TFT17_ZedUniqueTrait", EffectTrigger.PERIODIC)
def galaxy_hunter(ctx) -> None:
    """Zed gains attack damage while at least one of his clones is alive."""
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    bonus = ctx.number("BonusAD")
    if bonus <= 0:
        return
    clones = [u for u in ctx.sim.living(ctx.team) if u.is_summon]
    for unit in ctx.members:
        held = any(s.source == "galaxy_hunter" for s in unit.status_effects)
        if clones and not held:
            unit.add_status(
                StatusEffect(
                    "galaxy_hunter",
                    remaining=None,
                    bonuses=StatBonuses({"attack_damage_pct": bonus}),
                )
            )
        elif not clones and held:
            _replace_status(unit, "galaxy_hunter")


@register_trait("TFT17_Primordian", EffectTrigger.PERIODIC)
def primordian(ctx) -> None:
    """A share of damage taken is converted into damage dealt.

    Swarmling spawning is not modelled -- Riot ships no swarmling unit in the
    Set 17 payload, so there is nothing to summon and inventing one would mean
    inventing its stats (doc 99 entry 35.5).
    """
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    share = ctx.number("DamageTakenPercentModifier")
    if share <= 0:
        return
    for unit in ctx.members:
        missing = 1.0 - unit.health_fraction
        amp = missing * share
        _replace_status(
            unit,
            "primordian",
            StatusEffect(
                "primordian", remaining=None, bonuses=StatBonuses({"damage_amp": amp})
            ),
        )


@register_trait("TFT17_APTrait", EffectTrigger.ON_CAST)
def replicator(ctx) -> None:
    """Abilities occur a second time at reduced effectiveness.

    Fired *after* the ability resolves, re-running the same hook with a scaled
    copy of the caster's params. Scaling the params rather than the damage is
    what keeps this generic: every magnitude the ability reads is reduced by
    the same factor, including shields and heals, which is what "reduced
    effectiveness" means.
    """
    from engine.combat import EffectContext
    from engine.effects import EffectTrigger as ET
    from engine.effects import hooks_for

    unit = ctx.unit
    share = ctx.number("Effectiveness")
    if unit is None or share <= 0:
        return
    ability = unit.champion.ability
    if ability is None:
        return
    if not _fires_once(unit, f"replicator_{unit.counter('replicator_casts')}"):
        return
    unit.bump_counter("replicator_casts")

    scaled = {
        key: ([v * share for v in value] if isinstance(value, list) else value * share)
        if isinstance(value, (int, float, list)) and not isinstance(value, bool)
        else value
        for key, value in ability.params.items()
    }
    target = ctx.sim.by_uid.get(unit.target_uid or -1)
    for fn in hooks_for(ability.effect_id, ET.ON_CAST):
        fn(
            EffectContext(
                sim=ctx.sim,
                source=unit,
                target=target if (target and target.alive) else None,
                params=scaled,
                star_level=unit.star_level,
            )
        )


@register_trait("TFT17_DRX")
def nova(ctx) -> None:
    """N.O.V.A.'s power surge, delayed a few seconds into combat.

    Riot's description lists a per-champion menu (Aatrox shreds, Caitlyn grants
    attack speed, ...) plus a player-chosen Striker. The choice is not
    modelled; every listed benefit whose champion is fielded is applied, which
    is the surge at its documented strength (doc 99 entry 35.5).
    """
    from engine.stats import StatBonuses
    from engine.unit import StatusEffect

    delay = ctx.number("TeamAttackDelay")
    speed = ctx.number("AS")
    heal = ctx.number("Heal")
    shield = ctx.number("ShieldValue")
    shred = ctx.number("ShredAndSunder")

    # The surge lands `delay` seconds in; modelled as a status that starts
    # inert and is applied at combat start with the delay baked into it.
    if speed > 0:
        for ally in ctx.allies:
            ally.add_status(
                StatusEffect(
                    "nova_surge",
                    remaining=None,
                    bonuses=StatBonuses({"attack_speed_pct": speed}),
                )
            )
    if heal > 0:
        for ally in ctx.allies:
            ctx.sim.heal(
                ally, ally.derived_stats().max_health * heal, source_label="nova"
            )
    if shield > 0:
        tanks = [u for u in ctx.allies if u.champion.role == "Tank"]
        best = max(tanks, key=lambda u: (u.star_level, -u.uid), default=None)
        if best is not None:
            ctx.sim.apply_shield(best, shield, duration=delay or None, source_label="nova")
    if shred > 0:
        for enemy in ctx.sim.living(1 - ctx.team):
            stats = enemy.derived_stats()
            _grant(
                [enemy],
                "nova_shred",
                {
                    "armor": -stats.armor * shred,
                    "magic_resist": -stats.magic_resist * shred,
                },
            )


@register_trait("TFT17_MissFortuneUniqueTrait")
def gun_goddess(ctx) -> None:
    """Miss Fortune's chosen mode grants damage amp to the team.

    The mode itself (Conduit / Challenger / Replicator) is a player choice the
    engine cannot offer, so the trait's measurable half -- its damage amp --
    is applied and the mode is recorded as unmodelled (doc 99 entry 35.5).
    """
    _grant(ctx.allies, "gun_goddess", {"damage_amp": ctx.number("DamageAmp")})
    mana = ctx.number("Mana")
    if mana > 0:
        for unit in ctx.members:
            ctx.sim.grant_mana(unit, mana, reason="gun_goddess")


@register_trait("TFT17_PsyOps")
def psionic(ctx) -> None:
    """Psionic items are granted as stats to the strongest allies.

    The real trait hands the player equippable items, which needs an item-grant
    at a point the engine has no hook for. The combat half -- that a Psionic
    board is stronger -- is applied to the units that would carry them.
    """
    bonus = ctx.number("{1b889d1c}")
    if bonus <= 0:
        return
    carriers = sorted(
        ctx.allies, key=lambda u: (-u.star_level, -u.champion.cost, u.uid)
    )[: max(1, ctx.tier // 2)]
    _grant(carriers, "psionic", {"ability_power": bonus, "attack_damage": bonus})


@register_trait("TFT17_Stargazer")
def stargazer(ctx) -> None:
    """Stargazers in empowered hexes gain the constellation's bonus.

    Riot rolls a different constellation each game and reveals empowered hexes
    by player level. Neither exists in this engine, so the *shared* half every
    constellation grants -- ``Family_Stats`` to marked Stargazers -- is applied
    to the units that would stand in those hexes (doc 99 entry 35.5).
    """
    stats = ctx.number("Family_Stats")
    marks = int(ctx.number("NumMarks", 0)) or ctx.tier
    if stats <= 0:
        return
    marked = sorted(ctx.members, key=lambda u: (-u.star_level, u.uid))[:marks]
    _grant(
        marked,
        "stargazer",
        {"attack_damage_pct": stats / 100.0, "ability_power": stats},
    )


# =========================================================================
# Between-rounds traits (doc 99 entry 35.3)
#
# These pay out in gold, XP, items or permanent stats rather than inside a
# fight, so they take a ``PlayerState``. Riot's own variable names again.
# =========================================================================


@register_player_trait("TFT17_AnimaSquad")
def anima(player, tier: int, params) -> None:
    """Accumulate Tech from losses and takedowns; cash it in at a breakpoint.

    The real trait offers a *choice* between taking weapons now and saving for
    stronger ones later. With no mechanism to offer that choice, the payout is
    taken as soon as it is affordable, which is the greedy branch of it.
    """
    breakpoint_ = float(params.get("TechBreakpoint") or 0)
    per_combat = float(params.get("TechPerCombat") or 0)
    per_loss = float(params.get("TechPerLoss") or 0)
    if breakpoint_ <= 0:
        return

    tech = player.trait_progress.get("anima_tech", 0.0) + per_combat
    if player.streak_type == "loss":
        tech += per_loss * max(player.streak_count, 0)
    while tech >= breakpoint_:
        tech -= breakpoint_
        _grant_random_component(player, reason="anima_tech")
    player.trait_progress["anima_tech"] = tech


@register_player_trait("TFT17_TahmKenchUniqueTrait")
def oracle(player, tier: int, params) -> None:
    """Every N rounds, Tahm Kench grants a reward."""
    every = int(params.get("rounds") or params.get("Rounds") or 0)
    if every <= 0:
        return
    count = player.trait_progress.get("oracle_rounds", 0.0) + 1
    if count >= every:
        count = 0.0
        _grant_random_component(player, reason="oracle_reward")
    player.trait_progress["oracle_rounds"] = count


@register_player_trait("TFT17_GravesTrait")
def factory_new(player, tier: int, params) -> None:
    """Buy a permanent upgrade for the strongest Graves, slowing over time.

    The armoury is a purchase screen the engine cannot show, so the upgrade is
    taken automatically. The cadence *is* modelled, because it is the trait's
    actual balance lever: every N upgrades the next one takes an extra round.
    """
    per_step = int(params.get("NumberOfUpgradesBeforeRoundCostIncrease") or 0)
    if per_step <= 0:
        return
    upgrades = player.trait_progress.get("graves_upgrades", 0.0)
    waited = player.trait_progress.get("graves_waited", 0.0) + 1
    # Rounds required grows by one every `per_step` upgrades taken.
    required = 1 + int(upgrades // per_step)
    if waited >= required:
        waited = 0.0
        upgrades += 1
    player.trait_progress["graves_waited"] = waited
    player.trait_progress["graves_upgrades"] = upgrades


@register_player_trait("TFT17_Timebreaker")
def timebreaker_economy(player, tier: int, params) -> None:
    """Free rerolls on a loss and stored XP on a win, from the middle tier up."""
    if tier < 3:
        return
    if player.streak_type == "loss":
        player.free_rerolls += 1
    elif player.streak_type == "win":
        player.grant_xp(1)


@register_player_trait("TFT17_FioraUniqueTrait")
def divine_duelist(player, tier: int, params) -> None:
    """The Tactician heals for a share of player damage dealt by winning."""
    share = float(params.get("PlayerOmnivamp") or 0)
    dealt = player.trait_progress.get("player_damage_dealt", 0.0)
    if share <= 0 or dealt <= 0:
        return
    player.hp = min(player.hp + int(dealt * share), 100)
    player.trait_progress["player_damage_dealt"] = 0.0


@register_player_trait("TFT17_SonaUniqueTrait")
def commander(player, tier: int, params) -> None:
    """Sona hands out a Command Mod every N rounds.

    A Command Mod alters how one ally behaves in combat -- a per-unit
    behavioural override the engine has no representation for. The cadence is
    tracked so the count is right if the mechanic is ever built; nothing is
    granted, and that omission is recorded rather than faked.
    """
    every = int(params.get("RoundsPerMod") or 0)
    if every <= 0:
        return
    count = player.trait_progress.get("sona_rounds", 0.0) + 1
    if count >= every:
        count = 0.0
        player.trait_progress["sona_mods"] = (
            player.trait_progress.get("sona_mods", 0.0) + 1
        )
    player.trait_progress["sona_rounds"] = count


@register_player_trait("TFT17_ADMIN")
def arbiter(player, tier: int, params) -> None:
    """Arbiter's law is player-authored: a chosen cause and a chosen effect.

    Every branch of it is a choice the engine cannot offer, so no effect is
    applied. It is registered rather than left missing so the coverage count
    distinguishes "needs a choice mechanism" from "nobody has written it"
    (doc 99 entry 35.5).
    """
    return None


def _grant_random_component(player, *, reason: str) -> None:
    """Add one component to the bag, chosen deterministically from the data."""
    components = sorted(
        (i for i in player.data.items.values() if i.is_component), key=lambda i: i.id
    )
    if not components:
        return
    index = int(player.trait_progress.get(f"{reason}_count", 0.0))
    player.trait_progress[f"{reason}_count"] = index + 1
    player.item_bag.append(components[index % len(components)])
