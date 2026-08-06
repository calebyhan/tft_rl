"""The auxiliary expert-imitation anchor during PPO (doc 99 entry 64).

The anchor exists because PPO drifts a cloned policy toward actions that
cloning suppressed *and* that are legal nearly everywhere (entry 63). If it
silently no-ops, PPO looks unchanged and the arm reads as "the anchor does not
help" when it never ran.
"""

from __future__ import annotations

import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.train_ppo import BCAnchorCallback, collect_expert_data  # noqa: E402


def _model_and_data():
    from sb3_contrib import MaskablePPO

    from engine.loader import load_all
    from rl.env import TFTEnv
    from tests.paths import REAL_DATA_DIR

    data = load_all(REAL_DATA_DIR)
    env = TFTEnv(data=data)
    model = MaskablePPO("MlpPolicy", env, device="cpu", seed=0, n_steps=64)
    dataset = collect_expert_data(data, 2, expert_kwargs={"sell_bench": True})
    return model, dataset


def test_anchor_fires_only_on_its_interval():
    """`every` must gate the step, or the anchor runs on every environment step."""
    model, dataset = _model_and_data()
    anchor = BCAnchorCallback(dataset, coef=1.0, every=100, batch_size=8,
                              label_smoothing=0.0, lr=1e-4)
    anchor.init_callback(model)
    anchor._on_training_start()

    for timestep in (37, 99, 101):
        anchor.num_timesteps = timestep
        anchor._on_step()
    assert anchor.steps == 0, "anchor fired off-interval"

    anchor.num_timesteps = 100
    anchor._on_step()
    assert anchor.steps == 1, "anchor did not fire on its interval"


def test_anchor_moves_the_policy_toward_the_expert():
    """The load-bearing claim: it raises expert-action log-probability.

    A callback that runs but leaves the policy unchanged would be invisible in
    every training metric.
    """
    model, dataset = _model_and_data()
    observations, masks, actions, _ = dataset
    obs_t = torch.as_tensor(observations[:64], dtype=torch.float32)
    mask_t = torch.as_tensor(masks[:64], dtype=torch.bool)
    action_t = torch.as_tensor(actions[:64], dtype=torch.long)

    def expert_logprob() -> float:
        with torch.no_grad():
            distribution = model.policy.get_distribution(
                obs_t, action_masks=mask_t
            )
            return float(distribution.log_prob(action_t).mean())

    before = expert_logprob()
    anchor = BCAnchorCallback(dataset, coef=1.0, every=1, batch_size=32,
                              label_smoothing=0.0, lr=1e-3)
    anchor.init_callback(model)
    anchor._on_training_start()
    for step in range(1, 41):
        anchor.num_timesteps = step
        anchor._on_step()
    after = expert_logprob()

    assert anchor.steps == 40
    assert after > before, (
        f"expert log-prob fell {before:.4f} -> {after:.4f}; the anchor ran but "
        "did not pull the policy toward the expert"
    )


def test_zero_coefficient_leaves_the_policy_alone():
    """coef=0 must be a true no-op, so the flag's default cannot change results."""
    model, dataset = _model_and_data()
    before = {k: v.detach().clone() for k, v in model.policy.state_dict().items()}
    anchor = BCAnchorCallback(dataset, coef=0.0, every=1, batch_size=32,
                              label_smoothing=0.0, lr=1e-3)
    anchor.init_callback(model)
    anchor._on_training_start()
    for step in range(1, 6):
        anchor.num_timesteps = step
        anchor._on_step()
    after = model.policy.state_dict()
    moved = [k for k, v in before.items()
             if not torch.equal(v, after[k]) and v.dtype.is_floating_point]
    assert not moved, f"coef=0 still moved {len(moved)} tensors (e.g. {moved[:1]})"


def test_steps_multiplies_gradient_steps_per_firing():
    """`steps` must actually run that many updates.

    The first anchored run fired once per 2048 environment steps while PPO ran
    80 gradient steps in the same window. It lost 17 points of expert agreement
    and was read as "anchoring is too weak" when it measured one step against
    eighty (doc 99 entry 64). If `steps` silently ran once, the corrected arm
    would repeat that error while appearing fixed.
    """
    model, dataset = _model_and_data()
    anchor = BCAnchorCallback(dataset, coef=1.0, every=4, batch_size=8,
                              label_smoothing=0.0, lr=1e-4, steps=7)
    anchor.init_callback(model)
    anchor._on_training_start()
    anchor.num_timesteps = 4
    anchor._on_step()
    assert anchor.steps == 7, (
        f"steps=7 produced {anchor.steps} gradient steps"
    )
