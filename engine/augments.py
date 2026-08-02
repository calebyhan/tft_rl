"""Augment offering and the player-scoped effect hooks they apply (doc 01 sec 8).

Doc 01 sec 8 recommends building the augment *system* -- offer 3, apply a
persistent hook -- and wiring up only a handful of simple augments. That is
exactly what this module is: the offering machinery is complete and general,
while the shipped ``data/augments.json`` covers stat and econ effects only.

**Why a second registry rather than reusing** :mod:`engine.effects`. That
registry's implementations all take a combat context and fire on a tick; an
augment hook takes a :class:`~engine.player.PlayerState` and fires on a round
boundary. Sharing one table would mean two incompatible call signatures behind
one lookup, so a data typo would surface as a ``TypeError`` deep inside combat
instead of as a missing effect. The two registries follow the same discipline:
an unregistered id warns **once** and no-ops, never crashes (doc 02 sec 2).

Stat-granting augments need no hook at all. Any ``params`` key naming a
modelled stat is applied to the player's whole board by
:func:`board_bonuses`, the same way a trait breakpoint's params work -- so a
purely statistical augment is pure data.
"""

from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING, Callable, Sequence, TypeVar

from engine.items import ItemError
from engine.schema import AugmentDef, GameData
from engine.stats import StatBonuses, bonuses_from_params

if TYPE_CHECKING:  # avoids a runtime cycle (player -> augments -> player)
    from engine.player import PlayerState

log = logging.getLogger(__name__)

# When a hook runs.
ON_PICK = "on_pick"
ON_ROUND_END = "on_round_end"

# (effect_id, when) -> implementation, populated by @register at import time.
AUGMENT_EFFECTS: dict[tuple[str, str], Callable] = {}

# Ids already reported as missing, so the warning fires once per id.
_reported_missing: set[str] = set()

F = TypeVar("F", bound=Callable)


def register(effect_id: str, when: str = ON_PICK) -> Callable[[F], F]:
    """Register an augment hook for ``effect_id``, firing at ``when``."""

    def decorator(fn: F) -> F:
        key = (effect_id, when)
        if key in AUGMENT_EFFECTS:
            raise ValueError(f"augment effect {effect_id!r} ({when}) already registered")
        AUGMENT_EFFECTS[key] = fn
        return fn

    return decorator


def is_implemented(effect_id: str | None) -> bool:
    return effect_id is not None and any(
        key[0] == effect_id for key in AUGMENT_EFFECTS
    )


def _resolve(effect_id: str | None, when: str) -> Callable | None:
    """Look up a hook, warning once if the id has no implementation at all.

    An id that *is* implemented but simply has no hook for this phase is not a
    problem -- an on-pick augment legitimately does nothing at round end -- so
    only a wholly unknown id warns.
    """
    if effect_id is None:
        return None
    fn = AUGMENT_EFFECTS.get((effect_id, when))
    if fn is None and not is_implemented(effect_id):
        if effect_id not in _reported_missing:
            _reported_missing.add(effect_id)
            log.warning(
                "augment effect_id %r has no implementation -- skipping it. "
                "Stats granted by the same augment still apply; only its "
                "special behaviour is missing.",
                effect_id,
            )
    return fn


# --- application ---------------------------------------------------------


def board_bonuses(augments: Sequence[AugmentDef]) -> StatBonuses:
    """Stat bonuses every unit on the player's board receives.

    Only ``params`` keys that name a modelled stat contribute; everything else
    belongs to the augment's ``effect_id`` and is ignored here. That is what
    lets an augment with an unimplemented hook still deliver its stat half.
    """
    bonuses = StatBonuses()
    for augment in augments:
        bonuses = bonuses.merged_with(bonuses_from_params(augment.params))
    return bonuses


def apply_on_pick(player: "PlayerState", augment: AugmentDef) -> None:
    """Fire ``augment``'s one-shot effect, the moment it is chosen."""
    fn = _resolve(augment.effect_id, ON_PICK)
    if fn is not None:
        fn(player, augment)


def apply_on_round_end(player: "PlayerState") -> None:
    """Fire every held augment's per-round effect, after income is paid."""
    for augment in player.augments:
        fn = _resolve(augment.effect_id, ON_ROUND_END)
        if fn is not None:
            fn(player, augment)


def extra_board_slots(augments: Sequence[AugmentDef]) -> int:
    """Additional units the player may field, summed over held augments.

    Read directly rather than through a hook because board size is queried
    constantly (every legality check) and must stay cheap and side-effect free.
    """
    return sum(int(a.params.get("board_slots", 0)) for a in augments)


# --- offering ------------------------------------------------------------


class AugmentOffer:
    """Draws augment choices, without repeats within a player's own game.

    Real TFT draws from a shared, per-player-independent pool; a player is
    never offered an augment they already hold. Offers are drawn from the
    match's seeded ``Random`` so a whole game still replays from its seed.
    """

    def __init__(self, data: GameData) -> None:
        self.data = data
        self._by_tier = {
            tier: data.augments_of_tier(tier)
            for tier in {a.tier for a in data.augments.values()}
        }

    def offer(
        self, tier: str, rng: random.Random, exclude: Sequence[AugmentDef] = ()
    ) -> tuple[AugmentDef, ...]:
        """``config.augments.choices`` augments of ``tier``, or fewer if the
        tier is too small to fill the offer."""
        held = {a.id for a in exclude}
        available = [a for a in self._by_tier.get(tier, ()) if a.id not in held]
        count = min(self.data.config.augments.choices, len(available))
        if count == 0:
            return ()
        return tuple(rng.sample(available, count))


# --- shipped hooks -------------------------------------------------------
#
# Doc 01 sec 8's "handful of simple augments": econ tweaks and free items.
# Anything combat-shaped is expressed as stat params instead and needs no code.


@register("augment_instant_gold")
def _instant_gold(player: "PlayerState", augment: AugmentDef) -> None:
    player.gold += int(augment.params.get("gold", 0))


@register("augment_instant_xp")
def _instant_xp(player: "PlayerState", augment: AugmentDef) -> None:
    player.grant_xp(int(augment.params.get("xp", 0)))


@register("augment_instant_items")
def _instant_items(player: "PlayerState", augment: AugmentDef) -> None:
    """Grant named items into the bag.

    Unknown item ids are skipped with a warning rather than raising: an
    augment referencing an item the current set does not ship should not take
    a match down (doc 03 sec 2.4).
    """
    for item_id in augment.params.get("items", ()):
        try:
            player.add_item(str(item_id))
        except ItemError:
            log.warning(
                "augment %r grants unknown item %r -- skipping", augment.id, item_id
            )


@register("augment_bonus_income", when=ON_ROUND_END)
def _bonus_income(player: "PlayerState", augment: AugmentDef) -> None:
    player.gold += int(augment.params.get("gold", 0))


@register("augment_extra_board_slot")
def _extra_board_slot(player: "PlayerState", augment: AugmentDef) -> None:
    """No-op on pick; :func:`extra_board_slots` reads ``params.board_slots``.

    Registered anyway so the id is *known* and does not trip the missing-effect
    warning -- the behaviour is real, it is just read rather than fired.
    """
    return None
