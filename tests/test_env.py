"""RL environment tests (milestone 6, doc 03 sec 3).

The central invariant is that the **action mask and the executor agree**: every
action the mask calls legal must apply without raising, and the mask must never
be empty. A mismatch would have the agent learning from silent no-ops or
crashing mid-training.
"""

from __future__ import annotations

import random

import numpy as np
import pytest

from engine.items import ItemRegistry
from engine.loader import load_all
from engine.player import IllegalAction, PlayerState
from engine.schema import GameData
from rl.action import ActionKind, ActionSpace
from rl.env import TFTEnv, rollout
from rl.observation import ObservationEncoder
from rl.opponents import RandomPolicy
from tests.paths import STARTER_DATA_DIR


@pytest.fixture(scope="module")
def data() -> GameData:
    return load_all(STARTER_DATA_DIR)


@pytest.fixture(scope="module")
def registry(data) -> ItemRegistry:
    return ItemRegistry(data.items, data.config.max_items_per_unit)


@pytest.fixture
def env(data) -> TFTEnv:
    return TFTEnv(data=data, seed=1)


@pytest.fixture
def space(data) -> ActionSpace:
    from engine.hexgrid import Board

    s = ActionSpace(data.config)
    s.bind_board(Board().half_board_hexes(0))
    return s


# --- action space --------------------------------------------------------


def test_every_index_decodes_and_round_trips(space):
    for index in range(space.n):
        action = space.decode(index)
        assert space.encode(action) == index


def test_out_of_range_index_is_rejected(space):
    with pytest.raises(ValueError):
        space.decode(space.n)
    with pytest.raises(ValueError):
        space.decode(-1)


def test_action_blocks_are_contiguous_and_sized_correctly(space):
    kinds = [space.decode(i).kind for i in range(space.n)]
    assert kinds.count(ActionKind.BUY) == space.shop_slots == 5
    assert kinds.count(ActionKind.SELL) == space.unit_slots
    assert kinds.count(ActionKind.SELECT) == space.unit_slots
    assert kinds.count(ActionKind.PLACE) == space.unit_slots
    assert kinds.count(ActionKind.EQUIP) == space.item_bag_slots * space.unit_slots
    for singleton in (ActionKind.REROLL, ActionKind.BUY_XP, ActionKind.END_PLANNING):
        assert kinds.count(singleton) == 1


def test_slot_indexing_covers_board_then_bench(space, data):
    assert space.board_slots == 28
    assert space.unit_slots == 28 + data.config.bench_size == 37
    assert space.hex_for_slot(0) is not None
    assert space.hex_for_slot(27) is not None
    assert space.hex_for_slot(28) is None
    assert space.bench_index_for_slot(28) == 0
    assert space.bench_index_for_slot(36) == data.config.bench_size - 1
    assert space.bench_index_for_slot(27) is None


def test_move_space_is_linear_not_quadratic(space):
    """SELECT/PLACE keeps moves at O(slots), not O(slots^2)."""
    assert space.n < 600
    assert space.n < space.unit_slots**2


# --- mask correctness ----------------------------------------------------


def test_mask_is_never_empty(env):
    env.reset(seed=1)
    assert env.action_mask().any()


def test_end_planning_is_always_legal(env):
    env.reset(seed=1)
    assert env.action_mask()[env.action_space_helper.end_index]


def test_buying_is_masked_out_without_gold(env):
    env.reset(seed=1)
    env.player.gold = 0
    mask = env.action_mask()
    assert not any(mask[: env.action_space_helper.shop_slots])


def test_buying_is_legal_with_gold_and_a_stocked_shop(env):
    env.reset(seed=1)
    env.player.gold = 50
    mask = env.action_mask()
    stocked = [i for i, c in enumerate(env.player.shop.slots) if c is not None]
    assert all(mask[i] for i in stocked)


def test_selling_an_empty_slot_is_masked_out(env):
    env.reset(seed=1)
    space = env.action_space_helper
    mask = env.action_mask()
    for slot in range(space.unit_slots):
        if env.executor.unit_at(env.player, slot) is None:
            assert not mask[space.sell_offset + slot]


def test_place_is_only_legal_after_a_select(env):
    env.reset(seed=1)
    space = env.action_space_helper
    env.player.gold = 20
    stocked = next(i for i, c in enumerate(env.player.shop.slots) if c is not None)
    env.step(stocked)

    mask = env.action_mask()
    assert not any(mask[space.place_offset : space.place_offset + space.unit_slots])
    bench_slot = space.slot_for_bench(0)
    assert mask[space.select_offset + bench_slot]

    env.step(space.select_offset + bench_slot)
    mask = env.action_mask()
    assert any(mask[space.place_offset : space.place_offset + space.unit_slots])
    # Selecting is unavailable while something is already held.
    assert not any(mask[space.select_offset : space.select_offset + space.unit_slots])


def test_bench_to_bench_moves_are_masked_out(env):
    """Regression: the mask allowed them but the executor rejected them."""
    env.reset(seed=1)
    space = env.action_space_helper
    env.player.gold = 40
    for slot in [i for i, c in enumerate(env.player.shop.slots) if c is not None][:2]:
        if env.action_mask()[slot]:
            env.step(slot)
    env.step(space.select_offset + space.slot_for_bench(0))
    mask = env.action_mask()
    for bench_index in range(env.data.config.bench_size):
        assert not mask[space.place_offset + space.slot_for_bench(bench_index)]


def test_fielding_is_masked_out_at_the_board_cap(env, data):
    env.reset(seed=1)
    space = env.action_space_helper
    player = env.player
    player.gold = 100
    player.level = 1
    # Buy two units, field one; the second must not be fieldable at level 1.
    bought = 0
    while bought < 2:
        legal = [i for i in range(space.shop_slots) if env.action_mask()[i]]
        if not legal:
            player.roll_shop(env.match.pool, env.match.rng)
            continue
        env.step(legal[0])
        bought += 1
    env.step(space.select_offset + space.slot_for_bench(0))
    places = [i for i in range(space.place_offset, space.place_offset + space.unit_slots)
              if env.action_mask()[i]]
    env.step(places[0])
    assert len(player.board) == 1

    env.step(space.select_offset + space.slot_for_bench(1))
    mask = env.action_mask()
    empty_board_slots = [
        s for s in range(space.board_slots)
        if space.hex_for_slot(s) not in player.board
    ]
    assert not any(mask[space.place_offset + s] for s in empty_board_slots), (
        "fielding a second unit at level 1 must be illegal"
    )


def test_equip_is_masked_out_with_an_empty_bag(env):
    env.reset(seed=1)
    space = env.action_space_helper
    mask = env.action_mask()
    assert not any(mask[space.equip_offset : space.reroll_index])


def test_equip_becomes_legal_with_an_item_and_a_unit(env):
    env.reset(seed=1)
    space = env.action_space_helper
    env.player.gold = 20
    stocked = next(i for i, c in enumerate(env.player.shop.slots) if c is not None)
    env.step(stocked)
    env.player.add_item("TFT_Item_Deathblade")
    mask = env.action_mask()
    bench_slot = space.slot_for_bench(0)
    assert mask[space.equip_offset + 0 * space.unit_slots + bench_slot]


def test_buy_xp_is_masked_out_at_max_level(env):
    env.reset(seed=1)
    env.player.level = env.data.config.max_level
    env.player.gold = 100
    assert not env.action_mask()[env.action_space_helper.buy_xp_index]


def test_a_selection_consumed_by_a_combine_is_dropped(env):
    """Regression: buying a unit's third copy combines away a SELECTed bench
    unit, leaving the selection pointing at an empty slot."""
    space = env.action_space_helper
    env.reset(seed=1)
    player = env.player
    player.gold = 100

    for _ in range(2):
        player.shop.slots = ["TFT17_Poppy"] + [None] * 4
        env.match.pool.take("TFT17_Poppy")
        env.step(0)
    assert len(player.bench_units) == 2

    env.step(space.select_offset + space.slot_for_bench(1))
    assert env.executor.selected is not None

    # The third copy combines, consuming the selected bench unit.
    player.shop.slots = ["TFT17_Poppy"] + [None] * 4
    env.match.pool.take("TFT17_Poppy")
    env.step(0)

    assert env.executor.selected is None, "stale selection was not cleared"
    mask = env.action_mask()
    assert not any(mask[space.place_offset : space.place_offset + space.unit_slots])
    assert any(mask[space.select_offset : space.select_offset + space.unit_slots])


# --- the central invariant ----------------------------------------------


@pytest.mark.parametrize("seed", range(5))
def test_every_masked_legal_action_applies_without_raising(data, seed):
    """Fuzz: sample only from the mask, and no action may raise IllegalAction."""
    env = TFTEnv(data=data, seed=seed)
    rng = random.Random(seed)
    env.reset(seed=seed)
    terminated = False
    steps = 0
    while not terminated and steps < 600:
        mask = env.action_mask()
        assert mask.any(), "mask went empty"
        legal = np.flatnonzero(mask)
        action = int(rng.choice(list(legal)))
        try:
            _, _, terminated, _, _ = env.step(action)
        except IllegalAction as exc:
            decoded = env.action_space_helper.decode(action)
            pytest.fail(f"mask allowed {decoded!r} but it raised: {exc}")
        steps += 1


def test_strict_mode_raises_on_an_unmasked_illegal_action(data):
    """Doc 03 sec 2.10: the engine raises so the wrapper can mask."""
    env = TFTEnv(data=data, strict_actions=True)
    env.reset(seed=1)
    env.player.gold = 0
    with pytest.raises(IllegalAction):
        env.step(0)  # buying with no gold


def test_default_mode_reports_an_illegal_action_instead_of_crashing(data):
    """Training loops that ignore the mask must not blow up mid-rollout."""
    env = TFTEnv(data=data, invalid_action_penalty=-0.01)
    env.reset(seed=1)
    env.player.gold = 0
    gold_before = env.player.gold
    _, reward, _, _, info = env.step(0)
    assert info["illegal_action"] is True
    assert reward == pytest.approx(-0.01)
    assert env.player.gold == gold_before, "an illegal action must change nothing"


def test_legal_actions_are_not_flagged_as_illegal(env):
    env.reset(seed=1)
    _, _, _, _, info = env.step(env.action_space_helper.end_index)
    assert info["illegal_action"] is False


# --- observations --------------------------------------------------------


def test_observation_matches_the_declared_space(env):
    obs, _ = env.reset(seed=1)
    assert obs.shape == env.observation_space.shape
    assert obs.dtype == np.float32
    assert env.observation_space.contains(obs)


def test_observation_encodes_selection_state(env):
    """Regression (judgement doc 6c.10): the policy was blind to whether it
    was holding a unit, which is exactly what decides SELECT vs PLACE."""
    space = env.action_space_helper
    spec = env.encoder.spec
    start = spec.offset_of("selection")
    env.reset(seed=1)
    env.player.gold = 50

    env.step(next(i for i, c in enumerate(env.player.shop.slots) if c is not None))
    idle = env._observe()[start : start + 7]
    assert idle[0] == 0.0, "nothing held, yet the observation says otherwise"

    env.step(space.select_offset + space.slot_for_bench(0))
    held = env._observe()[start : start + 7]
    assert held[0] == 1.0, "holding a unit must be visible to the policy"
    assert held[1] > 0.0, "which slot is held must be visible"
    assert held[6] > 0.0, "the held unit's attack range drives front/back placement"


def test_selection_features_distinguish_melee_from_ranged(env, data):
    """Placement quality depends on range, so it must be a feature."""
    space = env.action_space_helper
    start = env.encoder.spec.offset_of("selection")

    ranges = {}
    for champion_id in ("TFT17_Poppy", "TFT17_Jinx"):  # range 1 vs range 4
        env.reset(seed=1)
        env.player.gold = 50
        env.player.shop.slots = [champion_id] + [None] * 4
        env.match.pool.take(champion_id)
        env.step(0)
        env.step(space.select_offset + space.slot_for_bench(0))
        ranges[champion_id] = env._observe()[start + 6]
    assert ranges["TFT17_Jinx"] > ranges["TFT17_Poppy"]


def test_selection_block_clears_once_the_unit_is_placed(env):
    space = env.action_space_helper
    start = env.encoder.spec.offset_of("selection")
    env.reset(seed=1)
    env.player.gold = 50
    env.step(next(i for i, c in enumerate(env.player.shop.slots) if c is not None))
    env.step(space.select_offset + space.slot_for_bench(0))
    assert env._observe()[start] == 1.0
    places = [
        i for i in range(space.place_offset, space.place_offset + space.board_slots)
        if env.action_mask()[i]
    ]
    env.step(places[0])
    assert env._observe()[start] == 0.0


def test_section_offsets_are_consistent_with_widths(env):
    spec = env.encoder.spec
    cursor = 0
    for name, width in spec.describe():
        assert spec.offset_of(name) == cursor
        cursor += width
    assert cursor == spec.size


def test_observation_sections_sum_to_the_total(env):
    spec = env.encoder.spec
    assert sum(width for _, width in spec.describe()) == spec.size


def test_observation_features_stay_in_range(data):
    """Every feature is normalised, so the Box bounds are never violated."""
    env = TFTEnv(data=data, seed=4)
    rng = random.Random(4)
    obs, _ = env.reset(seed=4)
    terminated = False
    for _ in range(200):
        if terminated:
            break
        assert np.all(obs >= -1.0) and np.all(obs <= 1.0)
        obs, _, terminated, _, _ = env.step(env.sample_legal_action(rng))


def test_observation_reflects_state_changes(env):
    obs_before, _ = env.reset(seed=1)
    env.player.gold = 90
    env.player.hp = 40
    obs_after = env._observe()
    assert not np.array_equal(obs_before, obs_after)
    assert obs_after[0] == pytest.approx(0.9)  # gold
    assert obs_after[3] == pytest.approx(0.4)  # hp


def test_opponent_features_are_public_info_only(data, registry):
    """Doc 03 sec 3.1: v1 exposes opponent HP/level/streak, not their boards."""
    from engine.hexgrid import Board

    encoder = ObservationEncoder(data, 28, 7)
    spec = encoder.spec
    player = PlayerState(data, registry, player_id=0)
    opponent = PlayerState(data, registry, player_id=1)
    opponent.hp, opponent.level = 50, 6

    from engine.economy import RoundId

    hexes = Board().half_board_hexes(0)
    baseline = encoder.encode(player, RoundId(2, 1), [opponent], hexes)

    # Giving the opponent a board must not change the observation at all.
    opponent.gold = 50
    opponent.shop.slots = [next(iter(data.champions))] * data.config.shop_slots
    opponent.buy(0)
    with_board = encoder.encode(player, RoundId(2, 1), [opponent], hexes)
    assert np.array_equal(baseline, with_board)

    # But changing HP does.
    opponent.hp = 10
    assert not np.array_equal(baseline, encoder.encode(player, RoundId(2, 1), [opponent], hexes))
    del spec


def test_active_traits_appear_in_the_observation(env, data):
    env.reset(seed=1)
    space = env.action_space_helper
    player = env.player
    player.level = 4
    player.gold = 100
    # Field two Snipers to activate the trait.
    for champion_id in ("TFT17_Jinx", "TFT17_Kindred"):
        player.shop.slots = [champion_id] + [None] * 4
        env.match.pool.take(champion_id)
        env.step(0)
    # Distinct hexes: placing onto an occupied hex swaps, which would just
    # bounce the first unit back to the bench.
    for bench_index, board_slot in ((0, 0), (1, 5)):
        env.step(space.select_offset + space.slot_for_bench(bench_index))
        assert env.action_mask()[space.place_offset + board_slot]
        env.step(space.place_offset + board_slot)
    assert len(player.board) == 2
    obs = env._observe()
    trait_start = env.encoder.spec.offset_of("traits")
    trait_index = sorted(data.traits).index("Sniper")
    assert obs[trait_start + trait_index] > 0


# --- environment lifecycle ----------------------------------------------


def test_reset_returns_a_fresh_game(env):
    env.reset(seed=1)
    for _ in range(5):
        env.step(env.action_space_helper.end_index)
    env.reset(seed=1)
    assert env.player.hp == env.data.config.starting_hp
    assert env.match.round_id.stage == 1
    assert env.player.all_units == []


def test_the_same_seed_replays_the_same_episode(data):
    def run(seed):
        env = TFTEnv(data=data, seed=seed)
        return rollout(env, seed=seed)

    assert run(17) == run(17)


def test_random_rollouts_terminate(data):
    env = TFTEnv(data=data)
    for seed in range(4):
        result = rollout(env, seed=seed)
        assert result["placement"] in range(1, 9)
        assert result["steps"] > 0


def test_episode_ends_when_the_agent_is_eliminated(data):
    env = TFTEnv(data=data)
    env.reset(seed=2)
    env.player.hp = 1
    terminated = False
    rng = random.Random(0)
    for _ in range(400):
        _, _, terminated, _, info = env.step(env.sample_legal_action(rng))
        if terminated:
            break
    assert terminated
    assert not env.player.alive or env.match.finished


def test_agent_seat_is_configurable(data):
    """Doc 03 sec 2.11: no seat is privileged."""
    for seat in (0, 3, 7):
        env = TFTEnv(data=data, agent_seat=seat)
        env.reset(seed=1)
        assert env.player.player_id == seat
        result = rollout(env, seed=1)
        assert result["placement"] in range(1, 9)


def test_invalid_agent_seat_is_rejected(data):
    with pytest.raises(ValueError, match="agent_seat"):
        TFTEnv(data=data, agent_seat=8)


def test_opponents_are_configurable(data):
    env = TFTEnv(data=data, opponent_factory=lambda seat: RandomPolicy(seed=seat))
    env.reset(seed=1)
    assert all(
        isinstance(p, RandomPolicy)
        for i, p in enumerate(env.match.policies)
        if i != env.agent_seat
    )


def test_step_before_reset_raises(data):
    env = TFTEnv(data=data)
    with pytest.raises(RuntimeError, match="reset"):
        env.step(0)


# --- reward (doc 03 sec 3.3) --------------------------------------------


def test_reward_is_sparse_and_terminal_by_default(data):
    env = TFTEnv(data=data)
    env.reset(seed=3)
    rng = random.Random(3)
    rewards = []
    terminated = False
    while not terminated:
        _, reward, terminated, _, _ = env.step(env.sample_legal_action(rng))
        rewards.append(reward)
    assert all(r == 0.0 for r in rewards[:-1]), "no shaping should leak in"
    assert rewards[-1] > 0.0


def test_terminal_reward_scales_with_placement(data):
    env = TFTEnv(data=data)
    env.reset(seed=1)
    for placement, expected in ((1, 1.0), (4, 0.625), (8, 0.125)):
        env.player.placement = placement
        assert env._terminal_reward() == pytest.approx(expected)


def test_shaping_rewards_board_strength(data):
    """The dominant shaping term must respond to what the agent controls."""
    env = TFTEnv(data=data, reward_shaping=True)
    env.reset(seed=1)
    empty = env._shaping_reward(hp_before=env.player.hp)

    player = env.player
    player.level = 4
    player.gold = 100
    for i, champion_id in enumerate(("TFT17_Jinx", "TFT17_Leona")):
        player.shop.slots = [champion_id] + [None] * 4
        env.match.pool.take(champion_id)
        env.step(0)
        space = env.action_space_helper
        env.step(space.select_offset + space.slot_for_bench(0))
        env.step(space.place_offset + i)
    stronger = env._shaping_reward(hp_before=env.player.hp)
    assert stronger > empty, "fielding units must increase the shaping reward"


def test_shaping_penalises_hp_loss(data):
    env = TFTEnv(data=data, reward_shaping=True)
    env.reset(seed=1)
    unhurt = env._shaping_reward(hp_before=env.player.hp)
    hurt = env._shaping_reward(hp_before=env.player.hp + 30)
    assert hurt < unhurt


def test_shaping_is_off_by_default(data):
    env = TFTEnv(data=data)
    env.reset(seed=1)
    assert env._advance_round.__self__ is env
    assert not env.reward_shaping


def test_shaping_is_small_relative_to_the_terminal_reward(data):
    env = TFTEnv(data=data, reward_shaping=True)
    env.reset(seed=3)
    rng = random.Random(3)
    intermediate = []
    terminated = False
    while not terminated:
        _, reward, terminated, _, _ = env.step(env.sample_legal_action(rng))
        if not terminated:
            intermediate.append(reward)
    assert any(r != 0.0 for r in intermediate), "shaping should be active"
    assert all(abs(r) <= 0.05 for r in intermediate)


# --- rendering -----------------------------------------------------------


def test_render_returns_none_without_a_render_mode(env):
    env.reset(seed=1)
    assert env.render() is None


def test_ansi_render_describes_the_seat(data):
    env = TFTEnv(data=data, render_mode="ansi")
    env.reset(seed=1)
    text = env.render()
    assert "seat 0" in text and "board:" in text and "shop:" in text


# --- gymnasium conformance ----------------------------------------------


def test_passes_the_gymnasium_api_checker(data):
    from gymnasium.utils.env_checker import check_env

    env = TFTEnv(data=data, seed=1)
    check_env(env, skip_render_check=True)
