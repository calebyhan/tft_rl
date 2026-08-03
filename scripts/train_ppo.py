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
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from engine.loader import load_all  # noqa: E402
from rl.env import SHAPING_MODES, TFTEnv  # noqa: E402
from rl.evaluate import (  # noqa: E402
    end_planning_policy,
    evaluate,
    random_policy,
    sb3_policy,
    scripted_policy,
)
from rl.observation import CHAMPION_ENCODINGS, SCOUTING_MODES  # noqa: E402

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


def discounted_returns(rewards: Sequence[float], gamma: float) -> list[float]:
    """Discounted return at each step, accumulated backwards from the terminal.

    ``G_t = r_t + gamma * G_{t+1}``, with ``G_T = r_T``. Computed per episode:
    letting returns bleed across an episode boundary would credit one game's
    reward to another's states, which is the classic way to poison a value
    target without it being visible in the loss curve.
    """
    running = 0.0
    out = [0.0] * len(rewards)
    for i in range(len(rewards) - 1, -1, -1):
        running = rewards[i] + gamma * running
        out[i] = running
    return out


def collect_expert_data(
    data,
    episodes: int,
    gamma: float = 0.999,
    actor=None,
    seed_offset: int = 10_000,
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
    env = build_env(data, **env_kwargs)
    policy = scripted_policy(env)
    observations, masks, actions, returns = [], [], [], []
    for seed in range(episodes):
        obs, _ = env.reset(seed=seed_offset + seed)
        terminated = False
        rewards: list[float] = []
        episode_start = len(observations)
        while not terminated:
            mask = env.action_mask()
            # Label with the expert *before* stepping -- the label must describe
            # the state as seen, not whatever the actor's move turns it into.
            observations.append(obs.copy())
            masks.append(mask.copy())
            actions.append(policy(obs, mask))
            obs, reward, terminated, _, _ = env.step(
                actions[-1] if actor is None else actor(obs, mask)
            )
            rewards.append(float(reward))
        returns.extend(discounted_returns(rewards, gamma))
        assert len(returns) == len(observations) == episode_start + len(rewards)
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
    **env_kwargs,
) -> tuple[dict, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
    """Warm-start the policy *and the value head* by imitating the scripted heuristic.

    With a terminal-only reward an untrained policy places 8th every game, so
    PPO starts with no gradient (see docs/99_judgement_calls.md 6c.2). Even with
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
    dataset = collect_expert_data(data, episodes, gamma=gamma, **env_kwargs)
    print(f"  collected {len(dataset[0])} expert transitions from {episodes} episodes")
    stats = fit_clone(
        model,
        dataset,
        epochs,
        batch_size=batch_size,
        value_coef=value_coef,
        label="bc",
    )
    return stats, dataset


def fit_clone(
    model,
    dataset: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    epochs: int,
    batch_size: int = 256,
    value_coef: float = 0.5,
    label: str = "bc",
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

    optimiser = torch.optim.Adam(model.policy.parameters(), lr=1e-3)
    n = len(obs_t)
    stats: dict = {}
    for epoch in range(epochs):
        permutation = torch.randperm(n, device=device)
        total_loss = 0.0
        total_value_loss = 0.0
        correct = 0
        for start in range(0, n, batch_size):
            batch = permutation[start : start + batch_size]
            distribution = model.policy.get_distribution(
                obs_t[batch], action_masks=mask_t[batch]
            )
            log_prob = distribution.log_prob(action_t[batch])
            policy_loss = -log_prob.mean()
            values = model.policy.predict_values(obs_t[batch]).flatten()
            value_loss = torch.nn.functional.mse_loss(values, return_t[batch])
            loss = policy_loss + value_coef * value_loss
            optimiser.zero_grad()
            loss.backward()
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
        }
        print(
            f"  {label} epoch {epoch + 1}/{epochs}: loss={stats['policy_loss']:.4f} "
            f"value_loss={stats['value_loss']:.4f} "
            f"action_match={stats['action_match']:.1%}"
        )

    # The number that says whether the fix worked: PPO's advantage estimate is
    # only as good as this. Below 0 the critic is worse than a constant.
    with torch.no_grad():
        predicted = model.policy.predict_values(obs_t).flatten()
        residual = torch.var(return_t - predicted)
        total = torch.var(return_t)
        stats["explained_variance"] = float(1 - residual / total) if total > 0 else 0.0
    print(f"  critic explained_variance on expert data: {stats['explained_variance']:.3f}")
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
    for round_index in range(rounds):
        fresh = collect_expert_data(
            data,
            episodes_per_round,
            gamma=gamma,
            actor=student_actor(model),
            seed_offset=seed_offset + round_index * episodes_per_round,
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
            "measured (+0.793 placement, t=+4.36, last-place rate 11.7% -> "
            "26.3%), while no leash is flat (+0.070, t=+0.38). See doc 99 "
            "entry 31. None disables"
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
        "--value-coef",
        type=float,
        default=0.5,
        help=(
            "weight on the value-regression term during behaviour cloning. "
            "0 reproduces the old policy-only clone, which left the critic at "
            "explained_variance -0.43 and made PPO degrade its own warm start "
            "(see docs/99_judgement_calls.md 18)"
        ),
    )
    parser.add_argument(
        "--shaping-mode",
        default="potential",
        choices=SHAPING_MODES,
        help=(
            "potential-based shaping is policy-invariant; 'bonus' is the "
            "earlier standing-payment form, kept for comparison "
            "(see docs/99_judgement_calls.md 6c.3)"
        ),
    )
    parser.add_argument(
        "--champion-encoding",
        default="index",
        choices=CHAMPION_ENCODINGS,
        help=(
            "how champions are encoded in the observation. 'features' "
            "describes role/stats/traits; 'index' is the legacy ordinal id "
            "(see docs/99_judgement_calls.md 6b.5)"
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
    model = MaskablePPO(
        "MlpPolicy",
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

    started = time.perf_counter()
    if args.warm_start:
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
