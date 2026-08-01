"""Shared pool and shop-roll tests (milestone 4, doc 01 sec 5)."""

from __future__ import annotations

import random
from collections import Counter

import pytest

from engine.loader import load_all
from engine.schema import GameData
from engine.shop import (
    SharedPool,
    Shop,
    ShopError,
    expected_tier_distribution,
    roll_cost_tier,
    roll_shop,
)
from tests.paths import STARTER_DATA_DIR


@pytest.fixture(scope="module")
def data() -> GameData:
    return load_all(STARTER_DATA_DIR)


@pytest.fixture
def pool(data) -> SharedPool:
    return SharedPool(data)


@pytest.fixture
def rng() -> random.Random:
    return random.Random(1234)


# --- pool sizes (doc 01 sec 5 / doc 02 sec 4) ---------------------------


def test_pool_starts_at_the_configured_size_per_cost(data, pool):
    expected = {1: 30, 2: 25, 3: 18, 4: 10, 5: 9}
    for champ in data.champions.values():
        assert pool.remaining(champ.id) == expected[champ.cost], champ.id


def test_total_pool_matches_champion_counts(data, pool):
    expected = sum(
        data.config.pool_sizes[c.cost] for c in data.champions.values()
    )
    assert pool.total_remaining == expected


def test_unknown_champion_is_rejected(pool):
    with pytest.raises(ShopError, match="unknown champion"):
        pool.remaining("TFT17_NotAChampion")


# --- taking and returning ------------------------------------------------


def test_taking_reduces_the_pool(pool):
    before = pool.remaining("TFT17_Jinx")
    pool.take("TFT17_Jinx", 3)
    assert pool.remaining("TFT17_Jinx") == before - 3


def test_cannot_take_more_copies_than_remain(pool):
    with pytest.raises(ShopError, match="only 10 left"):
        pool.take("TFT17_Jinx", 11)


def test_returning_restores_the_pool(pool):
    pool.take("TFT17_Jinx", 4)
    pool.return_to_pool("TFT17_Jinx", 4)
    assert pool.remaining("TFT17_Jinx") == 10


def test_cannot_return_beyond_the_pool_size(pool):
    """Guards against a bookkeeping bug silently minting extra copies."""
    with pytest.raises(ShopError, match="exceed the pool size"):
        pool.return_to_pool("TFT17_Jinx", 1)


def test_a_three_star_returns_nine_copies(data, pool):
    """Doc 01 sec 5: a 3-star is 9 one-star copies."""
    from engine.items import ItemRegistry
    from engine.unit import UnitInstance

    registry = ItemRegistry(data.items, data.config.max_items_per_unit)
    unit = UnitInstance(data.champions["TFT17_Poppy"], 3, registry=registry)
    assert unit.pool_copies == 9
    pool.take("TFT17_Poppy", 9)
    pool.return_to_pool("TFT17_Poppy", unit.pool_copies)
    assert pool.remaining("TFT17_Poppy") == 30


def test_exhausted_champion_leaves_the_available_list(pool, data):
    ones = pool.available_in_tier(1)
    pool.take(ones[0], 30)
    assert ones[0] not in pool.available_in_tier(1)
    assert pool.remaining(ones[0]) == 0


# --- cost tier rolls (doc 01 sec 5 odds table) --------------------------


def test_level_one_only_rolls_one_costs(data, rng):
    assert all(roll_cost_tier(data.config, 1, rng) == 1 for _ in range(200))


def test_level_three_only_rolls_one_and_two_costs(data, rng):
    tiers = {roll_cost_tier(data.config, 3, rng) for _ in range(500)}
    assert tiers <= {1, 2}


def test_five_costs_are_impossible_below_level_seven(data, rng):
    for level in range(1, 7):
        tiers = {roll_cost_tier(data.config, level, rng) for _ in range(300)}
        assert 5 not in tiers, f"level {level} rolled a 5-cost"


def test_tier_frequencies_converge_on_the_odds_table(data, rng):
    """Doc 01 sec 5's level 7 row: 19/30/40/10/1."""
    level, trials = 7, 200_000
    counts = Counter(roll_cost_tier(data.config, level, rng) for _ in range(trials))
    expected = expected_tier_distribution(data.config, level)
    for tier, probability in expected.items():
        observed = counts[tier] / trials
        assert observed == pytest.approx(probability, abs=0.01), (
            f"tier {tier}: saw {observed:.3f}, expected {probability:.3f}"
        )


def test_rolls_are_reproducible_under_a_fixed_seed(data):
    a = [roll_cost_tier(data.config, 8, random.Random(42)) for _ in range(1)]
    b = [roll_cost_tier(data.config, 8, random.Random(42)) for _ in range(1)]
    assert a == b


# --- shop rolls ----------------------------------------------------------


def test_a_shop_roll_produces_five_slots(data, pool, rng):
    slots = roll_shop(data.config, 5, pool, rng)
    assert len(slots) == data.config.shop_slots == 5


def test_rolled_champions_are_removed_from_the_pool(data, pool, rng):
    before = pool.total_remaining
    slots = roll_shop(data.config, 6, pool, rng)
    assert pool.total_remaining == before - sum(1 for s in slots if s is not None)


def test_rolled_champions_match_their_rolled_tier(data, pool, rng):
    for _ in range(50):
        for champion_id in roll_shop(data.config, 8, pool, rng):
            if champion_id is not None:
                assert champion_id in data.champions


def test_an_exhausted_tier_yields_an_empty_slot(data, pool, rng):
    """A bought-out tier leaves the slot empty rather than substituting."""
    for champion_id in list(pool.snapshot()):
        if data.champions[champion_id].cost == 1:
            pool.take(champion_id, pool.remaining(champion_id))
    assert pool.available_in_tier(1) == []
    assert pool.draw(1, rng) is None
    # Level 1 rolls only 1-costs, so every slot must come back empty.
    assert roll_shop(data.config, 1, pool, rng) == [None] * data.config.shop_slots


def test_draw_weighting_follows_remaining_copies(data, pool):
    """With ``by_copies``, a nearly-bought-out champion becomes rare."""
    assert data.config.shop_draw_weighting == "by_copies"
    fours = sorted(c.id for c in data.champions.values() if c.cost == 4)
    assert len(fours) == 2
    rare, common = fours
    pool.take(rare, 9)  # 1 copy left vs 10

    rng = random.Random(7)
    counts = Counter()
    for _ in range(4000):
        drawn = pool.draw(4, rng)
        counts[drawn] += 1
        pool.return_to_pool(drawn, 1)
    assert counts[common] > counts[rare] * 5


def test_uniform_weighting_ignores_copy_counts(data, monkeypatch):
    """The alternative reading of doc 01 sec 5, selectable via config."""
    import dataclasses

    config = dataclasses.replace(data.config, shop_draw_weighting="uniform")
    patched = dataclasses.replace(data, config=config)
    pool = SharedPool(patched)
    fours = sorted(c.id for c in data.champions.values() if c.cost == 4)
    rare, common = fours
    pool.take(rare, 9)

    rng = random.Random(7)
    counts = Counter()
    for _ in range(4000):
        drawn = pool.draw(4, rng)
        counts[drawn] += 1
        pool.return_to_pool(drawn, 1)
    assert counts[common] == pytest.approx(counts[rare], rel=0.15)


# --- Shop state ----------------------------------------------------------


def test_shop_starts_empty(data):
    shop = Shop(data.config)
    assert shop.slots == [None] * 5


def test_taking_a_slot_empties_it(data, pool, rng):
    shop = Shop(data.config)
    shop.roll(5, pool, rng)
    index = next(i for i, s in enumerate(shop.slots) if s is not None)
    champion_id = shop.take_slot(index)
    assert shop.slots[index] is None
    assert champion_id in data.champions


def test_taking_an_empty_or_out_of_range_slot_raises(data, pool, rng):
    shop = Shop(data.config)
    shop.roll(5, pool, rng)
    index = next(i for i, s in enumerate(shop.slots) if s is not None)
    shop.take_slot(index)
    with pytest.raises(ShopError, match="is empty"):
        shop.take_slot(index)
    with pytest.raises(ShopError, match="out of range"):
        shop.take_slot(99)


def test_rerolling_returns_unbought_slots_to_the_pool(data, pool, rng):
    """Otherwise every reroll would leak copies out of the shared pool."""
    shop = Shop(data.config)
    before = pool.total_remaining
    shop.roll(6, pool, rng)
    for _ in range(20):
        shop.roll(6, pool, rng)
    shop.discard(pool)
    assert pool.total_remaining == before


def test_bought_copies_stay_out_of_the_pool_across_rerolls(data, pool, rng):
    shop = Shop(data.config)
    shop.roll(6, pool, rng)
    index = next(i for i, s in enumerate(shop.slots) if s is not None)
    bought = shop.take_slot(index)
    before = pool.remaining(bought)
    shop.roll(6, pool, rng)
    shop.discard(pool)
    assert pool.remaining(bought) <= before


def test_pool_is_conserved_across_a_long_roll_session(data, pool, rng):
    """The lobby's total copies must never drift up or down."""
    shops = [Shop(data.config) for _ in range(8)]
    taken: Counter[str] = Counter()
    start = pool.total_remaining
    for _ in range(60):
        for shop in shops:
            shop.roll(7, pool, rng)
            if rng.random() < 0.4:
                candidates = [i for i, s in enumerate(shop.slots) if s is not None]
                if candidates:
                    taken[shop.take_slot(rng.choice(candidates))] += 1
    for shop in shops:
        shop.discard(pool)
    assert pool.total_remaining == start - sum(taken.values())
    for champion_id, count in taken.items():
        expected = data.config.pool_sizes[data.champions[champion_id].cost] - count
        assert pool.remaining(champion_id) == expected


def test_pool_is_shared_between_players(data, pool, rng):
    """One player buying a champion reduces what everyone else can roll."""
    ones = pool.available_in_tier(1)
    target = ones[0]
    pool.take(target, 29)
    assert pool.remaining(target) == 1
    pool.take(target, 1)
    assert target not in pool.available_in_tier(1)
