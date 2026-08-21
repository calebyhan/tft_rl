"""The unimplemented-trait stat fallback (doc 99 entry 152).

Doc 02 sec 2 promises that an unimplemented entry "still delivers its stat
half". For traits that promise was silently false: `normalise_trait` keeps
Riot's variable names (`AS`, `BonusHealth`) while `bonuses_from_params` matched
our schema names (`attack_speed_pct`, `health`), so the overlap was empty and
an unimplemented trait granted nothing at all.

The fix must not fire for *implemented* traits: all 35 Set 17 traits have
behaviour hooks that already spend these params via `ctx.number`, so a blanket
name mapping would grant every trait's stats twice.
"""

import pytest

from engine.schema import TraitBreakpoint
from engine.trait_effects import is_trait_implemented
from engine.traits import trait_bonuses_for
from tests.paths import REAL_DATA_DIR

TEAMWIDE = {"targets": "team"}


def _bp(effect_id, **params):
    return TraitBreakpoint(count=2, effect_id=effect_id, params={**TEAMWIDE, **params})


def test_unimplemented_trait_still_delivers_its_stat_half():
    trait_id = "TFT17_NotARealTrait"
    assert not is_trait_implemented(trait_id), "fixture assumes no hook exists"
    bonuses = trait_bonuses_for(
        None, {trait_id: _bp("trait_TFT17_NotARealTrait_2", AS=25.0, BonusHealth=200.0)}
    )
    assert bonuses.get("attack_speed_pct") == pytest.approx(0.25)
    assert bonuses.get("health") == pytest.approx(200.0)


def test_implemented_trait_does_not_double_apply_its_params():
    trait_id = "TFT17_ASTrait"
    assert is_trait_implemented(trait_id), "fixture assumes this trait is implemented"
    bonuses = trait_bonuses_for(
        None, {trait_id: _bp("trait_TFT17_ASTrait_2", AS=25.0, BonusHealth=200.0)}
    )
    assert bonuses.get("attack_speed_pct") == 0.0
    assert bonuses.get("health") == 0.0


def test_every_set17_trait_is_implemented_so_the_fallback_is_inert_today():
    """Why this fix changes no current measurement."""
    import json

    traits = json.loads((REAL_DATA_DIR / "traits.json").read_text())
    unimplemented = [t["id"] for t in traits if not is_trait_implemented(t["id"])]
    assert unimplemented == []


def test_trait_and_item_stat_maps_agree_on_shared_keys():
    """The two tables are separate by design; they must not contradict.

    Duplicating the mapping is what produced entry 152 in the first place, so
    the duplication is allowed but pinned.
    """
    import importlib.util

    from engine.stats import TRAIT_STAT_MAP
    from tests.paths import TESTS_DIR

    spec = importlib.util.spec_from_file_location(
        "_fetch", TESTS_DIR.parent / "scripts" / "fetch_cdragon.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    shared = set(TRAIT_STAT_MAP) & set(mod.ITEM_STAT_MAP)
    assert shared, "the two tables should overlap; an empty intersection is the bug"
    for key in sorted(shared):
        assert TRAIT_STAT_MAP[key] == mod.ITEM_STAT_MAP[key], key
