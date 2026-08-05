"""PPO training loop (milestone 7, doc 03 sec 3.4).

Uses **MaskablePPO** from ``sb3-contrib`` rather than plain SB3 PPO: the action
space is large and mostly illegal at any given moment, and doc 03 sec 3.2's
design assumes masking. Masking turns "learn the rules of the interface" into a
non-problem so the agent only has to learn strategy.

Tracks win rate and average placement over training, per doc 03 sec 4.

    python scripts/train_ppo.py --timesteps 50000
    python scripts/train_ppo.py --timesteps 200000 --envs 8 --eval-episodes 30
    python scripts/train_ppo.py --baseline-only     # just measure the baselines

Checkpoints are written with a metadata sidecar recording the data version,
hyperparameters and metrics, so a saved model can always be traced back to the
Set/patch it was trained against (doc 02 sec 6).
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from engine.loader import load_all  # noqa: E402
from rl.collect import (  # noqa: E402
    collect_episode,
    collect_parallel,
)
from rl.env import SHAPING_MODES, TFTEnv  # noqa: E402
from rl.evaluate import (  # noqa: E402
    end_planning_policy,
    evaluate,
    random_policy,
    sb3_policy,
    scripted_policy,
)
from rl.observation import CHAMPION_ENCODINGS, SCOUTING_MODES  # noqa: E402
from rl.timing import timed  # noqa: E402

DEFAULT_RUN_DIR = Path("runs")


# Env options shared by every helper here -- training, evaluation, expert
# collection and the run metadata. Set once from the CLI so the observation
# layout cannot differ between them; a mismatch otherwise surfaces as an
# opaque matmul shape error inside torch rather than as a config problem.
ENV_DEFAULTS: dict[str, object] = {}


def build_env(data, seed: int | None = None, **kwargs) -> TFTEnv:
    return TFTEnv(data=data, seed=seed, **{**ENV_DEFAULTS, **kwargs})


def make_vec_env(data, n_envs: int, seed: int, shaping: bool = False, pool=None,
                 mix: float = 1.0):
    """Build the training envs, optionally with self-play opponent seats.

    ``pool`` is a :class:`~rl.selfplay.SnapshotPool`. Passing one is safe from
    step 0: while it is empty every seat falls back to the scripted bot, so
    training begins against the heuristics and shifts to self-play as
    snapshots accumulate.
    """
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv

    def factory(rank: int):
        def _init():
            env = build_env(data, seed=seed + rank, reward_shaping=shaping)
            if pool is not None:
                from rl.selfplay import snapshot_factory

                env.opponent_factory = snapshot_factory(
                    pool, env, mix=mix, seed=seed + rank
                )
            return Monitor(env)

        return _init

    return DummyVecEnv([factory(i) for i in range(n_envs)])


class MetricsCallback:
    """Periodically evaluates the policy and records win rate / avg placement.

    Implemented against SB3's ``BaseCallback`` lazily so importing this module
    does not require torch when only the baselines are being measured.
    """

    def __new__(cls, *args, **kwargs):
        from stable_baselines3.common.callbacks import BaseCallback

        class _Callback(BaseCallback):
            def __init__(self, data, every: int, episodes: int, run_dir: Path, verbose=1):
                super().__init__(verbose)
                self.data = data
                self.every = every
                self.episodes = episodes
                self.run_dir = run_dir
                self.history: list[dict] = []
                self._eval_env = build_env(data)

            def _on_step(self) -> bool:
                if self.num_timesteps % self.every != 0:
                    return True
                self._record()
                return True

            def _record(self) -> None:
                result = evaluate(
                    self._eval_env,
                    sb3_policy(self.model),
                    seeds=range(self.episodes),
                )
                entry = {"timesteps": self.num_timesteps, **result.as_dict()}
                self.history.append(entry)
                self.logger.record("eval/avg_placement", result.avg_placement)
                self.logger.record("eval/win_rate", result.win_rate)
                self.logger.record("eval/top4_rate", result.top4_rate)
                if self.verbose:
                    print(
                        f"[{self.num_timesteps:>8} steps] "
                        f"avg_placement={result.avg_placement:.3f}  "
                        f"win_rate={result.win_rate:.1%}  top4={result.top4_rate:.1%}"
                    )
                (self.run_dir / "metrics.json").write_text(json.dumps(self.history, indent=2))

            def on_training_end(self) -> None:
                self._record()

        return _Callback(*args, **kwargs)


class SnapshotCallback:
    """Periodically freezes the current policy into a self-play pool.

    Snapshots go through ``save``/``load`` rather than ``copy.deepcopy``: an
    SB3 model holds an optimiser, a rollout buffer and a live reference to the
    vectorised env it is training in, and deep-copying that graph would give
    the opponent seats a handle on the learner's own env. Round-tripping
    through disk yields a genuinely detached policy, and leaves the snapshots
    on disk as artifacts.
    """

    def __new__(cls, *args, **kwargs):
        from stable_baselines3.common.callbacks import BaseCallback

        class _Callback(BaseCallback):
            def __init__(self, pool, every: int, run_dir: Path, verbose=1):
                super().__init__(verbose)
                self.pool = pool
                self.every = every
                self.dir = run_dir / "snapshots"
                self.dir.mkdir(parents=True, exist_ok=True)

            def _on_step(self) -> bool:
                if self.num_timesteps % self.every == 0:
                    self._snapshot()
                return True

            def _snapshot(self) -> None:
                from sb3_contrib import MaskablePPO

                path = self.dir / f"snapshot_{self.num_timesteps}"
                self.model.save(path)
                self.pool.add(MaskablePPO.load(path, device=self.model.device))
                if self.verbose:
                    print(
                        f"[{self.num_timesteps:>8} steps] "
                        f"snapshot added (pool size {len(self.pool)})"
                    )

        return _Callback(*args, **kwargs)


def collect_expert_data(
    data,
    episodes: int,
    gamma: float = 0.999,
    actor=None,
    seed_offset: int = 10_000,
    expert_kwargs: dict | None = None,
    search_kwargs: dict | None = None,
    workers: int | None = None,
    **env_kwargs,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Record ``(observation, action_mask, expert action, return)``.

    ``env_kwargs`` must match whatever the model's own env was built with --
    anything affecting the observation layout (``champion_encoding``,
    ``scouting``) would otherwise produce transitions the policy cannot
    consume, and ``reward_shaping`` would make the returns describe a different
    reward than PPO will see.

    Returns are the discounted sum of future reward within each episode, at
    the same ``gamma`` PPO trains with -- that is what makes them a valid
    regression target for the value head.

    **``actor`` is what turns this into DAgger.** With ``actor=None`` the
    scripted expert both chooses and labels, giving plain behaviour cloning:
    every state comes from the expert's own distribution, so the student never
    sees the states its own mistakes lead to. Pass a student policy and the
    *actor* drives the episode while the *expert still labels every state* --
    the aggregation step from Ross, Gordon & Bagnell (2011). That is the
    documented fix for the compounding drift measured here: 81.7% action match
    against the expert, yet 1.29 placement worse than it (doc 99 22, open 3).
    """
    seeds = [seed_offset + seed for seed in range(episodes)]

    # Only plain cloning parallelises; a DAgger actor is a torch model that
    # would have to be shipped to every worker and re-shipped each round.
    if actor is None and workers != 1 and episodes > 1:
        return collect_parallel(
            seeds,
            gamma,
            workers=workers,
            env_kwargs={**ENV_DEFAULTS, **env_kwargs},
            expert_kwargs=expert_kwargs or {},
            search_kwargs=search_kwargs,
        )

    env = build_env(data, **env_kwargs)
    # The teacher's own configuration is part of the dataset, not a detail:
    # imitation caps at whatever this policy does, so cloning a teacher that
    # cannot sell caps the student there too (doc 99 entry 37.4).
    policy = scripted_policy(env, **(expert_kwargs or {}))
    if search_kwargs is not None:
        from rl.search import search_policy

        policy = search_policy(env, base=policy, **search_kwargs)
    observations, masks, actions, returns = [], [], [], []
    for seed in seeds:
        episode_start = len(observations)
        # The per-episode loop is shared with the parallel path so the two
        # cannot drift; labelling happens before the step in both.
        block_obs, block_masks, block_actions, block_returns = collect_episode(
            env, policy, seed, gamma, actor=actor
        )
        observations.extend(block_obs)
        masks.extend(block_masks)
        actions.extend(block_actions)
        returns.extend(block_returns)
        assert len(returns) == len(observations) == episode_start + len(block_returns)
    return (
        np.array(observations),
        np.array(masks),
        np.array(actions),
        np.array(returns, dtype=np.float32),
    )


def student_actor(model):
    """Wrap a model as an ``actor`` for :func:`collect_expert_data`.

    Sampled rather than deterministic: DAgger wants the states the student
    actually reaches, and a deterministic rollout explores a vanishingly narrow
    slice of them.
    """

    def act(obs, mask):
        action, _ = model.predict(obs, action_masks=mask, deterministic=False)
        return int(action)

    return act


def behaviour_clone(
    model,
    data,
    episodes: int,
    epochs: int,
    batch_size: int = 256,
    gamma: float = 0.999,
    value_coef: float = 0.5,
    expert_kwargs: dict | None = None,
    search_kwargs: dict | None = None,
    label_smoothing: float = 0.02,
    **env_kwargs,
) -> tuple[dict, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
    """Warm-start the policy *and the value head* by imitating the scripted heuristic.

    With a terminal-only reward an untrained policy places 8th every game, so
    PPO starts with no gradient (see doc 99 entry 6c.2). Even with
    shaping, discovering the BUY -> SELECT -> PLACE chain by chance is slow.
    Behaviour cloning puts the policy in the neighbourhood of competent play
    first; PPO then improves from there rather than from nothing.

    **The value term is not optional garnish.** Cloning the policy alone
    optimises ``-log_prob``, which backprops through the action head and the
    shared feature extractor but gives the value head *zero* gradient -- while
    rewriting the extractor underneath it. PPO then starts from a critic that
    is both untrained and mismatched to its own inputs: measured
    ``explained_variance`` at the first update was **-0.43**, worse than
    predicting the mean. Advantages computed against that baseline are noise,
    and the first updates walk the cloned policy off its solution, which is why
    PPO made the agent *worse* than its own warm start (doc 99 entry 18).

    Regressing the value head on the expert's observed discounted returns fixes
    the input to PPO's advantage estimate. ``value_coef`` weights it against the
    imitation term. Returns the final diagnostics so the caller can record
    whether the critic actually fitted, and the collected dataset so DAgger can
    aggregate onto it.
    """
    dataset = collect_expert_data(
        data, episodes, gamma=gamma, expert_kwargs=expert_kwargs,
        search_kwargs=search_kwargs, **env_kwargs
    )
    print(f"  collected {len(dataset[0])} expert transitions from {episodes} episodes")
    # A small held-out set from the same teacher, on seeds disjoint from the
    # training range, so the critic's quality is reported on states it did not
    # fit. Cheap now that collection is parallel (doc 99 entry 48.5).
    holdout_obs, _, _, holdout_returns = collect_expert_data(
        data,
        max(episodes // 20, 5),
        gamma=gamma,
        seed_offset=510_000,
        expert_kwargs=expert_kwargs,
        search_kwargs=search_kwargs,
        **env_kwargs,
    )
    stats = fit_clone(
        model,
        dataset,
        epochs,
        batch_size=batch_size,
        value_coef=value_coef,
        holdout=(holdout_obs, holdout_returns),
        label="bc",
        label_smoothing=label_smoothing,
    )
    return stats, dataset


def fit_clone(
    model,
    dataset: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    epochs: int,
    batch_size: int = 256,
    value_coef: float = 0.5,
    label: str = "bc",
    holdout: tuple[np.ndarray, np.ndarray] | None = None,
    lr: float = 1e-3,
    weight_decay: float = 1e-2,
    label_smoothing: float = 0.02,
) -> dict:
    """Supervised fit of policy + value head on ``(obs, masks, actions, returns)``.

    Split out of :func:`behaviour_clone` so DAgger can refit on an aggregated
    dataset without re-deriving the training loop.
    """
    import torch

    obs, masks, actions, returns = dataset
    expected = model.observation_space.shape[0]
    if obs.shape[1] != expected:
        raise ValueError(
            f"expert observations are {obs.shape[1]}-dim but the policy expects "
            f"{expected}. Pass the same env kwargs used to build the model "
            f"(e.g. champion_encoding)."
        )

    device = model.device
    obs_t = torch.as_tensor(obs, dtype=torch.float32, device=device)
    mask_t = torch.as_tensor(masks, dtype=torch.bool, device=device)
    action_t = torch.as_tensor(actions, dtype=torch.long, device=device)
    return_t = torch.as_tensor(returns, dtype=torch.float32, device=device)

    # A fresh Adam per call, so each DAgger refit restarts its moment
    # estimates. `lr` is exposed because 1e-3 -- 3.3x PPO's rate -- is stable on
    # a 137k-row expert dataset and **not** on an aggregated one: two DAgger
    # runs diverged to a loss of 1e5-3e5 and finished placing ~8.000, once in
    # round 3 and once in round 1. Gradient clipping alone did not prevent it
    # (doc 99 entry 55).
    # AdamW rather than Adam: **the logits are otherwise unbounded**.
    # Instrumented, every fit grows them monotonically -- BC reaches ~1200 by
    # epoch 50 and a DAgger refit starting from there reaches 1.2e8, at which
    # point one misclassified example contributes a loss of ~1e5 and the policy
    # is destroyed (doc 99 entry 57). That is the classic behaviour of softmax
    # cross-entropy on nearly-separable data: at 94% action match the remaining
    # gradient just drives the correct logit further out, forever.
    #
    # Neither of the two fixes tried before this addressed it. Gradient
    # clipping bounds step *size* while the drift is slow and directional, and
    # lowering the learning rate only slows the march -- which is exactly why
    # it moved the divergence from round 1 to round 2 instead of preventing it.
    # Decay was measured and is **not** sufficient on its own: it halved the
    # endpoint (1224 -> 684 over 50 BC epochs) without flattening the curve,
    # whose last eight epochs were steeper than its middle thirty. It is kept
    # because it cost no accuracy (89.4% -> 88.8%), not because it worked.
    #
    # `label_smoothing` is the part that actually bounds them, and it is the
    # only one of the four with a reason it *must*. Clipping, learning rate and
    # decay all bound the rate of travel against an objective whose optimum is
    # at infinity; plain cross-entropy on separable data has no interior
    # minimum to settle into. Smoothing gives it one: the loss is minimised at a
    # finite logit gap of log((1-eps)(K-1)/eps), so the drift has somewhere to
    # stop (doc 99 entry 57).
    optimiser = torch.optim.AdamW(
        model.policy.parameters(), lr=lr, weight_decay=weight_decay
    )
    n = len(obs_t)
    stats: dict = {}

    def _ev(observations, returns_tensor) -> float:
        predicted = model.policy.predict_values(observations).flatten()
        total = torch.var(returns_tensor)
        if total <= 0:
            return 0.0
        return float(1 - torch.var(returns_tensor - predicted) / total)

    hold_obs_t = hold_return_t = None
    if holdout is not None:
        hold_obs_t = torch.as_tensor(holdout[0], dtype=torch.float32, device=device)
        hold_return_t = torch.as_tensor(holdout[1], dtype=torch.float32, device=device)

    # **The value head peaks decades of epochs before the policy does.** Measured
    # over 75-1200 episodes, held-out explained variance is best at epoch 1-3 and
    # falls thereafter, while action match needs all 50 epochs (63.5% -> 89.8%).
    # Stopping the whole fit early would trade the policy away for the critic.
    #
    # The two are separable because they share no parameters: with
    # `net_arch=dict(pi=[], vf=[256,256])` over a parameterless Flatten
    # extractor, the value branch is `mlp_extractor.value_net.*` + `value_net.*`
    # and the policy is `action_net.*`. So the fit runs to completion for the
    # policy while the value head is rewound to its own best epoch
    # (doc 99 entry 59.2).
    value_prefixes = ("mlp_extractor.value_net.", "value_net.")
    best_value = {"ev": -float("inf"), "epoch": 0, "state": None}

    for epoch in range(epochs):
        permutation = torch.randperm(n, device=device)
        total_loss = 0.0
        total_value_loss = 0.0
        max_grad = 0.0
        max_logit = 0.0
        correct = 0
        for start in range(0, n, batch_size):
            batch = permutation[start : start + batch_size]
            distribution = model.policy.get_distribution(
                obs_t[batch], action_masks=mask_t[batch]
            )
            log_prob = distribution.log_prob(action_t[batch])
            if label_smoothing > 0.0:
                # Spread `label_smoothing` uniformly over the *legal* actions,
                # not all of them. `distribution.logits` is already normalised
                # log-probability with illegal entries at ~-1e8, so masking
                # before the mean is what keeps those out of the target.
                legal_mask = mask_t[batch].float()
                mean_legal = (
                    distribution.distribution.logits * legal_mask
                ).sum(-1) / legal_mask.sum(-1).clamp(min=1.0)
                policy_loss = -(
                    (1.0 - label_smoothing) * log_prob
                    + label_smoothing * mean_legal
                ).mean()
            else:
                policy_loss = -log_prob.mean()
            values = model.policy.predict_values(obs_t[batch]).flatten()
            value_loss = torch.nn.functional.mse_loss(values, return_t[batch])
            loss = policy_loss + value_coef * value_loss
            optimiser.zero_grad()
            loss.backward()
            # Instrumentation, not decoration. Three DAgger runs diverged at
            # three different rounds under three configurations, and two
            # proposed mechanisms (no clipping, then learning rate) each only
            # moved *when* it happened. Gradient norm before clipping and the
            # largest logit separate "the gradient spiked" from "the weights
            # drifted until the logits blew up" -- which no loss curve can
            # (doc 99 entry 57).
            grad_norm = float(
                torch.nn.utils.clip_grad_norm_(
                    model.policy.parameters(), model.max_grad_norm
                )
            )
            max_grad = max(max_grad, grad_norm)
            with torch.no_grad():
                # Only *legal* actions. sb3-contrib fills masked logits with a
                # large negative constant (~1e8), so an unfiltered max reads
                # that constant every time and says nothing about the network.
                legal = distribution.distribution.logits[mask_t[batch]]
                if legal.numel():
                    max_logit = max(max_logit, float(legal.abs().max()))
            optimiser.step()
            total_loss += float(policy_loss.detach()) * len(batch)
            total_value_loss += float(value_loss.detach()) * len(batch)
            with torch.no_grad():
                predicted = distribution.distribution.logits.argmax(dim=-1)
                correct += int((predicted == action_t[batch]).sum())
        stats = {
            "policy_loss": total_loss / n,
            "value_loss": total_value_loss / n,
            "action_match": correct / n,
            # Returned, not just printed, so the divergence that destroyed three
            # DAgger runs is assertable and lands in the run's sidecar.
            "max_logit": max_logit,
            "max_grad": max_grad,
        }
        held = ""
        if hold_obs_t is not None:
            with torch.no_grad():
                ev_hold = _ev(hold_obs_t, hold_return_t)
            held = f" ev_hold={ev_hold:.3f}"
            if ev_hold > best_value["ev"]:
                best_value = {
                    "ev": ev_hold,
                    "epoch": epoch + 1,
                    "state": {
                        k: v.detach().clone()
                        for k, v in model.policy.state_dict().items()
                        if k.startswith(value_prefixes)
                    },
                }
        print(
            f"  {label} epoch {epoch + 1}/{epochs}: loss={stats['policy_loss']:.4f} "
            f"value_loss={stats['value_loss']:.4f} "
            f"action_match={stats['action_match']:.1%} "
            f"grad={max_grad:.2f} logit={max_logit:.1f}{held}"
        )

    # The number that says whether the fix worked: PPO's advantage estimate is
    # only as good as this. Below 0 the critic is worse than a constant.
    #
    # Reported **twice**, in-sample and held-out, because for a long time only
    # the first existed and it flattered the critic badly: 0.968 on the rows it
    # had just fitted against 0.262 on held-out expert states from the same
    # teacher (doc 99 entry 49.3). The in-sample figure was cited as evidence
    # the value-regression warm start worked. It shows the optimiser converged;
    # it says nothing about whether the critic generalises, and PPO consumes it
    # on states it has never seen.
    if best_value["state"] is not None:
        model.policy.load_state_dict(best_value["state"], strict=False)
        stats["value_best_epoch"] = best_value["epoch"]
        print(
            f"  value head rewound to epoch {best_value['epoch']}/{epochs} "
            f"(held-out EV {best_value['ev']:.3f}); the policy keeps all "
            f"{epochs} (doc 99 entry 59.2)"
        )

    with torch.no_grad():
        stats["explained_variance"] = _ev(obs_t, return_t)
        if hold_obs_t is not None:
            stats["explained_variance_holdout"] = _ev(hold_obs_t, hold_return_t)
    message = (
        f"  critic explained_variance: {stats['explained_variance']:.3f} in-sample"
    )
    if "explained_variance_holdout" in stats:
        message += f", {stats['explained_variance_holdout']:.3f} held-out"
    else:
        message += " (no holdout supplied -- in-sample only, see doc 99 entry 49.3)"
    print(message)
    return stats


def dagger(
    model,
    data,
    rounds: int,
    episodes_per_round: int,
    epochs: int,
    dataset: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    batch_size: int = 256,
    gamma: float = 0.999,
    value_coef: float = 0.5,
    seed_offset: int = 50_000,
    expert_kwargs: dict | None = None,
    lr: float = 3e-4,
    label_smoothing: float = 0.02,
    **env_kwargs,
) -> list[dict]:
    """DAgger: aggregate expert labels on states the *student* actually reaches.

    Plain behaviour cloning trains only on the expert's own state distribution.
    The student is then evaluated on the distribution *it* induces, and any
    disagreement compounds: one off-policy action leads somewhere the expert
    never went, where the clone has no data, which causes the next mistake.
    Measured here at 81.7% action match but 1.29 placement worse than the
    teacher -- an 18% disagreement rate costing a fifth of the placement range,
    which is the signature of exactly this failure (doc 99 22, open item 3).

    Each round rolls out under the current student, labels every visited state
    with the expert's choice, appends to the aggregate, and refits from that.
    The dataset only grows -- discarding earlier rounds reintroduces the
    forgetting the method exists to prevent.
    """
    history: list[dict] = []
    # Its own held-out set, on seeds disjoint from both the training range and
    # the warm start's holdout, so every refit can rewind its value head to the
    # right epoch. Without one, DAgger rounds train the critic 50 epochs past
    # its optimum -- the defect entry 59.2 found in the warm start.
    holdout_obs, _, _, holdout_returns = collect_expert_data(
        data,
        max(episodes_per_round // 10, 5),
        gamma=gamma,
        seed_offset=610_000,
        expert_kwargs=expert_kwargs,
        **env_kwargs,
    )
    for round_index in range(rounds):
        fresh = collect_expert_data(
            data,
            episodes_per_round,
            gamma=gamma,
            actor=student_actor(model),
            seed_offset=seed_offset + round_index * episodes_per_round,
            expert_kwargs=expert_kwargs,
            **env_kwargs,
        )
        dataset = tuple(
            np.concatenate([old, new]) for old, new in zip(dataset, fresh, strict=True)
        )
        print(
            f"\n--- dagger round {round_index + 1}/{rounds}: "
            f"+{len(fresh[0])} student-state transitions, "
            f"{len(dataset[0])} total ---"
        )
        stats = fit_clone(
            model,
            dataset,
            epochs,
            batch_size=batch_size,
            value_coef=value_coef,
            label=f"dagger{round_index + 1}",
            lr=lr,
            label_smoothing=label_smoothing,
            holdout=(holdout_obs, holdout_returns),
        )
        history.append(stats)
    return history


def measure_baselines(data, episodes: int) -> dict:
    """Doc 03 sec 4: know the floor before claiming the agent learned anything."""
    env = build_env(data)
    rng = random.Random(0)
    baselines = {
        "do_nothing": end_planning_policy(env),
        "random_legal": random_policy(rng),
        "scripted": scripted_policy(env),
    }
    out = {}
    for name, policy in baselines.items():
        result = evaluate(env, policy, seeds=range(episodes))
        out[name] = result.as_dict()
        print(f"{name:>14}: {result.summary()}")
    return out


def write_metadata(run_dir: Path, data, args, metrics: dict, elapsed: float) -> None:
    """CLAUDE.md: store checkpoints with the context needed to interpret them."""
    metadata = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "elapsed_seconds": round(elapsed, 1),
        "data_version": asdict(data.version),
        "unverified_constants": list(data.config.unverified),
        "hyperparameters": vars(args),
        "metrics": metrics,
        "algorithm": "MaskablePPO (sb3-contrib)",
        "observation_size": build_env(data).observation_space.shape[0],
        "action_space_size": build_env(data).action_space.n,
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, default=str))


# Flags that change the observation width or the policy class. A mismatch on
# any of these makes the checkpoint's weights the wrong shape for the model
# being built -- which `set_parameters` catches, but only as a tensor-shape
# error naming a layer, from which the actual cause is not obvious.
ARCHITECTURE_FLAGS = ("copy_counts", "champion_encoding", "scouting", "slot_head")


def check_init_flags(checkpoint: Path, args) -> None:
    """Fail loudly when --init-from is handed a differently-shaped run.

    Three scripts in this project have reconstructed an env from module
    defaults rather than from the checkpoint they were loading, and each time
    the result was a plausible-looking number measured on the wrong thing
    (doc 99 entry 45.2). The sidecar records what the checkpoint was actually
    built with, so this compares against that rather than trusting the caller.
    """
    sidecar = checkpoint.parent / "metadata.json"
    if not sidecar.exists():
        print(f"  !! {sidecar} missing -- cannot verify architecture flags")
        return
    saved = json.loads(sidecar.read_text()).get("hyperparameters", {})
    mismatched = [
        (flag, saved.get(flag), getattr(args, flag))
        for flag in ARCHITECTURE_FLAGS
        if flag in saved and saved[flag] != getattr(args, flag)
    ]
    if mismatched:
        detail = ", ".join(f"{f}: checkpoint={was!r} but requested={now!r}"
                           for f, was, now in mismatched)
        raise SystemExit(
            f"--init-from {checkpoint} was trained with different architecture "
            f"flags ({detail}). Pass the checkpoint's flags, or clone afresh."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timesteps", type=int, default=50_000)
    parser.add_argument("--envs", type=int, default=4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--eval-episodes", type=int, default=100,
                        help="30 episodes gives a 95%% CI of about +/-0.7 placement, "
                             "which is wider than the effects worth detecting")
    parser.add_argument("--eval-every", type=int, default=10_000)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--n-steps", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--gamma", type=float, default=0.999, help="long horizon: ~30 rounds")
    parser.add_argument("--ent-coef", type=float, default=0.01)
    parser.add_argument(
        "--expert-sell",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "give the cloning teacher a sell branch. The teacher could not "
            "sell until 2026-08-03, so its bench filled and it made 28.6 "
            "purchases a game against an achievable 136.8 -- and imitation "
            "caps at the teacher (doc 99 entry 37.4). Off reproduces every "
            "clone measured before that date"
        ),
    )
    parser.add_argument(
        "--expert-roll-at-level",
        type=int,
        default=0,
        help=(
            "teacher spends spare gold rerolling from this level up; 0 is off. "
            "Inert without --expert-sell (doc 99 entry 37.4)"
        ),
    )
    parser.add_argument(
        "--dagger-rounds",
        type=int,
        default=0,
        help=(
            "after the initial clone, run N rounds of DAgger: roll out under "
            "the *student*, label every visited state with the scripted "
            "expert, aggregate, refit. Targets compounding off-policy drift -- "
            "the clone matches the expert's action 81.7%% of the time yet "
            "places 1.29 worse than it (doc 99 22, open item 3). 0 disables"
        ),
    )
    parser.add_argument(
        "--dagger-lr",
        type=float,
        default=3e-4,
        help=(
            "learning rate for DAgger refits. The clone fits at 1e-3, which is "
            "stable on 137k expert rows and diverged on aggregated ones -- two "
            "runs blew up to a loss of 1e5-3e5 and finished placing ~8.000, "
            "and gradient clipping alone did not prevent it (doc 99 entry 55). "
            "Defaults to PPO's 3e-4"
        ),
    )
    parser.add_argument(
        "--label-smoothing",
        type=float,
        default=0.02,
        help=(
            "smoothing mass spread over the legal actions in every supervised "
            "fit. Bounds the logits, which plain cross-entropy does not: on "
            "near-separable data its optimum is at infinite logit gap, and "
            "instrumented runs grew monotonically to 1.2e8 and destroyed the "
            "policy. Smoothing puts the optimum at log((1-eps)(K-1)/eps) "
            "instead (doc 99 entry 57). 0 restores plain cross-entropy"
        ),
    )
    parser.add_argument(
        "--dagger-episodes",
        type=int,
        default=100,
        help="episodes of student rollout collected per DAgger round",
    )
    parser.add_argument(
        "--target-kl",
        type=float,
        default=None,
        help=(
            "stop an update early once the policy has moved this far (in KL) "
            "from the one that collected the rollout. Briefly the default at "
            "0.02, on evidence from a weak warm start (doc 99 23.5): it "
            "removed that clone's degradation entirely. **Reverted** -- from a "
            "clone at teacher parity the same setting is the *worst* arm "
            "measured (+0.793 placement, t=+4.36, last-place rate 11.7%% -> "
            "26.3%%), while no leash is flat (+0.070, t=+0.38). See doc 99 "
            "entry 31. None disables"
        ),
    )
    # Defaults flipped on 2026-08-04 (doc 99 entry 53). Until then a run with
    # no flags reproduced a configuration measured ~1.5 placement worse than
    # the best known one: no `copy_counts` (t=-4.55, 40.1), a teacher that
    # could not sell (worth 1.893, 52.2), and no teacher flags (-0.407,
    # t=-2.82, 43). Every one of them is a *measured* improvement, and leaving
    # them opt-in meant the honest default was the weak one. `--no-...`
    # reproduces the old behaviour for any comparison that needs it.
    parser.add_argument(
        "--expert-reposition",
        action="store_true",
        help=(
            "wrap the cloning teacher in a one-ply positional search, so it "
            "moves a fielded unit when simulation says a different arrangement "
            "wins. The scripted teacher issues **zero** board-slot SELECTs -- "
            "it places a unit once and never revisits it (doc 99 entry 52.4) -- "
            "while rearranging a fixed board moves the fight outcome by 2.8x "
            "engine noise with a 5.78-unit best-worst spread (47.2). This is "
            "the one axis the incumbent leaves entirely untouched"
        ),
    )
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--device", default="cpu", help="cpu is faster for small MLPs")
    parser.add_argument(
        "--warm-start",
        type=int,
        default=400,
        help=(
            "behaviour-clone from the scripted policy for N episodes first. "
            "400 is the measured minimum viable value: at 150 the cloned "
            "policy places 8th in 84%% of games, which leaves no outcome "
            "variance for any comparison to resolve (docs/99_judgement_calls.md "
            "18.5). 0 disables cloning"
        ),
    )
    parser.add_argument("--warm-start-epochs", type=int, default=50)
    parser.add_argument(
        "--init-from",
        type=Path,
        default=None,
        help=(
            "start PPO from an existing run's model.zip instead of cloning "
            "again. Cloning costs ~39 minutes and is deterministic, so every "
            "PPO arm branched off one warm start was paying for an identical "
            "copy of it -- and any drift between those copies would confound "
            "the arms it was meant to separate. Implies --warm-start 0. The "
            "architecture-affecting flags must match the checkpoint's sidecar"
        ),
    )
    parser.add_argument(
        "--value-coef",
        type=float,
        default=0.5,
        help=(
            "weight on the value-regression term during behaviour cloning. "
            "0 reproduces the old policy-only clone, which left the critic at "
            "explained_variance -0.43 and made PPO degrade its own warm start "
            "(see doc 99 entry 18)"
        ),
    )
    parser.add_argument(
        "--shaping-mode",
        default="potential",
        choices=SHAPING_MODES,
        help=(
            "potential-based shaping is policy-invariant; 'bonus' is the "
            "earlier standing-payment form, kept for comparison "
            "(see doc 99 entry 6c.3)"
        ),
    )
    parser.add_argument(
        "--champion-encoding",
        default="index",
        choices=CHAMPION_ENCODINGS,
        help=(
            "how champions are encoded in the observation. 'features' "
            "describes role/stats/traits; 'index' is the legacy ordinal id "
            "(see doc 99 entry 6b.5)"
        ),
    )
    parser.add_argument(
        "--expert-flags",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "give the teacher buy_synergy + match_items + corner_carry. On a "
            "teacher that can sell these are worth -0.407 placement together "
            "(t=-2.82, n=300) while no one of them is significant alone "
            "(doc 99 entry 43). Measured before selling existed, they were "
            "flat -- doc 99 34.13"
        ),
    )
    parser.add_argument(
        "--slot-head",
        action="store_true",
        help=(
            "score unit slots with shared weights instead of one independent "
            "row of a flat Linear per action. Reading the same observation "
            "this way predicts the teacher's SELL choice at 99.9%% against "
            "49.1%% for a monolithic MLP (doc 99 entry 39.1)"
        ),
    )
    parser.add_argument(
        "--copy-counts",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "encode copies-held per owned unit slot. The SELL rule needs an "
            "identity match across slots to avoid breaking up a pair, and "
            "without it a probe reads the teacher's sell choice from the "
            "observation at 20.7%% against 49.1%% with it (doc 99 entry 38.9)"
        ),
    )
    parser.add_argument(
        "--scouting",
        default="summary",
        choices=SCOUTING_MODES,
        help=(
            "how much of an opponent's board the agent sees. 'full' adds board "
            "strength and trait tiers for all 7 seats. The 'measured harmful' "
            "verdict (doc 99 19.1) was WITHDRAWN by 22.2: on the frozen engine "
            "the sign reversed (+0.270, t=-1.79, not significant). Still worse "
            "than skipping PPO entirely; single training seed, needs 3-seed "
            "replication"
        ),
    )
    parser.add_argument(
        "--self-play",
        action="store_true",
        help=(
            "fill opponent seats from a pool of past policy snapshots "
            "(doc 03 sec 3.4). The 'inert' verdict (doc 99 19.2) was WITHDRAWN "
            "by 22.3: against a control that degrades, this is the only arm "
            "that holds level with its warm start (-0.580 vs the PPO control, "
            "t=-3.78). Mechanism unknown; single training seed"
        ),
    )
    parser.add_argument("--snapshot-every", type=int, default=25_000,
                        help="self-play: timesteps between policy snapshots")
    parser.add_argument("--snapshot-pool", type=int, default=5,
                        help="self-play: how many past snapshots to keep")
    parser.add_argument("--self-play-mix", type=float, default=1.0,
                        help="self-play: fraction of opponent seats drawn from "
                             "the snapshot pool; the rest stay scripted")
    parser.add_argument(
        "--reward-shaping",
        action="store_true",
        help=(
            "Enable dense survival shaping. Doc 03 sec 3.3 recommends starting "
            "without it, but with a terminal-only reward an untrained policy "
            "places 8th every game, so all returns are identical and PPO gets "
            "no gradient. Shaping is what bootstraps out of that."
        ),
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(name)s: %(message)s")
    ENV_DEFAULTS["champion_encoding"] = args.champion_encoding
    ENV_DEFAULTS["scouting"] = args.scouting
    ENV_DEFAULTS["copy_counts"] = args.copy_counts
    ENV_DEFAULTS["shaping_mode"] = args.shaping_mode
    # The telescoping guarantee only holds if shaping uses the training gamma.
    ENV_DEFAULTS["shaping_gamma"] = args.gamma
    data = load_all()

    print(f"data: set {data.version.set} patch {data.version.patch}")
    print(f"{len(data.champions)} champions, {len(data.traits)} traits, {len(data.items)} items\n")

    print("=== baselines ===")
    baselines = measure_baselines(data, args.eval_episodes)
    if args.baseline_only:
        return 0

    from sb3_contrib import MaskablePPO

    run_dir = args.run_dir or DEFAULT_RUN_DIR / time.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n=== training -> {run_dir} ===")

    np.random.seed(args.seed)
    random.seed(args.seed)

    pool = None
    if args.self_play:
        from rl.selfplay import SnapshotPool

        pool = SnapshotPool(capacity=args.snapshot_pool)
        print(
            f"self-play: snapshot every {args.snapshot_every} steps, "
            f"pool of {args.snapshot_pool}, {args.self_play_mix:.0%} of seats"
        )

    vec_env = make_vec_env(
        data,
        args.envs,
        args.seed,
        shaping=args.reward_shaping,
        pool=pool,
        mix=args.self_play_mix,
    )
    if args.slot_head:
        from rl.policy import make_slot_policy

        # Built from a throwaway env so the head's offsets come from the real
        # observation and action layouts rather than being recomputed.
        policy_class = make_slot_policy(build_env(data))
    else:
        policy_class = "MlpPolicy"

    model = MaskablePPO(
        policy_class,
        vec_env,
        learning_rate=args.learning_rate,
        n_steps=args.n_steps,
        batch_size=args.batch_size,
        gamma=args.gamma,
        ent_coef=args.ent_coef,
        # sb3 treats None as "no leash"; 0 would early-stop every update.
        target_kl=args.target_kl if args.target_kl and args.target_kl > 0 else None,
        seed=args.seed,
        device=args.device,
        verbose=0,
        tensorboard_log=str(run_dir / "tb"),
    )

    # One dict, built once, so the clone and every DAgger round label with the
    # *same* teacher. Two different teachers across rounds would aggregate
    # contradictory labels for identical states.
    expert_kwargs = {
        "sell_bench": args.expert_sell,
        "roll_at_level": args.expert_roll_at_level,
        "buy_synergy": args.expert_flags,
        "match_items": args.expert_flags,
        "corner_carry": args.expert_flags,
    }

    # `mode="move"` is the positional variant; 47.10 measured it worth ~0.19
    # pooled across five configurations, and no configuration beat another.
    search_kwargs = (
        {"mode": "move", "panel_size": 1, "max_candidates": 6}
        if args.expert_reposition
        else None
    )

    started = time.perf_counter()
    if args.init_from:
        check_init_flags(args.init_from, args)
        # `set_parameters` rather than `MaskablePPO.load`: the model built above
        # is already bound to this run's env, hyperparameters and callbacks, and
        # only its weights should come from the checkpoint. `load` would bring
        # the saved run's hyperparameters with it and silently override the ones
        # this arm is meant to be testing.
        model.set_parameters(str(args.init_from), device=args.device)
        print(f"\n--- initialised from {args.init_from} (no cloning) ---")
        warm = evaluate(build_env(data), sb3_policy(model), seeds=range(args.eval_episodes))
        print(f"  loaded checkpoint: {warm.summary()}")
        baselines["after_warm_start"] = warm.as_dict()
    elif args.warm_start:
        print("\n--- behaviour cloning from the scripted policy ---")
        # Returns must be computed under the same reward and discount PPO will
        # use, or the critic is fitted to a different objective than the one it
        # is about to serve.
        bc_stats, expert_dataset = behaviour_clone(
            model,
            data,
            args.warm_start,
            args.warm_start_epochs,
            gamma=args.gamma,
            value_coef=args.value_coef,
            expert_kwargs=expert_kwargs,
            search_kwargs=search_kwargs,
            label_smoothing=args.label_smoothing,
            reward_shaping=args.reward_shaping,
        )
        warm = evaluate(build_env(data), sb3_policy(model), seeds=range(args.eval_episodes))
        print(f"  after cloning: {warm.summary()}")
        baselines["after_warm_start"] = warm.as_dict()
        baselines["warm_start_stats"] = bc_stats

        if args.dagger_rounds:
            dagger_stats = dagger(
                model,
                data,
                args.dagger_rounds,
                args.dagger_episodes,
                args.warm_start_epochs,
                expert_dataset,
                gamma=args.gamma,
                value_coef=args.value_coef,
                expert_kwargs=expert_kwargs,
                lr=args.dagger_lr,
                label_smoothing=args.label_smoothing,
                reward_shaping=args.reward_shaping,
            )
            aggregated = evaluate(
                build_env(data), sb3_policy(model), seeds=range(args.eval_episodes)
            )
            print(f"  after dagger: {aggregated.summary()}")
            baselines["after_dagger"] = aggregated.as_dict()
            baselines["dagger_stats"] = dagger_stats

    callback = MetricsCallback(data, args.eval_every, args.eval_episodes, run_dir)
    callbacks = [callback]
    if pool is not None:
        callbacks.append(SnapshotCallback(pool, args.snapshot_every, run_dir))
    # `episodes` is the training budget in thousands of steps so the ledger's
    # per-unit rate transfers between runs of different length; the evaluation
    # passes are folded in via `arms`, since they are a large share of wall
    # clock at these step counts.
    with timed(
        "ppo",
        episodes=max(args.timesteps // 1000, 1),
        arms=1,
        workers=1,
        eval_episodes=args.eval_episodes,
        init_from=str(args.init_from) if args.init_from else None,
    ):
        model.learn(
            total_timesteps=args.timesteps,
            callback=callbacks if len(callbacks) > 1 else callback,
            progress_bar=False,
        )
    elapsed = time.perf_counter() - started

    model.save(run_dir / "model")

    print("\n=== final evaluation ===")
    env = build_env(data)
    final = evaluate(env, sb3_policy(model), seeds=range(args.eval_episodes))
    print(f"     trained: {final.summary()}")
    print(f"   vs random: avg_placement={baselines['random_legal']['avg_placement']:.3f}")
    print(f" vs scripted: avg_placement={baselines['scripted']['avg_placement']:.3f}")

    metrics = {
        "baselines": baselines,
        "final": final.as_dict(),
        "history": callback.history,
    }
    write_metadata(run_dir, data, args, metrics, elapsed)

    improvement = baselines["random_legal"]["avg_placement"] - final.avg_placement
    print(f"\nimprovement over random: {improvement:+.3f} placement")
    print(f"artifacts: {run_dir}/model.zip, metadata.json, metrics.json")
    print(f"trained {args.timesteps} steps in {elapsed:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
