"""PlayerState planning-phase tests (milestone 4, doc 01 sec 4-5, doc 03 sec 2.10).

Illegal actions must raise :class:`IllegalAction` rather than no-op, so the RL
wrapper can mask them; several tests below assert exactly that.
"""

from __future__ import annotations

import random

import pytest

from engine.economy import RoundId
from engine.hexgrid import Board, axial_to_offset
from engine.items import ItemRegistry
from engine.loader import load_all
from engine.player import IllegalAction, PlayerState
from engine.schema import GameData
from engine.shop import SharedPool
from engine.unit import UnitInstance
from tests.paths import STARTER_DATA_DIR


@pytest.fixture(scope="module")
def data() -> GameData:
    return load_all(STARTER_DATA_DIR)


@pytest.fixture
def registry(data) -> ItemRegistry:
    return ItemRegistry(data.items, data.config.max_items_per_unit)


@pytest.fixture
def pool(data) -> SharedPool:
    return SharedPool(data)


@pytest.fixture
def player(data, registry) -> PlayerState:
    p = PlayerState(data, registry, player_id=0)
    p.gold = 50
    return p


@pytest.fixture
def rng() -> random.Random:
    return random.Random(99)


def stock_shop(player, *champion_ids, pool=None):
    """Put specific champions into the shop, bypassing the random roll.

    Still takes the copies out of the shared pool, exactly as a real roll does,
    so pool bookkeeping stays consistent across buy/sell.
    """
    if pool is not None:
        for champion_id in champion_ids:
            pool.take(champion_id)
    player.shop.slots = list(champion_ids) + [None] * (
        player.config.shop_slots - len(champion_ids)
    )


def own_hex(player, row=0, col=0):
    """A hex on the player's own half-board (row 0 = front line)."""
    return player.hex_board.to_combat(0, row, col)


# --- initial state -------------------------------------------------------


def test_player_starts_with_configured_hp_bench_and_level(data, registry):
    p = PlayerState(data, registry)
    assert p.hp == data.config.starting_hp == 100
    assert len(p.bench) == data.config.bench_size == 9
    assert p.level == 1 and p.xp == 0
    assert p.board == {} and p.alive


def test_board_size_is_the_players_level(player):
    player.level = 6
    assert player.max_board_units == 6


# --- buying --------------------------------------------------------------


def test_buying_spends_gold_and_puts_the_unit_on_the_bench(player, pool):
    stock_shop(player, "TFT17_Jinx")
    unit = player.buy(0, pool)
    assert player.gold == 46  # 50 - 4
    assert unit in player.bench_units
    assert player.shop.peek(0) is None


def test_buying_cannot_exceed_available_gold(player, pool):
    player.gold = 3
    stock_shop(player, "TFT17_Jinx")
    with pytest.raises(IllegalAction, match="needs 4"):
        player.buy(0, pool)
    assert player.gold == 3
    assert player.shop.peek(0) == "TFT17_Jinx", "a failed buy must not consume the slot"


def test_buying_an_empty_slot_raises(player, pool):
    with pytest.raises(IllegalAction, match="is empty"):
        player.buy(0, pool)


def test_buying_with_a_full_bench_raises(player, pool):
    player.bench = [
        UnitInstance(player.data.champions["TFT17_Corki"], registry=player.registry)
        for _ in range(9)
    ]
    stock_shop(player, "TFT17_Jinx")
    with pytest.raises(IllegalAction, match="bench is full"):
        player.buy(0, pool)


def test_a_full_bench_still_allows_a_buy_that_immediately_combines(player, pool):
    """TFT lets you buy the third copy even with no free bench slot."""
    player.bench = [
        UnitInstance(player.data.champions["TFT17_Poppy"], registry=player.registry)
        for _ in range(2)
    ] + [
        UnitInstance(player.data.champions["TFT17_Corki"], registry=player.registry)
        for _ in range(7)
    ]
    stock_shop(player, "TFT17_Poppy")
    unit = player.buy(0, pool)
    assert unit.star_level == 2


def test_can_buy_reports_without_raising(player, pool):
    stock_shop(player, "TFT17_Jinx")
    assert player.can_buy(0) is True
    player.gold = 0
    assert player.can_buy(0) is False


# --- combining -----------------------------------------------------------


def test_three_copies_combine_into_a_two_star(player, pool):
    for _ in range(3):
        stock_shop(player, "TFT17_Poppy")
        player.buy(0, pool)
    units = [u for u in player.all_units if u.champion.id == "TFT17_Poppy"]
    assert len(units) == 1
    assert units[0].star_level == 2


def test_nine_copies_cascade_into_a_three_star(player, pool):
    """Doc 01 sec 5: 9 one-star copies make a 3-star."""
    player.gold = 100
    for _ in range(9):
        stock_shop(player, "TFT17_Poppy")
        player.buy(0, pool)
    units = [u for u in player.all_units if u.champion.id == "TFT17_Poppy"]
    assert len(units) == 1 and units[0].star_level == 3


def test_combining_keeps_the_fielded_copy_on_the_board(player, pool):
    stock_shop(player, "TFT17_Poppy")
    player.buy(0, pool)
    hex_ = own_hex(player, 0, 3)
    player.move_to_board(0, hex_)
    for _ in range(2):
        stock_shop(player, "TFT17_Poppy")
        player.buy(0, pool)
    assert hex_ in player.board
    assert player.board[hex_].star_level == 2


def test_combining_inherits_items_from_the_consumed_copies(player, pool):
    stock_shop(player, "TFT17_Poppy")
    first = player.buy(0, pool)
    player.add_item("TFT_Item_Deathblade")
    player.equip_from_bag("TFT_Item_Deathblade", first)
    for _ in range(2):
        stock_shop(player, "TFT17_Poppy")
        player.buy(0, pool)
    survivor = next(u for u in player.all_units if u.champion.id == "TFT17_Poppy")
    assert survivor.star_level == 2
    assert [i.id for i in survivor.items] == ["TFT_Item_Deathblade"]


def test_items_beyond_the_slot_cap_fall_back_to_the_bag(player, pool):
    """A combine can salvage more items than the survivor can hold."""
    player.gold = 100

    def buy_poppy_with(*item_ids):
        stock_shop(player, "TFT17_Poppy")
        unit = player.buy(0, pool)
        for item_id in item_ids:
            player.add_item(item_id)
            player.equip_from_bag(item_id, unit)
        return unit

    # Two copies carrying 2 items each; the third triggers the combine, so the
    # survivor inherits 4 items but may only hold 3.
    buy_poppy_with("TFT_Item_Deathblade", "TFT_Item_WarmogsArmor")
    buy_poppy_with("TFT_Item_BrambleVest", "TFT_Item_DragonsClaw")
    assert player.item_bag == []
    buy_poppy_with()

    survivor = next(u for u in player.all_units if u.champion.id == "TFT17_Poppy")
    assert survivor.star_level == 2
    assert len(survivor.items) == player.config.max_items_per_unit == 3
    # Nothing is destroyed -- the overflow lands back in the bag.
    assert len(player.item_bag) == 1
    held = {i.id for i in survivor.items} | {i.id for i in player.item_bag}
    assert held == {
        "TFT_Item_Deathblade",
        "TFT_Item_WarmogsArmor",
        "TFT_Item_BrambleVest",
        "TFT_Item_DragonsClaw",
    }


def test_buy_returns_the_unit_just_bought_not_an_earlier_copy(player, pool):
    """Regression: buy() used to hand back the first copy of that champion,
    so equipping onto its return value hit the wrong unit."""
    stock_shop(player, "TFT17_Poppy")
    first = player.buy(0, pool)
    stock_shop(player, "TFT17_Poppy")
    second = player.buy(0, pool)
    assert second is not first
    assert first.star_level == second.star_level == 1


def test_buy_returns_the_upgraded_survivor_when_the_copy_is_consumed(player, pool):
    for _ in range(2):
        stock_shop(player, "TFT17_Poppy")
        player.buy(0, pool)
    stock_shop(player, "TFT17_Poppy")
    third = player.buy(0, pool)
    assert third.star_level == 2
    assert third in player.all_units


def test_two_different_champions_do_not_combine(player, pool):
    for champion_id in ("TFT17_Poppy", "TFT17_Kindred", "TFT17_Talon"):
        stock_shop(player, champion_id)
        player.buy(0, pool)
    assert all(u.star_level == 1 for u in player.all_units)
    assert len(player.all_units) == 3


# --- selling -------------------------------------------------------------


def test_selling_refunds_gold_and_frees_the_slot(player, pool):
    stock_shop(player, "TFT17_Jinx", pool=pool)
    unit = player.buy(0, pool)
    gold_before = player.gold
    refund = player.sell(unit, pool)
    assert refund == 4  # 4-cost 1-star, floored at cost
    assert player.gold == gold_before + 4
    assert unit not in player.all_units


def test_selling_returns_copies_to_the_shared_pool(player, pool):
    stock_shop(player, "TFT17_Poppy", pool=pool)
    player.buy(0, pool)
    assert pool.remaining("TFT17_Poppy") == 29
    player.sell(player.all_units[0], pool)
    assert pool.remaining("TFT17_Poppy") == 30


def test_selling_a_two_star_returns_three_copies(player, pool):
    for _ in range(3):
        stock_shop(player, "TFT17_Poppy", pool=pool)
        player.buy(0, pool)
    assert pool.remaining("TFT17_Poppy") == 27
    player.sell(player.all_units[0], pool)
    assert pool.remaining("TFT17_Poppy") == 30


def test_selling_returns_items_to_the_bag(player, pool):
    stock_shop(player, "TFT17_Jinx", pool=pool)
    unit = player.buy(0, pool)
    player.add_item("TFT_Item_Deathblade")
    player.equip_from_bag("TFT_Item_Deathblade", unit)
    assert player.item_bag == []
    player.sell(unit, pool)
    assert [i.id for i in player.item_bag] == ["TFT_Item_Deathblade"]


def test_selling_a_unit_the_player_does_not_own_raises(player, pool, data, registry):
    stranger = UnitInstance(data.champions["TFT17_Jinx"], registry=registry)
    with pytest.raises(IllegalAction, match="does not own"):
        player.sell(stranger, pool)


def test_selling_an_empty_slot_raises(player, pool):
    with pytest.raises(IllegalAction, match="is empty"):
        player.sell_bench_slot(0, pool)
    with pytest.raises(IllegalAction, match="no unit on"):
        player.sell_board_hex(own_hex(player), pool)


# --- moving --------------------------------------------------------------


def test_moving_from_bench_to_board(player, pool):
    stock_shop(player, "TFT17_Jinx")
    unit = player.buy(0, pool)
    hex_ = own_hex(player, 0, 3)
    player.move_to_board(0, hex_)
    assert player.board[hex_] is unit
    assert player.bench[0] is None


def test_board_capacity_is_capped_by_level(player, pool):
    player.gold = 100
    player.level = 2
    for i in range(3):
        stock_shop(player, "TFT17_Kindred" if i == 0 else "TFT17_Corki")
        player.buy(0, pool)
    player.move_to_board(0, own_hex(player, 0, 0))
    player.move_to_board(1, own_hex(player, 0, 1))
    with pytest.raises(IllegalAction, match="can field 2 units"):
        player.move_to_board(2, own_hex(player, 0, 2))


def test_swapping_a_benched_unit_with_a_fielded_one_ignores_the_cap(player, pool):
    """A swap keeps the fielded count constant, so it stays legal at the cap."""
    player.level = 1
    for champion_id in ("TFT17_Jinx", "TFT17_Corki"):
        stock_shop(player, champion_id)
        player.buy(0, pool)
    hex_ = own_hex(player, 0, 3)
    player.move_to_board(0, hex_)
    jinx = player.board[hex_]
    player.move_to_board(1, hex_)
    assert player.board[hex_].champion.id == "TFT17_Corki"
    assert jinx in player.bench_units


def test_moving_within_the_board_swaps_occupants(player, pool):
    for champion_id in ("TFT17_Jinx", "TFT17_Corki"):
        stock_shop(player, champion_id)
        player.buy(0, pool)
    player.level = 4
    a, b = own_hex(player, 0, 1), own_hex(player, 2, 5)
    player.move_to_board(0, a)
    player.move_to_board(1, b)
    unit_a, unit_b = player.board[a], player.board[b]
    player.move_on_board(a, b)
    assert player.board[b] is unit_a
    assert player.board[a] is unit_b


def test_moving_to_an_empty_hex_vacates_the_source(player, pool):
    stock_shop(player, "TFT17_Jinx")
    player.buy(0, pool)
    a, b = own_hex(player, 0, 1), own_hex(player, 3, 5)
    player.move_to_board(0, a)
    player.move_on_board(a, b)
    assert a not in player.board and b in player.board


def test_cannot_place_a_unit_on_the_opponents_half(player, pool):
    stock_shop(player, "TFT17_Jinx")
    player.buy(0, pool)
    enemy_hex = player.hex_board.to_combat(1, 0, 3)
    with pytest.raises(IllegalAction, match="not on .* half-board"):
        player.move_to_board(0, enemy_hex)


def test_moving_back_to_the_bench(player, pool):
    stock_shop(player, "TFT17_Jinx")
    player.buy(0, pool)
    hex_ = own_hex(player, 0, 3)
    player.move_to_board(0, hex_)
    player.move_to_bench(hex_)
    assert hex_ not in player.board
    assert len(player.bench_units) == 1


def test_moving_to_the_bench_with_no_free_slot_raises(player, pool):
    stock_shop(player, "TFT17_Jinx")
    player.buy(0, pool)
    hex_ = own_hex(player, 0, 3)
    player.move_to_board(0, hex_)
    player.bench = [
        UnitInstance(player.data.champions["TFT17_Corki"], registry=player.registry)
        for _ in range(9)
    ]
    with pytest.raises(IllegalAction, match="bench is full"):
        player.move_to_bench(hex_)


def test_moving_an_empty_bench_slot_or_hex_raises(player):
    with pytest.raises(IllegalAction, match="is empty"):
        player.move_to_board(0, own_hex(player))
    with pytest.raises(IllegalAction, match="no unit on"):
        player.move_to_bench(own_hex(player))
    with pytest.raises(IllegalAction, match="out of range"):
        player.move_to_board(99, own_hex(player))


# --- items ---------------------------------------------------------------


def test_equipping_a_completed_item_from_the_bag(player, pool):
    stock_shop(player, "TFT17_Jinx")
    unit = player.buy(0, pool)
    player.add_item("TFT_Item_Deathblade")
    player.equip_from_bag("TFT_Item_Deathblade", unit)
    assert [i.id for i in unit.items] == ["TFT_Item_Deathblade"]
    assert player.item_bag == []


def test_two_components_on_one_unit_combine_automatically(player, pool):
    """Dropping Sparring Gloves onto a unit holding a B.F. Sword makes an IE."""
    stock_shop(player, "TFT17_Jinx")
    unit = player.buy(0, pool)
    player.add_item("TFT_Item_BFSword")
    player.add_item("TFT_Item_SparringGloves")
    player.equip_from_bag("TFT_Item_BFSword", unit)
    player.equip_from_bag("TFT_Item_SparringGloves", unit)
    assert [i.id for i in unit.items] == ["TFT_Item_InfinityEdge"]
    assert unit.derived_stats().attack_damage == 65 + 15
    assert unit.derived_stats().crit_chance == 0.25 + 0.25


def test_components_with_no_recipe_stay_separate(player, pool):
    stock_shop(player, "TFT17_Jinx")
    unit = player.buy(0, pool)
    for item_id in ("TFT_Item_ChainVest", "TFT_Item_TearOfTheGoddess"):
        player.add_item(item_id)
        player.equip_from_bag(item_id, unit)
    assert len(unit.items) == 2


def test_equipping_an_item_not_in_the_bag_raises(player, pool):
    stock_shop(player, "TFT17_Jinx")
    unit = player.buy(0, pool)
    with pytest.raises(IllegalAction, match="no 'TFT_Item_Deathblade'"):
        player.equip_from_bag("TFT_Item_Deathblade", unit)


def test_exceeding_the_item_cap_raises_and_keeps_the_item(player, pool):
    stock_shop(player, "TFT17_Jinx")
    unit = player.buy(0, pool)
    for _ in range(3):
        player.add_item("TFT_Item_Deathblade")
        player.equip_from_bag("TFT_Item_Deathblade", unit)
    player.add_item("TFT_Item_Deathblade")
    with pytest.raises(IllegalAction, match="at most 3 items"):
        player.equip_from_bag("TFT_Item_Deathblade", unit)
    assert len(player.item_bag) == 1, "the item must go back to the bag"


def test_equipping_onto_a_unit_the_player_does_not_own_raises(player, data, registry):
    stranger = UnitInstance(data.champions["TFT17_Jinx"], registry=registry)
    player.add_item("TFT_Item_Deathblade")
    with pytest.raises(IllegalAction, match="does not own"):
        player.equip_from_bag("TFT_Item_Deathblade", stranger)


# --- shop and XP ---------------------------------------------------------


def test_reroll_costs_gold_and_refreshes_the_shop(player, pool, rng):
    player.gold = 10
    player.roll_shop(pool, rng)
    before = list(player.shop.slots)
    player.reroll(pool, rng)
    assert player.gold == 8
    assert player.shop.slots != before or before == [None] * 5


def test_reroll_without_enough_gold_raises(player, pool, rng):
    player.gold = 1
    with pytest.raises(IllegalAction, match="reroll costs 2"):
        player.reroll(pool, rng)
    assert player.gold == 1


def test_buying_xp_costs_four_gold_for_four_xp(player):
    player.gold = 10
    player.level, player.xp = 3, 0
    player.buy_xp()
    assert player.gold == 6
    # Level 3 needs 6 XP, so 4 XP leaves the player still level 3.
    assert player.level == 3 and player.xp == 4
    player.buy_xp()
    assert player.level == 4 and player.xp == 2


def test_buying_xp_without_gold_raises(player):
    player.gold = 3
    with pytest.raises(IllegalAction, match="costs 4"):
        player.buy_xp()


def test_buying_xp_at_max_level_raises(player):
    player.level = player.config.max_level
    with pytest.raises(IllegalAction, match="max level"):
        player.buy_xp()


# --- round transitions ---------------------------------------------------


def test_income_is_paid_and_passive_xp_granted(player):
    player.gold = 20
    player.level, player.xp = 5, 0
    breakdown = player.award_income(RoundId(3, 2))
    assert breakdown.base == 5 and breakdown.interest == 2
    assert player.gold == 20 + 7
    assert player.xp == 2  # passive trickle


def test_streaks_build_and_reset(player):
    for _ in range(3):
        player.record_result(won=True)
    assert (player.streak_type, player.streak_count) == ("win", 3)
    player.record_result(won=False)
    assert (player.streak_type, player.streak_count) == ("loss", 1)


def test_a_streak_pays_out_through_award_income(player):
    player.gold = 0
    for _ in range(5):
        player.record_result(won=True)
    breakdown = player.award_income(RoundId(3, 2), won_pvp=True)
    assert breakdown.streak == 2 and breakdown.win_bonus == 1
    assert player.gold == 8


def test_damage_reduces_hp_and_cannot_go_negative(player):
    player.take_damage(30)
    assert player.hp == 70
    lost = player.take_damage(500)
    assert lost == 70 and player.hp == 0
    assert not player.alive


def test_elimination_returns_every_unit_to_the_pool(player, pool, rng):
    player.gold = 100
    for champion_id in ("TFT17_Poppy", "TFT17_Poppy", "TFT17_Poppy", "TFT17_Jinx"):
        stock_shop(player, champion_id, pool=pool)
        player.buy(0, pool)
    player.move_to_board(0, own_hex(player, 0, 3))
    player.roll_shop(pool, rng)
    start = SharedPool(player.data).total_remaining

    player.release_all_to_pool(pool)
    assert pool.total_remaining == start
    assert player.all_units == []


# --- pool conservation ---------------------------------------------------


def total_copies_held(player):
    return sum(u.pool_copies for u in player.all_units)


def test_a_rejected_buy_mutates_nothing(player, pool):
    """Regression: buy() used to spend gold and empty the slot before checking
    that the unit had somewhere to go, destroying the copy."""
    player.bench = [
        UnitInstance(player.data.champions["TFT17_Corki"], registry=player.registry)
        for _ in range(9)
    ]
    stock_shop(player, "TFT17_Jinx", pool=pool)
    gold_before = player.gold
    pool_before = pool.total_remaining

    with pytest.raises(IllegalAction):
        player.buy(0, pool)

    assert player.gold == gold_before
    assert player.shop.peek(0) == "TFT17_Jinx"
    assert pool.total_remaining == pool_before


def test_buying_the_combining_copy_with_a_full_bench_keeps_the_bench_intact(player, pool):
    player.bench = [
        UnitInstance(player.data.champions["TFT17_Poppy"], registry=player.registry)
        for _ in range(2)
    ] + [
        UnitInstance(player.data.champions["TFT17_Corki"], registry=player.registry)
        for _ in range(7)
    ]
    stock_shop(player, "TFT17_Poppy", pool=pool)
    player.buy(0, pool)
    assert len(player.bench) == player.config.bench_size
    poppies = [u for u in player.all_units if u.champion.id == "TFT17_Poppy"]
    assert len(poppies) == 1 and poppies[0].star_level == 2


@pytest.mark.parametrize("seed", range(8))
def test_pool_is_conserved_across_a_random_planning_session(data, registry, seed):
    """Every copy is always in exactly one of: the pool, a shop, or a player."""
    rng = random.Random(seed)
    pool = SharedPool(data)
    start = pool.total_remaining
    players = [PlayerState(data, registry, player_id=i) for i in range(4)]
    for p in players:
        p.gold = 40

    def audit():
        held = sum(total_copies_held(p) for p in players)
        in_shops = sum(1 for p in players for s in p.shop.slots if s is not None)
        assert pool.total_remaining + held + in_shops == start

    for _ in range(25):
        for p in players:
            p.roll_shop(pool, rng)
            audit()
            for slot in range(len(p.shop)):
                if rng.random() < 0.6 and p.can_buy(slot):
                    p.buy(slot, pool)
            audit()
            if p.all_units and rng.random() < 0.25:
                p.sell(rng.choice(p.all_units), pool)
            audit()
            if rng.random() < 0.3 and p.gold >= p.config.reroll_cost:
                p.reroll(pool, rng)
            audit()
            p.gold += 10

    for p in players:
        p.release_all_to_pool(pool)
    assert pool.total_remaining == start


def test_pool_never_exceeds_its_configured_size(data, registry):
    """A bookkeeping bug that minted copies would trip the pool's own guard."""
    rng = random.Random(3)
    pool = SharedPool(data)
    p = PlayerState(data, registry)
    p.gold = 200
    for _ in range(30):
        p.roll_shop(pool, rng)
        for slot in range(len(p.shop)):
            if p.can_buy(slot):
                p.buy(slot, pool)
        for unit in list(p.all_units):
            p.sell(unit, pool)
        p.gold += 50
    for champion_id, remaining in pool.snapshot().items():
        assert remaining <= data.config.pool_sizes[data.champions[champion_id].cost]


# --- combat handoff ------------------------------------------------------


def test_deploy_maps_own_hexes_onto_the_assigned_side(player, pool):
    player.gold = 100
    player.level = 4
    for champion_id in ("TFT17_Jinx", "TFT17_Poppy"):
        stock_shop(player, champion_id)
        player.buy(0, pool)
    player.move_to_board(0, own_hex(player, 3, 0))  # back row, left
    player.move_to_board(1, own_hex(player, 0, 3))  # front row, centre

    board = Board()
    as_team_0 = player.deploy_for_combat(0, board)
    assert {u.team for u in as_team_0} == {0}
    assert all(u.position in set(board.half_board_hexes(0)) for u in as_team_0)

    as_team_1 = player.deploy_for_combat(1, board)
    assert {u.team for u in as_team_1} == {1}
    assert all(u.position in set(board.half_board_hexes(1)) for u in as_team_1)


def test_deploy_preserves_relative_formation(player, pool):
    """A unit placed on the front line must stay on the front line as team 1."""
    player.level = 4
    for champion_id in ("TFT17_Jinx", "TFT17_Poppy"):
        stock_shop(player, champion_id)
        player.buy(0, pool)
    player.move_to_board(0, own_hex(player, 0, 3))  # front
    player.move_to_board(1, own_hex(player, 3, 3))  # back

    board = Board()
    units = player.deploy_for_combat(1, board)
    front = next(u for u in units if u.champion.id == "TFT17_Jinx")
    back = next(u for u in units if u.champion.id == "TFT17_Poppy")
    # Team 1's front line is the row nearest the centre (row 3 of 0-7).
    assert axial_to_offset(front.position)[0] == 3
    assert axial_to_offset(back.position)[0] == 0


def test_deployed_units_never_share_a_hex(player, pool):
    player.gold = 100
    player.level = 6
    champions = ["TFT17_Poppy", "TFT17_Jinx", "TFT17_Corki", "TFT17_Lulu"]
    for i, champion_id in enumerate(champions):
        stock_shop(player, champion_id)
        player.buy(0, pool)
        player.move_to_board(0, own_hex(player, i % 4, i))
    for team in (0, 1):
        positions = [u.position for u in player.deploy_for_combat(team)]
        assert len(positions) == len(set(positions))
