"""The shared-weight slot head (doc 99 entry 39).

The claim being tested is not "it runs" but "it is permutation-equivariant
across unit slots": one network scores every slot, so identical unit features
in different slots produce identical scores, and swapping two slots swaps their
logits. A head that merely *looked* shared while learning per-slot rows would
pass a smoke test and fail these.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.policy import make_slot_policy  # noqa: E402
from tests.paths import REAL_DATA_DIR  # noqa: E402


@pytest.fixture(scope="module")
def data():
    return load_all(REAL_DATA_DIR)


@pytest.fixture(scope="module")
def env(data):
    return TFTEnv(data=data, copy_counts=True)


@pytest.fixture
def head(env):
    """The head alone, without SB3 around it.

    Function-scoped on purpose: `_freeze_context` mutates it, and a shared
    instance let one test silently disable the context for the next.
    """
    from rl.policy import SlotScoringHead

    spec = env.encoder.spec
    space = env.action_space_helper
    return SlotScoringHead(
        obs_dim=env.encoder.size,
        n_actions=space.n,
        board_start=spec.offset_of("board"),
        unit_width=spec.unit_width,
        n_slots=space.unit_slots,
        board_slots=spec.board_slots,
        slot_rows=[0.0] * space.unit_slots,
        shop_start=spec.offset_of("shop"),
        shop_width=spec.shop_width,
        n_shop=spec.shop_slots,
        offsets={
            "buy": space.buy_offset,
            "sell": space.sell_offset,
            "select": space.select_offset,
            "place": space.place_offset,
            "equip": space.equip_offset,
        },
        item_bag_slots=space.item_bag_slots,
    )


class _ZeroContext(torch.nn.Module):
    """Freezes the global context so per-slot behaviour can be isolated.

    The context vector is a function of the *whole* observation, so moving a
    unit between slots changes it and the head is only equivariant with the
    context held fixed. That is the property worth pinning: the scoring
    function is shared across slots, not that the head ignores the board.
    """

    def __init__(self, dim: int):
        super().__init__()
        self.dim = dim

    def forward(self, obs):
        return torch.zeros(obs.shape[0], self.dim)


def _freeze_context(head):
    head.context_net = _ZeroContext(head.slot_net[0].in_features
                                    - head.unit_width - head.position.shape[1])
    return head


def _slot_block(env, obs, slot):
    spec = env.encoder.spec
    start = spec.offset_of("board") + slot * spec.unit_width
    return start, start + spec.unit_width


def test_identical_units_in_different_bench_slots_score_identically(env, head):
    """The core of weight sharing. A per-slot Linear could not do this."""
    obs = torch.zeros(1, env.encoder.size)
    spec = env.encoder.spec
    a, b = spec.board_slots, spec.board_slots + 1  # two bench slots

    block = torch.rand(spec.unit_width)
    for slot in (a, b):
        lo, hi = _slot_block(env, obs, slot)
        obs[0, lo:hi] = block

    with torch.no_grad():
        logits = head(obs)
    sell = env.action_space_helper.sell_offset
    assert float(logits[0, sell + a]) == pytest.approx(
        float(logits[0, sell + b]), abs=1e-5
    ), "the same unit must score the same in either bench slot"


def test_swapping_two_slots_swaps_their_logits(env, head):
    obs = torch.zeros(1, env.encoder.size)
    spec = env.encoder.spec
    a, b = spec.board_slots, spec.board_slots + 3

    first, second = torch.rand(spec.unit_width), torch.rand(spec.unit_width)
    lo_a, hi_a = _slot_block(env, obs, a)
    lo_b, hi_b = _slot_block(env, obs, b)

    _freeze_context(head)
    with torch.no_grad():
        obs[0, lo_a:hi_a], obs[0, lo_b:hi_b] = first, second
        before = head(obs)
        obs[0, lo_a:hi_a], obs[0, lo_b:hi_b] = second, first
        after = head(obs)

    select = env.action_space_helper.select_offset
    assert float(before[0, select + a]) == pytest.approx(
        float(after[0, select + b]), abs=1e-5
    )
    assert float(before[0, select + b]) == pytest.approx(
        float(after[0, select + a]), abs=1e-5
    )


def test_a_board_slot_and_a_bench_slot_can_differ(env, head):
    """Equivariance must not collapse into ignoring position.

    SELECT reads the strongest *bench* unit, so a head that could not
    distinguish board from bench would be unable to express the rule at all.
    """
    spec = env.encoder.spec
    obs = torch.zeros(1, env.encoder.size)
    block = torch.rand(spec.unit_width)
    board_slot, bench_slot = 0, spec.board_slots
    for slot in (board_slot, bench_slot):
        lo, hi = _slot_block(env, obs, slot)
        obs[0, lo:hi] = block

    with torch.no_grad():
        logits = head(obs)
    sell = env.action_space_helper.sell_offset
    assert float(logits[0, sell + board_slot]) != pytest.approx(
        float(logits[0, sell + bench_slot]), abs=1e-6
    ), "on_bench must reach the scorer"


def test_equip_logits_land_at_the_right_indices(env, head):
    """EQUIP is item * n_slots + slot; a transpose error would be invisible.

    Perturbing one slot must move exactly the strided set of EQUIP actions
    belonging to that slot, and no others.
    """
    spec = env.encoder.spec
    space = env.action_space_helper
    n_slots = space.unit_slots
    obs = torch.zeros(1, env.encoder.size)
    _freeze_context(head)
    with torch.no_grad():
        before = head(obs)
        slot = spec.board_slots + 2
        lo, hi = _slot_block(env, obs, slot)
        obs[0, lo:hi] = torch.rand(spec.unit_width) + 1.0
        after = head(obs)

    changed = {
        i
        for i in range(space.equip_offset, space.equip_offset + space.item_bag_slots * n_slots)
        if abs(float(before[0, i] - after[0, i])) > 1e-6
    }
    expected = {
        space.equip_offset + item * n_slots + slot
        for item in range(space.item_bag_slots)
    }
    assert changed == expected


def test_non_slot_actions_still_come_from_the_global_trunk(env, head):
    """REROLL/BUY_XP/END must respond to the observation as a whole."""
    space = env.action_space_helper
    obs = torch.zeros(1, env.encoder.size)
    with torch.no_grad():
        before = head(obs)
        obs[0, 0] = 1.0  # a self-scalar, far from any unit block
        after = head(obs)
    assert abs(float(before[0, space.reroll_index] - after[0, space.reroll_index])) > 1e-9


def test_the_policy_trains_and_the_shared_net_receives_gradient(env):
    """A head whose parameters never update would still predict legal actions."""
    from sb3_contrib import MaskablePPO

    model = MaskablePPO(
        make_slot_policy(env), env, device="cpu",
        n_steps=64, batch_size=32, seed=0, verbose=0,
    )
    model.learn(total_timesteps=128)
    grads = [
        p.grad
        for name, p in model.policy.action_net.named_parameters()
        if "slot_net" in name and p.grad is not None
    ]
    assert grads, "the shared slot network got no gradient at all"
    assert any(float(g.abs().sum()) > 0 for g in grads)


def test_slot_head_rejects_a_layout_it_cannot_score(data):
    """Silently scoring the wrong floats is the failure worth guarding."""
    env = TFTEnv(data=data)
    original = env.encoder.spec.bench_slots
    object.__setattr__(env.encoder.spec, "bench_slots", original + 1)
    try:
        with pytest.raises(ValueError, match="unit slots"):
            make_slot_policy(env)
    finally:
        object.__setattr__(env.encoder.spec, "bench_slots", original)


def test_a_saved_slot_policy_can_be_loaded_back(env, tmp_path):
    """The policy class is built inside a closure, so this is not free.

    SB3 pickles the class with cloudpickle, which captures it -- but a model
    that trains for an hour and then cannot be reloaded is a run thrown away,
    and nothing else in the suite would catch it.
    """
    from sb3_contrib import MaskablePPO

    model = MaskablePPO(
        make_slot_policy(env), env, device="cpu",
        n_steps=64, batch_size=32, seed=0, verbose=0,
    )
    path = tmp_path / "model"
    model.save(path)

    from rl.policy import SlotScoringHead

    reloaded = MaskablePPO.load(path, device="cpu")
    assert isinstance(reloaded.policy.action_net, SlotScoringHead)

    obs, _ = env.reset(seed=3)
    mask = env.action_mask()
    action, _ = reloaded.predict(obs, action_masks=mask, deterministic=True)
    assert bool(mask[int(action)]), "reloaded policy chose a masked action"


def test_the_global_context_reaches_the_slot_scorer(env, head):
    """The regression test for doc 99 entry 41.2.

    A scorer fed only its own slot cannot express PLACE (a function of the
    *held* unit's range and the target row) or SELECT's board-full regime.
    Built that way, the head cost 1.387 placement: PLACE match fell 68.8% ->
    44.0% and SELECT 66.7% -> 37.0%. Changing a part of the observation that
    is not any unit block must move the slot logits.
    """
    space = env.action_space_helper
    spec = env.encoder.spec
    obs = torch.zeros(1, env.encoder.size)
    slot = spec.board_slots

    with torch.no_grad():
        before = head(obs)
        # The selection block -- what unit is currently held -- lives outside
        # every unit block and is exactly what PLACE depends on.
        start = spec.offset_of("selection")
        obs[0, start : start + 4] = 1.0
        after = head(obs)

    for offset in (space.place_offset, space.select_offset):
        assert abs(float(before[0, offset + slot] - after[0, offset + slot])) > 1e-6, (
            "slot logits must respond to context outside the slot"
        )


def test_buy_logits_come_from_a_shared_shop_scorer(env, head):
    """BUY is an argmax over shop slots and was not covered by the first head.

    Probed at doc 99 entry 45: hand-computed (owned, synergy, cost) reads the
    teacher's rule at 92.3% against a 91.8% tie ceiling, a monolithic MLP over
    the real observation at 68.1%, and a shared-weight reader of the same
    floats at 84.4%.
    """
    space = env.action_space_helper
    spec = env.encoder.spec
    obs = torch.zeros(1, env.encoder.size)
    _freeze_context(head)

    a, b = 0, 2
    block = torch.rand(spec.shop_width)
    for slot in (a, b):
        start = spec.offset_of("shop") + slot * spec.shop_width
        obs[0, start : start + spec.shop_width] = block

    with torch.no_grad():
        logits = head(obs)
    assert float(logits[0, space.buy_offset + a]) == pytest.approx(
        float(logits[0, space.buy_offset + b]), abs=1e-5
    ), "the same shop unit must score the same in either shop slot"


def test_perturbing_a_shop_slot_moves_only_that_buy_logit(env, head):
    space = env.action_space_helper
    spec = env.encoder.spec
    obs = torch.zeros(1, env.encoder.size)
    _freeze_context(head)

    with torch.no_grad():
        before = head(obs)
        slot = 1
        start = spec.offset_of("shop") + slot * spec.shop_width
        obs[0, start : start + spec.shop_width] = torch.rand(spec.shop_width) + 1.0
        after = head(obs)

    changed = {
        i
        for i in range(space.buy_offset, space.buy_offset + spec.shop_slots)
        if abs(float(before[0, i] - after[0, i])) > 1e-6
    }
    assert changed == {space.buy_offset + slot}


def test_board_rows_reach_the_scorer(env):
    """PLACE is melee-to-the-front, ranged-to-the-back (doc 99 entry 45.5).

    The row is a real fact about a hex, unlike the raw slot index which only
    encodes the teacher's arbitrary tiebreak. Dropping both together cost 36
    points of PLACE match, so this pins that the row survives.
    """
    from rl.policy import make_slot_policy

    policy_cls = make_slot_policy(env)
    model = policy_cls(
        env.observation_space, env.action_space, lambda _: 3e-4
    )
    position = model.action_net.position
    board_slots = env.encoder.spec.board_slots

    rows = position[:board_slots, 1]
    assert float(rows.min()) == pytest.approx(0.0)
    assert float(rows.max()) == pytest.approx(1.0)
    assert len(set(float(r) for r in rows)) > 1, "every board slot got the same row"
    assert float(position[board_slots:, 1].abs().sum()) == 0.0, "bench has no row"
