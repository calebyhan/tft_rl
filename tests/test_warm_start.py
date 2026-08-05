"""Behaviour-cloning warm start: value targets and expert data (doc 99 entry 18).

The value-regression half of the warm start is what stops PPO degrading its own
cloned policy, and its correctness rests entirely on the return targets being
right. A subtly wrong return -- discounted from the wrong end, or bled across an
episode boundary -- would still produce a falling loss curve while teaching the
critic nonsense, so these are asserted directly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rl.collect import discounted_returns  # noqa: E402
from scripts.train_ppo import (  # noqa: E402
    ARCHITECTURE_FLAGS,
    ENV_DEFAULTS,
    check_init_flags,
    collect_expert_data,
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


# --- the teacher's own configuration (doc 99 entry 37.4) -----------------
#
# Imitation caps at the teacher, so which teacher labels the dataset is part
# of the experiment rather than an implementation detail. Until 2026-08-03 it
# was hardcoded, and the teacher it hardcoded could not sell.


def test_expert_kwargs_reach_the_labelling_policy(data_module):
    """A teacher given the sell branch must actually label SELL actions."""
    from rl.action import ActionKind

    space = collect_expert_data.__globals__["build_env"](
        data_module
    ).action_space_helper

    def sells(expert_kwargs):
        actions = collect_expert_data(
            data_module, episodes=1, gamma=0.9, expert_kwargs=expert_kwargs
        )[2]
        return sum(space.decode(int(a)).kind is ActionKind.SELL for a in actions)

    assert sells(None) == 0, "the historical teacher never sold"
    assert sells({"sell_bench": True}) > 0, "expert_kwargs did not reach the policy"


def test_expert_kwargs_default_reproduces_the_historical_dataset(data_module):
    plain = collect_expert_data(data_module, episodes=1, gamma=0.9)[2]
    explicit = collect_expert_data(
        data_module,
        episodes=1,
        gamma=0.9,
        expert_kwargs={"sell_bench": False, "roll_at_level": 0},
    )[2]
    assert np.array_equal(plain, explicit)


def test_the_cli_help_renders(): 
    """`--help` crashed for months on an unescaped %% in --target-kl's help.

    argparse only formats help lazily, so nothing else exercises these strings.
    """
    import subprocess

    root = Path(__file__).resolve().parent.parent
    done = subprocess.run(
        [sys.executable, str(root / "scripts" / "train_ppo.py"), "--help"],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    assert "--expert-sell" in done.stdout


# --- --init-from architecture guard --------------------------------------


class _Args:
    """Just the architecture-affecting attributes `check_init_flags` reads."""

    def __init__(self, **kwargs):
        self.copy_counts = True
        self.champion_encoding = "index"
        self.scouting = "summary"
        self.slot_head = True
        for key, value in kwargs.items():
            setattr(self, key, value)


def _checkpoint(tmp_path: Path, **hyperparameters) -> Path:
    saved = {
        "copy_counts": True,
        "champion_encoding": "index",
        "scouting": "summary",
        "slot_head": True,
    }
    saved.update(hyperparameters)
    (tmp_path / "metadata.json").write_text(
        json.dumps({"hyperparameters": saved})
    )
    return tmp_path / "model.zip"


def test_matching_flags_pass(tmp_path):
    check_init_flags(_checkpoint(tmp_path), _Args())


@pytest.mark.parametrize(
    "flag,value",
    [
        ("copy_counts", False),
        ("slot_head", False),
        ("champion_encoding", "features"),
        ("scouting", "full"),
    ],
)
def test_each_architecture_flag_is_checked(tmp_path, flag, value):
    """Every flag in ARCHITECTURE_FLAGS must actually be compared.

    Parametrised per flag rather than asserted as a set: a guard that reads the
    list but compares only the first entry would pass a single-case test, and
    the failure mode -- PPO silently starting from a differently-shaped policy --
    is exactly the kind this project has already shipped three times.
    """
    checkpoint = _checkpoint(tmp_path, **{flag: value})
    with pytest.raises(SystemExit, match=flag):
        check_init_flags(checkpoint, _Args())


def test_every_architecture_flag_is_exercised_by_the_parametrisation():
    """Guards against a flag being added to the tuple but never tested."""
    covered = {"copy_counts", "slot_head", "champion_encoding", "scouting"}
    assert set(ARCHITECTURE_FLAGS) == covered


def test_missing_sidecar_warns_rather_than_crashing(tmp_path, capsys):
    check_init_flags(tmp_path / "model.zip", _Args())
    assert "cannot verify" in capsys.readouterr().out


# --- critic quality is reported out-of-sample (doc 99 entry 49.3) ---------


def _tiny_clone_inputs(data):
    """A model plus a small expert dataset, for exercising `fit_clone`."""
    from sb3_contrib import MaskablePPO

    from rl.env import TFTEnv

    env = TFTEnv(data=data)
    model = MaskablePPO("MlpPolicy", env, device="cpu", seed=0, n_steps=64)
    dataset = collect_expert_data(data, 2, expert_kwargs={"sell_bench": True})
    return model, dataset


def test_fit_clone_reports_holdout_explained_variance():
    """Both figures must be reported, and they must not be the same number.

    For a long time only the in-sample figure existed, and it read as evidence
    the critic was excellent: 0.968 against 0.262 on held-out states from the
    same teacher. A model fitted on one set and scored on a genuinely different
    one cannot produce identical variance explained.
    """
    from engine.loader import load_all
    from scripts.train_ppo import fit_clone
    from tests.paths import REAL_DATA_DIR

    data = load_all(REAL_DATA_DIR)
    model, dataset = _tiny_clone_inputs(data)
    observations, _, _, returns = dataset
    half = len(observations) // 2
    stats = fit_clone(
        model,
        (dataset[0][:half], dataset[1][:half], dataset[2][:half], dataset[3][:half]),
        epochs=2,
        holdout=(observations[half:], returns[half:]),
    )
    assert "explained_variance" in stats
    assert "explained_variance_holdout" in stats
    assert stats["explained_variance"] != stats["explained_variance_holdout"], (
        "in-sample and held-out explained variance are identical; the holdout "
        "is not actually being scored separately"
    )


def test_fit_clone_without_holdout_says_so():
    """Silence would let an in-sample number be read as a generalisation one."""
    from engine.loader import load_all
    from scripts.train_ppo import fit_clone
    from tests.paths import REAL_DATA_DIR

    data = load_all(REAL_DATA_DIR)
    model, dataset = _tiny_clone_inputs(data)
    stats = fit_clone(model, dataset, epochs=1)
    assert "explained_variance_holdout" not in stats


def test_fit_clone_clips_gradients():
    """The BC/DAgger fit must clip, as SB3's own PPO update does.

    Without clipping a single bad batch destroys the policy. A DAgger run went
    from loss 0.257 at epoch 6 to 371159 by epoch 18 and finished placing 8.000
    in every game, after two healthy rounds at 92-93% action match
    (doc 99 entry 55.1). Cloning survived the same code because its dataset was
    smaller; aggregation did not.

    **Structural rather than behavioural, deliberately.** A behavioural version
    was written first -- poison some value targets, assert the loss stays
    finite -- and it **passed against the unclipped code** at every size tried
    (one target then every seventh, 1e6 then 1e8, 3 epochs then 8). The real
    divergence needed 237k rows and 18 epochs; a fixture that small recovers.
    A test that passes on broken code reads as coverage, so it was deleted
    rather than kept. This one is mutation-checked: removing the clip fails it.
    """
    from pathlib import Path

    source = (
        Path(__file__).resolve().parent.parent / "scripts" / "train_ppo.py"
    ).read_text()
    fit = source[source.index("def fit_clone"):]
    assert "clip_grad_norm_" in fit, "fit_clone must clip gradients"
    assert "model.max_grad_norm" in fit, (
        "clip to the model's own max_grad_norm, not a second hardcoded constant"
    )


def test_label_smoothing_bounds_the_logits():
    """The fit must not drive logits to infinity, and smoothing is what stops it.

    Plain softmax cross-entropy on near-separable data has no interior minimum:
    once the argmax is right, the only remaining gradient pushes the correct
    logit further out, forever. Instrumented runs grew monotonically -- BC to
    ~1200 over 50 epochs, and a DAgger refit starting from there to 1.2e8, at
    which point one misclassified example contributed a loss of ~1e5 and the
    policy was destroyed (doc 99 entry 57).

    Three earlier attempts bounded the *rate* of that march rather than its
    destination -- gradient clipping, a lower learning rate, and AdamW decay --
    and each only moved which round blew up. Decay was measured on its own:
    1224 -> 684 over the same 50 epochs, with the last eight steeper than the
    middle thirty. So this asserts the comparison, not an absolute threshold:
    the same fit, same seed, same data, smoothed against unsmoothed.
    """
    from engine.loader import load_all
    from scripts.train_ppo import fit_clone
    from tests.paths import REAL_DATA_DIR

    data = load_all(REAL_DATA_DIR)
    epochs = 12
    smoothed = fit_clone(
        *_tiny_clone_inputs(data), epochs=epochs, label_smoothing=0.02
    )
    plain = fit_clone(*_tiny_clone_inputs(data), epochs=epochs, label_smoothing=0.0)

    assert "max_logit" in smoothed, "fit_clone must report the largest logit"
    assert smoothed["max_logit"] < plain["max_logit"], (
        f"smoothing did not bound the logits: {smoothed['max_logit']:.1f} "
        f"smoothed vs {plain['max_logit']:.1f} plain. Bounding them is the "
        "whole point of the term"
    )


def test_value_head_rewinds_but_the_policy_does_not():
    """The critic is rewound to its best epoch; the policy keeps every epoch.

    The value head's held-out explained variance peaks at epoch 1-3 and decays
    for the remaining 47, while action match needs all 50 (63.5% -> 89.8%).
    Early-stopping the whole fit would trade the policy away for the critic;
    running to completion leaves the critic memorising (0.965 in-sample against
    0.228 held-out). The fit does both, which is only possible because the two
    share no parameters (doc 99 entry 59.2).

    **Compared against a run with no rewind, not against pre-training values.**
    The first version asserted only that some policy parameter had moved during
    the fit, and it **passed** against a mutation that rewound the whole network
    -- because when the best epoch is the last one, restoring everything is a
    no-op and the policy has still moved. Two fits from identical seeds, one
    with a holdout and one without, must leave *identical* policy parameters:
    that is the claim, and it is what the mutation breaks.
    """
    import torch

    from engine.loader import load_all
    from scripts.train_ppo import fit_clone
    from tests.paths import REAL_DATA_DIR

    data = load_all(REAL_DATA_DIR)
    EPOCHS = 12

    def policy_after(with_holdout: bool):
        torch.manual_seed(0)
        model, dataset = _tiny_clone_inputs(data)
        observations, _, _, returns = dataset
        half = len(observations) // 2
        subset = tuple(part[:half] for part in dataset)
        holdout = (observations[half:], returns[half:]) if with_holdout else None
        torch.manual_seed(0)
        stats = fit_clone(model, subset, epochs=EPOCHS, holdout=holdout)
        return stats, {
            k: v.detach().clone()
            for k, v in model.policy.state_dict().items()
            if k.startswith("action_net.")
        }

    stats, rewound = policy_after(True)
    _, plain = policy_after(False)

    assert "value_best_epoch" in stats, "the fit must report which epoch it kept"
    # Without this the test goes vacuous: if the best epoch is the last one,
    # rewinding is a no-op and even a mutation that restores the *whole*
    # network passes. That mutation did pass an earlier version of this test.
    assert stats["value_best_epoch"] < EPOCHS, (
        f"value head peaked at the final epoch ({EPOCHS}), so the rewind is a "
        "no-op and this test cannot detect a rewind that is too broad"
    )

    differing = [k for k in plain if not torch.equal(plain[k], rewound[k])]
    assert not differing, (
        f"{len(differing)} policy tensors changed when the value head was "
        f"rewound (e.g. {differing[0]}); the rewind must touch the critic only"
    )


def test_value_rewind_is_skipped_without_a_holdout():
    """With no holdout there is no honest epoch to rewind to, so it must not."""
    from engine.loader import load_all
    from scripts.train_ppo import fit_clone
    from tests.paths import REAL_DATA_DIR

    data = load_all(REAL_DATA_DIR)
    model, dataset = _tiny_clone_inputs(data)
    stats = fit_clone(model, dataset, epochs=2)
    assert "value_best_epoch" not in stats
