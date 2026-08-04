"""Tick-based combat simulator (doc 01 sec 3, doc 03 sec 2.9).

Combat advances in fixed time steps (``config.combat.tick_seconds``). Each tick
every living unit, in a stable order, runs the state machine from doc 01
sec 3.1:

1. tick status effects, shields and cooldowns
2. skip acting if stunned
3. select a target (nearest enemy by default)
4. cast if the ability is ready -- casting interrupts moving and attacking
5. otherwise move one hex toward the target if out of range
6. otherwise progress the attack timer and auto-attack when it completes
7. resolve deaths
8. end when one side is empty, or the stall-breaker/timeout fires

**Determinism**: every random decision (crit rolls, targeting tie-breaks) draws
from a ``random.Random`` owned by the simulator and seeded explicitly. The
global ``random`` module is never touched, so a seed fully determines a fight.
Ordering tie-breaks use unit ``uid``, which is allocated from a process-global
counter -- their *relative* order is fixed by the order units are constructed,
so a given seed plus a given build sequence always replays identically, but the
absolute uid numbers printed in a log differ between processes.

Everything the simulator does is recorded in a :class:`CombatLog` of
timestamped events -- the primary way to verify mechanics and debug fights.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Iterable, Mapping, Sequence

# `abilities` and `trait_effects` are imported for their registration side
# effects: both populate the effect registries at import time, and combat is
# the module that dispatches them.
from engine import abilities as _abilities  # noqa: F401
from engine import effects, trait_effects
from engine.effects import EffectTrigger, _once
from engine.hexgrid import Board, Hex, distance, spread
from engine.schema import CombatConfig, GameData
from engine.traits import TraitState, unit_traits
from engine.unit import Shield, StatusEffect, UnitInstance

log = logging.getLogger(__name__)


class DamageType(str, Enum):
    PHYSICAL = "physical"
    MAGIC = "magic"
    TRUE = "true"


class EventKind(str, Enum):
    COMBAT_START = "combat_start"
    TARGET = "target"
    MOVE = "move"
    ATTACK = "attack"
    PROJECTILE_LAUNCH = "projectile_launch"
    PROJECTILE_FIZZLE = "projectile_fizzle"
    DAMAGE = "damage"
    HEAL = "heal"
    SHIELD = "shield"
    MANA = "mana"
    CAST = "cast"
    CAST_SKIPPED = "cast_skipped"
    STATUS = "status"
    DEATH = "death"
    SUDDEN_DEATH = "sudden_death"
    SUMMON = "summon"
    COMBAT_END = "combat_end"


# --- combat log ----------------------------------------------------------


@dataclass(frozen=True)
class CombatEvent:
    t: float
    tick: int
    kind: EventKind
    actor: int | None = None
    target: int | None = None
    detail: Mapping[str, object] = field(default_factory=dict)


class CombatLog:
    """An ordered, timestamped record of everything that happened in a fight."""

    def __init__(self) -> None:
        self.events: list[CombatEvent] = []
        self._names: dict[int, str] = {}

    def name_of(self, uid: int | None) -> str:
        if uid is None:
            return "-"
        return self._names.get(uid, f"unit#{uid}")

    def register(self, unit: UnitInstance) -> None:
        self._names[unit.uid] = f"{unit.name}#{unit.uid}(T{unit.team})"

    def add(
        self,
        t: float,
        tick: int,
        kind: EventKind,
        actor: UnitInstance | None = None,
        target: UnitInstance | None = None,
        **detail: object,
    ) -> CombatEvent:
        event = CombatEvent(
            t=round(t, 4),
            tick=tick,
            kind=kind,
            actor=actor.uid if actor else None,
            target=target.uid if target else None,
            detail=detail,
        )
        self.events.append(event)
        return event

    def of_kind(self, *kinds: EventKind) -> list[CombatEvent]:
        wanted = set(kinds)
        return [e for e in self.events if e.kind in wanted]

    def for_unit(self, uid: int) -> list[CombatEvent]:
        return [e for e in self.events if e.actor == uid or e.target == uid]

    def format_line(self, event: CombatEvent) -> str:
        actor = self.name_of(event.actor)
        target = self.name_of(event.target)
        detail = " ".join(
            f"{k}={v:.4g}" if isinstance(v, float) else f"{k}={v}"
            for k, v in event.detail.items()
        )
        arrow = f" -> {target}" if event.target is not None else ""
        return f"[{event.t:6.2f}s] {event.kind.value:<18} {actor}{arrow} {detail}".rstrip()

    def render(self, kinds: Iterable[EventKind] | None = None) -> str:
        wanted = set(kinds) if kinds else None
        return "\n".join(
            self.format_line(e)
            for e in self.events
            if wanted is None or e.kind in wanted
        )

    def __len__(self) -> int:
        return len(self.events)


# --- results -------------------------------------------------------------


@dataclass(frozen=True)
class CombatResult:
    """Outcome of one fight. ``winner`` is ``None`` for a draw."""

    winner: int | None
    survivors: tuple[UnitInstance, ...]
    duration: float
    ticks: int
    log: CombatLog
    timed_out: bool

    @property
    def survivor_summary(self) -> list[tuple[str, int, float]]:
        return [(u.champion.id, u.star_level, round(u.current_hp, 1)) for u in self.survivors]


# --- targeting -----------------------------------------------------------

TargetingRule = Callable[[UnitInstance, Sequence[UnitInstance]], UnitInstance | None]


def _nearest(unit: UnitInstance, enemies: Sequence[UnitInstance]) -> UnitInstance | None:
    """TFT's default: nearest enemy, ties broken by uid for determinism."""
    if not enemies:
        return None
    return min(enemies, key=lambda e: (distance(unit.position, e.position), e.uid))


def _lowest_health(unit: UnitInstance, enemies: Sequence[UnitInstance]) -> UnitInstance | None:
    if not enemies:
        return None
    return min(enemies, key=lambda e: (e.current_hp, e.uid))


def _highest_attack_damage(
    unit: UnitInstance, enemies: Sequence[UnitInstance]
) -> UnitInstance | None:
    if not enemies:
        return None
    return max(enemies, key=lambda e: (e.derived_stats().attack_damage, -e.uid))


TARGETING_RULES: dict[str, TargetingRule] = {
    "nearest": _nearest,
    "lowest_health": _lowest_health,
    "highest_attack_damage": _highest_attack_damage,
}
DEFAULT_TARGETING_RULE = "nearest"


# --- projectiles ---------------------------------------------------------


@dataclass
class Projectile:
    """An in-flight ranged auto-attack (doc 01 sec 3.1 step 5)."""

    source_uid: int
    target_uid: int
    remaining: float
    raw_damage: float
    damage_type: DamageType
    is_crit: bool


@dataclass
class Burn:
    """A damage-over-time applied to one unit (Morellonomicon, Sunfire Cape).

    Burn damage in TFT is a share of the *target's* maximum health per second,
    dealt as true damage on a fixed tick rate rather than continuously. Only
    the strongest burn on a unit applies, which is why :meth:`apply_burn`
    replaces rather than appends.
    """

    source_uid: int | None
    target_uid: int
    remaining: float
    pct_max_hp_per_tick: float
    tick_interval: float
    until_next_tick: float
    source_label: str = ""


# --- effect plumbing -----------------------------------------------------


@dataclass
class EffectContext:
    """What an ``effect_id`` implementation receives (doc 03 sec 2.4)."""

    sim: "CombatSimulator"
    source: UnitInstance
    target: UnitInstance | None = None
    params: Mapping[str, object] = field(default_factory=dict)
    star_level: int = 1
    amount: float = 0.0
    damage_type: DamageType | None = None
    is_crit: bool = False

    def param(self, key: str, default: object = None) -> object:
        """Read a param, indexing per-star lists by the caster's star level."""
        if key not in self.params:
            return default
        value = self.params[key]
        if isinstance(value, (list, tuple)):
            return value[self.star_level - 1]
        return value

    def number(self, key: str, default: float = 0.0) -> float:
        value = self.param(key, default)
        return float(value) if isinstance(value, (int, float)) else default


# --- the simulator -------------------------------------------------------


class CombatSimulator:
    """Runs one fight between two already-positioned teams."""

    def __init__(
        self,
        team0: Sequence[UnitInstance],
        team1: Sequence[UnitInstance],
        data: GameData,
        *,
        seed: int = 0,
        board: Board | None = None,
        config: CombatConfig | None = None,
    ) -> None:
        self.data = data
        self.config = config or data.config.combat
        self.board = board or Board()
        self.rng = random.Random(seed)
        self.seed = seed
        self.log = CombatLog()

        self.teams: tuple[list[UnitInstance], list[UnitInstance]] = (
            list(team0),
            list(team1),
        )
        self.units: list[UnitInstance] = [*self.teams[0], *self.teams[1]]
        self.by_uid: dict[int, UnitInstance] = {u.uid: u for u in self.units}
        self.projectiles: list[Projectile] = []
        self.burns: dict[int, Burn] = {}

        self.t = 0.0
        self.tick_index = 0
        self._move_timers: dict[int, float] = {}
        self._finished = False
        self._sudden_death_logged = False

        self._prepare()

    # -- setup ------------------------------------------------------------

    def _prepare(self) -> None:
        for team_index, team in enumerate(self.teams):
            for unit in team:
                if unit.position is None:
                    raise ValueError(
                        f"{unit!r} has no position; place units before combat"
                    )
                if unit.position not in self.board:
                    raise ValueError(f"{unit!r} is positioned off the board")
                unit.team = team_index

        occupied: dict[Hex, int] = {}
        for unit in self.units:
            if unit.position in occupied:
                raise ValueError(
                    f"two units occupy {unit.position}: "
                    f"#{occupied[unit.position]} and #{unit.uid}"
                )
            occupied[unit.position] = unit.uid

        # Traits are fixed for the fight, so resolve them once up front.
        self.trait_states = tuple(TraitState(team, self.data) for team in self.teams)
        for team_index, team in enumerate(self.teams):
            for unit in team:
                unit.set_trait_bonuses(self.trait_states[team_index].bonuses_for(unit))
                unit.reset_for_combat()
                self._move_timers[unit.uid] = 0.0
                self.log.register(unit)

        for team_index, state in enumerate(self.trait_states):
            self.log.add(
                self.t,
                0,
                EventKind.COMBAT_START,
                team=team_index,
                units=[u.name for u in self.teams[team_index]],
                traits={tid: bp.count for tid, bp in sorted(state.active.items())},
            )
        self._fire_trigger_all(EffectTrigger.ON_COMBAT_START)
        # Traits resolve after items so that percentage-of-max-health grants
        # (Brawler) see the health items have already added.
        for team_index in (0, 1):
            self._fire_trait_triggers(team_index, EffectTrigger.ON_COMBAT_START)

    # -- queries ----------------------------------------------------------

    def living(self, team: int) -> list[UnitInstance]:
        return [u for u in self.teams[team] if u.alive]

    def targetable(self, team: int) -> list[UnitInstance]:
        """Living units that can currently be picked as a target.

        Untargetable units (Edge of Night, Rogue's stealth, Party Animal) are
        skipped by target selection but still occupy their hex and still take
        area damage, which is how TFT treats them.
        """
        return [u for u in self.teams[team] if u.alive and not u.is_untargetable]

    def enemies_of(self, unit: UnitInstance) -> list[UnitInstance]:
        return self.living(1 - unit.team)

    def targetable_enemies_of(self, unit: UnitInstance) -> list[UnitInstance]:
        return self.targetable(1 - unit.team)

    def allies_of(self, unit: UnitInstance, include_self: bool = True) -> list[UnitInstance]:
        return [
            u for u in self.living(unit.team) if include_self or u.uid != unit.uid
        ]

    @property
    def occupied(self) -> dict[Hex, int]:
        return {u.position: u.uid for u in self.units if u.alive and u.position}

    def units_within(
        self, center: Hex, radius: int, team: int | None = None
    ) -> list[UnitInstance]:
        """Living units within ``radius`` hexes of ``center``, ordered by uid."""
        return sorted(
            (
                u
                for u in self.units
                if u.alive
                and u.position is not None
                and distance(u.position, center) <= radius
                and (team is None or u.team == team)
            ),
            key=lambda u: u.uid,
        )

    # -- main loop --------------------------------------------------------

    def run(self) -> CombatResult:
        """Step until the fight resolves, then return the result."""
        dt = self.config.tick_seconds
        max_ticks = int(self.config.max_duration_seconds / dt) + 1

        while not self._finished and self.tick_index < max_ticks:
            self.step(dt)

        timed_out = not self._finished
        return self._finish(timed_out)

    def step(self, dt: float) -> None:
        """Advance the simulation by one tick."""
        self.tick_index += 1
        self.t += dt

        for unit in self.units:
            if unit.alive:
                unit.tick_statuses(dt)
                # Ability cooldowns run on wall-clock time: they keep ticking
                # while the unit is stunned, moving or out of range.
                if unit.cast_timer > 0:
                    unit.cast_timer = max(0.0, unit.cast_timer - dt)
                # Role passive: Casters regenerate mana over time as well as
                # on attack, so they keep casting while kiting or stunned.
                regen = self.config.mana_per_second(unit.champion.role)
                if regen > 0:
                    self.grant_mana(unit, regen * dt, reason="role_regen")
                # Item-granted mana regen (Tear and everything built from it).
                item_regen = unit.derived_stats().mana_regen
                if item_regen > 0:
                    self.grant_mana(unit, item_regen * dt, reason="item_regen")

        self._advance_projectiles(dt)
        self._advance_burns(dt)

        # Interval items (Archangel's Staff) need a per-tick dispatch; the
        # implementation decides whether its interval has elapsed. Same
        # reasoning as ON_HIT above -- a PERIODIC item was previously
        # registered and unreachable (doc 99 entry 33.2).
        for unit in sorted(self.units, key=lambda u: u.uid):
            if unit.alive:
                self._fire_item_triggers(unit, EffectTrigger.PERIODIC)
                self._fire_ability_triggers(unit, EffectTrigger.PERIODIC)
        for team_index in (0, 1):
            self._fire_trait_triggers(team_index, EffectTrigger.PERIODIC)

        if self.t >= self.config.sudden_death_start_seconds:
            self._apply_sudden_death(dt)

        # Fixed iteration order keeps ties reproducible across runs.
        for unit in sorted(self.units, key=lambda u: u.uid):
            if not unit.alive:
                continue
            self._act(unit, dt)

        if not self.living(0) or not self.living(1):
            self._finished = True

    def _act(self, unit: UnitInstance, dt: float) -> None:
        if unit.is_stunned:
            return

        target = self._select_target(unit)
        if target is None:
            return

        if self._try_cast(unit, target):
            return

        stats = unit.derived_stats()
        in_range = distance(unit.position, target.position) <= stats.attack_range
        if not in_range:
            self._move_toward(unit, target, dt)
            return

        if unit.is_disarmed:
            return
        self._progress_attack(unit, target, dt)

    # -- targeting --------------------------------------------------------

    def _select_target(self, unit: UnitInstance) -> UnitInstance | None:
        """Keep the current target while it lives and stays reachable.

        This is TFT's "sticky" targeting: a unit commits to a target and chases
        it, rather than switching to whatever is nearest each tick. It re-picks
        only when the target dies, or when :meth:`_move_toward` finds no path
        and clears the target as unreachable.

        Doc 01 sec 3.1 step 3 reads as "re-target when dead *or out of range*",
        which taken literally makes chasing units flip targets constantly; the
        doc should be amended to match this behaviour.
        """
        # The sticky check comes first because it is the overwhelmingly common
        # case, and building the candidate list is not free: it scans the enemy
        # team and evaluates `is_untargetable` on each, once per unit per tick.
        # Profiled, this reordering alone is 19% of whole-game wall clock.
        #
        # It cannot change the answer. A `current` that is alive and targetable
        # is by definition a member of `targetable_enemies_of(unit)`, so the
        # `not enemies` early return below is unreachable in exactly the case
        # this skips ahead of -- an empty list and a valid current target are
        # not simultaneously possible.
        current = self.by_uid.get(unit.target_uid) if unit.target_uid else None
        # An untargetable target is dropped as if it had died, so attackers
        # re-pick rather than standing still waiting for it to reappear.
        if current is not None and current.alive and not current.is_untargetable:
            return current

        enemies = self.targetable_enemies_of(unit)
        if not enemies:
            return None

        rule_name = getattr(unit, "targeting_rule", DEFAULT_TARGETING_RULE)
        rule = TARGETING_RULES.get(rule_name)
        if rule is None:
            log.warning(
                "unknown targeting_rule %r on %s -- falling back to %r",
                rule_name,
                unit.name,
                DEFAULT_TARGETING_RULE,
            )
            rule = TARGETING_RULES[DEFAULT_TARGETING_RULE]

        chosen = rule(unit, enemies)
        if chosen is not None and chosen.uid != unit.target_uid:
            unit.target_uid = chosen.uid
            self.log.add(self.t, self.tick_index, EventKind.TARGET, unit, chosen)
        return chosen

    # -- movement ---------------------------------------------------------

    def _move_toward(self, unit: UnitInstance, target: UnitInstance, dt: float) -> None:
        if unit.is_rooted:
            return
        self._move_timers[unit.uid] += dt
        if self._move_timers[unit.uid] < self.config.seconds_per_hex:
            return
        self._move_timers[unit.uid] -= self.config.seconds_per_hex

        blocked = set(self.occupied) - {unit.position}
        step = self.board.next_step_toward(unit.position, target.position, blocked)
        if step is None:
            # No route to the target and not in range: treat it as unreachable
            # and let sticky targeting re-pick next tick, rather than stalling.
            unit.target_uid = None
            return
        origin = unit.position
        unit.position = step
        self.log.add(
            self.t,
            self.tick_index,
            EventKind.MOVE,
            unit,
            target,
            **{"from": str(origin), "to": str(step)},
        )

    # -- auto-attacks -----------------------------------------------------

    def _progress_attack(self, unit: UnitInstance, target: UnitInstance, dt: float) -> None:
        stats = unit.derived_stats()
        unit.attack_timer += dt
        period = stats.seconds_per_attack
        # Cap the carry-over so a long out-of-range gap cannot produce a burst
        # of stacked attacks the moment the unit closes.
        if unit.attack_timer > period:
            unit.attack_timer = period
        if unit.attack_timer < period:
            return
        unit.attack_timer -= period
        self._auto_attack(unit, target)

    def _auto_attack(self, unit: UnitInstance, target: UnitInstance) -> None:
        stats = unit.derived_stats()
        is_crit = self.rng.random() < stats.crit_chance
        raw = stats.attack_damage * (stats.crit_damage if is_crit else 1.0)

        self.log.add(
            self.t,
            self.tick_index,
            EventKind.ATTACK,
            unit,
            target,
            raw=raw,
            crit=is_crit,
            ranged=stats.attack_range > 1,
        )

        if stats.attack_range > 1:
            travel = (
                distance(unit.position, target.position)
                / self.config.projectile_hexes_per_second
            )
            self.projectiles.append(
                Projectile(unit.uid, target.uid, travel, raw, DamageType.PHYSICAL, is_crit)
            )
            self.log.add(
                self.t,
                self.tick_index,
                EventKind.PROJECTILE_LAUNCH,
                unit,
                target,
                travel=travel,
            )
            return

        self._land_attack(unit, target, raw, DamageType.PHYSICAL, is_crit)

    def _land_attack(
        self,
        unit: UnitInstance,
        target: UnitInstance,
        raw: float,
        damage_type: DamageType,
        is_crit: bool,
    ) -> None:
        """Resolve a connecting auto-attack: damage, mana, on-attack effects."""
        self.deal_damage(unit, target, raw, damage_type, is_crit=is_crit, source_label="auto")
        # Doc 01 sec 3.2: mana is granted for an attack that *lands*.
        self.grant_mana(unit, unit.derived_stats().mana_per_attack, reason="attack")
        self._fire_item_triggers(
            unit, EffectTrigger.ON_ATTACK, target=target, is_crit=is_crit
        )
        self._fire_ability_triggers(
            unit, EffectTrigger.ON_ATTACK, target=target, is_crit=is_crit
        )

    def _advance_projectiles(self, dt: float) -> None:
        still_flying: list[Projectile] = []
        for projectile in self.projectiles:
            projectile.remaining -= dt
            if projectile.remaining > 0:
                still_flying.append(projectile)
                continue
            source = self.by_uid[projectile.source_uid]
            target = self.by_uid[projectile.target_uid]
            if not target.alive or not source.alive:
                # The shot dissipates: no damage and no mana, since doc 01
                # sec 3.2 grants mana only for an attack that connects.
                self.log.add(
                    self.t,
                    self.tick_index,
                    EventKind.PROJECTILE_FIZZLE,
                    source,
                    target,
                    reason="target_dead" if not target.alive else "source_dead",
                )
                continue
            self._land_attack(
                source, target, projectile.raw_damage, projectile.damage_type, projectile.is_crit
            )
        self.projectiles = still_flying

    # -- casting ----------------------------------------------------------

    def _try_cast(self, unit: UnitInstance, target: UnitInstance) -> bool:
        """Cast if ready. Returns True if the unit spent this tick casting."""
        ability = unit.champion.ability
        if ability is None:
            return False

        if ability.cast_mode == "cooldown":
            if unit.cast_timer > 0:
                return False
        else:
            stats = unit.derived_stats()
            if unit.current_mana < stats.max_mana:
                return False

        fn = effects.resolve(ability.effect_id)
        if fn is None:
            # Unimplemented ability: consume the resource and log, but do not
            # crash and do not stall the unit forever (doc 02 sec 2).
            self._consume_cast_resource(unit)
            self.log.add(
                self.t,
                self.tick_index,
                EventKind.CAST_SKIPPED,
                unit,
                target,
                ability=ability.name,
                effect_id=ability.effect_id,
                reason="effect_not_implemented",
            )
            return False

        self._consume_cast_resource(unit)
        self.log.add(
            self.t,
            self.tick_index,
            EventKind.CAST,
            unit,
            target,
            ability=ability.name,
            effect_id=ability.effect_id,
        )
        ctx = EffectContext(
            sim=self,
            source=unit,
            target=target,
            params=ability.params,
            star_level=unit.star_level,
        )
        fn(ctx)
        # Traits that react to a cast (Replicator's second casting) run after
        # the ability has resolved, so they see its full effect.
        self._fire_trait_triggers(
            unit.team, EffectTrigger.ON_CAST, unit=unit, target=target
        )
        return True

    def _consume_cast_resource(self, unit: UnitInstance) -> None:
        ability = unit.champion.ability
        assert ability is not None
        max_mana = unit.derived_stats().max_mana
        unit.mana_locked_until = self.t + self.config.mana_lock_seconds
        if ability.cast_mode == "cooldown":
            unit.cast_timer = ability.cooldown_seconds or 0.0
        else:
            # Doc 01 sec 3.2: overflow above max mana carries into the next bar.
            unit.current_mana = max(0.0, unit.current_mana - max_mana)
        # Ionic Spark punishes the cast itself, scaled by the mana it cost, so
        # a cooldown-caster still counts for its notional bar.
        for enemy in self.enemies_of(unit):
            self._fire_item_triggers(
                enemy, EffectTrigger.ON_ENEMY_CAST, target=unit, amount=max_mana
            )

    def _fire_ability_triggers(
        self,
        unit: UnitInstance,
        trigger: EffectTrigger,
        target: UnitInstance | None = None,
        amount: float = 0.0,
        is_crit: bool = False,
    ) -> list[float]:
        """Run a champion's *ability* hooks for a non-cast trigger.

        Most of the 29 champions the fetch script declined to canonicalise have
        a passive as well as an active -- "Every third attack...", "Attacks
        deal bonus magic damage". Those passives are registered on ON_ATTACK,
        ON_HIT, ON_DAMAGED or PERIODIC against the same ``ability_<Name>``
        effect_id as the active, which the multi-hook registry supports
        directly (doc 99 entry 35.1).
        """
        ability = unit.champion.ability
        if ability is None:
            return []
        hooks = effects.hooks_for(ability.effect_id, trigger)
        out: list[float] = []
        for fn in hooks:
            result = fn(
                EffectContext(
                    sim=self,
                    source=unit,
                    target=target,
                    params=ability.params,
                    star_level=unit.star_level,
                    amount=amount,
                    is_crit=is_crit,
                )
            )
            if isinstance(result, (int, float)) and not isinstance(result, bool):
                out.append(float(result))
        return out

    # -- mana -------------------------------------------------------------

    def grant_mana(self, unit: UnitInstance, amount: float, reason: str = "") -> float:
        """Add mana, letting it overflow past the cap (doc 01 sec 3.2)."""
        if amount <= 0 or not unit.alive:
            return 0.0
        # Real TFT locks a champion out of mana gain for 1s after it casts, so
        # a tank does not convert the damage it takes mid-cast straight back
        # into its next cast (doc 99 entry 36.7).
        if unit.mana_locked_until > self.t:
            return 0.0
        amount *= 1.0 + unit.mana_gain_bonus
        unit.current_mana += amount
        self.log.add(
            self.t,
            self.tick_index,
            EventKind.MANA,
            unit,
            amount=amount,
            total=unit.current_mana,
            reason=reason,
        )
        return amount

    def _mana_from_damage_taken(
        self,
        unit: UnitInstance,
        pre_mitigation: float,
        hp_lost: float,
        after_resists: float | None = None,
    ) -> None:
        """Doc 01 sec 3.2: Tanks build mana from damage taken, capped per hit.

        What "post-mitigation" means when a shield eats the hit is genuinely
        ambiguous -- the wiki gives the 1%/3%/42.5 numbers but does not say
        whether absorbed damage counts. Both readings are selectable via
        ``damage_mana_post_mitigation_basis`` (doc 99 entry 5.4). Note the 1%
        pre-mitigation term applies either way, so a fully-shielded tank still
        generates some mana.
        """
        if not self.config.generates_mana_from_damage(unit.champion.role):
            return
        if self.config.damage_mana_post_mitigation_basis == "after_resists":
            post = hp_lost if after_resists is None else after_resists
        else:
            post = hp_lost
        gained = (
            pre_mitigation * self.config.damage_mana_pre_mitigation_pct
            + post * self.config.damage_mana_post_mitigation_pct
        )
        gained = min(gained, self.config.damage_mana_cap_per_instance)
        if gained > 0:
            self.grant_mana(unit, gained, reason="damage_taken")

    # -- damage primitives (doc 03 sec 2.4) -------------------------------

    def mitigation_multiplier(self, target: UnitInstance, damage_type: DamageType) -> float:
        """Diminishing-returns mitigation: K / (K + resist) (doc 01 sec 3.3)."""
        if damage_type is DamageType.TRUE:
            return 1.0
        stats = target.derived_stats()
        resist = stats.armor if damage_type is DamageType.PHYSICAL else stats.magic_resist
        k = self.config.armor_mitigation_constant
        return k / (k + resist)

    def deal_damage(
        self,
        source: UnitInstance | None,
        target: UnitInstance,
        amount: float,
        damage_type: DamageType,
        *,
        is_crit: bool = False,
        source_label: str = "",
        trigger_effects: bool = True,
    ) -> float:
        """Apply damage through mitigation, amp, shields and HP.

        Returns the HP actually lost (shield absorption excluded).
        """
        if not target.alive or amount <= 0:
            return 0.0

        # Precision (Infinity Edge, Jeweled Gauntlet, Fateweaver) lets ability
        # damage critically strike. Auto-attacks roll their own crit in
        # `_auto_attack` and arrive with `is_crit` already decided, so only
        # non-attack damage is rolled here (doc 99 entry 36.2).
        if (
            source is not None
            and not is_crit
            and source_label not in ("auto", "")
            and source.has_precision
        ):
            stats = source.derived_stats()
            if stats.crit_chance > 0 and self.rng.random() < stats.crit_chance:
                is_crit = True
                amount *= stats.crit_damage

        pre_mitigation = amount
        mitigated = amount * self.mitigation_multiplier(target, damage_type)

        # Doc 01 sec 3.3: amp and reduction apply multiplicatively *after*
        # armour/MR mitigation.
        if source is not None:
            mitigated *= 1.0 + source.derived_stats().damage_amp
            # Conditional amps depend on who is being hit (Giant Slayer vs
            # Tanks), so they cannot live in the attacker's stat block.
            if trigger_effects:
                mitigated *= self._damage_multiplier_from_items(source, target)
        mitigated *= 1.0 - target.derived_stats().durability

        absorbed = self._absorb_with_shields(target, mitigated, damage_type)
        hp_lost = min(mitigated - absorbed, target.current_hp)
        target.current_hp -= hp_lost

        self.log.add(
            self.t,
            self.tick_index,
            EventKind.DAMAGE,
            source,
            target,
            amount=round(mitigated, 3),
            pre_mitigation=round(pre_mitigation, 3),
            absorbed=round(absorbed, 3),
            hp_lost=round(hp_lost, 3),
            type=damage_type.value,
            crit=is_crit,
            via=source_label,
            hp=round(target.current_hp, 2),
        )

        # ``mitigated`` is the damage that got past armour/MR but before any
        # shield absorbed it -- the alternative basis for the 3% term.
        self._mana_from_damage_taken(target, pre_mitigation, hp_lost, mitigated)
        if trigger_effects:
            # Reflect-style effects pass trigger_effects=False when they deal
            # their own damage, so two thorns-carrying units cannot bounce
            # damage off each other forever.
            self._fire_item_triggers(
                target, EffectTrigger.ON_DAMAGED, target=source, amount=mitigated
            )
            self._fire_ability_triggers(
                target, EffectTrigger.ON_DAMAGED, target=source, amount=mitigated
            )
            # ON_HIT is the attacker's side of the same event -- shreds and
            # on-hit riders (Last Whisper, Void Staff) live here. Without this
            # dispatch an ON_HIT item is registered, warns about nothing, and
            # silently never fires (doc 99 entry 33.2).
            if source is not None and source.alive:
                self._fire_item_triggers(
                    source,
                    EffectTrigger.ON_HIT,
                    target=target,
                    amount=mitigated,
                    is_crit=is_crit,
                )
                self._fire_ability_triggers(
                    source,
                    EffectTrigger.ON_HIT,
                    target=target,
                    amount=mitigated,
                    is_crit=is_crit,
                )

        # Omnivamp: heal the attacker for a fraction of damage dealt. Sources
        # are the wearer's items plus their role's innate share (Fighters get
        # 10%). Measured on damage that landed, so a fully-absorbed hit heals
        # nothing (doc 99 entry 9.2).
        if source is not None and source.alive and hp_lost > 0:
            omnivamp = source.derived_stats().omnivamp + self.config.omnivamp_for(
                source.champion.role
            )
            if omnivamp > 0:
                self.heal(source, hp_lost * omnivamp, source_label="omnivamp")

        if target.current_hp <= 0:
            self._kill(target, source)
        return hp_lost

    def _absorb_with_shields(
        self, target: UnitInstance, amount: float, damage_type: DamageType
    ) -> float:
        """Shields soak damage before HP; type-specific shields only match."""
        remaining = amount
        absorbed = 0.0
        for shield in target.shields:
            if remaining <= 0:
                break
            if shield.damage_type is not None and shield.damage_type != damage_type.value:
                continue
            taken = min(shield.amount, remaining)
            shield.amount -= taken
            remaining -= taken
            absorbed += taken
        if any(s.expired for s in target.shields):
            target.shields = [s for s in target.shields if not s.expired]
        return absorbed

    def heal(self, target: UnitInstance, amount: float, source_label: str = "") -> float:
        if not target.alive or amount <= 0:
            return 0.0
        # Grievous Wounds (Morellonomicon, Sunfire Cape) cuts every heal the
        # target receives, including omnivamp and its own ability's lifesteal.
        amount *= 1.0 - target.healing_reduction
        if amount <= 0:
            return 0.0
        max_health = target.derived_stats().max_health
        healed = min(amount, max_health - target.current_hp)
        target.current_hp += healed
        if healed > 0:
            self.log.add(
                self.t,
                self.tick_index,
                EventKind.HEAL,
                target,
                amount=round(healed, 3),
                hp=round(target.current_hp, 2),
                via=source_label,
            )
        return healed

    def apply_shield(
        self,
        target: UnitInstance,
        amount: float,
        duration: float | None = None,
        damage_type: str | None = None,
        source_label: str = "",
    ) -> None:
        if not target.alive or amount <= 0:
            return
        target.shields.append(Shield(amount, duration, damage_type, source_label))
        self.log.add(
            self.t,
            self.tick_index,
            EventKind.SHIELD,
            target,
            amount=round(amount, 3),
            duration=duration,
            via=source_label,
        )

    def apply_status(self, target: UnitInstance, effect: StatusEffect) -> None:
        if not target.alive:
            return
        if target.is_cc_immune and (effect.stun or effect.root or effect.disarm):
            # Quicksilver and its kin. The status is dropped rather than
            # applied-and-ignored so that anything reading `is_stunned` sees
            # the truth, and so a CC-immune unit's log shows the miss.
            self.log.add(
                self.t,
                self.tick_index,
                EventKind.STATUS,
                target,
                source=effect.source,
                blocked_by="cc_immune",
            )
            return
        target.add_status(effect)
        self.log.add(
            self.t,
            self.tick_index,
            EventKind.STATUS,
            target,
            source=effect.source,
            duration=effect.remaining,
            stun=effect.stun,
            root=effect.root,
            disarm=effect.disarm,
        )

    # -- summons, movement and luck ---------------------------------------

    def summon(
        self,
        champion,
        team: int,
        near: Hex,
        *,
        star_level: int = 1,
        health_scale: float = 1.0,
        items=(),
        source_label: str = "summon",
    ) -> UnitInstance | None:
        """Create a unit mid-combat on a free hex near ``near``.

        Returns ``None`` when the board is full, which is a normal outcome and
        not an error. Summons are flagged ``is_summon`` so the match never
        returns them to the champion pool -- a leak the smoke test would catch
        as a pool-conservation failure.
        """
        from engine.unit import UnitInstance

        spot = self._free_hex_near(near)
        if spot is None:
            return None

        unit = UnitInstance(champion, star_level, items=items, registry=None)
        unit.team = team
        unit.position = spot
        unit.is_summon = True
        unit.set_trait_bonuses(self.trait_states[team].bonuses_for(unit))
        unit.reset_for_combat()
        if health_scale != 1.0:
            unit.current_hp *= health_scale

        self.teams[team].append(unit)
        self.units.append(unit)
        self.by_uid[unit.uid] = unit
        self._move_timers[unit.uid] = 0.0
        self.log.register(unit)
        self.log.add(
            self.t, self.tick_index, EventKind.SUMMON, unit, via=source_label
        )
        return unit

    def _free_hex_near(self, center: Hex) -> Hex | None:
        """Nearest unoccupied board hex to ``center``, or ``None`` if full."""
        taken = self.occupied
        for radius in range(0, 4):
            for hex_ in sorted(
                spread(center, radius), key=lambda h: (distance(center, h), h.q, h.r)
            ):
                if hex_ in self.board and hex_ not in taken:
                    return hex_
        return None

    def reposition(self, unit: UnitInstance, toward: Hex, max_hexes: int = 1) -> bool:
        """Move a unit up to ``max_hexes`` toward a hex, ignoring movement speed.

        Dashes and blinks (Pyke, Talon, Fizz, Gwen, Riven) are instantaneous
        repositions rather than movement, so they bypass the move timer. A
        rooted unit cannot be repositioned.
        """
        if unit.is_rooted or unit.position is None:
            return False
        taken = self.occupied
        best = None
        for hex_ in spread(unit.position, max_hexes):
            if hex_ not in self.board or (hex_ in taken and hex_ != unit.position):
                continue
            if best is None or distance(hex_, toward) < distance(best, toward):
                best = hex_
        if best is None or best == unit.position:
            return False
        unit.position = best
        self.log.add(self.t, self.tick_index, EventKind.MOVE, unit, to=str(best), via="dash")
        return True

    def lucky_roll(self, chance: float, lucky: bool) -> bool:
        """A probability check that rolls twice and keeps the better if ``lucky``.

        Fateweaver grants Lucky to its members and several abilities (Caitlyn's
        Headshot, Twisted Fate's card) call for it explicitly. Routing every
        such check through one method is what makes the trait expressible at
        all -- otherwise "check twice" would have to be duplicated per ability.
        """
        first = self.rng.random() < chance
        if not lucky:
            return first
        return first or (self.rng.random() < chance)

    def lucky_value(self, low: float, high: float, lucky: bool) -> float:
        """A uniform draw, taking the better of two when ``lucky``."""
        first = self.rng.uniform(low, high)
        if not lucky:
            return first
        return max(first, self.rng.uniform(low, high))

    def has_trait(self, unit: UnitInstance, trait_id: str) -> bool:
        return self.trait_states[unit.team].tier_of(trait_id) > 0

    def apply_burn(
        self,
        source: UnitInstance | None,
        target: UnitInstance,
        pct_max_hp_per_second: float,
        duration: float,
        *,
        ticks_per_second: float = 1.0,
        source_label: str = "",
    ) -> None:
        """Apply or refresh a max-health burn (doc 99 entry 34.2).

        Burns do not stack: a second application replaces the first only if it
        is at least as strong, so a Sunfire carrier does not overwrite a
        Morellonomicon's larger burn with its own.
        """
        if not target.alive or pct_max_hp_per_second <= 0 or duration <= 0:
            return
        interval = 1.0 / ticks_per_second if ticks_per_second > 0 else 1.0
        per_tick = pct_max_hp_per_second * interval
        existing = self.burns.get(target.uid)
        if existing is not None and existing.pct_max_hp_per_tick > per_tick:
            return
        self.burns[target.uid] = Burn(
            source_uid=source.uid if source else None,
            target_uid=target.uid,
            remaining=duration,
            pct_max_hp_per_tick=per_tick,
            tick_interval=interval,
            until_next_tick=interval,
            source_label=source_label,
        )

    def apply_grievous_wounds(
        self, target: UnitInstance, fraction: float, duration: float, source_label: str = ""
    ) -> None:
        """Reduce every heal ``target`` receives, for a duration."""
        if fraction <= 0 or duration <= 0:
            return
        self.apply_status(
            target,
            StatusEffect(
                source_label or "grievous_wounds",
                remaining=duration,
                healing_reduction=fraction,
            ),
        )

    def _advance_burns(self, dt: float) -> None:
        """Tick every active burn, dealing true damage on its own cadence."""
        for uid in sorted(self.burns):
            burn = self.burns[uid]
            target = self.by_uid.get(uid)
            if target is None or not target.alive:
                del self.burns[uid]
                continue
            burn.remaining -= dt
            burn.until_next_tick -= dt
            while burn.until_next_tick <= 0 and target.alive:
                burn.until_next_tick += burn.tick_interval
                damage = target.derived_stats().max_health * burn.pct_max_hp_per_tick
                self.deal_damage(
                    self.by_uid.get(burn.source_uid) if burn.source_uid else None,
                    target,
                    damage,
                    DamageType.TRUE,
                    source_label=burn.source_label or "burn",
                    trigger_effects=False,
                )
            if burn.remaining <= 0:
                del self.burns[uid]

    def apply_stun(self, target: UnitInstance, duration: float, source_label: str = "") -> None:
        self.apply_status(target, StatusEffect(source_label or "stun", duration, stun=True))

    # -- deaths and endings -----------------------------------------------

    def _kill(self, unit: UnitInstance, killer: UnitInstance | None) -> None:
        if not unit.alive:
            return
        unit.alive = False
        unit.current_hp = 0.0
        unit.shields.clear()
        self.log.add(
            self.t,
            self.tick_index,
            EventKind.DEATH,
            unit,
            killer,
            killed_by=self.log.name_of(killer.uid if killer else None),
        )
        self._fire_item_triggers(unit, EffectTrigger.ON_DEATH)
        self._fire_ability_triggers(unit, EffectTrigger.ON_DEATH)
        # Anything still chasing the dead unit re-picks next tick.
        for other in self.units:
            if other.target_uid == unit.uid:
                other.target_uid = None

    def _apply_overtime_buffs(self) -> None:
        """Grant the overtime acceleration once, to everything still standing."""
        from engine.stats import StatBonuses

        speed = self.config.overtime_attack_speed_pct
        amp = self.config.overtime_damage_amp
        cut = self.config.overtime_healing_reduction
        if not (speed or amp or cut):
            return
        for unit in sorted(self.units, key=lambda u: u.uid):
            if not unit.alive or not _once(unit, "overtime"):
                continue
            unit.add_status(
                StatusEffect(
                    "overtime",
                    remaining=None,
                    bonuses=StatBonuses(
                        {"attack_speed_pct": speed, "damage_amp": amp}
                    ),
                    healing_reduction=cut,
                )
            )

    def _apply_sudden_death(self, dt: float) -> None:
        """Overtime: amplify output rather than burn through mitigation.

        Real TFT's overtime is an *acceleration* -- attack speed and ability
        damage are amplified and healing is cut, with damage still resolving
        through resists and shields. The previous implementation was a
        percentage-of-max-health burn applied straight to ``current_hp``,
        bypassing armour, MR, ``durability``, shields and healing entirely.
        About a quarter of all fights were still live at 30s, so for the
        deciding seconds of those the entire defensive half of the game was
        worth nothing (doc 99 entry 36.8).

        The burn is kept as a *floor* so termination stays unconditional: two
        boards that cannot damage each other at all still resolve.
        """
        self._apply_overtime_buffs()

        elapsed = self.t - self.config.sudden_death_start_seconds

        fraction = self.config.sudden_death_damage_pct_per_second * elapsed * dt
        if fraction <= 0:
            return
        if not self._sudden_death_logged:
            self._sudden_death_logged = True
            self.log.add(
                self.t,
                self.tick_index,
                EventKind.SUDDEN_DEATH,
                reason="ramp_started",
                pct_per_second=self.config.sudden_death_damage_pct_per_second,
            )
        for unit in sorted(self.units, key=lambda u: u.uid):
            if not unit.alive:
                continue
            burn = unit.derived_stats().max_health * fraction
            unit.current_hp -= burn
            if unit.current_hp <= 0:
                self.log.add(
                    self.t,
                    self.tick_index,
                    EventKind.SUDDEN_DEATH,
                    unit,
                    reason="burned_down",
                    burn=burn,
                )
                self._kill(unit, None)

    def _finish(self, timed_out: bool) -> CombatResult:
        alive0, alive1 = self.living(0), self.living(1)
        if alive0 and not alive1:
            winner = 0
        elif alive1 and not alive0:
            winner = 1
        elif not alive0 and not alive1:
            winner = None
        else:
            # Both sides still standing at the cap: more survivors wins, then
            # more remaining health; a dead tie is a draw.
            key0 = (len(alive0), sum(u.current_hp for u in alive0))
            key1 = (len(alive1), sum(u.current_hp for u in alive1))
            winner = None if key0 == key1 else (0 if key0 > key1 else 1)

        survivors = tuple(alive0 + alive1)
        self.log.add(
            self.t,
            self.tick_index,
            EventKind.COMBAT_END,
            winner=winner,
            timed_out=timed_out,
            survivors=[self.log.name_of(u.uid) for u in survivors],
        )
        return CombatResult(
            winner=winner,
            survivors=survivors,
            duration=round(self.t, 4),
            ticks=self.tick_index,
            log=self.log,
            timed_out=timed_out,
        )

    # -- effect triggers --------------------------------------------------

    def _fire_item_triggers(
        self,
        unit: UnitInstance,
        trigger: EffectTrigger,
        target: UnitInstance | None = None,
        amount: float = 0.0,
        is_crit: bool = False,
    ) -> list[float]:
        """Run any equipped item's effect wired to ``trigger``.

        Returns whatever the implementations returned, discarding ``None``.
        Only :data:`EffectTrigger.DAMAGE_MODIFIER` uses the return value; every
        other trigger's implementations return ``None`` and the list is empty.
        """
        out: list[float] = []
        for item in unit.items:
            if item.effect_id is None:
                continue
            hooks = effects.hooks_for(item.effect_id, trigger)
            if not hooks:
                # Ask the registry anyway, so a genuinely unimplemented item
                # still warns exactly once instead of being skipped in silence.
                effects.resolve(item.effect_id)
                continue
            for fn in hooks:
                result = fn(
                    EffectContext(
                        sim=self,
                        source=unit,
                        target=target,
                        params=item.effect_values,
                        star_level=unit.star_level,
                        amount=amount,
                        is_crit=is_crit,
                    )
                )
                if isinstance(result, (int, float)) and not isinstance(result, bool):
                    out.append(float(result))
        return out

    def _fire_trait_triggers(
        self,
        team: int,
        trigger: EffectTrigger,
        unit: UnitInstance | None = None,
        target: UnitInstance | None = None,
        amount: float = 0.0,
    ) -> list[float]:
        """Run every active trait's hook for ``trigger`` on one team.

        When ``unit`` is given (the per-unit triggers), only traits that unit
        actually carries are considered -- Sniper's distance amp belongs to the
        Sniper doing the shooting, not to the whole board.
        """
        out: list[float] = []
        state = self.trait_states[team]
        living = self.living(team)
        carried = unit_traits(unit) if unit is not None else None

        for trait_id, breakpoint_ in sorted(state.active.items()):
            if carried is not None and trait_id not in carried:
                continue
            hooks = trait_effects.trait_hooks_for(trait_id, trigger)
            if not hooks:
                if not trait_effects.is_trait_implemented(trait_id):
                    trait_effects.note_missing_trait(trait_id)
                continue
            members = [u for u in living if trait_id in unit_traits(u)]
            ctx = trait_effects.TraitContext(
                sim=self,
                team=team,
                trait_id=trait_id,
                tier=breakpoint_.count,
                params=breakpoint_.params,
                members=members,
                allies=living,
                unit=unit,
                target=target,
                amount=amount,
            )
            for fn in hooks:
                result = fn(ctx)
                if isinstance(result, (int, float)) and not isinstance(result, bool):
                    out.append(float(result))
        return out

    def _damage_multiplier_from_items(
        self, source: UnitInstance, target: UnitInstance
    ) -> float:
        """Product of the attacker's conditional damage amps against ``target``."""
        multiplier = 1.0
        for value in self._fire_item_triggers(
            source, EffectTrigger.DAMAGE_MODIFIER, target=target
        ):
            multiplier *= value
        for value in self._fire_trait_triggers(
            source.team, EffectTrigger.DAMAGE_MODIFIER, unit=source, target=target
        ):
            multiplier *= value
        return multiplier

    def _fire_trigger_all(self, trigger: EffectTrigger) -> None:
        for unit in sorted(self.units, key=lambda u: u.uid):
            if unit.alive:
                self._fire_item_triggers(unit, trigger)


# --- placement helper ----------------------------------------------------


def place_team(
    units: Sequence[UnitInstance],
    slots: Sequence[tuple[int, int]],
    team: int,
    board: Board | None = None,
) -> list[UnitInstance]:
    """Position ``units`` on ``team``'s half-board at ``(row, col)`` slots.

    Row 0 is the front line. Returns the units for convenient chaining.
    """
    board = board or Board()
    if len(units) != len(slots):
        raise ValueError(f"got {len(units)} units but {len(slots)} slots")
    for unit, (row, col) in zip(units, slots, strict=True):
        unit.team = team
        unit.position = board.to_combat(team, row, col)
    return list(units)
