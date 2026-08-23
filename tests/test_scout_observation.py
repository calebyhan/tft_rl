"""Contracts for the opponent-board token representation (doc 99 entry 160)."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import torch
from sb3_contrib import MaskablePPO

from engine.economy import RoundId
from engine.items import ItemRegistry
from engine.loader import load_all
from engine.player import PlayerState
from engine.unit import UnitInstance
from rl.env import TFTEnv
from rl.observation import ScoutedObservationEncoder
from rl.opponents import FAST8
from rl.scout_policy import ScoutSetExtractor
from rl.search import opponent_panel, search_buy_greedy_policy
from tests.paths import REAL_DATA_DIR


def _scout_state():
    data = load_all(REAL_DATA_DIR)
    registry = ItemRegistry(data.items, data.config.max_items_per_unit)
    player = PlayerState(data, registry, player_id=0)
    opponent_a = PlayerState(data, registry, player_id=1)
    opponent_b = PlayerState(data, registry, player_id=2)
    hexes = tuple(sorted(player._own_hexes))
    first, second = hexes[:2]

    milo = data.champions["TFT17_Milio"]
    jax = data.champions["TFT17_Jax"]
    item_a = data.items["TFT_Item_Spatula"]
    item_b = data.items["TFT17_Item_SummonTraitEmblemItem"]
    opponent_a.board[first] = UnitInstance(milo, 1, [item_a], registry=registry)
    opponent_a.board[second] = UnitInstance(jax, 1, [item_b], registry=registry)
    opponent_b.board[first] = UnitInstance(jax, 2, registry=registry)

    encoder = ScoutedObservationEncoder(data, len(hexes), 2)
    encoder.bind_board_hexes(hexes)
    return encoder, player, [opponent_a, opponent_b], hexes, first, second


def _encode(encoder, player, opponents, hexes):
    return encoder.encode(player, RoundId(2, 1), opponents, hexes)


def test_scout_tokens_record_position_items_and_identity_without_global_leak():
    encoder, player, opponents, hexes, first, second = _scout_state()
    opponent = opponents[0]
    baseline = _encode(encoder, player, opponents, hexes)

    opponent.board[first], opponent.board[second] = (
        opponent.board[second], opponent.board[first],
    )
    moved = _encode(encoder, player, opponents, hexes)
    assert np.array_equal(baseline["global"], moved["global"])
    assert not np.array_equal(baseline["opponent_units"], moved["opponent_units"])
    opponent.board[first], opponent.board[second] = (
        opponent.board[second], opponent.board[first],
    )

    first_unit, second_unit = opponent.board[first], opponent.board[second]
    first_unit._items, second_unit._items = second_unit._items, first_unit._items
    first_unit._invalidate()
    second_unit._invalidate()
    reitemed = _encode(encoder, player, opponents, hexes)
    assert np.array_equal(baseline["global"], reitemed["global"])
    assert not np.array_equal(baseline["opponent_units"], reitemed["opponent_units"])
    first_unit._items, second_unit._items = second_unit._items, first_unit._items
    first_unit._invalidate()
    second_unit._invalidate()

    original = first_unit.champion
    first_unit.champion = second_unit.champion
    first_unit._invalidate()
    reidentified = _encode(encoder, player, opponents, hexes)
    assert np.array_equal(baseline["global"], reidentified["global"])
    assert not np.array_equal(
        baseline["opponent_units"], reidentified["opponent_units"]
    )
    first_unit.champion = original
    first_unit._invalidate()

    opponent.augments.append(next(iter(encoder.data.augments.values())))
    reaugmented = _encode(encoder, player, opponents, hexes)
    assert np.array_equal(baseline["global"], reaugmented["global"])
    assert not np.array_equal(
        baseline["opponent_augments"], reaugmented["opponent_augments"]
    )


def test_opponent_panel_tie_break_is_stable_when_hidden_ids_swap():
    """The search panel must not introduce an absent player-id feature."""
    _encoder, player, opponents, hexes, _first, _second = _scout_state()
    left, right = opponents
    # Give the second board the same unit count without making the boards
    # identical: this exercises the deterministic tie-break rather than a
    # vacuous equality case.
    right.board[hexes[1]] = UnitInstance(
        left.board[hexes[0]].champion, 1, registry=player.registry
    )
    left.hp = right.hp = 100
    left.level = right.level = 3
    # Equal HP / board count makes this exercise the final deterministic rank.
    assert len(left.board) == len(right.board) == 2
    match = SimpleNamespace(players=[player, left, right])
    baseline = opponent_panel(match, player, 1)
    left.player_id, right.player_id = right.player_id, left.player_id
    try:
        assert opponent_panel(match, player, 1) == baseline
    finally:
        left.player_id, right.player_id = right.player_id, left.player_id


def test_scout_extractor_is_invariant_to_token_and_board_storage_order():
    encoder, player, opponents, hexes, _first, _second = _scout_state()
    observation = _encode(encoder, player, opponents, hexes)
    extractor = ScoutSetExtractor(encoder.observation_space)

    def tensorize(obs):
        return {name: torch.as_tensor(value).unsqueeze(0) for name, value in obs.items()}

    baseline = extractor(tensorize(observation))
    shuffled_units = {name: value.copy() for name, value in observation.items()}
    shuffled_units["opponent_units"] = shuffled_units["opponent_units"][:, ::-1].copy()
    assert torch.allclose(baseline, extractor(tensorize(shuffled_units)))

    shuffled_boards = {name: value.copy() for name, value in observation.items()}
    shuffled_boards["opponent_units"] = shuffled_boards["opponent_units"][::-1].copy()
    shuffled_boards["opponent_board"] = shuffled_boards["opponent_board"][::-1].copy()
    shuffled_boards["opponent_augments"] = shuffled_boards["opponent_augments"][::-1].copy()
    assert torch.allclose(baseline, extractor(tensorize(shuffled_boards)))


def test_token_env_declares_and_preserves_its_dict_space():
    env = TFTEnv(load_all(REAL_DATA_DIR), scouting="tokens")
    observation, _ = env.reset(seed=0)
    assert env.observation_space.contains(observation)
    action = env.sample_legal_action()
    next_observation, _reward, _terminated, _truncated, _info = env.step(action)
    assert env.observation_space.contains(next_observation)


def test_multiinput_policy_preserves_storage_permutation_invariance():
    env = TFTEnv(load_all(REAL_DATA_DIR), scouting="tokens")
    observation, _ = env.reset(seed=0)
    model = MaskablePPO(
        "MultiInputPolicy",
        env,
        n_steps=8,
        batch_size=8,
        device="cpu",
        policy_kwargs={"features_extractor_class": ScoutSetExtractor},
    )

    def logits(obs):
        tensor, _is_vectorized = model.policy.obs_to_tensor(obs)
        with torch.no_grad():
            features = model.policy.extract_features(tensor)
            latent, _value = model.policy.mlp_extractor(features)
            return model.policy.action_net(latent)

    baseline = logits(observation)
    permuted = {name: value.copy() for name, value in observation.items()}
    permuted["opponent_units"] = permuted["opponent_units"][:, ::-1].copy()
    permuted["opponent_board"] = permuted["opponent_board"][::-1].copy()
    permuted["opponent_units"] = permuted["opponent_units"][::-1].copy()
    permuted["opponent_augments"] = permuted["opponent_augments"][::-1].copy()
    assert torch.allclose(baseline, logits(permuted))


def test_search_buy_teacher_accepts_token_observations():
    env = TFTEnv(load_all(REAL_DATA_DIR), scouting="tokens")
    observation, _ = env.reset(seed=0)
    teacher = search_buy_greedy_policy(env, econ=FAST8)
    env.register_external_policy(teacher)
    action = teacher(observation, env.action_masks())
    assert env.action_masks()[action]
    assert teacher.last_search_buy_slot is None
