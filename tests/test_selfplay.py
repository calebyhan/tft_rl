"""Self-play and scouting tests (milestone 9, doc 03 sec 3.1 / 3.4)."""

from __future__ import annotations

import random

import numpy as np
import pytest

from engine.loader import load_all
from engine.match import PlanningContext
from rl.env import TFTEnv
from rl.observation import SCOUTING_MODES, ObservationEncoder
from rl.opponents import GreedyPolicy
from rl.selfplay import SnapshotPolicy, SnapshotPool, snapshot_factory
from tests.paths import REAL_DATA_DIR


@pytest.fixture(scope="module")
def data():
    return load_all(REAL_DATA_DIR)


class _FixedModel:
    """A stand-in for a trained model: always picks the first legal action.

    Using this instead of a real ``MaskablePPO`` keeps these tests fast and
    torch-free; the SB3 integration is exercised by the training smoke test.
    """

    def __init__(self, prefer: int | None = None) -> None:
        self.prefer = prefer
        self.calls = 0

    def predict(self, obs, action_masks=None, deterministic=True):
        self.calls += 1
        legal = np.flatnonzero(action_masks)
        if self.prefer is not None and action_masks[self.prefer]:
            return self.prefer, None
        return int(legal[0]), None


# --- scouting ------------------------------------------------------------


@pytest.mark.parametrize("mode", SCOUTING_MODES)
def test_scouting_modes_encode_without_error(data, mode):
    env = TFTEnv(data=data, scouting=mode, seed=0)
    obs, _ = env.reset(seed=0)
    assert obs.shape == (env.encoder.size,)
    assert np.isfinite(obs).all()


def test_full_scouting_is_wider_than_summary(data):
    summary = ObservationEncoder(data, 28, 7, scouting="summary")
    full = ObservationEncoder(data, 28, 7, scouting="full")
    assert full.size > summary.size
    # Exactly the scouting block per opponent, and nothing else moved.
    from rl.observation import SCOUT_FEATURES

    assert full.size - summary.size == 7 * (SCOUT_FEATURES + len(data.traits))


def test_invalid_scouting_mode_is_rejected(data):
    with pytest.raises(ValueError, match="scouting must be one of"):
        ObservationEncoder(data, 28, 7, scouting="telepathy")


def test_scouting_block_is_zero_when_opponents_have_no_board(data):
    """An empty opponent board must not leak nonzero features."""
    env = TFTEnv(data=data, scouting="full", seed=0)
    env.reset(seed=0)
    for opponent in env.match.players:
        opponent.board.clear()
    obs = env._observe()
    start = env.encoder.spec.offset_of("opponents")
    block = obs[start:]
    width = env.encoder.spec.opponent_width
    from rl.observation import OPPONENT_FEATURES, SCOUT_FEATURES

    for i in range(7):
        scout = block[i * width + OPPONENT_FEATURES : (i + 1) * width]
        # Only the "at unit cap" flag may be set with an empty board -- at
        # level 1 with 0 units fielded, it is not.
        assert scout[:SCOUT_FEATURES - 1].sum() == 0
        assert scout[SCOUT_FEATURES:].sum() == 0


def test_scouting_reflects_a_stronger_opponent_board(data):
    env = TFTEnv(data=data, scouting="full", seed=0)
    env.reset(seed=0)
    from engine.unit import UnitInstance

    opponent = env.match.players[1]
    opponent.board.clear()
    champion = max(data.champions.values(), key=lambda c: c.cost)
    unit = UnitInstance(champion, 3, registry=env.registry)
    opponent.board[opponent.free_board_hexes[0]] = unit

    obs = env._observe()
    start = env.encoder.spec.offset_of("opponents")
    width = env.encoder.spec.opponent_width
    from rl.observation import OPPONENT_FEATURES

    # players[1] is the first opponent, since the agent holds seat 0.
    scout = obs[start + OPPONENT_FEATURES : start + width]
    assert scout[0] > 0  # board size
    assert scout[1] > 0  # board value
    assert scout[2] == pytest.approx(1.0)  # best star level is 3


# --- snapshot pool -------------------------------------------------------


def test_pool_starts_empty_and_samples_none():
    pool = SnapshotPool()
    assert len(pool) == 0
    assert pool.sample(random.Random(0)) is None


def test_pool_evicts_oldest_at_capacity():
    pool = SnapshotPool(capacity=2)
    for i in range(4):
        pool.add(i)
    assert pool.snapshots == [2, 3]


def test_pool_rejects_zero_capacity():
    with pytest.raises(ValueError, match="capacity"):
        SnapshotPool(capacity=0)


def test_pool_sampling_is_deterministic_given_a_seed():
    pool = SnapshotPool(capacity=5)
    for i in range(5):
        pool.add(i)
    a = [pool.sample(random.Random(7)) for _ in range(3)]
    b = [pool.sample(random.Random(7)) for _ in range(3)]
    assert a == b


# --- snapshot seats ------------------------------------------------------


def test_snapshot_policy_plays_a_planning_phase(data):
    env = TFTEnv(data=data, seed=0)
    env.reset(seed=0)
    model = _FixedModel()
    policy = SnapshotPolicy(model, data, env._board_hexes)
    player = env.match.players[1]
    ctx = PlanningContext(
        env.match, env.match.round_id, env.match.pool, env.match.rng, False
    )
    policy.plan(player, ctx)
    assert model.calls > 0


def test_snapshot_policy_stops_on_an_illegal_action(data, caplog):
    """A stale snapshot must end its turn loudly, not silently retry."""
    env = TFTEnv(data=data, seed=0)
    env.reset(seed=0)

    class Rogue:
        def predict(self, obs, action_masks=None, deterministic=True):
            # SELECT on an empty slot: never legal on an empty board.
            return env.action_space_helper.select_offset, None

    policy = SnapshotPolicy(Rogue(), data, env._board_hexes)
    player = env.match.players[1]
    player.board.clear()
    player.bench = [None] * data.config.bench_size
    ctx = PlanningContext(
        env.match, env.match.round_id, env.match.pool, env.match.rng, False
    )
    with caplog.at_level("WARNING"):
        policy.plan(player, ctx)
    assert "illegal action" in caplog.text


def test_snapshot_policy_respects_the_action_budget(data):
    """A model that never ends planning must still stop at the budget."""
    env = TFTEnv(data=data, seed=0)
    env.reset(seed=0)

    class Dawdler:
        def __init__(self):
            self.calls = 0

        def predict(self, obs, action_masks=None, deterministic=True):
            self.calls += 1
            # REROLL when affordable, else the first legal action that is not
            # END_PLANNING.
            space = env.action_space_helper
            if action_masks[space.reroll_index]:
                return space.reroll_index, None
            legal = [i for i in np.flatnonzero(action_masks) if i != space.end_index]
            return int(legal[0]) if legal else space.end_index, None

    model = Dawdler()
    policy = SnapshotPolicy(model, data, env._board_hexes, max_actions_per_round=5)
    ctx = PlanningContext(
        env.match, env.match.round_id, env.match.pool, env.match.rng, False
    )
    policy.plan(env.match.players[1], ctx)
    assert model.calls <= 5


def test_snapshot_seat_does_not_defer_augment_picks(data):
    """Unlike the RL seat, a snapshot resolves within one planning phase."""
    policy = SnapshotPolicy(_FixedModel(), data, tuple())
    assert policy.defers_augment_pick is False


# --- the factory ---------------------------------------------------------


def test_factory_falls_back_to_scripted_while_the_pool_is_empty(data):
    env = TFTEnv(data=data, seed=0)
    factory = snapshot_factory(SnapshotPool(), env)
    assert all(isinstance(factory(seat), GreedyPolicy) for seat in range(7))


def test_factory_uses_snapshots_once_the_pool_is_filled(data):
    env = TFTEnv(data=data, seed=0)
    pool = SnapshotPool()
    pool.add(_FixedModel())
    factory = snapshot_factory(pool, env, mix=1.0, seed=0)
    assert all(isinstance(factory(seat), SnapshotPolicy) for seat in range(7))


def test_mix_zero_keeps_every_seat_scripted(data):
    env = TFTEnv(data=data, seed=0)
    pool = SnapshotPool()
    pool.add(_FixedModel())
    factory = snapshot_factory(pool, env, mix=0.0, seed=0)
    assert all(isinstance(factory(seat), GreedyPolicy) for seat in range(7))


def test_mix_out_of_range_is_rejected(data):
    env = TFTEnv(data=data, seed=0)
    with pytest.raises(ValueError, match="mix must be"):
        snapshot_factory(SnapshotPool(), env, mix=1.5)


def test_snapshot_seats_inherit_the_learners_observation_layout(data):
    """A mismatched layout would surface as an opaque torch shape error."""
    env = TFTEnv(data=data, scouting="full", champion_encoding="features", seed=0)
    pool = SnapshotPool()
    pool.add(_FixedModel())
    seat = snapshot_factory(pool, env, seed=0)(1)
    assert seat.encoder.size == env.encoder.size
    assert seat.space.n == env.action_space_helper.n


def test_a_full_self_play_game_completes(data):
    """The end-to-end check: 8 seats, all model-driven, plays to a placement."""
    env = TFTEnv(data=data, seed=0)
    pool = SnapshotPool()
    pool.add(_FixedModel())
    env.opponent_factory = snapshot_factory(pool, env, seed=0)

    obs, _ = env.reset(seed=0)
    terminated = False
    steps = 0
    while not terminated:
        action = env.sample_legal_action(random.Random(steps))
        obs, _, terminated, _, info = env.step(action)
        steps += 1
        assert steps < 5000
    assert info["placement"] is not None


# --- observation layout must match the learner's (doc 99 entry 48) --------


def test_layout_options_covers_every_encoder_option():
    """`LAYOUT_OPTIONS` must list every layout-affecting encoder keyword.

    Introspects `ObservationEncoder.__init__` rather than restating the list,
    so adding an option without adding it here fails immediately. The bug this
    guards is not hypothetical: `copy_counts` was added to the encoder and not
    to `snapshot_factory`, and every self-play run after that died mid-training
    on a 381-vs-418 shape error.
    """
    import inspect

    from rl.observation import LAYOUT_OPTIONS, ObservationEncoder

    signature = inspect.signature(ObservationEncoder.__init__)
    structural = {"self", "data", "board_slots", "n_opponents"}
    options = {
        name for name, param in signature.parameters.items()
        if name not in structural and param.default is not inspect.Parameter.empty
    }
    assert options == set(LAYOUT_OPTIONS), (
        f"encoder options {options} but LAYOUT_OPTIONS is {set(LAYOUT_OPTIONS)}; "
        "a layout option is missing and self-play seats will mis-encode"
    )


@pytest.mark.parametrize(
    "env_kwargs",
    [
        {},
        {"copy_counts": True},
        {"scouting": "full"},
        {"copy_counts": True, "scouting": "full"},
    ],
)
def test_snapshot_seat_matches_the_learner_observation_width(data, env_kwargs):
    """A snapshot seat must encode exactly what the learner's policy expects."""
    from rl.env import TFTEnv
    from rl.selfplay import SnapshotPolicy

    env = TFTEnv(data=data, **env_kwargs)
    seat = SnapshotPolicy(
        model=None,
        data=env.data,
        board_hexes=env._board_hexes,
        n_opponents=env.n_players - 1,
        **env.encoder.layout_settings(),
    )
    assert seat.encoder.size == env.encoder.size


def test_snapshot_factory_propagates_copy_counts(data):
    """The exact regression: the factory must carry the full layout across."""
    from rl.env import TFTEnv
    from rl.selfplay import SnapshotPool, snapshot_factory

    env = TFTEnv(data=data, copy_counts=True)
    pool = SnapshotPool()
    pool.add(object())  # a stand-in model; only the encoder is exercised here
    seat = snapshot_factory(pool, env, seed=1)(seat=0)
    assert seat.encoder.size == env.encoder.size
    assert seat.encoder.copy_counts is True


def test_snapshot_factory_fills_every_seat_at_full_mix(data):
    """`mix=1.0` must put a trained policy in *every* opponent seat.

    `scripts/teacher_check.py` reads the teacher's strength against a field of
    trained clones (doc 99 entry 56). If the factory silently fell back to
    `GreedyPolicy` -- which it does whenever the pool is empty -- that arm would
    measure the bots while being labelled "clones", and 56's conclusion would
    invert.
    """
    from rl.env import TFTEnv
    from rl.opponents import GreedyPolicy
    from rl.selfplay import SnapshotPolicy, SnapshotPool, snapshot_factory

    env = TFTEnv(data=data, copy_counts=True)
    pool = SnapshotPool(capacity=1)
    pool.add(object())  # stand-in model; only seat construction is exercised
    factory = snapshot_factory(pool, env, mix=1.0, seed=3)
    seats = [factory(i) for i in range(env.n_players - 1)]
    assert all(isinstance(s, SnapshotPolicy) for s in seats), (
        f"mix=1.0 left {sum(not isinstance(s, SnapshotPolicy) for s in seats)} "
        "seats on the scripted bot"
    )

    # And the documented fallback still holds when there is nothing to sample.
    empty = snapshot_factory(SnapshotPool(capacity=1), env, mix=1.0, seed=3)
    assert isinstance(empty(0), GreedyPolicy)
