"""Champion encoding in the observation vector (doc 99 entry 6b.5).

The ``features`` encoding exists because the original ``index`` encoding put
champion identity into a single normalised float, which asserts that champion
*n* resembles champion *n+1*. These tests pin the properties that motivated
the change -- most importantly that identity is *not* recoverable and that
trait membership *is*.
"""

from __future__ import annotations

import numpy as np
import pytest

from engine.loader import load_all
from engine.schema import ROLES
from engine.unit import UnitInstance
from rl.observation import (
    SHOP_DERIVED_FEATURES,
    UNIT_RANK_FEATURES,
    UNIT_ROLE_FEATURES,
    UNIT_SCALAR_FEATURES,
    UNIT_STAT_FEATURES,
    ObservationEncoder,
)
from tests.paths import REAL_DATA_DIR, STARTER_DATA_DIR


@pytest.fixture(scope="module")
def data():
    return load_all(STARTER_DATA_DIR)


def make_encoder(data, encoding="features", board_slots=4, n_opponents=2):
    return ObservationEncoder(data, board_slots, n_opponents, champion_encoding=encoding)


@pytest.fixture(scope="module")
def real_data():
    """The derived shop features need trait *variety* to be tested honestly.

    On the 13-champion starter fixture every champion shares a trait with the
    two owned ones, so the disjoint-traits case cannot be constructed and the
    synergy test silently skipped -- which is exactly the test that pins the
    feature's meaning.
    """
    return load_all(REAL_DATA_DIR)


@pytest.fixture
def populated_player(real_data):
    """A player holding two units, plus the extra args ``encode`` needs."""
    from engine.economy import RoundId
    from engine.items import ItemRegistry
    from engine.player import PlayerState

    registry = ItemRegistry(real_data.items, real_data.config.max_items_per_unit)
    player = PlayerState(real_data, registry, player_id=0)
    hexes = sorted(player.hex_board.hexes)
    own_hexes = [h for h in hexes if h in player._own_hexes]
    for champion_id, hex_ in zip(sorted(real_data.champions)[:2], own_hexes, strict=False):
        player.board[hex_] = UnitInstance(real_data.champions[champion_id], 1)
    context = (RoundId(2, 1), [], tuple(hexes))
    return player, context


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------


@pytest.mark.parametrize("encoding", ["features", "index"])
def test_spec_size_matches_what_encode_writes(data, encoding):
    """encode() asserts on this internally; make it an explicit contract too."""
    encoder = make_encoder(data, encoding)
    assert encoder.spec.size == sum(w for _, w in encoder.spec.describe())


def test_unknown_encoding_is_rejected(data):
    with pytest.raises(ValueError, match="champion_encoding"):
        make_encoder(data, "one_hot")


def test_feature_encoding_is_wider_than_index_encoding(data):
    """Its whole cost is size; if that ever inverts, something is wrong."""
    assert make_encoder(data, "features").size > make_encoder(data, "index").size


def test_unit_width_accounts_for_every_feature_group(data):
    encoder = make_encoder(data, "features")
    assert encoder.spec.unit_width == (
        UNIT_SCALAR_FEATURES
        + UNIT_ROLE_FEATURES
        + UNIT_STAT_FEATURES
        + len(data.traits)
        + UNIT_RANK_FEATURES
    )
    # Shop slots reuse the unit layout, minus the rank tail -- a shop unit is
    # not owned, so it has no rank among owned units -- plus the derived
    # (owned, synergy) pair. Doc 99 entries 29 and 30.
    assert encoder.spec.shop_width == (
        encoder.spec.unit_width - UNIT_RANK_FEATURES + SHOP_DERIVED_FEATURES
    )


# --------------------------------------------------------------------------
# What a unit slot actually encodes
# --------------------------------------------------------------------------


def _unit_block(encoder, champion, star_level=1, item_count=0):
    out = np.zeros(encoder.spec.size, dtype=np.float32)
    encoder._write_champion_features(
        out, 0, champion, star_level=star_level, item_count=item_count
    )
    return out[: encoder.spec.unit_width]


def test_role_is_one_hot(data):
    encoder = make_encoder(data, "features")
    champion = next(iter(data.champions.values()))
    block = _unit_block(encoder, champion)
    roles = block[UNIT_SCALAR_FEATURES : UNIT_SCALAR_FEATURES + UNIT_ROLE_FEATURES]
    assert roles.sum() == 1.0
    assert roles[sorted(ROLES).index(champion.role)] == 1.0


def test_traits_are_multi_hot_and_identify_the_synergies(data):
    """The signal the index encoding could not express at all."""
    encoder = make_encoder(data, "features")
    champion = next(c for c in data.champions.values() if len(c.traits) >= 2)
    block = _unit_block(encoder, champion)
    # The rank tail now sits after the traits, so slice rather than take the end.
    trait_start = UNIT_SCALAR_FEATURES + UNIT_ROLE_FEATURES + UNIT_STAT_FEATURES
    trait_block = block[trait_start : trait_start + len(data.traits)]
    expected = {encoder.trait_ids.index(t) for t in champion.traits}
    assert {int(i) for i in np.flatnonzero(trait_block)} == expected
    assert trait_block.sum() == len(champion.traits)


def test_star_level_scales_the_stat_features(data):
    """A 2-star unit should read as the stronger thing it is."""
    encoder = make_encoder(data, "features")
    champion = next(iter(data.champions.values()))
    health_at = UNIT_SCALAR_FEATURES + UNIT_ROLE_FEATURES
    star_at = 1  # scalar block is (cost, star, item_count)
    one = _unit_block(encoder, champion, star_level=1)
    two = _unit_block(encoder, champion, star_level=2)
    assert two[health_at] > one[health_at], "health should scale with star level"
    assert two[star_at] > one[star_at], "star level itself should be visible"


def test_every_feature_stays_within_the_observation_box(data):
    """The Box is [-1, 1]; a stat over its normaliser would silently clip."""
    encoder = make_encoder(data, "features")
    for champion in data.champions.values():
        for star in (1, 2, 3):
            block = _unit_block(encoder, champion, star_level=star, item_count=3)
            assert np.all(block >= -1.0) and np.all(block <= 1.0), champion.id


def test_identity_is_not_recoverable_from_the_encoding(data):
    """The point of the change: no feature encodes 'which champion' as an ordinal.

    Two champions sharing role, cost, stats and traits must be
    indistinguishable -- that is generalisation, not information loss.
    """
    encoder = make_encoder(data, "features")
    champions = list(data.champions.values())
    blocks = {c.id: _unit_block(encoder, c) for c in champions}
    for champion in champions:
        twin = next(
            (
                other
                for other in champions
                if other.id != champion.id
                and other.role == champion.role
                and other.cost == champion.cost
                and set(other.traits) == set(champion.traits)
                and other.stats.health_at(1) == champion.stats.health_at(1)
                and other.stats.attack_damage_at(1) == champion.stats.attack_damage_at(1)
                and other.stats.attack_range == champion.stats.attack_range
                and other.stats.attack_speed == champion.stats.attack_speed
            ),
            None,
        )
        if twin is not None:
            assert np.array_equal(blocks[champion.id], blocks[twin.id])


def test_index_encoding_still_encodes_an_ordinal(data):
    """Guards the legacy path so the A/B comparison stays honest."""
    encoder = make_encoder(data, "index")
    out = np.zeros(encoder.spec.size, dtype=np.float32)
    first, last = encoder.champion_ids[0], encoder.champion_ids[-1]
    encoder._write_unit(out, 0, UnitInstance(data.champions[first], 1))
    low = out[0]
    out[:] = 0
    encoder._write_unit(out, 0, UnitInstance(data.champions[last], 1))
    assert out[0] > low


# --------------------------------------------------------------------------
# Derived shop features (doc 99 entry 29)
# --------------------------------------------------------------------------
#
# `owned` and `synergy` are the two quantities a 1281-parameter model needs to
# predict the scripted expert's BUY choice at 91.2%, and which the trained
# agent -- forced to derive them from the flat vector -- never learned (48%,
# unmoved by 3.75x data, DAgger, or the full trait multi-hot). They are
# relational: comparisons between a shop slot and the current roster. If either
# silently encoded a property of the champion alone, the fix would be inert and
# the placement numbers would be the only thing to notice.


def _shop_tail(encoder, player, slot, context):
    """The (owned, synergy) pair written for one shop slot."""
    obs = encoder.encode(player, *context)
    spec = encoder.spec
    start = spec.offset_of("shop") + slot * spec.shop_width
    return tuple(obs[start + spec.shop_width - SHOP_DERIVED_FEATURES : start + spec.shop_width])


@pytest.mark.parametrize("encoding", ["features", "index"])
def test_owned_flag_is_set_only_for_champions_the_player_holds(
    real_data, encoding, populated_player
):
    player, context = populated_player
    encoder = make_encoder(real_data, encoding, board_slots=len(player.hex_board.hexes))
    held = sorted({u.champion.id for u in player.all_units})
    assert held, "fixture must own at least one champion"

    stocked = held[0]
    other = next(c for c in sorted(real_data.champions) if c not in held)
    player.shop.slots[0] = stocked
    player.shop.slots[1] = other

    assert _shop_tail(encoder, player, 0, context)[0] == pytest.approx(1.0)
    assert _shop_tail(encoder, player, 1, context)[0] == pytest.approx(0.0)


@pytest.mark.parametrize("encoding", ["features", "index"])
def test_synergy_counts_owned_units_sharing_a_trait(real_data, encoding, populated_player):
    """Zero for a champion sharing no trait, positive for one that does."""
    player, context = populated_player
    encoder = make_encoder(real_data, encoding, board_slots=len(player.hex_board.hexes))
    owned_traits = {t for u in player.all_units for t in u.champion.traits}

    sharing = next(
        (c for c, d in sorted(real_data.champions.items()) if set(d.traits) & owned_traits),
        None,
    )
    disjoint = next(
        (c for c, d in sorted(real_data.champions.items()) if not set(d.traits) & owned_traits),
        None,
    )
    if sharing is None or disjoint is None:
        pytest.skip("fixture dataset cannot produce both cases")

    player.shop.slots[0] = sharing
    player.shop.slots[1] = disjoint
    assert _shop_tail(encoder, player, 0, context)[1] > 0.0
    assert _shop_tail(encoder, player, 1, context)[1] == pytest.approx(0.0)


@pytest.mark.parametrize("encoding", ["features", "index"])
def test_derived_features_are_zero_for_an_empty_shop_slot(
    real_data, encoding, populated_player
):
    player, context = populated_player
    encoder = make_encoder(real_data, encoding, board_slots=len(player.hex_board.hexes))
    player.shop.slots[0] = None
    assert _shop_tail(encoder, player, 0, context) == pytest.approx((0.0, 0.0))


@pytest.mark.parametrize("encoding", ["features", "index"])
def test_synergy_tracks_the_board_not_the_champion(real_data, encoding, populated_player):
    """The same champion must score differently as the roster changes.

    This is the property that makes the feature relational. A champion-only
    encoding of trait membership -- which `features` already had -- cannot
    express it, which is why that encoding did not move BUY.
    """
    player, context = populated_player
    encoder = make_encoder(real_data, encoding, board_slots=len(player.hex_board.hexes))
    owned_traits = {t for u in player.all_units for t in u.champion.traits}
    sharing = next(
        (c for c, d in sorted(real_data.champions.items()) if set(d.traits) & owned_traits),
        None,
    )
    if sharing is None:
        pytest.skip("fixture dataset has no trait overlap")

    player.shop.slots[0] = sharing
    before = _shop_tail(encoder, player, 0, context)[1]

    for unit in list(player.board.values()):
        hex_ = next(h for h, u in player.board.items() if u is unit)
        del player.board[hex_]
    player.bench[:] = [None] * len(player.bench)

    after = _shop_tail(encoder, player, 0, context)[1]
    assert before > 0.0
    assert after == pytest.approx(0.0)


# --------------------------------------------------------------------------
# Unit rank features (doc 99 entry 30)
# --------------------------------------------------------------------------
#
# SELECT is `max(bench, key=(star, cost))` -- fully determined by quantities
# the observation already encodes, yet the agent scores 21.9%. The missing
# piece is the *comparison*, not the data, so these expose an ordering.
#
# They are two independent ranks, never a composite. A single "strength" score
# would encode the expert's lexicographic (star, cost) preference -- its
# policy -- rather than a fact about the board.


def _unit_tail(encoder, player, context, slot_index, section="bench"):
    obs = encoder.encode(player, *context)
    spec = encoder.spec
    start = spec.offset_of(section) + slot_index * spec.unit_width
    tail = start + spec.unit_width - UNIT_RANK_FEATURES
    return tuple(obs[tail : tail + UNIT_RANK_FEATURES])


@pytest.mark.parametrize("encoding", ["features", "index"])
def test_star_rank_orders_units_by_star_level(real_data, encoding, populated_player):
    player, context = populated_player
    encoder = make_encoder(
        real_data, encoding, board_slots=len(player.hex_board.hexes)
    )
    champion = real_data.champions[sorted(real_data.champions)[0]]
    player.bench[0] = UnitInstance(champion, 1)
    player.bench[1] = UnitInstance(champion, 2)

    low = _unit_tail(encoder, player, context, 0)[0]
    high = _unit_tail(encoder, player, context, 1)[0]
    assert high > low


@pytest.mark.parametrize("encoding", ["features", "index"])
def test_rank_is_relative_to_the_roster_not_absolute(
    real_data, encoding, populated_player
):
    """The same unit must rank differently as the roster around it changes.

    Deliberately uses two *mid-priced* champions. An absolute rank over the
    cost scale would put them somewhere in the middle; a roster-relative rank
    puts the dearer at exactly 1.0 and the cheaper at exactly 0.0. Picking the
    global cheapest and dearest champions -- the obvious choice -- cannot tell
    the two schemes apart, and an earlier version of this test did not.
    """
    player, context = populated_player
    encoder = make_encoder(
        real_data, encoding, board_slots=len(player.hex_board.hexes)
    )
    costs = sorted({c.cost for c in real_data.champions.values()})
    assert len(costs) >= 4, "need a cost scale with interior values"
    lower, upper = costs[1], costs[2]
    cheap = next(c for c in real_data.champions.values() if c.cost == lower)
    dear = next(c for c in real_data.champions.values() if c.cost == upper)

    player.board.clear()
    player.bench[:] = [None] * len(player.bench)
    player.bench[0] = UnitInstance(dear, 1)
    player.bench[1] = UnitInstance(cheap, 1)

    assert _unit_tail(encoder, player, context, 0)[1] == pytest.approx(1.0)
    assert _unit_tail(encoder, player, context, 1)[1] == pytest.approx(0.0)

    # Swap the roster around the dear unit: now it is the *cheaper* of the two.
    dearer = next(c for c in real_data.champions.values() if c.cost == costs[-1])
    player.bench[1] = UnitInstance(dearer, 1)
    assert _unit_tail(encoder, player, context, 0)[1] == pytest.approx(0.0)
    assert _unit_tail(encoder, player, context, 1)[1] == pytest.approx(1.0)


@pytest.mark.parametrize("encoding", ["features", "index"])
def test_ranks_span_board_and_bench_together(real_data, encoding, populated_player):
    """The swap rule compares a benched unit against a fielded one.

    The *fielded* unit is the strong one here. Ranking over the bench alone
    would leave it at the default 0.0 and still satisfy a "bench beats board"
    assertion, so the comparison is deliberately the other way round.
    """
    player, context = populated_player
    encoder = make_encoder(
        real_data, encoding, board_slots=len(player.hex_board.hexes)
    )
    champion = real_data.champions[sorted(real_data.champions)[0]]
    player.board.clear()
    player.bench[:] = [None] * len(player.bench)

    own_hexes = [h for h in sorted(player.hex_board.hexes) if h in player._own_hexes]
    fielded_hex = own_hexes[0]
    player.board[fielded_hex] = UnitInstance(champion, 3)
    player.bench[0] = UnitInstance(champion, 1)

    board_index = sorted(player.hex_board.hexes).index(fielded_hex)
    board_star = _unit_tail(encoder, player, context, board_index, section="board")[0]
    bench_star = _unit_tail(encoder, player, context, 0)[0]
    assert board_star == pytest.approx(1.0), "a fielded unit must be ranked at all"
    assert bench_star == pytest.approx(0.0)


@pytest.mark.parametrize("encoding", ["features", "index"])
def test_empty_slots_carry_no_rank(real_data, encoding, populated_player):
    player, context = populated_player
    encoder = make_encoder(
        real_data, encoding, board_slots=len(player.hex_board.hexes)
    )
    player.bench[:] = [None] * len(player.bench)
    assert _unit_tail(encoder, player, context, 0) == pytest.approx((0.0, 0.0))


def test_board_full_flag_tracks_the_unit_cap(real_data, populated_player):
    """Switches the expert's placement rule between its two regimes."""
    from rl.observation import SELF_FEATURES

    player, context = populated_player
    encoder = make_encoder(
        real_data, "index", board_slots=len(player.hex_board.hexes)
    )
    champion = real_data.champions[sorted(real_data.champions)[0]]

    flag_at = SELF_FEATURES - 1
    # The fixture fields two units, and max_board_units at level 1 is smaller
    # than that -- start from an empty board so the flag has somewhere to go.
    player.board.clear()
    assert encoder.encode(player, *context)[flag_at] == pytest.approx(0.0)

    own_hexes = [h for h in sorted(player.hex_board.hexes) if h in player._own_hexes]
    for hex_ in own_hexes[: player.max_board_units]:
        player.board[hex_] = UnitInstance(champion, 1)
    assert len(player.board) >= player.max_board_units
    assert encoder.encode(player, *context)[flag_at] == pytest.approx(1.0)
