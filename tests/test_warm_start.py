"""Behaviour-cloning warm start: value targets and expert data (doc 99 entry 18).

The value-regression half of the warm start is what stops PPO degrading its own
cloned policy, and its correctness rests entirely on the return targets being
right. A subtly wrong return -- discounted from the wrong end, or bled across an
episode boundary -- would still produce a falling loss curve while teaching the
critic nonsense, so these are asserted directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.train_ppo import (  # noqa: E402
    ENV_DEFAULTS,
    collect_expert_data,
    discounted_returns,
)

# --- return computation --------------------------------------------------


def test_terminal_return_is_the_terminal_reward():
    assert discounted_returns([0.0, 0.0, 5.0], 0.9)[-1] == pytest.approx(5.0)


def test_returns_discount_backwards_from_the_terminal():
    returns = discounted_returns([1.0, 2.0, 3.0], 0.5)
    assert returns[2] == pytest.approx(3.0)
    assert returns[1] == pytest.approx(2.0 + 0.5 * 3.0)
    assert returns[0] == pytest.approx(1.0 + 0.5 * (2.0 + 0.5 * 3.0))


def test_undiscounted_returns_are_suffix_sums():
    assert discounted_returns([1.0, 2.0, 3.0], 1.0) == pytest.approx([6.0, 5.0, 3.0])


def test_empty_episode_yields_no_returns():
    assert discounted_returns([], 0.99) == []


def test_gamma_zero_is_myopic():
    assert discounted_returns([1.0, 2.0, 3.0], 0.0) == pytest.approx([1.0, 2.0, 3.0])


# --- expert collection ---------------------------------------------------


@pytest.fixture(scope="module")
def expert(data_module):
    return collect_expert_data(data_module, episodes=2, gamma=0.9)


@pytest.fixture(scope="module")
def data_module():
    from engine.loader import load_all
    from tests.paths import REAL_DATA_DIR

    return load_all(REAL_DATA_DIR)


def test_expert_arrays_are_aligned(expert):
    obs, masks, actions, returns = expert
    assert len(obs) == len(masks) == len(actions) == len(returns)
    assert len(obs) > 0


def test_expert_returns_are_finite(expert):
    _, _, _, returns = expert
    assert np.isfinite(returns).all()


def test_expert_actions_are_legal_under_their_own_mask(expert):
    """A cloned action the mask forbids would teach the policy an illegal move."""
    _, masks, actions, _ = expert
    assert all(masks[i][actions[i]] for i in range(len(actions)))


def test_returns_do_not_bleed_across_episodes(data_module):
    """Two episodes must not share credit.

    Collected one at a time and then together: the concatenation of the
    separate runs must equal the combined run, which can only hold if each
    episode's returns are computed in isolation.
    """
    combined = collect_expert_data(data_module, episodes=2, gamma=0.9)[3]
    first = collect_expert_data(data_module, episodes=1, gamma=0.9)[3]
    assert combined[: len(first)] == pytest.approx(first)


def test_env_defaults_reach_expert_collection(data_module):
    """A layout mismatch here surfaces as an opaque torch shape error later."""
    ENV_DEFAULTS["scouting"] = "full"
    try:
        obs = collect_expert_data(data_module, episodes=1, gamma=0.9)[0]
        summary_width = collect_expert_data.__globals__["build_env"](
            data_module, scouting="summary"
        ).encoder.size
        assert obs.shape[1] > summary_width
    finally:
        ENV_DEFAULTS.pop("scouting", None)


def test_shaping_changes_the_value_targets(data_module):
    """Returns must describe the reward PPO will actually see."""
    plain = collect_expert_data(data_module, episodes=1, gamma=0.9, reward_shaping=False)[3]
    shaped = collect_expert_data(data_module, episodes=1, gamma=0.9, reward_shaping=True)[3]
    assert not np.allclose(plain, shaped)


# --- DAgger aggregation --------------------------------------------------
#
# The whole method rests on one asymmetry: the *actor* drives the episode, the
# *expert* labels it. Get that backwards and the run still trains, still shows
# a falling loss, and quietly learns to imitate the student -- so it is
# asserted directly rather than trusted.


def _end_planning_actor():
    """An actor that always ends the planning phase -- deliberately not expert."""

    def act(obs, mask):
        return int(np.flatnonzero(mask)[-1])

    return act


def test_dagger_labels_come_from_the_expert_not_the_actor(data_module):
    """Recorded actions must be the expert's, even though the actor moved."""
    actor = _end_planning_actor()
    _, masks, actions, _ = collect_expert_data(
        data_module, episodes=2, gamma=0.9, actor=actor
    )
    taken = [int(np.flatnonzero(m)[-1]) for m in masks]
    assert any(a != t for a, t in zip(actions, taken, strict=True)), (
        "every label equalled the actor's own move -- the expert is not labelling"
    )


def test_dagger_labels_stay_legal_under_the_state_they_describe(data_module):
    """The label must describe the state as seen, not the post-step state."""
    _, masks, actions, _ = collect_expert_data(
        data_module, episodes=2, gamma=0.9, actor=_end_planning_actor()
    )
    assert all(masks[i][actions[i]] for i in range(len(actions)))


def test_the_actor_changes_which_states_are_visited(data_module):
    """DAgger's entire point: a different actor induces a different distribution."""
    expert_obs = collect_expert_data(data_module, episodes=2, gamma=0.9)[0]
    student_obs = collect_expert_data(
        data_module, episodes=2, gamma=0.9, actor=_end_planning_actor()
    )[0]
    assert expert_obs.shape[0] != student_obs.shape[0] or not np.allclose(
        expert_obs, student_obs
    )


def test_seed_offset_draws_different_episodes(data_module):
    """Each DAgger round must see fresh games, not re-label the same ones."""
    first = collect_expert_data(data_module, episodes=1, gamma=0.9, seed_offset=10_000)[0]
    same = collect_expert_data(data_module, episodes=1, gamma=0.9, seed_offset=10_000)[0]
    other = collect_expert_data(data_module, episodes=1, gamma=0.9, seed_offset=77_000)[0]
    assert np.allclose(first, same), "same offset must reproduce the same episode"
    assert first.shape[0] != other.shape[0] or not np.allclose(first, other)


# --- per-kind match diagnostic -------------------------------------------


def test_match_by_kind_buckets_by_the_experts_choice(data_module):
    """A model that echoes the expert must score 100% in every bucket.

    The diagnostic drives doc 99 entry 25's conclusion, so its bookkeeping is
    asserted rather than eyeballed: bucketing by the *prediction* instead of by
    the expert's label would silently rewrite which decision looks broken.
    """
    from scripts.action_match import match_by_kind

    class PerfectModel:
        def predict(self, obs, action_masks=None, deterministic=True):
            expert = match_by_kind.__globals__["collect_expert_data"](
                data_module, 1, seed_offset=90_000
            )[2]
            return expert, None

    table = match_by_kind(PerfectModel(), data_module, episodes=1, on_student_states=False)
    assert table, "no actions were bucketed"
    assert all(rate == 1.0 for _, _, rate in table.values())
    assert sum(n for _, n, _ in table.values()) > 0


def test_match_by_kind_scores_zero_for_a_model_that_never_agrees(data_module):
    from scripts.action_match import match_by_kind

    class WrongModel:
        def predict(self, obs, action_masks=None, deterministic=True):
            return np.full(len(obs), -1), None

    table = match_by_kind(WrongModel(), data_module, episodes=1, on_student_states=False)
    assert all(rate == 0.0 for _, _, rate in table.values())
