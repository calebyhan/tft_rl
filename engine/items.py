"""Item combination and item stat application (doc 03 sec 2.6).

The combination table is derived from the ``recipe`` field on each item, so
adding or re-balancing items is a data change only. Two components combine
into one completed item and order does not matter (doc 01 sec 5).

Emblems grant their wearer a trait. Which trait comes from the item's
``effect_id`` following the reserved ``emblem_<TraitId>`` convention -- a
naming rule rather than a per-set table in code, so the fetch script can
normalise real emblems into it and the loader validates the trait exists.
"""

from __future__ import annotations

from typing import Iterable, Mapping

from engine.schema import ItemDef
from engine.stats import StatBonuses

EMBLEM_EFFECT_PREFIX = "emblem_"


class ItemError(ValueError):
    """Raised on an illegal item operation (bad equip, unknown item, ...)."""


def emblem_trait_id(item: ItemDef) -> str | None:
    """The trait an emblem grants, or ``None`` if the item is not an emblem."""
    if item.category != "emblem" or item.effect_id is None:
        return None
    if not item.effect_id.startswith(EMBLEM_EFFECT_PREFIX):
        return None
    return item.effect_id[len(EMBLEM_EFFECT_PREFIX) :] or None


def recipe_key(component_a: str, component_b: str) -> tuple[str, str]:
    """Order-independent key for a component pair."""
    return tuple(sorted((component_a, component_b)))  # type: ignore[return-value]


class ItemRegistry:
    """Combination table and equip rules, built from loaded item data."""

    def __init__(
        self, items: Mapping[str, ItemDef], max_items_per_unit: int
    ) -> None:
        self.items = items
        self.max_items_per_unit = max_items_per_unit
        # Radiant items reuse their base item's recipe, so they are excluded
        # here -- otherwise a pair would map to two different results.
        self._by_recipe: dict[tuple[str, str], str] = {
            recipe_key(*item.recipe): item.id
            for item in items.values()
            if len(item.recipe) == 2 and item.category != "radiant"
        }
        self._radiant_by_base: dict[str, str] = {
            item.radiant_version_of: item.id
            for item in items.values()
            if item.radiant_version_of is not None
        }

    def get(self, item_id: str) -> ItemDef:
        try:
            return self.items[item_id]
        except KeyError:
            raise ItemError(f"unknown item id {item_id!r}") from None

    def combine(self, component_a: str, component_b: str) -> str | None:
        """The item made by combining two components, or ``None`` if no recipe.

        Order-independent. Returns ``None`` rather than raising for an unused
        pair, since "these two do not combine" is a normal answer.
        """
        for component_id in (component_a, component_b):
            component = self.get(component_id)
            if not component.is_component:
                raise ItemError(
                    f"{component_id!r} is not a component and cannot be combined"
                )
        return self._by_recipe.get(recipe_key(component_a, component_b))

    def radiant_version(self, item_id: str) -> str | None:
        """The radiant upgrade of ``item_id``, if the dataset defines one."""
        self.get(item_id)
        return self._radiant_by_base.get(item_id)

    @property
    def components(self) -> tuple[ItemDef, ...]:
        return tuple(i for i in self.items.values() if i.is_component)

    @property
    def combinable_pairs(self) -> int:
        return len(self._by_recipe)

    def validate_loadout(self, item_ids: Iterable[str]) -> None:
        """Check an equip loadout, raising :class:`ItemError` if illegal.

        Enforces the slot cap (doc 01 sec 5) and the ``unique`` flag, which
        forbids two copies of the same unique item on one unit.
        """
        loadout = list(item_ids)
        if len(loadout) > self.max_items_per_unit:
            raise ItemError(
                f"a unit may hold at most {self.max_items_per_unit} items, "
                f"got {len(loadout)}"
            )
        seen: set[str] = set()
        for item_id in loadout:
            item = self.get(item_id)
            if item.unique and item_id in seen:
                raise ItemError(f"{item.display_name} is unique and cannot be stacked")
            seen.add(item_id)


def item_bonuses(items: Iterable[ItemDef]) -> StatBonuses:
    """Sum the flat stat grants of a unit's equipped items."""
    bonuses = StatBonuses()
    for item in items:
        bonuses.add_all(item.stats)
    return bonuses
